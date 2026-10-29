"""Cada envio monta o catálogo do formulário uma vez só: a view passa ao serviço o que já montou
(o do AB é a conta pesada da curva ABC), e o envio que dá certo não monta a tela."""

import time
import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Material
from pedidos import servicos
from pedidos.models import ItemPedido, Pedido
from pedidos.protecao import emitir
from pedidos.regras import EnvioSaida
from pedidos.views import almoxarifado, publico
from tests.cenario import itens, montar_cenario, saida

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalogos(monkeypatch):
    """As origens de cada catálogo montado, pela view ou pelo serviço."""
    montadas = []
    original = servicos.catalogo_de

    def contando(origem):
        montadas.append(origem)
        return original(origem)

    for modulo in (servicos, publico, almoxarifado):
        monkeypatch.setattr(modulo, "catalogo_de", contando)
    return montadas


@pytest.fixture
def telas(monkeypatch):
    """Quantas vezes as opções da saída (parte da tela da saída avulsa) foram montadas."""
    montadas = []
    original = almoxarifado.opcoes_saida

    def contando(**kw):
        montadas.append(kw)
        return original(**kw)

    monkeypatch.setattr(almoxarifado, "opcoes_saida", contando)
    return montadas


@pytest.fixture
def logado(client):
    montar_cenario()
    # A saída avulsa só lista material com saldo: o "ITEM ANTIGO" do cenário vem zerado.
    Material.objects.filter(codigo="000.000.900").update(estoque=Decimal(10))
    usuario = get_user_model().objects.create_user(username="12345", password="x")
    client.force_login(usuario)
    return usuario


def postar_publico(client, fluxo, itens_enviados):
    dados = {
        "token": emitir(aberto_em=time.time() - 60).token,
        "solicitante": "Ana",
        "destino": "ETA II",
        "obs": "",
        "confirmacao_extra": "",
        "item_codigo": [c for c, _ in itens_enviados],
        "item_qtd": [q for _, q in itens_enviados],
    }
    url = reverse("pedidos:formulario", args=[fluxo])
    return client.post(url, dados, HTTP_HX_REQUEST="true")


@pytest.mark.parametrize(
    ("fluxo", "itens_enviados"),
    [("limpeza", [("023.001.002", "2")]), ("ab", [("016.005.010", "1")])],
)
def test_envio_publico_monta_o_catalogo_uma_vez(
    client, monkeypatch, catalogos, fluxo, itens_enviados
):
    montar_cenario()
    monkeypatch.setattr(servicos, "notificar_pedido", lambda pedido, url_painel="": "enviado")
    r = postar_publico(client, fluxo, itens_enviados)
    assert r.status_code == 200 and Pedido.objects.count() == 1
    assert len(catalogos) == 1


def test_envio_publico_recusado_tambem_monta_uma_vez(client, catalogos):
    montar_cenario()
    r = postar_publico(client, "limpeza", [("023.001.002", "101")])
    assert r.status_code == 200 and not Pedido.objects.exists()
    assert "Corrija" in r.text
    assert len(catalogos) == 1


def dados_avulsa(**extra):
    dados = {
        "data": timezone.localdate().isoformat(),
        "recebedor": "João Fictício",
        "centro_custo": "ETA II",
        "tipo": "BALCÃO",
        "placa": "",
        "obs": "",
        "item_codigo": ["000.000.900"],
        "item_qtd": ["2"],
    }
    dados.update(extra)
    return dados


def test_saida_avulsa_registrada_nao_monta_a_tela(client, logado, catalogos, telas):
    r = client.post(reverse("pedidos:avulsa"), dados_avulsa(envio_id=str(uuid.uuid4())))
    assert r.status_code == 302 and Pedido.objects.count() == 1
    assert len(catalogos) == 1 and telas == []


def test_saida_avulsa_recusada_volta_a_tela_com_o_que_veio(client, logado, catalogos, telas):
    r = client.post(
        reverse("pedidos:avulsa"), dados_avulsa(envio_id=str(uuid.uuid4()), recebedor="")
    )
    assert r.status_code == 200 and "Informe quem recebeu o material." in r.text
    assert 'value="000.000.900"' in r.text  # o carrinho enviado volta
    assert len(catalogos) == 1 and telas == [{"so_ativos": True}]


def test_saida_avulsa_com_envio_invalido_volta_a_tela(client, logado, telas):
    r = client.post(reverse("pedidos:avulsa"), dados_avulsa(envio_id="x"))
    assert r.status_code == 200
    assert "Identificador do envio inválido. Recarregue a página." in r.text
    assert 'value="000.000.900"' in r.text and len(telas) == 1


@pytest.fixture
def avulsa(logado):
    r = servicos.registrar_saida_avulsa(
        uuid.uuid4(),
        EnvioSaida(saida(), itens(("023.004.001", "1"))),
        usuario=logado,
        hoje=date(2026, 10, 9),
    )
    assert r.ok, r.erros
    return r.pedido


def test_edicao_da_avulsa_salva_monta_o_catalogo_uma_vez(client, avulsa, catalogos, telas):
    dados = dados_avulsa(versao="0", item_codigo=["023.004.001"], item_qtd=["3"])
    r = client.post(reverse("pedidos:editar", args=[avulsa.numero]), dados)
    assert r.status_code == 302
    assert ItemPedido.objects.get(codigo="023.004.001").qtd_entregue == Decimal(3)
    assert len(catalogos) == 1 and telas == []


def test_edicao_da_avulsa_recusada_volta_a_tela_de_edicao(client, avulsa, catalogos, telas):
    dados = dados_avulsa(versao="0", recebedor="", item_codigo=["023.004.001"], item_qtd=["3"])
    r = client.post(reverse("pedidos:editar", args=[avulsa.numero]), dados)
    assert r.status_code == 200 and "data-editando" in r.text
    assert "Informe quem recebeu o material." in r.text
    assert len(catalogos) == 1 and len(telas) == 1
