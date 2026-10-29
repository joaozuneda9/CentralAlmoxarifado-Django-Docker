import uuid
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.db import connections

from catalogo.models import trava_importacao
from pedidos.models import TRAVA_LANCAMENTO
from pedidos.regras import LIMPEZA, EnvioSaida
from pedidos.servicos import confirmar_atendimento, registrar_saida_avulsa
from tests.cenario import envio_limpeza, itens, montar_cenario, registrar, saida
from tests.epis_cenario import usuarios as usuarios_epis
from tests.scpi_simulado import SCPISimulado

HOJE = date(2026, 10, 9)


@pytest.fixture
def dois_lotes():
    """Dois lotes `PENDENTE` prontos para o robô: um pedido de limpeza atendido (`P-`, 2
    linhas) e uma saída avulsa (`AV-`, 1 linha), nesta ordem. Devolve os dois números."""
    montar_cenario()
    usuario = get_user_model().objects.create_user(username="12345", password="x")
    pedido = registrar(LIMPEZA, envio_limpeza()).pedido
    r = confirmar_atendimento(
        pedido.id,
        uuid.uuid4(),
        saida(),
        {"023.001.002": "2", "008.001.002": "1,5"},
        nao_lancar=False,
        usuario=usuario,
        hoje=HOJE,
    )
    assert r.ok, r.erros
    av = registrar_saida_avulsa(
        uuid.uuid4(),
        EnvioSaida(saida(), itens(("023.004.001", "1"))),
        usuario=usuario,
        hoje=HOJE,
    )
    assert av.ok, av.erros
    return pedido.numero, av.numero


@pytest.fixture
def usuario_logado(client):
    usuario = get_user_model().objects.create_user(username="12345", password="x")
    client.force_login(usuario)
    return usuario


@pytest.fixture
def quem():
    """Os usuários do cenário dos EPIs (`tests/epis_cenario.py`)."""
    return usuarios_epis()


@pytest.fixture
def journal(settings, tmp_path):
    """Aponta o `LOG_DIR` (onde fica o journal do lançamento) para uma pasta temporária."""
    settings.LOG_DIR = tmp_path
    return tmp_path


@pytest.fixture
def scpi():
    return SCPISimulado()


@pytest.fixture
def scpi_no_comando(monkeypatch, scpi):
    """O comando `lancar_saidas` abre o SCPI simulado em vez do navegador."""
    monkeypatch.setattr("scpi.management.commands.lancar_saidas.navegador", scpi.abrir)
    return scpi


@pytest.fixture
def trava_importacao_ocupada():
    """Devolve `ocupar(tipo)`: outra conexão passa a segurar a trava do tipo, como o processo da
    importação rodando. As conexões caem no fim do teste."""
    conexoes = []

    def ocupar(tipo):
        outra = connections.create_connection("default")
        conexoes.append(outra)
        with outra.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0)", [trava_importacao(tipo)])

    try:
        yield ocupar
    finally:
        for outra in conexoes:
            outra.close()


@pytest.fixture
def trava_ocupada():
    """Outra conexão segura a trava do lançamento, como o processo do robô rodando."""
    outra = connections.create_connection("default")
    try:
        with outra.cursor() as c:
            c.execute("SELECT GET_LOCK(%s, 0)", [TRAVA_LANCAMENTO])
        yield
    finally:
        outra.close()
