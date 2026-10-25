"""A folha (spec 006, FR-003, research R4/R5): a lista preenchida de uma vez, tudo ou nada.

`carrinho.aplicar_folha` é pura: recebe as linhas do carrinho, o fluxo, o catálogo e as
quantidades digitadas ({código: texto}) e devolve o carrinho novo ou os erros por linha."""

from decimal import Decimal

from django.test import override_settings

from catalogo.catalogos import ItemCatalogo
from pedidos.carrinho import LinhaCarrinho, aplicar_folha
from pedidos.fluxos import Fluxo


def item(codigo, nome, unidade="UN", estoque="10", fracionavel=False, duplicado=False):
    return ItemCatalogo(
        codigo=codigo,
        nome=nome,
        unidade=unidade,
        categoria="",
        grupo="REDES",
        subgrupo="",
        estoque=Decimal(estoque),
        disponivel=int(Decimal(estoque)),
        duplicado=duplicado,
        fracionavel=fracionavel,
    )


LUVA = item("L", "LUVA 3/4")
TUBO = item("T", "TUBO PVC 3/4", unidade="M", estoque="12.5", fracionavel=True)
TEE = item("E", "TEE 3/4", estoque="0")
PLUG = item("P", "PLUG 3/4", duplicado=True)
FITA = item("F", "FITA VEDA ROSCA")  # do AB, fora da folha
CATALOGO = [LUVA, TUBO, TEE, PLUG, FITA]
FOLHA = ["L", "T", "E", "P"]
FLUXO = Fluxo(
    nome="viaturas",
    origem="VIATURAS",
    titulo="Reposição de peças das viaturas",
    catalogo=lambda: CATALOGO,
    exemplo_busca="",
    folha=lambda: FOLHA,
)


def linha(i, q):
    return LinhaCarrinho(i.codigo, Decimal(q), i)


def aplicar(linhas, quantidades):
    return aplicar_folha(linhas, FLUXO, CATALOGO, quantidades)


def no_pedido(carrinho):
    return {linha.codigo: linha.quantidade for linha in carrinho.linhas}


def test_linhas_preenchidas_entram_e_as_em_branco_nao():
    r = aplicar([], {"L": "2", "T": "2,5", "E": "", "P": ""})
    assert not r.erros_folha and no_pedido(r) == {"L": Decimal(2), "T": Decimal("2.5")}


def test_a_folha_substitui_a_quantidade_e_nao_mexe_no_que_veio_da_busca():
    r = aplicar([linha(LUVA, "5"), linha(FITA, "1")], {"L": "2", "T": ""})
    assert no_pedido(r) == {"L": Decimal(2), "F": Decimal(1)}


def test_em_branco_ou_zero_tira_do_pedido():
    r = aplicar([linha(LUVA, "5"), linha(TUBO, "1")], {"L": "", "T": "0"})
    assert no_pedido(r) == {}


def test_codigo_fora_da_folha_ou_do_catalogo_e_ignorado():
    r = aplicar([], {"F": "3", "X": "1", "L": "1"})
    assert no_pedido(r) == {"L": Decimal(1)}


def test_tudo_ou_nada_com_um_erro_por_linha():
    antes = [linha(LUVA, "5")]
    r = aplicar(antes, {"L": "2,5", "T": "13", "E": "1", "P": "1"})
    assert r.linhas == antes
    assert r.erros_folha == {
        "L": "Este material só é pedido em quantidade inteira (unidade: UN).",
        "T": "Quantidade acima do estoque. Estoque disponível: 12,5 M.",
        "E": "Sem estoque — não pode ser adicionado.",
        "P": "Cadastro duplicado — avise o almoxarifado — não pode ser adicionado.",
    }


def test_quantidade_ilegivel_e_recusada_na_linha():
    r = aplicar([], {"L": "abc", "T": "1"})
    assert no_pedido(r) == {} and set(r.erros_folha) == {"L"}


def test_virgula_sem_numero_e_recusada_e_nao_tira_do_pedido():
    antes = [linha(LUVA, "5"), linha(TUBO, "1")]
    r = aplicar(antes, {"L": ",", "T": ",,"})
    assert r.linhas == antes and set(r.erros_folha) == {"L", "T"}


def test_zero_com_casas_tira_do_pedido():
    r = aplicar([linha(LUVA, "5"), linha(TUBO, "1")], {"L": "00", "T": "0,000"})
    assert no_pedido(r) == {}


@override_settings(PEDIDOS_MAX_ITENS=2)
def test_passar_do_limite_de_materiais_e_recusado():
    r = aplicar([linha(FITA, "1")], {"L": "1", "T": "1"})
    assert no_pedido(r) == {"F": Decimal(1)}
    assert r.erro == "O pedido pode ter no máximo 2 materiais."
