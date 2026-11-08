"""Papéis de acesso na área interna (spec 012): a tabela de rotas aplicada pelo middleware, o que
cada papel abre, o menu, o painel, o usuário sem papel e a recusa (contracts/tabela-de-rotas.md e
contracts/recusa.md)."""

import subprocess
import uuid

import pytest
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.test import Client, override_settings
from django.urls import include, path, reverse
from django.utils import timezone

from contas.acesso import (
    ADMIN,
    ATENDER,
    GRUPO_ATENDIMENTO,
    GRUPO_GESTAO,
    PUBLICA,
    REGRAS_POR_ROTA,
    SEGURANCA,
    Regra,
    regra_da_rota,
)
from pedidos.models import Atendimento, ExecucaoRobo, LinhaSaida
from pedidos.regras import LIMPEZA
from tests.cenario import envio_limpeza, montar_cenario, registrar
from tests.papeis import usuario_com
from tests.rotas import rotas_nomeadas

pytestmark = pytest.mark.django_db

NEGADO = "interface/acesso_negado.html"


def _fora_da_tabela(request):
    return HttpResponse("aberta")


# URLconf de teste: as rotas do projeto mais uma que nenhuma tabela conhece.
urlpatterns = [
    path("teste-fora-da-tabela/", _fora_da_tabela, name="fora_da_tabela"),
    path("", include("config.urls")),
]


@pytest.fixture(autouse=True)
def sem_processos(monkeypatch):
    """Nenhum robô sobe de verdade: as ações de Automações chamam o `Popen`."""
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: chamadas.append(a))
    return chamadas


def cliente(usuario):
    c = Client(raise_request_exception=False)
    c.force_login(usuario)
    return c


def negado(resposta) -> bool:
    return resposta.status_code == 403 and NEGADO in [t.name for t in resposta.templates]


def com_a_regra(regra: Regra):
    """Um usuário que cumpre a regra: os dois papéis e, se pedir, staff com as permissões."""
    usuario = usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO, username="com", is_staff=True)
    if regra.exige_staff:
        from django.contrib.auth.models import Permission

        codinomes = [p.split(".", 1)[1] for p in regra.permissoes if p.startswith("catalogo.")]
        usuario.user_permissions.add(*Permission.objects.filter(codename__in=codinomes))
    return usuario


def sem_a_regra(regra: Regra):
    """Um usuário com o outro papel (ou os dois sem staff, nas gravações da spec 009)."""
    if regra.exige_staff:
        return usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO, username="sem")
    outro = GRUPO_GESTAO if ATENDER in regra.permissoes else GRUPO_ATENDIMENTO
    return usuario_com(outro, username="sem")


# --- A tabela (contrato, garantias 1 a 4) ---------------------------------------------------


def test_toda_rota_nomeada_esta_na_tabela():
    fora = [nome for nome in rotas_nomeadas() if regra_da_rota(nome) is None]
    assert fora == []


def test_a_tabela_so_tem_rotas_que_existem():
    assert set(REGRAS_POR_ROTA) <= set(rotas_nomeadas())


def test_categorias_do_contrato():
    assert {n for n, r in REGRAS_POR_ROTA.items() if r == PUBLICA} == {
        "login",
        "logout",
        "pedidos:inicio",
        "pedidos:formulario",
        "pedidos:materiais",
        "pedidos:carrinho",
        "pedidos:consulta",
        "pedidos:consulta_epi",
    }
    assert {n for n, r in REGRAS_POR_ROTA.items() if r == SEGURANCA} == {
        "pedidos:autorizacoes",
        "pedidos:autorizacao",
        "pedidos:decidir",
    }
    assert regra_da_rota("admin:index") == ADMIN
    assert sum(isinstance(r, Regra) for r in REGRAS_POR_ROTA.values()) == 25


@pytest.mark.parametrize(
    "nome", sorted(n for n, r in REGRAS_POR_ROTA.items() if isinstance(r, Regra))
)
def test_sem_a_regra_e_negado_em_get_e_post(nome):
    regra = REGRAS_POR_ROTA[nome]
    url = rotas_nomeadas()[nome]
    c = cliente(sem_a_regra(regra))
    for metodo in (c.get, c.post):
        r = metodo(url)
        assert negado(r), (nome, metodo.__name__, r.status_code)
        assert regra.motivo in r.text
    assert not ExecucaoRobo.objects.exists()


@pytest.mark.parametrize(
    "nome", sorted(n for n, r in REGRAS_POR_ROTA.items() if isinstance(r, Regra))
)
def test_com_a_regra_o_middleware_nao_recusa(nome):
    montar_cenario()
    regra = REGRAS_POR_ROTA[nome]
    url = rotas_nomeadas()[nome]
    c = cliente(com_a_regra(regra))
    for metodo in (c.get, c.post):
        r = metodo(url)
        assert not negado(r), (nome, metodo.__name__)


@override_settings(ROOT_URLCONF=__name__)
def test_rota_fora_da_tabela_so_abre_ao_superusuario():
    url = reverse("fora_da_tabela")
    r = cliente(usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO, username="1")).get(url)
    assert negado(r) and "não está liberada" in r.text
    assert cliente(usuario_com(username="2", is_superuser=True)).get(url).text == "aberta"
    anonimo = Client().get(url)
    assert anonimo.status_code == 302 and reverse("login") in anonimo["Location"]


def test_anonimo_vai_ao_login():
    for nome in ("pedidos:painel", "automacoes:pagina", "catalogo:curva"):
        r = Client().get(reverse(nome))
        assert r.status_code == 302 and reverse("login") in r["Location"], nome


# --- US1: Automações só do chefe --------------------------------------------------------------


def test_atendimento_nao_dispara_nada_em_automacoes(sem_processos):
    c = cliente(usuario_com(GRUPO_ATENDIMENTO))
    for nome in [n for n in REGRAS_POR_ROTA if n.startswith("automacoes:")]:
        url = rotas_nomeadas()[nome]
        assert negado(c.get(url)) and negado(c.post(url, {"modo": "lancar", "lotes": ["P-1"]}))
        assert "Esta página é de quem opera as automações." in c.get(url).text
    assert sem_processos == [] and not ExecucaoRobo.objects.exists()


def test_painel_esconde_o_cartao_do_lancamento_de_quem_so_atende():
    montar_cenario()
    so_atende = cliente(usuario_com(GRUPO_ATENDIMENTO, username="1")).get(reverse("pedidos:painel"))
    assert so_atende.status_code == 200
    assert reverse("automacoes:lancar") not in so_atende.text
    assert "Ver automações" not in so_atende.text
    assert "Saúde do catálogo" in so_atende.text
    gestao = cliente(usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO, username="2"))
    completo = gestao.get(reverse("pedidos:painel")).text
    assert reverse("automacoes:lancar") in completo and "Ver automações" in completo


def test_detalhe_so_leva_a_automacoes_quem_opera(dois_lotes):
    numero, _ = dois_lotes
    LinhaSaida.objects.filter(lote=numero).update(status=LinhaSaida.Status.VERIFICAR)
    url = reverse("pedidos:detalhe", args=[numero])
    so_atende = cliente(usuario_com(GRUPO_ATENDIMENTO, username="1")).get(url).text
    completo = cliente(usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO, username="2")).get(url).text
    assert "Resolver em Automações" in completo
    assert "Resolver em Automações" not in so_atende


# --- US2: o Atendimento segue igual -------------------------------------------------------------


def test_atendimento_atende_imprime_edita_e_registra_avulsa():
    montar_cenario()
    pedido = registrar(LIMPEZA, envio_limpeza()).pedido
    c = cliente(usuario_com(GRUPO_ATENDIMENTO))
    r = c.post(
        reverse("pedidos:atender", args=[pedido.numero]),
        {
            "atendimento_id": str(uuid.uuid4()),
            "data": timezone.localdate().isoformat(),
            "recebedor": "Carla",
            "centro_custo": "ETA II",
            "tipo": "BALCÃO",
            "placa": "",
            "obs": "",
            "entregue-023.001.002": "2",
            "entregue-008.001.002": "1,5",
        },
    )
    assert r.status_code == 302 and Atendimento.objects.filter(pedido=pedido).exists()
    atendimento = Atendimento.objects.get(pedido=pedido)
    r = c.post(reverse("pedidos:marcar_impressos"), {"atendimentos": [atendimento.pk]})
    assert r.status_code != 403
    assert c.get(reverse("pedidos:editar", args=[pedido.numero])).status_code == 200
    assert c.get(reverse("pedidos:avulsa")).status_code == 200
    for nome in ("catalogo:curva", "catalogo:formularios"):
        r = c.get(reverse(nome))
        assert negado(r) and "Esta página é da gestão do almoxarifado." in r.text


def rotulos_do_menu(usuario):
    return [
        item["rotulo"] for item in cliente(usuario).get(reverse("pedidos:painel")).context["menu"]
    ]


def test_menu_por_papel():
    montar_cenario()
    assert rotulos_do_menu(usuario_com(GRUPO_ATENDIMENTO, username="1")) == [
        "Painel",
        "Saída avulsa",
    ]
    assert rotulos_do_menu(usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO, username="2")) == [
        "Painel",
        "Saída avulsa",
        "Automações",
        "Curva ABC",
        "Formulários",
    ]
    staff = usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO, username="3", is_staff=True)
    assert rotulos_do_menu(staff)[-1] == "Cadastros"


# --- US3: papéis pelo admin, usuário sem papel e superusuário ------------------------------------


def test_usuario_sem_papel_ve_a_explicacao_e_nada_mais():
    montar_cenario()
    pedido = registrar(LIMPEZA, envio_limpeza()).pedido
    usuario_com(username="1")
    c = Client()
    r = c.post(reverse("login"), {"username": "1", "password": "x"}, follow=True)
    assert r.status_code == 403 and NEGADO in [t.name for t in r.templates]
    assert "Seu usuário ainda não tem acesso" in r.text
    assert pedido.numero not in r.text and pedido.solicitante not in r.text
    assert "Voltar ao painel" not in r.text
    assert r.text.count(f'action="{reverse("logout")}"') == 1


def test_dar_e_tirar_o_papel_vale_na_proxima_requisicao():
    montar_cenario()
    pedido = registrar(LIMPEZA, envio_limpeza()).pedido
    usuario = usuario_com(username="1")
    c = cliente(usuario)
    painel = reverse("pedidos:painel")
    assert negado(c.get(painel))
    atendimento = Group.objects.get(name=GRUPO_ATENDIMENTO)
    usuario.groups.add(atendimento)
    assert c.get(painel).status_code == 200
    usuario.groups.remove(atendimento)
    assert negado(c.post(reverse("pedidos:atender", args=[pedido.numero])))


def test_superusuario_sem_grupo_abre_a_area_interna_mas_nao_decide_epi():
    montar_cenario()
    c = cliente(usuario_com(username="1", is_superuser=True, is_staff=True))
    for nome in ("pedidos:painel", "automacoes:pagina", "catalogo:curva", "catalogo:formularios"):
        assert c.get(reverse(nome)).status_code == 200, nome
    assert c.get(reverse("pedidos:autorizacoes")).status_code == 403


def test_recusa_do_htmx_e_sem_cache_e_sem_dados():
    montar_cenario()
    pedido = registrar(LIMPEZA, envio_limpeza()).pedido
    c = cliente(usuario_com(GRUPO_GESTAO))
    r = c.get(reverse("pedidos:detalhe", args=[pedido.numero]), HTTP_HX_REQUEST="true")
    assert r.status_code == 403
    assert "no-store" in r["Cache-Control"]
    assert pedido.numero not in r.text and pedido.solicitante not in r.text
