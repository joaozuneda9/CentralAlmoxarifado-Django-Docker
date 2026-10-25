"""A regra de destinos e de materiais dos formulários **antes da spec 009**, congelada.

Não editar: é a referência de SC-001 (os formulários oferecem o mesmo conjunto antes e depois da
configuração) e da verificação da migração. As funções são cópias de `catalogo/catalogos.py` e de
`pedidos/servicos.py` no commit anterior à configuração por formulário, com os mesmos nomes.
"""

from django.db.models import Q

from catalogo.catalogos import _grupo, _item, grupos_epis, grupos_oficina, unidades_fracionaveis
from catalogo.models import CentroCusto, Material
from pedidos.regras import CENTRO_OFICINA, Centro, norm_u


def centros() -> list[Centro]:
    """Todas as linhas do cadastro (limpeza, AB e EPIs)."""
    return [Centro(c.descricao, c.codigo, c.placa or "") for c in CentroCusto.objects.all()]


def centros_equipe_manutencao() -> list[Centro]:
    """Viaturas: os centros com alguma linha marcada como de equipe, um por descrição, sem placa."""
    centros_: dict[str, Centro] = {}
    for c in CentroCusto.objects.filter(equipe_manutencao=True).order_by("descricao", "codigo"):
        centros_.setdefault(c.descricao, Centro(c.descricao, c.codigo))
    return list(centros_.values())


def centros_oficina() -> list[Centro]:
    """Oficina: o centro OFICINA MECÂNICA (a linha sem placa) e cada viatura (centro com placa)."""
    oficina = [
        Centro(c.descricao, c.codigo)
        for c in CentroCusto.objects.filter(placa__isnull=True).order_by("codigo")
        if norm_u(c.descricao) == norm_u(CENTRO_OFICINA)
    ][:1]
    viaturas = [
        Centro(c.descricao, c.codigo, c.placa, so_com_placa=True)
        for c in CentroCusto.objects.filter(placa__isnull=False).order_by("descricao", "placa")
    ]
    return oficina + viaturas


def catalogo_oficina() -> list:
    """Oficina: os grupos escolhidos e os avulsos de `MaterialOficina`, pelo nome."""
    grupos = grupos_oficina()
    visiveis = Material.objects.filter(oculto=False)
    casados = [
        g for g in visiveis.values_list("grupo", flat=True).distinct() if _grupo(g) in grupos
    ]
    materiais = visiveis.filter(Q(grupo__in=casados) | Q(material_oficina__isnull=False))
    fracionaveis = unidades_fracionaveis()
    return [_item(m, fracionaveis) for m in materiais.distinct().order_by("nome", "codigo")]


def catalogo_epis() -> list:
    """EPIs: os grupos escolhidos e os avulsos de `MaterialEpi`, pelo nome."""
    grupos = grupos_epis()
    visiveis = Material.objects.filter(oculto=False)
    casados = [
        g for g in visiveis.values_list("grupo", flat=True).distinct() if _grupo(g) in grupos
    ]
    materiais = visiveis.filter(Q(grupo__in=casados) | Q(material_epi__isnull=False))
    fracionaveis = unidades_fracionaveis()
    return [_item(m, fracionaveis) for m in materiais.distinct().order_by("nome", "codigo")]
