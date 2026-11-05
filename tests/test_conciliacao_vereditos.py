"""Vereditos dos lotes lançados e a revisão (spec 010, PR 4). Os casos do SC-002a são sintéticos:
o CSV real (com nomes de pessoas) só se repassa à mão, numa cópia do banco."""

import unicodedata
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from conciliacao import regras
from conciliacao.consultas import liberacao
from conciliacao.extracao import extrair
from conciliacao.models import ConferenciaLote, ExtracaoOficial
from conciliacao.servicos import conciliar
from pedidos.models import ExecucaoRobo, LinhaSaida
from scpi.lancamento import executar_lancamento
from scpi.requisicoes import ResultadoIncerto
from tests.relacao_requisicoes import ItemCSV, RequisicaoCSV

Item = regras.ItemConferido
DIA = date(2026, 10, 23)


def entrega(**campos):
    base = dict(
        data=DIA,
        tipo="BALCÃO",
        cod_ccusto="15",
        centro_nome="MANUTENÇÃO DE REDE DE ÁGUA",
        recebedor="Recebedor Sintético",
        placa_centro="",
        itens=(Item("023.003.004", Decimal("5")), Item("023.002.010", Decimal("4"))),
    )
    base.update(campos)
    return regras.Entrega(**base)


def oficial(requisicao="003584/26", lote="", **campos):
    base = dict(
        requisicao=requisicao,
        lote_observado=lote,
        data=DIA,
        tipo="BALCÃO",
        cod_ccusto="15",
        centro_nome="MANUTENÇÃO DE REDE DE ÁGUA",
        recebedor="Recebedor Sintético",
        itens=(Item("023.002.010", Decimal("4.0000")), Item("023.003.004", Decimal("5"))),
    )
    base.update(campos)
    return regras.Oficial(**base)


def campos(diferencas):
    return [d["campo"] for d in diferencas]


# --- Comparação (FR-016, FR-019, FR-019a, FR-019b, FR-020) ---


def test_mesma_entrega_nao_tem_diferenca_nem_nota():
    assert regras.comparar(entrega(), oficial()) == ([], [])


def test_tipo_vazio_no_scpi_e_divergencia_de_tipo():
    diferencas, _ = regras.comparar(entrega(), oficial(tipo=""))
    assert diferencas == [{"campo": "tipo", "esperado": "BALCÃO", "oficial": "(vazio)"}]


def test_codigo_trocado_e_divergencia_de_codigo_e_o_depara_so_explica():
    lote = entrega(itens=(Item("024.006.011", Decimal("1")),))
    scpi = oficial(itens=(Item("006.011.020", Decimal("1")),))
    diferencas, notas = regras.comparar(lote, scpi, {"006.011.020": "024.006.011"})
    assert diferencas == [
        {"campo": "código", "esperado": "024.006.011 × 1", "oficial": "006.011.020 × 1"}
    ]
    assert notas == [
        {"campo": "código", "texto": "de/para: 006.011.020 → 024.006.011 (só explicação)"}
    ]


def test_item_a_mais_e_quantidade_diferente_mostram_so_o_que_difere():
    scpi = oficial(itens=(Item("023.002.010", Decimal("4")), Item("023.003.004", Decimal("3")),
                          Item("023.001.001", Decimal("6"))))  # fmt: skip
    diferencas, _ = regras.comparar(entrega(), scpi)
    assert diferencas == [
        {"campo": "itens", "esperado": "023.003.004 × 5",
         "oficial": "023.001.001 × 6; 023.003.004 × 3"}
    ]  # fmt: skip


def test_data_diferente():
    diferencas, _ = regras.comparar(entrega(), oficial(data=date(2026, 10, 21)))
    assert campos(diferencas) == ["data"]


def test_centro_renomeado_com_o_mesmo_codigo_e_so_nota():
    scpi = oficial(cod_ccusto="0015", centro_nome="Viatura de Manutenção #68")
    diferencas, notas = regras.comparar(entrega(centro_nome="Equipe de Manutenção #168"), scpi)
    assert diferencas == [] and campos(notas) == ["centro de custo"]


def test_centro_com_outro_codigo_e_divergencia():
    assert campos(regras.comparar(entrega(), oficial(cod_ccusto="4"))[0]) == ["centro de custo"]


def test_acentos_decompostos_maiusculas_e_espacos_nas_pontas_nao_divergem():
    decomposto = unicodedata.normalize("NFD", "  RECEBEDOR SINTÉTICO ")
    lote = entrega(recebedor="Recebedor Sintético", centro_nome="Manutenção")
    scpi = oficial(recebedor=decomposto, centro_nome=unicodedata.normalize("NFD", "MANUTENÇÃO"))
    assert regras.comparar(lote, scpi) == ([], [])


def test_placa_vinda_do_centro_vale_e_placa_diferente_diverge():
    itens = (Item("006.003.005", Decimal("1")),)
    lote = entrega(placa_centro="CYU4A99", itens=itens)
    assert regras.comparar(lote, oficial(itens=(Item("006.003.005", 1, "CYU-4A99"),))) == ([], [])
    diferencas, _ = regras.comparar(lote, oficial(itens=(Item("006.003.005", 1, "ABC1D23"),)))
    assert campos(diferencas) == ["placa"]


# --- Veredito (FR-015, FR-016, SC-005, SC-008) ---


def test_comprovado_ligado_pelas_observacoes_e_pelo_numero():
    r = regras.veredito("AV-1", "003584/26", [oficial(lote="AV-1")], entrega(), maior="003600/26")
    assert (r.veredito, r.origem, r.requisicao.requisicao) == ("COMPROVADO", "AMBOS", "003584/26")


def test_so_pelo_numero_avisa_que_o_lote_nao_esta_nas_observacoes():
    r = regras.veredito("AV-1", "003584/26", [oficial()], entrega(), maior="003600/26")
    assert (r.veredito, r.origem) == ("COMPROVADO", "NUMERO")
    assert campos(r.notas) == ["observações"]
    sem = regras.veredito(
        "AV-1", "003584/26", [oficial()], entrega(), maior=None, espera_observacoes=False
    )
    assert sem.notas == ()


def test_tres_lotes_identicos_no_mesmo_dia_cada_um_na_sua_requisicao():
    reqs = [oficial(f"00358{n}/26", f"AV-00004{n}") for n in (0, 1, 2)]
    for n in (0, 1, 2):
        r = regras.veredito(f"AV-00004{n}", f"00358{n}/26", reqs, entrega(), maior="003582/26")
        assert (r.veredito, r.requisicao.requisicao) == ("COMPROVADO", f"00358{n}/26")


def test_observacoes_e_numero_em_requisicoes_diferentes_e_conflito():
    reqs = [oficial("003584/26"), oficial("003590/26", "AV-1")]
    r = regras.veredito("AV-1", "003584/26", reqs, entrega(), maior="003600/26")
    assert (r.veredito, r.requisicao.requisicao, r.outra.requisicao) == (
        "CONFLITO",
        "003584/26",
        "003590/26",
    )


def test_duas_requisicoes_com_o_lote_ou_numero_em_outro_lote_e_duplicado():
    reqs = [oficial("003584/26", "AV-1"), oficial("003585/26", "AV-1")]
    assert regras.veredito("AV-1", "003584/26", reqs, entrega(), maior=None).veredito == (
        "DUPLICADO"
    )
    r = regras.veredito(
        "AV-1", "003584/26", [oficial()], entrega(), maior=None, numero_em_outro_lote=True
    )
    assert r.veredito == "DUPLICADO"


def test_nao_encontrado_so_com_numero_maior_no_relatorio():
    outras = [oficial("003590/26", "AV-9")]
    achou = regras.veredito("AV-1", "003584/26", outras, entrega(), maior="003590/26")
    assert achou.veredito == "NAO_ENCONTRADO"
    recem = regras.veredito("AV-1", "003584/26", [], entrega(), maior="003583/26")
    assert recem.veredito == "AGUARDANDO"  # SC-008: o relatório ainda não chegou ao número
    # Já achada numa conferência conclusiva, sumir não é demora do relatório.
    sumiu = regras.veredito("AV-1", "003584/26", [], entrega(), maior="003583/26", ja_vista=True)
    assert sumiu.veredito == "NAO_ENCONTRADO"


# --- Contra o SCPI simulado ---


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


def conferencias(lote):
    return list(
        ConferenciaLote.objects.filter(lote=lote, tipo__in=("LANCAMENTO", "REVISAO")).order_by(
            "criada_em", "pk"
        )
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_execucao_concilia_os_lotes_depois_de_lancar(dois_lotes, scpi):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    for lote in (p, av):
        (c,) = conferencias(lote)
        assert (c.tipo, c.veredito, c.origem_vinculo) == ("LANCAMENTO", "COMPROVADO", "AMBOS")
        assert c.tentativa is not None and c.diferencas == [] and c.notas == []


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_tipo_perdido_no_scpi_sai_divergente_e_a_correcao_vira_comprovado(dois_lotes, scpi):
    p, _ = dois_lotes
    scpi.perde_tipo.add(p)
    lancar(scpi, [p])
    (lancamento,) = conferencias(p)
    assert lancamento.veredito == "DIVERGENTE" and campos(lancamento.diferencas) == ["tipo"]
    scpi.salvas[0].tipo = "BALCÃO"  # alguém corrige o tipo no SCPI
    nova_extracao(scpi)
    lancamento_de_novo, revisao = conferencias(p)
    assert lancamento_de_novo.veredito == "DIVERGENTE"  # o veredito do lançamento fica
    assert (revisao.tipo, revisao.veredito, revisao.alterado_depois) == (
        "REVISAO",
        "COMPROVADO",
        True,
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_requisicao_editada_depois_do_lancamento_e_alterado_no_scpi(dois_lotes, scpi):
    p, _ = dois_lotes
    lancar(scpi, [p])
    scpi.salvas[0].itens.append(ItemCSV("023.001.001", "6"))
    nova_extracao(scpi)
    _, revisao = conferencias(p)
    assert revisao.alterado_depois and revisao.veredito == "DIVERGENTE"
    assert any(d.get("alteracao") and d["campo"] == "itens" for d in revisao.diferencas)


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_requisicao_excluida_vira_nao_encontrado_depois_de_um_numero_maior(dois_lotes, scpi):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    scpi.salvas = [r for r in scpi.salvas if r.requisicao != "000001/26"]
    nova_extracao(scpi)
    lancamento, revisao = conferencias(p)
    assert lancamento.veredito == "COMPROVADO"  # o veredito do lançamento fica
    assert (revisao.veredito, revisao.alterado_depois) == ("NAO_ENCONTRADO", True)
    assert revisao.diferencas == [
        {"campo": "requisição", "esperado": "000001/26", "oficial": "(ausente no relatório)",
         "alteracao": True}
    ]  # fmt: skip


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_excluida_a_requisicao_de_maior_numero_nao_volta_a_aguardando(dois_lotes, scpi):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    scpi.salvas = [r for r in scpi.salvas if r.requisicao != "000002/26"]  # a do AV, a maior
    nova_extracao(scpi)
    _, revisao = conferencias(av)
    assert (revisao.tipo, revisao.veredito, revisao.alterado_depois) == (
        "REVISAO",
        "NAO_ENCONTRADO",
        True,
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_aguardando_e_provisorio_e_nao_vira_revisao(dois_lotes, scpi):
    p, _ = dois_lotes
    lancar(scpi, [p])
    salva = scpi.salvas.pop()  # o relatório ainda não traz a requisição recém-salva
    # ...mas traz outra, de número menor: o relatório não está vazio (vazio seria falha).
    scpi.salvas.append(RequisicaoCSV("000000/26", 100, timezone.localdate(), tipo="OUTRA"))
    ConferenciaLote.objects.all().delete()
    nova_extracao(scpi)
    assert [(c.tipo, c.veredito) for c in conferencias(p)] == [("LANCAMENTO", "AGUARDANDO")]
    scpi.salvas.append(salva)
    nova_extracao(scpi)
    assert [(c.tipo, c.veredito) for c in conferencias(p)] == [
        ("LANCAMENTO", "AGUARDANDO"),
        ("LANCAMENTO", "COMPROVADO"),
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_lote_lancado_antes_da_conciliacao_usa_as_linhas_de_saida(dois_lotes, scpi):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    ConferenciaLote.objects.all().delete()
    from conciliacao.models import TentativaLancamento

    TentativaLancamento.objects.update(foto=None)  # como um lote lançado antes do PR 2
    nova_extracao(scpi)
    (c,) = conferencias(p)
    assert c.veredito == "COMPROVADO" and c.notas == []


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_comando_concilia_um_csv_e_recusa_com_lancamento_em_andamento(
    dois_lotes, scpi, tmp_path, capsys
):
    p, av = dois_lotes
    lancar(scpi, [p, av])
    ConferenciaLote.objects.all().delete()  # o arquivo dá o primeiro veredito
    hoje = timezone.localdate()
    arquivo = tmp_path / "requisicoes.csv"
    arquivo.write_bytes(scpi.relatorio(hoje - timedelta(days=40), hoje + timedelta(days=1)))
    call_command("conciliar_lancamentos", arquivo=str(arquivo))
    assert "comprovado" in capsys.readouterr().out
    assert len(conferencias(p)) == 1
    # Um arquivo não sabe quando foi exportado: não revisa o veredito que o lote já tem.
    call_command("conciliar_lancamentos", arquivo=str(arquivo))
    assert "nenhum lote a conferir" in capsys.readouterr().out
    assert len(conferencias(p)) == 1
    ExecucaoRobo.objects.create()  # em andamento
    with pytest.raises(CommandError, match="em andamento"):
        call_command("conciliar_lancamentos", arquivo=str(arquivo))
    assert LinhaSaida.objects.filter(status="LANCADA").count() == 3  # nada mudou nas linhas


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_revisao_compara_com_o_lancamento_e_nao_com_a_revisao_anterior(dois_lotes, scpi):
    p, _ = dois_lotes
    lancar(scpi, [p])
    scpi.salvas[0].itens.append(ItemCSV("023.001.001", "6"))
    nova_extracao(scpi)
    scpi.salvas[0].itens.pop()  # o SCPI volta à requisição do lançamento
    nova_extracao(scpi)
    _, primeira_revisao, segunda_revisao = conferencias(p)
    assert primeira_revisao.alterado_depois
    assert not segunda_revisao.alterado_depois
    assert segunda_revisao.veredito == "COMPROVADO"


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_arquivo_nunca_confere_lote_em_verificar(dois_lotes, scpi, tmp_path):
    # Um CSV exportado antes do Salvar que se perdeu não traria a requisição: o intervalo
    # sairia vazio e o lote seria relançado. A extração de arquivo não conta (Princípio III).
    p, av = dois_lotes
    scpi.falhas_salvar[p] = ResultadoIncerto("o SCPI não respondeu")
    lancar(scpi, [p, av])
    ConferenciaLote.objects.filter(tipo="VERIFICAR").delete()
    hoje = timezone.localdate()
    arquivo = tmp_path / "antigo.csv"
    arquivo.write_bytes(scpi.relatorio(hoje - timedelta(days=40), hoje + timedelta(days=1)))
    call_command("conciliar_lancamentos", arquivo=str(arquivo))
    assert not ConferenciaLote.objects.filter(lote=p, tipo="VERIFICAR").exists()
    assert not liberacao(p).permitida


def test_quantidades_trocadas_entre_os_mesmos_codigos_sao_itens():
    lote = entrega(itens=(Item("A", Decimal("1")), Item("B", Decimal("2"))))
    scpi = oficial(itens=(Item("A", Decimal("2")), Item("B", Decimal("1"))))
    assert campos(regras.comparar(lote, scpi)[0]) == ["itens"]


def test_placa_errada_aparece_mesmo_com_os_itens_divergindo():
    lote = entrega(itens=(Item("A", Decimal("1"), "ABC1D23"), Item("B", Decimal("2"))))
    scpi = oficial(itens=(Item("A", Decimal("1"), "XYZ9K99"), Item("B", Decimal("3"))))
    assert campos(regras.comparar(lote, scpi)[0]) == ["itens", "placa"]


def test_quantidade_na_quarta_casa_e_alteracao_e_aparece_no_texto():
    antes = oficial(itens=(Item("A", Decimal("1.0001")),))
    agora = oficial(itens=(Item("A", Decimal("1.0002")),))
    (mudou,) = regras.alteracoes(antes, agora)
    assert (mudou["antes"], mudou["agora"]) == ("A × 1,0001", "A × 1,0002")


def test_placa_editada_no_scpi_e_alteracao():
    antes = oficial(itens=(Item("A", Decimal("1"), "ABC1D23"),))
    agora = oficial(itens=(Item("A", Decimal("1"), "XYZ9K99"),))
    assert [m["campo"] for m in regras.alteracoes(antes, agora)] == ["placa"]


def test_centro_que_saiu_do_cadastro_nao_e_conferido_e_vira_nota():
    diferencas, notas = regras.comparar(entrega(cod_ccusto=""), oficial())
    assert diferencas == [] and campos(notas) == ["centro de custo"]


@pytest.mark.django_db
def test_comando_recusa_periodo_invertido_e_arquivo_que_nao_abre(tmp_path):
    with pytest.raises(CommandError, match="depois do fim"):
        call_command("conciliar_lancamentos", desde="24/10/2026", ate="22/10/2026")
    with pytest.raises(CommandError, match="Não foi possível ler"):
        call_command("conciliar_lancamentos", arquivo=str(tmp_path / "nao-existe.csv"))
    assert not ExtracaoOficial.objects.exists()


def test_codigo_trocado_e_quantidade_mudada_num_codigo_comum_sao_itens():
    lote = entrega(itens=(Item("A", Decimal("1")), Item("B", Decimal("2"))))
    scpi = oficial(itens=(Item("A", Decimal("2")), Item("C", Decimal("1"))))
    assert campos(regras.comparar(lote, scpi)[0]) == ["itens"]


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_etapa_que_falha_nao_some_e_o_comando_sai_com_erro(dois_lotes, scpi, tmp_path, monkeypatch):
    from conciliacao import servicos

    p, av = dois_lotes
    lancar(scpi, [p, av])

    def quebra(extracao, falhas=None):
        raise RuntimeError("tabela indisponível")

    monkeypatch.setattr(servicos, "conciliar_lancados", quebra)
    hoje = timezone.localdate()
    arquivo = tmp_path / "requisicoes.csv"
    arquivo.write_bytes(scpi.relatorio(hoje - timedelta(days=40), hoje + timedelta(days=1)))
    with pytest.raises(CommandError, match="lotes lançados: tabela indisponível"):
        call_command("conciliar_lancamentos", arquivo=str(arquivo))


def test_numero_que_leva_a_requisicao_de_outro_lote_nao_comprova():
    # Mesmo conteúdo, mas as observações dão a requisição do número como do lote B.
    r = regras.veredito("AV-1", "003584/26", [oficial(lote="AV-2")], entrega(), maior="003600/26")
    assert (r.veredito, r.requisicao.requisicao, r.outra) == ("CONFLITO", "003584/26", None)
    assert "AV-2" in r.notas[0]["texto"]


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_lote_resolvido_a_mao_usa_a_foto_da_tentativa_e_nao_o_cadastro_de_hoje(dois_lotes, scpi):
    from django.contrib.auth import get_user_model

    from catalogo.models import CentroCusto
    from pedidos.servicos import resolver_lote

    p, av = dois_lotes
    scpi.salva_e_falha.add(p)  # o SCPI salvou a 000001/26 e a resposta se perdeu
    lancar(scpi, [p, av])
    usuario = get_user_model().objects.create_user("00088", password="x")
    assert resolver_lote(p, "lancada", usuario=usuario, requisicao="000001/26").ok
    # O cadastro muda depois: o código do centro do lote não é mais o que o robô digitou.
    centro = LinhaSaida.objects.filter(lote=p).first().centro_custo
    CentroCusto.objects.filter(descricao=centro).update(codigo="999")
    ConferenciaLote.objects.filter(tipo__in=("LANCAMENTO", "REVISAO")).delete()
    nova_extracao(scpi)
    (c,) = conferencias(p)
    assert c.tentativa is not None and c.tentativa.resultado == "VERIFICAR"
    assert c.veredito == "COMPROVADO" and c.diferencas == []


@pytest.mark.django_db
@pytest.mark.usefixtures("journal")
def test_lote_que_quebra_nao_impede_os_outros_e_a_contagem_e_a_gravada(
    dois_lotes, scpi, monkeypatch
):
    from conciliacao import servicos
    from conciliacao.servicos import ConciliacaoIncompleta

    p, av = dois_lotes
    lancar(scpi, [p, av])
    ConferenciaLote.objects.all().delete()
    original = regras.veredito

    def quebra_no_av(lote, *args, **kwargs):
        if lote == av:  # uma foto malformada, por exemplo
            raise RuntimeError("tabela indisponível")
        return original(lote, *args, **kwargs)

    monkeypatch.setattr(servicos.regras, "veredito", quebra_no_av)
    with pytest.raises(ConciliacaoIncompleta) as erro:
        nova_extracao(scpi)
    # O AV vem antes na ordem e quebra; o P segue e fica gravado, e a contagem o diz.
    assert erro.value.contagem == {"COMPROVADO": 1}
    assert erro.value.falhas == [f"lote {av} (lançado): tabela indisponível"]
    assert [c.veredito for c in conferencias(p)] == ["COMPROVADO"]
    assert conferencias(av) == []
