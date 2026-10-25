"""Catálogo do formulário de EPIs (spec 008, FR-004, FR-005, FR-007, FR-029; research R7): os
materiais visíveis dos grupos de EPIs e os materiais avulsos, uma vez cada."""

import pytest

from catalogo.catalogos import catalogo_epis, formulario_epis, grupos_epis
from catalogo.models import ExcecaoMaterial, Formulario, Material, Opcao
from tests.epis_cenario import CAPACETE, FITA, LUVA, OCULOS, PROTETOR, montar_epis

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


def codigos():
    return [i.codigo for i in formulario_epis() or []]


def test_grupos_e_avulsos_pelo_nome():
    # CAPACETE…, LUVA…, ÓCULOS…, PROTETOR…: pelo nome
    assert codigos() == [CAPACETE, LUVA, OCULOS, PROTETOR]


def test_o_grupo_e_comparado_sem_acento_maiusculas_e_espacos():
    assert grupos_epis() == {"MATERIALDESEGURANCAEEPI"}
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_EPI).update(
        valor="  material  de segurança e epi "
    )
    assert LUVA in codigos()


def test_outro_grupo_fica_de_fora():
    assert FITA not in codigos()
    assert "000.000.900" not in codigos()  # do GERAL, sem ser avulso


def test_o_catalogo_antigo_de_epi_do_cenario_nao_entra_sem_ser_escolhido():
    # BOTINA e LUVA NITRÍLICA estão no grupo `EPI` do cenário geral, que não é o grupo escolhido.
    assert "013.006.001" not in codigos() and "013.005.007" not in codigos()


def test_avulso_que_tambem_e_do_grupo_aparece_uma_vez():
    ExcecaoMaterial.objects.create(
        material=Material.objects.get(codigo=LUVA), formulario=Formulario.EPIS, habilitado=True
    )
    assert codigos().count(LUVA) == 1


def test_retirar_o_avulso_nao_tira_o_material_do_grupo():
    ExcecaoMaterial.objects.create(
        material=Material.objects.get(codigo=LUVA), formulario=Formulario.EPIS, habilitado=True
    )
    ExcecaoMaterial.objects.filter(formulario=Formulario.EPIS, material__codigo=LUVA).delete()
    assert LUVA in codigos()


def test_retirar_o_avulso_de_outro_grupo_tira_o_material():
    ExcecaoMaterial.objects.filter(formulario=Formulario.EPIS, material__codigo=OCULOS).delete()
    assert OCULOS not in codigos()


def test_oculto_nao_aparece():
    Material.objects.filter(codigo__in=[LUVA, OCULOS]).update(oculto=True)
    assert codigos() == [CAPACETE, PROTETOR]


def test_sem_estoque_e_duplicado_aparecem_bloqueados():
    Material.objects.filter(codigo=LUVA).update(duplicado=True)
    itens = {i.codigo: i for i in formulario_epis()}
    assert itens[PROTETOR].disponivel == 0
    assert itens[LUVA].duplicado


def test_unidade_e_fracao_sao_as_do_scpi():
    itens = {i.codigo: i for i in formulario_epis()}
    assert (itens[LUVA].unidade, itens[LUVA].fracionavel) == ("UN", False)


def test_sem_escolha_o_formulario_fica_indisponivel():
    assert formulario_epis()
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_EPI).delete()
    ExcecaoMaterial.objects.all().delete()
    assert catalogo_epis() == [] and formulario_epis() is None


def test_sem_saldo_importado_o_formulario_fica_indisponivel():
    Material.objects.update(estoque_em=None)
    assert formulario_epis() is None


def test_grupo_desativado_nao_conta():
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_EPI).update(ativo=False)
    assert codigos() == [OCULOS]


def test_a_escolha_da_oficina_nao_muda_a_dos_epis():
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_OFICINA, valor="ALMOXARIFADO")
    assert codigos() == [CAPACETE, LUVA, OCULOS, PROTETOR]
