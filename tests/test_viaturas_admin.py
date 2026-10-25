"""Manutenção da lista de peças no admin (spec 006, US3, FR-011, SC-003): vale no próximo acesso ao
formulário, sem nova publicação. A marca dos centros saiu do admin na spec 009."""

import re

import pytest
from django.urls import reverse

from catalogo.models import Material, PecaViatura
from tests.viaturas_cenario import FITA, ISOLANTE, TUBO, montar_viaturas

pytestmark = pytest.mark.django_db

CARRINHO = reverse("pedidos:carrinho", args=["viaturas"])


@pytest.fixture(autouse=True)
def cenario():
    montar_viaturas()


def nomes_da_folha(client):
    return re.findall(r"<strong>([^<]+)</strong>", client.post(CARRINHO, {"folha_abrir": "1"}).text)


def test_a_lista_no_admin(admin_client):
    url = reverse("admin:catalogo_pecaviatura_changelist")
    html = admin_client.get(url).text
    assert "Tubo PVC 3/4 Soldável Marrom (metro)" in html and 'name="form-0-ordem"' in html
    nova = admin_client.post(
        reverse("admin:catalogo_pecaviatura_add"),
        {"material": Material.objects.get(codigo=ISOLANTE).pk, "nome_exibido": "", "ordem": 9},
    )
    assert (
        nova.status_code == 302 and PecaViatura.objects.filter(material__codigo=ISOLANTE).exists()
    )
    repetida = admin_client.post(
        reverse("admin:catalogo_pecaviatura_add"),
        {"material": Material.objects.get(codigo=FITA).pk, "nome_exibido": "", "ordem": 1},
    )
    assert repetida.status_code == 200 and "já existe" in repetida.text


def test_incluir_retirar_e_reordenar_valem_no_proximo_acesso(client):
    assert nomes_da_folha(client)[0] == "Tubo PVC 3/4 Soldável Marrom (metro)"
    PecaViatura.objects.create(material=Material.objects.get(codigo=ISOLANTE), ordem=0)
    PecaViatura.objects.filter(material__codigo=TUBO).delete()
    PecaViatura.objects.filter(material__codigo=FITA).update(ordem=99)
    nomes = nomes_da_folha(client)
    assert nomes[0] == "FITA ISOLANTE" and nomes[-1] == "FITA VEDA ROSCA"
    assert "Tubo PVC 3/4 Soldável Marrom (metro)" not in nomes


def test_a_marca_antiga_dos_centros_saiu_do_admin(admin_client):
    """Spec 009: os destinos das viaturas se definem na página Formulários; a marca de equipe de
    manutenção deixou de valer e não aparece mais, nem como coluna nem como filtro."""
    html = admin_client.get(reverse("admin:catalogo_centrocusto_changelist")).text
    assert "Equipe de manutenção" not in html and "equipe_manutencao" not in html
    assert "ativo" in html  # o estado global do centro, no lugar
