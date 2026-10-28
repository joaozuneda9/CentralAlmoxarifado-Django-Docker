"""O estoque exibido é o limite real do pedido (spec 005, US2, SC-001).

A lista, o teto de adicionar e alterar, a validação do envio e o texto "Estoque disponível" usam o
mesmo número: o saldo truncado a 3 casas para unidade de medida e a parte inteira para unidade
contada, sem zeros à direita.
"""

import re
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils.html import strip_tags

from catalogo.models import Material
from pedidos.models import Pedido
from tests.cenario import montar_cenario
from tests.config_cenario import enviar_formulario

pytestmark = pytest.mark.django_db

# Um material por formulário e por tipo de unidade (todos com saldo 100 ou parecido no cenário).
MEDIDA = {"limpeza": ("023.001.002", "detergente"), "ab": ("016.005.010", "fita")}
CONTADO = {"limpeza": ("023.004.001", "papel"), "ab": ("013.006.001", "botina")}
FORMULARIOS = ["limpeza", "ab"]


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()


def definir(codigo, saldo, unidade):
    Material.objects.filter(codigo=codigo).update(estoque=Decimal(saldo), unidade=unidade)


def linha_da_lista(client, fluxo, codigo, busca):
    """O texto visível do item na lista de resultados do formulário."""
    html = client.get(reverse("pedidos:materiais", args=[fluxo]), {"q": busca}).text
    inicio = html.index(f'data-codigo="{codigo}"')
    item = html[inicio : html.index("</li>", inicio)]
    return " ".join(strip_tags(item).split())


def adicionar(client, fluxo, codigo, quantidade):
    return client.post(
        reverse("pedidos:carrinho", args=[fluxo]),
        {"adicionar": codigo, f"qtd-{codigo}": quantidade},
    ).text


def entra(html, codigo):
    return f'name="item_codigo" value="{codigo}"' in html


def enviar(client, fluxo, codigo, quantidade):
    return enviar_formulario(
        client, fluxo, [(codigo, quantidade)], destino="ETA II", solicitante="Ana"
    ).text


# --- a linha de estoque ------------------------------------------------------------------------


@pytest.mark.parametrize("fluxo", FORMULARIOS)
@pytest.mark.parametrize(
    ("saldo", "esperado"),
    [
        ("2.4996", "Estoque 2,499 · M"),
        ("2.5", "Estoque 2,5 · M"),
        ("10.000", "Estoque 10 · M"),  # nunca "10,000"
        ("0.0004", "Estoque 0 · M"),
    ],
)
def test_unidade_de_medida_mostra_o_saldo_truncado_a_3_casas(client, fluxo, saldo, esperado):
    codigo, busca = MEDIDA[fluxo]
    definir(codigo, saldo, "M")
    assert esperado in linha_da_lista(client, fluxo, codigo, busca)


@pytest.mark.parametrize("fluxo", FORMULARIOS)
@pytest.mark.parametrize(
    ("saldo", "esperado"),
    [("2.5", "Estoque 2 · UN"), ("2.9999", "Estoque 2 · UN"), ("10.000", "Estoque 10 · UN")],
)
def test_unidade_contada_mostra_a_parte_inteira(client, fluxo, saldo, esperado):
    codigo, busca = CONTADO[fluxo]
    definir(codigo, saldo, "UN")
    assert esperado in linha_da_lista(client, fluxo, codigo, busca)


@pytest.mark.parametrize("fluxo", FORMULARIOS)
@pytest.mark.parametrize(("tipo", "saldo"), [("medida", "0.0004"), ("contado", "0.5")])
def test_maximo_zero_fica_sem_estoque_e_bloqueado(client, fluxo, tipo, saldo):
    codigo, busca = (MEDIDA if tipo == "medida" else CONTADO)[fluxo]
    definir(codigo, saldo, "M" if tipo == "medida" else "UN")
    linha = linha_da_lista(client, fluxo, codigo, busca)
    assert "Sem estoque" in linha
    html = adicionar(client, fluxo, codigo, "1")
    assert not entra(html, codigo)
    assert "Sem estoque — não pode ser adicionado." in html


@pytest.mark.parametrize("fluxo", FORMULARIOS)
def test_material_sem_unidade_mostra_so_o_numero(client, fluxo):
    codigo, busca = CONTADO[fluxo]
    definir(codigo, "7", "")
    linha = linha_da_lista(client, fluxo, codigo, busca)
    assert re.search(r"Estoque 7(?! ·)", linha)


@pytest.mark.parametrize("fluxo", FORMULARIOS)
def test_a_frase_n_un_disponiveis_nao_existe_mais(client, fluxo):
    codigo, busca = CONTADO[fluxo]
    definir(codigo, "10", "UN")
    html = client.get(reverse("pedidos:materiais", args=[fluxo]), {"q": busca}).text
    assert "disponíveis" not in html
    assert re.search(r"Estoque 10 · UN", " ".join(strip_tags(html).split()))


# --- o mesmo número na lista, no limite e na mensagem ------------------------------------------


@pytest.mark.parametrize("fluxo", FORMULARIOS)
def test_unidade_de_medida_limite_e_mensagem_sao_o_numero_da_lista(client, fluxo):
    codigo, busca = MEDIDA[fluxo]
    definir(codigo, "2.4996", "M")
    assert "Estoque 2,499 · M" in linha_da_lista(client, fluxo, codigo, busca)
    texto = "Quantidade acima do estoque. Estoque disponível: 2,499 M."
    # Adicionar: o máximo entra; o máximo mais um, não.
    assert entra(adicionar(client, fluxo, codigo, "2,499"), codigo)
    html = adicionar(client, fluxo, codigo, "2,5")
    assert texto in html and not entra(html, codigo)
    # Alterar: a linha volta à última quantidade válida.
    alterar = client.post(
        reverse("pedidos:carrinho", args=[fluxo]),
        {"item_codigo": [codigo], "item_qtd": ["2,5"], "alterar": codigo, "anterior": "1"},
    ).text
    assert texto in alterar and 'name="item_qtd" value="1"' in alterar
    # Enviar: o mesmo texto, depois do nome do material.
    assert texto in enviar(client, fluxo, codigo, "2,5")
    assert not Pedido.objects.exists()
    assert "Pedido registrado" in enviar(client, fluxo, codigo, "2,499")
    assert Pedido.objects.get().itens.get().qtd_pedida == Decimal("2.499")


@pytest.mark.parametrize("fluxo", FORMULARIOS)
def test_unidade_contada_limite_e_mensagem_sao_a_parte_inteira(client, fluxo):
    codigo, busca = CONTADO[fluxo]
    definir(codigo, "2.5", "UN")
    assert "Estoque 2 · UN" in linha_da_lista(client, fluxo, codigo, busca)
    texto = "Quantidade acima do estoque. Estoque disponível: 2 UN."
    assert entra(adicionar(client, fluxo, codigo, "2"), codigo)
    html = adicionar(client, fluxo, codigo, "3")
    assert texto in html and not entra(html, codigo)
    assert texto in enviar(client, fluxo, codigo, "3")
    assert "Pedido registrado" in enviar(client, fluxo, codigo, "2")


@pytest.mark.parametrize("fluxo", FORMULARIOS)
def test_material_sem_unidade_diz_estoque_disponivel_sem_unidade(client, fluxo):
    codigo, _ = CONTADO[fluxo]
    definir(codigo, "2", "")
    html = adicionar(client, fluxo, codigo, "3")
    assert "Quantidade acima do estoque. Estoque disponível: 2." in html


# --- a saída avulsa mostra o mesmo número do seu teto ------------------------------------------


@pytest.fixture
def logado(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="12345", password="x"))


def test_avulsa_mostra_o_saldo_truncado_e_mantem_codigo_e_unidade(client, logado):
    definir("016.005.010", "2.4996", "UN")
    html = client.get(reverse("pedidos:avulsa_materiais"), {"q": "fita"}).text
    inicio = html.index('data-codigo="016.005.010"')
    linha = " ".join(strip_tags(html[inicio : html.index("</li>", inicio)]).split())
    assert "016.005.010 · Estoque 2,499 · UN" in linha
    # A equipe aceita fração em qualquer unidade, até o saldo truncado.
    url = reverse("pedidos:avulsa_carrinho")
    assert entra(
        client.post(url, {"adicionar": "016.005.010", "qtd-016.005.010": "2,499"}).text,
        "016.005.010",
    )
    recusa = client.post(url, {"adicionar": "016.005.010", "qtd-016.005.010": "2,5"}).text
    assert "Estoque disponível: 2,499 UN." in recusa
