"""Extração diária e retenção de 60 dias (spec 010, PR 6, quickstart passo 8). Nenhum teste abre o
navegador: o SCPI é o simulado, e o `atualizar_catalogo` roda com os comandos substituídos."""

from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from catalogo.models import Importacao
from conciliacao.extracao import extrair
from conciliacao.limpeza import limpar
from conciliacao.models import ConferenciaLote, ExtracaoOficial, RequisicaoOficial
from pedidos.models import ExecucaoRobo
from scpi.lancamento import executar_lancamento

ATUALIZAR = "scpi.management.commands.atualizar_catalogo.call_command"


def lancar(scpi, lotes):
    return executar_lancamento(
        ExecucaoRobo.objects.create(), scpi.abrir, lotes=lotes, extrair=scpi.relatorio
    )


def periodo():
    hoje = timezone.localdate()
    return hoje - timedelta(days=40), hoje + timedelta(days=1)


def extracao(scpi, motivo=ExtracaoOficial.Motivo.MANUAL):
    if not scpi.salvas:  # vazio, o relatório diz "Nada a exibir" e não há bruto
        scpi.requisicao_manual(timezone.localdate(), tipo="OUTRA")
    de, ate = periodo()
    return extrair(motivo, (de, ate), lambda: scpi.relatorio(de, ate))


def envelhecer(*extracoes, dias=61):
    """Recua o início das extrações: a retenção conta a partir dele."""
    antes = timezone.now() - timedelta(days=dias)
    Importacao.objects.filter(pk__in=[e.importacao_id for e in extracoes]).update(
        inicio=antes, fim=antes
    )


# --- O passo Requisições do atualizar_catalogo (R19) ---


def test_atualizar_catalogo_termina_com_a_extracao_diaria(monkeypatch):
    feitos = []
    monkeypatch.setattr(ATUALIZAR, lambda nome, *a, **k: feitos.append((nome, k)))
    call_command("atualizar_catalogo")
    assert [nome for nome, _ in feitos] == [
        "importar_cadastro",
        "importar_estoque",
        "importar_saidas_scpi",
        "conciliar_lancamentos",
    ]
    assert feitos[-1][1]["diaria"] is True


def test_falha_no_passo_das_requisicoes_nao_desfaz_os_tres_primeiros(monkeypatch, capsys):
    feitos = []

    def falso(nome, *args, **kwargs):
        feitos.append(nome)
        if nome == "conciliar_lancamentos":
            raise CommandError("Requisições do SCPI: o SCPI demorou demais para responder.")

    monkeypatch.setattr(ATUALIZAR, falso)
    with pytest.raises(CommandError, match=r"^Falharam: conciliar_lancamentos\.$"):
        call_command("atualizar_catalogo")
    assert feitos[:3] == ["importar_cadastro", "importar_estoque", "importar_saidas_scpi"]
    assert "o SCPI demorou demais" in capsys.readouterr().err


def test_carga_inicial_tambem_passa_a_diaria(monkeypatch):
    feitos = {}
    monkeypatch.setattr(ATUALIZAR, lambda nome, *a, **k: feitos.setdefault(nome, k))
    call_command("atualizar_catalogo", carga_inicial=True)
    assert feitos["importar_cadastro"]["completo"] is True
    assert feitos["conciliar_lancamentos"]["diaria"] is True


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_conciliar_lancamentos_diaria_extrai_concilia_e_limpa(dois_lotes, scpi, monkeypatch):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    monkeypatch.setattr(
        "conciliacao.management.commands.conciliar_lancamentos.relatorios.baixar_requisicoes",
        scpi.relatorio,
    )
    limpezas = []
    monkeypatch.setattr(
        "conciliacao.management.commands.conciliar_lancamentos.limpar",
        lambda: limpezas.append(1),
    )
    call_command("conciliar_lancamentos", diaria=True)
    # Os lotes do cenário são de 09/10, fora dos 9 dias da diária: ela roda, sem lote a conferir.
    diaria = ExtracaoOficial.objects.get(motivo=ExtracaoOficial.Motivo.DIARIA)
    assert diaria.bem_sucedida
    assert limpezas == [1]
    call_command("conciliar_lancamentos", sem_limpeza=True)
    assert limpezas == [1]  # com --sem-limpeza, nada


# --- Retenção de 60 dias (FR-004, SC-007) ---


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_limpeza_esvazia_o_bruto_e_mantem_vereditos_e_requisicoes_ligadas(dois_lotes, scpi):
    p, av = dois_lotes
    scpi.requisicao_manual(timezone.localdate(), tipo="OUTRA")  # sem ligação com nenhum lote
    lancar(scpi, [p, av])
    depois = ExtracaoOficial.objects.get(motivo=ExtracaoOficial.Motivo.DEPOIS)
    assert depois.arquivo is not None and depois.requisicoes_lidas.count() == 3
    envelhecer(*ExtracaoOficial.objects.all())
    resultado = limpar()
    # A requisição sem ligação aparece nas duas extrações (a de antes e a de depois): sai das duas.
    assert resultado.brutos >= 1 and resultado.requisicoes == 2
    depois.refresh_from_db()
    assert depois.arquivo is None and depois.arquivo_apagado_em is not None
    assert depois.impressao  # a impressão digital fica
    # As duas requisições ligadas aos lotes ficam, e todo veredito continua consultável.
    assert sorted(depois.requisicoes_lidas.values_list("requisicao", flat=True)) == [
        "000002/26",
        "000003/26",
    ]
    for lote in (p, av):
        conferencia = ConferenciaLote.objects.get(lote=lote, extracao=depois)
        assert conferencia.veredito == "COMPROVADO" and conferencia.requisicao is not None
    assert limpar().requisicoes == 0  # de novo, nada


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_candidata_de_lote_em_verificar_nao_e_apagada(dois_lotes, scpi):
    p, av = dois_lotes
    scpi.salva_e_falha.add(p)
    lancar(scpi, [p, av])
    envelhecer(*ExtracaoOficial.objects.all())
    limpar()
    assert RequisicaoOficial.objects.filter(candidaturas__isnull=False).exists()


@pytest.mark.django_db
def test_extracao_igual_a_anterior_nao_guarda_arquivo_novo(scpi):
    primeira = extracao(scpi)
    segunda = extracao(scpi)
    assert primeira.arquivo is not None
    assert segunda.arquivo is None and segunda.mesmo_arquivo_que == primeira


@pytest.mark.django_db
def test_origem_so_perde_o_bruto_quando_ela_e_as_que_apontam_passaram_dos_60_dias(scpi):
    origem = extracao(scpi)
    copia = extracao(scpi)
    assert copia.mesmo_arquivo_que == origem
    envelhecer(origem)  # a cópia, recente, segura o bruto da origem
    assert limpar().brutos == 0
    origem.refresh_from_db()
    assert origem.arquivo is not None
    envelhecer(copia)
    assert limpar().brutos == 1
    origem.refresh_from_db()
    assert origem.arquivo is None and origem.arquivo_apagado_em is not None


@pytest.mark.django_db
def test_extracao_igual_a_uma_origem_sem_bruto_guarda_o_seu(scpi):
    origem = extracao(scpi)
    envelhecer(origem)
    limpar()
    nova = extracao(scpi)
    assert nova.arquivo is not None and nova.mesmo_arquivo_que is None
    assert nova.impressao == ExtracaoOficial.objects.get(pk=origem.pk).impressao


@pytest.mark.django_db
def test_limpeza_espera_a_extracao_em_andamento(scpi, trava_importacao_ocupada):
    origem = extracao(scpi)
    envelhecer(origem)
    trava_importacao_ocupada(Importacao.Tipo.REQUISICOES)
    assert limpar() is None
    origem.refresh_from_db()
    assert origem.arquivo is not None


@pytest.mark.django_db
def test_limpeza_espera_a_conciliacao_em_andamento(scpi, monkeypatch):
    from django.db import connections

    from conciliacao import servicos

    origem = extracao(scpi)
    envelhecer(origem)
    monkeypatch.setattr(servicos, "ESPERA_TRAVA_S", 0)
    outra = connections.create_connection("default")
    try:
        with outra.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0)", [servicos.TRAVA_CONCILIACAO])
        assert limpar() is None
    finally:
        outra.close()
    origem.refresh_from_db()
    assert origem.arquivo is not None


COMANDO = "conciliacao.management.commands.conciliar_lancamentos"


@pytest.fixture
def comando_com_scpi(scpi, monkeypatch):
    scpi.requisicao_manual(timezone.localdate(), tipo="OUTRA")
    monkeypatch.setattr(f"{COMANDO}.relatorios.baixar_requisicoes", scpi.relatorio)
    return scpi


@pytest.mark.django_db
def test_limpeza_roda_mesmo_com_falha_inesperada_da_conciliacao(comando_com_scpi, monkeypatch):
    limpezas = []

    def quebra(extracao):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(f"{COMANDO}.conciliar", quebra)
    monkeypatch.setattr(f"{COMANDO}.limpar", lambda: limpezas.append(1))
    with pytest.raises(CommandError, match="Conciliação com o SCPI falhou: banco fora do ar"):
        call_command("conciliar_lancamentos")
    assert limpezas == [1]


@pytest.mark.django_db
def test_falha_da_conciliacao_e_da_limpeza_saem_juntas(comando_com_scpi, monkeypatch):
    from conciliacao.servicos import ConciliacaoIncompleta

    def incompleta(extracao):
        raise ConciliacaoIncompleta({}, ["lotes lançados: tabela indisponível"])

    def quebra_limpeza():
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(f"{COMANDO}.conciliar", incompleta)
    monkeypatch.setattr(f"{COMANDO}.limpar", quebra_limpeza)
    with pytest.raises(CommandError) as erro:
        call_command("conciliar_lancamentos")
    assert "tabela indisponível" in str(erro.value)
    assert "Limpeza de 60 dias falhou: disco cheio" in str(erro.value)
