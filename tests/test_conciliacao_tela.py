"""Tela, avisos e correção da conciliação (spec 010, PR 5): a aba Lançamento no SCPI mostra os
vereditos e as candidatas, o "Conferir agora" e a correção do número de um lote lançado."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalogo.saude import saude_do_catalogo
from conciliacao.consultas import conciliacao_da_aba
from conciliacao.extracao import extrair
from conciliacao.models import ConferenciaLote, CorrecaoVinculo, ExtracaoOficial
from conciliacao.saude import um_dia_util_antes
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


def test_conferir_e_corrigir_so_por_post(client):
    assert client.get(reverse("automacoes:conferir")).status_code in (302, 405)


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


def test_um_dia_util_antes_pula_o_fim_de_semana():
    segunda = datetime(2026, 11, 9, 10, 0)
    assert um_dia_util_antes(segunda) == datetime(2026, 11, 6, 10, 0)  # sexta
    quarta = datetime(2026, 11, 4, 10, 0)
    assert um_dia_util_antes(quarta) == datetime(2026, 11, 3, 10, 0)


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
