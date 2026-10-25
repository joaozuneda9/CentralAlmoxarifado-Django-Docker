"""Saúde do catálogo para o formulário de EPIs (spec 008, FR-030): quanto ele oferece, por que
está indisponível, os grupos sem material e os avulsos ocultos; e a contagem em Automações."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalogo.models import ExcecaoMaterial, Material, Opcao
from catalogo.saude import ItemSaude, saude_do_catalogo, situacao_do_catalogo
from tests.epis_cenario import OCULOS, montar_epis

pytestmark = pytest.mark.django_db

FORMULARIO = "Formulário de EPIs"


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


def itens_de(prefixo):
    return [i for i in saude_do_catalogo() if i.texto.startswith(prefixo)]


def texto_de(prefixo):
    (item,) = itens_de(prefixo)
    return item


def test_disponivel_conta_os_materiais():
    assert texto_de(FORMULARIO) == ItemSaude("ok", f"{FORMULARIO}: 4 materiais.")
    assert situacao_do_catalogo().epis == 4


def test_um_so_material_fica_no_singular():
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_EPI).delete()
    assert texto_de(FORMULARIO) == ItemSaude("ok", f"{FORMULARIO}: 1 material.")


def test_sem_material_fica_indisponivel():
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_EPI).delete()
    ExcecaoMaterial.objects.all().delete()
    assert texto_de(FORMULARIO) == ItemSaude(
        "erro",
        f"{FORMULARIO}: nenhum material nos grupos nem entre os materiais de EPIs; o formulário "
        "fica indisponível.",
    )
    assert situacao_do_catalogo().epis == 0


def test_grupo_sem_material_visivel_e_aviso():
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_EPI, valor="CALÇADOS DE SEGURANÇA")
    assert texto_de("Grupos de EPIs sem material") == ItemSaude(
        "aviso", "Grupos de EPIs sem material visível: CALÇADOS DE SEGURANÇA."
    )


def test_avulso_oculto_e_aviso():
    Material.objects.filter(codigo=OCULOS).update(oculto=True)
    assert texto_de("Materiais de EPIs ocultos") == ItemSaude(
        "aviso", f"Materiais de EPIs ocultos no SCPI (não aparecem): {OCULOS}."
    )


def test_sem_saldo_importado_nada_dos_epis():
    Material.objects.update(estoque_em=None)
    assert not itens_de(FORMULARIO) and not itens_de("Grupos de EPIs")


def test_a_visao_geral_mostra_a_contagem(client):
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    html = client.get(reverse("automacoes:pagina")).text
    assert "Formulário de EPIs" in html and "4 materiais" in html
