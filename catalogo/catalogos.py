"""Catálogos de materiais dos formulários, montados do banco a cada consulta (sem cache).

Traduz `montarCatalogos_` do `Catalogo.gs`: limpeza vem do `ItemLimpeza`; AB, das saídas do
SCPI no período da curva ABC, consolidadas pelo de/para e ordenadas por número de ocorrências; a
saída avulsa, de todo material não oculto e com saldo positivo; o de viaturas, da `PecaViatura`
seguida do catálogo AB (spec 006); o da oficina mecânica, dos grupos da lista `GRUPO_OFICINA` e dos
`MaterialOficina` (spec 007). Em todos, o material `duplicado`
aparece (bloqueado pelo formulário).
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.utils import timezone

from catalogo.consultas_curva import consolidado
from catalogo.curva import periodo
from catalogo.models import (
    CentroCusto,
    ConfiguracaoCurva,
    ExcecaoMaterial,
    ItemLimpeza,
    Material,
    Opcao,
    PecaViatura,
)
from pedidos.regras import (
    AB,
    EPIS,
    LIMPEZA,
    OFICINA,
    VIATURAS,
    Centro,
    estoque_inteiro,
    norm_u,
)

# Usados quando a lista GRUPO_OCULTO_AB está vazia (como `GRUPOS_OCULTOS_PADRAO_`).
GRUPOS_OCULTOS_PADRAO = (
    "GERAL",
    "MATERIAL DE EXPEDIENTE ( ESCRITORIO)",
    "MATERIAL DE CONSUMO",
)


@dataclass(frozen=True)
class ItemCatalogo:
    codigo: str
    nome: str
    unidade: str
    categoria: str
    grupo: str
    subgrupo: str
    estoque: Decimal
    disponivel: int
    duplicado: bool
    # A unidade do SCPI (não a exibida) admite fração: decide a regra de quantidade do formulário
    # público. O padrão é o lado seguro, só inteiro.
    fracionavel: bool = False


@dataclass
class CatalogoAB:
    itens: list[ItemCatalogo] = field(default_factory=list)
    codigos: int = 0
    na_limpeza: int = 0
    ocultos: int = 0
    sem_cadastro: list[str] = field(default_factory=list)


def _grupo(texto: str) -> str:
    return norm_u(texto).replace(" ", "")


def grupos_ocultos_ab() -> set[str]:
    """Grupos fora do formulário AB, normalizados (sem acento, maiúsculas, sem espaços)."""
    valores = Opcao.valores(Opcao.Lista.GRUPO_OCULTO_AB) or GRUPOS_OCULTOS_PADRAO
    return {_grupo(v) for v in valores}


def unidades_fracionaveis() -> set[str]:
    """As unidades do SCPI em que a quantidade pode ter fração (lista mantida no admin),
    normalizadas como `norm_u`. Lista vazia: nenhuma, e todo material aceita só inteiro."""
    return {norm_u(v) for v in Opcao.valores(Opcao.Lista.UNIDADE_FRACIONAVEL)}


def _item(material: Material, fracionaveis: set[str], **outros) -> ItemCatalogo:
    campos = {
        "codigo": material.codigo,
        "nome": material.nome,
        "unidade": material.unidade,
        "categoria": "",
        "grupo": material.grupo,
        "subgrupo": material.subgrupo,
        "estoque": material.estoque,
        "disponivel": estoque_inteiro(material.estoque),
        "duplicado": material.duplicado,
        # Pela unidade do cadastro do SCPI, antes de `outros` trocar o texto exibido.
        "fracionavel": norm_u(material.unidade) in fracionaveis,
    }
    campos.update(outros)
    return ItemCatalogo(**campos)


def aplicar_excecoes(
    origem: str, base: list[ItemCatalogo], *, ordem_do_banco: bool = False
) -> list[ItemCatalogo]:
    """A base (a regra de origem do formulário) sem os materiais que o administrador retirou e com
    os que acrescentou (spec 009): duas consultas pequenas, as exceções do formulário e os
    materiais acrescentados.

    O material oculto no cadastro nunca entra (o cadastro vence a exceção) e o que a base já traz
    não se repete. Os acrescentados vêm ao fim, em ordem alfabética por nome e código; nos
    formulários de catálogo alfabético por inteiro (`ordem_do_banco`: oficina e EPIs), a lista toda
    sai na ordem do banco, com o acrescentado no lugar dele."""
    excecoes = list(
        ExcecaoMaterial.objects.filter(formulario=origem).values_list(
            "material__codigo", "habilitado"
        )
    )
    if not excecoes:
        return base
    retirados = {norm_u(codigo) for codigo, habilitado in excecoes if not habilitado}
    itens = [i for i in base if norm_u(i.codigo) not in retirados]
    presentes = {norm_u(i.codigo) for i in itens}
    acrescentar = [c for c, habilitado in excecoes if habilitado and norm_u(c) not in presentes]
    novos = Material.objects.filter(codigo__in=acrescentar, oculto=False)
    if ordem_do_banco:
        codigos = [i.codigo for i in itens] + [m.codigo for m in novos]
        fracionaveis = unidades_fracionaveis()
        todos = Material.objects.filter(codigo__in=codigos, oculto=False).order_by("nome", "codigo")
        return [_item(m, fracionaveis) for m in todos]
    fracionaveis = unidades_fracionaveis()
    return itens + [_item(m, fracionaveis) for m in novos.order_by("nome", "codigo")]


def regra_de_origem(
    origem: str, ab: CatalogoAB | None = None, viaturas: list[ItemCatalogo] | None = None
) -> list[ItemCatalogo]:
    """Os itens que a regra de origem do formulário traz hoje, **sem** as exceções (e sem o corte
    "indisponível" por saldo nunca importado): a base da disponibilidade efetiva. `ab` é o catálogo
    AB que o chamador já calculou (a conta pesada); sem ele, é calculado aqui. `viaturas`, do mesmo
    jeito, é a lista das viaturas (`catalogo_viaturas`) já calculada."""
    if origem == LIMPEZA:
        return catalogo_limpeza()
    if origem == AB:
        ab = ab if ab is not None else catalogo_ab()
        return ab.itens if ab is not None else []
    if origem == VIATURAS:
        return _base_viaturas(ab, viaturas)
    if origem == OFICINA:
        return catalogo_oficina()
    if origem == EPIS:
        return catalogo_epis()
    raise KeyError(origem)


def catalogo_efetivo(
    origem: str,
    ab: CatalogoAB | None = None,
    *,
    viaturas: list[ItemCatalogo] | None = None,
) -> list[ItemCatalogo]:
    """A disponibilidade efetiva do formulário (regra de origem mais exceções), sem o corte de
    "indisponível" por saldo nunca importado: o que a saúde e a tela de configuração contam. `ab`
    e `viaturas` reaproveitam o catálogo AB e a lista das viaturas já calculados pelo chamador."""
    return aplicar_excecoes(
        origem, regra_de_origem(origem, ab, viaturas), ordem_do_banco=origem in (OFICINA, EPIS)
    )


def catalogo_limpeza() -> list[ItemCatalogo]:
    """Itens do formulário de limpeza cujo material não está oculto; nome e unidade
    exibidos têm prioridade sobre o cadastro."""
    itens = ItemLimpeza.objects.select_related("material").filter(material__oculto=False)
    fracionaveis = unidades_fracionaveis()
    return [
        _item(
            i.material,
            fracionaveis,
            nome=i.nome_exibido or i.material.nome,
            unidade=i.unidade_exibida or i.material.unidade,
            categoria=i.categoria,
        )
        for i in itens
    ]


def saldo_importado() -> bool:
    """Se o saldo de estoque já foi importado do SCPI alguma vez (sem isso, todo material
    apareceria sem estoque)."""
    return Material.objects.filter(estoque_em__isnull=False).exists()


def catalogo_ab(hoje: date | None = None) -> CatalogoAB | None:
    """Itens do formulário AB, ou None se o saldo de estoque nunca foi importado.

    Um item por código canônico, na ordem das ocorrências consolidadas no período da curva ABC,
    com o saldo do canônico (é nele que a saída será lançada)."""
    if not saldo_importado():
        return None
    hoje = hoje or timezone.localdate()
    linhas, _ = consolidado(periodo(hoje, ConfiguracaoCurva.atual().janela_meses))
    ranking = [
        linha.canonico
        for linha in sorted(linhas, key=lambda linha: (-linha.ocorrencias, norm_u(linha.canonico)))
    ]
    materiais = {norm_u(m.codigo): m for m in Material.objects.filter(codigo__in=ranking)}
    na_limpeza = {
        norm_u(c)
        for c in ItemLimpeza.objects.filter(material__codigo__in=ranking).values_list(
            "material__codigo", flat=True
        )
    }
    ocultos = grupos_ocultos_ab()
    fracionaveis = unidades_fracionaveis()
    ab = CatalogoAB(codigos=len(ranking))
    for codigo in ranking:
        material = materiais.get(norm_u(codigo))
        if material is None:
            ab.sem_cadastro.append(codigo)
        elif norm_u(codigo) in na_limpeza:
            ab.na_limpeza += 1
        elif material.oculto or _grupo(material.grupo) in ocultos:
            ab.ocultos += 1
        else:
            ab.itens.append(_item(material, fracionaveis))
    return ab


def materiais_avulsa():
    """Materiais da saída avulsa: o cadastro com saldo positivo, menos os ocultos."""
    return Material.objects.filter(oculto=False, estoque__gt=0)


def catalogo_avulsa() -> list[ItemCatalogo]:
    """Itens da saída avulsa: o cadastro com saldo positivo, menos os ocultos (duplicado
    aparece bloqueado)."""
    fracionaveis = unidades_fracionaveis()
    return [_item(m, fracionaveis) for m in materiais_avulsa()]


def formulario_limpeza() -> list[ItemCatalogo] | None:
    """O catálogo do formulário de limpeza, ou None se ele está indisponível: o saldo nunca foi
    importado (o formulário limita pelo saldo) ou não há item algum (depois das exceções)."""
    if not saldo_importado():
        return None
    return aplicar_excecoes(LIMPEZA, catalogo_limpeza()) or None


def formulario_ab() -> list[ItemCatalogo] | None:
    """O catálogo do formulário AB, ou None se ele está indisponível: o saldo nunca foi importado
    ou nenhum material com saída entra no catálogo (depois das exceções)."""
    ab = catalogo_ab()
    if ab is None:
        return None
    return aplicar_excecoes(AB, ab.itens) or None


def formulario_avulsa() -> list[ItemCatalogo] | None:
    """O catálogo da saída avulsa, ou None se nenhum material tem saldo."""
    return catalogo_avulsa() or None


def catalogo_viaturas() -> list[ItemCatalogo]:
    """Peças da lista das viaturas (spec 006), na ordem da lista, sem as de material oculto; o
    nome exibido tem prioridade sobre o do cadastro, e a unidade é sempre a do SCPI."""
    pecas = PecaViatura.objects.select_related("material").filter(material__oculto=False)
    fracionaveis = unidades_fracionaveis()
    return [_item(p.material, fracionaveis, nome=p.nome_exibido or p.material.nome) for p in pecas]


def _base_viaturas(
    ab: CatalogoAB | None = None, viaturas: list[ItemCatalogo] | None = None
) -> list[ItemCatalogo]:
    """A regra de origem das viaturas: a lista e, depois, o catálogo AB sem repetir as peças da
    lista. `viaturas` é a lista já calculada pelo chamador (sem ela, é calculada aqui)."""
    lista = viaturas if viaturas is not None else catalogo_viaturas()
    na_lista = {norm_u(i.codigo) for i in lista}
    ab = ab if ab is not None else catalogo_ab()
    resto = [i for i in (ab.itens if ab is not None else []) if norm_u(i.codigo) not in na_lista]
    return lista + resto


def formulario_viaturas() -> list[ItemCatalogo] | None:
    """O catálogo do formulário de viaturas: a lista e, depois, o catálogo AB sem repetir as peças
    da lista, com as exceções; None se o saldo nunca foi importado ou não há nada a oferecer."""
    if not saldo_importado():
        return None
    return aplicar_excecoes(VIATURAS, _base_viaturas()) or None


def folha_viaturas() -> list[str]:
    """Os códigos da folha do formulário de viaturas: a lista visível, na ordem."""
    return [i.codigo for i in catalogo_viaturas()]


MODO_PADRAO = "padrao"
MODO_SEM_PLACA = "sem_placa"
MODO_OFICINA = "oficina"

# Como cada formulário apresenta o destino (característica do formulário, não configuração):
# limpeza, AB e EPIs oferecem a descrição e, para a linha com placa, "descrição — placa"; as
# viaturas só a descrição, uma por centro (a placa não importa); a oficina oferece a linha com
# placa só como "descrição — placa" e a linha sem placa como a descrição (spec 009, FR-007a).
MODO_DESTINO = {
    LIMPEZA: MODO_PADRAO,
    AB: MODO_PADRAO,
    EPIS: MODO_PADRAO,
    VIATURAS: MODO_SEM_PLACA,
    OFICINA: MODO_OFICINA,
}


def centros_do_formulario(origem: str) -> list[Centro]:
    """Os destinos do formulário: as linhas de centro ativas e habilitadas nele (página
    Formulários), apresentadas pelo modo do formulário. Lista vazia: formulário sem destino."""
    linhas = CentroCusto.objects.filter(ativo=True, formularios__formulario=origem)
    modo = MODO_DESTINO[origem]
    if modo == MODO_SEM_PLACA:
        centros: dict[str, Centro] = {}
        for c in linhas.order_by("descricao", "codigo"):
            centros.setdefault(c.descricao, Centro(c.descricao, c.codigo))
        return list(centros.values())
    if modo == MODO_OFICINA:
        sem_placa = [
            Centro(c.descricao, c.codigo)
            for c in linhas.filter(placa__isnull=True).order_by("descricao", "codigo")
        ]
        com_placa = [
            Centro(c.descricao, c.codigo, c.placa, so_com_placa=True)
            for c in linhas.filter(placa__isnull=False).order_by("descricao", "placa")
        ]
        return sem_placa + com_placa
    return [
        Centro(c.descricao, c.codigo, c.placa or "") for c in linhas.order_by("descricao", "placa")
    ]


def grupos_oficina() -> set[str]:
    """Os grupos do formulário da oficina mecânica (spec 007), normalizados como os ocultos do AB.
    Lista vazia: nenhum grupo (sem padrão)."""
    return {_grupo(v) for v in Opcao.valores(Opcao.Lista.GRUPO_OFICINA)}


def _materiais_dos_grupos(grupos: set[str]) -> list[ItemCatalogo]:
    """Os materiais visíveis dos grupos dados, pelo nome (regra de origem da oficina e dos EPIs)."""
    visiveis = Material.objects.filter(oculto=False)
    casados = [
        g for g in visiveis.values_list("grupo", flat=True).distinct() if _grupo(g) in grupos
    ]
    fracionaveis = unidades_fracionaveis()
    materiais = visiveis.filter(grupo__in=casados).order_by("nome", "codigo")
    return [_item(m, fracionaveis) for m in materiais]


def catalogo_oficina() -> list[ItemCatalogo]:
    """A regra de origem da oficina (spec 007): os materiais não ocultos dos grupos da lista
    `GRUPO_OFICINA`, pelo nome. Os avulsos são exceções da configuração (spec 009)."""
    return _materiais_dos_grupos(grupos_oficina())


def formulario_oficina() -> list[ItemCatalogo] | None:
    """O catálogo do formulário da oficina, ou None se ele está indisponível: o saldo nunca foi
    importado ou a oficina não tem material visível (depois das exceções)."""
    if not saldo_importado():
        return None
    return aplicar_excecoes(OFICINA, catalogo_oficina(), ordem_do_banco=True) or None


def grupos_epis() -> set[str]:
    """Os grupos do formulário de EPIs (spec 008), normalizados como os da oficina. Lista vazia:
    nenhum grupo (sem padrão)."""
    return {_grupo(v) for v in Opcao.valores(Opcao.Lista.GRUPO_EPI)}


def catalogo_epis() -> list[ItemCatalogo]:
    """A regra de origem dos EPIs (spec 008): os materiais não ocultos dos grupos da lista
    `GRUPO_EPI`, pelo nome. Os avulsos são exceções da configuração (spec 009)."""
    return _materiais_dos_grupos(grupos_epis())


def formulario_epis() -> list[ItemCatalogo] | None:
    """O catálogo do formulário de EPIs, ou None se ele está indisponível: o saldo nunca foi
    importado ou a escolha dos EPIs não tem material visível (depois das exceções)."""
    if not saldo_importado():
        return None
    return aplicar_excecoes(EPIS, catalogo_epis(), ordem_do_banco=True) or None
