"""Exemplo da planilha MAPEAMENTO DE/PARA CONSOLIDADO exportada (.xlsx), para os testes do
`importar_depara`. Só as abas e colunas que a carga lê, mais uma coluna a mais em cada aba."""

from pathlib import Path

import openpyxl

ABA_MAPEAMENTO = "Planilha de mapeamento depara"


def _mapeamento(antigo, novo, nome="MATERIAL"):
    return {"Nome": nome, "Código Antigo": antigo, "Código Novo": novo}


def _depara(antigo, novo, fator=None, observacao=""):
    return {
        "Código Antigo": antigo,
        "Código Novo": novo,
        "Código Canônico": novo,
        "Fator p/ Qtd": fator,
        "Observação": observacao,
    }


def abas_depara(aba_mapeamento: str = ABA_MAPEAMENTO) -> dict[str, list[dict[str, object]]]:
    """Linha 2 em diante de cada aba (a 1 é o cabeçalho):

    Mapeamento: 2 par válido; 3 "PRODUTO NOVO"; 4 traço; 5 vazio no novo; 6 antigo repetido
    (vale a linha 2); 7 antigo = novo; 8 par corrigido pela DEPARA; 9 e 10 fecham um ciclo (a 10 é
    recusada); 11 par válido com código novo fora do cadastro.

    DEPARA: 2 corrige o par da linha 8, com fator 5; 3 par só da DEPARA; 4 fator inválido.
    """
    return {
        aba_mapeamento: [
            _mapeamento("000.029.872", "016.001.021", "TUBO PEAD"),
            _mapeamento("000.000.010", "PRODUTO NOVO"),
            _mapeamento("000.000.011", "-"),
            _mapeamento("000.000.012", None),
            _mapeamento("000.029.872", "016.009.999"),
            _mapeamento("003.001.001", "003.001.001"),
            _mapeamento("010.000.113", "023.004.009"),
            _mapeamento("000.000.020", "000.000.021"),
            _mapeamento("000.000.021", "000.000.020"),
            _mapeamento("003.000.025", "003.001.002"),
        ],
        "DEPARA": [
            _depara("010.000.113", "023.004.001", 5, "álcool 5 L virou 1 L"),
            _depara("004.000.019", "004.001.019"),
            _depara("004.000.022", "004.001.022", "zero"),
        ],
    }


def salvar_xlsx(abas: dict[str, list[dict[str, object]]], caminho: Path) -> Path:
    """Grava uma aba por chave; o cabeçalho são as chaves da primeira linha, sem `_linha`."""
    livro = openpyxl.Workbook()
    livro.remove(livro.active)
    for nome, linhas in abas.items():
        folha = livro.create_sheet(nome)
        cabecalho = [chave for chave in linhas[0] if chave != "_linha"]
        folha.append(cabecalho)
        for linha in linhas:
            folha.append([linha.get(chave) for chave in cabecalho])
    livro.save(caminho)
    return caminho


def salvar_depara(caminho: Path, abas=None) -> Path:
    return salvar_xlsx(abas or abas_depara(), caminho)
