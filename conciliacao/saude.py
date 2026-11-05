"""Avisos de saúde da conciliação (spec 010, FR-028): entram na lista curta do painel e nos
avisos da visão geral de Automações, pelo `catalogo.saude`."""

from datetime import datetime, timedelta

from catalogo.models import Importacao
from catalogo.saude import ItemSaude, _quando, resumo_do_erro
from conciliacao.consultas import PROBLEMAS, lotes_conferidos
from conciliacao.models import ConferenciaLote
from scpi.gravacao import lista_curta

Veredito = ConferenciaLote.Veredito


def um_dia_util_antes(agora: datetime) -> datetime:
    """O mesmo horário no dia útil anterior (sábado e domingo não contam; feriado, sim)."""
    antes = agora - timedelta(days=1)
    while antes.weekday() >= 5:
        antes -= timedelta(days=1)
    return antes


def _lotes(lotes: list[str], singular: str, plural: str) -> str:
    n = len(lotes)
    frase = f"1 requisição {singular}" if n == 1 else f"{n} requisições {plural}"
    return f"{frase}: {lista_curta(lotes)}."


def avisos(agora: datetime) -> list[ItemSaude]:
    saude = []
    ultima = Importacao.objects.filter(tipo=Importacao.Tipo.REQUISICOES).order_by("-inicio").first()
    if ultima is not None and ultima.situacao == Importacao.Situacao.FALHA:
        saude.append(
            ItemSaude(
                "erro",
                "Requisições do SCPI: a última extração falhou em "
                f"{_quando(ultima.fim or ultima.inicio)}: {resumo_do_erro(ultima.erro)}",
            )
        )
    lotes = lotes_conferidos()
    divergentes = [
        i.lote
        for i in lotes
        if i.conferencia
        and i.conferencia.veredito in PROBLEMAS
        and i.conferencia.veredito != Veredito.NAO_ENCONTRADO
    ]
    if divergentes:
        saude.append(
            ItemSaude(
                "aviso",
                _lotes(
                    divergentes,
                    "lançada com divergência no SCPI",
                    "lançadas com divergência no SCPI",
                ),
            )
        )
    nao_encontrados = [
        i.lote for i in lotes if i.conferencia and i.conferencia.veredito == Veredito.NAO_ENCONTRADO
    ]
    if nao_encontrados:
        saude.append(
            ItemSaude(
                "erro",
                _lotes(
                    nao_encontrados,
                    "lançada não encontrada no SCPI",
                    "lançadas não encontradas no SCPI",
                ),
            )
        )
    limite = um_dia_util_antes(agora)
    atrasados = [
        i.lote
        for i in lotes
        if i.conferencia is None and i.esperando_desde and i.esperando_desde < limite
    ]
    if atrasados:
        saude.append(
            ItemSaude(
                "aviso",
                _lotes(
                    atrasados,
                    "aguardando conferência há mais de um dia útil",
                    "aguardando conferência há mais de um dia útil",
                ),
            )
        )
    return saude
