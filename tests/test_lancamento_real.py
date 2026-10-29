import re

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.urls import reverse

from pedidos.models import ExecucaoRobo, LinhaSaida
from scpi.lancamento import LANCAMENTO_BLOQUEADO
from tests.test_config import PRODUCAO, RAIZ, rodar

# O comando abre o SCPI simulado.
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("scpi_no_comando")]


@pytest.fixture(autouse=True)
def _bloqueado(settings, journal):
    settings.LANCAMENTO_REAL = False


@pytest.fixture
def usuario_logado(client):
    # A matrícula 12345 já é do fixture `dois_lotes`.
    usuario = get_user_model().objects.create_user(username="54321", password="x")
    client.force_login(usuario)
    return usuario


def test_comando_recusa_lancamento_real_sem_criar_execucao(dois_lotes, scpi):
    with pytest.raises(CommandError, match="bloqueado"):
        call_command("lancar_saidas", "--lote", dois_lotes[0])
    assert ExecucaoRobo.objects.count() == 0 and scpi.chamadas == []
    assert set(LinhaSaida.objects.values_list("status", flat=True)) == {"PENDENTE"}


def test_execucao_real_do_botao_termina_em_falha(dois_lotes, scpi):
    e = ExecucaoRobo.objects.create(simulacao=False)
    with pytest.raises(CommandError, match="bloqueado"):
        call_command("lancar_saidas", "--execucao", str(e.pk), "--lote", dois_lotes[0])
    e.refresh_from_db()
    assert e.situacao == "FALHA" and "bloqueado" in e.erro and e.fim is not None
    assert scpi.chamadas == []


def test_simulacao_roda_com_o_bloqueio(dois_lotes):
    call_command("lancar_saidas", "--dry-run", "--lote", dois_lotes[0], "--lote", dois_lotes[1])
    assert ExecucaoRobo.objects.get().resumo["simuladas"] == 2


@pytest.mark.parametrize("dados", [{}, {"modo": "lancar"}])
def test_botao_lancar_recusado_com_mensagem(client, usuario_logado, monkeypatch, dados):
    monkeypatch.setattr(
        "automacoes.views.iniciar_lancamento",
        lambda *a, **k: pytest.fail("não deveria iniciar"),
    )
    r = client.post(reverse("automacoes:lancar"), dados, follow=True)
    # A mensagem da recusa, não só o aviso fixo da página.
    assert LANCAMENTO_BLOQUEADO in r.content.decode()


def test_simulacao_pelo_botao_continua(client, usuario_logado, dois_lotes, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "automacoes.views.iniciar_lancamento",
        lambda usuario, **k: chamadas.append(k) or ExecucaoRobo(pk=1),
    )
    client.post(reverse("automacoes:lancar"), {"simulacao": "1", "lotes": [dois_lotes[0]]})
    assert chamadas == [{"simulacao": True, "lotes": [dois_lotes[0]]}]


@pytest.mark.parametrize("rota", ["automacoes:pagina", "pedidos:painel"])
def test_paginas_mostram_o_bloqueio(client, usuario_logado, dois_lotes, settings, rota):
    html = client.get(reverse(rota)).content.decode()
    assert "Lançamento real bloqueado" in html
    settings.LANCAMENTO_REAL = True
    assert "Lançamento real bloqueado" not in client.get(reverse(rota)).content.decode()


def test_lancar_bloqueado_no_painel_recebe_foco_e_nao_envia(client, usuario_logado, dois_lotes):
    """Com `disabled` o botão sairia do Tab, e a dica do motivo, do alcance do teclado."""
    html = client.get(reverse("pedidos:painel")).content.decode()
    botao = re.search(r'<button[^>]*aria-describedby="dica-lancamento-real"[^>]*>', html)
    assert botao, html
    assert 'type="button"' in botao.group(0) and 'aria-disabled="true"' in botao.group(0)
    assert " disabled" not in botao.group(0)


@pytest.mark.parametrize("valor", [None, ""], ids=["ausente", "vazia"])
def test_sem_a_variavel_o_lancamento_real_fica_bloqueado(valor):
    codigo = (
        "import django, os; django.setup(); from django.conf import settings; "
        "print(settings.LANCAMENTO_REAL, 'LANCAMENTO_REAL' in os.environ)"
    )
    r = rodar(["-c", codigo], **{**PRODUCAO, "LANCAMENTO_REAL": valor})
    assert r.stdout.split() == ["False", str(valor is not None)], r.stderr


def test_env_exemplo_documenta_o_bloqueio():
    assert "\nLANCAMENTO_REAL=0\n" in (RAIZ / ".env.example").read_text(encoding="utf-8")
