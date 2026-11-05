import csv
import io
from datetime import date
from decimal import Decimal

import pytest

from scpi.leitura import ErroImportacao, ler_requisicoes
from tests.relacao_requisicoes import COLUNAS, ItemCSV, RequisicaoCSV, relatorio

DIA = date(2026, 10, 23)


def _req(numero=3588, **campos):
    return RequisicaoCSV(f"{numero:06d}/26", numero + 100, DIA, **campos)


def test_le_cada_requisicao_com_o_cabecalho_e_os_itens_na_ordem():
    conteudo = relatorio(
        [
            _req(
                3588,
                observacoes="Central Almoxarifado AV-000083",
                data_filtro=date(2026, 10, 24),
                itens=[ItemCSV("006.011.020", "2"), ItemCSV("023.003.004", "1,5", "LT")],
            ),
            _req(3589, tipo="", entrada=True, cod_ccusto="4", centro="ALMOXARIFADO"),
        ]
    )
    primeira, segunda = ler_requisicoes(conteudo).linhas
    assert (primeira.requisicao, primeira.ano, primeira.numero, primeira.id_requi) == (
        "003588/26",
        2026,
        3588,
        3688,
    )
    assert (primeira.data, primeira.data_filtro, primeira.tipo) == (
        DIA,
        date(2026, 10, 24),
        "BALCÃO",
    )
    assert (primeira.cod_ccusto, primeira.centro_nome, primeira.recebedor) == (
        "15",
        "MANUTENÇÃO DE REDE DE ÁGUA",
        "Recebedor Sintético",
    )
    assert primeira.observacoes == "Central Almoxarifado AV-000083"
    assert [(i.codigo, i.quantidade, i.unidade) for i in primeira.itens] == [
        ("006.011.020", Decimal("2"), "UN"),
        ("023.003.004", Decimal("1.5"), "LT"),
    ]
    assert (segunda.tipo, segunda.entrada, segunda.cod_ccusto) == ("", True, "4")


def test_registro_quebrado_em_duas_linhas_e_recolado():
    item = ItemCSV("003.001.001", descricao_longa="Cimento CP II-E-32\ncom escória granulada")
    (lida,) = ler_requisicoes(relatorio([_req(itens=[item])])).linhas
    assert [i.codigo for i in lida.itens] == ["003.001.001"]
    assert lida.recebedor == "Recebedor Sintético"


def test_csv_sem_quebra_de_linha_no_fim_e_valido():
    lidas = ler_requisicoes(relatorio([_req(3588), _req(3589)], quebra_final=False)).linhas
    assert [r.requisicao for r in lidas] == ["003588/26", "003589/26"]


def test_relatorio_cortado_no_meio_do_ultimo_registro_e_erro():
    texto = relatorio([_req(3588), _req(3589)], quebra_final=False).decode("utf-8-sig")
    cortado = texto[: texto.rindex("BALCÃO")].encode("utf-8-sig")  # o download parou ali
    with pytest.raises(ErroImportacao, match="cortado no registro 2"):
        ler_requisicoes(cortado)


def test_coluna_obrigatoria_ausente_e_erro_com_o_nome():
    conteudo = relatorio([_req()]).replace(b";TPREQUI;", b";TIPO;")
    with pytest.raises(ErroImportacao, match="TPREQUI"):
        ler_requisicoes(conteudo)


def test_relatorio_sem_nenhuma_requisicao_e_erro():
    with pytest.raises(ErroImportacao, match="nenhuma requisição"):
        ler_requisicoes(relatorio([]))


def test_numero_fora_do_formato_e_erro():
    with pytest.raises(ErroImportacao, match="número de requisição inválido"):
        ler_requisicoes(relatorio([RequisicaoCSV("3588/26", 3688, DIA)]))


def test_cabecalho_que_varia_dentro_da_requisicao_e_erro():
    conteudo = relatorio([_req(itens=[ItemCSV("1"), ItemCSV("2")])]).decode("utf-8-sig")
    linhas = conteudo.split("\r\n")
    linhas[2] = linhas[2].replace("Recebedor Sintético", "Outro Recebedor")
    with pytest.raises(ErroImportacao, match="RECEBE"):
        ler_requisicoes("\r\n".join(linhas).encode("utf-8-sig"))


def test_quantidade_ilegivel_e_erro_e_zero_e_aceito():
    with pytest.raises(ErroImportacao, match="quantidade inválida"):
        ler_requisicoes(relatorio([_req(itens=[ItemCSV("1", "dois")])]))
    (lida,) = ler_requisicoes(relatorio([_req(itens=[ItemCSV("1", "0")])])).linhas
    assert lida.itens[0].quantidade == 0


def test_mesmo_codigo_repetido_vira_duas_linhas():
    (lida,) = ler_requisicoes(
        relatorio([_req(itens=[ItemCSV("1", "2"), ItemCSV("1", "3")])])
    ).linhas
    assert [(i.codigo, i.quantidade) for i in lida.itens] == [("1", 2), ("1", 3)]


def test_placa_e_lida_por_item():
    itens = [ItemCSV("1", placa="CYU4A99"), ItemCSV("2")]
    (lida,) = ler_requisicoes(relatorio([_req(itens=itens)])).linhas
    assert [i.placa for i in lida.itens] == ["CYU4A99", ""]


def test_relatorio_salvo_por_planilha():
    original = relatorio([_req(itens=[ItemCSV("1", "1,5")])]).decode("utf-8-sig").split("\r\n")
    saida = io.StringIO()
    escritor = csv.writer(saida)
    for linha in filter(None, original):
        escritor.writerow(linha.split(";"))
    (lida,) = ler_requisicoes(saida.getvalue().encode("utf-8")).linhas
    assert (lida.requisicao, lida.itens[0].quantidade) == ("003588/26", Decimal("1.5"))


def test_gerador_usa_o_cabecalho_real():
    assert len(COLUNAS) == 65
    assert relatorio([]).startswith("﻿GRUPO;GRUPO_1;ID_REQUI;REQUI;".encode())


@pytest.mark.parametrize("quantidade", ["1,23456", "12345678901"])
def test_quantidade_que_nao_cabe_exata_no_banco_e_erro(quantidade):
    with pytest.raises(ErroImportacao, match="quantidade inválida"):
        ler_requisicoes(relatorio([_req(itens=[ItemCSV("1", quantidade)])]))


def test_quantidade_com_zeros_a_direita_e_no_limite_e_aceita():
    itens = [ItemCSV("1", "1,50000"), ItemCSV("2", "9999999999,9999")]
    (lida,) = ler_requisicoes(relatorio([_req(itens=itens)])).linhas
    assert [i.quantidade for i in lida.itens] == [Decimal("1.5"), Decimal("9999999999.9999")]


def test_fracao_longa_que_o_contexto_arredondaria_e_erro():
    quantidade = "1," + "0" * 34 + "1"  # 36 casas: o normalize() arredondaria para 1
    with pytest.raises(ErroImportacao, match="quantidade inválida"):
        ler_requisicoes(relatorio([_req(itens=[ItemCSV("1", quantidade)])]))
