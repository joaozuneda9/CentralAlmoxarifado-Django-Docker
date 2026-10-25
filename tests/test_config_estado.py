"""O estado efetivo de um material num formulário (spec 009, data-model.md): função pura."""

import pytest

from catalogo.disponibilidade import (
    ACRESCENTADO,
    FORA,
    REGRA,
    RETIRADO,
    Estado,
    estado,
)

# (oculto, na_regra, excecao) -> (disponivel, origem, sem_efeito)
TABELA = [
    # Sem ser oculto: as seis combinações de regra e exceção.
    ((False, True, None), (True, REGRA, False)),
    ((False, True, False), (False, RETIRADO, False)),
    ((False, True, True), (True, REGRA, True)),  # acrescentar o que a regra já traz: sem efeito
    ((False, False, None), (False, FORA, False)),
    ((False, False, True), (True, ACRESCENTADO, False)),
    ((False, False, False), (False, FORA, True)),  # retirar o que a regra não traz: sem efeito
]


@pytest.mark.parametrize(("entrada", "esperado"), TABELA)
def test_tabela_do_estado(entrada, esperado):
    resultado = estado(*entrada)
    assert (resultado.disponivel, resultado.origem, resultado.sem_efeito) == esperado
    assert resultado.oculto is False


@pytest.mark.parametrize(("entrada", "esperado"), TABELA)
def test_oculto_nunca_esta_disponivel_e_guarda_o_que_seria(entrada, esperado):
    _, na_regra, excecao = entrada
    resultado = estado(True, na_regra, excecao)
    assert resultado.disponivel is False and resultado.oculto is True
    # A origem e o "sem efeito" são os que valeriam sem o oculto: a tela os mostra.
    assert (resultado.origem, resultado.sem_efeito) == (esperado[1], esperado[2])


def test_estado_e_imutavel():
    with pytest.raises(AttributeError):
        estado(False, True, None).disponivel = False  # type: ignore[misc]
    assert isinstance(estado(False, True, None), Estado)
