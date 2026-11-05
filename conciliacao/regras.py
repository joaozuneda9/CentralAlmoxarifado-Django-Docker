"""Regras puras da conciliação com o SCPI (spec 010): sem ORM, testáveis sem banco."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from pedidos.regras import norm_u

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


# --- Lote em verificar: intervalo e candidatas (spec 010, FR-022 e FR-023, research R14) ---


@dataclass(frozen=True)
class TentativaResumo:
    """Uma tentativa da execução, só com o que o intervalo usa."""

    ordem: int
    lote: str
    requisicao: str  # o número obtido; vazio se não lançou


@dataclass(frozen=True)
class RequisicaoResumo:
    """Uma requisição oficial, só com o que as candidatas usam."""

    requisicao: str
    lote_observado: str
    tipo: str = ""
    cod_ccusto: str = ""
    itens: tuple[tuple[str, Decimal], ...] = ()


def intervalo(
    tentativas: Iterable[TentativaResumo], piso: str | None, lote: str
) -> tuple[str | None, str | None]:
    """Os limites, exclusivos, onde a requisição do `lote` estaria se o SCPI a salvou.

    Inferior: o maior número conhecido antes da tentativa (o piso da execução e os números das
    tentativas anteriores). Superior: o primeiro número obtido por uma tentativa posterior; sem
    nenhuma, fica aberto (None). O superior fica de fora: é o número do lote seguinte."""
    tentativas = list(tentativas)
    alvo = next(t for t in tentativas if t.lote == lote)
    antes = [t.requisicao for t in tentativas if t.ordem < alvo.ordem and t.requisicao]
    depois = [t.requisicao for t in tentativas if t.ordem > alvo.ordem and t.requisicao]
    de = maior_requisicao([*([piso] if piso else []), *antes])
    ate = min(depois, key=chave, default=None)
    return de, ate


def no_intervalo(requisicao: str, de: str | None, ate: str | None) -> bool:
    """Se o número fica estritamente entre os limites (None = aberto daquele lado)."""
    numero = chave(requisicao)
    return (de is None or numero > chave(de)) and (ate is None or numero < chave(ate))


def _qtd(texto: object) -> Decimal | None:
    try:
        return Decimal(str(texto).replace(".", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def semelhanca(requisicao: RequisicaoResumo, foto: dict | None) -> int:
    """Quanto a requisição se parece com o que o robô ia digitar: só ordena as candidatas, nunca
    decide nada. Itens iguais pesam mais; depois os mesmos códigos, o tipo e o centro."""
    if not foto:
        return 0
    esperado = sorted(
        (norm_u(item.get("codigo")), _qtd(item.get("qtd"))) for item in foto.get("itens", [])
    )
    oficial = sorted((norm_u(codigo), qtd) for codigo, qtd in requisicao.itens)
    pontos = 0
    if esperado and esperado == oficial:
        pontos += 3
    elif {c for c, _ in esperado} == {c for c, _ in oficial}:
        pontos += 1
    if norm_u(requisicao.tipo) == norm_u(foto.get("tipo_saida")):
        pontos += 1
    if requisicao.cod_ccusto.lstrip("0") == str(foto.get("cod_ccusto", "")).lstrip("0"):
        pontos += 1
    return pontos


def candidatas(
    requisicoes: Iterable[RequisicaoResumo],
    lote: str,
    de: str | None,
    ate: str | None,
    foto: dict | None = None,
) -> list[tuple[RequisicaoResumo, bool]]:
    """As requisições que podem ser do `lote`, com a marca "é esta".

    Toda requisição no intervalo é candidata, seja qual for o tipo ou o conteúdo, salvo a que tem
    outro lote nas observações. A que tem este lote nas observações é candidata e "é esta" mesmo
    fora do intervalo (um número lido errado): é a prova mais forte de que o SCPI salvou. A ordem
    é a das marcadas, depois a semelhança com a foto, depois o número."""
    lote = lote.upper()
    escolhidas = []
    for requisicao in requisicoes:
        if requisicao.lote_observado == lote:
            escolhidas.append((requisicao, True))
        elif not requisicao.lote_observado and no_intervalo(requisicao.requisicao, de, ate):
            escolhidas.append((requisicao, False))
    return sorted(
        escolhidas,
        key=lambda par: (not par[1], -semelhanca(par[0], foto), chave(par[0].requisicao)),
    )
