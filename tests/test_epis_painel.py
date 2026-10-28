"""Painel do almoxarifado com os pedidos de EPI (spec 008, FR-022, FR-025, FR-032): a situação de
autorização aparece, filtra e não conta como pedido a atender."""

import re

import pytest
from django.urls import reverse

from pedidos.consultas import FiltrosPainel, pedidos_do_painel
from pedidos.models import Pedido
from pedidos.servicos import decidir_autorizacao
from tests.cenario import criar_pedido
from tests.epis_cenario import montar_epis, registrar
from tests.paginas import texto

pytestmark = pytest.mark.django_db

PAINEL = reverse("pedidos:painel")


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


@pytest.fixture
def almox(client, quem):
    client.force_login(quem["almox"])
    return quem["almox"]


@pytest.fixture
def tres(quem):
    """Um pedido de EPI em cada estado de autorização."""
    aguardando = registrar(solicitante="Ana Aguardando")
    autorizado = registrar(solicitante="Bia Autorizada")
    recusado = registrar(solicitante="Caio Recusado")
    decidir_autorizacao(autorizado.numero, "autorizar", "", quem["seguranca"])
    decidir_autorizacao(recusado.numero, "recusar", "Sem laudo", quem["seguranca"])
    return aguardando, autorizado, recusado


def numeros(client, **filtros):
    html = client.get(PAINEL, filtros, HTTP_HX_REQUEST="true").text
    return set(re.findall(r"P-\d{6}", html))


def test_a_lista_mostra_a_situacao_de_cada_pedido_de_epi(client, almox, tres):
    html = client.get(PAINEL).text
    for p, rotulo in zip(
        tres, ["Aguardando autorização", "Aguardando atendimento", "Recusado"], strict=True
    ):
        linha = next(t for t in html.split("<tr>") if p.numero in t)
        assert rotulo in texto(linha), (p.numero, rotulo)


def test_o_filtro_de_autorizacao(client, almox, tres):
    aguardando, autorizado, recusado = (p.numero for p in tres)
    assert numeros(client, autorizacao="aguardando") == {aguardando}
    assert numeros(client, autorizacao="autorizado") == {autorizado}
    assert numeros(client, autorizacao="recusado") == {recusado}
    assert numeros(client, autorizacao="") == {aguardando, autorizado, recusado}


def test_o_filtro_de_autorizacao_nao_inclui_pedido_de_outro_formulario(client, almox, tres):
    outro = criar_pedido()
    for valor in ("aguardando", "autorizado", "recusado"):
        assert outro.numero not in numeros(client, autorizacao=valor)
    assert outro.numero in numeros(client)


def test_o_filtro_de_autorizacao_combina_com_a_origem_e_a_situacao(client, almox, tres):
    autorizado = tres[1].numero
    assert numeros(client, autorizacao="autorizado", origem="EPIS") == {autorizado}
    assert numeros(client, autorizacao="autorizado", origem="AB") == set()
    assert numeros(client, autorizacao="autorizado", situacao="aguardando") == {autorizado}
    assert numeros(client, autorizacao="aguardando", situacao="aguardando") == set()


def test_situacao_aguardando_atendimento_nao_inclui_nao_autorizado_nem_recusado(
    client, almox, tres
):
    assert numeros(client, situacao="aguardando") == {tres[1].numero}


def test_o_atalho_atender_conta_so_o_que_pode_ser_atendido(client, almox, tres):
    outro = criar_pedido()
    html = client.get(PAINEL).text
    atalho = html.partition('class="atalho-numero">')[2].partition("<")[0]
    assert atalho == "2"  # o autorizado e o pedido de outro formulário
    assert outro.numero


def test_o_pedido_recusado_continua_consultavel_no_painel(client, almox, tres):
    r = client.get(reverse("pedidos:detalhe", args=[tres[2].numero]))
    assert r.status_code == 200 and "Recusado" in texto(r.text)


def test_sem_pedido_de_epi_o_painel_e_o_de_sempre(client, almox):
    criar_pedido()
    criar_pedido(atendido=True)
    assert numeros(client, situacao="aguardando") and numeros(client)
    filtrados = pedidos_do_painel(FiltrosPainel({"autorizacao": "aguardando"}).filtros())
    assert not filtrados.exists()
    assert Pedido.objects.count() == 2
