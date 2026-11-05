"""Execução real do robô com as extrações antes e depois do lançamento (spec 010, PR 2), contra o
SCPI simulado. Nenhum teste abre o navegador."""

from datetime import date, timedelta

import pytest
from django.core.management import CommandError, call_command
from django.db import DatabaseError
from django.utils import timezone

from catalogo.models import CentroCusto, Importacao
from conciliacao import robo
from conciliacao.models import ExtracaoOficial, RequisicaoOficial, TentativaLancamento
from pedidos.models import ExecucaoRobo, LinhaSaida
from scpi.lancamento import executar_lancamento
from scpi.requisicoes import ErroSCPI, ResultadoIncerto
from tests.relacao_requisicoes import ItemCSV

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("journal")]


def lancar(scpi, lotes, *, simulacao=False):
    execucao = ExecucaoRobo.objects.create(simulacao=simulacao)
    return executar_lancamento(execucao, scpi.abrir, lotes=lotes, extrair=scpi.relatorio)


def status():
    return set(LinhaSaida.objects.values_list("status", flat=True))


def test_extrai_antes_e_depois_e_registra_as_tentativas_na_ordem(dois_lotes, scpi):
    p, av = dois_lotes
    execucao = lancar(scpi, [p, av])
    assert execucao.situacao == "SUCESSO" and status() == {"LANCADA"}

    antes, depois = ExtracaoOficial.objects.filter(execucao=execucao).order_by("pk")
    assert (antes.motivo, antes.bem_sucedida, antes.requisicoes) == ("ANTES", True, 0)
    assert antes.maior_requisicao is None  # o SCPI simulado começa sem requisições
    assert (depois.motivo, depois.bem_sucedida, depois.requisicoes) == ("DEPOIS", True, 2)
    assert depois.maior_requisicao == "000002/26"

    tentativas = list(TentativaLancamento.objects.filter(execucao=execucao))
    assert [(t.ordem, t.lote, t.resultado, t.requisicao) for t in tentativas] == [
        (1, p, "LANCADA", "000001/26"),
        (2, av, "LANCADA", "000002/26"),
    ]
    foto = tentativas[0].foto
    assert foto["observacoes"] == f"Central Almoxarifado {p}"
    assert foto["tipo_saida"] == "BALCÃO"
    assert {i["codigo"] for i in foto["itens"]} == {"023.001.002", "008.001.002"}


def test_extracao_de_antes_e_a_primeira_coisa_e_cobre_os_lotes(dois_lotes, scpi):
    lancar(scpi, list(dois_lotes))
    data_lote = LinhaSaida.objects.first().data
    hoje = timezone.localdate()
    assert scpi.relatorios[0] == (data_lote - timedelta(days=1), hoje + timedelta(days=1))
    assert scpi.relatorios[0] == scpi.relatorios[1]  # o depois repete o mesmo período


def test_cada_requisicao_salva_leva_o_lote_nas_observacoes(dois_lotes, scpi):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    assert [r.observacoes for r in scpi.salvas] == [
        f"Central Almoxarifado {p}",
        f"Central Almoxarifado {av}",
    ]
    lotes = set(RequisicaoOficial.objects.values_list("lote_observado", flat=True))
    assert lotes == {p, av}


def test_extracao_de_antes_que_falha_tres_vezes_nao_lanca_nada(dois_lotes, scpi):
    scpi.falhas_relatorio = 3
    execucao = ExecucaoRobo.objects.create()
    with pytest.raises(robo.ExtracaoAntesFalhou, match="3 tentativas"):
        executar_lancamento(execucao, scpi.abrir, lotes=list(dois_lotes), extrair=scpi.relatorio)
    execucao.refresh_from_db()
    assert execucao.situacao == "FALHA" and "Nenhum lote foi lançado" in execucao.erro
    assert status() == {"PENDENTE"}
    assert scpi.abertas == 0 and scpi.salvas == []
    assert not TentativaLancamento.objects.exists()
    falhas = ExtracaoOficial.objects.filter(execucao=execucao, motivo="ANTES")
    assert [e.importacao.situacao for e in falhas] == ["FALHA"] * 3


def test_extracao_de_antes_que_funciona_na_terceira_tentativa_lanca(dois_lotes, scpi):
    scpi.falhas_relatorio = 2
    execucao = lancar(scpi, list(dois_lotes))
    assert execucao.situacao == "SUCESSO" and status() == {"LANCADA"}
    antes = ExtracaoOficial.objects.filter(execucao=execucao, motivo="ANTES").order_by("pk")
    assert [e.importacao.situacao for e in antes] == ["FALHA", "FALHA", "SUCESSO"]


def test_outra_extracao_em_andamento_conta_como_tentativa_falha(
    dois_lotes, scpi, trava_importacao_ocupada
):
    trava_importacao_ocupada("REQUISICOES")
    with pytest.raises(robo.ExtracaoAntesFalhou, match="outra extração"):
        lancar(scpi, list(dois_lotes))
    assert status() == {"PENDENTE"}
    assert not Importacao.objects.filter(tipo="REQUISICOES").exists()


def test_piso_e_a_maior_requisicao_que_ja_existia(dois_lotes, scpi):
    hoje = timezone.localdate()
    scpi.requisicao_manual(hoje, tipo="OUTRA")
    scpi.requisicao_manual(hoje, tipo="OUTRA")
    execucao = lancar(scpi, list(dois_lotes))
    antes = ExtracaoOficial.objects.get(execucao=execucao, motivo="ANTES")
    assert antes.maior_requisicao == "000002/26"
    assert list(
        TentativaLancamento.objects.filter(execucao=execucao).values_list("requisicao", flat=True)
    ) == ["000003/26", "000004/26"]


def test_relatorio_vazio_com_lote_lancado_no_periodo_e_falha(dois_lotes, scpi):
    p, av = dois_lotes
    LinhaSaida.objects.filter(lote=av).update(status="LANCADA", requisicao_scpi="000009/26")
    with pytest.raises(robo.ExtracaoAntesFalhou, match="veio vazio"):
        lancar(scpi, [p])
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", flat=True)) == {"PENDENTE"}


def test_tentativas_que_nao_chegam_a_lancar(dois_lotes, scpi):
    p, av = dois_lotes
    scpi.falhas_preencher[p] = ErroSCPI("campo 'Observações' não encontrado no formulário")
    scpi.falhas_salvar[av] = ResultadoIncerto("o SCPI não respondeu")
    execucao = lancar(scpi, [p, av])
    assert execucao.situacao == "ATENCAO"
    resultados = TentativaLancamento.objects.filter(execucao=execucao).values_list(
        "ordem", "lote", "resultado", "requisicao"
    )
    assert list(resultados) == [(1, p, "ERRO", ""), (2, av, "VERIFICAR", "")]


def test_salvar_que_grava_e_perde_a_resposta_fica_em_verificar_e_aparece_depois(dois_lotes, scpi):
    p, av = dois_lotes
    scpi.salva_e_falha.add(av)
    execucao = lancar(scpi, [p, av])
    assert LinhaSaida.objects.filter(lote=av).first().status == "VERIFICAR"
    depois = ExtracaoOficial.objects.get(execucao=execucao, motivo="DEPOIS")
    salva = RequisicaoOficial.objects.get(extracao=depois, lote_observado=av)
    assert salva.requisicao == "000002/26"  # a prova de que o SCPI salvou, para o PR 3


def test_extracao_de_depois_que_falha_nao_piora_a_execucao(dois_lotes, scpi):
    original = scpi.relatorio
    chamadas = []

    def so_a_primeira(de, ate):
        chamadas.append((de, ate))
        if len(chamadas) == 2:
            raise RuntimeError("SCPI caiu depois do lançamento")
        return original(de, ate)

    execucao = executar_lancamento(
        ExecucaoRobo.objects.create(), scpi.abrir, lotes=list(dois_lotes), extrair=so_a_primeira
    )
    assert execucao.situacao == "SUCESSO" and status() == {"LANCADA"}
    depois = ExtracaoOficial.objects.get(execucao=execucao, motivo="DEPOIS")
    assert depois.importacao.situacao == "FALHA" and depois.requisicoes == 0
    assert "aguardando conferência" in execucao.log


def test_simulacao_nao_extrai(dois_lotes, scpi):
    lancar(scpi, list(dois_lotes), simulacao=True)
    assert scpi.relatorios == []
    assert not ExtracaoOficial.objects.exists() and not TentativaLancamento.objects.exists()


def test_sem_lote_valido_nao_extrai(dois_lotes, scpi):
    p, _ = dois_lotes
    LinhaSaida.objects.filter(lote=p).update(centro_custo="")
    lancar(scpi, [p])
    assert scpi.relatorios == []
    assert LinhaSaida.objects.filter(lote=p).first().status == "ERRO"


def test_lote_em_verificar_aberto_entra_no_periodo(dois_lotes, scpi):
    p, av = dois_lotes
    antigo = date(2026, 9, 1)
    LinhaSaida.objects.filter(lote=av).update(status="VERIFICAR", data=antigo)
    lancar(scpi, [p])
    assert scpi.relatorios[0][0] == antigo - timedelta(days=1)


def test_comando_real_extrai_pelo_scpi_e_recusa_quando_a_extracao_falha(
    dois_lotes, scpi_no_comando
):
    scpi_no_comando.falhas_relatorio = 3
    with pytest.raises(CommandError, match="antes de lançar"):
        call_command("lancar_saidas", lote=list(dois_lotes))
    assert status() == {"PENDENTE"}
    scpi_no_comando.falhas_relatorio = 0
    call_command("lancar_saidas", lote=list(dois_lotes))
    assert status() == {"LANCADA"}


def test_simulado_guarda_itens_e_tipo_perdido(dois_lotes, scpi):
    p, _ = dois_lotes
    scpi.perde_tipo.add(p)
    lancar(scpi, [p])
    (salva,) = scpi.salvas
    assert salva.tipo == "" and {i.codigo for i in salva.itens} == {"023.001.002", "008.001.002"}
    assert isinstance(salva.itens[0], ItemCSV)


def test_obs_da_saida_vai_as_observacoes_e_nao_quebra_o_relatorio(dois_lotes, scpi):
    p, _ = dois_lotes
    # Uma observação que começa por uma data partiria o registro do CSV sem o "Obs.: ".
    LinhaSaida.objects.filter(lote=p).update(obs="05/11/2026 retirado por Fulano")
    execucao = lancar(scpi, [p])
    (salva,) = scpi.salvas
    assert salva.observacoes == f"Central Almoxarifado {p}\nObs.: 05/11/2026 retirado por Fulano"
    tentativa = TentativaLancamento.objects.get(execucao=execucao)
    assert tentativa.foto["observacoes"] == salva.observacoes
    depois = ExtracaoOficial.objects.get(execucao=execucao, motivo="DEPOIS")
    assert depois.bem_sucedida
    lida = RequisicaoOficial.objects.get(extracao=depois)
    assert lida.lote_observado == p
    assert lida.observacoes == f"Central Almoxarifado {p} Obs.: 05/11/2026 retirado por Fulano"


def test_ponto_e_virgula_na_obs_nao_desloca_as_colunas_do_relatorio(dois_lotes, scpi):
    p, _ = dois_lotes
    LinhaSaida.objects.filter(lote=p).update(obs="Entregue; conferido; ok")
    execucao = lancar(scpi, [p])
    (salva,) = scpi.salvas
    assert salva.observacoes == f"Central Almoxarifado {p}\nObs.: Entregue, conferido, ok"
    depois = ExtracaoOficial.objects.get(execucao=execucao, motivo="DEPOIS")
    assert depois.bem_sucedida
    lida = RequisicaoOficial.objects.get(extracao=depois)
    assert (lida.lote_observado, lida.tipo) == (p, "BALCÃO")
    assert {i.codigo for i in lida.itens.all()} == {"023.001.002", "008.001.002"}


def test_erro_de_banco_na_extracao_de_depois_nao_piora_a_execucao(dois_lotes, scpi, monkeypatch):
    original = robo.extrair

    def quebra_no_depois(motivo, *args, **kwargs):
        if motivo == "DEPOIS":
            raise DatabaseError("o banco caiu ao registrar a extração")
        return original(motivo, *args, **kwargs)

    monkeypatch.setattr(robo, "extrair", quebra_no_depois)
    execucao = lancar(scpi, list(dois_lotes))
    assert execucao.situacao == "SUCESSO" and status() == {"LANCADA"}
    assert "não pôde ser registrada" in execucao.log


def test_foto_guarda_a_placa_do_centro_de_viatura(dois_lotes, scpi):
    p, _ = dois_lotes
    centro = LinhaSaida.objects.filter(lote=p).first().centro_custo
    # Só a linha do cadastro que o robô resolve (a descrição sem placa), com uma placa nova.
    linha = CentroCusto.objects.filter(descricao=centro, placa__isnull=True).first()
    CentroCusto.objects.filter(pk=linha.pk).update(placa="QWE1R23")
    execucao = lancar(scpi, [p])
    tentativa = TentativaLancamento.objects.get(execucao=execucao)
    assert tentativa.foto["placa_centro"] == "QWE1R23"
    assert {i["placa"] for i in tentativa.foto["itens"]} == {""}
