"""Lote em verificar sem risco de lançar duas vezes (spec 010, PR 3): intervalo, candidatas e a
trava da liberação, contra o SCPI simulado. Nenhum teste abre o navegador."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from conciliacao import regras
from conciliacao.consultas import liberacao
from conciliacao.extracao import extrair
from conciliacao.models import ConferenciaLote, ExtracaoOficial, TentativaLancamento
from conciliacao.servicos import conciliar_verificar
from pedidos.models import ExecucaoRobo, LinhaSaida
from pedidos.servicos import resolver_lote
from scpi.lancamento import executar_lancamento
from scpi.leitura import NadaAExibir
from scpi.requisicoes import ResultadoIncerto
from tests.cenario import criar_pedido
from tests.conciliacao_cenario import tentativa_em_verificar

T = regras.TentativaResumo
R = regras.RequisicaoResumo


# --- Regras puras ---


def test_intervalo_entre_o_lancamento_anterior_e_o_seguinte_da_execucao():
    tentativas = [T(1, "P-1", "003495/26"), T(2, "P-18", ""), T(3, "P-2", "003496/26")]
    assert regras.intervalo(tentativas, "003490/26", "P-18") == ("003495/26", "003496/26")


def test_execucoes_8_e_28_tem_o_intervalo_vazio():
    # As duas tentativas reais do P-000018: os números de antes e de depois são vizinhos.
    for antes, depois in (("003495/26", "003496/26"), ("003532/26", "003533/26")):
        tentativas = [T(1, "AV-1", antes), T(2, "P-000018", ""), T(3, "AV-2", depois)]
        de, ate = regras.intervalo(tentativas, None, "P-000018")
        lidas = [R(antes, "AV-1"), R(depois, "AV-2")]
        assert regras.candidatas(lidas, "P-000018", de, ate) == []


def test_intervalo_usa_o_piso_e_fica_aberto_sem_lancamento_posterior():
    tentativas = [T(1, "P-1", ""), T(2, "P-2", "")]
    assert regras.intervalo(tentativas, "003712/26", "P-1") == ("003712/26", None)
    assert regras.intervalo(tentativas, None, "P-2") == (None, None)


def test_candidatas_no_intervalo_excluem_outro_lote_e_marcam_este():
    lidas = [
        R("000010/26", ""),  # à mão, no intervalo: candidata
        R("000011/26", "AV-9"),  # outro lote nas observações: nunca é candidata
        R("000020/26", ""),  # fora do intervalo
        R("000030/26", "P-5"),  # este lote, fora do intervalo (número lido errado): é esta
    ]
    achadas = regras.candidatas(lidas, "P-5", "000009/26", "000012/26")
    assert [(r.requisicao, e) for r, e in achadas] == [("000030/26", True), ("000010/26", False)]


def test_candidatas_ordenadas_pela_semelhanca_com_a_foto():
    foto = {"tipo_saida": "BALCÃO", "cod_ccusto": "15", "itens": [{"codigo": "1", "qtd": "2"}]}
    lidas = [
        R("000010/26", "", "OUTRA", "4", (("9", Decimal("1")),)),
        R("000011/26", "", "BALCÃO", "15", (("1", Decimal("2")),)),
    ]
    achadas = regras.candidatas(lidas, "P-5", None, None, foto)
    assert [r.requisicao for r, _ in achadas] == ["000011/26", "000010/26"]


# --- Contra o SCPI simulado ---


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user("00077", password="x")


def lancar(scpi, lotes):
    return executar_lancamento(
        ExecucaoRobo.objects.create(), scpi.abrir, lotes=lotes, extrair=scpi.relatorio
    )


def conferencia(lote):
    return ConferenciaLote.objects.get(lote=lote, tipo="VERIFICAR")


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_scpi_que_salvou_e_perdeu_a_resposta_bloqueia_a_liberacao(dois_lotes, scpi, usuario):
    p, av = dois_lotes
    scpi.salva_e_falha.add(p)
    lancar(scpi, [p, av])
    c = conferencia(p)
    assert c.veredito == "COM_CANDIDATAS"
    (candidata,) = c.candidatas.all()
    assert (candidata.requisicao.requisicao, candidata.e_esta) == ("000001/26", True)
    r = resolver_lote(p, "liberar", usuario=usuario, conferido=True)
    assert not r.ok and "000001/26" in r.mensagem
    assert set(LinhaSaida.objects.filter(lote=p).values_list("status", flat=True)) == {"VERIFICAR"}
    # "É esta": informar o número da candidata resolve o lote.
    assert resolver_lote(p, "lancada", usuario=usuario, requisicao="000001/26").ok


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_salvar_que_falhou_sem_gravar_tem_o_intervalo_vazio_e_libera(dois_lotes, scpi, usuario):
    p, av = dois_lotes
    scpi.falhas_salvar[p] = ResultadoIncerto("o SCPI não respondeu")
    lancar(scpi, [p, av])
    c = conferencia(p)
    assert (c.veredito, c.intervalo_de, c.intervalo_ate) == ("INTERVALO_VAZIO", "", "000001/26")
    assert liberacao(p).permitida
    assert resolver_lote(p, "liberar", usuario=usuario, conferido=True).ok


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_requisicao_feita_a_mao_no_meio_da_execucao_bloqueia(dois_lotes, scpi, usuario):
    p, av = dois_lotes
    original = scpi.salvar

    def salvar_com_requisicao_alheia():
        if scpi._lote == p:
            scpi.requisicao_manual(timezone.localdate(), tipo="OUTRA")
            raise ResultadoIncerto("o SCPI não respondeu")
        return original()

    scpi.salvar = salvar_com_requisicao_alheia
    lancar(scpi, [p, av])
    c = conferencia(p)
    assert c.veredito == "COM_CANDIDATAS"
    assert [(x.requisicao.requisicao, x.e_esta) for x in c.candidatas.all()] == [
        ("000001/26", False)
    ]
    assert not resolver_lote(p, "liberar", usuario=usuario, conferido=True).ok


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_sem_extracao_depois_da_tentativa_a_liberacao_e_recusada(dois_lotes, scpi, usuario):
    p, av = dois_lotes
    scpi.falhas_salvar[p] = ResultadoIncerto("o SCPI não respondeu")
    original = scpi.relatorio
    chamadas = []

    def so_a_de_antes(de, ate):
        chamadas.append(1)
        if len(chamadas) > 1:
            raise RuntimeError("SCPI caiu depois do lançamento")
        return original(de, ate)

    executar_lancamento(
        ExecucaoRobo.objects.create(), scpi.abrir, lotes=[p, av], extrair=so_a_de_antes
    )
    r = resolver_lote(p, "liberar", usuario=usuario, conferido=True)
    assert not r.ok and "extração do SCPI feita depois desta tentativa" in r.mensagem


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_candidata_vista_uma_vez_continua_bloqueando(dois_lotes, scpi, usuario):
    p, av = dois_lotes
    scpi.salva_e_falha.add(p)
    lancar(scpi, [p, av])
    # A requisição some do relatório (falha dele, ou alguém a excluiu): uma extração nova e
    # sem a candidata não desfaz o bloqueio.
    scpi.salvas = [r for r in scpi.salvas if r.requisicao != "000001/26"]
    hoje = timezone.localdate()
    nova = extrair(
        ExtracaoOficial.Motivo.MANUAL,
        (hoje - timedelta(days=30), hoje + timedelta(days=1)),
        lambda: scpi.relatorio(hoje - timedelta(days=30), hoje + timedelta(days=1)),
    )
    conciliar_verificar(nova)
    assert ConferenciaLote.objects.get(extracao=nova, lote=p).veredito == "INTERVALO_VAZIO"
    assert not liberacao(p).permitida


@pytest.mark.django_db
def test_lote_sem_tentativa_registrada_nao_e_liberado(usuario):
    n = criar_pedido(atendido=True, linhas=[("VERIFICAR", "")]).numero
    r = resolver_lote(n, "liberar", usuario=usuario, conferido=True)
    assert not r.ok and "não tem a tentativa registrada" in r.mensagem


@pytest.mark.django_db
def test_extracao_anterior_a_tentativa_nao_conta(usuario):
    n = criar_pedido(atendido=True, linhas=[("VERIFICAR", "")]).numero
    tentativa = tentativa_em_verificar(n, horas_atras=0)
    data = LinhaSaida.objects.filter(lote=n).values_list("data", flat=True).first()

    def nada_a_exibir():
        raise NadaAExibir("Requisições do SCPI: nada a exibir.")

    extracao = extrair(
        ExtracaoOficial.Motivo.MANUAL,
        (data - timedelta(days=1), data + timedelta(days=1)),
        nada_a_exibir,
    )
    assert extracao.bem_sucedida  # o motivo de não contar tem que ser só o tempo
    # A extração começou antes do momento da tentativa (aqui, criado depois): não conta.
    TentativaLancamento.objects.filter(pk=tentativa.pk).update(
        momento=extracao.importacao.inicio + timedelta(seconds=1)
    )
    assert conciliar_verificar(extracao) == 0
    assert not liberacao(n).permitida
    # A mesma extração, posterior à tentativa, passa a contar (intervalo vazio: libera).
    TentativaLancamento.objects.filter(pk=tentativa.pk).update(
        momento=extracao.importacao.inicio - timedelta(seconds=1)
    )
    assert conciliar_verificar(extracao) == 1
    assert liberacao(n).permitida


# --- importar_tentativas ---


def _journal(tmp_path, eventos):
    caminho = tmp_path / "journal.jsonl"
    caminho.write_text("\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")
    return caminho


@pytest.mark.django_db
def test_importar_tentativas_do_journal_na_ordem_e_idempotente(tmp_path, capsys):
    e = ExecucaoRobo.objects.create()
    ts = "2026-10-20T10:0{}:00-03:00"
    caminho = _journal(
        tmp_path,
        [
            {"ts": ts.format(1), "evento": "em_lancamento", "execucao": e.pk, "lote": "AV-1"},
            {"ts": ts.format(2), "evento": "lancada", "execucao": e.pk, "lote": "AV-1",
             "requisicao": "003495/26"},
            {"ts": ts.format(3), "evento": "em_lancamento", "execucao": e.pk, "lote": "P-18"},
            {"ts": ts.format(4), "evento": "incerto", "execucao": e.pk, "lote": "P-18"},
            {"ts": ts.format(5), "evento": "em_lancamento", "execucao": e.pk, "lote": "AV-2"},
            {"ts": ts.format(6), "evento": "lancada", "execucao": e.pk, "lote": "AV-2",
             "requisicao": "003496/26"},
            {"ts": ts.format(7), "evento": "em_lancamento", "execucao": 999999, "lote": "X-1"},
        ],
    )  # fmt: skip
    call_command("importar_tentativas", journal=str(caminho), dry_run=True)
    assert "tentativas a criar: 3" in capsys.readouterr().out
    assert not TentativaLancamento.objects.exists()

    call_command("importar_tentativas", journal=str(caminho))
    saida = capsys.readouterr().out
    assert "tentativas criadas: 3" in saida and "sem a execução no banco: 1" in saida
    linhas = TentativaLancamento.objects.filter(execucao=e).values_list(
        "ordem", "lote", "resultado", "requisicao", "historica"
    )
    assert list(linhas) == [
        (1, "AV-1", "LANCADA", "003495/26", True),
        (2, "P-18", "VERIFICAR", "", True),
        (3, "AV-2", "LANCADA", "003496/26", True),
    ]
    call_command("importar_tentativas", journal=str(caminho))
    assert "tentativas criadas: 0" in capsys.readouterr().out
