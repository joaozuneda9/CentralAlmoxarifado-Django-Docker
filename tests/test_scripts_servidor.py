import io
import os
import shutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from catalogo.models import Importacao
from pedidos.models import ExecucaoRobo

RAIZ = Path(__file__).resolve().parent.parent
DEPLOY = RAIZ / "deploy"


@pytest.mark.django_db
def test_sem_robo_em_andamento():
    saida = io.StringIO()
    call_command("robos_em_andamento", stdout=saida)
    assert "Nenhum robô em andamento." in saida.getvalue()


@pytest.mark.django_db
def test_lancamento_ou_importacao_em_andamento_param_a_atualizacao():
    e = ExecucaoRobo.objects.create(simulacao=True)
    Importacao.objects.create(tipo=Importacao.Tipo.ESTOQUE)
    with pytest.raises(CommandError) as erro:
        call_command("robos_em_andamento")
    assert f"Simulação #{e.pk}" in str(erro.value) and "Importação de Estoque" in str(erro.value)


@pytest.mark.django_db
def test_execucao_interrompida_nao_conta():
    ExecucaoRobo.objects.create(inicio=timezone.now() - timedelta(hours=2))
    call_command("robos_em_andamento", stdout=io.StringIO())


def _linhas_crontab():
    texto = (DEPLOY / "crontab").read_text(encoding="utf-8")
    return [
        linha.split(None, 5)
        for linha in texto.splitlines()
        if linha.strip() and not linha.startswith("#")
    ]


def test_crontab_mantem_os_horarios_do_agendador():
    # O estoque de 30 em 30 minutos das 07:00 às 17:00 só nos dias úteis; o resto todo dia.
    agenda = {tuple(campos[:5]): campos[5] for campos in _linhas_crontab()}
    assert agenda == {
        ("*/30", "7-16", "*", "*", "1-5"): "/app/deploy/tarefa.sh importar_estoque",
        ("0", "17", "*", "*", "1-5"): "/app/deploy/tarefa.sh importar_estoque",
        # O SCPI só é estável das 7h às 17h (spec 010, R19): o catálogo saiu das 06:30.
        ("15", "7", "*", "*", "*"): "/app/deploy/tarefa.sh atualizar_catalogo",
        ("0", "23", "*", "*", "*"): "/app/deploy/tarefa.sh backup_banco",
    }


@pytest.mark.parametrize(
    "nome",
    ["deploy/crontab", "deploy/tarefa.sh", "deploy/atualizar.sh", "Dockerfile", "compose.yaml"],
)
def test_arquivos_do_container_com_fim_de_linha_lf(nome):
    # Com CRLF, o bash recusa o script ("set: -\r") e o supercronic lê o comando com \r.
    dados = (RAIZ / nome).read_bytes()
    assert b"\r\n" not in dados and dados.endswith(b"\n")


def _bash() -> str:
    """O bash do Git no Windows (o `bash` do PATH lá é o do WSL); fora dele, o do PATH."""
    if sys.platform == "win32":
        git = shutil.which("git")
        if git:
            for pasta in Path(git).parents:
                candidato = pasta / "bin" / "bash.exe"
                if candidato.exists():
                    return str(candidato)
        pytest.skip("sem o bash do Git")
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("sem bash")
    return bash


def test_tarefa_repassa_o_codigo_de_saida(tmp_path):
    ambiente = {
        **os.environ,
        "TAREFA_LOG": (tmp_path / "agendador.log").as_posix(),
        "TAREFA_PYTHON": Path(sys.executable).as_posix(),
    }
    script = (DEPLOY / "tarefa.sh").as_posix()
    ok = subprocess.run([_bash(), script, "check"], env=ambiente, timeout=120)
    falha = subprocess.run([_bash(), script, "comando_que_nao_existe"], env=ambiente, timeout=120)
    assert ok.returncode == 0 and falha.returncode != 0
    log = (tmp_path / "agendador.log").read_text(encoding="utf-8", errors="replace")
    assert "=== " in log and "comando_que_nao_existe" in log


def test_atualizador_legado_recusa_sem_executar_git_ou_docker(tmp_path):
    # Mesmo numa pasta com dados reais, o caminho antigo deve falhar antes de agir.
    marcador = tmp_path / "comando-executado"
    ambiente = {**os.environ, "MARCADOR_DEPLOY": str(marcador)}
    script = (DEPLOY / "atualizar.sh").as_posix()
    comando = (
        'git() { touch "$MARCADOR_DEPLOY"; }; '
        'docker() { touch "$MARCADOR_DEPLOY"; }; '
        f'export -f git docker; bash "{script}"'
    )
    resultado = subprocess.run(
        [_bash(), "-c", comando], env=ambiente, capture_output=True, text=True, timeout=30
    )
    assert resultado.returncode != 0
    assert "bloqueado" in resultado.stderr
    assert not marcador.exists()
