"""Destinos do formulário de viaturas (spec 006, FR-007, FR-008, FR-008a): só os centros de custo
habilitados nas viaturas (spec 009; antes, a marca de equipe de manutenção), sem placa; os outros
formulários não mudam."""

import uuid

import pytest
from django.urls import reverse

from catalogo.models import CentroCusto, CentroFormulario, Formulario
from pedidos.models import Pedido
from pedidos.regras import VIATURAS, EnvioPedido
from pedidos.servicos import registrar_pedido
from tests.cenario import itens
from tests.config_cenario import habilitar
from tests.viaturas_cenario import EQUIPE, FITA, enviar, montar_viaturas

pytestmark = pytest.mark.django_db

INDISPONIVEL = "Este formulário está indisponível no momento. Avise o almoxarifado."


@pytest.fixture(autouse=True)
def cenario():
    montar_viaturas()


def destinos(client, nome):
    html = client.get(reverse("pedidos:formulario", args=[nome])).text
    return html.split('<datalist id="destinos">')[1].split("</datalist>")[0]


def test_so_os_centros_habilitados_sem_placa(client):
    opcoes = destinos(client, "viaturas")
    assert f'<option value="{EQUIPE}">' in opcoes
    assert "ETA II" not in opcoes and "—" not in opcoes and "BBB2B22" not in opcoes
    assert (
        'placeholder="Centro de custo da equipe"'
        in client.get(reverse("pedidos:formulario", args=["viaturas"])).text
    )


@pytest.mark.parametrize("destino", ["ETA II", "BBB2B22", f"{EQUIPE} — BBB2B22"])
def test_outro_centro_ou_placa_sao_recusados(client, destino):
    r = enviar(client, [(FITA, "1")], destino=destino)
    assert "não está na lista de centros de custo" in r.text
    assert not Pedido.objects.exists()
    # O pedido é mantido para escolher outro destino.
    assert f'name="item_codigo" value="{FITA}"' in r.text


def test_sem_centro_habilitado_o_formulario_fica_indisponivel(client):
    CentroFormulario.objects.filter(formulario=Formulario.VIATURAS).delete()
    assert INDISPONIVEL in client.get(reverse("pedidos:formulario", args=["viaturas"])).text
    envio = EnvioPedido(solicitante="Carlos", destino=EQUIPE, itens=itens((FITA, "1")))
    r = registrar_pedido(VIATURAS, uuid.uuid4(), envio)
    assert not r.ok and "Não há centros de custo cadastrados" in r.mensagem


def test_centro_desabilitado_entre_abrir_e_enviar_e_recusado(client):
    client.get(reverse("pedidos:formulario", args=["viaturas"]))
    CentroFormulario.objects.filter(formulario=Formulario.VIATURAS).delete()
    habilitar(CentroCusto.objects.filter(descricao="ETA I"), Formulario.VIATURAS)
    r = enviar(client, [(FITA, "1")])
    assert "não está na lista de centros de custo" in r.text and not Pedido.objects.exists()


def test_desabilitar_depois_do_envio_nao_muda_o_pedido(client):
    assert "Pedido registrado" in enviar(client, [(FITA, "1")]).text
    CentroFormulario.objects.filter(formulario=Formulario.VIATURAS).delete()
    assert Pedido.objects.get().destino == EQUIPE


def test_limpeza_e_ab_continuam_com_todos_os_centros_e_placas(client):
    for nome in ("limpeza", "ab"):
        opcoes = destinos(client, nome)
        assert '<option value="ETA II">' in opcoes and f"{EQUIPE} — BBB2B22" in opcoes
