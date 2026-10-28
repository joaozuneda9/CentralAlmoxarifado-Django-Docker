"""A linha do lançamento no SCPI na visão geral, ao lado das fontes do catálogo (`saude.Fonte`).

Função pura: recebe os números e a última execução já consultados, sem tocar no banco.
"""

from dataclasses import dataclass
from datetime import datetime

from django.urls import reverse

from catalogo.saude import ha_quanto
from pedidos import andamento


@dataclass(frozen=True)
class LinhaAutomacao:
    """Uma automação na visão geral. `nivel` vai no selo: "ok", "neutro", "aviso", "erro" ou
    "andamento"; o estado é sempre dito em texto (`selo`)."""

    rotulo: str
    nivel: str
    selo: str
    resumo: str
    complemento: str = ""
    quando: datetime | None = None
    ha_quanto: str = ""
    erro: str = ""
    acao_rotulo: str = ""
    acao_url: str = ""
    acao_discreta: bool = False


def _aguardando(n: int) -> str:
    if not n:
        return "Nada aguardando o robô"
    return f"{n} {'requisição aguardando' if n == 1 else 'requisições aguardando'} o robô"


def _estado(ultima, travados: int, em_andamento: bool, interrompida: bool) -> tuple[str, str]:
    if em_andamento:
        return "andamento", "Em andamento"
    if travados:
        return "aviso", f"{travados} para conferir"
    if ultima is None:
        return "neutro", "Sem execuções"
    if ultima.situacao == ultima.Situacao.FALHA:
        return "erro", "Falhou"
    if interrompida:
        return "aviso", "Interrompida"
    if ultima.situacao == ultima.Situacao.ATENCAO:
        return "aviso", "Com pendências"
    return "ok", "Em dia"


def linha_lancamento(
    *,
    pendentes: int,
    travados: int,
    ultima,
    em_andamento: bool,
    interrompida: bool,
    agora: datetime,
) -> LinhaAutomacao:
    """O lançamento no SCPI: quantas requisições aguardam, quantas travas há e como foi a última
    execução (`ultima` é uma `ExecucaoRobo` ou None)."""
    nivel, selo = _estado(ultima, travados, em_andamento, interrompida)
    pagina = reverse("automacoes:pagina")
    if travados:
        acao_rotulo, acao_url, acao_discreta = (
            "Conferir travas",
            f"{pagina}?aba=lancamento#travas",
            False,
        )
    else:
        acao_rotulo, acao_url, acao_discreta = "Abrir", f"{pagina}?aba=lancamento", True
    quando, complemento, erro = None, "", ""
    if ultima is not None:
        quando = ultima.fim or ultima.inicio
        complemento = "última: simulação" if ultima.simulacao else "último: lançamento real"
        falha = andamento.explicar_falha(ultima)
        erro = falha.frase if falha else ""
    return LinhaAutomacao(
        rotulo="Lançamento no SCPI",
        nivel=nivel,
        selo=selo,
        resumo=_aguardando(pendentes),
        complemento=complemento,
        quando=quando,
        ha_quanto=ha_quanto(quando, agora) if quando else "",
        erro=erro,
        acao_rotulo=acao_rotulo,
        acao_url=acao_url,
        acao_discreta=acao_discreta,
    )
