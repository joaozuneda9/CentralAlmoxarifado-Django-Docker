import subprocess
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.utils import timezone

from pedidos.models import ExecucaoRobo
from scpi.disparo import iniciar_lancamento
from scpi.requisicoes import ErroSCPI

# Nenhum teste grava o journal no `logs/` do repositório, e o comando abre o SCPI simulado.
from tests.papeis import dar_papeis

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("journal", "scpi_no_comando"),
]


@pytest.fixture
def usuario():
    return dar_papeis(get_user_model().objects.create_user("00012", password="x"))


def test_comando_usa_a_execucao_do_botao(dois_lotes):
    p, av = dois_lotes
    e = ExecucaoRobo.objects.create()
    call_command("lancar_saidas", "--execucao", str(e.pk), "--lote", p, "--lote", av)
    e.refresh_from_db()
    assert e.situacao == "SUCESSO" and e.resumo["lancadas"] == 2


def test_dry_run_vence_uma_execucao_real(dois_lotes, scpi):
    e = ExecucaoRobo.objects.create(simulacao=False)
    call_command("lancar_saidas", "--execucao", str(e.pk), "--dry-run", "--lote", dois_lotes[0])
    e.refresh_from_db()
    assert e.simulacao and not any(c[0] == "salvar" for c in scpi.chamadas)


def test_sem_execucao_cria_registro_de_linha_de_comando(dois_lotes):
    call_command("lancar_saidas", "--lote", dois_lotes[0])
    e = ExecucaoRobo.objects.get()
    assert e.iniciada_por is None and e.resumo["lancadas"] == 1


def test_execucao_encerrada_e_recusada():
    e = ExecucaoRobo.objects.create(situacao="SUCESSO")
    with pytest.raises(CommandError, match="não encontrada ou já encerrada"):
        call_command("lancar_saidas", "--execucao", str(e.pk), "--lote", "P-0001")


def test_falhas_viram_codigo_de_saida(dois_lotes, scpi):
    scpi.falhas_preencher[dois_lotes[0]] = ErroSCPI("x")
    with pytest.raises(CommandError, match="erros ou linhas a verificar"):
        call_command("lancar_saidas", "--lote", dois_lotes[0])


def test_disparo_cria_execucao_e_inicia_processo(monkeypatch, usuario):
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: chamadas.append(args))
    e = iniciar_lancamento(usuario, simulacao=True, lotes=["P-0001", "AV-0002"])
    assert e.iniciada_por == usuario and e.simulacao and e.situacao == "ANDAMENTO"
    assert chamadas[0][1:] == [
        str(settings.BASE_DIR / "manage.py"),
        "lancar_saidas",
        "--execucao",
        str(e.pk),
        "--dry-run",
        "--lote",
        "P-0001",
        "--lote",
        "AV-0002",
    ]


def test_disparo_recusa_com_execucao_em_andamento_mas_nao_interrompida(monkeypatch, usuario):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)
    ExecucaoRobo.objects.create()
    assert iniciar_lancamento(usuario, simulacao=False, lotes=["P-0001"]) is None
    ExecucaoRobo.objects.update(inicio=timezone.now() - timedelta(minutes=2))
    assert iniciar_lancamento(usuario, simulacao=False, lotes=["P-0001"]) is not None


def test_comando_exige_ao_menos_um_lote(dois_lotes):
    """Nada lança a fila inteira sem escolha: sem `--lote` o comando recusa, sem criar execução."""
    with pytest.raises(CommandError, match="--lote"):
        call_command("lancar_saidas")
    with pytest.raises(CommandError, match="--lote"):
        call_command("lancar_saidas", "--dry-run", "--lote", "  ")
    assert not ExecucaoRobo.objects.exists()


def test_disparo_que_nao_inicia_o_processo_encerra_a_execucao_como_falha(monkeypatch, usuario):
    def quebrar(*a, **k):
        raise OSError("python.exe não encontrado")

    monkeypatch.setattr(subprocess, "Popen", quebrar)
    with pytest.raises(OSError):
        iniciar_lancamento(usuario, simulacao=False, lotes=["P-0001"])
    e = ExecucaoRobo.objects.get()
    assert (e.situacao, e.erro) == ("FALHA", "python.exe não encontrado") and e.fim is not None
    assert not ExecucaoRobo.em_andamento().exists()


@pytest.mark.parametrize("simulacao", [True, False])
def test_disparo_sem_a_permissao_de_automacoes_nao_cria_nada(monkeypatch, simulacao):
    """Segunda barreira do lançamento (spec 012, FR-007): sem `operar_automacoes`, nem simular."""
    from django.core.exceptions import PermissionDenied

    from contas.acesso import GRUPO_ATENDIMENTO
    from tests.papeis import usuario_com

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("subiu processo"))
    # A recusa vem antes de qualquer consulta: nem a execução em andamento é procurada.
    monkeypatch.setattr(
        ExecucaoRobo, "em_andamento", lambda *a, **k: pytest.fail("consultou execução")
    )
    with pytest.raises(PermissionDenied):
        iniciar_lancamento(usuario_com(GRUPO_ATENDIMENTO), simulacao=simulacao, lotes=["P-0001"])
    assert not ExecucaoRobo.objects.exists()


def test_disparo_vale_pela_permissao_nao_pelo_grupo(monkeypatch):
    """A segunda barreira pergunta pela permissão: dada direto ao usuário, sem o grupo Gestão,
    o disparo inicia (spec 012, o código nunca pergunta pelo nome do papel)."""
    from django.contrib.auth.models import Permission

    from tests.papeis import usuario_com

    usuario = usuario_com()
    usuario.user_permissions.add(Permission.objects.get(codename="operar_automacoes"))
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: chamadas.append(args))
    e = iniciar_lancamento(usuario, simulacao=True, lotes=["P-0001"])
    assert e is not None and e.iniciada_por == usuario and len(chamadas) == 1
    assert not usuario.groups.exists()
