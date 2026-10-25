"""Consulta pública do resultado do pedido de EPI pelo número (spec 008, US5, FR-031, FR-031a,
FR-031b): só a situação e o motivo da recusa, resposta neutra e limite por origem."""

import re
import uuid

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from pedidos.regras import AB, normalizar_numero_pedido, texto_situacao_consulta
from pedidos.servicos import decidir_autorizacao, registrar_pedido
from tests.cenario import envio_ab
from tests.epis_cenario import enviar, montar_epis, registrar, usuarios

pytestmark = pytest.mark.django_db

URL = reverse("pedidos:consulta_epi")
NAO_ACHADO = "Não encontramos um pedido de EPIs com este número."
LIMITE = "Muitas consultas desta rede em pouco tempo. Procure o almoxarifado."


@pytest.fixture(autouse=True)
def cenario():
    cache.clear()  # o limite vive no cache: cada teste começa do zero
    montar_epis()


@pytest.fixture
def quem():
    return usuarios()


def texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def consultar(client, numero):
    return client.post(URL, {"numero": numero})


def test_a_url_fica_sob_o_formulario_de_epis():
    assert URL == "/pedido/epis/consulta/"


def test_get_so_mostra_o_formulario_do_numero(client):
    r = client.get(URL)
    assert r.status_code == 200
    assert 'name="numero"' in r.text and 'name="csrfmiddlewaretoken"' in r.text
    assert "Pedido P-" not in r.text


def test_aguardando(client):
    pedido = registrar()
    html = texto(consultar(client, pedido.numero).text)
    assert f"Pedido {pedido.numero}: aguardando autorização da Segurança do Trabalho." in html


def test_autorizado(client, quem):
    pedido = registrar()
    decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    html = texto(consultar(client, pedido.numero).text)
    assert f"Pedido {pedido.numero}: autorizado. O almoxarifado vai atendê-lo" in html
    assert "procure o almoxarifado para retirar" in html


def test_recusado_mostra_o_motivo(client, quem):
    pedido = registrar()
    decidir_autorizacao(pedido.numero, "recusar", "EPI já entregue em março", quem["seguranca"])
    html = texto(consultar(client, pedido.numero).text)
    assert f"Pedido {pedido.numero}: recusado pela Segurança do Trabalho." in html
    assert "Motivo: EPI já entregue em março" in html


def test_nao_mostra_nome_destino_observacao_nem_materiais(client, quem):
    pedido = registrar(solicitante="Marcos Pereira da Silva")
    r = consultar(client, pedido.numero)
    for dado in ["Marcos", "Pereira", "ETA I", "LUVA DE VAQUETA", "013.005.100", "Destino"]:
        assert dado not in r.text, dado
    # Nem na recusa, que mostra o motivo mas continua sem identificar o servidor.
    decidir_autorizacao(pedido.numero, "recusar", "Sem laudo", quem["seguranca"])
    r = consultar(client, pedido.numero)
    assert "Sem laudo" in r.text and "Marcos" not in r.text and "LUVA" not in r.text


def test_o_numero_digitado_e_normalizado(client):
    pedido = registrar()
    numero = pedido.numero  # P-000001
    for digitado in [numero.lower(), f" {numero} ", "P-1", "p1", "P-0001"]:
        assert "aguardando autorização" in texto(consultar(client, digitado).text), digitado


def test_numero_inexistente_e_de_outro_formulario_tem_a_mesma_resposta(client):
    registrar()
    ab = registrar_pedido(AB, uuid.uuid4(), envio_ab()).pedido
    inexistente = consultar(client, "P-999999")
    de_outro = consultar(client, ab.numero)
    assert texto(inexistente.text) == texto(de_outro.text.replace(ab.numero, "P-999999"))
    assert NAO_ACHADO in texto(inexistente.text) and NAO_ACHADO in texto(de_outro.text)
    assert inexistente.status_code == de_outro.status_code == 200


def test_numero_em_branco_pede_o_numero(client):
    r = consultar(client, "   ")
    assert "Informe o número do pedido." in texto(r.text)


def test_o_limite_por_origem_recusa_a_consulta_seguinte(client, settings):
    settings.PEDIDOS_CONSULTA_LIMITE_IP_10_MIN = 2
    pedido = registrar()
    assert "aguardando" in texto(consultar(client, pedido.numero).text)
    assert "aguardando" in texto(consultar(client, pedido.numero).text)
    r = consultar(client, pedido.numero)
    assert LIMITE in texto(r.text) and "aguardando" not in texto(r.text)


def test_o_limite_e_por_origem(client, settings):
    settings.PEDIDOS_CONSULTA_LIMITE_IP_10_MIN = 1
    pedido = registrar()
    consultar(client, pedido.numero)
    assert LIMITE in texto(consultar(client, pedido.numero).text)
    outro = Client(REMOTE_ADDR="10.9.9.9")
    assert "aguardando" in texto(outro.post(URL, {"numero": pedido.numero}).text)


def test_nao_vai_para_o_cache_do_navegador(client):
    assert "no-store" in consultar(client, "P-000001")["Cache-Control"]
    assert "no-store" in client.get(URL)["Cache-Control"]


def test_a_consulta_exige_o_csrf():
    estrito = Client(enforce_csrf_checks=True)
    assert estrito.post(URL, {"numero": "P-000001"}).status_code == 403


def test_outro_metodo_nao_e_aceito(client):
    assert client.put(URL).status_code == 405 and client.delete(URL).status_code == 405


def test_a_consulta_nao_grava_nada(client):
    pedido = registrar()
    from pedidos.models import AutorizacaoPedido, Pedido

    antes = (
        Pedido.objects.count(),
        AutorizacaoPedido.objects.filter(situacao="AGUARDANDO").count(),
    )
    consultar(client, pedido.numero)
    depois = (
        Pedido.objects.count(),
        AutorizacaoPedido.objects.filter(situacao="AGUARDANDO").count(),
    )
    assert antes == depois


def test_a_tela_de_sucesso_leva_ao_link_da_consulta(client):
    r = enviar(client, [("013.005.100", "1")])
    assert f'href="{URL}"' in r.text
    assert "consulte o resultado" in texto(r.text).lower()


def test_o_texto_da_situacao_e_puro():
    assert texto_situacao_consulta("P-000001", "AGUARDANDO", "") == (
        "Pedido P-000001: aguardando autorização da Segurança do Trabalho.",
        "",
    )
    assert texto_situacao_consulta("P-000001", "AUTORIZADO", "")[0].startswith(
        "Pedido P-000001: autorizado."
    )
    assert texto_situacao_consulta("P-000001", "RECUSADO", "Sem laudo") == (
        "Pedido P-000001: recusado pela Segurança do Trabalho.",
        "Sem laudo",
    )


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("P-000123", "P-000123"),
        ("p-123", "P-000123"),
        (" P123 ", "P-000123"),
        ("AV-000002", "AV-000002"),
        ("abc", "ABC"),
        ("", ""),
        ("  ", ""),
    ],
)
def test_normalizar_numero_pedido(digitado, esperado):
    assert normalizar_numero_pedido(digitado) == esperado
