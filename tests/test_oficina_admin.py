"""Manutenção da escolha da oficina no admin (spec 007, US3, FR-012, SC-004): a lista de grupos vale
no próximo acesso ao formulário, sem nova publicação. Os avulsos saíram do admin na spec 009."""

import pytest
from django.contrib import admin
from django.urls import NoReverseMatch, reverse

from catalogo.models import MaterialOficina, Opcao
from tests.oficina_cenario import FILTRO, montar_oficina

pytestmark = pytest.mark.django_db

BUSCA = reverse("pedidos:materiais", args=["oficina"])


@pytest.fixture(autouse=True)
def cenario():
    montar_oficina()


def acha(client, q, codigo):
    return f'data-codigo="{codigo}"' in client.get(BUSCA, {"q": q}).text


def test_os_avulsos_da_oficina_saíram_do_admin():
    """Spec 009: o material avulso da oficina é uma exceção da configuração (página Formulários);
    o cadastro antigo ficou no banco, sem tela."""
    assert MaterialOficina not in admin.site._registry
    with pytest.raises(NoReverseMatch):
        reverse("admin:catalogo_materialoficina_changelist")


def test_a_lista_de_grupos_no_admin(client, admin_client):
    grupo = Opcao.objects.get(lista=Opcao.Lista.GRUPO_OFICINA)
    admin_client.post(reverse("admin:catalogo_opcao_delete", args=[grupo.pk]), {"post": "yes"})
    assert not acha(client, "filtro", FILTRO)
    r = admin_client.post(
        reverse("admin:catalogo_opcao_add"),
        {"lista": "GRUPO_OFICINA", "valor": "AUTO PECAS", "ordem": "0", "ativo": "on"},
    )
    assert r.status_code == 302
    assert acha(client, "filtro", FILTRO)
