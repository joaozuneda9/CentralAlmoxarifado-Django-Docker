"""Regra de quantidade por unidade do material (spec 005, US1): regras puras e fluxos."""

from decimal import Decimal

import pytest
from django.urls import reverse

from catalogo.models import ItemLimpeza, Material, Opcao
from pedidos.models import Pedido
from pedidos.regras import (
    CAUSA_ACIMA_DO_MAXIMO,
    CAUSA_FRACAO_EM_CONTAVEL,
    CAUSA_ILEGIVEL,
    CAUSA_ZERO,
    REGRA_LIVRE,
    REGRA_POR_UNIDADE,
    interpretar_quantidade,
    maximo_pedivel,
    texto_erro_quantidade,
    truncar_qtd,
)
from tests.cenario import montar_cenario
from tests.config_cenario import enviar_formulario

D = Decimal


# --- truncar_qtd -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (D("2.4996"), D("2.499")),
        (D("0.0004"), D("0")),
        (D("10"), D("10")),
        (D("2.5"), D("2.5")),
        (D("0.9999"), D("0.999")),
        (3, D("3")),
        ("1.2349", D("1.234")),
    ],
)
def test_truncar_qtd_corta_para_baixo_em_3_casas(valor, esperado):
    assert truncar_qtd(valor) == esperado


# --- maximo_pedivel ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("saldo", "fracionavel", "regra", "esperado"),
    [
        # Unidade de medida no formulário público: o saldo truncado a 3 casas.
        ("0.0004", True, REGRA_POR_UNIDADE, "0"),
        ("0.5", True, REGRA_POR_UNIDADE, "0.5"),
        ("2.4996", True, REGRA_POR_UNIDADE, "2.499"),
        ("2.5", True, REGRA_POR_UNIDADE, "2.5"),
        ("10", True, REGRA_POR_UNIDADE, "10"),
        # Unidade contável (ou sem unidade) no formulário público: só a parte inteira.
        ("0.0004", False, REGRA_POR_UNIDADE, "0"),
        ("0.5", False, REGRA_POR_UNIDADE, "0"),
        ("2.4996", False, REGRA_POR_UNIDADE, "2"),
        ("2.5", False, REGRA_POR_UNIDADE, "2"),
        ("10", False, REGRA_POR_UNIDADE, "10"),
        # A equipe aceita fração em qualquer unidade: o saldo truncado a 3 casas.
        ("0.0004", False, REGRA_LIVRE, "0"),
        ("0.5", False, REGRA_LIVRE, "0.5"),
        ("2.4996", False, REGRA_LIVRE, "2.499"),
        ("10", False, REGRA_LIVRE, "10"),
    ],
)
def test_maximo_pedivel_pela_unidade_e_pela_regra(saldo, fracionavel, regra, esperado):
    assert maximo_pedivel(D(saldo), fracionavel, regra) == D(esperado)


def test_maximo_pedivel_nunca_e_negativo():
    assert maximo_pedivel(D("-3"), True, REGRA_POR_UNIDADE) == D("0")
    assert maximo_pedivel(D("-3"), False, REGRA_LIVRE) == D("0")


# --- interpretar_quantidade --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "fracionavel", "valor"),
    [
        ("3", True, D("3")),
        ("3", False, D("3")),
        ("2,5", True, D("2.5")),
        ("0,001", True, D("0.001")),
        ("999999", False, D("999999")),
        ("999999", True, D("999999")),
        (" 4 ", False, D("4")),
        (D("2.5"), True, D("2.5")),
        (7, False, D("7")),
    ],
)
def test_interpretar_quantidade_valida(texto, fracionavel, valor):
    assert interpretar_quantidade(texto, fracionavel) == (valor, "")


@pytest.mark.parametrize(
    ("texto", "fracionavel", "causa"),
    [
        ("", True, CAUSA_ILEGIVEL),
        ("", False, CAUSA_ILEGIVEL),
        ("abc", True, CAUSA_ILEGIVEL),
        ("1.5", True, CAUSA_ILEGIVEL),  # ponto decimal: o robô leria 15
        ("1.5", False, CAUSA_ILEGIVEL),
        ("1,2345", True, CAUSA_ILEGIVEL),  # mais de 3 casas
        ("-1", True, CAUSA_ILEGIVEL),
        ("0", True, CAUSA_ZERO),
        ("0", False, CAUSA_ZERO),
        ("0,000", True, CAUSA_ZERO),
        ("2,5", False, CAUSA_FRACAO_EM_CONTAVEL),
        ("0,5", False, CAUSA_FRACAO_EM_CONTAVEL),
        ("1000000", True, CAUSA_ACIMA_DO_MAXIMO),
        ("1000000", False, CAUSA_ACIMA_DO_MAXIMO),
        ("999999,001", True, CAUSA_ACIMA_DO_MAXIMO),
    ],
)
def test_interpretar_quantidade_recusada_pela_causa(texto, fracionavel, causa):
    valor, achada = interpretar_quantidade(texto, fracionavel)
    assert valor is None and achada == causa


def test_fracao_com_zeros_a_direita_conta_como_inteira_em_material_contado():
    assert interpretar_quantidade("2,000", False) == (D("2"), "")


# --- textos únicos (contracts/mensagens.md) ----------------------------------------------------


def test_textos_de_erro_de_quantidade():
    fraciona = "Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5)."
    conta = "Informe um número inteiro maior que zero."
    assert texto_erro_quantidade(CAUSA_ILEGIVEL, fracionavel=True) == fraciona
    assert texto_erro_quantidade(CAUSA_ZERO, fracionavel=True) == fraciona
    assert texto_erro_quantidade(CAUSA_ILEGIVEL, fracionavel=False) == conta
    assert texto_erro_quantidade(CAUSA_ZERO, fracionavel=False) == conta
    assert texto_erro_quantidade(CAUSA_FRACAO_EM_CONTAVEL, fracionavel=False, unidade="UN") == (
        "Este material só é pedido em quantidade inteira (unidade: UN)."
    )
    assert texto_erro_quantidade(CAUSA_FRACAO_EM_CONTAVEL, fracionavel=False) == (
        "Este material só é pedido em quantidade inteira."
    )
    assert texto_erro_quantidade(CAUSA_ACIMA_DO_MAXIMO, fracionavel=True) == (
        "A quantidade máxima é 999.999."
    )


# --- pelo carrinho e pelo envio (US1) ----------------------------------------------------------

MEDIDA_LIMPEZA = "023.001.002"  # DETERGENTE NEUTRO, saldo 100
MEDIDA_AB = "016.005.010"  # FITA VEDA ROSCA, saldo 10
CONTADO_LIMPEZA = "023.004.001"  # PAPEL HIGIÊNICO, contado ("Pacote 500 g" na tela), saldo 50
CONTADO_AB = "013.006.001"  # BOTINA, saldo 2,5

TEXTO_FRACIONAVEL = "Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5)."
TEXTO_CONTADO = "Informe um número inteiro maior que zero."


@pytest.fixture
def cenario():
    montar_cenario()
    Material.objects.filter(codigo__in=[MEDIDA_LIMPEZA, MEDIDA_AB]).update(unidade="M")
    # Na tela da limpeza o texto da unidade é outro; a regra olha a unidade do SCPI.
    ItemLimpeza.objects.filter(material__codigo=CONTADO_LIMPEZA).update(
        unidade_exibida="Pacote 500 g"
    )


def adicionar_pelo_carrinho(client, fluxo, codigo, quantidade):
    return client.post(
        reverse("pedidos:carrinho", args=[fluxo]),
        {"adicionar": codigo, f"qtd-{codigo}": quantidade},
    ).text


def no_pedido(html, codigo):
    return f'name="item_codigo" value="{codigo}"' in html


def enviar(client, fluxo, codigo, quantidade):
    return enviar_formulario(
        client, fluxo, [(codigo, quantidade)], destino="ETA II", solicitante="Ana"
    ).text


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fluxo", "codigo"), [("limpeza", MEDIDA_LIMPEZA), ("ab", MEDIDA_AB)], ids=["limpeza", "ab"]
)
def test_unidade_de_medida_aceita_fracao_nos_dois_formularios(client, cenario, fluxo, codigo):
    html = adicionar_pelo_carrinho(client, fluxo, codigo, "2,5")
    assert no_pedido(html, codigo)
    assert 'value="2,5"' in html
    assert "Pedido registrado" in enviar(client, fluxo, codigo, "2,5")
    assert Pedido.objects.get().itens.get().qtd_pedida == Decimal("2.5")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fluxo", "codigo", "unidade_na_tela"),
    [("limpeza", CONTADO_LIMPEZA, "Pacote 500 g"), ("ab", CONTADO_AB, "UN")],
    ids=["limpeza", "ab"],
)
def test_unidade_contavel_recusa_fracao_ao_adicionar_alterar_e_enviar(
    client, cenario, fluxo, codigo, unidade_na_tela
):
    esperado = f"Este material só é pedido em quantidade inteira (unidade: {unidade_na_tela})."
    # Adicionar.
    html = adicionar_pelo_carrinho(client, fluxo, codigo, "1,5")
    assert esperado in html and not no_pedido(html, codigo)
    # Alterar: a linha volta à última quantidade válida.
    alterar = client.post(
        reverse("pedidos:carrinho", args=[fluxo]),
        {"item_codigo": [codigo], "item_qtd": ["1,5"], "alterar": codigo, "anterior": "1"},
    ).text
    assert esperado in alterar and 'name="item_qtd" value="1"' in alterar
    # Enviar: o mesmo texto, com o nome do material, e nada é gravado.
    enviado = enviar(client, fluxo, codigo, "1,5")
    assert esperado in enviado
    assert not Pedido.objects.exists()


@pytest.mark.django_db
def test_material_sem_unidade_recusa_fracao_sem_citar_a_unidade(client, cenario):
    Material.objects.filter(codigo=CONTADO_AB).update(unidade="")
    html = adicionar_pelo_carrinho(client, "ab", CONTADO_AB, "1,5")
    assert "Este material só é pedido em quantidade inteira." in html
    assert "(unidade:" not in html


@pytest.mark.django_db
@pytest.mark.parametrize("fluxo", ["limpeza", "ab"])
@pytest.mark.parametrize("texto", ["1,2345", "1.5", "0", "abc", ""])
def test_quantidade_ilegivel_em_material_fracionavel(client, cenario, fluxo, texto):
    codigo = MEDIDA_LIMPEZA if fluxo == "limpeza" else MEDIDA_AB
    html = adicionar_pelo_carrinho(client, fluxo, codigo, texto)
    assert TEXTO_FRACIONAVEL in html and not no_pedido(html, codigo)


@pytest.mark.django_db
@pytest.mark.parametrize("fluxo", ["limpeza", "ab"])
@pytest.mark.parametrize("texto", ["1.5", "0", "abc", ""])
def test_quantidade_ilegivel_em_material_contado(client, cenario, fluxo, texto):
    codigo = CONTADO_LIMPEZA if fluxo == "limpeza" else CONTADO_AB
    html = adicionar_pelo_carrinho(client, fluxo, codigo, texto)
    assert TEXTO_CONTADO in html and not no_pedido(html, codigo)


@pytest.mark.django_db
@pytest.mark.parametrize("fluxo", ["limpeza", "ab"])
def test_quantidade_acima_de_999999_tem_a_propria_mensagem(client, cenario, fluxo):
    codigo = MEDIDA_LIMPEZA if fluxo == "limpeza" else MEDIDA_AB
    html = adicionar_pelo_carrinho(client, fluxo, codigo, "1000000")
    assert "A quantidade máxima é 999.999." in html and not no_pedido(html, codigo)


@pytest.mark.django_db
def test_a_lista_de_unidades_vale_no_proximo_pedido_sem_reiniciar(client, cenario):
    assert no_pedido(adicionar_pelo_carrinho(client, "ab", MEDIDA_AB, "2,5"), MEDIDA_AB)
    Opcao.objects.filter(lista=Opcao.Lista.UNIDADE_FRACIONAVEL, valor="M").update(ativo=False)
    html = adicionar_pelo_carrinho(client, "ab", MEDIDA_AB, "2,5")
    assert "Este material só é pedido em quantidade inteira (unidade: M)." in html
