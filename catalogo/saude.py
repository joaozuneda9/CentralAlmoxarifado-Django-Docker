"""Saúde do catálogo: o que o almoxarifado precisa saber sobre as importações e os catálogos
dos formulários (traduz o relatório de saúde de `montarCatalogos_`, no `Catalogo.gs`).

`saude_do_catalogo` é a lista curta que o painel mostra; `situacao_do_catalogo` é a mesma
informação arrumada para a página Catálogo: uma linha por fonte de dados, os avisos agrupados e
os números dos formulários."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property

from django.db.models import Max
from django.utils import timezone
from django.utils.formats import number_format

from catalogo.catalogos import (
    CatalogoAB,
    _grupo,
    catalogo_ab,
    catalogo_efetivo,
    catalogo_viaturas,
    centros_do_formulario,
)
from catalogo.models import (
    CentroCusto,
    ExcecaoMaterial,
    Formulario,
    Importacao,
    ItemLimpeza,
    Material,
    Opcao,
    PecaViatura,
)
from scpi.execucao import PREFIXO_FALHA_INESPERADA
from scpi.gravacao import lista_curta

# Importações que o catálogo precisa sempre; a carga dos pares de/para (DEPARA) é única e só
# aparece depois de feita.
IMPORTACOES_DO_SCPI = (
    Importacao.Tipo.CADASTRO,
    Importacao.Tipo.ESTOQUE,
    Importacao.Tipo.SAIDAS,
)

# Saldo mais antigo que isto gera aviso.
LIMITE_SALDO = timedelta(hours=24)


@dataclass(frozen=True)
class ItemSaude:
    nivel: str  # "ok", "aviso" ou "erro"
    texto: str


@dataclass(frozen=True)
class GrupoAvisos:
    """Avisos com o mesmo começo ("Texto cortado em nome (255 caracteres)") juntos: o importador
    gera um por código, e oito iguais seguidos escondem o resto."""

    titulo: str
    itens: tuple[str, ...] = ()

    @property
    def texto(self) -> str:
        if not self.itens:
            return f"{self.titulo}."
        if len(self.itens) == 1:
            return f"{self.titulo}: {self.itens[0]}."
        return f"{self.titulo} ({len(self.itens)}): {lista_curta(list(self.itens))}."


def agrupar_avisos(avisos: list[str]) -> list[GrupoAvisos]:
    """Junta os avisos pelo texto antes do primeiro ": ", na ordem em que aparecem."""
    grupos: dict[str, list[str]] = {}
    for aviso in avisos:
        titulo, separador, resto = aviso.partition(": ")
        if not separador:
            titulo, resto = aviso, ""
        itens = grupos.setdefault(titulo.rstrip(". "), [])
        if resto.strip():
            itens.append(resto.strip().rstrip("."))
    return [GrupoAvisos(titulo, tuple(itens)) for titulo, itens in grupos.items()]


def resumo_do_erro(erro: str) -> str:
    """Uma frase para a tabela. O erro previsto pelo importador já é uma frase para quem usa; o
    inesperado traz o registro do Playwright, que fica nos detalhes."""
    if not erro.startswith(PREFIXO_FALHA_INESPERADA):
        return erro
    primeira = erro.removeprefix(PREFIXO_FALHA_INESPERADA).strip().splitlines()[0:1]
    if primeira and "Timeout" in primeira[0]:
        return "O SCPI demorou demais para responder e a importação parou."
    return "O robô parou por um erro inesperado."


def erro_tecnico(erro: str) -> bool:
    return erro.startswith(PREFIXO_FALHA_INESPERADA)


def numero(valor: int) -> str:
    """11597 → "11.597"."""
    return number_format(valor, force_grouping=True)


def _quando(momento: datetime) -> str:
    return timezone.localtime(momento).strftime("%d/%m/%Y %H:%M")


def ha_quanto(momento: datetime, agora: datetime) -> str:
    """Há quanto tempo, em texto curto: "há 5 min", "há 3 h", "ontem às 10:16" ou "07/10 às
    10:16"."""
    segundos = (agora - momento).total_seconds()
    local = timezone.localtime(momento)
    if segundos < 60:
        return "agora há pouco"
    if segundos < 3600:
        return f"há {int(segundos // 60)} min"
    if local.date() == timezone.localtime(agora).date():
        return f"há {int(segundos // 3600)} h"
    if (timezone.localtime(agora).date() - local.date()).days == 1:
        return f"ontem às {local:%H:%M}"
    return f"{local:%d/%m} às {local:%H:%M}"


def _importacao(tipo: Importacao.Tipo, agora: datetime) -> ItemSaude:
    rotulo = tipo.label
    ultima = Importacao.objects.filter(tipo=tipo).order_by("-inicio").first()
    if ultima is None:
        return ItemSaude("erro", f"{rotulo}: nenhuma importação ainda.")
    if ultima.situacao == Importacao.Situacao.FALHA:
        return ItemSaude(
            "erro",
            f"{rotulo}: a última importação falhou em {_quando(ultima.fim or ultima.inicio)}: "
            f"{resumo_do_erro(ultima.erro)} Os dados anteriores continuam valendo.",
        )
    if ultima.situacao == Importacao.Situacao.ANDAMENTO:
        if ultima.esta_interrompida(agora):
            return ItemSaude(
                "aviso",
                f"{rotulo}: a importação iniciada em {_quando(ultima.inicio)} não terminou "
                "(interrompida).",
            )
        return ItemSaude("ok", f"{rotulo}: importação em andamento desde {_quando(ultima.inicio)}.")
    quando = _quando(ultima.fim or ultima.inicio)
    if ultima.avisos:
        avisos = " ".join(grupo.texto for grupo in agrupar_avisos(ultima.avisos))
        return ItemSaude("aviso", f"{rotulo}: atualizado em {quando}, com avisos: {avisos}")
    return ItemSaude("ok", f"{rotulo}: atualizado em {quando}.")


def _tipos() -> list[Importacao.Tipo]:
    tipos = list(IMPORTACOES_DO_SCPI)
    if Importacao.objects.filter(tipo=Importacao.Tipo.DEPARA).exists():
        tipos.append(Importacao.Tipo.DEPARA)
    return tipos


def _cadastro() -> tuple[int, int]:
    total = Material.objects.count()
    return total, (Material.objects.filter(oculto=True).count() if total else 0)


class _Catalogos:
    """Os catálogos que a saúde e os cartões da visão geral leem, cada um calculado uma vez e só
    quando alguém o pede: a oficina e os EPIs leem o cadastro inteiro, e a visão geral se recarrega
    a cada 5 s. `ab` é o catálogo AB que o chamador já calculou (None: saldo nunca importado)."""

    def __init__(self, ab: CatalogoAB | None):
        self.ab = ab

    @cached_property
    def limpeza(self) -> list:
        return catalogo_efetivo(Formulario.LIMPEZA)

    @cached_property
    def ab_efetivo(self) -> list:
        return catalogo_efetivo(Formulario.AB, self.ab) if self.ab is not None else []

    @cached_property
    def lista_viaturas(self) -> list:
        return catalogo_viaturas()

    @cached_property
    def viaturas_efetivo(self) -> list:
        return catalogo_efetivo(Formulario.VIATURAS, self.ab, viaturas=self.lista_viaturas)

    @cached_property
    def oficina(self) -> list:
        return catalogo_efetivo(Formulario.OFICINA)

    @cached_property
    def epis(self) -> list:
        return catalogo_efetivo(Formulario.EPIS)

    @cached_property
    def grupos_visiveis(self) -> set[str]:
        """Os grupos com algum material visível, normalizados (os da oficina e dos EPIs)."""
        visiveis = Material.objects.filter(oculto=False).values_list("grupo", flat=True)
        return {_grupo(g) for g in visiveis.distinct()}


FORMULARIO_VIATURAS = "Formulário de reposição de peças das viaturas"


def _viaturas(ab: CatalogoAB, catalogos: _Catalogos) -> list[ItemSaude]:
    """O formulário de reposição de peças das viaturas (spec 006): quanto oferece ou por que está
    indisponível, e as peças da lista que não aparecem (o saldo já foi importado)."""
    saude = []
    lista = {i.codigo for i in catalogos.lista_viaturas}
    do_ab = sum(1 for i in ab.itens if i.codigo not in lista)
    efetivo = catalogos.viaturas_efetivo
    if not centros_do_formulario(Formulario.VIATURAS):
        saude.append(
            ItemSaude(
                "erro",
                f"{FORMULARIO_VIATURAS}: nenhum centro de custo habilitado como destino; o "
                "formulário fica indisponível.",
            )
        )
    elif not efetivo:
        # O que o formulário oferece de fato (regra mais exceções): só está vazio se a lista, o AB
        # e os acrescentados estão; o texto diz qual dos dois casos é.
        if not lista and not do_ab:
            motivo = "nenhuma peça na lista nem material no AB"
        else:
            motivo = "todos os materiais foram retirados do formulário"
        saude.append(
            ItemSaude("erro", f"{FORMULARIO_VIATURAS}: {motivo}; o formulário fica indisponível.")
        )
    else:
        pecas = "1 peça" if len(lista) == 1 else f"{numero(len(lista))} peças"
        materiais = "1 material" if do_ab == 1 else f"{numero(do_ab)} materiais"
        saude.append(
            ItemSaude("ok", f"{FORMULARIO_VIATURAS}: {pecas} na lista e {materiais} do AB.")
        )
    ocultas = list(
        PecaViatura.objects.filter(material__oculto=True).values_list("material__codigo", flat=True)
    )
    if ocultas:
        saude.append(
            ItemSaude(
                "aviso",
                f"Peças das viaturas ocultas no SCPI (não aparecem): {lista_curta(ocultas)}.",
            )
        )
    return saude


FORMULARIO_OFICINA = "Formulário da oficina mecânica"


def _materiais(n: int) -> str:
    return "1 material" if n == 1 else f"{numero(n)} materiais"


def _grupos_e_ocultos(catalogos: _Catalogos, origem: str, lista: str, de: str) -> list[ItemSaude]:
    """Os avisos dos formulários por grupos (oficina e EPIs): os grupos da lista sem material
    visível e os avulsos (exceções que acrescentam) ocultos no SCPI. `de`: "da oficina", "de
    EPIs"."""
    saude = []
    sem_material = [v for v in Opcao.valores(lista) if _grupo(v) not in catalogos.grupos_visiveis]
    if sem_material:
        saude.append(
            ItemSaude("aviso", f"Grupos {de} sem material visível: {lista_curta(sem_material)}.")
        )
    ocultos = list(
        ExcecaoMaterial.objects.filter(
            formulario=origem, habilitado=True, material__oculto=True
        ).values_list("material__codigo", flat=True)
    )
    if ocultos:
        saude.append(
            ItemSaude(
                "aviso", f"Materiais {de} ocultos no SCPI (não aparecem): {lista_curta(ocultos)}."
            )
        )
    return saude


def _oficina(catalogos: _Catalogos) -> list[ItemSaude]:
    """O formulário da oficina mecânica (spec 007): quanto oferece ou por que está indisponível,
    os grupos da lista sem material visível, os avulsos ocultos e a falta do centro da oficina
    (o saldo já foi importado)."""
    saude = []
    centros = centros_do_formulario(Formulario.OFICINA)
    n = len(catalogos.oficina)
    if not centros:
        saude.append(
            ItemSaude(
                "erro",
                f"{FORMULARIO_OFICINA}: nenhum destino (nem o centro OFICINA MECÂNICA nem centro "
                "com placa); o formulário fica indisponível.",
            )
        )
    elif not n:
        saude.append(
            ItemSaude(
                "erro",
                f"{FORMULARIO_OFICINA}: nenhum material nos grupos nem entre os materiais da "
                "oficina; o formulário fica indisponível.",
            )
        )
    else:
        saude.append(ItemSaude("ok", f"{FORMULARIO_OFICINA}: {_materiais(n)}."))
    if centros and all(c.so_com_placa for c in centros):
        saude.append(
            ItemSaude(
                "aviso",
                f"{FORMULARIO_OFICINA}: centro OFICINA MECÂNICA não está habilitado como destino "
                "(ou não está cadastrado); só as viaturas são oferecidas.",
            )
        )
    return saude + _grupos_e_ocultos(
        catalogos, Formulario.OFICINA, Opcao.Lista.GRUPO_OFICINA, "da oficina"
    )


FORMULARIO_EPIS = "Formulário de EPIs"


def _epis(catalogos: _Catalogos) -> list[ItemSaude]:
    """O formulário de EPIs (spec 008): quanto oferece ou por que está indisponível, os grupos da
    lista sem material visível e os avulsos ocultos (o saldo já foi importado). O destino é
    qualquer centro de custo, como nos formulários de limpeza e AB, então não há aviso de destino
    aqui (o aviso geral de "nenhum centro de custo cadastrado" já cobre)."""
    n = len(catalogos.epis)
    if n:
        oferta = ItemSaude("ok", f"{FORMULARIO_EPIS}: {_materiais(n)}.")
    else:
        oferta = ItemSaude(
            "erro",
            f"{FORMULARIO_EPIS}: nenhum material nos grupos nem entre os materiais de EPIs; "
            "o formulário fica indisponível.",
        )
    return [oferta] + _grupos_e_ocultos(
        catalogos, Formulario.EPIS, Opcao.Lista.GRUPO_EPI, "de EPIs"
    )


FORMULARIOS_SEM_AVISO_PROPRIO = {
    Formulario.LIMPEZA: "Formulário de limpeza",
    Formulario.AB: "Formulário AB",
    Formulario.EPIS: FORMULARIO_EPIS,
}


def _destinos_e_excecoes(ab: CatalogoAB | None, catalogos: _Catalogos) -> list[ItemSaude]:
    """A configuração por formulário (spec 009, FR-039): formulário sem destino (as viaturas e a
    oficina já dizem o seu), centro ativo que não é destino de nenhum e exceção sem efeito. Só
    roda o cálculo das regras de origem para o formulário que tem exceção (o das viaturas
    reaproveita a lista já calculada em `catalogos`)."""
    from catalogo.disponibilidade import situacao_do_formulario

    saude = []
    for formulario, nome in FORMULARIOS_SEM_AVISO_PROPRIO.items():
        if not centros_do_formulario(formulario):
            saude.append(
                ItemSaude(
                    "erro",
                    f"{nome}: nenhum centro de custo habilitado como destino; o formulário "
                    "fica indisponível.",
                )
            )
    sem_formulario = sorted(
        {
            f"{c.descricao} — {c.placa}" if c.placa else c.descricao
            for c in CentroCusto.objects.filter(ativo=True, formularios__isnull=True)
        }
    )
    if sem_formulario:
        saude.append(
            ItemSaude(
                "aviso",
                "Centros de custo ativos sem nenhum formulário (não são destino de nenhum): "
                f"{lista_curta(sem_formulario)}.",
            )
        )
    com_excecao = set(ExcecaoMaterial.objects.values_list("formulario", flat=True))
    for formulario in Formulario.values:
        if formulario not in com_excecao:
            continue
        viaturas = catalogos.lista_viaturas if formulario == Formulario.VIATURAS else None
        situacao = situacao_do_formulario(formulario, ab, viaturas)
        sem_efeito = sorted(
            codigo
            for codigo, habilitado in situacao.excecoes.items()
            if habilitado == (codigo in situacao.na_regra)
        )
        if sem_efeito:
            saude.append(
                ItemSaude(
                    "aviso",
                    f"Exceções sem efeito em {Formulario(formulario).label} (a regra já dá o "
                    f"resultado): {lista_curta(sem_efeito)}.",
                )
            )
    return saude


def _demais(
    agora: datetime,
    ab: CatalogoAB | None,
    total: int,
    ocultos: int,
    catalogos: _Catalogos | None = None,
) -> list[ItemSaude]:
    """Tudo o que não é a situação de uma importação: cadastro, saldo e formulários. `catalogos`
    reaproveita os catálogos que o chamador já calculou (sem ele, são calculados aqui)."""
    catalogos = catalogos if catalogos is not None else _Catalogos(ab)
    saude = []
    if total:
        saude.append(
            ItemSaude(
                "ok",
                f"Cadastro: {numero(total)} materiais; {numero(ocultos)} ocultos no SCPI ficam "
                "fora de todos os formulários.",
            )
        )
    duplicados = list(Material.objects.filter(duplicado=True).values_list("codigo", flat=True))
    if duplicados:
        saude.append(
            ItemSaude(
                "aviso", f"Códigos repetidos no cadastro (bloqueados): {lista_curta(duplicados)}."
            )
        )

    if ab is None:
        saude.append(
            ItemSaude(
                "erro",
                "Sem saldo importado: os formulários públicos ficam indisponíveis até a próxima "
                "importação de estoque.",
            )
        )
    else:
        saldo_em = Material.objects.aggregate(m=Max("estoque_em"))["m"]
        if saldo_em < agora - LIMITE_SALDO:
            saude.append(
                ItemSaude(
                    "aviso",
                    f"O saldo de estoque não é atualizado desde {_quando(saldo_em)} "
                    "(mais de 24 h).",
                )
            )

    itens_limpeza = len(catalogos.limpeza)
    if itens_limpeza:
        saude.append(ItemSaude("ok", f"Formulário de limpeza: {itens_limpeza} itens."))
    else:
        saude.append(
            ItemSaude(
                "erro",
                "Formulário de limpeza: nenhum item no catálogo; o formulário fica indisponível.",
            )
        )
    limpeza_oculta = list(
        ItemLimpeza.objects.filter(material__oculto=True).values_list("material__codigo", flat=True)
    )
    if limpeza_oculta:
        saude.append(
            ItemSaude(
                "aviso",
                "Itens da lista de limpeza ocultos no SCPI (não aparecem): "
                f"{lista_curta(limpeza_oculta)}.",
            )
        )

    if ab is not None:
        com_saida = f"{ab.codigos} códigos com saída no SCPI"
        descartados = (
            f"{ab.na_limpeza} também na lista de limpeza, que prevalece; "
            f"{ab.ocultos} ocultos ou em grupo oculto"
        )
        # O que o formulário oferece de fato (regra mais exceções); a regra do AB segue como
        # informação separada, no texto.
        efetivo = catalogos.ab_efetivo
        if efetivo and not ExcecaoMaterial.objects.filter(formulario=Formulario.AB).exists():
            saude.append(
                ItemSaude(
                    "ok", f"Formulário AB: {len(efetivo)} itens de {com_saida} ({descartados})."
                )
            )
        elif efetivo:
            saude.append(
                ItemSaude(
                    "ok",
                    f"Formulário AB: {len(efetivo)} itens, contadas as exceções do administrador "
                    f"({len(ab.itens)} pela regra, de {com_saida}; {descartados}).",
                )
            )
        elif ab.itens:
            saude.append(
                ItemSaude(
                    "erro",
                    "Formulário AB: todos os materiais foram retirados do formulário; o "
                    "formulário fica indisponível.",
                )
            )
        else:
            saude.append(
                ItemSaude(
                    "erro",
                    f"Formulário AB: nenhum item no catálogo ({com_saida}; {descartados}); "
                    "o formulário fica indisponível.",
                )
            )
        if ab.sem_cadastro:
            saude.append(
                ItemSaude(
                    "aviso",
                    "Códigos com saída no SCPI sem cadastro (não aparecem): "
                    f"{lista_curta(ab.sem_cadastro)}.",
                )
            )

    if ab is not None:
        saude += _viaturas(ab, catalogos)
        saude += _oficina(catalogos)
        saude += _epis(catalogos)

    if not CentroCusto.objects.exists():
        saude.append(
            ItemSaude(
                "aviso",
                "Nenhum centro de custo cadastrado: não é possível confirmar atendimentos nem "
                "registrar saídas.",
            )
        )
    else:
        saude += _destinos_e_excecoes(ab, catalogos)
    return saude


def saude_do_catalogo(agora: datetime | None = None) -> list[ItemSaude]:
    agora = agora or timezone.now()
    total, ocultos = _cadastro()
    return [
        *(_importacao(tipo, agora) for tipo in _tipos()),
        *_demais(agora, catalogo_ab(timezone.localdate(agora)), total, ocultos),
    ]


# ---- página Catálogo ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Fonte:
    """Uma fonte de dados do SCPI (cadastro, estoque, saídas, de/para) e a sua última importação.
    `nivel` vai no selo: "ok", "aviso", "erro" ou "andamento"."""

    tipo: str
    rotulo: str
    nivel: str
    selo: str
    ultima: Importacao | None
    quando: datetime | None = None
    ha_quanto: str = ""
    resumo: str = ""
    avisos: list[GrupoAvisos] = field(default_factory=list)
    erro: str = ""  # resumo do erro da última importação, se ela falhou
    complemento: str = ""  # o que vem depois do número principal: ocultos, período das saídas

    @property
    def resumo_completo(self) -> str:
        return f"{self.resumo}, {self.complemento}" if self.complemento else self.resumo


def _resumo_da_fonte(tipo: str, ultima: Importacao, total: int, ocultos: int) -> tuple[str, str]:
    """O número principal e o complemento (que a página mostra mais apagado)."""
    if tipo == Importacao.Tipo.CADASTRO:
        return f"{numero(total)} materiais", f"{numero(ocultos)} ocultos"
    if tipo == Importacao.Tipo.ESTOQUE:
        return f"{numero(ultima.linhas)} saldos", ""
    if tipo == Importacao.Tipo.SAIDAS:
        periodo = (
            f"de {ultima.periodo_de:%d/%m/%Y} a {ultima.periodo_ate:%d/%m/%Y}"
            if ultima.periodo_de and ultima.periodo_ate
            else ""
        )
        return f"{numero(ultima.linhas)} saídas", periodo
    return f"{numero(ultima.linhas)} pares", ""


def _fonte(tipo: Importacao.Tipo, agora: datetime, total: int, ocultos: int) -> Fonte:
    ultima = Importacao.objects.filter(tipo=tipo).order_by("-inicio").first()
    if ultima is None:
        return Fonte(tipo, tipo.label, "erro", "Sem dados", None, resumo="Nenhuma importação ainda")
    sucesso = (
        ultima
        if ultima.situacao == Importacao.Situacao.SUCESSO
        else Importacao.objects.filter(tipo=tipo, situacao=Importacao.Situacao.SUCESSO)
        .order_by("-inicio")
        .first()
    )
    if ultima.situacao == Importacao.Situacao.ANDAMENTO and not ultima.esta_interrompida(agora):
        nivel, selo = "andamento", "Em andamento"
        resumo = f"Começou às {timezone.localtime(ultima.inicio):%H:%M}"
        return Fonte(tipo, tipo.label, nivel, selo, ultima, ultima.inicio, resumo=resumo)
    if ultima.situacao == Importacao.Situacao.FALHA:
        nivel, selo = "erro", "Falhou"
    elif ultima.situacao == Importacao.Situacao.ANDAMENTO:
        nivel, selo = "aviso", "Interrompida"
    elif ultima.avisos:
        nivel, selo = "aviso", "Com avisos"
    else:
        nivel, selo = "ok", "Em dia"
    # O que vale é a última carga bem-sucedida: uma falha não apaga os dados anteriores.
    base = sucesso or ultima
    quando = base.fim or base.inicio
    resumo, complemento = (
        _resumo_da_fonte(tipo, sucesso, total, ocultos)
        if sucesso
        else ("Nenhuma importação concluída", "")
    )
    return Fonte(
        tipo,
        tipo.label,
        nivel,
        selo,
        ultima,
        quando if sucesso else None,
        ha_quanto(quando, agora) if sucesso else "",
        resumo,
        agrupar_avisos(ultima.avisos) if ultima.situacao == Importacao.Situacao.SUCESSO else [],
        resumo_do_erro(ultima.erro) if ultima.situacao == Importacao.Situacao.FALHA else "",
        complemento,
    )


def _lista_e(nomes: list[str]) -> str:
    return nomes[0] if len(nomes) == 1 else f"{', '.join(nomes[:-1])} e {nomes[-1]}"


@dataclass(frozen=True)
class CartaoFormulario:
    """Um cartão da visão geral de Automações: o que um formulário público oferece. `total` é
    None quando o formulário está indisponível (o AB sem saldo importado)."""

    titulo: str
    total: int | None
    singular: str
    plural: str
    dica: str = ""

    @property
    def unidade(self) -> str:
        return self.singular if self.total == 1 else self.plural


@dataclass(frozen=True)
class Situacao:
    fontes: list[Fonte]
    avisos: list[ItemSaude]  # o que não é de uma importação e precisa de atenção
    limpeza: int
    ab: CatalogoAB | None
    ab_oferecidos: int = 0  # o que o formulário AB oferece de fato (regra mais exceções)
    viaturas: int = 0  # peças visíveis na lista do formulário de viaturas (spec 006)
    oficina: int = 0  # materiais do formulário da oficina mecânica (spec 007)
    epis: int = 0  # materiais do formulário de EPIs (spec 008)

    @property
    def cartoes(self) -> list[CartaoFormulario]:
        """Um cartão por formulário público, na ordem da visão geral. Formulário novo é uma linha
        aqui (e o campo com o número)."""
        if self.ab is None:
            ab = CartaoFormulario(
                "Formulário de ferramentas, peças e materiais",
                None,
                "item",
                "itens",
                "Falta importar o saldo de estoque.",
            )
        else:
            ab = CartaoFormulario(
                "Formulário de ferramentas, peças e materiais",
                self.ab_oferecidos,
                "item",
                "itens",
                f"Pela regra, de {numero(self.ab.codigos)} códigos com saída no SCPI: "
                f"{numero(self.ab.na_limpeza)} já estão no formulário de limpeza e "
                f"{numero(self.ab.ocultos)} estão ocultos ou em grupo oculto.",
            )
        return [
            CartaoFormulario(
                "Formulário de limpeza, copa e escritório", self.limpeza, "item", "itens"
            ),
            ab,
            CartaoFormulario(
                "Formulário de reposição de peças das viaturas",
                self.viaturas,
                "peça",
                "peças",
                "Da lista de peças; o resto do catálogo AB entra pela busca.",
            ),
            CartaoFormulario(
                "Formulário da oficina mecânica",
                self.oficina,
                "material",
                "materiais",
                "Dos grupos da oficina e dos materiais acrescentados na página Formulários.",
            ),
            CartaoFormulario(
                "Formulário de EPIs",
                self.epis,
                "material",
                "materiais",
                "Dos grupos de EPIs e dos materiais acrescentados na página Formulários.",
            ),
        ]

    @property
    def tem_avisos(self) -> bool:
        return bool(self.avisos) or any(f.avisos for f in self.fontes)

    @property
    def em_andamento(self) -> Fonte | None:
        return next((f for f in self.fontes if f.nivel == "andamento"), None)

    @property
    def resumo(self) -> str:
        """A resposta a "está tudo em dia?", numa frase."""
        andamento = self.em_andamento
        if andamento:
            desde = timezone.localtime(andamento.quando)
            return f"{andamento.rotulo}: importação em andamento desde {desde:%H:%M}."
        com_erro = [f.rotulo for f in self.fontes if f.nivel == "erro"]
        if com_erro:
            return f"Precisa de atenção: {_lista_e(com_erro)}."
        conferir = sum(1 for f in self.fontes if f.nivel == "aviso") + len(self.avisos)
        if conferir:
            pontos = "1 ponto" if conferir == 1 else f"{conferir} pontos"
            return f"Dados importados, com {pontos} para conferir."
        return "Tudo em dia."


def situacao_do_catalogo(agora: datetime | None = None) -> Situacao:
    agora = agora or timezone.now()
    total, ocultos = _cadastro()
    ab = catalogo_ab(timezone.localdate(agora))
    catalogos = _Catalogos(ab)
    return Situacao(
        fontes=[_fonte(tipo, agora, total, ocultos) for tipo in _tipos()],
        avisos=[i for i in _demais(agora, ab, total, ocultos, catalogos) if i.nivel != "ok"],
        limpeza=len(catalogos.limpeza),
        ab=ab,
        ab_oferecidos=len(catalogos.ab_efetivo),
        viaturas=len(catalogos.lista_viaturas),
        oficina=len(catalogos.oficina),
        epis=len(catalogos.epis),
    )
