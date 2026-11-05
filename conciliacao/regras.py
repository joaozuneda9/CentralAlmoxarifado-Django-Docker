"""Regras puras da conciliação com o SCPI (spec 010): sem ORM, testáveis sem banco."""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from pedidos.regras import norm_u, saldo_br

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


# --- Lote lançado: comparação e veredito (spec 010, FR-015 a FR-020, research R10 e R12) ---


@dataclass(frozen=True)
class ItemConferido:
    codigo: str
    qtd: Decimal
    placa: str = ""


@dataclass(frozen=True)
class Entrega:
    """O que deveria estar no SCPI: a foto da tentativa, ou as linhas de saída de um lote lançado
    antes da conciliação. `placa_centro` é a que o SCPI preenche sozinho pelo centro."""

    data: date
    tipo: str
    cod_ccusto: str
    centro_nome: str
    recebedor: str
    placa_centro: str
    itens: tuple[ItemConferido, ...]


@dataclass(frozen=True)
class Oficial:
    """Uma requisição como o relatório a trouxe."""

    requisicao: str
    lote_observado: str
    data: date
    tipo: str
    cod_ccusto: str
    centro_nome: str
    recebedor: str
    itens: tuple[ItemConferido, ...]


@dataclass(frozen=True)
class Resultado:
    veredito: str
    requisicao: Oficial | None = None
    outra: Oficial | None = None
    origem: str = ""  # OBSERVACOES, NUMERO, AMBOS
    diferencas: tuple[dict, ...] = ()
    notas: tuple[dict, ...] = ()


def texto_igual(a: object, b: object) -> bool:
    """Igualdade de texto da conferência (FR-019b): ignora a forma Unicode dos acentos, as
    maiúsculas e os espaços nas pontas."""

    def normal(valor: object) -> str:
        return unicodedata.normalize("NFC", str(valor or "")).casefold().strip()

    return normal(a) == normal(b)


def _codigo_centro(codigo: str) -> str:
    return str(codigo or "").strip().lstrip("0")


def _placa(valor: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(valor or "").upper())


def _itens_texto(itens) -> str:
    return "; ".join(f"{codigo} × {saldo_br(qtd)}" for codigo, qtd in itens) or "nenhum"


def _placas_texto(pares) -> str:
    return ", ".join(f"{codigo} {placa or '(sem placa)'}" for codigo, placa in pares) or "nenhum"


def comparar(
    entrega: Entrega, oficial: Oficial, depara: dict[str, str] | None = None
) -> tuple[list[dict], list[dict]]:
    """As diferenças (campo, esperado, oficial) e as notas entre a entrega e a requisição.

    Códigos por `norm_u` e nunca pelo de/para (FR-019b, FR-020): um par só vira nota. O centro
    é comparado pelo código; o nome diferente é nota (FR-019a), e o centro sem código esperado
    (o lote antigo cujo centro saiu do cadastro) não é conferido. A placa esperada de cada item é
    a do item ou, sem ela, a do centro (FR-019), conferida também quando os itens divergem."""
    depara = depara or {}
    diferencas: list[dict] = []
    notas: list[dict] = []

    def diferenca(campo, esperado, encontrado):
        diferencas.append({"campo": campo, "esperado": str(esperado), "oficial": str(encontrado)})

    if not texto_igual(entrega.tipo, oficial.tipo):
        diferenca("tipo", entrega.tipo, oficial.tipo or "(vazio)")
    if entrega.data != oficial.data:
        diferenca("data", f"{entrega.data:%d/%m/%Y}", f"{oficial.data:%d/%m/%Y}")
    if not _codigo_centro(entrega.cod_ccusto):
        notas.append(
            {
                "campo": "centro de custo",
                "texto": f'"{entrega.centro_nome}" não está mais no cadastro de centros; o centro '
                f"não foi conferido (no SCPI, {oficial.cod_ccusto})",
            }
        )
    elif _codigo_centro(entrega.cod_ccusto) != _codigo_centro(oficial.cod_ccusto):
        diferenca("centro de custo", entrega.cod_ccusto, oficial.cod_ccusto)
    elif (
        entrega.centro_nome
        and oficial.centro_nome
        and not texto_igual(entrega.centro_nome, oficial.centro_nome)
    ):
        notas.append(
            {
                "campo": "centro de custo",
                "texto": f"mesmo código {oficial.cod_ccusto}, nome no SCPI "
                f'"{oficial.centro_nome}" (no Central, "{entrega.centro_nome}")',
            }
        )
    if not texto_igual(entrega.recebedor, oficial.recebedor):
        diferenca("recebedor", entrega.recebedor, oficial.recebedor or "(vazio)")

    esperados = sorted((norm_u(i.codigo), i.qtd) for i in entrega.itens)
    achados = sorted((norm_u(i.codigo), i.qtd) for i in oficial.itens)
    if esperados != achados:
        # "código" só quando uma linha trocou de código e nada mais: as mesmas quantidades, mas
        # a contagem de linhas de algum código diferente. O resto (quantidades trocadas entre os
        # mesmos códigos, item a mais ou a menos) é "itens".
        mesmas_qtds = sorted(q for _, q in esperados) == sorted(q for _, q in achados)

        def qtds(lista, codigo):
            return sorted(q for c, q in lista if c == codigo)

        comuns_lista = {c for c, _ in esperados} & {c for c, _ in achados}
        mesmas_qtds_nos_comuns = all(qtds(esperados, c) == qtds(achados, c) for c in comuns_lista)
        trocou_codigo = (
            mesmas_qtds
            and mesmas_qtds_nos_comuns
            and Counter(c for c, _ in esperados) != Counter(c for c, _ in achados)
        )
        # Só o que difere: o que está só no lote e o que está só no SCPI (contando repetidos).
        so_no_lote = list((Counter(esperados) - Counter(achados)).elements())
        so_no_scpi = list((Counter(achados) - Counter(esperados)).elements())
        diferenca(
            "código" if trocou_codigo else "itens",
            _itens_texto(sorted(so_no_lote)),
            _itens_texto(sorted(so_no_scpi)),
        )
        codigos_lote = {c for c, _ in esperados} - {c for c, _ in achados}
        codigos_scpi = {c for c, _ in achados} - {c for c, _ in esperados}
        for antigo, novo in sorted(depara.items()):
            ida = norm_u(antigo) in codigos_scpi and norm_u(novo) in codigos_lote
            volta = norm_u(antigo) in codigos_lote and norm_u(novo) in codigos_scpi
            if ida or volta:
                notas.append(
                    {"campo": "código", "texto": f"de/para: {antigo} → {novo} (só explicação)"}
                )

    # A placa, por código, nos códigos que estão dos dois lados (mesmo com os itens divergindo).
    comuns = {norm_u(i.codigo) for i in entrega.itens} & {norm_u(i.codigo) for i in oficial.itens}
    placas_esperadas = sorted(
        (norm_u(i.codigo), _placa(i.placa or entrega.placa_centro))
        for i in entrega.itens
        if norm_u(i.codigo) in comuns
    )
    placas_oficiais = sorted(
        (norm_u(i.codigo), _placa(i.placa)) for i in oficial.itens if norm_u(i.codigo) in comuns
    )
    if Counter(placas_esperadas) != Counter(placas_oficiais):
        diferenca("placa", _placas_texto(placas_esperadas), _placas_texto(placas_oficiais))
    return diferencas, notas


def veredito(
    lote: str,
    numero: str,
    requisicoes: Iterable[Oficial],
    entrega: Entrega,
    *,
    maior: str | None,
    numero_em_outro_lote: bool = False,
    depara: dict[str, str] | None = None,
    espera_observacoes: bool = True,
    ja_vista: bool = False,
) -> Resultado:
    """O veredito de um lote lançado numa extração bem-sucedida que cobre a sua data (R12).

    Liga a requisição pelo lote nas observações e pelo número gravado; os dois têm de apontar
    para a mesma. Sem nenhuma das duas, "Não encontrado" só quando o relatório já traz número
    maior que o do lote (SC-008); antes disso, "Aguardando". Com `ja_vista` (uma conferência
    conclusiva já achou a requisição), sumir não é demora do relatório: é "Não encontrado"."""
    lote = lote.upper()
    requisicoes = list(requisicoes)
    pelas_obs = [r for r in requisicoes if r.lote_observado == lote]
    pelo_numero = next((r for r in requisicoes if r.requisicao == numero), None)
    if len(pelas_obs) > 1 or numero_em_outro_lote:
        primeira = pelas_obs[0] if pelas_obs else pelo_numero
        segunda = pelas_obs[1] if len(pelas_obs) > 1 else None
        return Resultado("DUPLICADO", primeira, segunda)
    if pelas_obs and pelo_numero and pelas_obs[0].requisicao != pelo_numero.requisicao:
        return Resultado("CONFLITO", pelo_numero, pelas_obs[0])
    if pelo_numero and pelo_numero.lote_observado and pelo_numero.lote_observado != lote:
        # O número gravado leva a uma requisição que as observações dão como de outro lote: ela
        # não pode comprovar esta entrega, mesmo com o conteúdo igual.
        return Resultado(
            "CONFLITO",
            pelo_numero,
            pelas_obs[0] if pelas_obs else None,
            origem="NUMERO",
            notas=(
                {
                    "campo": "observações",
                    "texto": f"a requisição {pelo_numero.requisicao} tem nas observações o lote "
                    f"{pelo_numero.lote_observado}",
                },
            ),
        )
    ligada = pelas_obs[0] if pelas_obs else pelo_numero
    if ligada is None:
        if ja_vista or (
            maior and RE_REQUISICAO.match(numero or "") and chave(maior) > chave(numero)
        ):
            return Resultado("NAO_ENCONTRADO")
        return Resultado("AGUARDANDO")
    origem = "AMBOS" if pelas_obs and pelo_numero else "OBSERVACOES" if pelas_obs else "NUMERO"
    diferencas, notas = comparar(entrega, ligada, depara)
    if origem == "NUMERO" and espera_observacoes:
        # Só quando o robô escreveu o lote (a foto o traz): os lotes de antes da conciliação
        # nunca o tiveram, e a nota em todos eles seria ruído.
        notas.append(
            {"campo": "observações", "texto": "o lote não está nas observações da requisição"}
        )
    return Resultado(
        "DIVERGENTE" if diferencas else "COMPROVADO",
        ligada,
        origem=origem,
        diferencas=tuple(diferencas),
        notas=tuple(notas),
    )


def alteracoes(antes: Oficial, agora: Oficial) -> list[dict]:
    """O que mudou na requisição entre a conferência do lançamento e uma revisão (FR-017).

    Compara os valores, não os textos: uma quantidade que muda na quarta casa é alteração."""
    mudou = []

    def itens(oficial):
        return sorted((norm_u(i.codigo), i.qtd) for i in oficial.itens)

    def placas(oficial):
        return sorted((norm_u(i.codigo), _placa(i.placa)) for i in oficial.itens)

    if not texto_igual(antes.tipo, agora.tipo):
        mudou.append({"campo": "tipo", "antes": antes.tipo, "agora": agora.tipo})
    if antes.data != agora.data:
        mudou.append(
            {"campo": "data", "antes": f"{antes.data:%d/%m/%Y}", "agora": f"{agora.data:%d/%m/%Y}"}
        )
    if _codigo_centro(antes.cod_ccusto) != _codigo_centro(agora.cod_ccusto):
        mudou.append(
            {"campo": "centro de custo", "antes": antes.cod_ccusto, "agora": agora.cod_ccusto}
        )
    if not texto_igual(antes.recebedor, agora.recebedor):
        mudou.append({"campo": "recebedor", "antes": antes.recebedor, "agora": agora.recebedor})
    if itens(antes) != itens(agora):
        mudou.append(
            {
                "campo": "itens",
                "antes": _itens_texto(itens(antes)),
                "agora": _itens_texto(itens(agora)),
            }
        )
    if placas(antes) != placas(agora):
        mudou.append(
            {
                "campo": "placa",
                "antes": _placas_texto(placas(antes)),
                "agora": _placas_texto(placas(agora)),
            }
        )
    return mudou
