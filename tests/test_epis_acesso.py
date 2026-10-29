"""Acesso da Segurança do Trabalho (spec 008, US6, FR-017 a FR-020, SC-004): só a fila, o detalhe
de autorização, a decisão e as páginas públicas; o resto é negado por padrão, inclusive rota nova.
"""

import pytest
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from contas.acesso import ROTAS_SEGURANCA_TRABALHO, da_seguranca_trabalho
from pedidos.models import AutorizacaoPedido
from tests.epis_cenario import SENHA, montar_epis, registrar
from tests.paginas import texto

pytestmark = pytest.mark.django_db

FILA = reverse("pedidos:autorizacoes")

PERMITIDAS = {
    "login",
    "logout",
    "pedidos:autorizacoes",
    "pedidos:autorizacao",
    "pedidos:decidir",
    "pedidos:inicio",
    "pedidos:formulario",
    "pedidos:materiais",
    "pedidos:carrinho",
    "pedidos:consulta_epi",
}


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


def rotas_nomeadas():
    """Toda rota com nome do projeto (com o namespace), com uma URL concreta de teste."""
    achadas = {}

    def andar(padroes, namespace):
        for p in padroes:
            if isinstance(p, URLResolver):
                novo = f"{namespace}{p.namespace}:" if p.namespace else namespace
                andar(p.url_patterns, novo)
            elif isinstance(p, URLPattern) and p.name:
                nome = f"{namespace}{p.name}"
                parametros = list(p.pattern.regex.groupindex) or list(
                    getattr(p.pattern, "converters", {})
                )
                kwargs = {k: "1" for k in parametros}
                try:
                    achadas.setdefault(nome, reverse(nome, kwargs=kwargs))
                except Exception:  # rota que o reverse não monta com um valor qualquer
                    continue

    andar(get_resolver().url_patterns, "")
    return achadas


def test_a_lista_de_rotas_permitidas_e_a_do_contrato():
    assert ROTAS_SEGURANCA_TRABALHO == PERMITIDAS


def test_o_teste_enxerga_as_rotas_de_todas_as_areas():
    nomes = set(rotas_nomeadas())
    for esperado in [
        "pedidos:painel",
        "pedidos:avulsa",
        "pedidos:detalhe",
        "automacoes:pagina",
        "catalogo:curva",
        "admin:index",
        "pedidos:autorizacoes",
        "pedidos:consulta_epi",
        "login",
        "logout",
    ]:
        assert esperado in nomes, esperado
    assert len(nomes) > 60


def test_o_grupo_so_abre_as_rotas_da_lista(client, quem):
    client.force_login(quem["seguranca"])
    rotas = rotas_nomeadas()
    for nome, url in sorted(rotas.items()):
        if nome in PERMITIDAS:
            continue
        r = client.get(url)
        assert r.status_code == 302 and r["Location"] == FILA, (nome, url, r.status_code)
        for metodo in (client.post, client.put, client.delete):
            assert metodo(url).status_code == 403, (nome, metodo.__name__)


def test_as_rotas_permitidas_passam_pelo_filtro(client, quem):
    client.force_login(quem["seguranca"])
    rotas = rotas_nomeadas()
    for nome in sorted(PERMITIDAS - {"login", "logout"}):
        r = client.get(rotas[nome])
        assert not (
            r.status_code == 302 and r["Location"] == FILA and nome != "pedidos:autorizacoes"
        )
        assert r.status_code != 403 or nome == "pedidos:decidir", nome  # a view decide o resto


@pytest.mark.parametrize(
    "caminho",
    [
        "/painel/",
        "/painel/saida-avulsa/",
        "/painel/automacoes/",
        "/painel/catalogo/curva/",
        "/admin/",
        "/admin/login/",
        "/admin/contas/usuario/",
        "/admin/rota-inexistente-do-admin/",
        "/painel/pedidos/P-000001/",
        "/painel/pedidos/P-000001/atender/",
        "/painel/recibos/impressos/",
    ],
)
def test_caminhos_digitados_sao_negados_ao_grupo(client, quem, caminho):
    client.force_login(quem["seguranca"])
    r = client.get(caminho)
    assert r.status_code in (302, 404) and (r.status_code == 404 or r["Location"] == FILA)
    assert client.post(caminho).status_code in (403, 404)


def test_o_detalhe_de_pedido_que_nao_e_de_epi_e_negado(client, quem):
    import uuid

    from pedidos.regras import AB
    from pedidos.servicos import registrar_pedido
    from tests.cenario import envio_ab

    ab = registrar_pedido(AB, uuid.uuid4(), envio_ab()).pedido
    client.force_login(quem["seguranca"])
    r = client.get(reverse("pedidos:detalhe", args=[ab.numero]))
    assert r.status_code == 302 and r["Location"] == FILA
    assert client.get(reverse("pedidos:autorizacao", args=[ab.numero])).status_code == 404


def test_o_grupo_decide_pela_rota_permitida(client, quem):
    pedido = registrar()
    client.force_login(quem["seguranca"])
    client.post(reverse("pedidos:decidir", args=[pedido.numero]), {"decisao": "autorizar"})
    assert AutorizacaoPedido.objects.get(pedido=pedido).situacao == "AUTORIZADO"


def test_o_grupo_continua_abrindo_as_paginas_publicas(client, quem):
    client.force_login(quem["seguranca"])
    assert client.get(reverse("pedidos:inicio")).status_code == 200
    assert client.get(reverse("pedidos:formulario", args=["epis"])).status_code == 200
    assert client.get(reverse("pedidos:consulta_epi")).status_code == 200


def test_o_login_do_grupo_termina_na_fila(client, quem):
    r = client.post(reverse("login"), {"username": "70001", "password": SENHA}, follow=True)
    assert r.redirect_chain[-1][0] == FILA and r.status_code == 200
    assert "Autorizações de EPIs" in r.text


def test_o_menu_do_grupo_so_tem_autorizacoes(client, quem):
    client.force_login(quem["seguranca"])
    html = client.get(FILA).text
    menu = html.partition('<nav class="app-menu"')[2].partition("</nav>")[0]
    assert "Autorizações" in texto(menu)
    for fora in ["Painel", "Saída avulsa", "Automações", "Curva ABC", "Cadastros"]:
        assert fora not in texto(menu), fora
    # A marca leva à fila, não ao painel que ele não abre.
    assert f'<a class="marca" href="{FILA}">' in html
    assert 'href="/painel/"' not in html.partition("</aside>")[0]


def test_o_menu_dos_demais_nao_muda_e_nao_tem_autorizacoes(client, quem):
    client.force_login(quem["almox"])
    menu = texto(client.get(reverse("pedidos:painel")).text.partition('<nav class="app-menu"')[2])
    assert "Painel" in menu and "Saída avulsa" in menu and "Automações" in menu
    assert "Autorizações" not in menu.partition("</nav>")[0]


def test_almoxarifado_administrador_e_anonimo_nao_mudam(client, quem):
    client.force_login(quem["almox"])
    for nome in ["pedidos:painel", "pedidos:avulsa", "automacoes:pagina", "catalogo:curva"]:
        assert client.get(reverse(nome)).status_code == 200, nome
    admin = Client()
    admin.force_login(quem["admin"])
    assert admin.get(reverse("admin:index")).status_code == 200
    assert admin.get(reverse("pedidos:painel")).status_code == 200
    anonimo = Client()
    assert anonimo.get(reverse("pedidos:painel")).status_code == 302
    assert anonimo.get(reverse("pedidos:painel"))["Location"].startswith(reverse("login"))


def test_administrador_no_grupo_tambem_e_restringido(client, quem):
    """O acesso é a participação no grupo, nunca `is_staff` (research R4)."""
    quem["admin"].groups.add(*quem["seguranca"].groups.all())
    assert da_seguranca_trabalho(quem["admin"])
    client.force_login(quem["admin"])
    r = client.get(reverse("admin:index"))
    assert r.status_code == 302 and r["Location"] == FILA


def test_anonimo_nao_e_do_grupo():
    from django.contrib.auth.models import AnonymousUser

    assert not da_seguranca_trabalho(AnonymousUser()) and not da_seguranca_trabalho(None)
