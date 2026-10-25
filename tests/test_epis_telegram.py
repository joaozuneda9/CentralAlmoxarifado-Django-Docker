"""Avisos do Telegram do formulário de EPIs (spec 008, FR-026, FR-027, FR-028): a Segurança do
Trabalho é avisada ao registrar; o almoxarifado, só depois de autorizado."""

import json
from urllib.error import URLError

import pytest

from pedidos.models import Pedido
from tests.epis_cenario import LUVA, enviar, montar_epis

pytestmark = pytest.mark.django_db


class Resposta200:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


@pytest.fixture
def telegram(settings, monkeypatch):
    """Telegram configurado com dois chats; devolve as mensagens enviadas (chat, texto, botão)."""
    settings.TELEGRAM_TOKEN = "t"
    settings.TELEGRAM_CHAT_ID = "almox"
    settings.TELEGRAM_CHAT_ID_SEGURANCA = "seg"
    enviadas = []

    def falso(req, timeout):
        corpo = json.loads(req.data)
        botao = corpo.get("reply_markup", {}).get("inline_keyboard", [[{}]])[0][0]
        enviadas.append((corpo["chat_id"], corpo["text"], botao))
        return Resposta200()

    monkeypatch.setattr("pedidos.telegram.urlopen", falso)
    return enviadas


def test_ao_registrar_so_o_chat_da_seguranca_do_trabalho_recebe(
    client, telegram, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        enviar(client, [(LUVA, "2")])
    pedido = Pedido.objects.get()
    assert [chat for chat, _, _ in telegram] == ["seg"]
    chat, texto, botao = telegram[0]
    assert f"Pedido de EPIs {pedido.numero}" in texto and "aguardando autorização" in texto
    assert "Marcos Pereira" in texto and "LUVA DE VAQUETA (013.005.100)" in texto
    assert botao["text"] == "Abrir fila" and botao["url"].endswith("/painel/autorizacoes/")


def test_sem_o_chat_da_seguranca_nada_sai_e_o_pedido_fica(
    client, telegram, settings, django_capture_on_commit_callbacks
):
    settings.TELEGRAM_CHAT_ID_SEGURANCA = ""
    with django_capture_on_commit_callbacks(execute=True):
        r = enviar(client, [(LUVA, "2")])
    assert telegram == [] and "Pedido registrado" in r.text
    assert Pedido.objects.count() == 1


def test_falha_do_envio_nao_desfaz_o_pedido(
    client, telegram, monkeypatch, django_capture_on_commit_callbacks
):
    def falha(req, timeout):
        raise URLError("sem rede")

    monkeypatch.setattr("pedidos.telegram.urlopen", falha)
    with django_capture_on_commit_callbacks(execute=True):
        r = enviar(client, [(LUVA, "2")])
    assert "Pedido registrado" in r.text and Pedido.objects.count() == 1


def test_reenvio_igual_nao_reavisa(client, telegram, django_capture_on_commit_callbacks):
    import time

    from pedidos.protecao import emitir

    token = emitir(aberto_em=time.time() - 60)
    with django_capture_on_commit_callbacks(execute=True):
        enviar(client, [(LUVA, "1")], token=token)
    with django_capture_on_commit_callbacks(execute=True):
        enviar(client, [(LUVA, "1")], token=token)
    assert len(telegram) == 1


def test_o_pedido_de_outro_formulario_continua_avisando_o_almoxarifado(
    client, telegram, django_capture_on_commit_callbacks
):
    import time

    from django.urls import reverse

    from pedidos.protecao import emitir

    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("pedidos:formulario", args=["ab"]),
            {
                "token": emitir(aberto_em=time.time() - 60).token,
                "solicitante": "Marcos Pereira",
                "destino": "ETA I",
                "obs": "",
                "item_codigo": ["016.005.010"],
                "item_qtd": ["1"],
            },
            HTTP_HX_REQUEST="true",
        )
    assert [chat for chat, _, _ in telegram] == ["almox"]


def test_ao_autorizar_so_o_chat_do_almoxarifado_recebe_uma_vez(
    telegram, django_capture_on_commit_callbacks
):
    from pedidos.servicos import decidir_autorizacao
    from tests.epis_cenario import registrar, usuarios

    quem = usuarios()
    pedido = registrar()
    with django_capture_on_commit_callbacks(execute=True):
        r = decidir_autorizacao(
            pedido.numero, "autorizar", "", quem["seguranca"], url_painel="https://almox/painel/"
        )
    assert r.ok
    chats = [chat for chat, _, _ in telegram]
    assert chats == ["almox"]
    chat, texto, botao = telegram[0]
    assert f"Pedido {pedido.numero}" in texto and "Pedido de EPIs" in texto
    assert botao == {"text": "Abrir painel", "url": "https://almox/painel/"}
    # A segunda tentativa não avisa de novo.
    with django_capture_on_commit_callbacks(execute=True):
        decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    assert len(telegram) == 1


def test_ao_recusar_nenhum_chat_recebe(telegram, django_capture_on_commit_callbacks):
    from pedidos.servicos import decidir_autorizacao
    from tests.epis_cenario import registrar, usuarios

    quem = usuarios()
    pedido = registrar()
    with django_capture_on_commit_callbacks(execute=True):
        decidir_autorizacao(pedido.numero, "recusar", "Sem laudo", quem["seguranca"])
    assert telegram == []


def test_autorizar_sem_o_chat_do_almoxarifado_nao_desfaz_a_decisao(
    telegram, settings, django_capture_on_commit_callbacks
):
    from pedidos.models import AutorizacaoPedido
    from pedidos.servicos import decidir_autorizacao
    from tests.epis_cenario import registrar, usuarios

    settings.TELEGRAM_CHAT_ID = ""
    quem = usuarios()
    pedido = registrar()
    with django_capture_on_commit_callbacks(execute=True):
        r = decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    assert r.ok and r.telegram == "sem_configuracao" and telegram == []
    assert AutorizacaoPedido.objects.get(pedido=pedido).situacao == "AUTORIZADO"
