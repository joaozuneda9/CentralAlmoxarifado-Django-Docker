import uuid
from dataclasses import replace

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from catalogo.models import Opcao
from catalogo.saude import saude_do_catalogo
from pedidos import carrinho as carrinho_mod
from pedidos.consultas import (
    FiltrosPainel,
    contar_lotes_travados,
    filtrar_situacao,
    lotes_pendentes,
    nomes_scpi,
    pedidos_do_painel,
    unidades_scpi,
)
from pedidos.fluxos import FLUXOS
from pedidos.models import Atendimento, ExecucaoRobo, ItemPedido, Pedido
from pedidos.regras import (
    AVULSA,
    ERRO,
    Adicionado,
    DadosSaida,
    EnvioSaida,
    edicao_permitida,
    frase_diferenca,
    lote_todo_sem_lancar,
    qtd_br,
)
from pedidos.servicos import (
    catalogo_avulsa_por_codigo,
    catalogo_de,
    centros,
    centros_ativos,
    confirmar_atendimento,
    editar_atendimento,
    editar_saida_avulsa,
    erros_de_vinculo,
    item_catalogo_gravado,
    marcar_recibos_impressos,
    recibos_alterados,
    registrar_saida_avulsa,
    tetos_de_entrega,
    tipos_saida,
)
from pedidos.views.materiais import _carrinho, _materiais, contexto_busca, urls_do_fluxo

# O atendimento de um pedido sai sempre como balcão: o campo vem fixo no formulário.
TIPO_ATENDIMENTO = "BALCÃO"


@login_required
def painel(request):
    """Pedidos e saídas avulsas, mais recentes primeiro, com filtros e paginação via HTMX."""
    form = FiltrosPainel(request.GET)
    pagina = Paginator(pedidos_do_painel(form.filtros()), 25).get_page(request.GET.get("pagina"))
    contexto = {"pagina": pagina, "filtros": form}
    # Só o trecho para a troca do HTMX; ao restaurar o histórico (botão Voltar) o HTMX também
    # manda HX-Request, mas precisa da página inteira.
    parcial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    if parcial:
        resposta = render(request, "pedidos/_painel_lista.html", contexto)
        patch_vary_headers(resposta, ["HX-Request", "HX-History-Restore-Request"])
        return resposta
    contexto["saude"] = [item for item in saude_do_catalogo() if item.nivel != "ok"]
    contexto["recibos_pendentes"] = Atendimento.objects.filter(
        recibo_impresso_em__isnull=True
    ).count()
    contexto["pedidos_aguardando"] = filtrar_situacao(Pedido.objects.all(), "aguardando").count()
    contexto["lancamento_pendentes"] = lotes_pendentes()
    contexto["lancamento_travados"] = contar_lotes_travados()
    contexto["lancamento_em_andamento"] = ExecucaoRobo.em_andamento().exists()
    contexto["lancamento_real"] = settings.LANCAMENTO_REAL
    resposta = render(request, "pedidos/painel.html", contexto)
    patch_vary_headers(resposta, ["HX-Request", "HX-History-Restore-Request"])
    return resposta


def opcoes_saida(*, so_ativos: bool = False) -> dict:
    """Listas dos campos de uma saída: funcionários, centros, placas e tipos. Com `so_ativos` (a
    saída avulsa nova), o centro inativo não é oferecido; o atendimento e a edição listam todos
    (spec 009)."""
    linhas = centros_ativos() if so_ativos else centros()
    return {
        "funcionarios": Opcao.valores(Opcao.Lista.FUNCIONARIO),
        "centros": list(dict.fromkeys((c.descricao, c.codigo) for c in linhas)),
        "placas": sorted((c.placa, c.descricao) for c in linhas if c.placa),
        "tipos": tipos_saida(),
        "hoje": timezone.localdate().isoformat(),
    }


def dados_saida(post) -> tuple[DadosSaida, bool]:
    dados = DadosSaida(
        data=post.get("data", ""),
        recebedor=post.get("recebedor", ""),
        centro_custo=post.get("centro_custo", ""),
        tipo=post.get("tipo", ""),
        placa=post.get("placa", ""),
        obs=post.get("obs", ""),
    )
    return dados, "nao_lancar" in post


def _tipo_fixo(tipos: list[str], atendimento=None) -> str:
    """O tipo que o formulário do atendimento trava: BALCÃO, ou na edição o gravado (o importado
    das planilhas pode não ser BALCÃO). Sem BALCÃO nas opções, "" (o formulário libera a
    escolha)."""
    if TIPO_ATENDIMENTO not in tipos:
        return ""
    return atendimento.tipo_saida if atendimento is not None else TIPO_ATENDIMENTO


def _dados_do_atendimento(post, atendimento=None) -> tuple[DadosSaida, bool]:
    """Dados da saída do atendimento. O tipo é o travado (`_tipo_fixo`): o servidor não confia
    no `tipo` enviado. Sem tipo travado, vale o que veio."""
    dados, nao_lancar = dados_saida(post)
    tipos = tipos_saida()
    if TIPO_ATENDIMENTO in tipos:
        dados = replace(dados, tipo=_tipo_fixo(tipos, atendimento))
    return dados, nao_lancar


def _entregas_enviadas(pedido, post) -> tuple[dict[str, str], list[Adicionado]]:
    """As quantidades entregues (itens pedidos e acrescentados) e os acrescentados do POST."""
    qtds = {i.codigo: post.get(f"entregue-{i.codigo}", "") for i in pedido.itens.all()}
    adicionados = _adicionados_enviados(post)
    qtds.update({a.codigo: post.get(f"entregue-{a.codigo}", "") for a in adicionados})
    return qtds, adicionados


def _lote_com_erro(linhas) -> bool:
    return any(linha.status == ERRO for linha in linhas)


def _campos_gravados(atendimento, linhas) -> tuple[dict, bool]:
    """Os dados gravados da saída, para preencher o formulário de edição. "Não lançar" marcado em
    Automações muda as linhas, não o atendimento: o formulário o mostra marcado, e salvar o grava
    no atendimento (a recriação das linhas não o desfaz)."""
    campos = {
        "data": atendimento.data_efetiva.isoformat(),
        "recebedor": atendimento.recebedor,
        "centro_custo": atendimento.centro_custo,
        "tipo": atendimento.tipo_saida,
        "placa": atendimento.placa,
        "obs": atendimento.obs,
    }
    nao_lancar = atendimento.nao_lancar or lote_todo_sem_lancar(linha.status for linha in linhas)
    return campos, nao_lancar


def _pedido(numero):
    consulta = Pedido.objects.select_related(
        "atendimento",
        "atendimento__atendido_por",
        "registrado_por",
        "autorizacao",
        "autorizacao__decidido_por",
    ).prefetch_related("itens", "atendimento__linhas")
    return get_object_or_404(consulta, numero=numero)


def _saida_do_destino(destino: str, opcoes: dict) -> dict:
    """Centro de custo e placa sugeridos pelo destino do pedido ("centro" ou "centro — placa",
    como em `regras.opcoes_destino`). Com placa, o centro é o dela, que o formulário trava."""
    for placa, descricao in opcoes["placas"]:
        if destino == f"{descricao} — {placa}":
            return {"centro_custo": descricao, "placa": placa}
    if any(destino == descricao for descricao, _ in opcoes["centros"]):
        return {"centro_custo": destino}
    return {}


def _contexto_edicao(pedido) -> dict:
    """Se o atendimento ainda pode ser editado (botão, avisos) e o histórico das edições."""
    atendimento = pedido.atendimento_ou_none
    if atendimento is None:
        return {"edicao": edicao_permitida(False, [])}
    linhas = pedido.linhas
    return {
        "edicao": edicao_permitida(True, linhas),
        "lote_com_erro": _lote_com_erro(linhas),
        "alteracoes": list(pedido.alteracoes.select_related("usuario")),
    }


def _contexto_detalhe(pedido, **extra) -> dict:
    autorizacao = pedido.autorizacao_ou_none
    contexto = {
        "pedido": pedido,
        "atendivel": False,
        "autorizacao": autorizacao,
        "unidades_scpi": unidades_scpi([pedido]),
        "nomes_scpi": nomes_scpi([pedido]),
        **_contexto_edicao(pedido),
    }
    # O pedido de EPI só abre o atendimento depois de autorizado (spec 008).
    if (
        pedido.origem != AVULSA
        and pedido.atendimento_ou_none is None
        and pedido.atendimento_liberado
    ):
        opcoes = opcoes_saida()
        contexto.update(
            atendivel=True,
            atendimento_id=uuid.uuid4(),
            campos={
                "data": timezone.localdate().isoformat(),
                **_saida_do_destino(pedido.destino, opcoes),
            },
            entregues={i.codigo: qtd_br(i.qtd_pedida) for i in _itens_pedidos(pedido)},
            tetos=tetos_de_entrega(_itens_pedidos(pedido)),
            tipo_fixo=_tipo_fixo(opcoes["tipos"]),
            **opcoes,
        )
    contexto.update(extra)
    return contexto


@login_required
def detalhe(request, numero):
    """Recibo do pedido na tela e, enquanto não atendido, o formulário de atendimento."""
    return render(request, "pedidos/detalhe.html", _contexto_detalhe(_pedido(numero)))


@login_required
@require_POST
def atender(request, numero):
    pedido = _pedido(numero)
    try:
        atendimento_id = uuid.UUID(request.POST.get("atendimento_id", ""))
    except ValueError:
        messages.error(request, "Identificador do atendimento inválido. Recarregue a página.")
        return redirect("pedidos:detalhe", numero=numero)
    dados, nao_lancar = _dados_do_atendimento(request.POST)
    qtds, adicionados = _entregas_enviadas(pedido, request.POST)
    resposta = confirmar_atendimento(
        pedido.id,
        atendimento_id,
        dados,
        qtds,
        nao_lancar=nao_lancar,
        usuario=request.user,
        adicionados=adicionados,
    )
    if resposta.ok:
        texto = "já estava registrado" if resposta.reenvio else "registrado"
        messages.success(request, f"Atendimento do pedido {numero} {texto}.")
        return redirect("pedidos:detalhe", numero=numero)
    if not resposta.erros:
        messages.error(request, resposta.mensagem)
        return redirect("pedidos:detalhe", numero=numero)
    contexto = _contexto_detalhe(
        pedido,
        atendimento_id=atendimento_id,
        campos=request.POST,
        nao_lancar=nao_lancar,
        entregues=qtds,
        adicionados=_linhas_adicionadas(pedido, adicionados, qtds),
        codigos_erro={e.codigo for e in resposta.erros if e.codigo},
        mensagem=resposta.mensagem,
        erros=resposta.erros,
    )
    return render(request, "pedidos/detalhe.html", contexto)


def _linha_gravada(item: ItemPedido, nomes: dict[str, str], por_id: dict) -> dict:
    """Material acrescentado já gravado, no formato de `_linha_adicionada`: o nome é o do SCPI
    (`nomes`, como na tabela do detalhe) e, se o código saiu do cadastro, o do próprio item; a
    unidade é a do item. O trocado vem dos itens já lidos (`por_id`), sem outra consulta."""
    trocado = por_id.get(item.no_lugar_de_id)
    return {
        "item": None,
        "codigo": item.codigo,
        "nome": nomes.get(item.codigo) or item.material,
        "unidade": item.unidade,
        "qtd": qtd_br(item.qtd_entregue),
        "no_lugar_de": trocado.codigo if trocado else "",
        "no_lugar_de_nome": (nomes.get(trocado.codigo) or trocado.material) if trocado else "",
    }


def _contexto_edicao_atendimento(pedido, **extra) -> dict:
    """O detalhe com o formulário do atendimento preenchido com o que está gravado."""
    atendimento = pedido.atendimento
    opcoes = opcoes_saida()
    nomes = nomes_scpi([pedido])
    campos, nao_lancar = _campos_gravados(atendimento, pedido.linhas)
    itens = list(pedido.itens.all())
    por_id = {i.id: i for i in itens}
    contexto = {
        "atendivel": True,
        "editando": True,
        "acompanhar_robo": _acompanhar_robo(),
        "versao": pedido.versao,
        "campos": campos,
        "nao_lancar": nao_lancar,
        "entregues": {i.codigo: qtd_br(i.qtd_entregue) for i in _itens_pedidos(pedido)},
        "tetos": tetos_de_entrega(_itens_pedidos(pedido)),
        "adicionados": [
            _linha_gravada(i, nomes, por_id)
            for i in itens
            if i.origem == ItemPedido.Origem.ALMOXARIFADO
        ],
        "tipo_fixo": _tipo_fixo(opcoes["tipos"], atendimento),
        **opcoes,
    }
    contexto.update(extra)
    return _contexto_detalhe(pedido, **contexto)


def _recusa_da_edicao(resposta) -> dict:
    """O que a faixa do modo de edição mostra quando o salvar foi recusado sem erro de campo
    (o lote entrou em lançamento, ou outra pessoa salvou antes)."""
    return {
        "editando": True,
        "recusa_edicao": resposta.motivo,
        "mensagem_edicao": resposta.mensagem,
        "nao_gravadas": [frase_diferenca(d) for d in resposta.diferencas],
    }


def _avisar_salvo(request, resposta, recibo_estava_impresso: bool) -> None:
    texto = resposta.mensagem
    if resposta.diferencas and recibo_estava_impresso:
        texto += " O recibo voltou para impressão."
    messages.success(request, texto)
    if resposta.diferencas:
        messages.info(
            request, "O que mudou: " + "; ".join(frase_diferenca(d) for d in resposta.diferencas)
        )


FAIXA_DA_EDICAO = "div#edicao-faixa"


def _acompanhar_robo() -> bool:
    """Com o robô lançando, a faixa do modo de edição se recarrega para avisar se o lote travou."""
    return ExecucaoRobo.em_andamento().exists()


def _faixa(request, pedido, edicao):
    """Só a faixa do modo de edição, pedida pela recarga periódica (`HX-Target`)."""
    contexto = {
        "pedido": pedido,
        "edicao": edicao,
        "edicao_encerrada": not edicao.permitida,
        "acompanhar_robo": edicao.permitida and _acompanhar_robo(),
        "lote_com_erro": _lote_com_erro(pedido.linhas),
    }
    resposta = render(request, "pedidos/_edicao_faixa.html", contexto)
    patch_vary_headers(resposta, ["HX-Request", "HX-Target"])
    return resposta


@login_required
def editar(request, numero):
    """Modo de edição do atendimento (ou da saída avulsa) até o robô lançar o lote no SCPI."""
    pedido = _pedido(numero)
    atendimento = pedido.atendimento_ou_none
    edicao = edicao_permitida(atendimento is not None, pedido.linhas)
    if (
        request.method != "POST"
        and request.headers.get("HX-Request")
        and request.headers.get("HX-Target") == FAIXA_DA_EDICAO
    ):
        return _faixa(request, pedido, edicao)
    if request.method != "POST":
        if not edicao.permitida:
            if edicao.motivo:
                messages.info(request, edicao.motivo)
            return redirect("pedidos:detalhe", numero=numero)
        if pedido.origem != AVULSA:
            return render(request, "pedidos/detalhe.html", _contexto_edicao_atendimento(pedido))
    if pedido.origem == AVULSA:
        return _editar_avulsa(request, pedido)

    try:
        versao = int(request.POST.get("versao", ""))
    except ValueError:
        messages.error(request, "Versão do pedido inválida. Abra a edição de novo.")
        return redirect("pedidos:detalhe", numero=numero)
    recibo_estava_impresso = bool(atendimento and atendimento.recibo_impresso_em)
    dados, nao_lancar = _dados_do_atendimento(request.POST, atendimento)
    qtds, adicionados = _entregas_enviadas(pedido, request.POST)
    resposta = editar_atendimento(
        pedido.id,
        versao,
        dados,
        qtds,
        nao_lancar=nao_lancar,
        adicionados=adicionados,
        usuario=request.user,
    )
    if resposta.ok:
        _avisar_salvo(request, resposta, recibo_estava_impresso)
        return redirect("pedidos:detalhe", numero=numero)
    pedido = _pedido(numero)
    if resposta.motivo:
        contexto = _contexto_detalhe(pedido, **_recusa_da_edicao(resposta))
        return render(request, "pedidos/detalhe.html", contexto)
    if not resposta.erros:
        messages.error(request, resposta.mensagem)
        return redirect("pedidos:detalhe", numero=numero)
    contexto = _contexto_edicao_atendimento(
        pedido,
        versao=versao,
        campos=request.POST,
        nao_lancar=nao_lancar,
        entregues=qtds,
        adicionados=_linhas_adicionadas(pedido, adicionados, qtds),
        codigos_erro={e.codigo for e in resposta.erros if e.codigo},
        mensagem=resposta.mensagem,
        erros=resposta.erros,
    )
    return render(request, "pedidos/detalhe.html", contexto)


def _editar_avulsa(request, pedido):
    """Modo de edição da saída avulsa: o formulário da saída avulsa, com o carrinho e os dados
    da saída gravados. A tela só é montada quando é mostrada (o salvar que dá certo não a paga), e
    o catálogo vai pronto para o serviço."""
    fluxo = FLUXOS["avulsa"]
    catalogo = catalogo_de(fluxo.origem)
    atendimento = pedido.atendimento

    def tela(**extra):
        por_codigo = {i.codigo: i for i in catalogo or []}
        linhas = pedido.linhas
        campos, nao_lancar = _campos_gravados(atendimento, linhas)
        contexto = {
            "fluxo": fluxo,
            "indisponivel": catalogo is None,
            "editando": True,
            "acompanhar_robo": _acompanhar_robo(),
            "pedido": pedido,
            "versao": pedido.versao,
            "lote_com_erro": _lote_com_erro(linhas),
            "campos": campos,
            "nao_lancar": nao_lancar,
            # Material já na saída aparece mesmo que tenha saído do catálogo.
            "carrinho": carrinho_mod.Carrinho(
                [
                    carrinho_mod.LinhaCarrinho(
                        i.codigo,
                        i.qtd_entregue,
                        por_codigo.get(i.codigo) or item_catalogo_gravado(i),
                    )
                    for i in pedido.itens.all()
                ]
            ),
            "codigos_erro": set(),
            "filtros": [],
            **contexto_busca(fluxo, catalogo or []),
            **urls_do_fluxo(fluxo),
            **opcoes_saida(),
            **extra,
        }
        return render(request, "pedidos/avulsa.html", contexto)

    if request.method != "POST":
        return tela()

    try:
        versao = int(request.POST.get("versao", ""))
    except ValueError:
        messages.error(request, "Versão da saída inválida. Abra a edição de novo.")
        return redirect("pedidos:detalhe", numero=pedido.numero)
    recibo_estava_impresso = bool(atendimento.recibo_impresso_em)
    dados, nao_lancar = dados_saida(request.POST)
    envio = EnvioSaida(dados, carrinho_mod.itens_enviados(request.POST), nao_lancar)
    resposta = editar_saida_avulsa(
        pedido.id, versao, envio, usuario=request.user, catalogo=catalogo
    )
    if resposta.ok:
        _avisar_salvo(request, resposta, recibo_estava_impresso)
        return redirect("pedidos:detalhe", numero=pedido.numero)
    if resposta.motivo:
        contexto = _contexto_detalhe(_pedido(pedido.numero), **_recusa_da_edicao(resposta))
        return render(request, "pedidos/detalhe.html", contexto)
    if not resposta.erros:
        messages.error(request, resposta.mensagem)
        return redirect("pedidos:detalhe", numero=pedido.numero)
    return tela(
        versao=versao,
        campos=request.POST,
        nao_lancar=nao_lancar,
        carrinho=carrinho_mod.Carrinho(carrinho_mod.ler(request.POST, fluxo, catalogo)),
        mensagem=resposta.mensagem,
        erros=resposta.erros,
        codigos_erro={e.codigo for e in resposta.erros if e.codigo},
    )


def _adicionados_enviados(post) -> list[Adicionado]:
    """Os materiais acrescentados na página (`adicionado` repetido, na ordem em que entraram)
    e o item pedido que cada um substitui (`no-lugar-de-<codigo>`, vazio sem troca)."""
    return [Adicionado(c, post.get(f"no-lugar-de-{c}", "")) for c in post.getlist("adicionado")]


def _itens_pedidos(pedido) -> list[ItemPedido]:
    return [i for i in pedido.itens.all() if i.origem == ItemPedido.Origem.PEDIDO]


def _linha_adicionada(pedido, a: Adicionado, qtd: str, catalogo: dict) -> dict:
    """O que `_adicionado.html` desenha de um acrescentado: o material do catálogo da saída
    avulsa (a unidade é a do SCPI), a quantidade digitada e o item pedido que ele substitui."""
    item = catalogo.get(a.codigo)
    trocado = next((i for i in _itens_pedidos(pedido) if i.codigo == a.no_lugar_de), None)
    # Fora do catálogo (acrescentado gravado que ficou oculto, na edição): o nome gravado.
    gravado = next((i for i in pedido.itens.all() if i.codigo == a.codigo), None)
    return {
        "item": item,
        "codigo": a.codigo,
        "nome": item.nome if item else (gravado.material if gravado else a.codigo),
        "unidade": item.unidade if item else (gravado.unidade if gravado else ""),
        "qtd": qtd,
        "no_lugar_de": a.no_lugar_de,
        "no_lugar_de_nome": trocado.material if trocado else a.no_lugar_de,
    }


def _linhas_adicionadas(pedido, adicionados, qtds) -> list[dict]:
    catalogo = catalogo_avulsa_por_codigo() if adicionados else {}
    return [_linha_adicionada(pedido, a, qtds.get(a.codigo, ""), catalogo) for a in adicionados]


def _pedido_com_atendimento_aberto(numero):
    """Pedido (não avulso) ainda por atender, ou atendido e ainda editável: só nele se
    acrescenta ou troca material."""
    pedido = _pedido(numero)
    atendido = pedido.atendimento_ou_none is not None
    if (
        pedido.origem == AVULSA
        or (atendido and not edicao_permitida(True, pedido.linhas).permitida)
        # Pedido de EPI aguardando ou recusado não tem atendimento aberto (spec 008).
        or not pedido.atendimento_liberado
    ):
        raise Http404("Pedido sem atendimento aberto.")
    return pedido


@login_required
def atendimento_materiais(request, numero):
    """Busca do material que o almoxarifado acrescenta ao atendimento (troca ou acréscimo):
    catálogo da saída avulsa, com o resultado entrando no grupo dos acrescentados. Na troca
    (`no_lugar_de`), a quantidade já vem com a pedida do item trocado."""
    pedido = _pedido_com_atendimento_aberto(numero)
    fluxo = FLUXOS["avulsa"]
    no_lugar_de = request.GET.get("no_lugar_de", "")
    trocado = next((i for i in _itens_pedidos(pedido) if i.codigo == no_lugar_de), None)
    contexto = {
        "fluxo": fluxo,
        **contexto_busca(
            fluxo,
            catalogo_de(fluxo.origem) or [],
            request.GET.get("q", ""),
            request.GET.get("filtro", ""),
        ),
        "url_carrinho": reverse("pedidos:atendimento_adicionar", args=[pedido.numero]),
        # O painel do atendimento já é a escolha: cada resultado adiciona (ou troca) direto.
        "um_passo": True,
        "alvo_resultado": "#adicionados",
        "troca_resultado": "beforeend",
        # Cada clique anexa uma linha: com um pedido em voo, o segundo clique é descartado.
        "sincronia_resultado": "drop",
        # O botão fica no formulário do painel (quantidade, CSRF e `no_lugar_de` vão junto);
        # os acrescentados já na página vêm do formulário do atendimento.
        "inclusao_resultado": (
            "[name=adicionado], [name^=no-lugar-de-], [data-atendimento-painel] [name=no_lugar_de]"
        ),
    }
    if trocado is not None:
        contexto["qtd_inicial"] = qtd_br(trocado.qtd_pedida)
        # Na troca, a ação dos resultados é "Trocar" (primária), não "Adicionar".
        contexto["acao_rotulo"] = "Trocar"
        contexto["acao_aria"] = f"Trocar {trocado.material} por"
        contexto["acao_primaria"] = True
    return render(request, "pedidos/_resultados.html", contexto)


@login_required
@require_POST
def atendimento_adicionar(request, numero):
    """Linha do material acrescentado, a juntar ao grupo dos acrescentados da página. Recusado
    (fora do catálogo, bloqueado, repetido, troca inválida ou quantidade inválida), devolve só
    a mensagem, com status 200 (o `htmx-config` não troca respostas 4xx) e o alvo trocado para
    `#adicionar-erro`."""
    pedido = _pedido_com_atendimento_aberto(numero)
    catalogo = catalogo_avulsa_por_codigo()
    codigo = request.POST.get("adicionar", "").strip()
    novo = Adicionado(codigo, request.POST.get("no_lugar_de", "").strip())
    item = catalogo.get(codigo)
    erro = carrinho_mod.recusa_do_material(FLUXOS["avulsa"], item)
    if not erro:
        # Os casos de repetição e troca da confirmação, contra os pedidos e os acrescentados
        # que já estão na página: só os erros que o novo (o último da lista) acrescenta.
        existentes = _adicionados_enviados(request.POST)
        itens = _itens_pedidos(pedido)
        _, antes = erros_de_vinculo(existentes, itens, catalogo)
        _, depois = erros_de_vinculo([*existentes, novo], itens, catalogo)
        if len(depois) > len(antes):
            erro = depois[len(antes)].texto
    if not erro:
        # A equipe aceita fração em qualquer unidade e em pedido de qualquer origem: vale a regra
        # da saída avulsa, maior que zero.
        qtd, erro = carrinho_mod.quantidade(FLUXOS["avulsa"], request.POST.get(f"qtd-{codigo}", ""))
        # O material vem do catálogo da saída avulsa: o teto é o saldo dele, qualquer que seja
        # a origem do pedido.
        erro = erro or carrinho_mod.acima_do_estoque(FLUXOS["avulsa"], item, qtd)
    if erro:
        resposta = render(request, "pedidos/_adicionado.html", {"erro": erro})
        resposta["HX-Retarget"] = "#adicionar-erro"
        resposta["HX-Reswap"] = "innerHTML"
        return resposta
    linha = _linha_adicionada(pedido, novo, qtd_br(qtd), catalogo)
    return render(request, "pedidos/_adicionado.html", {"pedido": pedido, "a": linha})


@login_required
def avulsa_materiais(request):
    return _materiais(request, FLUXOS["avulsa"])


@login_required
@require_POST
def avulsa_carrinho(request):
    return _carrinho(request, FLUXOS["avulsa"])


@login_required
def avulsa(request):
    """Saída registrada direto pelo almoxarifado, sem pedido anterior. A tela só é montada quando
    é mostrada (o registro que dá certo não a paga), e o catálogo vai pronto para o serviço."""
    fluxo = FLUXOS["avulsa"]
    catalogo = catalogo_de(fluxo.origem)

    def tela(**extra):
        contexto = {
            "fluxo": fluxo,
            "indisponivel": catalogo is None,
            "envio_id": uuid.uuid4(),
            "campos": {"data": timezone.localdate().isoformat()},
            "carrinho": carrinho_mod.Carrinho(),
            "codigos_erro": set(),
            "filtros": [],
            **contexto_busca(fluxo, catalogo or []),
            **urls_do_fluxo(fluxo),
            **opcoes_saida(so_ativos=True),
            **extra,
        }
        return render(request, "pedidos/avulsa.html", contexto)

    if request.method != "POST":
        return tela()

    dados, nao_lancar = dados_saida(request.POST)
    enviado = {
        "campos": request.POST,
        "nao_lancar": nao_lancar,
        "carrinho": carrinho_mod.Carrinho(carrinho_mod.ler(request.POST, fluxo, catalogo)),
    }
    try:
        envio_id = uuid.UUID(request.POST.get("envio_id", ""))
    except ValueError:
        return tela(**enviado, mensagem="Identificador do envio inválido. Recarregue a página.")
    envio = EnvioSaida(dados, carrinho_mod.itens_enviados(request.POST), nao_lancar)
    resposta = registrar_saida_avulsa(envio_id, envio, usuario=request.user, catalogo=catalogo)
    if resposta.ok:
        if resposta.reenvio:
            texto = f"Saída já registrada (reenvio confirmado): Nº {resposta.numero}."
        else:
            texto = f"Saída avulsa registrada: Nº {resposta.numero}."
        messages.success(request, texto)
        return redirect("pedidos:detalhe", numero=resposta.numero)
    return tela(
        **enviado,
        envio_id=uuid.uuid4() if resposta.divergente else envio_id,
        divergente=resposta.divergente,
        mensagem=resposta.mensagem,
        erros=resposta.erros,
        codigos_erro={e.codigo for e in resposta.erros if e.codigo},
    )


@login_required
@require_POST
def marcar_impressos(request):
    ids, versoes = [], {}
    for valor in request.POST.getlist("atendimento"):
        try:
            atendimento_id = uuid.UUID(valor)
        except ValueError:
            continue
        ids.append(atendimento_id)
        versao = request.POST.get(f"versao-{valor}", "")
        if versao.isdigit():
            versoes[atendimento_id] = int(versao)
    alterados = recibos_alterados(versoes)
    n = marcar_recibos_impressos(ids, versoes=versoes)
    if alterados:
        messages.warning(
            request, "O pedido foi alterado depois de abrir esta página; imprima de novo."
        )
    if n == 1:
        messages.success(request, "1 recibo marcado como impresso.")
    elif n:
        messages.success(request, f"{n} recibos marcados como impressos.")
    elif not alterados:
        messages.info(
            request, "Nenhum recibo novo para marcar: todos já estavam marcados como impressos."
        )
    voltar = request.POST.get("voltar", "")
    if url_has_allowed_host_and_scheme(
        voltar, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(voltar)
    return redirect("pedidos:painel")
