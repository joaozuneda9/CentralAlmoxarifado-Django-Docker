"""A equipe aceita fração em qualquer unidade e nada corta a quantidade (spec 005).

Antes: o aviso do Telegram e o campo de entrega do atendimento faziam `int()` nos pedidos do AB, e
o atendimento só aceitava inteiro neles. Agora o AB também pede fração (em unidade de medida), então
esses pontos têm de mostrar e aceitar o número exato.
"""

import re
import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from pedidos.models import LinhaSaida
from pedidos.regras import AB
from pedidos.servicos import confirmar_atendimento
from pedidos.telegram import texto_aviso
from pedidos.views.almoxarifado import _formatar_qtd
from tests.cenario import criar_pedido, envio_ab, montar_cenario, registrar, saida

pytestmark = pytest.mark.django_db
HOJE = date(2026, 10, 9)


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="12345", password="x", first_name="Ana")


@pytest.fixture
def pedido_ab():
    montar_cenario()
    return registrar(AB, envio_ab()).pedido  # 3 de FITA VEDA ROSCA (016.005.010)


def test_telegram_mostra_a_fracao_do_pedido_ab():
    pedido = criar_pedido(origem=AB, itens=(("016.005.010", "2,5"), ("013.006.001", "3")))
    texto = texto_aviso(pedido)
    assert "<b>2,5 UN</b>" in texto
    assert "<b>3 UN</b>" in texto


def test_campo_de_entrega_mostra_a_fracao_do_pedido_ab():
    pedido = criar_pedido(origem=AB, itens=(("016.005.010", "2,5"),))
    assert _formatar_qtd(pedido, Decimal("2.5")) == "2,5"
    assert _formatar_qtd(pedido, Decimal("3.000")) == "3"


def test_atendimento_aceita_entrega_fracionada_em_pedido_ab(pedido_ab, usuario):
    r = confirmar_atendimento(
        pedido_ab.id,
        uuid.uuid4(),
        saida(),
        {"016.005.010": "2,5"},
        nao_lancar=False,
        usuario=usuario,
        hoje=HOJE,
    )
    assert r.ok, [e.texto for e in r.erros]
    assert LinhaSaida.objects.get().qtd == Decimal("2.5")


@pytest.fixture
def logado(client, usuario):
    client.force_login(usuario)
    return usuario


def test_adicionar_pela_pagina_aceita_fracao_em_pedido_ab(client, pedido_ab, logado):
    c = "008.001.002"  # CAFÉ 500 G, fora do pedido, com saldo
    r = client.post(
        reverse("pedidos:atendimento_adicionar", args=[pedido_ab.numero]),
        {"adicionar": c, f"qtd-{c}": "1,5"},
    )
    assert r.status_code == 200 and "HX-Retarget" not in r.headers
    campo = re.search(rf'<input[^>]*name="entregue-{re.escape(c)}"[^>]*>', r.text).group(0)
    assert 'value="1,5"' in campo
    assert 'inputmode="decimal"' in campo


def test_campo_de_entrega_do_recibo_do_ab_aceita_decimal(client, pedido_ab, logado):
    r = client.get(reverse("pedidos:detalhe", args=[pedido_ab.numero]))
    campo = re.search(r'<input[^>]*name="entregue-016\.005\.010"[^>]*>', r.text).group(0)
    assert 'inputmode="decimal"' in campo
    assert "numeric" not in campo
