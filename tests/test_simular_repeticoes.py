from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from pedidos.models import ExecucaoRobo, LinhaSaida
from scpi.management.commands.simular_repeticoes import RE_QTD_DO_SERVIDOR, medir

# Nenhum teste grava o journal no `logs/` do repositório.
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("journal")]


def rodar(*argumentos):
    saida = StringIO()
    call_command("simular_repeticoes", *argumentos, stdout=saida)
    return saida.getvalue()


def test_repete_a_simulacao_abrindo_o_scpi_uma_vez_so(monkeypatch, dois_lotes, scpi):
    monkeypatch.setattr("scpi.management.commands.simular_repeticoes.navegador", scpi.abrir)
    p, _ = dois_lotes
    saida = rodar("--lote", p, "--vezes", "3")
    assert scpi.abertas == 1
    assert [c for c in scpi.chamadas if c[0] == "simulacao"] == [("simulacao", p)] * 3
    assert [c for c in scpi.chamadas if c[0] == "preencher"] == [("preencher", p)] * 3
    assert saida.count("repetição ") == 3 and "3 repetição(ões)" in saida
    # nunca salva nem muda linha
    assert not any(c[0] == "salvar" for c in scpi.chamadas)
    assert set(LinhaSaida.objects.values_list("status", flat=True)) == {"PENDENTE"}


def test_apaga_as_execucoes_por_padrao_e_mantem_com_a_opcao(monkeypatch, dois_lotes, scpi):
    monkeypatch.setattr("scpi.management.commands.simular_repeticoes.navegador", scpi.abrir)
    p, _ = dois_lotes
    rodar("--lote", p, "--vezes", "2")
    assert ExecucaoRobo.objects.count() == 0
    rodar("--lote", p, "--vezes", "2", "--manter-registros")
    assert ExecucaoRobo.objects.filter(simulacao=True).count() == 2


def test_exige_lote_e_vezes_positivo(monkeypatch, dois_lotes, scpi):
    monkeypatch.setattr("scpi.management.commands.simular_repeticoes.navegador", scpi.abrir)
    with pytest.raises(CommandError):
        call_command("simular_repeticoes")
    with pytest.raises(CommandError, match="--vezes"):
        rodar("--lote", dois_lotes[0], "--vezes", "0")
    assert scpi.abertas == 0


def test_medir_le_o_log_da_execucao():
    registro = ExecucaoRobo(
        log=(
            "  ⚠ servidor devolveu QTD 1 no item 4 (pedido: 5)\n"
            "  ⚠ servidor devolveu QTD 1 no item 4 (pedido: 5)\n"
            "  ⚠ servidor devolveu QTD 1 no item 7 (pedido: 2)\n"
            "  conferência final: item(ns) [4, 7] divergem do pedido (...); corrigindo (1/5)\n"
            "  conferência final: 10 item(ns) do grid iguais ao pedido\n"
        ),
        resumo={"falhas": 0},
    )
    m = medir(registro)
    assert m["resetados"] == [4, 7] and m["correcoes"] == 1 and m["final_ok"]
    assert RE_QTD_DO_SERVIDOR.findall("servidor devolveu QTD 1 no item 12") == ["12"]
