"""Modelos da reposição de peças das viaturas (spec 006): a lista de peças, a marca dos centros
de equipe de manutenção e o número da ocorrência do pedido."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from catalogo.models import CentroCusto, Material, PecaViatura
from pedidos.models import Pedido
from pedidos.regras import VIATURAS
from tests.cenario import criar_pedido

pytestmark = pytest.mark.django_db


def material(codigo, nome):
    return Material.objects.create(codigo=codigo, nome=nome, unidade="UN", estoque=Decimal(5))


def test_um_material_entra_uma_vez_so_na_lista():
    luva = material("016.001.001", "LUVA 3/4")
    PecaViatura.objects.create(material=luva)
    with pytest.raises(IntegrityError), transaction.atomic():
        PecaViatura.objects.create(material=luva, nome_exibido="Luva 3/4 soldável")


def test_material_da_lista_nao_pode_ser_apagado():
    luva = material("016.001.001", "LUVA 3/4")
    PecaViatura.objects.create(material=luva)
    with pytest.raises(ProtectedError):
        luva.delete()


def test_a_lista_segue_a_ordem_e_depois_o_nome():
    tee = PecaViatura.objects.create(material=material("1", "TEE 3/4"), ordem=2)
    capa = PecaViatura.objects.create(material=material("2", "CAPA 3/4"), ordem=2)
    abracadeira = PecaViatura.objects.create(material=material("3", "ABRAÇADEIRA"), ordem=1)
    assert list(PecaViatura.objects.all()) == [abracadeira, capa, tee]


def test_o_nome_da_peca_e_o_exibido_ou_o_do_material():
    luva = PecaViatura.objects.create(material=material("1", "LUVA PVC 3/4"))
    assert str(luva) == str(luva.material)
    luva.nome_exibido = "Luva 3/4 soldável PVC"
    assert str(luva) == "Luva 3/4 soldável PVC"


def test_centro_de_custo_nasce_fora_das_equipes_de_manutencao():
    assert CentroCusto.objects.create(descricao="ETA I", codigo="12").equipe_manutencao is False


def test_origem_e_ocorrencia_do_pedido():
    assert Pedido.Origem(VIATURAS).label == "Reposição de peças das viaturas"
    assert criar_pedido().ocorrencia == ""
