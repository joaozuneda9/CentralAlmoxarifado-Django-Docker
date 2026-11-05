"""O robô de relatórios só roda contra o SCPI real; aqui se confere só a estrutura das esperas."""

import inspect

from scpi import relatorios


def test_cadastro_espera_a_geracao_por_muitos_minutos():
    # A primeira carga pede o cadastro inteiro (de 2000 até hoje), que o SCPI demora para gerar.
    assert relatorios.ESPERA_GERACAO_CADASTRO_MS >= 15 * 60 * 1000
    assert relatorios.ESPERA_GERACAO_ESTOQUE_MS >= 5 * 60 * 1000
    assert relatorios.ESPERA_GERACAO_SAIDAS_MS >= 5 * 60 * 1000


def test_cada_relatorio_usa_a_sua_constante_e_nao_um_numero_solto():
    for funcao, constante in (
        (relatorios.baixar_cadastro, "ESPERA_GERACAO_CADASTRO_MS"),
        (relatorios.baixar_estoque, "ESPERA_GERACAO_ESTOQUE_MS"),
        # As saídas BALCÃO e as requisições sem filtro (spec 010) usam a mesma navegação.
        (relatorios._relacao_de_requisicoes, "ESPERA_GERACAO_SAIDAS_MS"),
    ):
        fonte = inspect.getsource(funcao)
        assert f"timeout={constante}" in fonte, funcao.__name__
        assert "timeout=60000" not in fonte and "timeout=300000" not in fonte, funcao.__name__


def test_saidas_e_requisicoes_passam_pela_mesma_navegacao():
    assert "_relacao_de_requisicoes(" in inspect.getsource(relatorios.baixar_saidas)
    assert 'tipo="BALCÃO"' in inspect.getsource(relatorios.baixar_saidas)
    assert "tipo=None" in inspect.getsource(relatorios.baixar_requisicoes)
