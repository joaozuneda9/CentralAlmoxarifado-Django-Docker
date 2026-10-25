import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pedidos.models import Pedido
from pedidos.protecao import emitir, ler, recusar
from pedidos.regras import LIMPEZA
from pedidos.servicos import (
    MENSAGEM_LIMITE_IP,
    MENSAGEM_LIMITE_SOLICITANTE,
    registrar_pedido,
)
from tests.cenario import criar_pedido, envio_limpeza, itens, montar_cenario, registrar

pytestmark = pytest.mark.django_db

AGORA = datetime(2026, 10, 9, 15, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()


def test_tres_pedidos_do_mesmo_ip_em_10_minutos_e_o_quarto_e_recusado():
    for minutos in (9, 5, 1):
        criar_pedido(ip="10.0.0.1", criado_em=AGORA - timedelta(minutes=minutos))
    r = registrar(LIMPEZA, envio_limpeza(), ip="10.0.0.1", agora=AGORA)
    assert (r.ok, r.mensagem) == (False, MENSAGEM_LIMITE_IP)
    assert MENSAGEM_LIMITE_IP == (
        "Muitos pedidos enviados desta rede em pouco tempo. Procure o almoxarifado."
    )
    assert Pedido.objects.count() == 3
    assert registrar(LIMPEZA, envio_limpeza(), ip="10.0.0.2", agora=AGORA).ok


def test_pedidos_de_mais_de_10_minutos_nao_contam_no_limite_curto():
    for minutos in (30, 20, 11):
        criar_pedido(ip="10.0.0.1", criado_em=AGORA - timedelta(minutes=minutos))
    assert registrar(LIMPEZA, envio_limpeza(), ip="10.0.0.1", agora=AGORA).ok


def test_dez_pedidos_no_dia_pelo_mesmo_ip_e_ontem_nao_conta():
    for horas in range(1, 10):
        criar_pedido(
            ip="10.0.0.1", solicitante=f"P{horas}", criado_em=AGORA - timedelta(hours=horas)
        )
    criar_pedido(ip="10.0.0.1", solicitante="Ontem", criado_em=AGORA - timedelta(days=1))
    assert registrar(LIMPEZA, envio_limpeza(), ip="10.0.0.1", agora=AGORA).ok  # 10º do dia
    criar_pedido(ip="10.0.0.1", solicitante="Outro", criado_em=AGORA - timedelta(hours=11))
    r = registrar(LIMPEZA, envio_limpeza(solicitante="Zé"), ip="10.0.0.1", agora=AGORA)
    assert (r.ok, r.mensagem) == (False, MENSAGEM_LIMITE_IP)


def test_cinco_pedidos_no_dia_pelo_mesmo_nome_de_qualquer_ip():
    for n in range(5):
        criar_pedido(ip=f"10.0.1.{n}", solicitante="Ana", criado_em=AGORA - timedelta(hours=n + 1))
    criar_pedido(ip="10.0.2.1", solicitante="Ana", criado_em=AGORA - timedelta(days=1))
    r = registrar(LIMPEZA, envio_limpeza(solicitante="ana"), ip="10.0.9.9", agora=AGORA)
    assert (r.ok, r.mensagem) == (False, MENSAGEM_LIMITE_SOLICITANTE)
    assert MENSAGEM_LIMITE_SOLICITANTE == (
        "Limite de pedidos por dia atingido para este nome. Procure o almoxarifado."
    )


def test_reenvio_nao_conta_no_limite():
    envio_id = uuid.uuid4()
    for minutos in (5, 1):
        criar_pedido(ip="10.0.0.1", criado_em=AGORA - timedelta(minutes=minutos))
    assert registrar_pedido(LIMPEZA, envio_id, envio_limpeza(), ip="10.0.0.1", agora=AGORA).ok
    r = registrar_pedido(LIMPEZA, envio_id, envio_limpeza(), ip="10.0.0.1", agora=AGORA)
    assert r.ok and r.reenvio


def test_tamanhos():
    muitos = itens(*[(f"023.001.{n:03d}", "1") for n in range(41)])
    r = registrar(LIMPEZA, envio_limpeza(itens=muitos, obs="x" * 201))
    textos = [e.texto for e in r.erros]
    assert "O pedido pode ter no máximo 40 materiais. Divida em mais de um pedido." in textos
    assert "Observação: no máximo 200 caracteres." in textos
    assert not Pedido.objects.exists()


def test_token_ida_e_volta_e_adulterado():
    envio = emitir()
    lido = ler(envio.token)
    assert (lido.id, lido.aberto_em) == (envio.id, envio.aberto_em)
    adulterado = envio.token[:-1] + ("A" if envio.token[-1] != "A" else "B")
    assert ler(adulterado) is None
    assert ler("lixo") is None
    assert ler("") is None


def test_recusar_devolve_o_motivo(settings):
    agora = time.time()
    assert recusar(emitir(aberto_em=agora - 60), "x", agora) == "isca"
    assert recusar(emitir(aberto_em=agora - 2), "", agora) == "rapido"
    assert recusar(emitir(aberto_em=agora - 2), "x", agora) == "isca"  # a isca vale mais
    assert recusar(emitir(aberto_em=agora - 10), "", agora) is None
    settings.PEDIDOS_TEMPO_MINIMO = 0
    assert recusar(emitir(aberto_em=agora), "", agora) is None
