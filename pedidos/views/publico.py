from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from pedidos import carrinho as carrinho_mod
from pedidos.fluxos import fluxo_da_origem, fluxo_publico, fluxos_publicos, opcoes_filtro
from pedidos.models import ItemPedido, Pedido
from pedidos.protecao import (
    CAMPO_ISCA,
    MENSAGEM_RAPIDO,
    MENSAGEM_RECUSA,
    MENSAGEM_TOKEN_INVALIDO,
    MOTIVO_ISCA,
    emitir,
    ler,
    recusar,
)
from pedidos.regras import (
    EnvioPedido,
    nome_confere,
    numero_de_pedido_publico,
    opcoes_destino,
    resolver_destino,
    texto_consulta_publica,
)
from pedidos.servicos import catalogo_de, centros_do_fluxo, registrar_pedido
from pedidos.views.materiais import contexto_busca, urls_do_fluxo


def inicio(request):
    """Página pública dos funcionários (sem login)."""
    publicos = fluxos_publicos()
    return render(
        request,
        "pedidos/inicio.html",
        {
            "fluxos_publicos": [f for f in publicos if not f.geral],
            "fluxos_gerais": [f for f in publicos if f.geral],
        },
    )


def _contexto(fluxo, catalogo, envio, **extra) -> dict:
    destinos = opcoes_destino(centros_do_fluxo(fluxo))
    contexto = {
        "fluxo": fluxo,
        "envio": envio,
        "indisponivel": catalogo is None,
        # Há itens, mas o máximo pedível de todos é zero: o formulário abre com um aviso no topo.
        "sem_estoque_agora": bool(catalogo)
        and all(carrinho_mod.limite(fluxo, i) <= 0 for i in catalogo),
        "sem_destinos": not destinos,
        "destinos": destinos,
        # Quantas peças a folha mostra (a dica do botão); 0 sem folha.
        "n_folha": len(carrinho_mod.pecas_da_folha(fluxo, catalogo)),
        "filtros": opcoes_filtro(fluxo, catalogo),
        "carrinho": carrinho_mod.Carrinho(),
        "campos": {},
        "codigos_erro": set(),
        "erros_por_campo": {},
        **contexto_busca(fluxo, catalogo or []),
        **urls_do_fluxo(fluxo),
    }
    contexto.update(extra)
    return contexto


def formulario(request, fluxo):
    """Formulário de pedido (limpeza, AB ou viaturas). O envio vem pelo HTMX, e a resposta
    substitui o formulário: o sucesso não tem URL própria, para o número não virar página
    pública."""
    fluxo = fluxo_publico(fluxo)
    catalogo = catalogo_de(fluxo.origem)
    parcial = bool(request.headers.get("HX-Request"))
    if request.method != "POST":
        return render(request, "pedidos/formulario.html", _contexto(fluxo, catalogo, emitir()))

    nomes = (
        ("solicitante", "destino", "obs", "ocorrencia")
        if fluxo.pede_ocorrencia
        else ("solicitante", "destino", "obs")
    )
    campos = {c: request.POST.get(c, "") for c in nomes}

    def de_volta(envio, **extra):
        contexto = _contexto(
            fluxo,
            catalogo,
            envio,
            campos=campos,
            carrinho=carrinho_mod.Carrinho(
                carrinho_mod.ler(request.POST, fluxo, catalogo, manter_ilegiveis=True)
            ),
            **extra,
        )
        modelo = "pedidos/_formulario.html" if parcial else "pedidos/formulario.html"
        return render(request, modelo, contexto)

    envio = ler(request.POST.get("token", ""))
    if envio is None:
        return de_volta(emitir(), mensagem=MENSAGEM_TOKEN_INVALIDO)
    if motivo := recusar(envio, request.POST.get(CAMPO_ISCA, "")):
        # Só a isca (que uma pessoa nunca preenche) recebe a mensagem genérica.
        return de_volta(
            envio, mensagem=MENSAGEM_RECUSA if motivo == MOTIVO_ISCA else MENSAGEM_RAPIDO
        )

    # O texto como está no cadastro; o que não existe segue como veio, para a validação recusar.
    destino = resolver_destino(campos["destino"], centros_do_fluxo(fluxo)) or campos["destino"]
    pedido = EnvioPedido(
        solicitante=campos["solicitante"],
        destino=destino,
        obs=campos["obs"],
        ocorrencia=campos.get("ocorrencia", ""),
        itens=carrinho_mod.itens_enviados(request.POST),
    )
    resposta = registrar_pedido(
        fluxo.origem,
        envio.id,
        pedido,
        ip=request.META.get("REMOTE_ADDR"),
        # Botão do aviso: a fila de autorização (a Segurança do Trabalho recebe) ou o painel.
        url_painel=request.build_absolute_uri(
            reverse("pedidos:autorizacoes" if fluxo.exige_autorizacao else "pedidos:painel")
        ),
        # O mesmo que a tela usa na volta com erro: o envio monta o catálogo uma vez só.
        catalogo=catalogo,
    )
    if resposta.ok:
        # `_sucesso.html` lista só o que o funcionário pediu (filtro por segurança).
        itens = list(resposta.pedido.itens.filter(origem=ItemPedido.Origem.PEDIDO))
        contexto = {
            "fluxo": fluxo,
            "resposta": resposta,
            "itens": itens,
            "n_itens": len(itens),
        }
        if parcial:
            return render(request, "pedidos/_sucesso.html", contexto)
        return render(request, "pedidos/formulario.html", {**contexto, "sucesso": True})
    if resposta.divergente:
        envio = emitir(aberto_em=envio.aberto_em)
    return de_volta(
        envio,
        mensagem=resposta.mensagem,
        erros=resposta.erros,
        divergente=resposta.divergente,
        codigos_erro={e.codigo for e in resposta.erros if e.codigo},
        erros_por_campo=_por_campo(resposta.erros),
    )


def _por_campo(erros) -> dict[str, list[str]]:
    """{campo: [textos]} dos erros de um campo do formulário, para mostrá-los junto dele."""
    por_campo: dict[str, list[str]] = {}
    for erro in erros:
        if erro.campo:
            por_campo.setdefault(erro.campo, []).append(erro.texto)
    return por_campo


MENSAGEM_CONSULTA_VAZIA = "Informe o número do pedido."
MENSAGEM_CONSULTA_INVALIDA = (
    "Este não é um número de pedido. O número começa com P, como P-000123, e aparece na tela de "
    "confirmação do envio."
)
MENSAGEM_CONSULTA_SEM_NOME = "Informe o seu primeiro nome, como foi escrito no pedido."
# A mesma para número inexistente, saída avulsa e nome que não confere: a resposta nunca diz que o
# número existe.
MENSAGEM_CONSULTA_NAO_ACHADA = (
    "Não encontramos um pedido com este número e este nome. Confira os dois na tela de confirmação "
    "do envio."
)
MENSAGEM_CONSULTA_LIMITE = (
    "Muitas consultas desta rede em pouco tempo. Tente de novo daqui a 10 minutos ou procure o "
    "almoxarifado."
)
JANELA_DAS_CONSULTAS = 10 * 60  # segundos


def _consultas_demais(ip: str) -> bool:
    """Conta esta consulta e diz se a origem passou do limite da janela. O contador vive no cache
    do processo (um só): zerar numa reinicialização é aceitável para um limite contra varredura
    de números (research R6), e evita uma tabela só para isso."""
    chave = f"consulta_pedido:{ip}"
    cache.add(chave, 0, timeout=JANELA_DAS_CONSULTAS)
    try:
        n = cache.incr(chave)
    except ValueError:  # a chave venceu entre o `add` e o `incr`
        cache.set(chave, 1, timeout=JANELA_DAS_CONSULTAS)
        n = 1
    return n > settings.PEDIDOS_CONSULTA_LIMITE_IP_10_MIN


@never_cache
@require_http_methods(["GET", "POST"])
def consulta(request):
    """O solicitante, sem login, consulta pelo número e pelo primeiro nome a situação de um pedido
    de qualquer formulário público (spec 011). Mostra só o que a seção 4 da spec permite: número,
    formulário, dia do envio, situação, a data que a explica, na recusa do EPI o motivo, e os
    materiais com as quantidades pedidas. Número que não existe, saída avulsa e nome que não
    confere têm a mesma resposta; só lê (nada é gravado). Também responde na rota antiga da
    consulta de EPIs (`pedidos:consulta_epi`)."""
    contexto = {"numero": "", "nome": ""}
    status = 200
    if request.method == "POST":
        digitado = request.POST.get("numero", "")
        nome = request.POST.get("nome", "")
        contexto.update(numero=digitado, nome=nome)
        numero = numero_de_pedido_publico(digitado)
        if _consultas_demais(request.META.get("REMOTE_ADDR", "")):
            contexto["aviso"] = MENSAGEM_CONSULTA_LIMITE
            status = 429
        elif not "".join(digitado.split()):
            contexto["aviso"] = MENSAGEM_CONSULTA_VAZIA
        elif numero is None:
            contexto["aviso"] = MENSAGEM_CONSULTA_INVALIDA
        elif not "".join(nome.split()):
            contexto["aviso"] = MENSAGEM_CONSULTA_SEM_NOME
        else:
            pedido = (
                Pedido.objects.select_related("atendimento", "autorizacao")
                .prefetch_related("itens")
                .filter(numero=numero, origem__in=[f.origem for f in fluxos_publicos()])
                .first()
            )
            if pedido is None or not nome_confere(nome, pedido.solicitante):
                contexto["aviso"] = MENSAGEM_CONSULTA_NAO_ACHADA
            else:
                contexto["resultado"] = _resultado_da_consulta(pedido)
    return render(request, "pedidos/consulta.html", contexto, status=status)


def _resultado_da_consulta(pedido: Pedido) -> dict:
    autorizacao = pedido.autorizacao_ou_none
    atendimento = pedido.atendimento_ou_none
    decidido_em = autorizacao.decidido_em if autorizacao else None
    return {
        "numero": pedido.numero,
        "formulario": fluxo_da_origem(pedido.origem).titulo,
        "enviado_em": timezone.localdate(pedido.criado_em),
        # Só o que o solicitante pediu, com a quantidade pedida (como na tela de sucesso): nem o
        # acrescentado pelo almoxarifado, nem a quantidade entregue. Vem do prefetch.
        "itens": [i for i in pedido.itens.all() if i.origem == ItemPedido.Origem.PEDIDO],
        "consulta": texto_consulta_publica(
            pedido.situacao,
            autorizacao=autorizacao.situacao if autorizacao else None,
            motivo=autorizacao.motivo if autorizacao else "",
            decidido_em=timezone.localdate(decidido_em) if decidido_em else None,
            saida_em=atendimento.data_efetiva if atendimento else None,
        ),
    }
