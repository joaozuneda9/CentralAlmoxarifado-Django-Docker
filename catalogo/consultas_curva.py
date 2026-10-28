"""Consultas da consolidação pelo de/para: lê os pares e as saídas do banco e entrega às funções
puras de `catalogo.depara` e `catalogo.curva`. Sem cache, como `catalogos.py`: um par novo vale
na consulta seguinte."""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Sum

from catalogo.curva import (
    COMPRAR,
    ESGOTADO,
    LinhaCurva,
    Pendente,
    Periodo,
    Reposicao,
    curva,
    pendentes,
    reposicao,
)
from catalogo.depara import (
    LinhaConsolidada,
    LinhaSaidas,
    Par,
    canonico_de,
    consolidar,
    resolver_canonicos,
)
from catalogo.models import (
    ConfiguracaoCurva,
    Material,
    ParametroReposicao,
    ParDePara,
    SaidaSCPI,
)
from pedidos.regras import norm_u


@dataclass(frozen=True)
class Reconciliacao:
    """Totais antes e depois da consolidação: ocorrências e valor precisam bater."""

    ocorrencias_antes: int
    ocorrencias_depois: int
    valor_antes: Decimal
    valor_depois: Decimal
    codigos_antes: int
    canonicos_depois: int

    @property
    def bate(self) -> bool:
        return (
            self.ocorrencias_antes == self.ocorrencias_depois
            and self.valor_antes == self.valor_depois
        )


def pares() -> list[Par]:
    return [Par(*p) for p in ParDePara.objects.values_list("antigo", "novo", "fator")]


def canonicos() -> dict[str, tuple[str, Decimal]]:
    """Código antigo normalizado → (canônico, fator), dos pares gravados (uma consulta)."""
    return resolver_canonicos(pares())


def saidas_por_codigo(periodo: Periodo) -> list[LinhaSaidas]:
    """Saídas do período somadas por código, numa consulta."""
    linhas = (
        SaidaSCPI.objects.filter(data__gte=periodo.inicio, data__lte=periodo.fim)
        .values("cadpro")
        .annotate(n=Count("id"), qtd=Sum("qtd"), valor=Sum("valor"))
        .order_by("cadpro")
    )
    return [LinhaSaidas(r["cadpro"], r["n"], r["qtd"], r["valor"]) for r in linhas]


def _reconciliar(brutas: list[LinhaSaidas], linhas: list[LinhaConsolidada]) -> Reconciliacao:
    return Reconciliacao(
        ocorrencias_antes=sum(b.ocorrencias for b in brutas),
        ocorrencias_depois=sum(c.ocorrencias for c in linhas),
        valor_antes=sum((b.valor for b in brutas), Decimal(0)),
        valor_depois=sum((c.valor for c in linhas), Decimal(0)),
        codigos_antes=len(brutas),
        canonicos_depois=len(linhas),
    )


def consolidado(periodo: Periodo) -> tuple[list[LinhaConsolidada], Reconciliacao]:
    """Saídas do período somadas pelo canônico, e a reconciliação dos totais."""
    brutas = saidas_por_codigo(periodo)
    linhas = consolidar(brutas, canonicos())
    return linhas, _reconciliar(brutas, linhas)


@dataclass(frozen=True)
class LinhaReposicao:
    """Linha da aba Reposição: o material, os parâmetros usados e o cálculo."""

    canonico: str
    descricao: str
    unidade: str
    consumo: Decimal
    estoque: Decimal  # saldo do canônico + saldos dos códigos antigos que apontam para ele
    prazo: int
    prazo_proprio: bool
    cobertura: int
    cobertura_propria: bool
    calculo: Reposicao


ORDEM_SITUACAO = {ESGOTADO: 0, COMPRAR: 1}


def tabela_de_reposicao(
    linhas: list[LinhaConsolidada], lista_pares: list[Par], periodo: Periodo
) -> list[LinhaReposicao]:
    """Reposição de cada canônico com saída no período que está no cadastro e não está oculto,
    dos esgotados para os em estoque. Consultas fixas: saldos, materiais e parâmetros."""
    mapa = resolver_canonicos(lista_pares)
    antigos: dict[str, list[str]] = {}
    for par in lista_pares:
        antigos.setdefault(norm_u(canonico_de(par.antigo, mapa)[0]), []).append(par.antigo)
    codigos = {c.canonico for c in linhas}
    codigos |= {a for c in linhas for a in antigos.get(norm_u(c.canonico), [])}
    materiais = {
        norm_u(m["codigo"]): m
        for m in Material.objects.filter(codigo__in=codigos).values(
            "codigo", "nome", "unidade", "oculto", "estoque"
        )
    }
    parametros = {
        norm_u(p.material.codigo): p
        for p in ParametroReposicao.objects.select_related("material").filter(
            material__codigo__in=[c.canonico for c in linhas]
        )
    }
    geral = ConfiguracaoCurva.atual()
    resultado = []
    for linha in linhas:
        chave = norm_u(linha.canonico)
        material = materiais.get(chave)
        if material is None or material["oculto"]:
            continue
        estoque = material["estoque"] + sum(
            (
                materiais[norm_u(a)]["estoque"]
                for a in antigos.get(chave, [])
                if norm_u(a) in materiais
            ),
            Decimal(0),
        )
        proprio = parametros.get(chave)
        prazo = proprio.prazo_entrega_dias if proprio else None
        cobertura = proprio.cobertura_alvo_dias if proprio else None
        resultado.append(
            LinhaReposicao(
                canonico=linha.canonico,
                descricao=material["nome"],
                unidade=material["unidade"],
                consumo=linha.qtd,
                estoque=estoque,
                prazo=prazo or geral.prazo_entrega_dias,
                prazo_proprio=prazo is not None,
                cobertura=cobertura or geral.cobertura_alvo_dias,
                cobertura_propria=cobertura is not None,
                calculo=reposicao(
                    linha.qtd,
                    estoque,
                    prazo or geral.prazo_entrega_dias,
                    cobertura or geral.cobertura_alvo_dias,
                    periodo.dias,
                ),
            )
        )
    return sorted(
        resultado,
        key=lambda r: (ORDEM_SITUACAO.get(r.calculo.situacao, 2), norm_u(r.canonico)),
    )


@dataclass(frozen=True)
class DadosCurva:
    """Tudo o que a página Curva ABC mostra para um período."""

    periodo: Periodo
    reconciliacao: Reconciliacao
    frequencia: list[LinhaCurva]
    valor: list[LinhaCurva]
    pendentes: list[Pendente]
    reposicao: list[LinhaReposicao]


def dados_da_curva(periodo: Periodo) -> DadosCurva:
    """Consolida o período e monta as curvas e os pendentes (consultas fixas, sem uma por
    material)."""
    lista_pares = pares()
    brutas = saidas_por_codigo(periodo)
    linhas = consolidar(brutas, resolver_canonicos(lista_pares))
    codigos = {b.codigo for b in brutas} | {c.canonico for c in linhas}
    materiais = {
        norm_u(m["codigo"]): m
        for m in Material.objects.filter(codigo__in=codigos).values(
            "codigo", "nome", "unidade", "oculto"
        )
    }
    descricoes = {chave: (m["nome"], m["unidade"]) for chave, m in materiais.items()}
    return DadosCurva(
        periodo=periodo,
        reconciliacao=_reconciliar(brutas, linhas),
        frequencia=curva(linhas, "ocorrencias", descricoes),
        valor=curva(linhas, "valor", descricoes),
        pendentes=pendentes(
            brutas,
            lista_pares,
            {chave: (m["nome"], m["oculto"]) for chave, m in materiais.items()},
        ),
        reposicao=tabela_de_reposicao(linhas, lista_pares, periodo),
    )
