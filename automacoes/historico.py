"""Histórico combinado das automações: as importações do catálogo (`Importacao`) e as execuções do
robô de lançamento (`ExecucaoRobo`) numa lista só, da mais recente para a mais antiga.

Os filtros correm no banco, uma consulta por modelo; `SequenciaHistorico` intercala as duas pela
data de início e serve direto ao `Paginator`. A conversão de um registro em linha é pura.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from heapq import merge

from django import forms
from django.db.models import CharField, Q
from django.db.models.functions import Cast

from catalogo import forms as robos_catalogo
from catalogo.models import Importacao
from catalogo.saude import GrupoAvisos, agrupar_avisos, erro_tecnico, numero, resumo_do_erro
from pedidos import andamento
from pedidos.consultas import inicio_do_dia
from pedidos.models import ExecucaoRobo

ROBOS = [
    ("lancamento", "Lançamento no SCPI"),
    *((robo.chave, robo.rotulo) for robo in robos_catalogo.ROBOS),
    ("depara", "Pares de/para"),
]
ROTULO_DO_TIPO = {chave.upper(): rotulo for chave, rotulo in ROBOS if chave != "lancamento"}
SITUACOES = [
    ("concluida", "Concluída"),
    ("com_avisos", "Com avisos"),
    ("falhou", "Falhou"),
    ("interrompida", "Interrompida"),
    ("andamento", "Em andamento"),
]
# Nível do selo de cada situação (o estado também vai sempre em texto).
NIVEL = {
    "concluida": "ok",
    "com_avisos": "aviso",
    "falhou": "erro",
    "interrompida": "aviso",
    "andamento": "info",
}


class FiltrosHistorico(forms.Form):
    q = forms.CharField(
        required=False,
        label="Buscar",
        widget=forms.TextInput(
            attrs={
                "class": "campo-entrada",
                "type": "search",
                "placeholder": "Erro, aviso ou registro",
            }
        ),
    )
    robo = forms.ChoiceField(
        required=False,
        label="Robô",
        choices=[("", "Todos"), *ROBOS],
        widget=forms.Select(attrs={"class": "campo-entrada"}),
    )
    situacao = forms.ChoiceField(
        required=False,
        label="Situação",
        choices=[("", "Todas"), *SITUACOES],
        widget=forms.Select(attrs={"class": "campo-entrada"}),
    )
    de = forms.DateField(
        required=False,
        label="De",
        widget=forms.DateInput(attrs={"type": "date", "class": "campo-entrada"}),
    )
    ate = forms.DateField(
        required=False,
        label="Até",
        widget=forms.DateInput(attrs={"type": "date", "class": "campo-entrada"}),
    )

    def filtros(self) -> dict:
        """Só os filtros válidos e preenchidos: um valor desconhecido some, a lista não quebra."""
        self.is_valid()
        return {nome: valor for nome, valor in self.cleaned_data.items() if valor}


@dataclass(frozen=True)
class LinhaHistorico:
    robo: str
    modo: str
    inicio: datetime
    duracao: str
    situacao: str  # chave de SITUACOES
    selo: str
    resumo: str
    avisos: list[GrupoAvisos] = field(default_factory=list)
    n_avisos: int = 0
    erro: str = ""
    erro_tecnico: str = ""
    iniciada_por: str = ""
    # Desempate na intercalação: com o mesmo início, o lançamento vem antes, e o mais novo antes.
    ordem: tuple = ()

    @property
    def nivel(self) -> str:
        return NIVEL[self.situacao]


def _periodo(de, ate) -> str:
    return f"{de:%d/%m} a {ate:%d/%m}"


def _modo_da_importacao(imp: Importacao) -> str:
    if imp.tipo == Importacao.Tipo.CADASTRO:
        if imp.periodo_de:
            return f"Só os novos ({_periodo(imp.periodo_de, imp.periodo_ate)})"
        return "Recarga completa"
    if imp.tipo == Importacao.Tipo.SAIDAS and imp.periodo_de:
        return f"Período {_periodo(imp.periodo_de, imp.periodo_ate)}"
    if imp.tipo == Importacao.Tipo.ESTOQUE:
        return "Saldos"
    if imp.tipo == Importacao.Tipo.DEPARA:
        return "Carga da planilha"
    return ""


def linha_de_importacao(imp: Importacao, em_andamento: set) -> LinhaHistorico:
    """`em_andamento`: ids das importações que estão rodando de verdade (as demais sem fim foram
    interrompidas)."""
    if imp.situacao == Importacao.Situacao.ANDAMENTO:
        situacao = "andamento" if imp.pk in em_andamento else "interrompida"
    elif imp.situacao == Importacao.Situacao.FALHA:
        situacao = "falhou"
    else:
        situacao = "com_avisos" if imp.avisos else "concluida"
    return LinhaHistorico(
        robo=ROTULO_DO_TIPO.get(imp.tipo, imp.get_tipo_display()),
        modo=_modo_da_importacao(imp),
        inicio=imp.inicio,
        duracao=andamento.duracao(imp.inicio, imp.fim),
        situacao=situacao,
        selo=dict(SITUACOES)[situacao],
        # Sem linhas gravadas (falhou ou ainda roda), o número não diz nada.
        resumo=f"{numero(imp.linhas)} {'linha' if imp.linhas == 1 else 'linhas'}"
        if imp.linhas or situacao in ("concluida", "com_avisos")
        else "",
        avisos=agrupar_avisos(imp.avisos or []),
        n_avisos=len(imp.avisos or []),
        erro=resumo_do_erro(imp.erro) if imp.erro else "",
        erro_tecnico=imp.erro if imp.erro and erro_tecnico(imp.erro) else "",
        ordem=(imp.inicio, 0, imp.pk or 0),
    )


def linha_de_execucao(exe: ExecucaoRobo, em_andamento: set) -> LinhaHistorico:
    """`em_andamento`: ids das execuções do robô que estão rodando de verdade."""
    if exe.situacao == ExecucaoRobo.Situacao.ANDAMENTO:
        situacao = "andamento" if exe.pk in em_andamento else "interrompida"
    elif exe.situacao == ExecucaoRobo.Situacao.FALHA:
        situacao = "falhou"
    elif exe.situacao == ExecucaoRobo.Situacao.ATENCAO:
        situacao = "com_avisos"
    else:
        situacao = "concluida"
    falha = andamento.explicar_falha(exe)
    quem = exe.iniciada_por
    return LinhaHistorico(
        robo="Lançamento no SCPI",
        modo="Simulação" if exe.simulacao else "Lançamento real",
        inicio=exe.inicio,
        duracao=andamento.duracao(exe.inicio, exe.fim),
        situacao=situacao,
        selo="Com pendências" if situacao == "com_avisos" else dict(SITUACOES)[situacao],
        resumo=andamento.n_de_m(exe) or "",
        erro=falha.frase if falha else "",
        erro_tecnico=exe.erro if falha and falha.tecnico else "",
        iniciada_por=(quem.get_full_name() or quem.username) if quem else "",
        ordem=(exe.inicio, 1, exe.pk or 0),
    )


def _filtrar_situacao(qs, situacao: str, ids_andamento: set, modelo):
    """O vocabulário unificado (research.md, R6) em cada modelo."""
    sem_fim = qs.filter(situacao=modelo.Situacao.ANDAMENTO)
    if situacao == "andamento":
        return sem_fim.filter(pk__in=ids_andamento)
    if situacao == "interrompida":
        return sem_fim.exclude(pk__in=ids_andamento)
    if situacao == "falhou":
        return qs.filter(situacao=modelo.Situacao.FALHA)
    if modelo is ExecucaoRobo:
        alvo = modelo.Situacao.ATENCAO if situacao == "com_avisos" else modelo.Situacao.SUCESSO
        return qs.filter(situacao=alvo)
    # Importação: "sem avisos" é a lista vazia, comparada como texto (MySQL e MariaDB guardam o
    # JSON de forma diferente, mas os dois devolvem "[]").
    qs = qs.filter(situacao=modelo.Situacao.SUCESSO).annotate(
        avisos_texto=Cast("avisos", CharField())
    )
    if situacao == "concluida":
        return qs.filter(avisos_texto="[]")
    return qs.exclude(avisos_texto="[]")


def _filtrar(qs, filtros: dict, ids_andamento: set, modelo):
    situacao, q = filtros.get("situacao"), filtros.get("q")
    if situacao:
        qs = _filtrar_situacao(qs, situacao, ids_andamento, modelo)
    if q and modelo is Importacao:
        qs = qs.annotate(avisos_busca=Cast("avisos", CharField())).filter(
            Q(erro__icontains=q) | Q(avisos_busca__icontains=q)
        )
    elif q:
        qs = qs.filter(Q(erro__icontains=q) | Q(log__icontains=q))
    if de := filtros.get("de"):
        qs = qs.filter(inicio__gte=inicio_do_dia(de))
    if ate := filtros.get("ate"):
        qs = qs.filter(inicio__lt=inicio_do_dia(ate + timedelta(days=1)))
    return qs


def consultas(filtros: dict, agora: datetime) -> tuple:
    """(importações, execuções, ids de importações em andamento, ids de execuções em andamento),
    já filtradas; uma das consultas é None quando o filtro de robô a exclui."""
    robo = filtros.get("robo")
    ids_imp = set(Importacao.em_andamento(agora).values_list("pk", flat=True))
    ids_exe = set(ExecucaoRobo.em_andamento(agora).values_list("pk", flat=True))
    importacoes = execucoes = None
    if robo != "lancamento":
        qs = Importacao.objects.filter(tipo=robo.upper()) if robo else Importacao.objects.all()
        importacoes = _filtrar(qs, filtros, ids_imp, Importacao)
    if not robo or robo == "lancamento":
        qs = ExecucaoRobo.objects.select_related("iniciada_por")
        execucoes = _filtrar(qs, filtros, ids_exe, ExecucaoRobo)
    return importacoes, execucoes, ids_imp, ids_exe


class SequenciaHistorico:
    """As duas consultas como uma lista ordenada por início (mais recente primeiro), que o
    `Paginator` fatia: a página N lê só `20·N` linhas de cada tabela."""

    def __init__(self, importacoes, execucoes, ids_imp: set, ids_exe: set):
        self.importacoes = (
            importacoes.order_by("-inicio", "-pk") if importacoes is not None else None
        )
        self.execucoes = execucoes.order_by("-inicio", "-pk") if execucoes is not None else None
        self.ids_imp, self.ids_exe = ids_imp, ids_exe
        self._total = None

    def count(self) -> int:
        if self._total is None:
            self._total = sum(
                qs.count() for qs in (self.importacoes, self.execucoes) if qs is not None
            )
        return self._total

    def __len__(self) -> int:
        return self.count()

    def __getitem__(self, fatia):
        if not isinstance(fatia, slice):
            return self[fatia : fatia + 1][0]
        fim = fatia.stop if fatia.stop is not None else self.count()
        partes = []
        if self.importacoes is not None:
            partes.append([linha_de_importacao(i, self.ids_imp) for i in self.importacoes[:fim]])
        if self.execucoes is not None:
            partes.append([linha_de_execucao(e, self.ids_exe) for e in self.execucoes[:fim]])
        juntas = merge(*partes, key=lambda linha: linha.ordem, reverse=True)
        return list(juntas)[fatia.start or 0 : fim]
