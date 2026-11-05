"""Gravações da conciliação (spec 010). Só o app `conciliacao` muda aqui; as linhas de saída
nunca (FR-021, Princípio II)."""

import logging

from django.db import transaction

from catalogo.models import Importacao
from conciliacao import regras
from conciliacao.models import (
    Candidata,
    ConferenciaLote,
    ExtracaoOficial,
    RequisicaoOficial,
    TentativaLancamento,
)
from pedidos.models import LinhaSaida
from pedidos.regras import EM_LANCAMENTO, VERIFICAR

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


def conciliar_verificar(extracao: ExtracaoOficial) -> int:
    """Grava, para cada lote em verificar coberto pela extração, a conferência com o intervalo
    e as candidatas (FR-022, FR-023). Só vale a extração bem-sucedida que começou depois da
    tentativa; um lote sem tentativa registrada ganha `SEM_TENTATIVA`. Devolve quantas gravou."""
    if not extracao.bem_sucedida:
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
    return gravadas
