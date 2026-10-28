import json
from contextlib import contextmanager

import pytest
from django.db import DatabaseError, InterfaceError, connection, connections
from django.db.models.query import QuerySet

from catalogo.models import CentroCusto
from pedidos.models import ExecucaoRobo, LinhaSaida
from scpi import lancamento
from scpi.lancamento import LancamentoEmAndamento, executar_lancamento
from scpi.leitura import ErroImportacao
from scpi.requisicoes import ErroSCPI, FalhaCritica
from tests.test_scpi_execucao import liberacao_quebrada

pytestmark = pytest.mark.django_db


def lancar_todos(execucao, abrir):
    """Escolhe todos os lotes que existem: o que o botão faria com a fila inteira marcada."""
    return executar_lancamento(
        execucao, abrir, lotes=set(LinhaSaida.objects.values_list("lote", flat=True))
    )


@pytest.fixture(autouse=True)
def _journal_temporario(journal):
    """Nenhum teste grava o journal no `logs/` do repositório."""


def test_lanca_um_lote_por_requisicao_e_grava_o_numero(dois_lotes, scpi):
    execucao = lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert execucao.situacao == "SUCESSO" and execucao.fim is not None
    assert execucao.resumo == {
        "requisicoes": 2,
        "processadas": 2,
        "lancadas": 2,
        "simuladas": 0,
        "falhas": 0,
        "verificar": 0,
        "ignoradas": 0,
    }
    p, av = dois_lotes
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", "requisicao_scpi")) == {
        ("LANCADA", "000001/26")
    }
    assert LinhaSaida.objects.get(lote=av).requisicao_scpi == "000002/26"
    assert not LinhaSaida.objects.filter(lancado_em__isnull=True).exists()
    assert "lançada no SCPI: requisição 000001/26" in execucao.log


@pytest.mark.django_db(transaction=True)
def test_trava_esta_confirmada_no_banco_antes_do_salvar(dois_lotes, scpi):
    vistos = []

    def olhar():
        outra = connections.create_connection("default")
        with outra.cursor() as c:
            c.execute(
                "SELECT DISTINCT status FROM pedidos_linhasaida WHERE lote=%s", [dois_lotes[0]]
            )
            vistos.append([r[0] for r in c.fetchall()])
        outra.close()

    scpi.ao_salvar = olhar
    executar_lancamento(ExecucaoRobo.objects.create(), scpi.abrir, lotes=[dois_lotes[0]])
    assert vistos == [["EM_LANCAMENTO"]]


def test_erro_antes_do_salvar_vira_erro_e_o_proximo_segue(dois_lotes, scpi):
    p, av = dois_lotes
    scpi.falhas_preencher[p] = ErroSCPI("item 1/2 (023.001.002): saldo insuficiente")
    e = lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert e.situacao == "ATENCAO" and e.resumo["falhas"] == 1 and e.resumo["lancadas"] == 1
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", "mensagem")) == {
        ("ERRO", "item 1/2 (023.001.002): saldo insuficiente")
    }
    assert ("descartar", p) in scpi.chamadas and ("salvar", p) not in scpi.chamadas


def test_qualquer_falha_no_salvar_vira_verificar_nunca_pendente(dois_lotes, scpi):
    p, _ = dois_lotes
    scpi.falhas_salvar[p] = RuntimeError("Timeout 10000ms exceeded")
    e = lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", flat=True)) == {"VERIFICAR"}
    assert "Timeout 10000ms exceeded" in LinhaSaida.objects.filter(lote=p).first().mensagem
    assert e.resumo["verificar"] == 1 and ("reiniciar", "") in scpi.chamadas


def test_lote_travado_ou_com_erro_nao_vai_ao_scpi(dois_lotes, scpi):
    p, av = dois_lotes
    LinhaSaida.objects.filter(lote=p).filter(seq=1).update(status="VERIFICAR")
    e = lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert ("preencher", p) not in scpi.chamadas and ("preencher", av) in scpi.chamadas
    assert LinhaSaida.objects.get(lote=p, seq=2).status == "PENDENTE"
    assert e.resumo["ignoradas"] == 1 and "P-" in e.log and "travado" in e.log


def test_simulacao_nao_salva_nem_muda_status(dois_lotes, scpi):
    e = lancar_todos(ExecucaoRobo.objects.create(simulacao=True), scpi.abrir)
    assert not any(c[0] == "salvar" for c in scpi.chamadas)
    assert [c for c in scpi.chamadas if c[0] == "simulacao"] == [
        ("simulacao", lote) for lote in dois_lotes
    ]
    assert set(LinhaSaida.objects.values_list("status", flat=True)) == {"PENDENTE"}
    assert e.resumo["simuladas"] == 2 and e.situacao == "SUCESSO"


def test_invalido_vira_erro_sem_abrir_o_navegador(dois_lotes, scpi):
    CentroCusto.objects.filter(descricao="ETA II").delete()
    e = lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert scpi.abertas == 0 and e.resumo["falhas"] == 2
    assert all(
        "centro de custo 'ETA II' não existe" in m
        for m in LinhaSaida.objects.values_list("mensagem", flat=True)
    )


def test_linha_alterada_durante_a_execucao_nao_e_lancada(dois_lotes, scpi):
    p, _ = dois_lotes
    original = scpi.preencher

    def mudar(req):
        original(req)
        if req.lote == p:
            LinhaSaida.objects.filter(lote=p, seq=2).update(status="NAO_LANCAR")

    scpi.preencher = mudar
    e = lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert ("salvar", p) not in scpi.chamadas and ("descartar", p) in scpi.chamadas
    assert list(
        LinhaSaida.objects.filter(lote=p).order_by("seq").values_list("status", flat=True)
    ) == ["PENDENTE", "NAO_LANCAR"]
    assert e.resumo["ignoradas"] == 1


def test_so_os_lotes_escolhidos_sao_lancados(dois_lotes, scpi):
    p, av = dois_lotes
    e = executar_lancamento(ExecucaoRobo.objects.create(), scpi.abrir, lotes=[av])
    assert e.resumo["lancadas"] == 1 and e.resumo["ignoradas"] == 1
    assert LinhaSaida.objects.get(lote=av).status == "LANCADA"
    assert not LinhaSaida.objects.filter(lote=p).exclude(status="PENDENTE").exists()


def test_lote_escolhido_que_saiu_da_fila_nao_e_lancado_e_e_avisado(dois_lotes, scpi):
    p, av = dois_lotes
    LinhaSaida.objects.filter(lote=av).update(status="LANCADA", requisicao_scpi="000009/26")
    e = executar_lancamento(ExecucaoRobo.objects.create(), scpi.abrir, lotes=[av])
    assert e.resumo["requisicoes"] == 0 and e.resumo["lancadas"] == 0
    assert f"{av} não está mais na fila do robô" in e.log
    assert not LinhaSaida.objects.filter(lote=p).exclude(status="PENDENTE").exists()


def test_lote_invalido_fora_da_escolha_nao_vira_erro(dois_lotes, scpi):
    p, av = dois_lotes
    LinhaSaida.objects.filter(lote=p).update(centro_custo="")
    e = executar_lancamento(ExecucaoRobo.objects.create(), scpi.abrir, lotes=[av])
    assert e.resumo["lancadas"] == 1 and e.resumo["falhas"] == 0
    assert not LinhaSaida.objects.filter(lote=p, status="ERRO").exists()


def test_banco_fora_ao_gravar_lancada_interrompe_e_guarda_no_journal(
    dois_lotes, scpi, journal, monkeypatch
):
    p, _ = dois_lotes
    original = QuerySet.update

    def quebrar(self, **kwargs):
        if kwargs.get("status") == "LANCADA":
            raise DatabaseError("MySQL server has gone away")
        return original(self, **kwargs)

    monkeypatch.setattr(QuerySet, "update", quebrar)
    execucao = ExecucaoRobo.objects.create()
    with pytest.raises(FalhaCritica):
        lancar_todos(execucao, scpi.abrir)
    execucao.refresh_from_db()
    assert execucao.situacao == "FALHA" and "gone away" in execucao.erro
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", flat=True)) == {
        "EM_LANCAMENTO"
    }
    eventos = [
        json.loads(linha)
        for linha in (journal / lancamento.JOURNAL).read_text("utf-8").splitlines()
    ]
    assert {"evento": "lancada", "lote": p, "requisicao": "000001/26"}.items() <= eventos[
        -2
    ].items()
    assert eventos[-1]["evento"] == "falha_banco"
    assert eventos[-1]["execucao"] == execucao.pk


def test_banco_fora_ate_o_fim_ainda_levanta_falha_critica(dois_lotes, scpi, monkeypatch):
    """Com o banco fora, a liberação da trava também falha: a `FalhaCritica` (que o comando
    traduz em código de saída) não pode ficar escondida atrás desse erro."""
    original = QuerySet.update

    def quebrar(self, **kwargs):
        if kwargs.get("status") == "LANCADA":
            raise DatabaseError("MySQL server has gone away")
        return original(self, **kwargs)

    monkeypatch.setattr(QuerySet, "update", quebrar)
    try:
        with connection.execute_wrapper(liberacao_quebrada):
            with pytest.raises(FalhaCritica, match="gone away"):
                lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    finally:
        with connection.cursor() as c:
            c.execute("SELECT RELEASE_LOCK('almoxarifado:lancar_saidas')")


def test_navegador_que_nao_abre_deixa_tudo_pendente(dois_lotes):
    @contextmanager
    def quebrado():
        raise ErroImportacao("Defina SAEP_USER e SAEP_PASS no .env.")
        yield

    e = ExecucaoRobo.objects.create()
    with pytest.raises(ErroImportacao):
        lancar_todos(e, quebrado)
    e.refresh_from_db()
    assert e.situacao == "FALHA" and "SAEP_USER" in e.erro
    assert set(LinhaSaida.objects.values_list("status", flat=True)) == {"PENDENTE"}


def test_trava_ocupada_recusa_sem_tocar_em_nada(dois_lotes, scpi):
    outra = connections.create_connection("default")
    with outra.cursor() as c:
        c.execute("SELECT GET_LOCK('almoxarifado:lancar_saidas', 0)")
    try:
        e = ExecucaoRobo.objects.create()
        with pytest.raises(LancamentoEmAndamento):
            lancar_todos(e, scpi.abrir)
        e.refresh_from_db()
        assert (e.situacao, e.erro) == ("FALHA", "Outro lançamento já está em andamento.")
        assert scpi.abertas == 0
    finally:
        outra.close()


def test_pendente_com_numero_de_requisicao_nao_e_lancada_de_novo(dois_lotes, scpi):
    p, av = dois_lotes
    LinhaSaida.objects.filter(lote=p, seq=1).update(requisicao_scpi="003354/26")
    e = lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert ("preencher", p) not in scpi.chamadas and ("salvar", av) in scpi.chamadas
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", flat=True)) == {"PENDENTE"}
    assert e.resumo["ignoradas"] == 1 and e.resumo["lancadas"] == 1


def test_numero_que_aparece_durante_a_execucao_impede_a_trava(dois_lotes, scpi):
    p, _ = dois_lotes
    original = scpi.preencher

    def numerar(req):
        original(req)
        if req.lote == p:
            LinhaSaida.objects.filter(lote=p, seq=2).update(requisicao_scpi="003354/26")

    scpi.preencher = numerar
    e = lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert ("salvar", p) not in scpi.chamadas and ("descartar", p) in scpi.chamadas
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", flat=True)) == {"PENDENTE"}
    assert e.resumo["ignoradas"] == 1


def test_lote_com_linha_lancada_e_pendente_lanca_so_a_pendente(dois_lotes, scpi):
    """Comportamento atual: a linha já lançada fica como está e a pendente do mesmo lote vai
    numa requisição própria."""
    p, _ = dois_lotes
    LinhaSaida.objects.filter(lote=p, seq=1).update(status="LANCADA", requisicao_scpi="000777/26")
    lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert list(
        LinhaSaida.objects.filter(lote=p).order_by("seq").values_list("status", "requisicao_scpi")
    ) == [("LANCADA", "000777/26"), ("LANCADA", "000001/26")]


def test_conexao_perdida_ao_travar_vira_falha_critica(dois_lotes, scpi, monkeypatch):
    """`InterfaceError` (conexão fechada) não é `DatabaseError`: também precisa parar o robô."""
    original = QuerySet.update

    def quebrar(self, **kwargs):
        if kwargs.get("status") == "EM_LANCAMENTO":
            raise InterfaceError("(0, '')")
        return original(self, **kwargs)

    monkeypatch.setattr(QuerySet, "update", quebrar)
    e = ExecucaoRobo.objects.create()
    with pytest.raises(FalhaCritica, match="não foi possível travar o lote"):
        lancar_todos(e, scpi.abrir)
    assert not any(c[0] == "salvar" for c in scpi.chamadas)


# Edição do atendimento contra o robô: a troca dos IDs das linhas é o que o faz pular o lote.


def _editar_recebedor(numero, recebedor):
    from datetime import date

    from pedidos.models import Pedido
    from pedidos.servicos import editar_atendimento
    from tests.cenario import saida

    pedido = Pedido.objects.get(numero=numero)
    return editar_atendimento(
        pedido.id,
        pedido.versao,
        saida(recebedor=recebedor),
        {"023.001.002": "2", "008.001.002": "1,5"},
        nao_lancar=False,
        usuario=pedido.atendimento.atendido_por,
        hoje=date(2026, 10, 9),
    )


def test_edicao_entre_a_leitura_e_a_trava_faz_o_robo_pular_o_lote(dois_lotes, scpi, monkeypatch):
    p, _ = dois_lotes
    preencher = scpi.preencher

    def preencher_e_editar(req):
        if req.lote == p:
            assert _editar_recebedor(p, "Ana").ok
        preencher(req)

    monkeypatch.setattr(scpi, "preencher", preencher_e_editar)
    execucao = lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert execucao.resumo["ignoradas"] == 1 and execucao.resumo["lancadas"] == 1
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", flat=True)) == {"PENDENTE"}

    monkeypatch.setattr(scpi, "preencher", preencher)
    lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", "recebedor")) == {
        ("LANCADA", "Ana")
    }


def test_robo_trava_antes_e_a_edicao_e_recusada(dois_lotes, scpi):
    p, _ = dois_lotes
    respostas = []

    def editar_durante_o_salvar():
        if scpi._lote == p:
            respostas.append(_editar_recebedor(p, "Ana"))

    scpi.ao_salvar = editar_durante_o_salvar
    lancar_todos(ExecucaoRobo.objects.create(), scpi.abrir)
    assert [r.motivo for r in respostas] == ["lancamento"]
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", "recebedor")) == {
        ("LANCADA", "João")
    }
