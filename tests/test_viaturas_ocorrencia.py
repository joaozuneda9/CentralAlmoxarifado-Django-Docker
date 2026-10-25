"""Número da ocorrência do pedido de viaturas (spec 006, FR-002a): opcional, até 20
caracteres, gravado no pedido e comparado no reenvio; os outros formulários não o têm."""

import uuid

import pytest

from catalogo.models import Material, PecaViatura
from pedidos.models import Pedido
from pedidos.regras import (
    LIMPEZA,
    MAX_OCORRENCIA,
    VIATURAS,
    Centro,
    EnvioPedido,
    cabecalho_enviado,
    validar_pedido,
)
from pedidos.servicos import registrar_pedido
from tests.cenario import envio_limpeza, itens, montar_cenario
from tests.config_cenario import criar_centro

pytestmark = pytest.mark.django_db

FITA = "016.005.010"
CENTROS = [Centro("EQUIPE NORTE", "51")]


def envio(**extra):
    campos = {
        "solicitante": "Carlos",
        "destino": "EQUIPE NORTE",
        "itens": itens((FITA, "2")),
        "ocorrencia": "1234/2026",
    }
    campos.update(extra)
    return EnvioPedido(**campos)


def erros(e):
    """Os erros de campo do envio (sem itens: o tamanho da ocorrência não depende deles)."""
    return [(x.campo, x.texto) for x in validar_pedido(e, [], CENTROS).erros if x.campo]


@pytest.fixture
def viaturas():
    montar_cenario()
    criar_centro("EQUIPE NORTE", "51", formularios=[VIATURAS])
    PecaViatura.objects.create(material=Material.objects.get(codigo=FITA))


def test_limite_de_20_caracteres_sem_contar_as_pontas():
    assert MAX_OCORRENCIA == 20
    assert erros(envio(ocorrencia="x" * 20, itens=())) == []
    assert erros(envio(ocorrencia="  " + "x" * 20 + "  ", itens=())) == []
    assert erros(envio(ocorrencia="x" * 21, itens=())) == [
        ("ocorrencia", "Nº da ocorrência: no máximo 20 caracteres.")
    ]


def test_o_cabecalho_do_reenvio_inclui_a_ocorrencia():
    assert cabecalho_enviado(VIATURAS, envio()) == (
        "Carlos",
        "EQUIPE NORTE",
        "",
        "1234/2026",
    )


def test_a_ocorrencia_e_gravada_e_o_reenvio_compara(viaturas):
    envio_id = uuid.uuid4()
    r = registrar_pedido(VIATURAS, envio_id, envio(ocorrencia=" 1234/2026 "))
    assert r.ok, r.erros
    assert Pedido.objects.get().ocorrencia == "1234/2026"
    assert registrar_pedido(VIATURAS, envio_id, envio()).reenvio
    assert registrar_pedido(VIATURAS, envio_id, envio(ocorrencia="99")).divergente


def test_ocorrencia_em_branco_e_aceita(viaturas):
    assert registrar_pedido(VIATURAS, uuid.uuid4(), envio(ocorrencia="")).ok
    assert Pedido.objects.get().ocorrencia == ""


def test_os_outros_formularios_ignoram_a_ocorrencia(viaturas):
    envio_id = uuid.uuid4()
    assert registrar_pedido(LIMPEZA, envio_id, envio_limpeza(ocorrencia="77")).ok
    assert Pedido.objects.get().ocorrencia == ""
    # O pedido antigo (ocorrência vazia) continua conferindo no reenvio.
    assert registrar_pedido(LIMPEZA, envio_id, envio_limpeza()).reenvio
