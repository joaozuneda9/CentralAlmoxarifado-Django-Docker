"""Catálogo do formulário da oficina mecânica (spec 007, FR-003, FR-005, FR-012, FR-012a; research
R4): os materiais visíveis dos grupos da oficina e os materiais avulsos, uma vez cada."""

import pytest

from catalogo.catalogos import catalogo_oficina, formulario_oficina, grupos_oficina
from catalogo.models import ExcecaoMaterial, Formulario, Material, Opcao
from tests.config_cenario import excecao
from tests.oficina_cenario import FILTRO, FITA, OLEO, PNEU, montar_oficina

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cenario():
    montar_oficina()


def codigos():
    return [i.codigo for i in formulario_oficina() or []]


def test_grupos_e_avulsos_pelo_nome():
    assert codigos() == [FILTRO, OLEO, PNEU]  # FILTRO…, ÓLEO…, PNEU…: pelo nome


def test_o_grupo_e_comparado_sem_acento_maiusculas_e_espacos():
    assert grupos_oficina() == {"AUTOPECAS"}
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_OFICINA).update(valor="  auto   peças ")
    assert FILTRO in codigos()


def test_outro_grupo_fica_de_fora():
    assert FITA not in codigos()
    assert "000.000.900" not in codigos()  # do GERAL, sem ser avulso


def test_avulso_que_tambem_e_do_grupo_aparece_uma_vez():
    excecao(Formulario.OFICINA, Material.objects.get(codigo=FILTRO), True)
    assert codigos().count(FILTRO) == 1


def test_retirar_o_avulso_nao_tira_o_material_do_grupo():
    excecao(Formulario.OFICINA, Material.objects.get(codigo=FILTRO), True)
    ExcecaoMaterial.objects.filter(formulario=Formulario.OFICINA, material__codigo=FILTRO).delete()
    assert FILTRO in codigos()


def test_oculto_nao_aparece():
    Material.objects.filter(codigo__in=[FILTRO, OLEO]).update(oculto=True)
    assert codigos() == [PNEU]


def test_sem_estoque_e_duplicado_aparecem():
    Material.objects.filter(codigo=FILTRO).update(duplicado=True)
    itens = {i.codigo: i for i in formulario_oficina()}
    assert itens[PNEU].disponivel == 0
    assert itens[FILTRO].duplicado


def test_unidade_e_fracao_sao_as_do_scpi():
    itens = {i.codigo: i for i in formulario_oficina()}
    assert (itens[OLEO].unidade, itens[OLEO].fracionavel) == ("LT", True)
    assert (itens[FILTRO].unidade, itens[FILTRO].fracionavel) == ("UN", False)


def test_sem_escolha_o_formulario_fica_indisponivel():
    assert formulario_oficina()
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_OFICINA).delete()
    ExcecaoMaterial.objects.all().delete()
    assert catalogo_oficina() == [] and formulario_oficina() is None


def test_sem_saldo_importado_o_formulario_fica_indisponivel():
    Material.objects.update(estoque_em=None)
    assert formulario_oficina() is None


def test_grupo_desativado_nao_conta():
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_OFICINA).update(ativo=False)
    assert codigos() == [OLEO]
