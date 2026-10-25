import openpyxl
import pytest

from implantacao.planilha import ErroPlanilha, ler_xlsx, texto_celula
from tests.depara_exemplo import salvar_xlsx

ABAS = {"Pares": ("Código", "Nome"), "Notas": ("Texto",)}


def _exemplo():
    return {
        "Pares": [
            {"Código": "001.001.001", "Nome": "Tubo", "Extra": "x"},
            {"Código": "001.001.002", "Nome": "Luva", "Extra": None},
            {"Código": "001.001.003", "Nome": "Cola", "Extra": None},
        ],
        "Notas": [{"Texto": "uma"}],
        "Ignorada": [{"Qualquer": 1}],
    }


def test_le_so_as_abas_pedidas_com_numero_da_linha(tmp_path):
    abas = ler_xlsx(salvar_xlsx(_exemplo(), tmp_path / "p.xlsx"), ABAS)
    assert set(abas) == set(ABAS)
    assert [linha["Código"] for linha in abas["Pares"]] == [
        "001.001.001",
        "001.001.002",
        "001.001.003",
    ]
    assert abas["Pares"][0]["_linha"] == 2
    assert abas["Pares"][0]["Extra"] == "x"


def test_linha_vazia_e_pulada_sem_mudar_a_numeracao(tmp_path):
    caminho = salvar_xlsx(_exemplo(), tmp_path / "p.xlsx")
    livro = openpyxl.load_workbook(caminho)
    livro["Pares"].insert_rows(3)  # linha 3 em branco
    livro.save(caminho)
    assert [linha["_linha"] for linha in ler_xlsx(caminho, ABAS)["Pares"]] == [2, 4, 5]


def test_cabecalho_com_espacos(tmp_path):
    exemplo = _exemplo()
    exemplo["Pares"] = [
        {(" Código " if k == "Código" else k): v for k, v in linha.items()}
        for linha in exemplo["Pares"]
    ]
    abas = ler_xlsx(salvar_xlsx(exemplo, tmp_path / "p.xlsx"), ABAS)
    assert abas["Pares"][0]["Código"] == "001.001.001"


def test_aba_e_coluna_faltando_aparecem_juntas(tmp_path):
    exemplo = _exemplo()
    del exemplo["Notas"]
    exemplo["Pares"] = [
        {k: v for k, v in linha.items() if k != "Nome"} for linha in exemplo["Pares"]
    ]
    with pytest.raises(ErroPlanilha) as erro:
        ler_xlsx(salvar_xlsx(exemplo, tmp_path / "p.xlsx"), ABAS)
    assert 'aba "Notas"' in str(erro.value)
    assert 'Pares: coluna "Nome"' in str(erro.value)


def test_cabecalho_repetido_vale_a_primeira_coluna(tmp_path):
    caminho = salvar_xlsx(_exemplo(), tmp_path / "p.xlsx")
    livro = openpyxl.load_workbook(caminho)
    folha = livro["Pares"]
    folha["D1"] = "Nome"
    folha["D2"] = "outro"
    livro.save(caminho)
    assert ler_xlsx(caminho, ABAS)["Pares"][0]["Nome"] == "Tubo"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (None, ""),
        ("  x ", "x"),
        ("'=SOMA(A1)", "=SOMA(A1)"),
        (12.0, "12"),
        (12, "12"),
        (1.5, "1.5"),
    ],
)
def test_texto_celula(valor, esperado):
    assert texto_celula(valor) == esperado
