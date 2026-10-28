"""Gravação de pedidos, atendimentos e saídas: o único lugar que grava em `pedidos`.

Cada operação é uma transação, e a trava da `Sequencia` serializa os registros: dois envios
do mesmo identificador nunca gravam os dois. Erro de negócio não é exceção: a `Resposta`
leva a lista do que corrigir.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from catalogo.catalogos import ItemCatalogo
from catalogo.models import CentroCusto, Opcao
from contas.acesso import da_seguranca_trabalho
from pedidos.fluxos import fluxo_da_origem
from pedidos.models import (
    TRAVA_LANCAMENTO,
    AlteracaoPedido,
    Atendimento,
    AutorizacaoPedido,
    ExecucaoRobo,
    ItemPedido,
    LinhaSaida,
    Pedido,
    Sequencia,
)
from pedidos.regras import (
    AVULSA,
    EM_LANCAMENTO,
    ERRO,
    LANCADA,
    NAO_LANCAR,
    PENDENTE,
    ROTULOS_CABECALHO,
    TIPOS_SAIDA_PADRAO,
    VERIFICAR,
    Adicionado,
    Centro,
    CentroResolvido,
    DadosSaida,
    EnvioPedido,
    EnvioSaida,
    Erro,
    EstadoAtendimento,
    ItemSaida,
    atendimento_confere,
    cabecalho_saida,
    diferencas_atendimento,
    edicao_permitida,
    marcado_nao_lancar,
    norm_placa,
    norm_u,
    parse_qtd_br,
    qtd_br,
    registro_confere,
    requisicao_valida,
    somar_por_codigo,
    texto,
    truncar_qtd,
    validar_pedido,
    validar_saida,
)
from pedidos.telegram import notificar_autorizacao_pendente, notificar_pedido
from scpi.execucao import trava

logger = logging.getLogger("pedidos")


@dataclass
class Resposta:
    ok: bool
    mensagem: str = ""
    erros: list[Erro] = field(default_factory=list)
    estoque_atual: dict[str, int | Decimal] = field(default_factory=dict)
    numero: str = ""
    reenvio: bool = False
    divergente: bool = False
    pedido: Pedido | None = None
    telegram: str = ""
    # Por que a operação foi recusada: na edição, "lancamento" ou "versao"; na decisão da
    # autorização, "grupo", "decisao", "motivo", "nao_encontrada" ou "ja_decidida".
    motivo: str = ""
    diferencas: list[dict] = field(default_factory=list)
    autorizacao: AutorizacaoPedido | None = None  # a decisão gravada (ou já gravada) do pedido


def mensagem_divergente(numero: str) -> str:
    return (
        f"Uma tentativa anterior deste envio já foi registrada (Nº {numero}), mas com dados "
        "diferentes destes. Avise o almoxarifado antes de enviar de novo."
    )


def travar_sequencia() -> Sequencia:
    """A linha única da numeração, travada até o fim da transação (chame dentro de
    `transaction.atomic()`)."""
    Sequencia.objects.get_or_create(nome="PEDIDOS")
    return Sequencia.objects.select_for_update().get(nome="PEDIDOS")


def proximo_numero(sequencia: Sequencia, origem: str) -> str:
    """Próximo Nº de uma sequência única para pedidos (P-, de qualquer formulário público) e
    saídas avulsas (AV-)."""
    sequencia.ultimo += 1
    sequencia.save(update_fields=["ultimo"])
    prefixo = "AV-" if origem == AVULSA else "P-"
    return f"{prefixo}{sequencia.ultimo:06d}"


def catalogo_de(origem: str) -> list[ItemCatalogo] | None:
    """Catálogo do formulário da origem, ou None quando ele está indisponível: o saldo nunca foi
    importado (a limpeza e o AB limitam pelo saldo) ou o catálogo não tem item algum (nos dois
    formulários, para o funcionário não preencher um formulário que não pode ser enviado). Quem
    diz de onde vem o catálogo é o `Fluxo` da origem."""
    fluxo = fluxo_da_origem(origem)
    return fluxo.catalogo() if fluxo is not None else None


def _itens_gravados(pedido: Pedido) -> list[tuple[str, Decimal]]:
    return [(i.codigo, i.qtd_pedida) for i in pedido.itens.filter(origem=ItemPedido.Origem.PEDIDO)]


def _gravar_itens(pedido: Pedido, validos) -> None:
    """Retrato do catálogo no momento do aceite: do navegador só vêm código e quantidade."""
    ItemPedido.objects.bulk_create(
        ItemPedido(
            pedido=pedido,
            codigo=v.material.codigo,
            material=v.material.nome,
            unidade=v.material.unidade,
            categoria=v.material.categoria,
            grupo=v.material.grupo,
            subgrupo=v.material.subgrupo,
            estoque_no_pedido=v.material.estoque,
            qtd_pedida=Decimal(v.quantidade),
        )
        for v in validos
    )


MENSAGEM_LIMITE_IP = "Muitos pedidos enviados desta rede em pouco tempo. Procure o almoxarifado."
MENSAGEM_LIMITE_SOLICITANTE = (
    "Limite de pedidos por dia atingido para este nome. Procure o almoxarifado."
)


def inicio_do_dia(agora: datetime) -> datetime:
    """Meia-noite local do dia de `agora`, com fuso."""
    return timezone.localtime(agora).replace(hour=0, minute=0, second=0, microsecond=0)


# Rótulo do campo nos erros de tamanho → nome do campo no formulário público (erro junto ao campo).
_CAMPO_DO_ROTULO = {"Nome completo": "solicitante", "Destino": "destino", "Observação": "obs"}


def erros_de_tamanho(campos: dict[str, str], n_itens: int | None) -> list[Erro]:
    maximo = settings.PEDIDOS_MAX_TEXTO
    erros = [
        Erro(None, f"{rotulo}: no máximo {maximo} caracteres.", _CAMPO_DO_ROTULO.get(rotulo))
        for rotulo, valor in campos.items()
        if len(texto(valor)) > maximo
    ]
    if n_itens is not None and n_itens > settings.PEDIDOS_MAX_ITENS:
        erros.append(
            Erro(
                None,
                f"O pedido pode ter no máximo {settings.PEDIDOS_MAX_ITENS} materiais. "
                "Divida em mais de um pedido.",
            )
        )
    return erros


def _limite_atingido(ip: str | None, solicitante: str, agora: datetime) -> str:
    """Mensagem do limite de pedidos atingido, ou "" (os limites ficam no settings)."""
    dia = inicio_do_dia(agora)
    if ip:
        do_ip = Pedido.objects.filter(ip=ip)
        recentes = do_ip.filter(criado_em__gte=agora - timedelta(minutes=10)).count()
        if recentes >= settings.PEDIDOS_LIMITE_IP_10_MIN:
            return MENSAGEM_LIMITE_IP
        if do_ip.filter(criado_em__gte=dia).count() >= settings.PEDIDOS_LIMITE_IP_DIA:
            return MENSAGEM_LIMITE_IP
    if solicitante:
        # A collation do banco já ignora maiúsculas e acentos.
        do_nome = (
            Pedido.objects.exclude(origem=AVULSA)
            .filter(solicitante=solicitante, criado_em__gte=dia)
            .count()
        )
        if do_nome >= settings.PEDIDOS_LIMITE_SOLICITANTE_DIA:
            return MENSAGEM_LIMITE_SOLICITANTE
    return ""


def registrar_pedido(
    origem: str,
    envio_id: uuid.UUID,
    envio: EnvioPedido,
    *,
    ip: str | None = None,
    url_painel: str = "",
    agora: datetime | None = None,
) -> Resposta:
    """Pedido dos formulários públicos (`registrarPedido`)."""
    agora = agora or timezone.now()
    # O catálogo (o do AB é uma conta pesada) e os centros são lidos antes de travar a numeração:
    # o estoque é só um teto, nada é reservado, e os outros envios não podem esperar essa conta.
    # A ordem das respostas abaixo não muda (reenvio, limite, indisponível, validação).
    catalogo = catalogo_de(origem)
    fluxo = fluxo_da_origem(origem)  # None só para origem desconhecida, que não tem catálogo
    lista_centros = centros_do_fluxo(fluxo)
    # O número da ocorrência só vale no formulário que o pede; nos outros, o que vier é ignorado.
    if fluxo is None or not fluxo.pede_ocorrencia:
        envio = replace(envio, ocorrencia="")
    with transaction.atomic():
        seq = travar_sequencia()
        anterior = Pedido.objects.filter(pk=envio_id).first()
        if anterior is not None:
            gravado = (anterior.solicitante, anterior.destino, anterior.obs, anterior.ocorrencia)
            if anterior.origem == origem and registro_confere(
                origem, gravado, _itens_gravados(anterior), envio
            ):
                return Resposta(ok=True, reenvio=True, numero=anterior.numero, pedido=anterior)
            logger.warning("Pedido %s: reenvio não confere com o registro gravado.", envio_id)
            return Resposta(
                ok=False, divergente=True, mensagem=mensagem_divergente(anterior.numero)
            )

        # Depois do reenvio (que nunca conta) e com a sequência travada: dois envios
        # simultâneos não passam juntos do limite.
        limite = _limite_atingido(ip, texto(envio.solicitante), agora)
        if limite:
            return Resposta(ok=False, mensagem=limite)

        if fluxo is None or catalogo is None:
            return Resposta(
                ok=False,
                mensagem="O catálogo deste formulário não está disponível agora. "
                "Avise o almoxarifado.",
            )
        if not lista_centros:
            return Resposta(
                ok=False,
                mensagem="Não há centros de custo cadastrados para escolher o destino. "
                "Avise o almoxarifado.",
            )
        # A regra de quantidade é a do formulário, a mesma do carrinho dele.
        v = validar_pedido(envio, catalogo, lista_centros, fluxo.regra_quantidade)
        tamanhos = erros_de_tamanho(
            {
                "Nome completo": envio.solicitante,
                "Destino": envio.destino,
                "Observação": envio.obs,
            },
            len(envio.itens),
        )
        if tamanhos or v.erros:
            return Resposta(
                ok=False,
                mensagem="Corrija os itens abaixo e envie de novo.",
                erros=tamanhos + v.erros,
                estoque_atual=v.estoque_atual,
            )

        pedido = Pedido.objects.create(
            id=envio_id,
            numero=proximo_numero(seq, origem),
            origem=origem,
            criado_em=agora,
            ip=ip,
            solicitante=texto(envio.solicitante),
            destino=texto(envio.destino),
            obs=texto(envio.obs),
            ocorrencia=texto(envio.ocorrencia),
        )
        _gravar_itens(pedido, v.validos)
        if fluxo.exige_autorizacao:
            # Na mesma transação do pedido: não existe pedido de EPI sem autorização (spec 008).
            AutorizacaoPedido.objects.create(pedido=pedido)
        resposta = Resposta(ok=True, numero=pedido.numero, pedido=pedido)

        def avisar():
            if fluxo.exige_autorizacao:
                # O almoxarifado só é avisado depois de autorizado (`decidir_autorizacao`);
                # agora quem precisa saber é a Segurança do Trabalho, com o botão para a fila.
                resposta.telegram = notificar_autorizacao_pendente(pedido, url_painel)
            else:
                resposta.telegram = notificar_pedido(pedido, url_painel)

        transaction.on_commit(avisar)
    return resposta


def _nome_do_usuario(usuario) -> str:
    return usuario.get_full_name().strip() or usuario.get_username()


def _ja_decidida(pedido: Pedido, autorizacao: AutorizacaoPedido) -> Resposta:
    """A decisão que já estava gravada: quem e quando (nada é alterado)."""
    decisao = (
        "autorizado"
        if autorizacao.situacao == AutorizacaoPedido.Situacao.AUTORIZADO
        else "recusado"
    )
    quando = timezone.localtime(autorizacao.decidido_em).strftime("%d/%m/%Y %H:%M")
    quem = _nome_do_usuario(autorizacao.decidido_por)
    return Resposta(
        ok=False,
        motivo="ja_decidida",
        mensagem=f"Este pedido já foi {decisao} por {quem} em {quando}.",
        numero=pedido.numero,
        pedido=pedido,
        autorizacao=autorizacao,
    )


def decidir_autorizacao(
    numero: str, decisao: str, motivo: str, usuario, *, url_painel: str = ""
) -> Resposta:
    """A Segurança do Trabalho autoriza ou recusa um pedido de EPI (spec 008, FR-011 a FR-016).

    `decisao` é "autorizar" ou "recusar"; a recusa exige o `motivo`. Só quem é do grupo da
    Segurança do Trabalho decide (nem o administrador, FR-021). A decisão é definitiva e vale a
    primeira: o pedido é travado como no atendimento, e a segunda tentativa devolve a decisão já
    gravada sem alterar nada. Ao autorizar, o almoxarifado é avisado depois do commit (nunca
    desfaz a decisão), e o pedido passa a poder ser atendido."""
    if not da_seguranca_trabalho(usuario):
        return Resposta(
            ok=False,
            motivo="grupo",
            mensagem="Só a Segurança do Trabalho pode autorizar ou recusar pedidos de EPI.",
        )
    if decisao not in ("autorizar", "recusar"):
        return Resposta(ok=False, motivo="decisao", mensagem="Escolha autorizar ou recusar.")
    motivo = texto(motivo) if decisao == "recusar" else ""
    if decisao == "recusar":
        if not motivo:
            return Resposta(ok=False, motivo="motivo", mensagem="Informe o motivo da recusa.")
        if len(motivo) > settings.PEDIDOS_MAX_TEXTO:
            return Resposta(
                ok=False,
                motivo="motivo",
                mensagem=f"Motivo da recusa: no máximo {settings.PEDIDOS_MAX_TEXTO} caracteres.",
            )
    with transaction.atomic():
        # O mesmo travamento do atendimento: decidir e atender o mesmo pedido não se cruzam.
        pedido = Pedido.objects.select_for_update().filter(numero=numero).first()
        autorizacao = (
            AutorizacaoPedido.objects.select_for_update()
            .select_related("decidido_por")
            .filter(pedido=pedido)
            .first()
            if pedido is not None
            else None
        )
        if autorizacao is None:
            return Resposta(
                ok=False,
                motivo="nao_encontrada",
                mensagem="Pedido de EPIs não encontrado.",
            )
        if autorizacao.situacao != AutorizacaoPedido.Situacao.AGUARDANDO:
            return _ja_decidida(pedido, autorizacao)
        autorizacao.situacao = (
            AutorizacaoPedido.Situacao.AUTORIZADO
            if decisao == "autorizar"
            else AutorizacaoPedido.Situacao.RECUSADO
        )
        autorizacao.decidido_por = usuario
        autorizacao.decidido_em = timezone.now()
        autorizacao.motivo = motivo
        autorizacao.save()
        resposta = Resposta(ok=True, numero=pedido.numero, pedido=pedido, autorizacao=autorizacao)
        if decisao == "autorizar":

            def avisar():
                resposta.telegram = notificar_pedido(pedido, url_painel)

            transaction.on_commit(avisar)
    return resposta


# ---------------------------------------------------------------------------
# Saídas: atendimento de pedido e saída avulsa
# ---------------------------------------------------------------------------


def centros() -> list[Centro]:
    """Todas as linhas do cadastro de centros, ativas ou não: é o que o atendimento, a edição e o
    robô do SCPI resolvem (spec 009, FR-012)."""
    return [Centro(c.descricao, c.codigo, c.placa or "") for c in CentroCusto.objects.all()]


def centros_ativos() -> list[Centro]:
    """As linhas de centro ativas: o que a saída avulsa **nova** oferece e aceita. O centro
    inativo continua resolvido por `centros()` onde já foi usado (spec 009, FR-008)."""
    return [
        Centro(c.descricao, c.codigo, c.placa or "") for c in CentroCusto.objects.filter(ativo=True)
    ]


def centros_do_fluxo(fluxo) -> list[Centro]:
    """Os destinos aceitos pelo formulário: os do `Fluxo` quando ele restringe, senão todos."""
    return fluxo.centros() if fluxo is not None and fluxo.centros is not None else centros()


def tipos_saida() -> list[str]:
    return Opcao.valores(Opcao.Lista.TIPO_SAIDA) or list(TIPOS_SAIDA_PADRAO)


def erros_extras_da_saida(
    dados: DadosSaida, nao_lancar: bool, centro: CentroResolvido
) -> list[Erro]:
    """O que o formulário antigo impedia na tela: centro diferente do da placa e o "não
    lançar" escrito só na observação."""
    erros = []
    if centro.via_placa and norm_u(centro.descricao) != norm_u(dados.centro_custo):
        erros.append(
            Erro(
                None,
                f"A placa {norm_placa(dados.placa)} pertence ao centro de custo "
                f'"{centro.descricao}". Escolha esse centro ou limpe a placa.',
            )
        )
    if marcado_nao_lancar(dados.obs) and not nao_lancar:
        erros.append(
            Erro(
                None,
                'Para não lançar no SCPI, marque a opção "Não lançar no SCPI" (a observação não '
                "basta).",
            )
        )
    return erros


def cabecalho_atendimento(atendimento: Atendimento) -> tuple[str, ...]:
    """Dados gravados da saída, na ordem de `regras.cabecalho_saida`."""
    return (
        atendimento.data_efetiva.isoformat(),
        atendimento.recebedor,
        atendimento.centro_custo,
        atendimento.tipo_saida,
        atendimento.placa,
        atendimento.obs,
        "1" if atendimento.nao_lancar else "",
    )


def _criar_atendimento(atendimento_id, pedido, dados: DadosSaida, nao_lancar, usuario):
    return Atendimento.objects.create(
        id=atendimento_id,
        pedido=pedido,
        data_efetiva=date.fromisoformat(texto(dados.data)),
        recebedor=texto(dados.recebedor),
        centro_custo=texto(dados.centro_custo),
        tipo_saida=texto(dados.tipo),
        placa=norm_placa(dados.placa),
        obs=texto(dados.obs),
        nao_lancar=nao_lancar,
        atendido_por=usuario,
    )


def _gravar_linhas(atendimento: Atendimento, pares, lote: str) -> None:
    """Uma `LinhaSaida` por material com quantidade maior que zero (contrato com o robô)."""
    status = NAO_LANCAR if atendimento.nao_lancar else PENDENTE
    linhas = []
    for item, qtd in pares:
        if not qtd or qtd <= 0:
            continue
        linhas.append(
            LinhaSaida(
                atendimento=atendimento,
                seq=len(linhas) + 1,
                data=atendimento.data_efetiva,
                qtd=Decimal(qtd),
                codigo=item.codigo,
                descricao=item.material,
                recebedor=atendimento.recebedor,
                centro_custo=atendimento.centro_custo,
                tipo_saida=atendimento.tipo_saida,
                placa=atendimento.placa,
                obs=atendimento.obs,
                lote=lote,
                status=status,
            )
        )
    LinhaSaida.objects.bulk_create(linhas)


def _qtd_adicionada(qtds: dict[str, str], codigo: str) -> Decimal | None:
    """Quantidade de um acrescentado: vírgula decimal, em qualquer unidade (a equipe não segue a
    regra por unidade); campo vazio ou ausente vale 0, que pede a quantidade."""
    return parse_qtd_br(texto(qtds.get(codigo)) or "0")


def _adicionados_gravados(itens: list[ItemPedido]) -> frozenset:
    por_id = {i.id: i for i in itens}
    return frozenset(
        (i.codigo, por_id[i.no_lugar_de_id].codigo if i.no_lugar_de_id else "", i.qtd_entregue)
        for i in itens
        if i.origem == ItemPedido.Origem.ALMOXARIFADO
    )


def erros_de_vinculo(
    adicionados: Sequence[Adicionado],
    pedidos: list[ItemPedido],
    catalogo: dict[str, ItemCatalogo],
) -> tuple[list[Adicionado], list[Erro]]:
    """Repetição e vínculo de troca dos acrescentados, na ordem em que entraram (também na
    busca do atendimento, antes do envio). Devolve os que não repetem código e os erros."""
    do_pedido = {i.codigo: i for i in pedidos}
    erros: list[Erro] = []
    unicos: list[Adicionado] = []
    vistos: set[str] = set()
    trocados: set[str] = set()

    def nome(codigo):
        if codigo in catalogo:
            return catalogo[codigo].nome
        return do_pedido[codigo].material if codigo in do_pedido else codigo

    for a in adicionados:
        if a.codigo in do_pedido or a.codigo in vistos:
            erros.append(
                Erro(
                    a.codigo,
                    f"{nome(a.codigo)} ({a.codigo}) já está no pedido: altere a quantidade nele.",
                )
            )
            continue
        vistos.add(a.codigo)
        unicos.append(a)
        if a.no_lugar_de and a.no_lugar_de not in do_pedido:
            erros.append(Erro(a.codigo, f"Material de troca inválido para {nome(a.codigo)}."))
        elif a.no_lugar_de in trocados:
            erros.append(
                Erro(
                    a.no_lugar_de,
                    f"{do_pedido[a.no_lugar_de].material} já foi trocado por outro material.",
                )
            )
        elif a.no_lugar_de:
            trocados.add(a.no_lugar_de)
    return unicos, erros


def _erros_dos_adicionados(
    adicionados: list[Adicionado],
    pedidos: list[ItemPedido],
    qtds_adicionadas: dict[str, Decimal | None],
    catalogo: dict[str, ItemCatalogo],
    validar,
    limites: dict[str, Decimal],
) -> tuple[list[Adicionado], list[Erro]]:
    """Regras dos acrescentados: repetição, vínculo de troca, catálogo e quantidade. Devolve
    os que não repetem código (os que vão para a validação comum) e os erros."""
    unicos, erros = erros_de_vinculo(adicionados, pedidos, catalogo)

    def nome(codigo):
        return catalogo[codigo].nome if codigo in catalogo else codigo

    # Catálogo, código e quantidade pela regra comum da saída; só os erros de cada material
    # (os dos dados da saída já vêm da validação do pedido inteiro).
    if not unicos:
        return unicos, erros
    v = validar(
        [
            ItemSaida(a.codigo, qtds_adicionadas[a.codigo], estoque=limites.get(a.codigo))
            for a in unicos
        ],
        catalogo,
    )
    dos_materiais = [e for e in v.erros if e.codigo is not None]
    com_erro = {e.codigo for e in dos_materiais}
    erros += dos_materiais
    erros += [
        Erro(a.codigo, f"Informe a quantidade de {nome(a.codigo)}.")
        for a in unicos
        if a.codigo not in com_erro and qtds_adicionadas[a.codigo] == 0
    ]
    return unicos, erros


def _erros_de_entrega_acima(
    itens: list[ItemPedido], parsed: dict, da_saida: dict[str, ItemCatalogo]
) -> list[Erro]:
    """Entregar mais que o pedido é permitido (o almoxarifado decide), mas só até o maior entre o
    pedido, o saldo do cadastro (truncado a 3 casas) e o que já está gravado: nunca recusa o que
    o pedido já permitia, e uma edição não derruba a entrega gravada."""
    erros = []
    for i in itens:
        q = parsed[i.codigo]
        saldo = truncar_qtd(da_saida[i.codigo].estoque) if i.codigo in da_saida else Decimal(0)
        teto = max(i.qtd_pedida, saldo, i.qtd_entregue or 0)
        if q is not None and q > teto:
            erros.append(
                Erro(
                    i.codigo,
                    f"Entrega de {i.codigo} acima do máximo de {qtd_br(teto)} "
                    "(o maior entre o pedido e o estoque).",
                )
            )
    return erros


def _erros_de_troca_entregue(
    unicos: list[Adicionado], pedidos: list[ItemPedido], parsed: dict
) -> list[Erro]:
    """O item pedido trocado fica com 0 até a troca ser desfeita: entregá-lo junto com o que o
    substitui seria a troca e o original ao mesmo tempo."""
    do_pedido = {i.codigo: i for i in pedidos}
    trocados = dict.fromkeys(a.no_lugar_de for a in unicos if a.no_lugar_de in do_pedido)
    return [
        Erro(
            codigo,
            f"{do_pedido[codigo].material} foi trocado por outro material: a quantidade "
            "entregue dele fica 0. Para entregá-lo, desfaça a troca.",
        )
        for codigo in trocados
        if parsed[codigo] is not None and parsed[codigo] != 0
    ]


def _validar_atendimento(
    pedido: Pedido,
    itens: list[ItemPedido],
    dados: DadosSaida,
    parsed: dict,
    adicionados: list[Adicionado],
    qtds_adicionadas: dict[str, Decimal | None],
    nao_lancar: bool,
    *,
    hoje: date,
    catalogo_extra: dict[str, ItemCatalogo] | None = None,
) -> tuple[list[Adicionado], dict[str, ItemCatalogo], list[Erro]]:
    """Regras do atendimento (e da edição dele): dados da saída, quantidades entregues e os
    materiais acrescentados. Devolve os acrescentados sem repetição, o catálogo usado (o da
    saída avulsa, com `catalogo_extra` por cima) e os erros."""
    lista_centros, tipos = centros(), tipos_saida()

    def validar(itens_saida, catalogo=None):
        return validar_saida(
            dados,
            itens_saida,
            centros=lista_centros,
            tipos=tipos,
            hoje=hoje,
            catalogo=catalogo,
        )

    da_saida = {c.codigo: c for c in catalogo_de(AVULSA) or []}
    catalogo = dict(da_saida) if adicionados else {}
    base = dict(catalogo)
    catalogo.update(catalogo_extra or {})
    unicos, erros_adicionados = _erros_dos_adicionados(
        adicionados,
        itens,
        qtds_adicionadas,
        catalogo,
        validar,
        _limites_de_estoque(catalogo, base=base),
    )
    # Os acrescentados entram aqui só para contar no "ao menos um material"; seus erros
    # por material vêm de `_erros_dos_adicionados`.
    codigos_unicos = {a.codigo for a in unicos}
    v = validar(
        [ItemSaida(i.codigo, parsed[i.codigo]) for i in itens]
        + [ItemSaida(a.codigo, qtds_adicionadas[a.codigo]) for a in unicos]
    )
    erros = (
        erros_de_tamanho(
            {
                "Recebedor": dados.recebedor,
                "Centro de custo": dados.centro_custo,
                "Observações": dados.obs,
            },
            None,
        )
        + [e for e in v.erros if e.codigo is None or e.codigo not in codigos_unicos]
        + erros_adicionados
        + _erros_de_entrega_acima(itens, parsed, da_saida)
        + _erros_de_troca_entregue(unicos, itens, parsed)
        + erros_extras_da_saida(dados, nao_lancar, v.centro)
    )
    return unicos, catalogo, erros


def estado_gravado(pedido: Pedido) -> EstadoAtendimento:
    """O que a edição pode mudar, como está gravado (o pedido precisa estar atendido)."""
    todos = list(pedido.itens.all())
    por_id = {i.id: i for i in todos}
    avulsa = pedido.origem == AVULSA
    cabecalho = cabecalho_atendimento(pedido.atendimento)
    # "Não lançar" marcado em Automações muda as linhas, não o atendimento: o formulário de
    # edição já abre marcado, então não é diferença.
    status = set(pedido.atendimento.linhas.values_list("status", flat=True))
    if status == {NAO_LANCAR}:
        cabecalho = (*cabecalho[:6], "1")
    return EstadoAtendimento(
        cabecalho=cabecalho,
        entregues={
            i.codigo: i.qtd_entregue
            for i in todos
            if avulsa or i.origem == ItemPedido.Origem.PEDIDO
        },
        adicionados={
            i.codigo: (por_id[i.no_lugar_de_id].codigo if i.no_lugar_de_id else "", i.qtd_entregue)
            for i in todos
            if not avulsa and i.origem == ItemPedido.Origem.ALMOXARIFADO
        },
        nomes={i.codigo: i.material for i in todos},
    )


def estado_enviado(
    pedido: Pedido,
    dados: DadosSaida,
    nao_lancar: bool,
    parsed: dict,
    adicionados: list[Adicionado],
    qtds_adicionadas: dict,
    nomes_extra: dict[str, str] | None = None,
) -> EstadoAtendimento:
    """O que chegou do formulário de edição, no formato de `estado_gravado`."""
    return EstadoAtendimento(
        cabecalho=cabecalho_saida(dados, nao_lancar),
        entregues=dict(parsed),
        adicionados={
            a.codigo: (texto(a.no_lugar_de), qtds_adicionadas.get(a.codigo)) for a in adicionados
        },
        nomes={**{i.codigo: i.material for i in pedido.itens.all()}, **(nomes_extra or {})},
    )


def _recusa_por_falta_de_autorizacao(pedido: Pedido) -> str:
    """O motivo de o atendimento não poder seguir por causa da autorização da Segurança do
    Trabalho, ou "" (o pedido não exige autorização, ou já está autorizado)."""
    autorizacao = pedido.autorizacao_ou_none
    if autorizacao is None or autorizacao.situacao == AutorizacaoPedido.Situacao.AUTORIZADO:
        return ""
    if autorizacao.situacao == AutorizacaoPedido.Situacao.RECUSADO:
        return (
            f"O pedido {pedido.numero} foi recusado pela Segurança do Trabalho e está encerrado. "
            "Nada foi gravado."
        )
    return (
        f"O pedido {pedido.numero} ainda não foi autorizado pela Segurança do Trabalho e não "
        "pode ser atendido. Nada foi gravado."
    )


def confirmar_atendimento(
    pedido_id: uuid.UUID,
    atendimento_id: uuid.UUID,
    dados: DadosSaida,
    qtds: dict[str, str],
    *,
    nao_lancar: bool,
    usuario,
    hoje: date | None = None,
    adicionados: Sequence[Adicionado] = (),
) -> Resposta:
    """Confirma o atendimento de um pedido (`confirmarAtendimento`): grava o atendimento, a
    quantidade entregue de cada item, os materiais acrescentados pelo almoxarifado e as linhas
    de saída, numa transação."""
    adicionados = [Adicionado(texto(a.codigo), texto(a.no_lugar_de)) for a in adicionados]
    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().filter(pk=pedido_id).first()
        if pedido is None or pedido.origem == AVULSA:
            return Resposta(ok=False, mensagem="Pedido não encontrado.")
        todos = list(pedido.itens.all())
        itens = [i for i in todos if i.origem == ItemPedido.Origem.PEDIDO]
        # A equipe aceita fração em qualquer unidade e em pedido de qualquer origem.
        parsed = {i.codigo: parse_qtd_br(qtds.get(i.codigo, "")) for i in itens}
        qtds_adicionadas = {a.codigo: _qtd_adicionada(qtds, a.codigo) for a in adicionados}

        anterior = pedido.atendimento_ou_none
        if anterior is not None:
            entregues = {i.codigo: i.qtd_entregue for i in itens}
            enviados = frozenset(
                (a.codigo, a.no_lugar_de, qtds_adicionadas[a.codigo]) for a in adicionados
            )
            if anterior.id == atendimento_id and atendimento_confere(
                cabecalho_atendimento(anterior),
                entregues,
                dados,
                nao_lancar,
                parsed,
                _adicionados_gravados(todos),
                enviados,
            ):
                return Resposta(ok=True, reenvio=True, numero=pedido.numero, pedido=pedido)
            return Resposta(
                ok=False,
                mensagem=f"O pedido {pedido.numero} já tem um atendimento registrado. "
                "Nada foi gravado.",
            )

        # O portão da autorização (spec 008): antes de qualquer gravação, na mesma transação que
        # trava o pedido, para o pedido de EPI aguardando ou recusado nunca virar atendimento nem
        # linha de saída (o robô só lê as linhas).
        if mensagem := _recusa_por_falta_de_autorizacao(pedido):
            return Resposta(ok=False, mensagem=mensagem)
        unicos, catalogo, erros = _validar_atendimento(
            pedido,
            itens,
            dados,
            parsed,
            adicionados,
            qtds_adicionadas,
            nao_lancar,
            hoje=hoje or timezone.localdate(),
        )
        if erros:
            return Resposta(ok=False, mensagem="Corrija os dados da saída.", erros=erros)

        atendimento = _criar_atendimento(atendimento_id, pedido, dados, nao_lancar, usuario)
        do_pedido = {i.codigo: i for i in itens}
        acrescentados = ItemPedido.objects.bulk_create(
            ItemPedido(
                pedido=pedido,
                codigo=a.codigo,
                material=catalogo[a.codigo].nome,
                unidade=catalogo[a.codigo].unidade,
                grupo=catalogo[a.codigo].grupo,
                subgrupo=catalogo[a.codigo].subgrupo,
                origem=ItemPedido.Origem.ALMOXARIFADO,
                no_lugar_de=do_pedido.get(a.no_lugar_de),
                adicionado_por=usuario,
                qtd_pedida=None,
                qtd_entregue=Decimal(qtds_adicionadas[a.codigo]),
            )
            for a in adicionados
        )
        for item in itens:
            item.qtd_entregue = Decimal(parsed[item.codigo])
        ItemPedido.objects.bulk_update(itens, ["qtd_entregue"])
        _gravar_linhas(
            atendimento, [(i, i.qtd_entregue) for i in itens + acrescentados], pedido.numero
        )
    return Resposta(ok=True, numero=pedido.numero, pedido=pedido)


# ---------------------------------------------------------------------------
# Edição do atendimento (e da saída avulsa) até o lançamento no SCPI
# ---------------------------------------------------------------------------

MENSAGEM_NADA_MUDOU = "Nada mudou; nada foi gravado."


def item_catalogo_gravado(item: ItemPedido) -> ItemCatalogo:
    """Material já gravado no pedido, aceito na edição mesmo que tenha saído do catálogo. O
    estoque é a quantidade entregue gravada: o teto de quem já saiu (ver `_limites_de_estoque`)."""
    return ItemCatalogo(
        codigo=item.codigo,
        nome=item.material,
        unidade=item.unidade,
        categoria="",
        grupo=item.grupo,
        subgrupo=item.subgrupo,
        estoque=item.qtd_entregue or Decimal(0),
        disponivel=0,
        duplicado=False,
    )


def _erros_de_valor_sumido(gravado: tuple[str, ...], dados: DadosSaida) -> list[Erro]:
    """Centro de custo, tipo ou placa que a pessoa não mexeu, mas que deixou de existir: a
    edição recusa (o robô também recusaria) e diz por quê."""
    lista_centros = centros()
    sumidos = []
    centro = texto(dados.centro_custo)
    if (
        centro
        and norm_u(centro) == norm_u(gravado[2])
        and not any(norm_u(c.descricao) == norm_u(centro) for c in lista_centros)
    ):
        sumidos.append(ROTULOS_CABECALHO[2])
    tipo = texto(dados.tipo)
    if tipo and tipo == gravado[3] and tipo not in tipos_saida():
        sumidos.append(ROTULOS_CABECALHO[3])
    placa = norm_placa(dados.placa)
    if (
        placa
        and placa == gravado[4]
        and not any(norm_placa(c.placa) == placa for c in lista_centros)
    ):
        sumidos.append(ROTULOS_CABECALHO[4])
    return [Erro(None, f"{r}: o valor gravado não existe mais. Escolha outro.") for r in sumidos]


def _conferir_edicao(pedido: Pedido, linhas, versao: int, diferencas: list) -> Resposta | None:
    """Recusa a edição de um lote que entrou em lançamento e a de quem abriu uma versão
    anterior (salvo o reenvio igual ao gravado). `None` quando pode seguir."""
    edicao = edicao_permitida(True, linhas)
    if not edicao.permitida:
        return Resposta(
            ok=False,
            motivo="lancamento",
            mensagem=edicao.motivo,
            diferencas=diferencas,
            numero=pedido.numero,
        )
    if versao == pedido.versao:
        return None
    if not diferencas:
        return Resposta(
            ok=True,
            reenvio=True,
            mensagem=f"As alterações já estavam salvas no pedido {pedido.numero}.",
            numero=pedido.numero,
            pedido=pedido,
        )
    ultima = pedido.alteracoes.select_related("usuario").first()
    if ultima is None:
        quem = "Outra pessoa salvou alterações neste pedido."
    else:
        nome = ultima.usuario.get_full_name() or ultima.usuario.username
        quem = f"{nome} salvou alterações neste pedido às {timezone.localtime(ultima.em):%H:%M}."
    return Resposta(
        ok=False, motivo="versao", mensagem=quem, diferencas=diferencas, numero=pedido.numero
    )


def _gravar_edicao(
    pedido: Pedido,
    atendimento: Atendimento,
    dados: DadosSaida,
    nao_lancar: bool,
    pares,
    diferencas: list,
    linhas_antigas: list[LinhaSaida],
    usuario,
) -> None:
    """Grava o cabeçalho do atendimento, a versão, o histórico e as linhas de saída novas. As
    linhas nunca são atualizadas no lugar: apagadas e recriadas, com IDs novos, o robô que leu
    o lote antes da edição o encontra mudado e o pula (`lancamento._travar`)."""
    atendimento.data_efetiva = date.fromisoformat(texto(dados.data))
    atendimento.recebedor = texto(dados.recebedor)
    atendimento.centro_custo = texto(dados.centro_custo)
    atendimento.tipo_saida = texto(dados.tipo)
    atendimento.placa = norm_placa(dados.placa)
    atendimento.obs = texto(dados.obs)
    atendimento.nao_lancar = nao_lancar
    atendimento.recibo_impresso_em = None
    atendimento.save()
    pedido.versao += 1
    pedido.save(update_fields=["versao"])
    AlteracaoPedido.objects.create(
        pedido=pedido,
        usuario=usuario,
        versao=pedido.versao,
        diferencas=diferencas,
        scpi_antes=[
            {
                "seq": linha.seq,
                "status": linha.status,
                "mensagem": linha.mensagem,
                "requisicao_scpi": linha.requisicao_scpi,
            }
            for linha in linhas_antigas
        ],
    )
    LinhaSaida.objects.filter(atendimento=atendimento).delete()
    _gravar_linhas(atendimento, pares, pedido.numero)
    quando = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    novas = LinhaSaida.objects.filter(atendimento=atendimento)
    novas.update(mensagem=f"Refeita na edição de {quando} por {usuario.username}.")
    # Material marcado sozinho para não lançar (no admin) continua fora do robô. O lote inteiro
    # marcado vira a caixa "Não lançar" do formulário, e aí vale o que veio dela.
    sem_lancar = {linha.codigo for linha in linhas_antigas if linha.status == NAO_LANCAR}
    if len(sem_lancar) < len({linha.codigo for linha in linhas_antigas}):
        novas.filter(codigo__in=sem_lancar).update(status=NAO_LANCAR)


def editar_atendimento(
    pedido_id: uuid.UUID,
    versao: int,
    dados: DadosSaida,
    qtds: dict[str, str],
    *,
    nao_lancar: bool,
    adicionados: Sequence[Adicionado] = (),
    usuario,
    hoje: date | None = None,
) -> Resposta:
    """Corrige o atendimento de um pedido enquanto o lote não entrou em lançamento: dados da
    saída, quantidades entregues e materiais acrescentados pelo almoxarifado. O que veio do
    funcionário (cabeçalho, materiais e quantidades pedidas) nunca muda."""
    adicionados = [Adicionado(texto(a.codigo), texto(a.no_lugar_de)) for a in adicionados]
    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().filter(pk=pedido_id).first()
        atendimento = pedido.atendimento_ou_none if pedido is not None else None
        if atendimento is None or pedido.origem == AVULSA:
            return Resposta(ok=False, mensagem="Pedido não encontrado.")
        linhas = list(
            LinhaSaida.objects.select_for_update().filter(atendimento=atendimento).order_by("seq")
        )
        todos = list(pedido.itens.all())
        itens = [i for i in todos if i.origem == ItemPedido.Origem.PEDIDO]
        gravados = {i.codigo: i for i in todos if i.origem == ItemPedido.Origem.ALMOXARIFADO}
        por_id = {i.id: i for i in todos}
        # A equipe aceita fração em qualquer unidade e em pedido de qualquer origem.
        parsed = {i.codigo: parse_qtd_br(qtds.get(i.codigo, "")) for i in itens}
        qtds_adicionadas = {a.codigo: _qtd_adicionada(qtds, a.codigo) for a in adicionados}

        mantidos = {
            a.codigo: item_catalogo_gravado(gravados[a.codigo])
            for a in adicionados
            if a.codigo in gravados
            and (
                por_id[gravados[a.codigo].no_lugar_de_id].codigo
                if gravados[a.codigo].no_lugar_de_id
                else ""
            )
            == a.no_lugar_de
        }
        catalogo_avulsa = {c.codigo: c for c in catalogo_de(AVULSA) or []} if adicionados else {}
        nomes = {c: catalogo_avulsa[c].nome for c in qtds_adicionadas if c in catalogo_avulsa}
        diferencas = diferencas_atendimento(
            estado_gravado(pedido),
            estado_enviado(pedido, dados, nao_lancar, parsed, adicionados, qtds_adicionadas, nomes),
        )
        recusa = _conferir_edicao(pedido, linhas, versao, diferencas)
        if recusa is not None:
            return recusa

        unicos, catalogo, erros = _validar_atendimento(
            pedido,
            itens,
            dados,
            parsed,
            adicionados,
            qtds_adicionadas,
            nao_lancar,
            hoje=hoje or timezone.localdate(),
            catalogo_extra=mantidos,
        )
        erros = _erros_de_valor_sumido(cabecalho_atendimento(atendimento), dados) + erros
        if erros:
            return Resposta(ok=False, mensagem="Corrija os dados da saída.", erros=erros)
        if not diferencas:
            return Resposta(
                ok=True, mensagem=MENSAGEM_NADA_MUDOU, numero=pedido.numero, pedido=pedido
            )

        do_pedido = {i.codigo: i for i in itens}
        for item in itens:
            item.qtd_entregue = Decimal(parsed[item.codigo])
        ItemPedido.objects.bulk_update(itens, ["qtd_entregue"])
        ficam = {a.codigo for a in unicos}
        ItemPedido.objects.filter(
            pk__in=[i.pk for c, i in gravados.items() if c not in ficam]
        ).delete()
        acrescentados = []
        for a in unicos:
            item = gravados.get(a.codigo)
            if item is None:
                m = catalogo[a.codigo]
                item = ItemPedido(
                    pedido=pedido,
                    codigo=a.codigo,
                    material=m.nome,
                    unidade=m.unidade,
                    grupo=m.grupo,
                    subgrupo=m.subgrupo,
                    origem=ItemPedido.Origem.ALMOXARIFADO,
                    adicionado_por=usuario,
                    qtd_pedida=None,
                )
            item.no_lugar_de = do_pedido.get(a.no_lugar_de)
            item.qtd_entregue = Decimal(qtds_adicionadas[a.codigo])
            item.save()
            acrescentados.append(item)
        _gravar_edicao(
            pedido,
            atendimento,
            dados,
            nao_lancar,
            [(i, i.qtd_entregue) for i in itens + acrescentados],
            diferencas,
            linhas,
            usuario,
        )
    return Resposta(
        ok=True,
        mensagem=f"Alterações salvas no pedido {pedido.numero}.",
        numero=pedido.numero,
        pedido=pedido,
        diferencas=diferencas,
    )


def _limites_de_estoque(catalogo: dict, gravados=(), base: dict | None = None) -> dict:
    """Teto da quantidade de cada material da saída: o saldo do catálogo truncado a 3 casas (o
    mesmo número da lista e das mensagens), ou a quantidade já gravada se for maior (o SCPI pode
    ter abatido o saldo, ou o material ter saído do catálogo, e quem já está na saída continua
    valendo). `base` é o catálogo de verdade, quando `catalogo` já traz os gravados por cima."""
    limites = {c: truncar_qtd(i.estoque) for c, i in catalogo.items()}
    for c, i in (base or {}).items():
        limites[c] = max(limites.get(c, Decimal(0)), truncar_qtd(i.estoque))
    for item in gravados:
        limites[item.codigo] = max(limites.get(item.codigo, Decimal(0)), item.qtd_entregue or 0)
    return limites


def _validar_saida_avulsa(
    envio: EnvioSaida, *, hoje: date, catalogo: dict, limites: dict, so_ativos: bool = False
):
    """Regras da saída avulsa (e da edição dela). Devolve a soma por código e os erros. Com
    `so_ativos` (a saída nova), o centro inativo não está na lista; a edição de uma saída já
    registrada aceita qualquer centro."""
    soma = somar_por_codigo(envio.itens, parse_qtd_br)
    v = validar_saida(
        envio.dados,
        [ItemSaida(c, soma.soma[c], estoque=limites.get(c)) for c in soma.ordem],
        centros=centros_ativos() if so_ativos else centros(),
        tipos=tipos_saida(),
        hoje=hoje,
        catalogo=catalogo,
    )
    erros = list(v.erros)
    erros += [
        Erro(i.codigo, f"Quantidade inválida para {i.codigo} (use vírgula para decimais).")
        for i in soma.invalidos
    ]
    if not soma.ordem and not soma.invalidos:
        erros.append(Erro(None, "Adicione ao menos um material."))
    erros += erros_extras_da_saida(envio.dados, envio.nao_lancar, v.centro)
    erros += erros_de_tamanho(
        {
            "Recebedor": envio.dados.recebedor,
            "Centro de custo": envio.dados.centro_custo,
            "Observações": envio.dados.obs,
        },
        None,
    )
    return soma, erros


def _gravar_itens_avulsa(pedido: Pedido, soma, por_codigo: dict) -> list[ItemPedido]:
    return ItemPedido.objects.bulk_create(
        ItemPedido(
            pedido=pedido,
            codigo=c,
            material=por_codigo[c].nome,
            unidade=por_codigo[c].unidade,
            grupo=por_codigo[c].grupo,
            qtd_pedida=Decimal(soma.soma[c]),
            qtd_entregue=Decimal(soma.soma[c]),
        )
        for c in soma.ordem
    )


def registrar_saida_avulsa(
    envio_id: uuid.UUID, envio: EnvioSaida, *, usuario, hoje: date | None = None
) -> Resposta:
    """Saída registrada direto pelo almoxarifado (`registrarSaidaAvulsa`): pedido AVULSA,
    atendimento e linhas de saída numa transação."""
    with transaction.atomic():
        seq = travar_sequencia()
        anterior = Pedido.objects.filter(pk=envio_id).first()
        if anterior is not None:
            atendimento = anterior.atendimento_ou_none
            if (
                anterior.origem == AVULSA
                and atendimento is not None
                and registro_confere(
                    AVULSA, cabecalho_atendimento(atendimento), _itens_gravados(anterior), envio
                )
            ):
                return Resposta(ok=True, reenvio=True, numero=anterior.numero, pedido=anterior)
            return Resposta(
                ok=False, divergente=True, mensagem=mensagem_divergente(anterior.numero)
            )

        catalogo = catalogo_de(AVULSA)
        if catalogo is None:
            return Resposta(ok=False, mensagem="O cadastro de materiais não está disponível agora.")
        por_codigo = {i.codigo: i for i in catalogo}
        soma, erros = _validar_saida_avulsa(
            envio,
            hoje=hoje or timezone.localdate(),
            catalogo=por_codigo,
            limites=_limites_de_estoque(por_codigo),
            so_ativos=True,
        )
        if erros:
            return Resposta(ok=False, mensagem="Corrija os itens abaixo.", erros=erros)

        pedido = Pedido.objects.create(
            id=envio_id,
            numero=proximo_numero(seq, AVULSA),
            origem=AVULSA,
            registrado_por=usuario,
        )
        itens = _gravar_itens_avulsa(pedido, soma, por_codigo)
        atendimento = _criar_atendimento(envio_id, pedido, envio.dados, envio.nao_lancar, usuario)
        _gravar_linhas(atendimento, [(i, i.qtd_entregue) for i in itens], pedido.numero)
    return Resposta(ok=True, numero=pedido.numero, pedido=pedido)


def editar_saida_avulsa(
    pedido_id: uuid.UUID,
    versao: int,
    envio: EnvioSaida,
    *,
    usuario,
    hoje: date | None = None,
) -> Resposta:
    """Corrige uma saída avulsa enquanto o lote não entrou em lançamento: dados da saída e
    materiais (o carrinho inteiro substitui os itens)."""
    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().filter(pk=pedido_id).first()
        atendimento = pedido.atendimento_ou_none if pedido is not None else None
        if atendimento is None or pedido.origem != AVULSA:
            return Resposta(ok=False, mensagem="Pedido não encontrado.")
        linhas = list(
            LinhaSaida.objects.select_for_update().filter(atendimento=atendimento).order_by("seq")
        )
        catalogo = catalogo_de(AVULSA)
        if catalogo is None:
            return Resposta(ok=False, mensagem="O cadastro de materiais não está disponível agora.")
        por_codigo = {i.codigo: i for i in catalogo}
        # Material já na saída continua aceito, mesmo que tenha saído do catálogo.
        gravados = list(pedido.itens.all())
        limites = _limites_de_estoque(por_codigo, gravados)
        for item in gravados:
            por_codigo.setdefault(item.codigo, item_catalogo_gravado(item))
        soma, erros = _validar_saida_avulsa(
            envio, hoje=hoje or timezone.localdate(), catalogo=por_codigo, limites=limites
        )
        nomes = {c: por_codigo[c].nome for c in soma.ordem if c in por_codigo}
        diferencas = diferencas_atendimento(
            estado_gravado(pedido),
            estado_enviado(
                pedido,
                envio.dados,
                envio.nao_lancar,
                {c: soma.soma[c] for c in soma.ordem},
                [],
                {},
                nomes,
            ),
        )
        recusa = _conferir_edicao(pedido, linhas, versao, diferencas)
        if recusa is not None:
            return recusa
        erros = _erros_de_valor_sumido(cabecalho_atendimento(atendimento), envio.dados) + erros
        if erros:
            return Resposta(ok=False, mensagem="Corrija os itens abaixo.", erros=erros)
        if not diferencas:
            return Resposta(
                ok=True, mensagem=MENSAGEM_NADA_MUDOU, numero=pedido.numero, pedido=pedido
            )
        pedido.itens.all().delete()
        itens = _gravar_itens_avulsa(pedido, soma, por_codigo)
        _gravar_edicao(
            pedido,
            atendimento,
            envio.dados,
            envio.nao_lancar,
            [(i, i.qtd_entregue) for i in itens],
            diferencas,
            linhas,
            usuario,
        )
    return Resposta(
        ok=True,
        mensagem=f"Alterações salvas na saída {pedido.numero}.",
        numero=pedido.numero,
        pedido=pedido,
        diferencas=diferencas,
    )


def marcar_recibos_impressos(
    atendimento_ids, agora: datetime | None = None, versoes: dict | None = None
) -> int:
    """Marca como impressos os recibos ainda não marcados: reimprimir não muda a data da
    primeira impressão. Com `versoes` ({atendimento: versão do pedido na página}), ignora o
    pedido editado depois que a página abriu: o que saiu na impressora era a versão anterior."""
    versoes = versoes or {}
    ids = list(atendimento_ids)
    conferem = Q(id__in=[i for i in ids if i not in versoes])
    for atendimento_id, versao in versoes.items():
        conferem |= Q(id=atendimento_id, pedido__versao=versao)
    return (
        Atendimento.objects.filter(id__in=ids, recibo_impresso_em__isnull=True)
        .filter(conferem)
        .update(recibo_impresso_em=agora or timezone.now())
    )


def recibos_alterados(versoes: dict) -> list:
    """Atendimentos ainda não impressos cujo pedido mudou de versão desde que a página abriu."""
    return [
        atendimento_id
        for atendimento_id, versao in versoes.items()
        if Atendimento.objects.filter(id=atendimento_id, recibo_impresso_em__isnull=True)
        .exclude(pedido__versao=versao)
        .exists()
    ]


ACOES_TRAVA = ("lancada", "liberar", "nao_lancar")
MENSAGEM_LANCAMENTO_EM_ANDAMENTO = (
    "Há um lançamento no SCPI em andamento. Aguarde terminar para resolver as travas."
)
_ESTADOS_TRAVA = (VERIFICAR, EM_LANCAMENTO, ERRO)


def resolver_lote(
    lote: str,
    acao: str,
    *,
    usuario,
    requisicao: str = "",
    conferido: bool = False,
    agora: datetime | None = None,
) -> Resposta:
    """Resolve as linhas que o robô deixou travadas (`VERIFICAR`, `EM_LANCAMENTO`, `ERRO`) de um
    lote: informa a requisição, libera para relançar ou marca para não lançar. As demais linhas
    do lote nunca mudam. Recusada enquanto houver execução do robô em andamento."""
    if acao not in ACOES_TRAVA:
        return Resposta(ok=False, mensagem="Ação desconhecida.")
    agora = agora or timezone.now()
    if ExecucaoRobo.em_andamento(agora).exists():
        return Resposta(ok=False, mensagem=MENSAGEM_LANCAMENTO_EM_ANDAMENTO)
    requisicao = texto(requisicao)
    # A trava do lançamento fica com a resolução do começo ao fim: um robô que comece agora não
    # reserva linhas que esta resolução esteja liberando. (A checagem acima só cobre o que já
    # estava rodando.)
    with trava(TRAVA_LANCAMENTO) as obtida:
        if not obtida:
            return Resposta(ok=False, mensagem=MENSAGEM_LANCAMENTO_EM_ANDAMENTO)
        return _resolver_com_a_trava(lote, acao, usuario, requisicao, conferido, agora)


def _resolver_com_a_trava(lote, acao, usuario, requisicao, conferido, agora) -> Resposta:
    with transaction.atomic():
        linhas = list(
            LinhaSaida.objects.select_for_update()
            .filter(lote=lote, status__in=_ESTADOS_TRAVA)
            .order_by("seq")
        )
        if not linhas:
            return Resposta(ok=False, mensagem=f"Nenhuma linha do lote {lote} aguarda conferência.")
        if acao == "lancada" and not requisicao_valida(requisicao):
            return Resposta(
                ok=False, mensagem="Informe o número da requisição no formato 000000/00."
            )
        if (
            acao == "liberar"
            and not conferido
            and any(linha.status in (VERIFICAR, EM_LANCAMENTO) for linha in linhas)
        ):
            return Resposta(
                ok=False,
                mensagem=(
                    "Antes de liberar, confira no SCPI que a requisição não foi gravada e "
                    "marque a confirmação."
                ),
            )
        if acao == "lancada":
            novo, feito = LANCADA, f"Requisição {requisicao} informada"
            final = f"Lote {lote}: requisição {requisicao} registrada."
        elif acao == "liberar":
            novo, feito = PENDENTE, "Liberada para relançar"
            final = f"Lote {lote} liberado para o próximo lançamento."
        else:
            novo, feito = NAO_LANCAR, "Marcada para não lançar"
            final = f"Lote {lote} marcado para não lançar no SCPI."
        quando = timezone.localtime(agora).strftime("%d/%m/%Y %H:%M")
        rotulos = dict(LinhaSaida.Status.choices)
        for linha in linhas:
            antes = rotulos.get(linha.status, linha.status)
            anterior = linha.mensagem.strip()
            historico = f"Antes: {antes} — {anterior}" if anterior else f"Antes: {antes}."
            linha.mensagem = f"{feito} por {usuario.username} em {quando}. {historico}"
            linha.status = novo
            if acao == "lancada":
                linha.requisicao_scpi = requisicao
                linha.lancado_em = agora
            elif acao == "liberar":
                # Linha liberada volta sem número: com ele, o robô a trataria como lançada.
                linha.requisicao_scpi = ""
                linha.lancado_em = None
        campos = ["status", "mensagem"]
        if acao in ("lancada", "liberar"):
            campos += ["requisicao_scpi", "lancado_em"]
        LinhaSaida.objects.bulk_update(linhas, campos)
    return Resposta(ok=True, mensagem=final)
