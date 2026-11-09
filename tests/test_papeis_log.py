"""O registro das recusas de acesso (spec 012, US5, FR-017 e FR-018, contracts/recusa.md): uma linha
no logger `contas.acesso` por recusa, nas quatro origens, sem dados do pedido."""

import logging
import re
import subprocess
from urllib.parse import unquote

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from contas.acesso import GRUPO_ATENDIMENTO, GRUPO_GESTAO
from pedidos.regras import LIMPEZA
from scpi.disparo import iniciar_lancamento
from tests.cenario import envio_limpeza, montar_cenario, registrar
from tests.epis_cenario import montar_epis
from tests.papeis import usuario_com

pytestmark = pytest.mark.django_db

LINHA = re.compile(r"^Acesso recusado: matricula=\S+ rota=\S+ metodo=\S+ falta=\S+$")


@pytest.fixture
def recusas(caplog):
    """As mensagens do logger `contas.acesso` (que não propaga para a raiz)."""
    logger = logging.getLogger("contas.acesso")
    logger.addHandler(caplog.handler)
    yield lambda: [r.getMessage() for r in caplog.records if r.name == "contas.acesso"]
    logger.removeHandler(caplog.handler)


def cliente(usuario):
    c = Client(raise_request_exception=False)
    c.force_login(usuario)
    return c


def test_recusa_do_middleware(recusas):
    cliente(usuario_com(GRUPO_ATENDIMENTO)).post(reverse("automacoes:lancar"))
    assert recusas() == [
        "Acesso recusado: matricula=12345 rota=automacoes:lancar metodo=POST "
        "falta=contas.operar_automacoes"
    ]


def test_matricula_com_espaco_ou_quebra_de_linha_nao_cria_campo_nem_linha(recusas):
    usuario = usuario_com(GRUPO_ATENDIMENTO, username="12 3\nfalta=x%")
    cliente(usuario).post(reverse("automacoes:lancar"))
    (linha,) = recusas()
    assert "\n" not in linha and LINHA.match(linha)
    assert "matricula=12%203%0Afalta=x%25 " in linha
    assert unquote("12%203%0Afalta=x%25") == usuario.username


def test_recusa_da_seguranca_do_trabalho_so_fora_do_get(recusas, quem):
    c = cliente(quem["seguranca"])
    c.get(reverse("pedidos:painel"))
    assert recusas() == []
    c.post(reverse("pedidos:painel"))
    assert recusas() == [
        "Acesso recusado: matricula=70001 rota=pedidos:painel metodo=POST "
        "falta=grupo:Segurança do Trabalho"
    ]


def test_recusa_das_views_de_autorizacao(recusas):
    montar_epis()
    cliente(usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO)).get(reverse("pedidos:autorizacoes"))
    assert recusas() == [
        "Acesso recusado: matricula=12345 rota=pedidos:autorizacoes metodo=GET "
        "falta=grupo:Segurança do Trabalho"
    ]


def test_recusa_do_criterio_da_pagina_formularios(recusas):
    """Quem passa pela tabela (lê a página) mas não grava: a recusa vem da view (spec 009)."""
    montar_cenario()
    c = cliente(usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO))
    r = c.post(reverse("catalogo:formularios_lote"), {"formulario": "AB", "acao": "retirar"})
    assert r.status_code == 403
    assert recusas() == [
        "Acesso recusado: matricula=12345 rota=catalogo:formularios_lote metodo=POST "
        "falta=is_staff,catalogo.change_excecaomaterial"
    ]


def test_recusa_do_disparo(recusas, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("subiu processo"))
    usuario = usuario_com(GRUPO_ATENDIMENTO)
    with pytest.raises(PermissionDenied):
        iniciar_lancamento(usuario, simulacao=True, lotes=["P-000001"])
    assert recusas() == [
        "Acesso recusado: matricula=12345 rota=scpi.disparo.iniciar_lancamento metodo=- "
        "falta=contas.operar_automacoes"
    ]


def test_toda_linha_tem_o_formato_e_nenhum_dado_do_pedido(recusas):
    montar_cenario()
    pedido = registrar(LIMPEZA, envio_limpeza()).pedido
    c = cliente(usuario_com(GRUPO_GESTAO))
    c.get(reverse("pedidos:detalhe", args=[pedido.numero]) + "?q=segredo")
    c.post(reverse("pedidos:atender", args=[pedido.numero]), {"recebedor": "Carla"})
    linhas = recusas()
    assert len(linhas) == 2 and all(LINHA.match(linha) for linha in linhas)
    for linha in linhas:
        for dado in (pedido.numero, pedido.solicitante, "segredo", "Carla"):
            assert dado not in linha


def test_metodo_e_csrf_de_quem_tem_a_permissao_nao_registram(recusas):
    usuario = usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO)
    assert cliente(usuario).get(reverse("automacoes:lancar")).status_code == 405
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(usuario)
    assert csrf.post(reverse("automacoes:lancar")).status_code == 403
    assert recusas() == []


def test_anonimo_nao_e_recusado_vai_ao_login(recusas):
    assert Client().get(reverse("pedidos:painel")).status_code == 302
    assert get_user_model().objects.count() == 0 and recusas() == []
