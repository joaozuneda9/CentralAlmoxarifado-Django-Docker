"""Modelos do formulário da oficina mecânica (spec 007): os materiais avulsos da oficina, a lista
de grupos e a origem nova do pedido."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from catalogo.models import Material, MaterialOficina, Opcao
from pedidos.models import Pedido
from pedidos.regras import CENTRO_OFICINA, OFICINA, resolver_centro_custo

pytestmark = pytest.mark.django_db


def material(codigo, nome):
    return Material.objects.create(codigo=codigo, nome=nome, unidade="UN", estoque=Decimal(5))


def test_um_material_entra_uma_vez_so_entre_os_da_oficina():
    oleo = material("999.001.010", "ÓLEO 15W40")
    MaterialOficina.objects.create(material=oleo)
    with pytest.raises(IntegrityError), transaction.atomic():
        MaterialOficina.objects.create(material=oleo)


def test_material_da_oficina_nao_pode_ser_apagado():
    oleo = material("999.001.010", "ÓLEO 15W40")
    MaterialOficina.objects.create(material=oleo)
    with pytest.raises(ProtectedError):
        oleo.delete()


def test_os_materiais_da_oficina_seguem_o_nome():
    pneu = MaterialOficina.objects.create(material=material("1", "PNEU"))
    filtro = MaterialOficina.objects.create(material=material("2", "FILTRO"))
    assert list(MaterialOficina.objects.all()) == [filtro, pneu]
    assert str(filtro) == str(filtro.material)


def test_a_lista_de_grupos_da_oficina_existe():
    assert Opcao.Lista.GRUPO_OFICINA.label == "Grupos (oficina)"
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_OFICINA, valor="AUTO PECAS")
    assert Opcao.valores(Opcao.Lista.GRUPO_OFICINA) == ["AUTO PECAS"]


def test_a_origem_da_oficina():
    assert Pedido.Origem(OFICINA).label == "Oficina mecânica"


def test_placa_sem_centro_proprio_continua_indo_para_a_oficina():
    from pedidos.regras import Centro

    resolvido = resolver_centro_custo("", "QQQ1Q11", [Centro(CENTRO_OFICINA, "20")])
    assert (resolvido.codigo, resolvido.descricao) == ("20", CENTRO_OFICINA)
