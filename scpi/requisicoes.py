"""Requisições a lançar no SCPI: seleção e validação sobre as `LinhaSaida`, sem ORM.

Vem de `selecionar_pendentes`, `validar`, `chave_grupo` e das exceções do `lancar_saidas.py`
do extrair-relatorio, agora sobre o banco e agrupadas por lote (um lote = uma requisição).
Quem chama carrega as linhas e os centros de custo; aqui só se decide o que lançar.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from pedidos.regras import (
    EM_LANCAMENTO,
    ERRO,
    PENDENTE,
    TIPOS_SAIDA_PADRAO,
    VERIFICAR,
    Centro,
    norm_placa,
    norm_u,
    resolver_centro_custo,
    texto,
)

RE_CADPRO = re.compile(r"^\d{3}\.\d{3}\.\d{3}$")
RE_REQUI = re.compile(r"\b(\d{6}/\d{2})\b")  # formato REQUI do SCPI: 003354/26

# Lote com linha em qualquer um destes estados espera conferência: não é lançado de novo.
ESTADOS_TRAVA = (EM_LANCAMENTO, VERIFICAR, ERRO)


class ErroValidacao(Exception):
    """Dados das linhas inválidos — nada foi feito no SCPI."""


class ErroSCPI(Exception):
    """Falha ANTES do clique final — nada foi lançado, seguro tentar de novo."""


class ResultadoIncerto(Exception):
    """Falha DEPOIS do clique final — a requisição pode ou não existir no SCPI."""


class FalhaCritica(Exception):
    """Não foi possível registrar um resultado no banco — interrompe a execução."""


@dataclass
class Item:
    cadpro: str
    qtd: str  # no formato do SCPI: vírgula decimal, sem zeros à direita
    placa: str


@dataclass
class Requisicao:
    lote: str
    linhas: list
    data: str = ""  # dd/mm/aaaa
    tipo_saida: str = ""
    cod_ccusto: str = ""
    recebedor: str = ""
    obs: str = ""  # a observação da saída no Central; vai às Observações do SCPI
    # A placa que o SCPI preenche sozinho a partir do centro de custo de uma viatura, pelo
    # cadastro usado na seleção: a foto da tentativa a guarda (spec 010, R10 e R11).
    placa_centro: str = ""
    itens: list[Item] = field(default_factory=list)
    erro: str = ""

    @property
    def ids(self) -> list[int]:
        return [linha.id for linha in self.linhas]

    def __str__(self) -> str:
        return (
            f"{self.lote} | {self.data} | {self.recebedor} | c.custo {self.cod_ccusto}"
            f" | {len(self.itens)} item(ns)"
        )


@dataclass
class Selecao:
    requisicoes: list[Requisicao]
    travados: list[str]


def qtd_scpi(qtd: Decimal) -> str:
    """10.000 → '10'; 0.330 → '0,33' (o formato que o campo do SCPI aceita)."""
    return format(qtd.normalize(), "f").replace(".", ",")


def _cabecalho(linha) -> tuple:
    return (
        linha.data,
        norm_u(linha.recebedor),
        norm_u(linha.centro_custo),
        norm_u(linha.tipo_saida),
        norm_placa(linha.placa),
    )


def placa_do_centro(codigo: str, centros: list[Centro]) -> str:
    """A placa do centro de custo `codigo` no cadastro, normalizada. Vazia quando o centro não
    tem placa ou quando as linhas dele no cadastro têm placas diferentes (o SCPI não teria uma
    só para preencher)."""
    placas = {norm_placa(c.placa) for c in centros if c.codigo == codigo and norm_placa(c.placa)}
    return placas.pop() if len(placas) == 1 else ""


def validar(req: Requisicao, centros: list[Centro]) -> None:
    """Preenche o cabeçalho e os itens da requisição, ou levanta `ErroValidacao` com todos os
    problemas juntos. O centro de custo e o tipo saem da primeira linha do lote."""
    erros = []
    req.itens = []
    l0 = req.linhas[0]
    if any(_cabecalho(linha) != _cabecalho(l0) for linha in req.linhas[1:]):
        erros.append(
            "linhas do lote com data, recebedor, centro de custo, tipo ou placa diferentes"
        )
    req.data = l0.data.strftime("%d/%m/%Y")
    req.recebedor = texto(l0.recebedor)
    req.obs = texto(l0.obs)
    if not req.recebedor:
        erros.append("recebedor vazio")
    centro = resolver_centro_custo(l0.centro_custo, l0.placa, centros)
    if centro.erro:
        erros.append(centro.erro)
    else:
        req.cod_ccusto = centro.codigo
        req.placa_centro = placa_do_centro(centro.codigo, centros)
    tipos = {norm_u(t): t for t in TIPOS_SAIDA_PADRAO}
    if norm_u(l0.tipo_saida) not in tipos:
        erros.append(
            f"'Tipo Saída' inválido '{l0.tipo_saida}' (aceitos: {', '.join(TIPOS_SAIDA_PADRAO)})"
        )
    else:
        req.tipo_saida = tipos[norm_u(l0.tipo_saida)]

    vistos: set[str] = set()
    for linha in req.linhas:
        if not RE_CADPRO.match(linha.codigo):
            erros.append(f"código '{linha.codigo}' fora do padrão 000.000.000")
            continue
        if linha.codigo in vistos:
            erros.append(f"código {linha.codigo} repetido na mesma requisição")
            continue
        vistos.add(linha.codigo)
        if linha.qtd <= 0:
            erros.append(f"quantidade de {linha.codigo} deve ser > 0")
            continue
        req.itens.append(
            Item(cadpro=linha.codigo, qtd=qtd_scpi(linha.qtd), placa=norm_placa(linha.placa))
        )

    if erros:
        raise ErroValidacao("; ".join(erros))


def agrupar(linhas) -> tuple[dict[str, Requisicao], list[str]]:
    """A regra única de "o que está na fila do robô": agrupa as linhas `PENDENTE` por lote (na
    ordem da primeira linha) e separa os lotes com alguma linha em `ESTADOS_TRAVA` ou `PENDENTE`
    com número de requisição, que ficam de fora inteiros. Linhas lançadas ou marcadas para não
    lançar são ignoradas. Um lote nunca sai dividido: se parte dele espera conferência, ele
    inteiro fica para trás (pode já ter sido lançado no SCPI). `consultas.fila_do_robo` repete
    esta regra em SQL."""
    travados: list[str] = []
    grupos: dict[str, Requisicao] = {}
    for linha in linhas:
        # Linha com número de requisição já foi lançada (é o que a situação do pedido mostra),
        # qualquer que seja o status: relançar duplicaria a requisição no SCPI.
        if linha.status in ESTADOS_TRAVA or (
            linha.status == PENDENTE and texto(linha.requisicao_scpi)
        ):
            if linha.lote not in travados:
                travados.append(linha.lote)
        elif linha.status == PENDENTE:
            grupos.setdefault(linha.lote, Requisicao(lote=linha.lote, linhas=[])).linhas.append(
                linha
            )
    return {lote: req for lote, req in grupos.items() if lote not in travados}, travados


def selecionar(linhas, centros: list[Centro]) -> Selecao:
    """Separa as requisições a lançar dos lotes travados (`agrupar`) e valida as requisições."""
    grupos, travados = agrupar(linhas)
    requisicoes = list(grupos.values())
    for req in requisicoes:
        try:
            validar(req, centros)
        except ErroValidacao as e:
            req.erro = str(e)
    return Selecao(requisicoes=requisicoes, travados=travados)
