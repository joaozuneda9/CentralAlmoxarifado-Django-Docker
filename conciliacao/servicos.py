"""Gravações da conciliação (spec 010). Só o app `conciliacao` muda aqui; as linhas de saída
nunca (FR-021, Princípio II)."""

import logging
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal

from django.db import Error, connection, transaction

from catalogo.models import Importacao, ParDePara
from conciliacao import regras
from conciliacao.models import (
    Candidata,
    ConferenciaLote,
    ExtracaoOficial,
    RequisicaoOficial,
    TentativaLancamento,
)
from pedidos.models import LinhaSaida
from pedidos.regras import (
    EM_LANCAMENTO,
    LANCADA,
    VERIFICAR,
    norm_placa,
    resolver_centro_custo,
)
from pedidos.servicos import centros
from scpi.requisicoes import placa_do_centro

logger = logging.getLogger("scpi.lancamento")

TRAVADOS = (VERIFICAR, EM_LANCAMENTO)


def ultima_tentativa(lote: str) -> TentativaLancamento | None:
    """A tentativa mais recente que deixou o lote em dúvida (passou do Salvar sem número)."""
    return (
        TentativaLancamento.objects.filter(
            lote=lote, resultado=TentativaLancamento.Resultado.VERIFICAR
        )
        .select_related("execucao")
        .order_by("-momento", "-pk")
        .first()
    )


def piso(execucao) -> str | None:
    """O maior número de requisição que já existia quando a execução começou: o da extração de
    antes; numa execução histórica, sem ela, o maior número de lote lançado antes do início
    (research R15)."""
    antes = (
        ExtracaoOficial.objects.filter(
            execucao=execucao,
            motivo=ExtracaoOficial.Motivo.ANTES,
            importacao__situacao=Importacao.Situacao.SUCESSO,
        )
        .order_by("-pk")
        .first()
    )
    if antes is not None:
        return antes.maior_requisicao
    numeros = (
        LinhaSaida.objects.filter(lancado_em__lt=execucao.inicio)
        .exclude(requisicao_scpi="")
        .values_list("requisicao_scpi", flat=True)
        .distinct()
    )
    return regras.maior_requisicao(n for n in numeros if regras.RE_REQUISICAO.match(n))


def _resumo(requisicao: RequisicaoOficial) -> regras.RequisicaoResumo:
    return regras.RequisicaoResumo(
        requisicao=requisicao.requisicao,
        lote_observado=requisicao.lote_observado,
        tipo=requisicao.tipo,
        cod_ccusto=requisicao.cod_ccusto,
        itens=tuple((item.codigo, item.quantidade) for item in requisicao.itens.all()),
    )


def _cobre(extracao: ExtracaoOficial, datas) -> bool:
    imp = extracao.importacao
    return imp.periodo_de is not None and all(
        imp.periodo_de <= data <= imp.periodo_ate for data in datas
    )


def conciliar_verificar(extracao: ExtracaoOficial, falhas: list[str] | None = None) -> int:
    """Grava, para cada lote em verificar coberto pela extração, a conferência com o intervalo
    e as candidatas (FR-022, FR-023). Só vale a extração bem-sucedida que começou depois da
    tentativa; um lote sem tentativa registrada ganha `SEM_TENTATIVA`. Devolve quantas gravou.
    Com `falhas`, o lote que quebra vai para a lista e os seguintes continuam; sem ela, sobe."""
    if not extracao.bem_sucedida or extracao.motivo == ExtracaoOficial.Motivo.ARQUIVO:
        # Um arquivo exportado antes do Salvar perdido não traria a requisição: se contasse, o
        # intervalo sairia vazio e o lote seria relançado (Princípio III).
        return 0
    datas: dict[str, set] = {}
    for lote, data in LinhaSaida.objects.filter(status__in=TRAVADOS).values_list("lote", "data"):
        datas.setdefault(lote, set()).add(data)
    lidas = {
        requisicao.pk: _resumo(requisicao)
        for requisicao in extracao.requisicoes_lidas.prefetch_related("itens")
    }
    por_numero = {resumo.requisicao: pk for pk, resumo in lidas.items()}
    gravadas = 0
    for lote, datas_do_lote in sorted(datas.items()):
        try:
            if not _cobre(extracao, datas_do_lote):
                continue
            if ConferenciaLote.objects.filter(
                lote=lote, extracao=extracao, tipo=ConferenciaLote.Tipo.VERIFICAR
            ).exists():
                continue
            tentativa = ultima_tentativa(lote)
            if tentativa is None:
                ConferenciaLote.objects.create(
                    lote=lote,
                    extracao=extracao,
                    tipo=ConferenciaLote.Tipo.VERIFICAR,
                    veredito=ConferenciaLote.Veredito.SEM_TENTATIVA,
                )
                gravadas += 1
                continue
            if extracao.importacao.inicio <= tentativa.momento:
                continue  # a extração não é posterior à tentativa: não prova nada sobre ela
            tentativas = [
                regras.TentativaResumo(t.ordem, t.lote, t.requisicao)
                for t in tentativa.execucao.tentativas.all()
            ]
            de, ate = regras.intervalo(tentativas, piso(tentativa.execucao), lote)
            achadas = regras.candidatas(lidas.values(), lote, de, ate, tentativa.foto)
            with transaction.atomic():
                conferencia = ConferenciaLote.objects.create(
                    lote=lote,
                    extracao=extracao,
                    tipo=ConferenciaLote.Tipo.VERIFICAR,
                    veredito=ConferenciaLote.Veredito.COM_CANDIDATAS
                    if achadas
                    else ConferenciaLote.Veredito.INTERVALO_VAZIO,
                    intervalo_de=de or "",
                    intervalo_ate=ate or "",
                    tentativa=tentativa,
                )
                Candidata.objects.bulk_create(
                    Candidata(
                        conferencia=conferencia,
                        requisicao_id=por_numero[resumo.requisicao],
                        e_esta=e_esta,
                        ordem=ordem,
                    )
                    for ordem, (resumo, e_esta) in enumerate(achadas, start=1)
                )
            gravadas += 1
            logger.info(
                "  %s em verificar: intervalo %s a %s, %d candidata(s)",
                lote,
                de or "(aberto)",
                ate or "(aberto)",
                len(achadas),
            )
        except Exception as exc:
            if falhas is None:
                raise
            logger.exception("⚠ não foi possível conferir o lote %s (em verificar)", lote)
            falhas.append(f"lote {lote} (em verificar): {exc}")
    return gravadas


# --- Lotes lançados: veredito e revisão (spec 010, PR 4) ---


def _oficial(requisicao: RequisicaoOficial) -> regras.Oficial:
    return regras.Oficial(
        requisicao=requisicao.requisicao,
        lote_observado=requisicao.lote_observado,
        data=requisicao.data,
        tipo=requisicao.tipo,
        cod_ccusto=requisicao.cod_ccusto,
        centro_nome=requisicao.centro_nome,
        recebedor=requisicao.recebedor,
        itens=tuple(
            regras.ItemConferido(item.codigo, item.quantidade, item.placa)
            for item in requisicao.itens.all()
        ),
    )


def _qtd(texto) -> Decimal:
    return Decimal(str(texto).replace(".", "").replace(",", "."))


def entrega_da_foto(foto: dict, centro_nome: str) -> regras.Entrega:
    """A entrega como o robô a digitou (a foto da tentativa, research R11)."""
    return regras.Entrega(
        data=datetime.strptime(foto["data"], "%d/%m/%Y").date(),
        tipo=foto.get("tipo_saida", ""),
        cod_ccusto=str(foto.get("cod_ccusto", "")),
        centro_nome=centro_nome,
        recebedor=foto.get("recebedor", ""),
        placa_centro=foto.get("placa_centro", ""),
        itens=tuple(
            regras.ItemConferido(item["codigo"], _qtd(item["qtd"]), item.get("placa", ""))
            for item in foto.get("itens", [])
        ),
    )


def entrega_das_linhas(linhas: list[LinhaSaida], lista_de_centros) -> regras.Entrega:
    """A entrega de um lote lançado sem foto (antes da conciliação), recalculada das linhas de
    saída com o cadastro de centros de hoje, pela mesma regra do robô (research R10)."""
    primeira = linhas[0]
    centro = resolver_centro_custo(primeira.centro_custo, primeira.placa, lista_de_centros)
    return regras.Entrega(
        data=primeira.data,
        tipo=primeira.tipo_saida,
        cod_ccusto=centro.codigo,
        centro_nome=primeira.centro_custo,
        recebedor=primeira.recebedor,
        placa_centro=placa_do_centro(centro.codigo, lista_de_centros) if centro.codigo else "",
        itens=tuple(
            regras.ItemConferido(linha.codigo, linha.qtd, norm_placa(linha.placa))
            for linha in linhas
        ),
    )


def _veredito_conclusivo(lote: str) -> ConferenciaLote | None:
    """A conferência do lançamento: a primeira conclusiva (FR-017, data-model)."""
    return (
        ConferenciaLote.objects.filter(lote=lote, tipo=ConferenciaLote.Tipo.LANCAMENTO)
        .exclude(veredito=ConferenciaLote.Veredito.AGUARDANDO)
        .select_related("requisicao")
        .order_by("criada_em", "pk")
        .first()
    )


def conciliar_lancados(
    extracao: ExtracaoOficial, falhas: list[str] | None = None
) -> dict[str, int]:
    """Grava o veredito de cada lote lançado coberto pela extração (FR-016 a FR-018).

    Só conta a extração bem-sucedida que começou depois do lançamento do lote. Enquanto o lote
    não tem conferência conclusiva, a conferência é do tipo `LANCAMENTO` (as `AGUARDANDO` são
    provisórias); depois da primeira conclusiva, as seguintes são `REVISAO`, com o
    "alterado no SCPI depois do lançamento" contra a requisição daquela. Devolve a contagem
    por veredito. Nunca muda as linhas de saída (FR-021). Com `falhas`, o lote que quebra (uma
    foto malformada, por exemplo) vai para a lista e os seguintes continuam; sem ela, sobe."""
    contagem: dict[str, int] = {}
    if not extracao.bem_sucedida:
        return contagem
    imp = extracao.importacao
    linhas_por_lote: dict[str, list[LinhaSaida]] = {}
    for linha in LinhaSaida.objects.filter(
        status=LANCADA, data__range=(imp.periodo_de, imp.periodo_ate)
    ).order_by("lote", "seq"):
        linhas_por_lote.setdefault(linha.lote, []).append(linha)
    oficiais = [
        _oficial(requisicao) for requisicao in extracao.requisicoes_lidas.prefetch_related("itens")
    ]
    pk_por_numero = dict(extracao.requisicoes_lidas.values_list("requisicao", "pk"))
    depara = dict(ParDePara.objects.values_list("antigo", "novo"))
    lista_de_centros = centros()
    for lote, linhas in sorted(linhas_por_lote.items()):
        try:
            lancado = max((linha.lancado_em for linha in linhas if linha.lancado_em), default=None)
            if lancado is None or imp.inicio <= lancado:
                continue  # a extração começou antes do lançamento: não pode trazê-lo
            if ConferenciaLote.objects.filter(
                lote=lote,
                extracao=extracao,
                tipo__in=(ConferenciaLote.Tipo.LANCAMENTO, ConferenciaLote.Tipo.REVISAO),
            ).exists():
                continue
            numero = linhas[0].requisicao_scpi
            # A foto da última tentativa que chegou ao Salvar: a lançada, ou a que ficou em
            # verificar e foi resolvida à mão com o número (o SCPI salvou e a resposta se perdeu).
            # Sem nenhuma, o lote é de antes da conciliação, e a entrega se recalcula das linhas.
            tentativa = (
                TentativaLancamento.objects.filter(
                    lote=lote,
                    foto__isnull=False,
                    resultado__in=(
                        TentativaLancamento.Resultado.LANCADA,
                        TentativaLancamento.Resultado.VERIFICAR,
                    ),
                )
                .order_by("-momento", "-pk")
                .first()
            )
            entrega = (
                entrega_da_foto(tentativa.foto, linhas[0].centro_custo)
                if tentativa
                else entrega_das_linhas(linhas, lista_de_centros)
            )
            em_outro_lote = (
                LinhaSaida.objects.filter(requisicao_scpi=numero).exclude(lote=lote).exists()
            )
            primeira = _veredito_conclusivo(lote)
            if primeira is not None and extracao.motivo == ExtracaoOficial.Motivo.ARQUIVO:
                # Um arquivo antigo não revisa um veredito: não se sabe quando foi exportado.
                continue
            resultado = regras.veredito(
                lote,
                numero,
                oficiais,
                entrega,
                maior=extracao.maior_requisicao,
                numero_em_outro_lote=em_outro_lote,
                depara=depara,
                espera_observacoes=bool(tentativa and tentativa.foto.get("observacoes")),
                ja_vista=bool(primeira and primeira.requisicao_id),
            )
            tipo = ConferenciaLote.Tipo.REVISAO if primeira else ConferenciaLote.Tipo.LANCAMENTO
            alterado = False
            diferencas = list(resultado.diferencas)
            if primeira is not None and primeira.requisicao:
                if resultado.requisicao:
                    mudou = regras.alteracoes(_oficial(primeira.requisicao), resultado.requisicao)
                else:  # a requisição conferida no lançamento sumiu do relatório (excluída no SCPI)
                    mudou = [
                        {
                            "campo": "requisição",
                            "antes": primeira.requisicao.requisicao,
                            "agora": "(ausente no relatório)",
                        }
                    ]
                alterado = bool(mudou)
                diferencas += [{"campo": m["campo"], "esperado": m["antes"], "oficial": m["agora"],
                                "alteracao": True} for m in mudou]  # fmt: skip
            ConferenciaLote.objects.create(
                lote=lote,
                extracao=extracao,
                tipo=tipo,
                veredito=resultado.veredito,
                requisicao_id=pk_por_numero.get(resultado.requisicao.requisicao)
                if resultado.requisicao
                else None,
                outra_requisicao_id=pk_por_numero.get(resultado.outra.requisicao)
                if resultado.outra
                else None,
                origem_vinculo=resultado.origem,
                diferencas=diferencas,
                notas=list(resultado.notas),
                alterado_depois=alterado,
                tentativa=tentativa,
            )
            contagem[resultado.veredito] = contagem.get(resultado.veredito, 0) + 1
        except Exception as exc:
            if falhas is None:
                raise
            logger.exception("⚠ não foi possível conferir o lote %s (lançado)", lote)
            falhas.append(f"lote {lote} (lançado): {exc}")
    return contagem


TRAVA_CONCILIACAO = "almoxarifado:conciliacao"
ESPERA_TRAVA_S = 120


class ConciliacaoEmAndamento(Exception):
    """Outra conciliação segurou a trava por mais que a espera."""


class ConciliacaoIncompleta(Exception):
    """Algum lote, ou alguma etapa, falhou; `contagem` é o que ficou gravado desta extração (os
    outros lotes seguem gravados; só o que falhou fica de fora)."""

    def __init__(self, contagem: dict[str, int], falhas: list[str]):
        self.contagem = contagem
        self.falhas = falhas
        super().__init__("Conciliação incompleta: " + "; ".join(falhas))


@contextmanager
def _trava_conciliacao():
    """Uma conciliação por vez entre processos (`GET_LOCK`, com espera): duas ao mesmo tempo
    poderiam gravar, cada uma, a conferência do lançamento do mesmo lote."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s)", [TRAVA_CONCILIACAO, ESPERA_TRAVA_S])
        obtida = cursor.fetchone()[0] == 1
    if not obtida:
        raise ConciliacaoEmAndamento("Outra conciliação com o SCPI está em andamento.")
    try:
        yield
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", [TRAVA_CONCILIACAO])
        except Error:
            logger.warning("Não foi possível liberar a trava da conciliação.", exc_info=True)


def _gravadas(extracao: ExtracaoOficial) -> dict[str, int]:
    """O que já está gravado desta extração, lido do banco: depois de uma falha no meio de uma
    etapa, as conferências dos lotes anteriores ficam (cada uma na sua transação; nos em verificar,
    apagá-las perderia uma candidata já vista), e a contagem tem de dizê-lo."""
    contagem: dict[str, int] = {}
    for tipo, veredito in ConferenciaLote.objects.filter(extracao=extracao).values_list(
        "tipo", "veredito"
    ):
        chave = "VERIFICAR" if tipo == ConferenciaLote.Tipo.VERIFICAR else veredito
        contagem[chave] = contagem.get(chave, 0) + 1
    return contagem


def conciliar(extracao: ExtracaoOficial) -> dict[str, int]:
    """Toda a conciliação de uma extração, sob a trava: primeiro os lotes em verificar (a que
    protege contra lançar duas vezes), depois os lançados. Um lote que falha não impede os outros,
    nem uma etapa a outra, mas a falha não fica escondida: no fim, `ConciliacaoIncompleta` leva
    a contagem do que ficou gravado e o que falhou. Quem chama decide: o robô só registra no
    log; os comandos saem com erro."""
    contagem: dict[str, int] = {}
    falhas: list[str] = []
    with _trava_conciliacao():
        try:
            verificar = conciliar_verificar(extracao, falhas)
        except Exception as exc:
            logger.exception("⚠ não foi possível conferir os lotes em verificar")
            falhas.append(f"lotes em verificar: {exc}")
        else:
            if verificar:
                contagem["VERIFICAR"] = verificar
        try:
            contagem = conciliar_lancados(extracao, falhas) | contagem
        except Exception as exc:
            logger.exception("⚠ não foi possível conferir os lotes lançados")
            falhas.append(f"lotes lançados: {exc}")
    if falhas:
        raise ConciliacaoIncompleta(_gravadas(extracao), falhas)
    return contagem
