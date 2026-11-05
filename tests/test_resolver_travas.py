from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from pedidos.models import ExecucaoRobo, LinhaSaida
from pedidos.regras import requisicao_valida
from pedidos.servicos import resolver_lote
from tests.cenario import criar_pedido
from tests.conciliacao_cenario import liberacao_comprovada

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user("00012", password="x")


def lote(*status):
    p = criar_pedido(atendido=True, linhas=[(s, "") for s in status])
    return p.numero


def test_informar_requisicao_lanca_so_as_travadas(usuario):
    n = lote("VERIFICAR", "LANCADA", "PENDENTE")
    r = resolver_lote(n, "lancada", usuario=usuario, requisicao=" 003354/26 ")
    assert r.ok and r.mensagem == f"Lote {n}: requisição 003354/26 registrada."
    assert list(
        LinhaSaida.objects.filter(lote=n).order_by("seq").values_list("status", "requisicao_scpi")
    ) == [("LANCADA", "003354/26"), ("LANCADA", ""), ("PENDENTE", "")]
    msg = LinhaSaida.objects.get(lote=n, seq=1).mensagem
    assert (
        msg.startswith(f"Requisição 003354/26 informada por {usuario.username} em ")
        and "Antes: Verificar no SCPI" in msg
    )
    assert LinhaSaida.objects.get(lote=n, seq=1).lancado_em is not None


@pytest.mark.parametrize("numero", ["", "3354/26", "003354-26", "0033540/26"])
def test_numero_fora_do_formato_e_recusado(usuario, numero):
    n = lote("VERIFICAR")
    r = resolver_lote(n, "lancada", usuario=usuario, requisicao=numero)
    assert not r.ok and r.mensagem == "Informe o número da requisição no formato 000000/00."
    assert LinhaSaida.objects.get(lote=n).status == "VERIFICAR"


def test_liberar_verificar_exige_conferencia(usuario):
    n = lote("VERIFICAR")
    assert not resolver_lote(n, "liberar", usuario=usuario).ok
    # Spec 010: sem a tentativa e uma extração posterior sem candidatas, nem com a caixa marcada.
    r = resolver_lote(n, "liberar", usuario=usuario, conferido=True)
    assert not r.ok and "tentativa registrada" in r.mensagem
    liberacao_comprovada(n)
    assert resolver_lote(n, "liberar", usuario=usuario, conferido=True).ok
    assert LinhaSaida.objects.get(lote=n).status == "PENDENTE"


def test_liberar_erro_nao_exige_conferencia(usuario):
    n = lote("ERRO")
    assert resolver_lote(n, "liberar", usuario=usuario).ok


def test_em_lancamento_orfa_pode_ser_marcada_nao_lancar(usuario):
    n = lote("EM_LANCAMENTO")
    r = resolver_lote(n, "nao_lancar", usuario=usuario)
    assert r.ok and LinhaSaida.objects.get(lote=n).status == "NAO_LANCAR"


def test_lote_sem_trava_ou_inexistente(usuario):
    assert resolver_lote(lote("PENDENTE"), "liberar", usuario=usuario).mensagem.endswith(
        "aguarda conferência."
    )
    assert not resolver_lote("P-999999", "liberar", usuario=usuario).ok


def test_acao_desconhecida(usuario):
    assert resolver_lote(lote("ERRO"), "apagar", usuario=usuario).mensagem == "Ação desconhecida."


def test_recusa_durante_execucao_e_libera_quando_interrompida(usuario):
    n = lote("VERIFICAR")
    e = ExecucaoRobo.objects.create()
    assert "em andamento" in resolver_lote(n, "nao_lancar", usuario=usuario).mensagem
    ExecucaoRobo.objects.filter(pk=e.pk).update(inicio=timezone.now() - timedelta(minutes=2))
    assert resolver_lote(n, "nao_lancar", usuario=usuario).ok


def test_recusa_com_a_trava_do_lancamento_ocupada_mesmo_sem_execucao_registrada(
    usuario, trava_ocupada
):
    """Um robô que acabou de subir segura a trava antes de a execução aparecer em andamento."""
    n = lote("VERIFICAR")
    r = resolver_lote(n, "nao_lancar", usuario=usuario)
    assert not r.ok and "em andamento" in r.mensagem
    assert LinhaSaida.objects.get(lote=n).status == "VERIFICAR"


def test_resolver_libera_a_trava_do_lancamento_ao_terminar(usuario):
    n = lote("VERIFICAR", "ERRO")
    assert resolver_lote(n, "nao_lancar", usuario=usuario).ok
    assert not ExecucaoRobo.trava_ocupada()
    assert resolver_lote(n, "nao_lancar", usuario=usuario).ok is False  # nada mais a resolver
    assert not ExecucaoRobo.trava_ocupada()


def test_requisicao_valida():
    assert requisicao_valida("003354/26") and not requisicao_valida("003354/2026")


def test_mensagem_da_linha_registra_quem_quando_e_o_estado_anterior(usuario):
    n = lote("ERRO", "ERRO")
    LinhaSaida.objects.filter(lote=n, seq=1).update(mensagem="Saldo insuficiente")
    agora = timezone.make_aware(timezone.datetime(2026, 10, 11, 14, 5))
    assert resolver_lote(n, "liberar", usuario=usuario, agora=agora).ok
    com, sem = LinhaSaida.objects.filter(lote=n).order_by("seq")
    assert com.mensagem == (
        f"Liberada para relançar por {usuario.username} em 11/10/2026 14:05. "
        "Antes: Erro — Saldo insuficiente"
    )
    assert sem.mensagem == (
        f"Liberada para relançar por {usuario.username} em 11/10/2026 14:05. Antes: Erro."
    )
    assert resolver_lote(n, "liberar", usuario=usuario).mensagem.endswith("aguarda conferência.")


def test_liberar_apaga_numero_e_data_de_lancamento(usuario):
    n = lote("VERIFICAR")
    LinhaSaida.objects.filter(lote=n).update(requisicao_scpi="003354/26", lancado_em=timezone.now())
    liberacao_comprovada(n)
    assert resolver_lote(n, "liberar", usuario=usuario, conferido=True).ok
    linha = LinhaSaida.objects.get(lote=n)
    assert (linha.status, linha.requisicao_scpi, linha.lancado_em) == ("PENDENTE", "", None)


def test_requisicao_valida_so_com_algarismos_ascii():
    assert not requisicao_valida("٠٠٣٣٥٤/٢٦")
