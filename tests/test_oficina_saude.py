"""Saúde do catálogo para o formulário da oficina mecânica (spec 007, FR-005, FR-013): quanto ele
oferece, por que está indisponível, os grupos sem material, os avulsos ocultos e a falta do centro
da oficina; e a contagem na visão geral de Automações."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalogo.models import CentroCusto, ExcecaoMaterial, Material, Opcao
from catalogo.saude import ItemSaude, saude_do_catalogo, situacao_do_catalogo
from tests.oficina_cenario import OFICINA, OLEO, montar_oficina

pytestmark = pytest.mark.django_db

FORMULARIO = "Formulário da oficina mecânica"


@pytest.fixture(autouse=True)
def cenario():
    montar_oficina()


def itens_de(prefixo):
    return [i for i in saude_do_catalogo() if i.texto.startswith(prefixo)]


def texto_de(prefixo):
    (item,) = itens_de(prefixo)
    return item


def test_disponivel_conta_os_materiais():
    assert texto_de(FORMULARIO) == ItemSaude("ok", f"{FORMULARIO}: 3 materiais.")
    assert situacao_do_catalogo().oficina == 3


def test_cartoes_da_visao_geral_seguem_os_formularios():
    """Um cartão por formulário público; os avulsos da oficina e dos EPIs são acrescentados na
    página Formulários (spec 009), não mais num cadastro do admin."""
    cartoes = {c.titulo: c for c in situacao_do_catalogo().cartoes}
    assert len(cartoes) == 5
    oficina = cartoes[FORMULARIO]
    assert (oficina.total, oficina.unidade) == (3, "materiais")
    for titulo in (FORMULARIO, "Formulário de EPIs"):
        assert "página Formulários" in cartoes[titulo].dica
        assert "Cadastros" not in cartoes[titulo].dica


def test_sem_destino_fica_indisponivel():
    CentroCusto.objects.all().delete()
    assert texto_de(FORMULARIO) == ItemSaude(
        "erro",
        f"{FORMULARIO}: nenhum destino (nem o centro OFICINA MECÂNICA nem centro com placa); o "
        "formulário fica indisponível.",
    )


def test_sem_material_fica_indisponivel():
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_OFICINA).delete()
    ExcecaoMaterial.objects.all().delete()
    assert texto_de(FORMULARIO) == ItemSaude(
        "erro",
        f"{FORMULARIO}: nenhum material nos grupos nem entre os materiais da oficina; o "
        "formulário fica indisponível.",
    )


def test_grupo_sem_material_visivel_e_aviso():
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_OFICINA, valor="PNEUS IMPORTADOS")
    assert texto_de("Grupos da oficina sem material") == ItemSaude(
        "aviso", "Grupos da oficina sem material visível: PNEUS IMPORTADOS."
    )


def test_avulso_oculto_e_aviso():
    Material.objects.filter(codigo=OLEO).update(oculto=True)
    assert texto_de("Materiais da oficina ocultos") == ItemSaude(
        "aviso", f"Materiais da oficina ocultos no SCPI (não aparecem): {OLEO}."
    )


def test_sem_o_centro_da_oficina_so_as_viaturas_e_aviso():
    CentroCusto.objects.filter(descricao=OFICINA).delete()
    assert texto_de(f"{FORMULARIO}: centro") == ItemSaude(
        "aviso",
        f"{FORMULARIO}: centro OFICINA MECÂNICA não está habilitado como destino (ou não está "
        "cadastrado); só as viaturas são oferecidas.",
    )


def test_sem_o_centro_e_sem_material_mostra_as_duas_pendencias():
    CentroCusto.objects.filter(descricao=OFICINA).delete()
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_OFICINA).delete()
    ExcecaoMaterial.objects.all().delete()
    assert texto_de(f"{FORMULARIO}: nenhum material").nivel == "erro"
    assert texto_de(f"{FORMULARIO}: centro").nivel == "aviso"


def test_sem_saldo_importado_nada_da_oficina():
    Material.objects.update(estoque_em=None)
    assert not itens_de(FORMULARIO) and not itens_de("Grupos da oficina")


def test_a_visao_geral_mostra_a_contagem(client):
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    html = client.get(reverse("automacoes:pagina")).text
    assert FORMULARIO in html and "3 materiais" in html
