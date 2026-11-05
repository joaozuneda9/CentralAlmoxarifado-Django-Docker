"""Regras puras da conciliação com o SCPI (spec 010): sem ORM, testáveis sem banco."""

import re
from collections.abc import Iterable
from datetime import date, timedelta

RE_REQUISICAO = re.compile(r"^(\d{6})/(\d{2})$")  # número visível do SCPI: 003588/26
# No máximo 9 dígitos: o lote cabe nos 12 caracteres de `lote_observado` (e da `LinhaSaida`); um
# número maior não casa, e a falta do lote não prova nada.
RE_LOTE_OBSERVADO = re.compile(r"central\s+almoxarifado\s+((?:P|AV)-[0-9]{1,9})\b", re.IGNORECASE)

# O período de cada extração começa um dia antes da data mais antiga envolvida e termina um dia
# depois de hoje (o SCPI aceita fim no futuro): a folga cobre o fuso e a virada do dia.
FOLGA_PERIODO = timedelta(days=1)


def chave(requisicao: str) -> tuple[int, int]:
    """Chave de ordem de um número visível: '003588/26' → (2026, 3588). Inválido: ValueError.

    O número traz o ano: na virada, '000001/27' vem depois de '004512/26'."""
    casou = RE_REQUISICAO.match((requisicao or "").strip())
    if not casou:
        raise ValueError(f"número de requisição inválido: {requisicao!r}")
    return 2000 + int(casou.group(2)), int(casou.group(1))


def maior_requisicao(requisicoes: Iterable[str]) -> str | None:
    """O maior número visível pela chave (ano, número); None sem nenhum."""
    return max(requisicoes, key=chave, default=None)


def periodo(datas: Iterable[date], hoje: date) -> tuple[date, date]:
    """Período de uma extração: do dia anterior à data mais antiga envolvida (ou a hoje, sem
    nenhuma) até o dia seguinte a hoje."""
    inicio = min((*datas, hoje))
    return inicio - FOLGA_PERIODO, hoje + FOLGA_PERIODO


def texto_observacoes(lote: str, obs: str = "") -> str:
    """O que o robô escreve no campo Observações da requisição: o lote na primeira linha e, num
    parágrafo novo, a observação da saída registrada no Central, numa linha só.

    Duas proteções da leitura do relatório, que é um CSV sem aspas: o "Obs.: " no começo do
    parágrafo, porque uma linha que começa por uma data (dd/mm/aaaa) é lida como um registro novo;
    e o ";" trocado por ",", porque ele é o separador de campos e deslocaria as colunas."""
    marca = f"Central Almoxarifado {lote}"
    obs = " ".join((obs or "").replace(";", ",").split())
    return f"{marca}\nObs.: {obs}" if obs else marca


def lote_observado(observacoes: str) -> str:
    """O lote escrito pelo robô nas observações ('Central Almoxarifado AV-000036'), em
    maiúsculas; vazio quando não há. Prova presença; a falta dele não prova nada."""
    casou = RE_LOTE_OBSERVADO.search(observacoes or "")
    return casou.group(1).upper() if casou else ""
