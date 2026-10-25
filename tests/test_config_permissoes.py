"""Quem vê e quem altera a configuração dos formulários (spec 009, US6; FR-028 a FR-032).

Ver é de todo usuário do almoxarifado; alterar exige `is_staff` mais a permissão do cadastro
afetado, e o servidor recusa a gravação de quem não pode, também com o formulário forjado.
"""

import pytest
from django.urls import reverse

from catalogo.acesso import pode_alterar_centros, pode_alterar_materiais
from catalogo.models import CentroCusto, CentroFormulario, ExcecaoMaterial, Material
from tests.cenario import montar_cenario
from tests.config_cenario import criar_centro, usuarios

pytestmark = pytest.mark.django_db

PAGINA = reverse("catalogo:formularios")
FITA = "016.005.010"


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()
    return usuarios()


@pytest.fixture
def centro():
    return criar_centro("SETOR NOVO", "90")


def gravacoes(centro):
    """Cada rota de gravação com um corpo válido: (nome da rota, corpo, quem pode)."""
    return {
        "centros": (
            reverse("catalogo:formularios_centros"),
            {"formulario": "AB", "centro": [centro.pk], "habilitado": "1"},
        ),
        "materiais": (
            reverse("catalogo:formularios_excecao"),
            {"formulario": "AB", "codigo": FITA, "acao": "retirar"},
        ),
    }


def estado():
    return (CentroFormulario.objects.count(), ExcecaoMaterial.objects.count())


def entrar(client, usuario):
    client.force_login(usuario)
    return client


# --- Anônimo e Segurança do Trabalho -----------------------------------------------------------


def test_anonimo_vai_ao_login_em_toda_rota(client, centro):
    assert "/entrar/" in client.get(PAGINA)["Location"]
    antes = estado()
    for url, corpo in gravacoes(centro).values():
        r = client.post(url, corpo)
        assert r.status_code == 302 and "/entrar/" in r["Location"]
    assert estado() == antes


def test_seguranca_do_trabalho_e_negada_como_toda_rota_interna(client, centro, cenario):
    entrar(client, cenario["seguranca"])
    r = client.get(PAGINA)
    assert r.status_code == 302 and r["Location"] == reverse("pedidos:autorizacoes")
    antes = estado()
    for url, corpo in gravacoes(centro).values():
        assert client.post(url, corpo).status_code == 403
    assert estado() == antes


def test_o_item_do_menu_nao_aparece_para_a_seguranca_do_trabalho(client, cenario):
    entrar(client, cenario["seguranca"])
    assert "Formulários" not in client.get(reverse("pedidos:autorizacoes")).text


# --- Quem só vê --------------------------------------------------------------------------------


def test_usuario_comum_ve_tudo_sem_os_controles(client, cenario, centro):
    entrar(client, cenario["comum"])
    for aba in ("centros", "materiais"):
        r = client.get(PAGINA, {"formulario": "AB", "aba": aba})
        assert r.status_code == 200
        assert reverse("catalogo:formularios_centros") not in r.text
        assert reverse("catalogo:formularios_excecao") not in r.text
        assert "Somente consulta" in r.text
    assert "SETOR NOVO" in client.get(PAGINA, {"formulario": "AB", "aba": "centros"}).text
    assert FITA in client.get(PAGINA, {"formulario": "AB", "aba": "materiais"}).text


@pytest.mark.parametrize("quem", ["comum", "staff"])
def test_quem_nao_pode_recebe_403_em_toda_gravacao_e_nada_muda(client, cenario, centro, quem):
    entrar(client, cenario[quem])
    antes = estado()
    for url, corpo in gravacoes(centro).values():
        assert client.post(url, corpo).status_code == 403
    assert estado() == antes
    assert not CentroCusto.objects.get(pk=centro.pk).formularios.exists()
    assert Material.objects.filter(codigo=FITA, oculto=False).exists()


def test_staff_sem_permissao_ve_a_pagina_sem_controles(client, cenario):
    entrar(client, cenario["staff"])
    r = client.get(PAGINA, {"aba": "materiais"})
    assert r.status_code == 200 and reverse("catalogo:formularios_excecao") not in r.text


# --- Quem altera -------------------------------------------------------------------------------


def test_staff_com_a_permissao_de_centros_altera_so_centros(client, cenario, centro):
    entrar(client, cenario["so_centros"])
    centros, materiais = gravacoes(centro)["centros"], gravacoes(centro)["materiais"]
    assert client.post(centros[0], centros[1]).status_code == 302
    assert CentroFormulario.objects.filter(centro=centro, formulario="AB").exists()
    assert client.post(materiais[0], materiais[1]).status_code == 403
    assert not ExcecaoMaterial.objects.exists()
    r = client.get(PAGINA, {"formulario": "AB", "aba": "centros"})
    assert reverse("catalogo:formularios_centros") in r.text
    assert (
        reverse("catalogo:formularios_excecao") not in client.get(PAGINA, {"aba": "materiais"}).text
    )


def test_staff_com_a_permissao_de_materiais_altera_so_materiais(client, cenario, centro):
    entrar(client, cenario["so_materiais"])
    centros, materiais = gravacoes(centro)["centros"], gravacoes(centro)["materiais"]
    assert client.post(materiais[0], materiais[1]).status_code == 302
    assert ExcecaoMaterial.objects.get().habilitado is False
    assert client.post(centros[0], centros[1]).status_code == 403
    assert not CentroFormulario.objects.filter(centro=centro).exists()


def test_superusuario_altera_os_dois(client, cenario, centro):
    entrar(client, cenario["admin"])
    for url, corpo in gravacoes(centro).values():
        assert client.post(url, corpo).status_code == 302
    assert CentroFormulario.objects.filter(centro=centro, formulario="AB").exists()
    assert ExcecaoMaterial.objects.filter(formulario="AB").count() == 1
    assert "Somente consulta" not in client.get(PAGINA).text


def test_a_permissao_sem_ser_staff_nao_basta(client, django_user_model, cenario, centro):
    """O critério é o do admin: `is_staff` mais a permissão. Só a permissão não abre a gravação."""
    from django.contrib.auth.models import Permission

    quem = django_user_model.objects.create_user(username="80099", password="x")
    quem.user_permissions.add(
        *Permission.objects.filter(codename__in=["change_centrocusto", "change_excecaomaterial"])
    )
    entrar(client, quem)
    for url, corpo in gravacoes(centro).values():
        assert client.post(url, corpo).status_code == 403


def test_as_funcoes_de_permissao(cenario):
    assert pode_alterar_centros(cenario["admin"]) and pode_alterar_materiais(cenario["admin"])
    assert pode_alterar_centros(cenario["so_centros"])
    assert not pode_alterar_materiais(cenario["so_centros"])
    assert pode_alterar_materiais(cenario["so_materiais"])
    assert not pode_alterar_centros(cenario["so_materiais"])
    assert not pode_alterar_centros(cenario["staff"]) and not pode_alterar_materiais(
        cenario["staff"]
    )
    assert not pode_alterar_centros(cenario["comum"])
    from django.contrib.auth.models import AnonymousUser

    assert not pode_alterar_centros(AnonymousUser()) and not pode_alterar_materiais(None)
