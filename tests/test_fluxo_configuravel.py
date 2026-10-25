"""Um formulário novo é só configuração: catálogo, textos e origem (spec 005, US8, SC-007).

O formulário de teste abaixo é registrado em `FLUXOS` sem mexer em busca, carrinho, validação,
gravação, proteções, recibo nem painel. Os formulários futuros (reposição de peças das viaturas e
autopeças da oficina) seguem o mesmo caminho.
"""

import re
import time
from dataclasses import replace
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalogo.catalogos import ItemCatalogo
from pedidos import fluxos
from pedidos.fluxos import Fluxo
from pedidos.models import Pedido
from pedidos.protecao import emitir
from pedidos.regras import REGRA_LIVRE
from pedidos.servicos import MENSAGEM_LIMITE_SOLICITANTE, catalogo_de
from tests.cenario import montar_cenario

pytestmark = pytest.mark.django_db

ORIGEM = "REPOSICAO_TESTE"
TITULO = "Reposição de peças das viaturas"
PARAFUSO = "T-001"
CABO = "T-002"
PORCA = "T-003"  # contada (UN), com saldo fracionado


def catalogo_do_formulario_novo():
    return [
        ItemCatalogo(
            codigo=PARAFUSO,
            nome="PARAFUSO DE TESTE",
            unidade="UN",
            categoria="",
            grupo="PEÇAS",
            subgrupo="FIXAÇÃO",
            estoque=Decimal("10"),
            disponivel=10,
            duplicado=False,
            fracionavel=False,
        ),
        ItemCatalogo(
            codigo=CABO,
            nome="CABO DE TESTE",
            unidade="M",
            categoria="",
            grupo="PEÇAS",
            subgrupo="ELÉTRICA",
            estoque=Decimal("5.5"),
            disponivel=5,
            duplicado=False,
            fracionavel=True,
        ),
        ItemCatalogo(
            codigo=PORCA,
            nome="PORCA DE TESTE",
            unidade="UN",
            categoria="",
            grupo="PEÇAS",
            subgrupo="FIXAÇÃO",
            estoque=Decimal("2.5"),
            disponivel=2,
            duplicado=False,
            fracionavel=False,
        ),
    ]


@pytest.fixture
def novo(monkeypatch):
    montar_cenario()
    formulario = Fluxo(
        nome="reposicao",
        origem=ORIGEM,
        titulo=TITULO,
        catalogo=catalogo_do_formulario_novo,
        exemplo_busca="Ex.: parafuso, cabo",
        exemplo_inicio="Ex.: parafuso, cabo, fusível",
        icone="caixa",
    )
    monkeypatch.setitem(fluxos.FLUXOS, "reposicao", formulario)
    return formulario


def enviar(client, itens, solicitante="Ana"):
    return client.post(
        reverse("pedidos:formulario", args=["reposicao"]),
        {
            "token": emitir(aberto_em=time.time() - 60).token,
            "solicitante": solicitante,
            "destino": "ETA II",
            "obs": "",
            "confirmacao_extra": "",
            "item_codigo": [c for c, _ in itens],
            "item_qtd": [q for _, q in itens],
        },
        HTTP_HX_REQUEST="true",
    )


def test_o_formulario_novo_abre_com_os_seus_textos_e_o_seu_catalogo(client, novo):
    html = client.get(reverse("pedidos:formulario", args=["reposicao"])).text
    assert f"<h1>{TITULO}</h1>" in html
    assert 'placeholder="Ex.: parafuso, cabo"' in html
    assert 'name="token"' in html and "PARAFUSO DE TESTE" in html and "CABO DE TESTE" in html
    # A linha de estoque é a mesma dos outros formulários.
    assert "Estoque 10 · UN" in " ".join(html.split()) or "Estoque 10" in html


def test_busca_carrinho_e_regra_de_quantidade_valem_para_o_formulario_novo(client, novo):
    busca = client.get(reverse("pedidos:materiais", args=["reposicao"]), {"q": "cabo"}).text
    assert "CABO DE TESTE" in busca and "PARAFUSO DE TESTE" not in busca
    url = reverse("pedidos:carrinho", args=["reposicao"])
    ok = client.post(url, {"adicionar": CABO, f"qtd-{CABO}": "2,5"}).text
    assert f'name="item_codigo" value="{CABO}"' in ok
    recusa = client.post(url, {"adicionar": PARAFUSO, f"qtd-{PARAFUSO}": "1,5"}).text
    assert "Este material só é pedido em quantidade inteira (unidade: UN)." in recusa
    acima = client.post(url, {"adicionar": CABO, f"qtd-{CABO}": "5,6"}).text
    assert "Quantidade acima do estoque. Estoque disponível: 5,5 M." in acima


def test_o_pedido_do_formulario_novo_e_gravado_e_aparece_no_painel_e_no_recibo(client, novo):
    r = enviar(client, [(PARAFUSO, "2"), (CABO, "2,5")])
    assert "Pedido registrado" in r.text
    pedido = Pedido.objects.get()
    assert pedido.origem == ORIGEM and pedido.numero.startswith("P-")
    assert [str(i.qtd_pedida) for i in pedido.itens.all()] == ["2.000", "2.500"]

    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    assert pedido.numero in client.get(reverse("pedidos:painel")).text
    detalhe = client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
    assert detalhe.status_code == 200 and "PARAFUSO DE TESTE" in detalhe.text


def test_o_limite_por_nome_inclui_o_formulario_novo(client, novo, settings):
    settings.PEDIDOS_LIMITE_IP_10_MIN = 100
    settings.PEDIDOS_LIMITE_IP_DIA = 100
    settings.PEDIDOS_LIMITE_SOLICITANTE_DIA = 1
    assert "Pedido registrado" in enviar(client, [(PARAFUSO, "1")], solicitante="Bia").text
    assert MENSAGEM_LIMITE_SOLICITANTE in enviar(client, [(PARAFUSO, "1")], solicitante="Bia").text
    assert Pedido.objects.count() == 1


def test_formulario_novo_com_catalogo_indisponivel_bloqueia(client, novo, monkeypatch):
    monkeypatch.setitem(fluxos.FLUXOS, "reposicao", _com_catalogo(novo, lambda: None))
    assert catalogo_de(ORIGEM) is None
    html = client.get(reverse("pedidos:formulario", args=["reposicao"])).text
    assert "Este formulário está indisponível no momento. Avise o almoxarifado." in html
    assert 'name="token"' not in html


def _com_catalogo(formulario, catalogo):
    from dataclasses import replace

    return replace(formulario, catalogo=catalogo)


def test_a_pagina_inicial_lista_os_formularios_publicos_a_partir_de_fluxos(client, novo):
    html = client.get(reverse("pedidos:inicio")).text
    # Os cinco formulários públicos de `FLUXOS` (limpeza, AB, viaturas, oficina, EPIs) e o de teste.
    assert html.count('class="cartao cartao-opcao"') == 6
    assert TITULO in html and "Ex.: parafuso, cabo, fusível" in html
    assert reverse("pedidos:formulario", args=["reposicao"]) in html
    # Os formulários de sempre continuam lá, e a saída avulsa nunca é pública.
    assert "Limpeza, copa e escritório" in html and "Ferramentas, peças e materiais" in html
    assert reverse("pedidos:formulario", args=["viaturas"]) in html
    assert re.search(r"Sa[ií]da avulsa", html) is None


def test_nome_desconhecido_e_formulario_interno_continuam_dando_404(client, novo):
    assert client.get(reverse("pedidos:formulario", args=["avulsa"])).status_code == 404
    assert client.get(reverse("pedidos:formulario", args=["xyz"])).status_code == 404


# --- a regra de quantidade do Fluxo vale no carrinho e no envio ---------------------------------


@pytest.mark.parametrize(
    ("regra", "aceita_fracao", "maximo"),
    [("por_unidade", False, "2"), (REGRA_LIVRE, True, "2,5")],
    ids=["por_unidade", "livre"],
)
def test_a_regra_do_fluxo_vale_no_carrinho_e_no_envio(
    client, novo, monkeypatch, regra, aceita_fracao, maximo
):
    """O carrinho e a validação do envio leem o mesmo `Fluxo.regra_quantidade`: um formulário
    público com a regra `livre` aceita fração em unidade contada nos dois, e o teto é o saldo
    truncado a 3 casas (não a parte inteira)."""
    monkeypatch.setitem(fluxos.FLUXOS, "reposicao", replace(novo, regra_quantidade=regra))
    url = reverse("pedidos:carrinho", args=["reposicao"])
    recusa = "Este material só é pedido em quantidade inteira (unidade: UN)."

    no_carrinho = client.post(url, {"adicionar": PORCA, f"qtd-{PORCA}": "1,5"}).text
    assert (f'name="item_codigo" value="{PORCA}"' in no_carrinho) is aceita_fracao
    assert (recusa not in no_carrinho) is aceita_fracao

    acima = client.post(url, {"adicionar": PORCA, f"qtd-{PORCA}": "3"}).text
    assert f"Estoque disponível: {maximo} UN." in acima

    envio = enviar(client, [(PORCA, "1,5")])
    assert ("Pedido registrado" in envio.text) is aceita_fracao
    assert (recusa not in envio.text) is aceita_fracao
    assert Pedido.objects.count() == int(aceita_fracao)
    if aceita_fracao:
        assert Pedido.objects.get().itens.get().qtd_pedida == Decimal("1.5")
        assert f"Estoque disponível: {maximo} UN." in enviar(client, [(PORCA, "3")], "Bia").text


def test_folha_e_ocorrencia_sao_opcionais_e_desligadas_nos_fluxos_antigos():
    """Os campos da spec 006 têm padrão neutro: limpeza, AB e saída avulsa não ganham folha e não
    pedem o número da ocorrência."""
    for nome in ("limpeza", "ab", "avulsa"):
        fluxo = fluxos.FLUXOS[nome]
        assert fluxo.folha is None and not fluxo.pede_ocorrencia


def test_os_destinos_dos_formularios_publicos_vem_da_configuracao_e_os_da_avulsa_nao():
    """Spec 009: cada formulário público lê os destinos da configuração (`centros`); a saída
    avulsa, que não faz parte dela, segue com todos os centros (`None`)."""
    assert fluxos.FLUXOS["avulsa"].centros is None
    for fluxo in fluxos.fluxos_publicos():
        assert callable(fluxo.centros)
        assert fluxo.centros.func.__name__ == "centros_do_formulario"
        assert fluxo.centros.args == (fluxo.origem,)


def test_a_autorizacao_e_so_do_formulario_que_a_exige():
    """`exige_autorizacao` (spec 008) tem padrão falso: os formulários anteriores não mudam."""
    assert Fluxo.__dataclass_fields__["exige_autorizacao"].default is False
    anteriores = [f for f in fluxos.FLUXOS.values() if f.nome != "epis"]
    assert anteriores and not any(f.exige_autorizacao for f in anteriores)
