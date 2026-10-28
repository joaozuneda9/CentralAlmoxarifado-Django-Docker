"""Regras de negócio do Central Almoxarifado.

Funções puras, sem ORM. Este módulo e os seus testes são a referência das regras: vieram de
`Regras.gs`/`Util.gs` do Apps Script (os nomes entre crases nas docstrings, como `normU_`, são só
a origem histórica), mas mudam como qualquer regra do sistema, sem compromisso de equivalência.
"""

import math
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

_ACENTOS = re.compile("[̀-ͯ]")
_NAO_ALFANUMERICO = re.compile("[^A-Z0-9]")


def _texto(valor: object) -> str:
    return "" if valor is None else str(valor)


def norm_placa(valor: object) -> str:
    """'CZA-1614' → 'CZA1614' (igual ao `normPlaca_` e ao `norm_placa` do robô)."""
    return _NAO_ALFANUMERICO.sub("", _texto(valor).upper())


def norm_u(valor: object) -> str:
    """Texto comparável: sem acento, em maiúsculas e com espaços colapsados (`normU_`)."""
    sem_acento = _ACENTOS.sub("", unicodedata.normalize("NFKD", _texto(valor)))
    return " ".join(sem_acento.upper().split())


def estoque_inteiro(valor: object) -> int:
    """A parte inteira do saldo, ou 0 se for menor que 1 ou inválido (`estoqueInteiro_`). Só
    preenche `ItemCatalogo.disponivel`, que nenhum formulário lê mais: o limite vem de
    `maximo_pedivel`. Texto aceita vírgula decimal."""
    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
        bruto = str(valor)
    else:
        bruto = _texto(valor).strip().replace(",", ".", 1)
    try:
        numero = Decimal(bruto)
    except InvalidOperation:
        return 0
    if not numero.is_finite() or numero < 1:
        return 0
    return math.floor(numero)


# ---------------------------------------------------------------------------
# Origens, conversões pt-BR e textos
# ---------------------------------------------------------------------------

LIMPEZA = "LIMPEZA"
AB = "AB"
VIATURAS = "VIATURAS"
OFICINA = "OFICINA"
EPIS = "EPIS"
AVULSA = "AVULSA"

# Situações da autorização da Segurança do Trabalho (spec 008), as mesmas gravadas em
# `AutorizacaoPedido.situacao`. O pedido de um formulário que não exige autorização não tem nenhuma.
AUTORIZACAO_AGUARDANDO = "AGUARDANDO"
AUTORIZACAO_AUTORIZADA = "AUTORIZADO"
AUTORIZACAO_RECUSADA = "RECUSADO"

# O centro de custo da oficina mecânica: destino do formulário da oficina (spec 007) e o da
# saída com placa sem centro próprio (`resolver_centro_custo`).
CENTRO_OFICINA = "OFICINA MECÂNICA"

# Acima disto a quantidade é inválida: protege a coluna decimal (12,3) do banco.
QTD_MAXIMA = Decimal("999999")

# [0-9] e não \d: \d aceita dígitos de outros alfabetos ("٣"), que o resto não entende.
_QTD_BR = re.compile(r"^[0-9]+(,[0-9]{1,3})?$")
_INTEIRO = re.compile(r"^[0-9]+$")
_DATA_ISO = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")


def texto(valor: object) -> str:
    """Texto sem espaços nas pontas; None vira "" (`texto_`)."""
    return _texto(valor).strip()


def normalizar_busca(valor: object) -> str:
    """Minúsculas e sem acento, para busca: "protecao" acha "PROTEÇÃO" (`normalizarBusca_`)."""
    return _ACENTOS.sub("", unicodedata.normalize("NFD", _texto(valor))).lower()


def _numero(valor: object) -> bool:
    return isinstance(valor, (int, Decimal)) and not isinstance(valor, bool)


def parse_qtd_br(valor: object) -> Decimal | None:
    """Quantidade pt-BR estrita: "3", "1,5". "1.5" é recusado (o robô leria 15)."""
    if _numero(valor):
        numero = Decimal(valor)
    elif isinstance(valor, str) and _QTD_BR.match(valor.strip()):
        numero = Decimal(valor.strip().replace(",", "."))
    else:
        return None
    if not numero.is_finite() or numero > QTD_MAXIMA:
        return None
    return numero


def parse_inteiro(valor: object) -> int | None:
    """Só inteiro >= 0 escrito com dígitos; "1.5", "1,5", "abc", True viram None."""
    if _numero(valor):
        numero = Decimal(valor)
        if not numero.is_finite() or numero != numero.to_integral_value():
            return None
        inteiro = int(numero)
    elif isinstance(valor, str) and _INTEIRO.match(valor.strip()):
        inteiro = int(valor.strip())
    else:
        return None
    return None if inteiro > QTD_MAXIMA else inteiro


def _decimal_br(numero: object, casas: str) -> str:
    q = Decimal(str(numero)).quantize(Decimal(casas), rounding=ROUND_HALF_UP)
    t = f"{q:f}"
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t.replace(".", ",")


def qtd_br(numero: object) -> str:
    """Número no formato que o robô espera: 1.5 → "1,5" (`qtdBR_`)."""
    return _decimal_br(numero, "0.001")


# ---------------------------------------------------------------------------
# Quantidade por unidade do material (spec 005)
#
# O funcionário que faz o pedido (regra `por_unidade`) pede fração só em material de unidade
# fracionável (a lista mantida no admin); a equipe (atendimento e saída avulsa, regra `livre`)
# aceita fração em qualquer unidade. O estoque exibido, o teto aceito e a mensagem de erro são
# sempre o mesmo número: `maximo_pedivel`.
# ---------------------------------------------------------------------------

REGRA_POR_UNIDADE = "por_unidade"
REGRA_LIVRE = "livre"

CAUSA_ILEGIVEL = "ilegivel"
CAUSA_ZERO = "zero"
CAUSA_FRACAO_EM_CONTAVEL = "fracao_em_contavel"
CAUSA_ACIMA_DO_MAXIMO = "acima_do_maximo"

_TEXTO_QUANTIDADE_FRACIONAVEL = (
    "Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5)."
)
_TEXTO_QUANTIDADE_CONTADA = "Informe um número inteiro maior que zero."


def truncar_qtd(valor: object) -> Decimal:
    """Corta (nunca arredonda) para as 3 casas da quantidade: 2,4996 → 2,499."""
    return Decimal(str(valor)).quantize(Decimal("0.001"), rounding=ROUND_DOWN)


def maximo_pedivel(estoque: object, fracionavel: bool, regra: str) -> Decimal:
    """O mais que se pode pôr no pedido, nunca negativo. Na regra `por_unidade`, o saldo
    truncado a 3 casas para unidade fracionável e a parte inteira para as demais; na `livre`, o
    saldo truncado a 3 casas."""
    saldo = max(truncar_qtd(estoque), Decimal(0))
    if regra != REGRA_POR_UNIDADE or fracionavel:
        return saldo
    return Decimal(math.floor(saldo))


def interpretar_quantidade(texto: object, fracionavel: bool) -> tuple[Decimal | None, str]:
    """A quantidade digitada, ou a causa que a recusa: `(valor, "")` ou `(None, causa)`.

    Formato pt-BR estrito ("1.5" é recusado: o robô leria 15), até 3 casas, de 0,001 a
    `QTD_MAXIMA`. Fração em material de unidade contável é recusada (`fracionavel` falso)."""
    if _numero(texto):
        valor = Decimal(texto)
        if not valor.is_finite() or valor < 0:
            return None, CAUSA_ILEGIVEL
    elif isinstance(texto, str) and _QTD_BR.match(texto.strip()):
        valor = Decimal(texto.strip().replace(",", "."))
    else:
        return None, CAUSA_ILEGIVEL
    if valor > QTD_MAXIMA:
        return None, CAUSA_ACIMA_DO_MAXIMO
    if valor == 0:
        return None, CAUSA_ZERO
    if not fracionavel and valor != valor.to_integral_value():
        return None, CAUSA_FRACAO_EM_CONTAVEL
    return valor, ""


def texto_erro_quantidade(causa: str, *, fracionavel: bool, unidade: str = "") -> str:
    """O texto único de cada causa de erro de quantidade, o mesmo ao adicionar, ao alterar e ao
    enviar (contracts/mensagens.md)."""
    if causa == CAUSA_FRACAO_EM_CONTAVEL:
        com_unidade = f" (unidade: {unidade})" if unidade else ""
        return f"Este material só é pedido em quantidade inteira{com_unidade}."
    if causa == CAUSA_ACIMA_DO_MAXIMO:
        return "A quantidade máxima é 999.999."
    return _TEXTO_QUANTIDADE_FRACIONAVEL if fracionavel else _TEXTO_QUANTIDADE_CONTADA


def texto_acima_do_estoque(maximo: object, unidade: str = "") -> str:
    """O texto único de quantidade acima do estoque. `maximo` é o máximo pedível, o mesmo número
    que a lista mostra como estoque."""
    disponivel = f"{qtd_br(maximo)} {unidade}" if unidade else qtd_br(maximo)
    return f"Quantidade acima do estoque. Estoque disponível: {disponivel}."


def data_valida_iso(valor: object) -> bool:
    """'aaaa-mm-dd' de uma data que existe (`dataValidaISO_`)."""
    m = _DATA_ISO.match(texto(valor))
    if not m:
        return False
    try:
        date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Pedidos dos funcionários
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Erro:
    codigo: str | None
    texto: str
    campo: str | None = None  # campo do formulário ("solicitante", "destino", "obs"), se é dele


@dataclass(frozen=True)
class ItemEnviado:
    codigo: str
    quantidade: object


@dataclass(frozen=True)
class EnvioPedido:
    solicitante: str = ""
    destino: str = ""
    obs: str = ""
    itens: tuple[ItemEnviado, ...] = ()
    # Só no formulário que a pede (`Fluxo.pede_ocorrencia`); nos outros fica "".
    ocorrencia: str = ""


# O número da ocorrência é texto livre e curto (spec 006, FR-002a).
MAX_OCORRENCIA = 20


@dataclass
class Soma:
    soma: dict
    ordem: list[str]
    invalidos: list[ItemEnviado]


@dataclass(frozen=True)
class ItemValido:
    material: Any
    quantidade: Decimal | int


@dataclass
class Validacao:
    erros: list[Erro] = field(default_factory=list)
    validos: list[ItemValido] = field(default_factory=list)
    estoque_atual: dict[str, int | Decimal] = field(default_factory=dict)


def somar_por_codigo(itens: Iterable[ItemEnviado], conv: Callable[[object], Any]) -> Soma:
    """Soma por código, mantendo a ordem de chegada (`somarPorCodigo_`)."""
    s = Soma(soma={}, ordem=[], invalidos=[])
    for item in itens or ():
        codigo = texto(item.codigo)
        q = conv(item.quantidade)
        if q is None or q <= 0:
            s.invalidos.append(item)
            continue
        if codigo not in s.soma:
            s.soma[codigo] = 0
            s.ordem.append(codigo)
        s.soma[codigo] += q
    return s


def opcoes_destino(centros) -> list[str]:
    """O que o formulário oferece como destino: cada centro de custo (uma vez, mesmo com
    várias placas) e, para cada placa cadastrada, "centro — placa". O centro cujas linhas são
    todas `so_com_placa` (as viaturas do formulário da oficina) só sai como "centro — placa"."""
    centros = list(centros or ())
    descricoes = dict.fromkeys(c.descricao for c in centros if not c.so_com_placa)
    com_placa = dict.fromkeys(f"{c.descricao} — {c.placa}" for c in centros if c.placa)
    return [*descricoes, *com_placa]


def resolver_destino(digitado: object, centros) -> str:
    """O destino como está no cadastro, para o que foi digitado: o centro de custo, "centro —
    placa" ou só a placa (com ou sem hífen). "" se não houver tal centro de custo."""
    t = texto(digitado)
    if not t:
        return ""
    opcoes = opcoes_destino(centros)
    if t in opcoes:
        return t
    alvo = norm_u(t)
    for opcao in opcoes:
        if norm_u(opcao) == alvo:
            return opcao
    placa = norm_placa(t)
    for c in centros or ():
        if placa and norm_placa(c.placa) == placa:
            return f"{c.descricao} — {c.placa}"
    return ""


def _erro_destino(envio: EnvioPedido, centros) -> str:
    """O erro do destino do pedido, ou "". Tem de ser o texto do cadastro (`resolver_destino`):
    quem chama o serviço com outra grafia recebe o erro, e a tela já manda o texto certo."""
    destino = texto(envio.destino)
    if not destino:
        return "Escolha o destino na lista."
    if resolver_destino(destino, centros) != destino:
        return f'Destino "{destino}" não está na lista de centros de custo.'
    return ""


def _por_codigo(catalogo) -> dict:
    return {m.codigo: m for m in catalogo or ()}


def _sem_codigo(codigo: str) -> str:
    return codigo or "(sem código)"


def aceita_fracao(regra: str, material) -> bool:
    """Se a quantidade deste material pode ter fração numa regra de quantidade. A `livre` (a
    equipe) aceita em qualquer unidade; na `por_unidade`, quem pede segue a unidade do material.
    Material fora do catálogo (`None`) não decide nada aqui, o envio o recusa: vale a leitura com
    fração. O carrinho e a validação do envio usam esta mesma conta."""
    return regra == REGRA_LIVRE or material is None or material.fracionavel


def validar_pedido(
    envio: EnvioPedido, catalogo, centros, regra_quantidade: str = REGRA_POR_UNIDADE
) -> Validacao:
    """Validação do envio dos formulários públicos de limpeza e AB (`validarPedidoLimpeza_` e
    `validarPedidoAB_`, hoje uma só, spec 005). A quantidade e o teto vêm da unidade do material
    (`interpretar_quantidade` e `maximo_pedivel`), pela `regra_quantidade` do `Fluxo` (a mesma que
    o carrinho usa), e os textos são os mesmos do carrinho. Dos itens só lê código e quantidade:
    nome, unidade e categoria vêm do catálogo do servidor."""
    v = Validacao()

    def campo(t, nome=None):
        v.erros.append(Erro(None, t, nome))

    if not texto(envio.solicitante):
        campo("Informe o nome completo.", "solicitante")
    if erro := _erro_destino(envio, centros):
        campo(erro, "destino")
    if len(texto(envio.ocorrencia)) > MAX_OCORRENCIA:
        campo(f"Nº da ocorrência: no máximo {MAX_OCORRENCIA} caracteres.", "ocorrencia")
    if not envio.itens:
        campo("Adicione ao menos um material ao pedido.")

    por_codigo = _por_codigo(catalogo)
    sem_catalogo: set[str] = set()

    def fora_do_catalogo(codigo):
        if codigo not in sem_catalogo:
            sem_catalogo.add(codigo)
            v.erros.append(
                Erro(codigo, f"O material {_sem_codigo(codigo)} não está mais no catálogo.")
            )
            v.estoque_atual[codigo] = 0

    def maximo_do(m):
        if m.duplicado:
            return Decimal(0)
        return maximo_pedivel(m.estoque, m.fracionavel, regra_quantidade)

    soma: dict[str, Decimal] = {}  # na ordem de chegada
    for item in envio.itens or ():
        codigo = texto(item.codigo)
        m = por_codigo.get(codigo)
        fracionavel = aceita_fracao(regra_quantidade, m)
        q, causa = interpretar_quantidade(item.quantidade, fracionavel)
        if causa and m is None:
            fora_do_catalogo(codigo)
        elif causa:
            v.erros.append(
                Erro(
                    codigo,
                    f"{m.nome} ({codigo}): "
                    + texto_erro_quantidade(causa, fracionavel=fracionavel, unidade=m.unidade),
                )
            )
            v.estoque_atual[codigo] = maximo_do(m)
        else:
            soma[codigo] = soma.get(codigo, Decimal(0)) + q

    for codigo, total in soma.items():
        m = por_codigo.get(codigo)
        if m is None:
            fora_do_catalogo(codigo)
        elif m.duplicado:
            v.erros.append(
                Erro(
                    codigo,
                    f"O material {codigo} está com cadastro duplicado. Avise o almoxarifado.",
                )
            )
            v.estoque_atual[codigo] = 0
        elif (maximo := maximo_do(m)) <= 0:
            v.erros.append(Erro(codigo, f"{m.nome} ({codigo}): Sem estoque."))
            v.estoque_atual[codigo] = 0
        elif total > maximo:
            v.erros.append(
                Erro(codigo, f"{m.nome} ({codigo}): {texto_acima_do_estoque(maximo, m.unidade)}")
            )
            v.estoque_atual[codigo] = maximo
        else:
            v.validos.append(ItemValido(m, total))
    return v


# ---------------------------------------------------------------------------
# Saídas (atendimento de pedido e saída avulsa)
# ---------------------------------------------------------------------------

# Status de cada linha de saída (contrato com o robô do SCPI).
PENDENTE = "PENDENTE"
EM_LANCAMENTO = "EM_LANCAMENTO"
LANCADA = "LANCADA"
ERRO = "ERRO"
VERIFICAR = "VERIFICAR"
NAO_LANCAR = "NAO_LANCAR"

_REQUISICAO = re.compile(r"^[0-9]{6}/[0-9]{2}$")


def requisicao_valida(valor: object) -> bool:
    """Número de requisição do SCPI no formato 000000/00."""
    return _REQUISICAO.match(texto(valor)) is not None


# Usados se a lista de tipos de saída estiver vazia.
TIPOS_SAIDA_PADRAO = (
    "BALCÃO",
    "ENTREGA",
    "OUTRA",
    "DOAÇÃO",
    "DEVOLUÇÃO",
    "PERMUTA",
    "PERDA",
    "ORDEM DE SERVIÇO",
    "REMESSA",
)

_CODIGO = re.compile(r"^[0-9]{3}\.[0-9]{3}\.[0-9]{3}$")


@dataclass(frozen=True)
class Centro:
    descricao: str
    codigo: str
    placa: str = ""
    # Destino só como "centro — placa", nunca a descrição sozinha (`opcoes_destino`).
    so_com_placa: bool = False


@dataclass(frozen=True)
class CentroResolvido:
    codigo: str = ""
    descricao: str = ""
    via_placa: bool = False
    erro: str = ""


@dataclass(frozen=True)
class DadosSaida:
    data: str  # aaaa-mm-dd
    recebedor: str
    centro_custo: str
    tipo: str
    placa: str
    obs: str = ""


@dataclass(frozen=True)
class ItemSaida:
    codigo: str
    quantidade: Decimal | int | None  # None = inválida
    maximo: Decimal | int | None = None
    estoque: Decimal | None = None  # saldo que limita a saída (None = sem limite)


@dataclass(frozen=True)
class Adicionado:
    """Material acrescentado pelo almoxarifado no atendimento: código e o item pedido que ele
    substitui (vazio quando é um acréscimo sem troca)."""

    codigo: str
    no_lugar_de: str = ""


@dataclass(frozen=True)
class EnvioSaida:
    dados: DadosSaida
    itens: tuple[ItemEnviado, ...] = ()
    nao_lancar: bool = False


@dataclass
class ValidacaoSaida:
    erros: list[Erro]
    centro: CentroResolvido


def resolver_centro_custo(cc_nome: object, placa: object, centros) -> CentroResolvido:
    """Mesma regra do robô (`resolverCentroCusto_`): placa com centro de custo próprio tem
    prioridade; placa em mais de um centro é erro; sem centro e com placa → OFICINA MECÂNICA."""
    p = norm_placa(placa)
    if p:
        da_placa = [c for c in centros if norm_placa(c.placa) == p]
        codigos = list(dict.fromkeys(c.codigo for c in da_placa))
        if len(codigos) > 1:
            return CentroResolvido(erro=f"placa '{p}' cadastrada em mais de um centro de custo")
        if len(codigos) == 1:
            return CentroResolvido(codigos[0], da_placa[0].descricao, via_placa=True)
    nome = texto(cc_nome) or (CENTRO_OFICINA if p else "")
    if not nome:
        return CentroResolvido(erro="'Centro de Custo' vazio")
    c = next((x for x in centros if norm_u(x.descricao) == norm_u(nome)), None)
    if c is None:
        return CentroResolvido(
            erro=f"centro de custo '{nome}' não existe no cadastro de centros de custo"
        )
    return CentroResolvido(c.codigo, c.descricao)


def validar_saida(
    d: DadosSaida,
    itens: Iterable[ItemSaida],
    *,
    centros,
    hoje: date,
    tipos=None,
    catalogo: dict | None = None,
) -> ValidacaoSaida:
    """Valida os dados de uma saída (`validarSaida_`). Centro de custo e placa só valem se
    estiverem no cadastro de centros de custo."""
    erros: list[Erro] = []

    def campo(t):
        erros.append(Erro(None, t))

    if not data_valida_iso(d.data):
        campo("Informe a data efetiva da saída.")
    elif date.fromisoformat(texto(d.data)) > hoje:
        campo("A data da saída não pode ser futura.")
    if not texto(d.recebedor):
        campo("Informe quem recebeu o material.")
    if texto(d.tipo) not in (TIPOS_SAIDA_PADRAO if tipos is None else tipos):
        campo("Selecione o Tipo Saída do SCPI.")

    centros = list(centros or ())
    placa = norm_placa(d.placa)
    if placa and not any(norm_placa(c.placa) == placa for c in centros):
        campo(f"A placa {placa} não está na lista de centros de custo.")
    if not texto(d.centro_custo):
        campo("Escolha o centro de custo na lista.")
    elif not any(norm_u(c.descricao) == norm_u(d.centro_custo) for c in centros):
        campo(f'O centro de custo "{texto(d.centro_custo)}" não está na lista.')
    cc = resolver_centro_custo(d.centro_custo, d.placa, centros)
    if cc.erro and not erros:
        campo(f"Centro de custo: {cc.erro}.")

    algum = False
    for i in itens or ():
        q = i.quantidade
        m = catalogo.get(i.codigo) if catalogo is not None else None
        if not _CODIGO.match(texto(i.codigo)):
            erros.append(Erro(i.codigo, f"Código '{i.codigo}' fora do padrão 000.000.000."))
        elif catalogo is not None and m is None:
            erros.append(Erro(i.codigo, f"Material {i.codigo} não encontrado no cadastro."))
        elif m is not None and m.duplicado:
            erros.append(Erro(i.codigo, f"Material {i.codigo} está com cadastro duplicado."))
        elif q is None or q < 0:
            erros.append(Erro(i.codigo, f"Quantidade inválida para {i.codigo}."))
        elif i.maximo is not None and q > i.maximo:
            erros.append(Erro(i.codigo, f"Entrega de {i.codigo} maior que a quantidade pedida."))
        elif i.estoque is not None and q > i.estoque:
            erros.append(
                Erro(i.codigo, f"Saída de {i.codigo} maior que o estoque ({qtd_br(i.estoque)}).")
            )
        if q is not None and q > 0:
            algum = True
    if not algum:
        campo("Informe ao menos um material com quantidade maior que zero.")
    return ValidacaoSaida(erros, cc)


def marcado_nao_lancar(obs: object) -> bool:
    """Observação que pede para não lançar no SCPI (`marcadoNaoLancar_`). Quem decide é a opção
    "Não lançar no SCPI"; a saída com esse texto e sem a opção é recusada, para a observação não
    ser tomada como ordem e a saída ir para o SCPI por engano."""
    o = norm_u(obs)
    return "FORA DE ESTOQUE" in o or "NAO LANCAR" in o


# ---------------------------------------------------------------------------
# Situação do pedido e no SCPI
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Situacao:
    chave: str
    rotulo: str
    desc: str
    numeros: tuple[str, ...] = ()


def situacao_scpi(linhas) -> Situacao:
    """Situação no SCPI a partir das linhas de saída (`situacaoScpi_`): só é "Lançado" quando
    todas as linhas foram lançadas."""
    linhas = list(linhas)
    if not linhas:
        return Situacao(
            "sem",
            "Aguarda o atendimento",
            "O lançamento no SCPI só começa depois que o atendimento é confirmado.",
        )
    ativas = [r for r in linhas if r.status != NAO_LANCAR]
    if not ativas:
        return Situacao(
            "sem", "Não será lançado", "Todas as linhas estão marcadas para não lançar no SCPI."
        )

    def estado(r):
        if texto(r.requisicao_scpi) or r.status == LANCADA:
            return "L"
        if r.status in (VERIFICAR, EM_LANCAMENTO):
            return "V"
        if r.status == ERRO:
            return "X"
        return "P"

    estados = [estado(r) for r in ativas]
    numeros = tuple(
        dict.fromkeys(texto(r.requisicao_scpi) for r in ativas if texto(r.requisicao_scpi))
    )
    if "V" in estados:
        return Situacao(
            "atencao",
            "Verificar no SCPI",
            "O robô não confirmou o resultado; as linhas ficam travadas até alguém conferir "
            "no SCPI.",
            numeros,
        )
    if "X" in estados:
        return Situacao(
            "atencao",
            "Erro no lançamento",
            "O robô recusou ou falhou antes de salvar. A linha precisa ser corrigida e liberada.",
            numeros,
        )
    if all(e == "L" for e in estados):
        desc = (
            "Itens lançados em requisições diferentes do SCPI."
            if len(numeros) > 1
            else "Todos os itens confirmados pelo robô."
        )
        return Situacao("lancado", "Lançado " + ", ".join(numeros), desc, numeros)
    if "L" in estados:
        return Situacao(
            "parcial",
            "Parcial " + ", ".join(numeros),
            "Parte dos itens lançada; o restante aguarda o robô.",
            numeros,
        )
    return Situacao(
        "aguardando", "Aguardando o robô", "Saídas registradas, ainda sem número oficial do SCPI."
    )


def situacao_pedido(origem: str, atendido: bool, itens, autorizacao: str | None = None) -> Situacao:
    """Situação do pedido (`situacaoPedido_`, sem o estado "conferir", que existia por causa
    de gravação parcial na planilha).

    `autorizacao` é a situação da autorização da Segurança do Trabalho (spec 008), ou None para o
    pedido de um formulário que não exige: aguardando ou recusada vale por cima de tudo (o pedido
    ainda não pode ser atendido, ou nunca mais), e autorizada segue a regra do atendimento."""
    if autorizacao == AUTORIZACAO_AGUARDANDO:
        return Situacao(
            "aguardando_autorizacao",
            "Aguardando autorização",
            "A Segurança do Trabalho ainda não autorizou; o pedido não pode ser atendido.",
        )
    if autorizacao == AUTORIZACAO_RECUSADA:
        return Situacao(
            "recusado", "Recusado", "A Segurança do Trabalho recusou o pedido; ele está encerrado."
        )
    if origem == AVULSA:
        # Já nasce atendida: a saída é registrada direto pelo almoxarifado.
        return Situacao("atendido", "Atendido", "Atendimento confirmado e saída registrada.")
    if atendido:
        itens = list(itens)
        # Item pedido que o almoxarifado trocou por outro entregue não conta como faltante;
        # o material acrescentado nunca faz o pedido parcial.
        trocados = {
            i.no_lugar_de_id
            for i in itens
            if i.origem == "ALMOXARIFADO" and (i.qtd_entregue or 0) > 0 and i.no_lugar_de_id
        }
        parcial = any(
            i.origem == "PEDIDO" and i.id not in trocados and (i.qtd_entregue or 0) < i.qtd_pedida
            for i in itens
        )
        if parcial:
            return Situacao(
                "parcial",
                "Atendido parcialmente",
                "Algum material foi entregue em quantidade menor que a pedida.",
            )
        return Situacao("atendido", "Atendido", "Atendimento confirmado e saída registrada.")
    return Situacao(
        "aguardando",
        "Aguardando atendimento",
        "Pedido enviado; o almoxarifado ainda não confirmou.",
    )


_NUMERO_DE_PEDIDO = re.compile(r"^P-?(\d{1,9})$")


def normalizar_numero_pedido(digitado: str) -> str:
    """O número de pedido como a numeração o grava ("P-000123"), a partir do que o servidor
    digita ("p-123", " P123 "). O que não parece um número de pedido volta só limpo e em
    maiúsculas (a consulta não o acha)."""
    limpo = "".join(str(digitado or "").split()).upper()
    casou = _NUMERO_DE_PEDIDO.match(limpo)
    return f"P-{int(casou.group(1)):06d}" if casou else limpo


def texto_situacao_consulta(numero: str, autorizacao: str, motivo: str) -> tuple[str, str]:
    """O que a consulta pública do pedido de EPI diz ao servidor (spec 008, FR-031): a situação
    e, na recusa, o motivo. Nada além disso: nem nome, nem destino, nem materiais."""
    if autorizacao == AUTORIZACAO_RECUSADA:
        return f"Pedido {numero}: recusado pela Segurança do Trabalho.", motivo
    if autorizacao == AUTORIZACAO_AUTORIZADA:
        return (
            f"Pedido {numero}: autorizado. O almoxarifado vai atendê-lo; procure o almoxarifado "
            "para retirar.",
            "",
        )
    return f"Pedido {numero}: aguardando autorização da Segurança do Trabalho.", ""


# ---------------------------------------------------------------------------
# Edição do atendimento: até quando se edita e o que mudou
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Edicao:
    """Se o atendimento ainda pode ser editado, pelas linhas de saída do lote."""

    chave: str  # "antes_do_atendimento" | "editavel" | "suspensa" | "bloqueada"
    motivo: str  # texto da tela; vazio quando se pode editar
    numeros: tuple[str, ...] = ()
    lancado_em: datetime | None = None

    @property
    def permitida(self) -> bool:
        return self.chave == "editavel"


def _data_hora(momento: datetime) -> str:
    if timezone.is_aware(momento):
        momento = timezone.localtime(momento)
    return momento.strftime("%d/%m/%Y %H:%M")


def edicao_permitida(atendido: bool, linhas) -> Edicao:
    """Editável enquanto nenhuma linha foi lançada nem está em lançamento: `PENDENTE`,
    `NAO_LANCAR` e `ERRO` sem número de requisição. `EM_LANCAMENTO` e `VERIFICAR` suspendem
    (ainda não se sabe se entrou no SCPI); lançada ou com número bloqueia de vez."""
    if not atendido:
        return Edicao("antes_do_atendimento", "")
    linhas = list(linhas)
    lancadas = [r for r in linhas if r.status == LANCADA or texto(r.requisicao_scpi)]
    if lancadas:
        numeros = tuple(
            dict.fromkeys(texto(r.requisicao_scpi) for r in lancadas if texto(r.requisicao_scpi))
        )
        datas = [r.lancado_em for r in lancadas if r.lancado_em]
        quando = max(datas) if datas else None
        onde = f"na requisição {', '.join(numeros)}" if numeros else "no SCPI"
        em = f" em {_data_hora(quando)}" if quando else ""
        return Edicao(
            "bloqueada",
            f"Lançado {onde}{em}; correções são feitas no SCPI.",
            numeros,
            quando,
        )
    if any(r.status in (EM_LANCAMENTO, VERIFICAR) for r in linhas):
        return Edicao(
            "suspensa",
            "Edição suspensa: o robô não confirmou se a requisição foi gravada no SCPI. "
            "Resolva em Automações.",
        )
    return Edicao("editavel", "")


ROTULOS_CABECALHO = (
    "Data efetiva",
    "Recebedor",
    "Centro de custo",
    "Tipo de saída",
    "Placa",
    "Observações",
    "Não lançar no SCPI",
)


@dataclass(frozen=True)
class EstadoAtendimento:
    """O que a edição pode mudar, gravado ou enviado, para comparar."""

    cabecalho: tuple[str, ...]  # na ordem de `cabecalho_saida`
    entregues: dict  # código -> quantidade (itens pedidos; na avulsa, todos)
    adicionados: dict  # código -> (no_lugar_de, quantidade)
    nomes: dict  # código -> material, para as frases


def _valor_cabecalho(i: int, valor: str) -> str:
    if i == 0 and valor:
        try:
            return date.fromisoformat(valor).strftime("%d/%m/%Y")
        except ValueError:
            return valor
    if i == 6:
        return "Sim" if valor else "Não"
    return valor


def _qtd_texto(q) -> str:
    return "" if q is None else qtd_br(q)


def diferencas_atendimento(gravado: EstadoAtendimento, enviado: EstadoAtendimento) -> list[dict]:
    """O que muda do gravado para o enviado, em textos (vai para o histórico, em JSON):
    cabeçalho da saída, quantidades entregues e materiais acrescentados pelo almoxarifado."""
    nomes = {**gravado.nomes, **enviado.nomes}
    difs: list[dict] = []
    for i, (antes, depois) in enumerate(zip(gravado.cabecalho, enviado.cabecalho, strict=True)):
        if texto(antes) != texto(depois):
            difs.append(
                {
                    "campo": ROTULOS_CABECALHO[i],
                    "antes": _valor_cabecalho(i, texto(antes)),
                    "depois": _valor_cabecalho(i, texto(depois)),
                }
            )

    def material(codigo, mudanca, antes, depois):
        return {
            "codigo": codigo,
            "material": nomes.get(codigo, codigo),
            "mudanca": mudanca,
            "antes": antes,
            "depois": depois,
        }

    codigos = list(dict.fromkeys([*gravado.entregues, *enviado.entregues]))
    for codigo in codigos:
        if codigo not in enviado.entregues:
            difs.append(material(codigo, "removido", _qtd_texto(gravado.entregues[codigo]), ""))
        elif codigo not in gravado.entregues:
            difs.append(material(codigo, "incluido", "", _qtd_texto(enviado.entregues[codigo])))
        elif gravado.entregues[codigo] != enviado.entregues[codigo]:
            difs.append(
                material(
                    codigo,
                    "entregue",
                    _qtd_texto(gravado.entregues[codigo]),
                    _qtd_texto(enviado.entregues[codigo]),
                )
            )

    for codigo, (lugar, qtd) in enviado.adicionados.items():
        if codigo not in gravado.adicionados:
            difs.append(material(codigo, "incluido", "", _qtd_texto(qtd)))
            continue
        lugar_antes, qtd_antes = gravado.adicionados[codigo]
        if texto(lugar_antes) != texto(lugar):
            difs.append(
                material(
                    codigo,
                    "troca",
                    nomes.get(lugar_antes, lugar_antes) if lugar_antes else "",
                    nomes.get(lugar, lugar) if lugar else "",
                )
            )
        if qtd_antes != qtd:
            difs.append(material(codigo, "entregue", _qtd_texto(qtd_antes), _qtd_texto(qtd)))
    for codigo, (_, qtd) in gravado.adicionados.items():
        if codigo not in enviado.adicionados:
            difs.append(material(codigo, "removido", _qtd_texto(qtd), ""))
    return difs


def frase_diferenca(d: dict) -> str:
    """Uma diferença de `diferencas_atendimento` em frase, para a tela."""
    if "campo" in d:
        return f"{d['campo']}: {d['antes'] or '—'} → {d['depois'] or '—'}"
    nome = f"{d['material']} ({d['codigo']})"
    mudanca = d["mudanca"]
    if mudanca == "entregue":
        return f"{nome}: entregue {d['antes'] or '—'} → {d['depois'] or '—'}"
    if mudanca == "incluido":
        return f"{nome}: incluído, {d['depois']}"
    if mudanca == "removido":
        return f"{nome}: removido (era {d['antes']})"
    if d["depois"]:
        return f"{nome}: agora no lugar de {d['depois']}"
    return f"{nome}: deixou de ser troca"


# ---------------------------------------------------------------------------
# Reenvio: o que está gravado é exatamente o que chegou de novo?
# ---------------------------------------------------------------------------


def cabecalho_saida(dados: DadosSaida, nao_lancar: bool) -> tuple[str, ...]:
    return (
        texto(dados.data),
        texto(dados.recebedor),
        texto(dados.centro_custo),
        texto(dados.tipo),
        norm_placa(dados.placa),
        texto(dados.obs),
        "1" if nao_lancar else "",
    )


def origem_publica(origem: str) -> bool:
    """Toda origem que não é a saída avulsa vem de um formulário público (cabeçalho: solicitante,
    destino e observação; sujeita ao limite por nome e à conferência de reenvio)."""
    return origem != AVULSA


def cabecalho_enviado(origem: str, envio) -> tuple[str, ...]:
    if origem_publica(origem):
        return (
            texto(envio.solicitante),
            texto(envio.destino),
            texto(envio.obs),
            texto(envio.ocorrencia),
        )
    return cabecalho_saida(envio.dados, envio.nao_lancar)


def itens_conferem(origem: str, itens_gravados, envio) -> bool:
    """Só o conjunto código → quantidade, somando repetições como a gravação faz."""
    gravados: dict[str, Decimal] = {}
    for codigo, qtd in itens_gravados:
        gravados[codigo] = gravados.get(codigo, Decimal(0)) + Decimal(qtd)
    if not gravados:
        return False
    enviados = somar_por_codigo(envio.itens, parse_qtd_br)
    if enviados.invalidos:
        return False
    return set(enviados.soma) == set(gravados) and all(
        Decimal(enviados.soma[c]) == gravados[c] for c in gravados
    )


def registro_confere(origem: str, cabecalho_gravado, itens_gravados, envio) -> bool:
    """Compara identificação, destino/observação (ou dados da saída) e os itens
    (`registroConfere_`)."""
    if tuple(texto(v) for v in cabecalho_gravado) != cabecalho_enviado(origem, envio):
        return False
    return itens_conferem(origem, itens_gravados, envio)


def atendimento_confere(
    cabecalho_gravado,
    entregues: dict,
    dados: DadosSaida,
    nao_lancar: bool,
    qtds: dict,
    adicionados_gravados: frozenset = frozenset(),
    adicionados_enviados: frozenset = frozenset(),
) -> bool:
    """Reenvio de um atendimento: mesmos dados da saída, mesmas quantidades entregues e o mesmo
    conjunto de acrescentados `(codigo, no_lugar_de, quantidade)`, em qualquer ordem."""
    if tuple(texto(v) for v in cabecalho_gravado) != cabecalho_saida(dados, nao_lancar):
        return False
    if set(adicionados_gravados) != set(adicionados_enviados):
        return False
    return all(
        Decimal(entregue or 0) == Decimal(qtds.get(codigo) or 0)
        for codigo, entregue in entregues.items()
    )
