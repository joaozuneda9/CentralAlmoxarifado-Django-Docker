"""Leituras da conciliação para as outras partes do sistema (spec 010)."""

from dataclasses import dataclass, field
from datetime import date, datetime

from django.core.paginator import Page, Paginator
from django.db.models import F, OuterRef, Q, Subquery, Window
from django.db.models.functions import RowNumber

from conciliacao import regras
from conciliacao.models import (
    Candidata,
    ConferenciaLote,
    CorrecaoVinculo,
    ExtracaoOficial,
    TentativaLancamento,
)
from conciliacao.servicos import ultima_tentativa
from pedidos.models import LinhaSaida
from pedidos.regras import LANCADA

SEM_TENTATIVA = (
    "Esta requisição não tem a tentativa registrada; não dá para provar que o SCPI não a salvou. "
    "Informe o número ou marque para não lançar."
)
SEM_EXTRACAO = (
    "Ainda não há uma extração do SCPI feita depois desta tentativa. Use “Conferir agora” e "
    "tente de novo."
)


@dataclass(frozen=True)
class Liberacao:
    permitida: bool
    motivo: str = ""
    candidatas: list[str] = field(default_factory=list)


def liberacao(lote: str) -> Liberacao:
    """Se um lote em verificar pode voltar para a fila (FR-024, research R17).

    Exige, para a tentativa mais recente do lote, ao menos uma conferência de uma extração
    bem-sucedida feita depois dela e cobrindo a data do lote, e nenhuma candidata em nenhuma
    delas: uma candidata vista uma vez continua bloqueando (Princípio III)."""
    tentativa = ultima_tentativa(lote)
    if tentativa is None:
        return Liberacao(False, SEM_TENTATIVA)
    conferencias = ConferenciaLote.objects.filter(
        lote=lote, tipo=ConferenciaLote.Tipo.VERIFICAR, tentativa=tentativa
    )
    if not conferencias.exists():
        return Liberacao(False, SEM_EXTRACAO)
    numeros = sorted(
        set(
            Candidata.objects.filter(conferencia__in=conferencias).values_list(
                "requisicao__requisicao", flat=True
            )
        ),
        key=regras.chave,
    )
    if numeros:
        quantas = "uma requisição" if len(numeros) == 1 else f"{len(numeros)} requisições"
        verbo = "pode" if len(numeros) == 1 else "podem"
        return Liberacao(
            False,
            f"Há {quantas} no SCPI que {verbo} ser esta: {', '.join(numeros)}. Confira e "
            "informe o número, ou marque para não lançar.",
            numeros,
        )
    return Liberacao(True)


# --- A aba Lançamento no SCPI (FR-027) ---

Veredito = ConferenciaLote.Veredito
PROBLEMAS = (Veredito.DIVERGENTE, Veredito.DUPLICADO, Veredito.CONFLITO, Veredito.NAO_ENCONTRADO)
FILTROS = (
    ("problemas", "Divergências"),
    ("aguardando", "Aguardando"),
    ("comprovados", "Comprovados"),
    ("todos", "Todos"),
)
FILTRO_PADRAO = "problemas"
SELOS = {
    Veredito.COMPROVADO: "ok",
    Veredito.DIVERGENTE: "aviso",
    Veredito.DUPLICADO: "erro",
    Veredito.CONFLITO: "erro",
    Veredito.NAO_ENCONTRADO: "erro",
}
VINCULOS = {
    ConferenciaLote.Origem.OBSERVACOES: "pelas observações",
    ConferenciaLote.Origem.NUMERO: "pelo número gravado",
    ConferenciaLote.Origem.AMBOS: "pelas observações e pelo número gravado",
}
LIMITE_DA_LISTA = 50


@dataclass
class LoteConferido:
    """Um lote lançado e o seu veredito atual: a última conferência conclusiva que ainda vale
    (depois de uma correção do número, só as de extrações posteriores a ela). Sem nenhuma, o lote
    está "Aguardando"."""

    lote: str
    data: date
    centro: str
    recebedor: str
    numero: str
    lancado_em: datetime | None
    conferencia: ConferenciaLote | None = None
    correcao: CorrecaoVinculo | None = None

    @property
    def rotulo(self) -> str:
        if self.conferencia is None:
            return "Aguardando conferência"
        return self.conferencia.get_veredito_display()

    @property
    def selo(self) -> str:
        """O sufixo da classe do selo (o texto vai sempre junto: nunca só a cor)."""
        if self.conferencia is None:
            return "neutro"
        return SELOS.get(self.conferencia.veredito, "neutro")

    @property
    def vinculo(self) -> str:
        if self.conferencia is None or not self.conferencia.origem_vinculo:
            return ""
        return VINCULOS.get(self.conferencia.origem_vinculo, "")

    @property
    def grupo(self) -> str:
        if self.conferencia is None:
            return "aguardando"
        return "problemas" if self.conferencia.veredito in PROBLEMAS else "comprovados"

    @property
    def corrigivel(self) -> bool:
        return self.conferencia is not None and self.conferencia.veredito in (
            Veredito.NAO_ENCONTRADO,
            Veredito.CONFLITO,
        )

    @property
    def conflito_com(self) -> list[str]:
        """No vínculo em conflito, as requisições entre as quais a pessoa escolhe."""
        if self.conferencia is None or self.conferencia.veredito != Veredito.CONFLITO:
            return []
        return [
            r.requisicao
            for r in (self.conferencia.requisicao, self.conferencia.outra_requisicao)
            if r is not None
        ]

    @property
    def esperando_desde(self) -> datetime | None:
        """Desde quando o lote espera um veredito: o lançamento ou a correção do número."""
        if self.correcao is not None:
            return self.correcao.quando
        return self.lancado_em


def lotes_conferidos() -> list[LoteConferido]:
    """Os lotes lançados que a conciliação acompanha (com conferência, correção ou lançados pelo
    robô desde a conciliação), do lançamento mais recente para o mais antigo. Um lote antigo, de
    antes da conciliação e fora de qualquer extração, não entra: nada o conferiria."""
    correcoes: dict[str, CorrecaoVinculo] = {}
    for correcao in CorrecaoVinculo.objects.select_related("usuario").order_by("quando", "pk"):
        correcoes[correcao.lote] = correcao
    do_lancamento = ConferenciaLote.objects.filter(
        tipo__in=(ConferenciaLote.Tipo.LANCAMENTO, ConferenciaLote.Tipo.REVISAO)
    )
    lotes = set(correcoes) | set(do_lancamento.values_list("lote", flat=True).distinct())
    # O veredito atual de cada lote sai do banco, uma linha por lote: a conclusiva mais recente
    # entre as que ainda valem (depois de uma correção, só as de extrações começadas depois dela).
    ultima_correcao = (
        CorrecaoVinculo.objects.filter(lote=OuterRef("lote"))
        .order_by("-quando", "-pk")
        .values("quando")[:1]
    )
    conferencias = (
        do_lancamento.exclude(veredito=Veredito.AGUARDANDO)
        .annotate(corrigido_em=Subquery(ultima_correcao))
        .filter(
            Q(corrigido_em__isnull=True) | Q(extracao__importacao__inicio__gt=F("corrigido_em"))
        )
        .annotate(
            posicao=Window(
                RowNumber(),
                partition_by=[F("lote")],
                order_by=[F("criada_em").desc(), F("pk").desc()],
            )
        )
        .filter(posicao=1)
        .select_related("requisicao", "outra_requisicao", "extracao__importacao")
        # O bruto gzip da extração não serve à tela e viria em cada conferência.
        .defer("extracao__arquivo")
    )
    atuais = {conferencia.lote: conferencia for conferencia in conferencias}
    # A tentativa em verificar que a pessoa resolveu informando o número também é um lançamento a
    # acompanhar; o filtro das linhas lançadas, abaixo, deixa de fora a que segue travada.
    lotes |= set(
        TentativaLancamento.objects.filter(
            resultado__in=(
                TentativaLancamento.Resultado.LANCADA,
                TentativaLancamento.Resultado.VERIFICAR,
            ),
            historica=False,
        ).values_list("lote", flat=True)
    )
    por_lote: dict[str, LoteConferido] = {}
    for linha in LinhaSaida.objects.filter(lote__in=lotes, status=LANCADA).order_by("lote", "seq"):
        item = por_lote.get(linha.lote)
        if item is None:
            por_lote[linha.lote] = LoteConferido(
                lote=linha.lote,
                data=linha.data,
                centro=linha.centro_custo,
                recebedor=linha.recebedor,
                numero=linha.requisicao_scpi,
                lancado_em=linha.lancado_em,
                conferencia=atuais.get(linha.lote),
                correcao=correcoes.get(linha.lote),
            )
        elif linha.lancado_em and (item.lancado_em is None or linha.lancado_em > item.lancado_em):
            item.lancado_em = linha.lancado_em
    return sorted(
        por_lote.values(),
        key=lambda item: (item.lancado_em is not None, item.lancado_em, item.lote),
        reverse=True,
    )


@dataclass
class Conciliacao:
    """O que a aba mostra da conciliação dos lançados."""

    filtro: str
    contagens: dict[str, int]
    pagina: Page  # a página pedida dos lotes do filtro (`LIMITE_DA_LISTA` por página)

    @property
    def lotes(self) -> list[LoteConferido]:
        return list(self.pagina.object_list)

    @property
    def total(self) -> int:
        return self.pagina.paginator.count

    @property
    def filtros(self) -> list[tuple[str, str, int]]:
        return [(chave, rotulo, self.contagens[chave]) for chave, rotulo in FILTROS]


def ultima_extracao() -> ExtracaoOficial | None:
    return (
        ExtracaoOficial.objects.select_related("importacao")
        .defer("arquivo")
        .order_by("-importacao__inicio", "-pk")
        .first()
    )


def conciliacao_da_aba(filtro: str = FILTRO_PADRAO, pagina=1) -> Conciliacao:
    filtro = filtro if filtro in dict(FILTROS) else FILTRO_PADRAO
    todos = lotes_conferidos()
    contagens = {chave: 0 for chave, _ in FILTROS}
    for item in todos:
        contagens[item.grupo] += 1
    contagens["todos"] = len(todos)
    escolhidos = todos if filtro == "todos" else [i for i in todos if i.grupo == filtro]
    return Conciliacao(
        filtro=filtro,
        contagens=contagens,
        pagina=Paginator(escolhidos, LIMITE_DA_LISTA).get_page(pagina),
    )


@dataclass
class Verificacao:
    """O que a conciliação sabe de um lote em verificar, para o painel de resolução (FR-027)."""

    liberacao: Liberacao
    conferencia: ConferenciaLote | None  # a mais recente da tentativa atual
    candidatas: list[Candidata]  # todas as vistas, uma por requisição ("é esta" primeiro)


def verificacoes(lotes) -> dict[str, Verificacao]:
    """Uma `Verificacao` por lote em verificar (são poucos: a consulta é por lote)."""
    resultado = {}
    for lote in lotes:
        tentativa = ultima_tentativa(lote)
        conferencias = (
            ConferenciaLote.objects.filter(
                lote=lote, tipo=ConferenciaLote.Tipo.VERIFICAR, tentativa=tentativa
            )
            .select_related("extracao__importacao")
            .defer("extracao__arquivo")
            .order_by("-criada_em", "-pk")
            if tentativa is not None
            else ConferenciaLote.objects.none()
        )
        vistas: dict[str, Candidata] = {}
        for candidata in (
            Candidata.objects.filter(conferencia__in=conferencias)
            .select_related("requisicao")
            .prefetch_related("requisicao__itens")
            .order_by("-e_esta", "ordem", "-conferencia__criada_em")
        ):
            vistas.setdefault(candidata.requisicao.requisicao, candidata)
        resultado[lote] = Verificacao(liberacao(lote), conferencias.first(), list(vistas.values()))
    return resultado
