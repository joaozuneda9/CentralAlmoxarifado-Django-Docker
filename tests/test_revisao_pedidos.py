"""Achados da revisão final do subprojeto 3: entradas que davam erro 500 e o histórico."""

import uuid
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from pedidos.regras import LIMPEZA, EnvioSaida, data_valida_iso, parse_qtd_br
from pedidos.servicos import confirmar_atendimento, registrar_saida_avulsa
from tests.cenario import criar_pedido, envio_limpeza, itens, montar_cenario, registrar, saida
from tests.papeis import dar_papeis

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    montar_cenario()
    return dar_papeis(get_user_model().objects.create_user(username="12345", password="x"))


def test_centro_de_custo_com_espacos_demais_vira_erro_e_nao_500(usuario):
    longo = "ETA" + " " * 300 + "II"
    p = registrar(LIMPEZA, envio_limpeza()).pedido
    r = confirmar_atendimento(
        p.id,
        uuid.uuid4(),
        saida(centro_custo=longo),
        {"023.001.002": "2", "008.001.002": "1"},
        nao_lancar=False,
        usuario=usuario,
        hoje=date(2026, 10, 9),
    )
    assert r.ok is False and "Centro de custo: no máximo 200 caracteres." in [
        e.texto for e in r.erros
    ]
    r = registrar_saida_avulsa(
        uuid.uuid4(),
        EnvioSaida(saida(centro_custo=longo), itens(("000.000.900", "1"))),
        usuario=usuario,
        hoje=date(2026, 10, 9),
    )
    assert r.ok is False and "Centro de custo: no máximo 200 caracteres." in [
        e.texto for e in r.erros
    ]


def test_digitos_fora_do_ascii_sao_invalidos():
    assert data_valida_iso("٢٠٢٦-١٠-٠١") is False
    assert parse_qtd_br("٣") is None


def test_painel_com_data_no_limite_nao_quebra(client, usuario):
    client.force_login(usuario)
    criar_pedido()
    r = client.get(reverse("pedidos:painel"), {"ate": "9999-12-31", "de": "0001-01-01"})
    assert r.status_code == 200 and "P-000001" in r.text


def test_restaurar_historico_devolve_a_pagina_inteira(client, usuario):
    client.force_login(usuario)
    r = client.get(
        reverse("pedidos:painel"),
        {"pagina": 1},
        HTTP_HX_REQUEST="true",
        HTTP_HX_HISTORY_RESTORE_REQUEST="true",
    )
    assert 'class="app-lateral' in r.text
    assert "HX-Request" in r.headers.get("Vary", "")
