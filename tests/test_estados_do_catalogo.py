"""Estados dos formulários públicos quando não há o que pedir (spec 005, US3, SC-003).

Indisponível (saldo nunca importado ou nenhum item no catálogo): o formulário bloqueia, com a mesma
mensagem nos dois. Sem estoque agora (há itens, todos com máximo pedível zero): o formulário abre
com um aviso no topo e a lista bloqueada.
"""

import pytest
from django.urls import reverse

from catalogo.models import ItemLimpeza, Material, SaidaSCPI
from tests.cenario import montar_cenario

pytestmark = pytest.mark.django_db

INDISPONIVEL = "Este formulário está indisponível no momento. Avise o almoxarifado."
SEM_ESTOQUE_AGORA = "Nenhum material deste formulário tem estoque agora."
FORMULARIOS = ["limpeza", "ab"]


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()


def abrir(client, fluxo):
    return client.get(reverse("pedidos:formulario", args=[fluxo])).text


def bloqueado(html):
    return INDISPONIVEL in html and 'name="token"' not in html


# --- indisponível ------------------------------------------------------------------------------


@pytest.mark.parametrize("fluxo", FORMULARIOS)
def test_saldo_nunca_importado_bloqueia_os_dois_formularios(client, fluxo):
    Material.objects.update(estoque_em=None)
    html = abrir(client, fluxo)
    assert bloqueado(html)
    assert "estoque ou catálogo" not in html  # a mesma mensagem nos dois
    assert SEM_ESTOQUE_AGORA not in html


def test_limpeza_sem_itens_bloqueia(client):
    ItemLimpeza.objects.all().delete()
    assert bloqueado(abrir(client, "limpeza"))


def test_ab_sem_saidas_na_janela_bloqueia_em_vez_de_abrir_vazio(client):
    SaidaSCPI.objects.all().delete()
    assert bloqueado(abrir(client, "ab"))


def test_ab_so_com_itens_filtrados_tambem_bloqueia(client):
    # Todos os materiais com saída ocultos no SCPI: nenhum item pedível no catálogo.
    Material.objects.update(oculto=True)
    assert bloqueado(abrir(client, "ab"))


# --- sem estoque agora -------------------------------------------------------------------------


@pytest.mark.parametrize("fluxo", FORMULARIOS)
def test_todos_sem_estoque_abre_com_aviso_e_itens_bloqueados(client, fluxo):
    Material.objects.update(estoque=0)
    html = abrir(client, fluxo)
    assert 'name="token"' in html and INDISPONIVEL not in html
    assert SEM_ESTOQUE_AGORA in html
    # O aviso fica no topo do formulário, antes dos passos.
    assert html.index(SEM_ESTOQUE_AGORA) < html.index('class="passo"')
    lista = client.get(reverse("pedidos:materiais", args=[fluxo]), {"q": ""}).text
    assert "Sem estoque" in lista
    assert "data-adicionar-abrir" not in lista  # nada pode ser adicionado


@pytest.mark.parametrize("fluxo", FORMULARIOS)
def test_com_um_item_com_estoque_o_aviso_some(client, fluxo):
    Material.objects.update(estoque=0)
    assert SEM_ESTOQUE_AGORA in abrir(client, fluxo)
    codigo = "023.001.002" if fluxo == "limpeza" else "016.005.010"
    Material.objects.filter(codigo=codigo).update(estoque=5)
    html = abrir(client, fluxo)
    assert SEM_ESTOQUE_AGORA not in html and 'name="token"' in html


def test_o_aviso_acompanha_o_formulario_devolvido_apos_uma_recusa(client):
    """O formulário reaberto por uma recusa (`de_volta`) também diz que nada tem estoque."""
    Material.objects.update(estoque=0)
    r = client.post(
        reverse("pedidos:formulario", args=["limpeza"]),
        {"token": "invalido", "solicitante": "Ana", "destino": "ETA II"},
        HTTP_HX_REQUEST="true",
    )
    assert SEM_ESTOQUE_AGORA in r.text


# --- bloqueio por cadastro duplicado -----------------------------------------------------------


@pytest.mark.parametrize("fluxo", FORMULARIOS)
def test_cadastro_duplicado_continua_bloqueado_com_o_motivo(client, fluxo):
    codigo, busca = ("023.001.002", "detergente") if fluxo == "limpeza" else ("016.005.010", "fita")
    Material.objects.filter(codigo=codigo).update(duplicado=True)
    html = client.get(reverse("pedidos:materiais", args=[fluxo]), {"q": busca}).text
    assert "Cadastro duplicado — avise o almoxarifado" in html
