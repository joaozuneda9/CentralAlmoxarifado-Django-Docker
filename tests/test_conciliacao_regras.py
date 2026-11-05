from datetime import date

import pytest

from conciliacao import regras


def test_chave_do_numero_visivel():
    assert regras.chave("003588/26") == (2026, 3588)
    assert regras.chave(" 000001/27 ") == (2027, 1)


@pytest.mark.parametrize("valor", ["", "3588/26", "003588-26", "003588/2026", "abc", None])
def test_chave_recusa_numero_fora_do_formato(valor):
    with pytest.raises(ValueError):
        regras.chave(valor)


def test_virada_do_ano_respeita_o_ano():
    assert regras.chave("000001/27") > regras.chave("004512/26")
    assert regras.maior_requisicao(["004512/26", "000001/27", "003000/26"]) == "000001/27"


def test_maior_requisicao_sem_nenhuma():
    assert regras.maior_requisicao([]) is None


def test_periodo_vai_do_dia_anterior_a_data_mais_antiga_ao_dia_seguinte_a_hoje():
    hoje = date(2026, 11, 3)
    assert regras.periodo([date(2026, 10, 29), date(2026, 11, 1)], hoje) == (
        date(2026, 10, 28),
        date(2026, 11, 4),
    )


def test_periodo_sem_datas_envolvidas_comeca_ontem():
    assert regras.periodo([], date(2026, 11, 3)) == (date(2026, 11, 2), date(2026, 11, 4))


def test_periodo_com_data_futura_ainda_comeca_no_dia_anterior_a_hoje():
    assert regras.periodo([date(2026, 11, 10)], date(2026, 11, 3))[0] == date(2026, 11, 2)


def test_lote_observado_acha_o_texto_do_robo():
    assert regras.lote_observado(regras.texto_observacoes("AV-000036")) == "AV-000036"
    assert regras.lote_observado("CENTRAL   almoxarifado p-000018") == "P-000018"


def test_lote_observado_no_meio_de_outro_texto():
    assert regras.lote_observado("Saída urgente. Central Almoxarifado AV-000140 ok") == "AV-000140"


@pytest.mark.parametrize(
    "texto",
    ["", None, "Ajuste de estoque decorrente de inventário", "Almoxarifado AV-000036"],
)
def test_sem_lote_nas_observacoes(texto):
    assert regras.lote_observado(texto) == ""


def test_lote_com_digitos_demais_nao_casa():
    # O lote precisa caber nos 12 caracteres de lote_observado.
    assert regras.lote_observado("Central Almoxarifado AV-123456789") == "AV-123456789"
    assert regras.lote_observado("Central Almoxarifado AV-1234567890") == ""
    assert regras.lote_observado("Central Almoxarifado AV-٠١٢") == ""  # dígitos não ASCII


def test_observacoes_levam_a_obs_da_saida_num_paragrafo_novo():
    assert regras.texto_observacoes("AV-000165") == "Central Almoxarifado AV-000165"
    assert (
        regras.texto_observacoes("AV-000165", "  Entregue ao\nAndré  ")
        == "Central Almoxarifado AV-000165\nObs.: Entregue ao André"
    )
    assert regras.lote_observado(regras.texto_observacoes("P-000019", "P-000020 junto")) == (
        "P-000019"
    )


def test_ponto_e_virgula_vira_virgula_nas_observacoes():
    assert regras.texto_observacoes("AV-1", "a; b;c") == "Central Almoxarifado AV-1\nObs.: a, b,c"
