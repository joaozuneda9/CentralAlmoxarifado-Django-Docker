"""O formulário de reposição de peças das viaturas de ponta a ponta (spec 006, US1 e US2): página
inicial, folha, busca, envio, painel, detalhe, recibo e aviso."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from pedidos.models import Pedido
from pedidos.regras import VIATURAS
from pedidos.telegram import texto_aviso
from tests.config_cenario import enviar_formulario
from tests.paginas import texto
from tests.viaturas_cenario import (
    BOTINA,
    EQUIPE,
    FITA,
    ISOLANTE,
    LUVA,
    TUBO,
    enviar,
    montar_viaturas,
)

pytestmark = pytest.mark.django_db

URL = reverse("pedidos:formulario", args=["viaturas"])
CARRINHO = reverse("pedidos:carrinho", args=["viaturas"])


@pytest.fixture(autouse=True)
def cenario():
    montar_viaturas()


def no_carrinho(html):
    return re.findall(r'name="item_codigo" value="([^"]+)"', html)


def folha(client, carrinho=(), **campos):
    dados = {
        "folha": "1",
        "item_codigo": [c for c, _ in carrinho],
        "item_qtd": [q for _, q in carrinho],
        **{f"folha-{c}": q for c, q in campos.items()},
    }
    return client.post(CARRINHO, dados)


def abrir_folha(client, carrinho=()):
    return client.post(
        CARRINHO,
        {
            "folha_abrir": "1",
            "item_codigo": [c for c, _ in carrinho],
            "item_qtd": [q for _, q in carrinho],
        },
    )


# Página e formulário


def test_a_pagina_inicial_lista_o_formulario(client):
    html = client.get(reverse("pedidos:inicio")).text
    assert "Reposição de peças das viaturas" in html and URL in html


def test_o_formulario_tem_ocorrencia_e_folha_e_os_outros_nao(client):
    html = client.get(URL).text
    assert "Nº da ocorrência" in html and 'name="ocorrencia"' in html and 'maxlength="20"' in html
    assert "Preencher a lista de peças" in html and "4 peças, como na folha de papel" in html
    for nome in ("limpeza", "ab"):
        outro = client.get(reverse("pedidos:formulario", args=[nome])).text
        assert 'name="ocorrencia"' not in outro and "data-folha-abrir" not in outro


def test_o_destino_se_chama_numero_da_viatura_so_neste_formulario(client):
    html = client.get(URL).text
    assert '<label class="campo-rotulo" for="destino">Número da viatura</label>' in html
    assert "Destino dos materiais" not in html
    outro = client.get(reverse("pedidos:formulario", args=["ab"])).text
    assert '<label class="campo-rotulo" for="destino">Destino dos materiais</label>' in outro


# Folha


def test_a_folha_abre_na_ordem_com_nome_exibido_estoque_e_bloqueio(client):
    html = abrir_folha(client, [(FITA, "3")]).text
    nomes = re.findall(r"<strong>([^<]+)</strong>", html)
    assert nomes == [
        "Tubo PVC 3/4 Soldável Marrom (metro)",
        "FITA VEDA ROSCA",
        "BOTINA",
        "LUVA NITRÍLICA",
    ]
    assert "Estoque 12,5 · M" in texto(html) and "Estoque 2 · UN" in texto(html)
    assert f'name="folha-{FITA}" value="3"' in html  # a quantidade que já está no pedido
    assert f'name="folha-{LUVA}"' not in html and "Sem estoque" in html
    assert 'inputmode="decimal"' in html and 'inputmode="numeric"' in html
    assert "data-folha-nova" in html


def test_aplicar_a_folha_devolve_o_carrinho_e_o_evento(client):
    r = folha(client, [(FITA, "1")], **{TUBO: "2,5", FITA: "", BOTINA: "2"})
    assert r["HX-Trigger"] == "folha-aplicada"
    assert no_carrinho(r.text) == [TUBO, BOTINA]


def test_folha_com_erro_volta_ao_dialogo_sem_mudar_o_pedido(client):
    r = folha(client, [(FITA, "1")], **{TUBO: "13", BOTINA: "1,5"})
    assert r["HX-Retarget"] == "#folha-conteudo" and r["HX-Reswap"] == "innerHTML"
    assert "HX-Trigger" not in r
    html = texto(r.text)
    assert "Corrija 2 linhas para pôr no pedido." in html
    assert "Quantidade acima do estoque. Estoque disponível: 12,5 M." in html
    assert "Este material só é pedido em quantidade inteira (unidade: UN)." in html
    assert f'name="folha-{TUBO}" value="13"' in r.text and 'aria-invalid="true"' in r.text


@override_settings(PEDIDOS_MAX_ITENS=2)
def test_folha_que_passa_do_limite_de_materiais(client):
    r = folha(client, [(ISOLANTE, "1")], **{TUBO: "1", BOTINA: "1"})
    assert "O pedido pode ter no máximo 2 materiais." in r.text
    assert r["HX-Retarget"] == "#folha-conteudo"


def test_peca_da_busca_soma_e_a_folha_mostra_a_soma(client):
    r = client.post(
        CARRINHO,
        {"adicionar": FITA, f"qtd-{FITA}": "2", "item_codigo": [FITA], "item_qtd": ["3"]},
    )
    assert 'value="5"' in r.text
    assert f'name="folha-{FITA}" value="5"' in abrir_folha(client, [(FITA, "5")]).text


# Busca (US2)


def test_a_busca_acha_o_ab_e_a_peca_da_lista_uma_vez(client):
    busca = reverse("pedidos:materiais", args=["viaturas"])
    tubo = client.get(busca, {"q": "marrom"}).text
    assert tubo.count(f'data-codigo="{TUBO}"') == 1
    fita = client.get(busca, {"q": "fita"}).text
    assert fita.count(f'data-codigo="{FITA}"') == 1
    assert "DETERGENTE" not in client.get(busca, {"q": "detergente"}).text  # nem lista nem AB
    # Material do AB fora da lista.
    assert f'data-codigo="{ISOLANTE}"' in client.get(busca, {"q": "isolante"}).text


def test_pedido_com_folha_e_busca_registra_tudo(client):
    r = enviar(client, [(TUBO, "2,5"), (FITA, "1"), (ISOLANTE, "1")])
    assert "Pedido registrado" in r.text
    assert {i.codigo for i in Pedido.objects.get().itens.all()} == {TUBO, FITA, ISOLANTE}


# Envio, painel, detalhe e aviso


def test_o_envio_registra_o_pedido_de_viaturas(client):
    r = enviar(client, [(TUBO, "2,5"), (FITA, "2")], ocorrencia="1234/2026")
    assert "Pedido registrado" in r.text
    assert "Nº da ocorrência: 1234/2026" in texto(r.text)  # o encarregado confere o que enviou
    pedido = Pedido.objects.get()
    assert pedido.origem == VIATURAS and pedido.numero.startswith("P-")
    assert pedido.destino == EQUIPE and pedido.ocorrencia == "1234/2026"
    itens = {i.codigo: i.material for i in pedido.itens.all()}
    assert itens[TUBO] == "Tubo PVC 3/4 Soldável Marrom (metro)"  # o nome que o encarregado viu


def test_ocorrencia_longa_e_recusada_no_campo(client):
    r = enviar(client, [(FITA, "1")], ocorrencia="x" * 21)
    assert "Nº da ocorrência: no máximo 20 caracteres." in r.text
    assert 'id="ocorrencia-erro"' in r.text and not Pedido.objects.exists()


def test_painel_detalhe_recibo_e_aviso(client):
    enviar(client, [(FITA, "2")], ocorrencia="1234/2026")
    pedido = Pedido.objects.get()
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    painel = client.get(reverse("pedidos:painel")).text
    assert "Ocorrência 1234/2026" in texto(painel)
    assert pedido.numero in client.get(reverse("pedidos:painel"), {"origem": VIATURAS}).text
    assert pedido.numero in client.get(reverse("pedidos:painel"), {"q": "1234/2026"}).text
    assert pedido.numero not in client.get(reverse("pedidos:painel"), {"origem": "AB"}).text
    detalhe = texto(client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text)
    assert "Nº da ocorrência 1234/2026" in detalhe
    aviso = texto_aviso(pedido)
    assert "Reposição de peças das viaturas" in aviso and "1234" not in aviso


def test_sem_ocorrencia_o_sucesso_e_o_detalhe_nao_mostram_o_campo(client):
    assert "Nº da ocorrência" not in enviar(client, [(FITA, "1")]).text
    pedido = Pedido.objects.get()
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    assert (
        "Nº da ocorrência" not in client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    )


def test_limite_por_nome_soma_viaturas_com_os_outros_formularios(client, settings):
    settings.PEDIDOS_LIMITE_SOLICITANTE_DIA = 1
    settings.PEDIDOS_LIMITE_IP_10_MIN = 99
    settings.PEDIDOS_LIMITE_IP_DIA = 99
    limpeza = enviar_formulario(
        client, "limpeza", [("023.001.002", "1")], destino="ETA II", solicitante="Carlos"
    )
    assert "Pedido registrado" in limpeza.text
    assert "Pedido registrado" not in enviar(client, [(FITA, "1")]).text
    assert Pedido.objects.count() == 1


def test_so_a_lista_sem_estoque_nao_mostra_o_aviso_geral(client):
    from catalogo.models import Material

    Material.objects.filter(codigo__in=[TUBO, FITA, BOTINA]).update(estoque=0)
    html = client.get(URL).text
    assert "Nenhum material deste formulário tem estoque agora." not in html
    assert texto(abrir_folha(client).text).count("Sem estoque") == 4


def test_o_pedidos_js_cuida_da_folha():
    """O diálogo só se confere à mão no navegador (quickstart §4); aqui, os marcadores de que o
    pedidos.js abre, fecha, devolve o foco, não envia o pedido no Enter e anuncia o resultado."""
    from django.contrib.staticfiles import finders

    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    for marcador in (
        "data-folha-nova",
        "showModal",
        '"folha-aplicada"',
        "[data-folha-fechar]",
        "[data-folha-aplicar]",
        ".folha-qtd",
        "botao.focus()",
        "Lista posta no pedido: ",
    ):
        assert marcador in js, marcador
