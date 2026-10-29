import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from tests.cenario import montar_cenario
from tests.paginas import item_atual

pytestmark = pytest.mark.django_db
SENHA = "senha-de-teste-bem-comprida-123"


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(
        username="12345", password=SENHA, first_name="Ana", last_name="Lima"
    )


def entrar(client, matricula="12345", senha=SENHA, **extra):
    return client.post(reverse("login"), {"username": matricula, "password": senha, **extra})


def test_inicio_publico_abre_sem_login_e_sem_barra_lateral(client):
    r = client.get(reverse("pedidos:inicio"))
    assert r.status_code == 200
    assert 'class="app-lateral' not in r.text
    assert f'href="{reverse("login")}"' in r.text


def test_painel_exige_login(client):
    r = client.get(reverse("pedidos:painel"))
    assert r.status_code == 302
    assert r.url.startswith(reverse("login"))


def test_entrar_por_matricula_leva_ao_painel(client, usuario):
    r = entrar(client)
    assert r.status_code == 302 and r.url == reverse("pedidos:painel")
    painel = client.get(r.url)
    assert 'class="app-lateral' in painel.text
    assert item_atual(painel.text, reverse("pedidos:painel"), "Painel")
    assert "12345" in painel.text


def test_matricula_com_espacos_em_volta_entra(client, usuario):
    assert entrar(client, matricula=" 12345 ").status_code == 302


@pytest.mark.parametrize(("matricula", "senha"), [("12345", "errada"), ("99999", SENHA)])
def test_recusa_tem_frase_correta(client, usuario, matricula, senha):
    r = entrar(client, matricula=matricula, senha=senha)
    assert r.status_code == 200
    assert "Matrícula ou senha incorretas." in r.text
    assert "um matrícula" not in r.text


def test_conta_desativada_recebe_a_mesma_recusa(client, usuario):
    usuario.is_active = False
    usuario.save()
    r = entrar(client)
    assert r.status_code == 200 and "Matrícula ou senha incorretas." in r.text


def test_next_para_outro_site_e_ignorado(client, usuario):
    r = entrar(client, next="https://outro.site/")
    assert r.status_code == 302 and r.url == reverse("pedidos:painel")


def test_next_interno_e_respeitado(client, usuario):
    r = entrar(client, next=reverse("pedidos:painel") + "?x=1")
    assert r.url == reverse("pedidos:painel") + "?x=1"


def test_quem_ja_entrou_e_levado_ao_painel(client, usuario):
    client.force_login(usuario)
    r = client.get(reverse("login"))
    assert r.status_code == 302 and r.url == reverse("pedidos:painel")


def test_sair_so_por_post_num_unico_formulario(client, usuario):
    client.force_login(usuario)
    painel = client.get(reverse("pedidos:painel")).text
    assert painel.count(f'action="{reverse("logout")}"') == 1
    assert f'href="{reverse("logout")}"' not in painel
    assert client.get(reverse("logout")).status_code == 405
    r = client.post(reverse("logout"))
    assert r.status_code == 302 and r.url == reverse("login")
    assert client.get(reverse("pedidos:painel")).status_code == 302


def test_cadastros_so_para_equipe(client, usuario):
    client.force_login(usuario)
    assert reverse("admin:index") not in client.get(reverse("pedidos:painel")).text
    usuario.is_staff = True
    usuario.save()
    assert reverse("admin:index") in client.get(reverse("pedidos:painel")).text


def test_login_do_admin_tambem_tem_frase_correta(client, usuario):
    r = client.post(reverse("admin:login"), {"username": "12345", "password": "errada"})
    assert r.status_code == 200
    assert "Matrícula ou senha incorretas" in r.text
    assert "um matrícula" not in r.text


def test_menu_na_ordem_da_spec(admin_client):
    texto = admin_client.get(reverse("pedidos:painel")).text
    rotulos = (
        "Painel",
        "Saída avulsa",
        "Automações",
        "Curva ABC",
        "Cadastros",
    )
    posicoes = [texto.index(f"<span>{r}</span>") for r in rotulos]
    assert posicoes == sorted(posicoes)


def test_login_no_estilo_clean(client):
    r = client.get(reverse("login"))
    assert 'class="ritmo-publico entrada-pagina"' in r.text
    assert 'class="cartao entrada-cartao"' in r.text
    assert 'class="botao botao-primario botao-bloco"' in r.text
    r = entrar(client, senha="errada")
    assert 'class="aviso aviso-erro"' in r.text


@pytest.mark.parametrize(
    "rota",
    ["pedidos:avulsa", "automacoes:pagina", "catalogo:curva"],
)
def test_paginas_internas_tem_o_link_de_volta_acima_do_rotulo(admin_client, rota):
    montar_cenario()
    texto = admin_client.get(reverse(rota)).text
    cabecalho = texto[texto.index('<header class="pagina-cabecalho">') :]
    voltar = cabecalho.index(f'<a class="link-voltar" href="{reverse("pedidos:painel")}">')
    assert voltar < cabecalho.index('<p class="rotulo-secao">')
    assert "Voltar ao painel</a>" in cabecalho


def test_painel_nao_tem_link_de_volta(admin_client):
    assert "link-voltar" not in admin_client.get(reverse("pedidos:painel")).text
