"""Leitura dos CSVs do SCPI: bytes do relatório → linhas tipadas. Sem ORM.

As colunas são localizadas pelo nome do cabeçalho, nunca pela posição. Linha que não dá para
ler vira aviso (a importação segue); arquivo ilegível ou sem as colunas vira `ErroImportacao`.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from conciliacao.regras import chave
from pedidos.regras import norm_u
from scpi.normalizadores import registros_produtos, registros_saidas


class ErroImportacao(Exception):
    """Falha esperada de uma importação; a mensagem vai para a saúde do catálogo."""


class NadaAExibir(ErroImportacao):
    """O SCPI não gerou o relatório: avisou "Nada a exibir" (nenhum registro no filtro). Na
    "Relação de Requisições" sem filtro, quem baixa decide se isso vale (spec 010); um arquivo
    vazio, sem esse aviso, nunca vale."""


@dataclass(frozen=True)
class Leitura:
    linhas: list = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LinhaCadastro:
    codigo: str
    nome: str
    unidade: str
    grupo: str
    subgrupo: str
    oculto: bool


@dataclass(frozen=True)
class LinhaEstoque:
    codigo: str
    qtd: Decimal


@dataclass(frozen=True)
class LinhaSaidaSCPI:
    id_requi: str
    cadpro: str
    data: date
    qtd: Decimal
    valor: Decimal


def decimal_br(texto: str) -> Decimal:
    """'1.234,5' → Decimal('1234.5'); '8,9948' → Decimal('8.9948'). Inválido: ValueError."""
    t = (texto or "").strip()
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        valor = Decimal(t)
    except InvalidOperation:
        raise ValueError(f"número inválido: {texto!r}") from None
    if not valor.is_finite():
        raise ValueError(f"número inválido: {texto!r}")
    return valor


def data_br(texto: str) -> date:
    """'12/01/2026' (com ou sem hora depois) → date(2026, 1, 12). Inválida: ValueError."""
    return datetime.strptime((texto or "").strip()[:10], "%d/%m/%Y").date()


def _campos(registro: str, esperado: int | None = None) -> list[str]:
    """Campos de um registro (uma linha, já recolada).

    Cada registro é lido sozinho, para uma aspa solta nunca juntar registros. O SCPI não põe
    campos entre aspas (as quebras de linha vêm soltas), então uma aspa no começo de um campo é
    dado: se a leitura com aspas não bate com o número de colunas do cabeçalho e a leitura
    literal (só `;`) chega mais perto, vale a literal.
    """
    try:
        com_aspas = next(csv.reader([registro], delimiter=";"), [])
    except csv.Error:
        com_aspas = []
    literal = registro.split(";")
    if esperado is None:
        return com_aspas or literal
    if len(com_aspas) != esperado and abs(len(literal) - esperado) < abs(len(com_aspas) - esperado):
        return literal
    return com_aspas


def _salvo_por_planilha(texto: str, inicio_cabecalho: str) -> bool:
    """O cabeçalho é separado por vírgula: o CSV do SCPI passou por uma planilha (Google Sheets,
    Excel) e foi salvo de novo. O do SCPI usa ";"."""
    cabecalho = next(
        (linha for linha in texto.splitlines() if linha.startswith(inicio_cabecalho)), ""
    )
    return cabecalho.count(",") > cabecalho.count(";")


def _registros_da_planilha(texto: str) -> list[list[str]]:
    """CSV padrão separado por vírgula: as aspas protegem vírgulas e quebras de linha dentro dos
    campos, então não há registro partido para recolar. A quebra de linha de um campo vira
    espaço, como na recolagem dos CSVs do SCPI."""
    return [
        [" ".join(campo.split("\n")) if "\n" in campo else campo for campo in linha]
        for linha in csv.reader(io.StringIO(texto, newline=""))
    ]


def _tabela(
    conteudo: bytes,
    rotulo: str,
    registros,
    inicio_cabecalho: str,
    colunas: list[str],
    *,
    opcionais: tuple[str, ...] = (),
    completos: bool = False,
):
    """Linhas do CSV como dicionários {coluna pedida → texto}. Aceita o CSV do SCPI (";") e o
    mesmo relatório salvo por uma planilha (",").

    `opcionais` são colunas lidas quando existem (vazias quando faltam). Com `completos`, um
    registro com menos campos que o cabeçalho (relatório cortado) é `ErroImportacao`; sem ele, os
    campos que faltam viram vazios."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ErroImportacao(f"{rotulo}: o arquivo não está em UTF-8.") from None
    cabecalho: list[str] = []
    corpo: list[list[str]] = []
    if _salvo_por_planilha(texto, inicio_cabecalho):
        divididos = _registros_da_planilha(texto.replace("\r\n", "\n").replace("\r", "\n"))
        pos = next(
            (i for i, c in enumerate(divididos) if c and c[0].startswith(inicio_cabecalho)), None
        )
        if pos is not None:
            cabecalho = [c.strip() for c in divididos[pos]]
            corpo = divididos[pos + 1 :]
    else:
        linhas = registros(texto)
        pos = next(
            (i for i, linha in enumerate(linhas) if linha.startswith(inicio_cabecalho)), None
        )
        if pos is not None:
            cabecalho = [c.strip() for c in _campos(linhas[pos])]
            corpo = [_campos(registro, len(cabecalho)) for registro in linhas[pos + 1 :]]
    faltando = [c for c in colunas if c not in cabecalho]
    if faltando:
        raise ErroImportacao(f"{rotulo}: cabeçalho(s) ausente(s): {', '.join(faltando)}")
    indices = {c: cabecalho.index(c) for c in (*colunas, *opcionais) if c in cabecalho}
    tabela = []
    for numero, linha in enumerate(corpo, start=1):
        if not any(c.strip() for c in linha):
            continue
        if completos and len(linha) < len(cabecalho):
            raise ErroImportacao(
                f"{rotulo}: o relatório está cortado no registro {numero} "
                f"({len(linha)} de {len(cabecalho)} campos); nada foi gravado."
            )
        registro = {c: (linha[i].strip() if i < len(linha) else "") for c, i in indices.items()}
        registro.update({c: "" for c in opcionais if c not in indices})
        tabela.append(registro)
    return tabela


# Grupos do SCPI que nunca entram no cadastro: o 800 é o dos serviços, que o SCPI deixa sair nos
# relatórios dos tipos de produto. A linha é descartada antes de tudo, como se não viesse no CSV.
GRUPOS_DESCARTADOS = frozenset({"800"})


def ler_cadastro(conteudo: bytes | list[bytes]) -> Leitura:
    """Um CSV ou vários (o robô baixa um relatório por tipo de produto): as linhas de todos são
    juntadas na ordem, como se fossem um só cadastro. As dos `GRUPOS_DESCARTADOS` ficam de fora."""
    colunas = ["CADPRO", "DISC1", "UNID1", "GRUPO", "NOMEGRUPO", "NOMESUBGRUPO", "NOCULTAR"]
    partes = conteudo if isinstance(conteudo, list) else [conteudo]
    tabela = [
        linha
        for parte in partes
        for linha in _tabela(parte, "Cadastro", registros_produtos, "CADPRO", colunas)
    ]
    linhas, ignoradas = [], 0
    for r in tabela:
        if r["GRUPO"] in GRUPOS_DESCARTADOS:
            continue
        if not r["CADPRO"] or not r["DISC1"]:
            ignoradas += 1
            continue
        linhas.append(
            LinhaCadastro(
                codigo=r["CADPRO"],
                nome=r["DISC1"],
                unidade=r["UNID1"],
                grupo=r["NOMEGRUPO"],
                subgrupo=r["NOMESUBGRUPO"],
                oculto=norm_u(r["NOCULTAR"]) == "SIM",
            )
        )
    avisos = [f"Linhas sem código ou nome ignoradas: {ignoradas}."] if ignoradas else []
    return Leitura(linhas, avisos)


def ler_estoque(conteudo: bytes) -> Leitura:
    tabela = _tabela(conteudo, "Estoque", registros_produtos, "CADPRO", ["CADPRO", "QUAN3"])
    linhas, avisos = [], []
    for r in tabela:
        if not r["CADPRO"]:
            continue
        try:
            linhas.append(LinhaEstoque(r["CADPRO"], decimal_br(r["QUAN3"])))
        except ValueError:
            avisos.append(f"Quantidade inválida ignorada: {r['CADPRO']} ('{r['QUAN3']}').")
    return Leitura(linhas, avisos)


def ler_saidas(conteudo: bytes) -> Leitura:
    colunas = ["ID_REQUI", "CADPRO", "DTLAN", "QUAN2", "VATO2"]
    tabela = _tabela(conteudo, "Saídas do SCPI", registros_saidas, "GRUPO", colunas)
    linhas, avisos, sem_chave = [], [], 0
    for r in tabela:
        if not r["ID_REQUI"] or not r["CADPRO"]:
            sem_chave += 1
            continue
        onde = f"requisição {r['ID_REQUI']}, {r['CADPRO']}"
        try:
            data = data_br(r["DTLAN"])
        except ValueError:
            avisos.append(f"Data inválida ignorada: {onde} ('{r['DTLAN']}').")
            continue
        try:
            qtd = decimal_br(r["QUAN2"])
        except ValueError:
            avisos.append(f"Quantidade inválida ignorada: {onde} ('{r['QUAN2']}').")
            continue
        try:
            valor = decimal_br(r["VATO2"]) if r["VATO2"] else Decimal(0)
        except ValueError:
            avisos.append(f"Valor inválido ignorado: {onde} ('{r['VATO2']}').")
            continue
        linhas.append(LinhaSaidaSCPI(r["ID_REQUI"], r["CADPRO"], data, qtd, valor))
    if sem_chave:
        avisos.append(f"Linhas sem requisição ou código ignoradas: {sem_chave}.")
    return Leitura(linhas, avisos)


@dataclass(frozen=True)
class ItemLido:
    """Um item de uma requisição da "Relação de Requisições", na ordem do relatório."""

    codigo: str
    quantidade: Decimal
    unidade: str
    placa: str


@dataclass(frozen=True)
class RequisicaoLida:
    """Uma requisição da "Relação de Requisições" sem filtro de tipo (spec 010)."""

    requisicao: str  # número visível, 003588/26
    ano: int
    numero: int
    id_requi: int
    data: date  # DTLAN
    data_filtro: date | None  # DTPAG, a data pela qual o período do relatório filtra
    tipo: str
    cod_ccusto: str
    centro_nome: str
    recebedor: str
    observacoes: str
    responsavel: str
    entrada: bool
    itens: tuple[ItemLido, ...]


# Limite de `conciliacao.ItemOficial.quantidade` (DecimalField de 14 dígitos com 4 casas): uma
# quantidade fora dele seria arredondada ou recusada pelo banco, e a leitura é tudo ou nada.
CASAS_QUANTIDADE = 4
TETO_QUANTIDADE = Decimal(10) ** (14 - CASAS_QUANTIDADE)


def _quantidade_que_cabe(valor: Decimal) -> Decimal:
    """A quantidade como veio, se cabe exata no campo do banco; senão, ValueError.

    Primeiro a magnitude, depois a precisão: comparar com o valor quantizado a 4 casas é exato
    (o `normalize()` arredondaria pela precisão do contexto e aceitaria uma fração longa)."""
    if abs(valor) >= TETO_QUANTIDADE:
        raise ValueError(f"quantidade fora do limite: {valor}")
    if valor != valor.quantize(Decimal(1).scaleb(-CASAS_QUANTIDADE)):
        raise ValueError(f"quantidade com mais de {CASAS_QUANTIDADE} casas: {valor}")
    return valor


# Colunas do cabeçalho de uma requisição: repetidas em cada linha, iguais em todas.
CABECALHO_REQUISICAO = (
    "ID_REQUI",
    "DTLAN",
    "DTPAG",
    "TPREQUI",
    "CODCCUSTO",
    "CCUSTO",
    "RECEBE",
    "OBS_CABECALHO",
    "ENTR",
    "RESPONSA",
)


def ler_requisicoes(conteudo: bytes) -> Leitura:
    """Relação de Requisições de saída sem filtro de tipo → `RequisicaoLida`, uma por número.

    Tudo ou nada (contrato `specs/010-conciliacao-scpi/contracts/relatorio-requisicoes.md`):
    qualquer linha ilegível, relatório cortado ou cabeçalho que varia dentro de uma requisição é
    `ErroImportacao`, e nada da leitura é aproveitado."""
    rotulo = "Requisições do SCPI"
    obrigatorias = [
        "REQUI",
        "ID_REQUI",
        "DTLAN",
        "DTPAG",
        "TPREQUI",
        "CODCCUSTO",
        "RECEBE",
        "OBS_CABECALHO",
        "CADPRO",
        "QUAN2",
    ]
    opcionais = ("CCUSTO", "PLACA", "UNID1", "ENTR", "RESPONSA")
    tabela = _tabela(
        conteudo,
        rotulo,
        registros_saidas,
        "GRUPO",
        obrigatorias,
        opcionais=opcionais,
        completos=True,
    )
    if not tabela:
        raise ErroImportacao(f"{rotulo}: o relatório não tem nenhuma requisição; nada foi gravado.")

    grupos: dict[str, list[dict]] = {}
    for posicao, r in enumerate(tabela, start=1):
        try:
            chave(r["REQUI"])
        except ValueError:
            raise ErroImportacao(
                f"{rotulo}: número de requisição inválido na linha {posicao} ('{r['REQUI']}')."
            ) from None
        grupos.setdefault(r["REQUI"], []).append(r)

    requisicoes = []
    for numero_visivel, linhas in grupos.items():
        primeira = linhas[0]
        for coluna in CABECALHO_REQUISICAO:
            if any(linha.get(coluna, "") != primeira.get(coluna, "") for linha in linhas):
                raise ErroImportacao(
                    f"{rotulo}: a requisição {numero_visivel} tem valores diferentes de "
                    f"{coluna} entre as suas linhas."
                )
        try:
            id_requi = int(primeira["ID_REQUI"])
            data = data_br(primeira["DTLAN"])
            data_filtro = data_br(primeira["DTPAG"]) if primeira["DTPAG"] else None
        except ValueError:
            raise ErroImportacao(
                f"{rotulo}: identificador ou data inválidos na requisição {numero_visivel}."
            ) from None
        itens = []
        for linha in linhas:
            try:
                quantidade = _quantidade_que_cabe(decimal_br(linha["QUAN2"]))
            except ValueError:
                raise ErroImportacao(
                    f"{rotulo}: quantidade inválida na requisição {numero_visivel}, "
                    f"{linha['CADPRO']} ('{linha['QUAN2']}')."
                ) from None
            itens.append(ItemLido(linha["CADPRO"], quantidade, linha["UNID1"], linha["PLACA"]))
        ano, numero = chave(numero_visivel)
        requisicoes.append(
            RequisicaoLida(
                requisicao=numero_visivel,
                ano=ano,
                numero=numero,
                id_requi=id_requi,
                data=data,
                data_filtro=data_filtro,
                tipo=primeira["TPREQUI"],
                cod_ccusto=primeira["CODCCUSTO"],
                centro_nome=primeira["CCUSTO"],
                recebedor=primeira["RECEBE"],
                observacoes=primeira["OBS_CABECALHO"],
                responsavel=primeira["RESPONSA"],
                entrada=primeira["ENTR"].upper() == "S",
                itens=tuple(itens),
            )
        )
    return Leitura(requisicoes, [])
