import itertools
from datetime import date
from decimal import Decimal

import pytest

from pedidos.models import LinhaSaida
from pedidos.regras import Centro
from scpi.requisicoes import agrupar, qtd_scpi, selecionar

_ids = itertools.count(1)

CENTROS = [
    Centro("ETA II", "90104"),
    Centro("OFICINA MECÂNICA", "20"),
    Centro("PICKUP 01", "31", "ABC1D23"),
    Centro("RETRO A", "41", "XYZ9K99"),
    Centro("RETRO B", "42", "XYZ9K99"),
]


def L(codigo, lote="P-000001", status="PENDENTE", **extra):
    campos = dict(
        id=next(_ids),
        lote=lote,
        status=status,
        data=date(2026, 10, 9),
        qtd=Decimal("1"),
        codigo=codigo,
        recebedor="JOÃO",
        centro_custo="ETA II",
        tipo_saida="BALCÃO",
        placa="",
    )
    campos.update(extra)
    return LinhaSaida(**campos)


def test_um_lote_vira_uma_requisicao_com_cabecalho_resolvido():
    sel = selecionar([L("001.001.001"), L("001.001.002", qtd=Decimal("1.500"))], CENTROS)
    (req,) = sel.requisicoes
    assert (req.lote, req.data, req.cod_ccusto, req.tipo_saida, req.recebedor, req.erro) == (
        "P-000001",
        "09/10/2026",
        "90104",
        "BALCÃO",
        "JOÃO",
        "",
    )
    assert [(i.cadpro, i.qtd) for i in req.itens] == [("001.001.001", "1"), ("001.001.002", "1,5")]
    assert req.ids == [req.linhas[0].id, req.linhas[1].id]
    assert str(req) == "P-000001 | 09/10/2026 | JOÃO | c.custo 90104 | 2 item(ns)"


def test_lotes_diferentes_separam_mesmo_com_codigo_repetido():
    sel = selecionar(
        [
            L("001.002.004", "P-000005"),
            L("002.001.003", "P-000005"),
            L("001.002.004", "AV-000008"),
        ],
        CENTROS,
    )
    assert [r.lote for r in sel.requisicoes] == ["P-000005", "AV-000008"]
    assert all(r.erro == "" for r in sel.requisicoes)


def test_mesmo_lote_com_codigo_repetido_e_recusado():
    (req,) = selecionar([L("001.002.004"), L("001.002.004")], CENTROS).requisicoes
    assert "código 001.002.004 repetido na mesma requisição" in req.erro


@pytest.mark.parametrize("trava", ["VERIFICAR", "EM_LANCAMENTO", "ERRO"])
def test_trava_bloqueia_so_o_proprio_lote(trava):
    sel = selecionar(
        [
            L("001.001.001", "P-000001", trava),
            L("001.001.002", "P-000001"),
            L("001.001.003", "P-000002"),
        ],
        CENTROS,
    )
    assert [r.lote for r in sel.requisicoes] == ["P-000002"]
    assert sel.travados == ["P-000001"]


def test_lancadas_e_nao_lancar_ficam_de_fora_sem_travar():
    sel = selecionar(
        [
            L("001.001.001", status="LANCADA"),
            L("001.001.002", status="NAO_LANCAR"),
            L("001.001.003"),
        ],
        CENTROS,
    )
    assert [len(r.itens) for r in sel.requisicoes] == [1] and sel.travados == []


def test_placa_com_centro_proprio_decide_o_centro():
    (req,) = selecionar(
        [L("001.001.001", placa="ABC1D23", centro_custo="ETA II")], CENTROS
    ).requisicoes
    assert req.cod_ccusto == "31" and req.itens[0].placa == "ABC1D23"


def test_placa_sem_centro_e_centro_vazio_cai_na_oficina():
    (req,) = selecionar([L("001.001.001", placa="ZZZ0Z00", centro_custo="")], CENTROS).requisicoes
    assert req.cod_ccusto == "20"


def test_placa_ambigua_e_centro_inexistente_sao_erros():
    (a,) = selecionar([L("001.001.001", placa="XYZ9K99")], CENTROS).requisicoes
    (b,) = selecionar([L("001.001.001", centro_custo="ETA IX")], CENTROS).requisicoes
    assert "placa 'XYZ9K99' cadastrada em mais de um centro de custo" in a.erro
    assert "centro de custo 'ETA IX' não existe no cadastro de centros de custo" in b.erro


def test_tipo_fora_da_lista_do_scpi_e_erro_e_grafia_vem_da_lista():
    (a,) = selecionar([L("001.001.001", tipo_saida="EMPRESTIMO")], CENTROS).requisicoes
    (b,) = selecionar([L("001.001.001", tipo_saida="balcao")], CENTROS).requisicoes
    assert a.erro.startswith("'Tipo Saída' inválido 'EMPRESTIMO' (aceitos: BALCÃO,")
    assert b.tipo_saida == "BALCÃO"


def test_cabecalho_diferente_no_mesmo_lote_e_erro():
    (req,) = selecionar(
        [L("001.001.001"), L("001.001.002", recebedor="MARIA")], CENTROS
    ).requisicoes
    assert (
        "linhas do lote com data, recebedor, centro de custo, tipo ou placa diferentes" in req.erro
    )


def test_codigo_fora_do_padrao_e_quantidade_zero():
    (req,) = selecionar([L("1.2.3"), L("001.001.002", qtd=Decimal("0"))], CENTROS).requisicoes
    assert "código '1.2.3' fora do padrão 000.000.000" in req.erro
    assert "quantidade de 001.001.002 deve ser > 0" in req.erro


def test_qtd_no_formato_do_scpi():
    assert [qtd_scpi(Decimal(v)) for v in ("10.000", "0.330", "1234.5")] == [
        "10",
        "0,33",
        "1234,5",
    ]


@pytest.mark.parametrize("status", ["PENDENTE", "VERIFICAR"])
def test_linha_com_numero_de_requisicao_trava_o_lote_inteiro(status):
    """Linha que já tem número de requisição foi lançada (é o que a situação mostra): o lote
    não sai de novo, mesmo com o status voltado para `PENDENTE`."""
    sel = selecionar(
        [
            L("001.001.001", "P-000001", status, requisicao_scpi="003354/26"),
            L("001.001.002", "P-000001"),
            L("001.001.003", "P-000002"),
        ],
        CENTROS,
    )
    assert [r.lote for r in sel.requisicoes] == ["P-000002"]
    assert sel.travados == ["P-000001"]


def test_lancada_com_numero_fica_de_fora_e_as_pendentes_do_lote_seguem():
    sel = selecionar(
        [
            L("001.001.001", status="LANCADA", requisicao_scpi="003354/26"),
            L("001.001.002", status="NAO_LANCAR", requisicao_scpi="003354/26"),
            L("001.001.003"),
        ],
        CENTROS,
    )
    assert [[i.cadpro for i in r.itens] for r in sel.requisicoes] == [["001.001.003"]]
    assert sel.travados == []


def test_agrupar_separa_a_fila_dos_travados_na_ordem_do_robo():
    linhas = [
        L("001.001.001", "P-000003"),
        L("001.001.002", "P-000001", "VERIFICAR"),
        L("001.001.003", "P-000001"),
        L("001.001.004", "P-000002", requisicao_scpi="003354/26"),
        L("001.001.005", "P-000004", "LANCADA"),
        L("001.001.006", "P-000005", "NAO_LANCAR"),
        L("001.001.007", "AV-000006"),
        L("001.001.008", "P-000003"),
        L("001.001.009", "P-000007", "ERRO"),
        L("001.001.010", "P-000008", "EM_LANCAMENTO"),
    ]
    grupos, travados = agrupar(linhas)
    assert list(grupos) == ["P-000003", "AV-000006"]
    assert [len(r.linhas) for r in grupos.values()] == [2, 1]
    assert travados == ["P-000001", "P-000002", "P-000007", "P-000008"]
    sel = selecionar(linhas, CENTROS)
    assert [r.lote for r in sel.requisicoes] == list(grupos) and sel.travados == travados


def test_placa_do_centro_de_viatura_fica_na_requisicao_sem_placa_na_saida():
    # O SCPI preenche a placa sozinho pelo centro de viatura: a foto da tentativa precisa dela.
    (req,) = selecionar([L("001.001.001", centro_custo="PICKUP 01")], CENTROS).requisicoes
    assert (req.cod_ccusto, req.placa_centro, req.itens[0].placa) == ("31", "ABC1D23", "")


def test_centro_sem_placa_deixa_a_placa_do_centro_vazia():
    (req,) = selecionar([L("001.001.001")], CENTROS).requisicoes
    assert req.placa_centro == ""


def test_placa_do_centro_vazia_quando_o_codigo_tem_placas_diferentes():
    centros = [*CENTROS, Centro("PICKUP 01", "31", "DEF2G34")]
    (req,) = selecionar([L("001.001.001", centro_custo="PICKUP 01")], centros).requisicoes
    assert req.placa_centro == ""
