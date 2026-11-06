"""Tela, avisos e correção da conciliação (spec 010, PR 5): a aba Lançamento no SCPI mostra os
vereditos e as candidatas, o "Conferir agora" e a correção do número de um lote lançado."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalogo.saude import saude_do_catalogo
from conciliacao.consultas import conciliacao_da_aba
from conciliacao.extracao import extrair
from conciliacao.models import ConferenciaLote, CorrecaoVinculo, ExtracaoOficial
from conciliacao.saude import um_dia_util_depois
from conciliacao.servicos import conciliar
from pedidos.models import ExecucaoRobo, LinhaSaida
from pedidos.servicos import corrigir_requisicao
from scpi.lancamento import executar_lancamento

ABA = reverse("automacoes:pagina") + "?aba=lancamento"


@pytest.fixture
def pessoa(client):
    usuario = get_user_model().objects.create_user(username="00099", password="x")
    client.force_login(usuario)
    return usuario


def lancar(scpi, lotes):
    return executar_lancamento(
        ExecucaoRobo.objects.create(), scpi.abrir, lotes=lotes, extrair=scpi.relatorio
    )


def nova_extracao(scpi):
    hoje = timezone.localdate()
    periodo = (hoje - timedelta(days=40), hoje + timedelta(days=1))
    extracao = extrair(ExtracaoOficial.Motivo.MANUAL, periodo, lambda: scpi.relatorio(*periodo))
    conciliar(extracao)
    return extracao


def atual(lote):
    return next(item for item in conciliacao_da_aba("todos").lotes if item.lote == lote)


# --- A aba ---


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_aba_mostra_veredito_diferencas_e_filtro(client, pessoa, dois_lotes, scpi):
    p, av = dois_lotes
    scpi.perde_tipo.add(av)  # o SCPI salva o AV com o tipo vazio
    lancar(scpi, [p, av])
    pagina = client.get(ABA).content.decode()
    assert "Conferência com o SCPI" in pagina
    assert 'Divergências <span class="conciliacao-filtro-numero">1</span>' in pagina
    assert av in pagina and "Divergente" in pagina
    assert 'esperado <span class="mono">BALCÃO</span>, no SCPI' in pagina
    assert p not in pagina.split('id="conciliacao"')[1]  # comprovado fica fora do padrão
    comprovados = client.get(ABA + "&veredito=comprovados").content.decode()
    assert p in comprovados.split('id="conciliacao"')[1] and "Comprovado" in comprovados


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_veredito_atual_e_a_conclusiva_mais_recente(dois_lotes, scpi):
    p, av = dois_lotes
    lancar(scpi, [p, av])  # a extração de depois dá o LANCAMENTO
    nova_extracao(scpi)  # e a seguinte, a REVISAO
    revisao = ConferenciaLote.objects.get(lote=p, tipo="REVISAO")
    assert atual(p).conferencia == revisao
    assert len(conciliacao_da_aba("todos").lotes) == 2  # uma linha por lote


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_trava_mostra_as_candidatas_e_o_e_esta(client, pessoa, dois_lotes, scpi):
    p, av = dois_lotes
    scpi.salva_e_falha.add(p)  # o SCPI salvou a 000001/26 e a resposta se perdeu
    lancar(scpi, [p, av])
    pagina = client.get(ABA).content.decode()
    assert f'Tem <span class="mono">{p}</span> nas observações' in pagina
    assert "É esta: 000001/26" in pagina
    assert "no SCPI que pode ser esta: 000001/26" in pagina


@pytest.mark.django_db
def test_sem_extracao_a_recusa_aponta_o_conferir_agora():
    from conciliacao.consultas import SEM_EXTRACAO

    assert "Conferir agora" in SEM_EXTRACAO


# --- Conferir agora ---


@pytest.mark.django_db
def test_conferir_agora_e_recusado_com_lancamento_em_andamento(client, pessoa, monkeypatch):
    iniciados = []
    monkeypatch.setattr("scpi.disparo._iniciar_comando", lambda *a: iniciados.append(a))
    ExecucaoRobo.objects.create()  # recém-criada e sem fim: em andamento
    resposta = client.post(reverse("automacoes:conferir"), follow=True)
    assert "lançamento em andamento" in resposta.content.decode()
    assert iniciados == []


@pytest.mark.django_db
def test_conferir_agora_inicia_o_comando(client, pessoa, monkeypatch):
    iniciados = []
    monkeypatch.setattr("scpi.disparo._iniciar_comando", lambda *a: iniciados.append(a))
    resposta = client.post(reverse("automacoes:conferir"))
    assert resposta.status_code == 302 and resposta["Location"].endswith("?aba=lancamento")
    assert iniciados[0][0] == ["conciliar_lancamentos"]


@pytest.mark.django_db
def test_conferir_e_corrigir_so_por_post(client, pessoa):
    assert client.get(reverse("automacoes:conferir")).status_code == 405
    assert client.get(reverse("automacoes:corrigir", args=["P-000001"])).status_code == 405


@pytest.mark.django_db
def test_cabecalho_da_conferencia_se_recarrega_so_enquanto_bloqueado(client, pessoa):
    alvo = {"HX-Request": "true", "HX-Target": "div#conferir-agora"}
    execucao = ExecucaoRobo.objects.create()  # lançamento em andamento: o botão fica bloqueado
    trecho = client.get(reverse("automacoes:pagina"), headers=alvo).content.decode()
    assert 'id="conferir-agora"' in trecho and 'hx-trigger="every 5s"' in trecho
    assert 'aria-disabled="true"' in trecho and "Conferência com o SCPI" in trecho
    assert 'id="conferir-agora-botao"' in trecho  # o mesmo id bloqueado e liberado: o foco volta
    ExecucaoRobo.objects.filter(pk=execucao.pk).update(fim=timezone.now(), situacao="SUCESSO")
    trecho = client.get(reverse("automacoes:pagina"), headers=alvo).content.decode()
    assert "hx-trigger" not in trecho and 'type="submit"' in trecho
    assert 'id="conferir-agora-botao"' in trecho


@pytest.mark.django_db
def test_erro_previsto_longo_da_extracao_sai_cortado_no_cabecalho(client, pessoa):
    from catalogo.models import Importacao

    imp = Importacao.objects.create(
        tipo=Importacao.Tipo.REQUISICOES,
        situacao=Importacao.Situacao.FALHA,
        fim=timezone.now(),
        erro="O relatório veio cortado " + "x" * 300,
    )
    ExtracaoOficial.objects.create(importacao=imp, motivo=ExtracaoOficial.Motivo.MANUAL)
    pagina = client.get(ABA).content.decode()
    cabecalho = pagina.split('id="conferir-agora"')[1].split("</p>")[0]
    assert "O relatório veio cortado" in cabecalho and "x" * 200 not in cabecalho


@pytest.mark.django_db
def test_falha_inesperada_da_extracao_aparece_resumida_em_portugues(client, pessoa):
    from catalogo.models import Importacao
    from scpi.execucao import PREFIXO_FALHA_INESPERADA

    imp = Importacao.objects.create(
        tipo=Importacao.Tipo.REQUISICOES,
        situacao=Importacao.Situacao.FALHA,
        fim=timezone.now(),
        erro=f"{PREFIXO_FALHA_INESPERADA} TimeoutError: page.click: Timeout 30000ms exceeded",
    )
    ExtracaoOficial.objects.create(importacao=imp, motivo=ExtracaoOficial.Motivo.MANUAL)
    pagina = client.get(ABA).content.decode()
    # O texto técnico fica só no "Detalhe técnico" do histórico; o cabeçalho mostra a frase.
    cabecalho = pagina.split('id="conferir-agora"')[1].split("</p>")[0]
    assert "O SCPI demorou demais para responder" in cabecalho
    assert "Timeout 30000ms" not in cabecalho


# --- Correção do número (FR-026) ---


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_corrigir_so_nao_encontrado_ou_conflito(dois_lotes, scpi, pessoa):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    r = corrigir_requisicao(p, "000009/26", usuario=pessoa)
    assert not r.ok and "Não encontrado ou Vínculo em conflito" in r.mensagem


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_corrigir_nao_encontrado_volta_a_aguardar_e_a_proxima_confere(dois_lotes, scpi, pessoa):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    salva = next(r for r in scpi.salvas if r.requisicao == "000001/26")
    scpi.salvas.remove(salva)  # excluída no SCPI: "Não encontrado"
    nova_extracao(scpi)
    assert atual(p).conferencia.veredito == "NAO_ENCONTRADO"
    # A pessoa lança à mão a requisição de novo no SCPI, com outro número, e o informa.
    scpi.salvas.append(
        replace(salva, requisicao="000003/26", id_requi=salva.id_requi + 50, observacoes="")
    )
    r = corrigir_requisicao(p, "000003/26", usuario=pessoa)
    assert r.ok, r.mensagem
    assert set(LinhaSaida.objects.filter(lote=p).values_list("requisicao_scpi", "status")) == {
        ("000003/26", "LANCADA")
    }
    correcao = CorrecaoVinculo.objects.get(lote=p)
    assert (correcao.anterior, correcao.novo, correcao.conferencia.veredito) == (
        "000001/26",
        "000003/26",
        "NAO_ENCONTRADO",
    )
    assert atual(p).conferencia is None and atual(p).rotulo == "Aguardando conferência"
    nova_extracao(scpi)
    ultima = ConferenciaLote.objects.filter(lote=p).order_by("-criada_em", "-pk").first()
    assert (ultima.tipo, ultima.veredito, ultima.requisicao.requisicao) == (
        "LANCAMENTO",  # o número novo começa do zero, sem "alterado" contra o anterior
        "COMPROVADO",
        "000003/26",
    )
    assert atual(p).conferencia == ultima


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_corrigir_recusa_numero_de_outro_lote_e_no_conflito_so_as_apontadas(
    dois_lotes, scpi, pessoa
):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    ConferenciaLote.objects.filter(lote=p).update(veredito="NAO_ENCONTRADO")
    r = corrigir_requisicao(p, "000002/26", usuario=pessoa)
    assert not r.ok and r.mensagem == f"A requisição 000002/26 do SCPI já está em {av}."
    r = corrigir_requisicao(p, "000001/26", usuario=pessoa)
    assert not r.ok and "já é o número gravado" in r.mensagem
    # No vínculo em conflito, só uma das duas requisições apontadas.
    conferencia = ConferenciaLote.objects.get(lote=p)
    conferencia.veredito = "CONFLITO"
    conferencia.outra_requisicao = conferencia.extracao.requisicoes_lidas.get(
        requisicao="000002/26"
    )
    conferencia.save()
    r = corrigir_requisicao(p, "000007/26", usuario=pessoa)
    assert not r.ok and "000001/26, 000002/26" in r.mensagem
    assert not CorrecaoVinculo.objects.exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_corrigir_conflito_com_a_requisicao_das_observacoes(dois_lotes, scpi, pessoa):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    # O número gravado leva a uma requisição feita à mão; as observações, à do robô.
    scpi.requisicao_manual(timezone.localdate(), tipo="OUTRA")
    manual = scpi.salvas[-1].requisicao
    LinhaSaida.objects.filter(lote=p).update(requisicao_scpi=manual)
    nova_extracao(scpi)
    assert atual(p).conferencia.veredito == "CONFLITO"
    assert sorted(atual(p).conflito_com) == sorted([manual, "000001/26"])
    r = corrigir_requisicao(p, "000001/26", usuario=pessoa)
    assert r.ok, r.mensagem
    nova_extracao(scpi)
    ultima = ConferenciaLote.objects.filter(lote=p).order_by("-criada_em", "-pk").first()
    assert (ultima.tipo, ultima.veredito, ultima.requisicao.requisicao) == (
        "LANCAMENTO",
        "COMPROVADO",
        "000001/26",
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_corrigir_espera_a_conciliacao_em_andamento(dois_lotes, scpi, pessoa, monkeypatch):
    from django.db import connections

    from conciliacao import servicos

    p, av = dois_lotes
    lancar(scpi, [p, av])
    ConferenciaLote.objects.filter(lote=p).update(veredito="NAO_ENCONTRADO")
    monkeypatch.setattr(servicos, "ESPERA_CORRECAO_S", 0)  # a da correção, não a padrão
    assert servicos.ESPERA_TRAVA_S == 120
    outra = connections.create_connection("default")
    try:
        with outra.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0)", [servicos.TRAVA_CONCILIACAO])
        r = corrigir_requisicao(p, "000009/26", usuario=pessoa)
    finally:
        outra.close()
    assert not r.ok and "conferência com o SCPI em andamento" in r.mensagem
    assert not CorrecaoVinculo.objects.exists()
    assert LinhaSaida.objects.filter(lote=p, requisicao_scpi="000001/26").exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_lista_paginada_e_lote_resolvido_a_mao_acompanhado(dois_lotes, scpi, pessoa, monkeypatch):
    from conciliacao import consultas
    from pedidos.servicos import resolver_lote

    p, av = dois_lotes
    scpi.salva_e_falha.add(p)  # fica em verificar; a pessoa informa o número
    lancar(scpi, [p, av])
    assert resolver_lote(p, "lancada", usuario=pessoa, requisicao="000001/26").ok
    ConferenciaLote.objects.filter(tipo__in=("LANCAMENTO", "REVISAO")).delete()
    lotes = {i.lote: i for i in consultas.lotes_conferidos()}
    assert lotes[p].conferencia is None  # acompanhado desde já, "Aguardando"
    monkeypatch.setattr(consultas, "LIMITE_DA_LISTA", 1)
    primeira = consultas.conciliacao_da_aba("todos", 1)
    segunda = consultas.conciliacao_da_aba("todos", 2)
    assert primeira.total == segunda.total == 2
    assert {primeira.lotes[0].lote, segunda.lotes[0].lote} == {p, av}


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_corrigir_recusado_com_lancamento_em_andamento(dois_lotes, scpi, pessoa):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    ConferenciaLote.objects.filter(lote=p).update(veredito="NAO_ENCONTRADO")
    ExecucaoRobo.objects.create()
    r = corrigir_requisicao(p, "000009/26", usuario=pessoa)
    assert not r.ok and "andamento" in r.mensagem


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_corrigir_pela_tela_volta_para_a_aba_com_a_mensagem(client, pessoa, dois_lotes, scpi):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    ConferenciaLote.objects.filter(lote=p).update(veredito="NAO_ENCONTRADO")
    pagina = client.get(ABA).content.decode()
    assert "Corrigir o número" in pagina
    resposta = client.post(
        reverse("automacoes:corrigir", args=[p]), {"requisicao": "000009/26"}, follow=True
    )
    assert "requisição corrigida para 000009/26" in resposta.content.decode()


# --- Avisos de saúde (FR-028) ---


def test_um_dia_util_depois_pula_o_fim_de_semana_no_fuso_local():
    local = timezone.get_current_timezone()

    def em(dia, hora):
        return timezone.make_aware(datetime(2026, 11, dia, hora), local)

    # Quinta às 23h vence sexta às 23h (hora local, não a de Greenwich).
    assert um_dia_util_depois(em(5, 23)) == em(6, 23)
    # Sexta às 15h vence só na segunda às 15h: no sábado à noite ainda não venceu.
    assert um_dia_util_depois(em(6, 15)) == em(9, 15)
    assert not um_dia_util_depois(em(6, 15)) <= em(7, 20)
    # Domingo às 22h local (segunda 01h em UTC): o lançado na quinta às 23h já venceu.
    assert um_dia_util_depois(em(5, 23)) <= em(8, 22).astimezone(UTC)


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_avisos_de_saude_da_conciliacao(dois_lotes, scpi):
    p, av = dois_lotes
    scpi.perde_tipo.add(av)
    lancar(scpi, [p, av])
    textos = [item.texto for item in saude_do_catalogo()]
    assert f"1 requisição lançada com divergência no SCPI: {av}." in textos
    ConferenciaLote.objects.filter(lote=p).update(veredito="NAO_ENCONTRADO")
    textos = [item.texto for item in saude_do_catalogo()]
    assert f"1 requisição lançada não encontrada no SCPI: {p}." in textos


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_aviso_de_lote_aguardando_ha_mais_de_um_dia_util(dois_lotes, scpi):
    p, _ = dois_lotes
    original = scpi.relatorio
    chamadas = []

    def so_a_de_antes(de, ate):
        chamadas.append(1)
        if len(chamadas) > 1:
            raise RuntimeError("SCPI fora")
        return original(de, ate)

    executar_lancamento(ExecucaoRobo.objects.create(), scpi.abrir, lotes=[p], extrair=so_a_de_antes)
    assert not any("aguardando" in i.texto for i in saude_do_catalogo())
    LinhaSaida.objects.filter(lote=p).update(lancado_em=timezone.now() - timedelta(days=4))
    assert any(
        i.texto == f"1 requisição aguardando conferência há mais de um dia útil: {p}."
        for i in saude_do_catalogo()
    )


@pytest.mark.django_db
def test_aviso_quando_a_ultima_extracao_falhou():
    hoje = timezone.localdate()

    def quebra():
        raise RuntimeError("tabela do SCPI indisponível")

    extrair(ExtracaoOficial.Motivo.MANUAL, (hoje - timedelta(days=1), hoje), quebra)
    assert any(
        i.nivel == "erro" and i.texto.startswith("Requisições do SCPI: a última extração falhou")
        for i in saude_do_catalogo()
    )
