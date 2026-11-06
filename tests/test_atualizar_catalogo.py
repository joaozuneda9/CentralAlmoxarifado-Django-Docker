import subprocess
import sys
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command
from django.utils import timezone

from catalogo.models import Importacao
from scpi.disparo import iniciar_atualizacao

pytestmark = pytest.mark.django_db


def test_atualizar_roda_os_tres_e_segue_depois_de_uma_falha(monkeypatch, capsys, caplog):
    feitos = []

    def falso(nome, *args, **kwargs):
        feitos.append(nome)
        if nome == "importar_cadastro":
            raise CommandError("Cadastro: o CSV não tem nenhum material; nada foi alterado.")

    monkeypatch.setattr("scpi.management.commands.atualizar_catalogo.call_command", falso)
    with pytest.raises(CommandError, match=r"^Falharam: importar_cadastro\.$"):
        call_command("atualizar_catalogo")
    assert feitos == [
        "importar_cadastro",
        "importar_estoque",
        "importar_saidas_scpi",
        "conciliar_lancamentos",
    ]
    assert "Cadastro: o CSV não tem nenhum material" in capsys.readouterr().err
    assert any(
        r.name == "scpi" and "importar_cadastro" in r.getMessage() and r.levelname == "ERROR"
        for r in caplog.records
    )


def test_atualizar_sem_falhas_termina_bem(monkeypatch):
    monkeypatch.setattr(
        "scpi.management.commands.atualizar_catalogo.call_command", lambda *a, **k: None
    )
    call_command("atualizar_catalogo")


def test_disparo_inicia_processo_separado(monkeypatch):
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: chamadas.append((args, kw)))
    assert iniciar_atualizacao() is True
    args, kw = chamadas[0]
    assert args[1:] == [str(settings.BASE_DIR / "manage.py"), "atualizar_catalogo"]
    assert kw["cwd"] == settings.BASE_DIR
    assert kw["stdin"] == subprocess.DEVNULL and kw["close_fds"] is True
    assert kw["stderr"] == subprocess.STDOUT


def test_disparo_grava_a_saida_do_processo_num_arquivo_de_log(monkeypatch, settings, tmp_path):
    """O que o processo relata (recusa pela trava, falhas, erro ao subir o Django) precisa
    ficar em algum lugar: vai para logs/atualizar_catalogo.log."""
    settings.LOG_DIR = tmp_path
    arquivos = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: arquivos.append(kw["stdout"]))
    iniciar_atualizacao()
    assert arquivos[0].name == str(tmp_path / "atualizar_catalogo.log")
    assert arquivos[0].closed  # o processo filho herda o arquivo; o pai fecha a sua cópia
    assert (tmp_path / "atualizar_catalogo.log").exists()


def test_disparo_fora_do_windows_abre_sessao_propria(monkeypatch):
    """No container, o robô fica numa sessão própria: não recebe os sinais do grupo do
    waitress, o paralelo do DETACHED_PROCESS do Windows."""
    monkeypatch.setattr(sys, "platform", "linux")
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: chamadas.append(kw))
    iniciar_atualizacao()
    assert chamadas[0]["start_new_session"] is True
    assert chamadas[0]["creationflags"] == 0


@pytest.mark.skipif(sys.platform != "win32", reason="flags do Windows")
def test_disparo_no_windows_mantem_o_processo_desligado(monkeypatch):
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: chamadas.append(kw))
    iniciar_atualizacao()
    assert chamadas[0]["start_new_session"] is False
    assert chamadas[0]["creationflags"] & subprocess.DETACHED_PROCESS


def test_disparo_recusa_com_importacao_em_andamento(monkeypatch):
    Importacao.objects.create(tipo="ESTOQUE")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("não deveria iniciar"))
    assert iniciar_atualizacao() is False


def test_importacao_interrompida_nao_bloqueia_o_disparo(monkeypatch):
    Importacao.objects.create(tipo="ESTOQUE", inicio=timezone.now() - timedelta(hours=2))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)
    assert iniciar_atualizacao() is True


def test_disparo_da_carga_inicial_passa_a_opcao(monkeypatch, settings, tmp_path):
    settings.LOG_DIR = tmp_path
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: chamadas.append(args))
    assert iniciar_atualizacao(carga_inicial=True) is True
    assert chamadas[0][2:] == ["atualizar_catalogo", "--carga-inicial"]
    assert "Carga inicial completa" in (tmp_path / "atualizar_catalogo.log").read_text()


def test_carga_inicial_pede_o_cadastro_inteiro_e_as_saidas_desde_o_inicio(monkeypatch):
    chamados = []
    monkeypatch.setattr(
        "scpi.management.commands.atualizar_catalogo.call_command",
        lambda nome, *a, stdout=None, stderr=None, **extras: chamados.append((nome, extras)),
    )
    call_command("atualizar_catalogo", carga_inicial=True)
    assert chamados == [
        ("importar_cadastro", {"completo": True}),
        ("importar_estoque", {}),
        ("importar_saidas_scpi", {"desde": "01/01/2026"}),
        ("conciliar_lancamentos", {"diaria": True}),
    ]
    chamados.clear()
    call_command("atualizar_catalogo")
    assert [extras for _, extras in chamados] == [{}, {}, {}, {"diaria": True}]
