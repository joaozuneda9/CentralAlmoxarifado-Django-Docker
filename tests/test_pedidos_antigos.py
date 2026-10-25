"""Pedidos gravados antes da spec 005 continuam iguais na tela, no recibo e no aviso (SC-008).

Não há conversão de dados: `qtd_pedida` e `qtd_entregue` já eram decimais. O que mudou foi o
formatador (agora um só, sem zeros à direita e sem cortar fração), e ele não pode alterar o que já
estava certo.
"""

import re
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from pedidos.regras import AB, LIMPEZA
from pedidos.telegram import texto_aviso
from pedidos.views.almoxarifado import _formatar_qtd
from tests.cenario import criar_pedido, montar_cenario

pytestmark = pytest.mark.django_db


@pytest.fixture
def logado(client):
    montar_cenario()
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))


def campo_de_entrega(html, codigo):
    return re.search(rf'<input[^>]*name="entregue-{re.escape(codigo)}"[^>]*>', html).group(0)


def test_pedido_antigo_do_ab_com_inteiros_abre_igual(client, logado):
    pedido = criar_pedido(origem=AB, itens=(("016.005.010", "3"), ("013.006.001", "2")))
    html = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    for codigo, qtd in (("016.005.010", "3"), ("013.006.001", "2")):
        campo = campo_de_entrega(html, codigo)
        assert f'data-pedido="{qtd}"' in campo and f'value="{qtd}"' in campo
        assert "," not in campo.split('value="')[1].split('"')[0]  # nenhum "3,0" nem "3,000"
    aviso = texto_aviso(pedido)
    assert "<b>3 UN</b>" in aviso and "<b>2 UN</b>" in aviso


def test_pedido_antigo_da_limpeza_com_decimais_abre_igual(client, logado):
    pedido = criar_pedido(origem=LIMPEZA, itens=(("008.001.002", "1,5"), ("023.001.002", "2")))
    html = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    cafe = campo_de_entrega(html, "008.001.002")
    assert 'data-pedido="1,5"' in cafe and 'value="1,5"' in cafe
    assert 'data-pedido="2"' in campo_de_entrega(html, "023.001.002")
    aviso = texto_aviso(pedido)
    assert "<b>1,5 UN</b>" in aviso and "<b>2 UN</b>" in aviso


def test_pedido_atendido_antigo_mostra_o_entregue_igual(client, logado):
    pedido = criar_pedido(origem=AB, itens=(("016.005.010", "3"),), atendido=True, entregues=["2"])
    html = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert "Atendido" in html or "atendido" in html
    assert re.search(r"\b2\b", html)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Decimal("3"), "3"),
        (Decimal("3.000"), "3"),
        (Decimal("1.5"), "1,5"),
        (Decimal("0.001"), "0,001"),
    ],
)
def test_formatador_da_equipe_nao_corta_nem_enche_de_zeros(valor, esperado):
    for origem in (AB, LIMPEZA):
        pedido = criar_pedido(origem=origem, itens=(("016.005.010", "1"),))
        assert _formatar_qtd(pedido, valor) == esperado
