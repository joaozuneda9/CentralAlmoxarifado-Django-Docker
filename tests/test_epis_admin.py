"""Manutenção da escolha dos EPIs e do acesso da Segurança do Trabalho no admin (spec 008, US4,
FR-019, FR-029): vale no próximo acesso ao formulário, sem nova publicação. Os avulsos saíram do
admin na spec 009."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import NoReverseMatch, reverse

from catalogo.models import MaterialEpi, Opcao
from contas.acesso import GRUPO_SEGURANCA_TRABALHO, da_seguranca_trabalho
from tests.epis_cenario import LUVA, montar_epis

pytestmark = pytest.mark.django_db

BUSCA = reverse("pedidos:materiais", args=["epis"])


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


def acha(client, q, codigo):
    return f'data-codigo="{codigo}"' in client.get(BUSCA, {"q": q}).text


def test_os_avulsos_de_epis_saíram_do_admin():
    """Spec 009: o material avulso de EPIs é uma exceção da configuração (página Formulários); o
    cadastro antigo ficou no banco, sem tela."""
    assert MaterialEpi not in admin.site._registry
    with pytest.raises(NoReverseMatch):
        reverse("admin:catalogo_materialepi_changelist")


def test_a_lista_de_grupos_de_epis_no_admin(client, admin_client):
    grupo = Opcao.objects.get(lista=Opcao.Lista.GRUPO_EPI)
    admin_client.post(reverse("admin:catalogo_opcao_delete", args=[grupo.pk]), {"post": "yes"})
    assert not acha(client, "luva", LUVA)
    r = admin_client.post(
        reverse("admin:catalogo_opcao_add"),
        {
            "lista": "GRUPO_EPI",
            "valor": "MATERIAL DE SEGURANÇA E EPI",
            "ordem": "0",
            "ativo": "on",
        },
    )
    assert r.status_code == 302
    assert acha(client, "luva", LUVA)


def test_a_lista_de_grupos_de_epis_aparece_nas_opcoes(admin_client):
    html = admin_client.get(reverse("admin:catalogo_opcao_add")).text
    assert "Grupos (EPIs)" in html and "Grupos (oficina)" in html


def test_o_administrador_da_o_acesso_marcando_o_grupo_no_usuario(admin_client):
    """FR-019: sem nova versão do sistema, só marcando o grupo no formulário do usuário."""
    grupo, _ = Group.objects.get_or_create(name=GRUPO_SEGURANCA_TRABALHO)
    usuario = get_user_model().objects.create_user(username="70050", password="x")
    assert not da_seguranca_trabalho(usuario)
    url = reverse("admin:contas_usuario_change", args=[usuario.pk])
    html = admin_client.get(url).text
    assert GRUPO_SEGURANCA_TRABALHO in html  # o grupo é uma opção do campo de grupos
    campos = {
        "username": "70050",
        "first_name": "",
        "last_name": "",
        "email": "",
        "is_active": "on",
        "groups": [grupo.pk],
        "date_joined_0": "2026-10-23",
        "date_joined_1": "10:00:00",
    }
    r = admin_client.post(url, campos)
    assert r.status_code == 302
    usuario = get_user_model().objects.get(pk=usuario.pk)  # sem o resultado guardado
    assert da_seguranca_trabalho(usuario)
    assert not usuario.is_staff  # o acesso é o grupo, não o administrador
