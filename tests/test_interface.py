"""Testes da interface compartilhada: template tags de `interface_extras`, parciais e o
layout público.

Os testes das tags foram portados de
`tests/test_catalogo_templatetags.py` do WMS-Almoxarifado (commit 7079843), sem o que dependia
do app `catalogo` de lá.
"""

from decimal import Decimal

import pytest
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from interface.templatetags.interface_extras import (
    dinheiro,
    intervalo_paginas,
    percentual,
    quantidade,
    querystring_pagina,
    separador_milhar,
)

_rf = RequestFactory()


# ---------------------------------------------------------------------------
# querystring_pagina (revisão T051, achado P3; contrato reforçado pela
# consolidação de UX, Fase A — `interface/_paginacao.html` compartilhado)
# ---------------------------------------------------------------------------


def test_querystring_pagina_substitui_so_o_proprio_parametro():
    request = _rf.get("/qualquer/", {"pagina": "1"})
    contexto = {"request": request}

    href = querystring_pagina(contexto, "pagina", 3)

    assert "pagina=3" in href
    assert "pagina=1" not in href


def test_querystring_pagina_preserva_parametros_de_outras_secoes_paginadas():
    """Uma página com mais de uma seção paginada (ex. `pagina_excecoes`/
    `pagina_divergencias`/`pagina_alteracoes`) não pode zerar as demais ao
    avançar uma delas."""
    request = _rf.get(
        "/qualquer/",
        {"pagina_excecoes": "1", "pagina_divergencias": "2", "pagina_alteracoes": "4"},
    )
    contexto = {"request": request}

    href = querystring_pagina(contexto, "pagina_excecoes", 3)

    assert "pagina_excecoes=3" in href
    assert "pagina_divergencias=2" in href
    assert "pagina_alteracoes=4" in href


def test_querystring_pagina_preserva_filtros_de_busca():
    request = _rf.get("/qualquer/", {"codigo": "000.000.001", "descricao": "parafuso"})
    contexto = {"request": request}

    href = querystring_pagina(contexto, "pagina", 2)

    assert "codigo=000.000.001" in href
    assert "descricao=parafuso" in href
    assert "pagina=2" in href


# ---------------------------------------------------------------------------
# intervalo_paginas (FR-042b)
# ---------------------------------------------------------------------------


def _pagina(numero_total_itens, por_pagina, numero_pagina):
    paginador = Paginator(range(numero_total_itens), por_pagina)
    return paginador.get_page(numero_pagina)


def test_intervalo_paginas_sem_reticencia_quando_poucas_paginas():
    pagina = _pagina(numero_total_itens=30, por_pagina=10, numero_pagina=1)  # 3 páginas

    itens = intervalo_paginas(pagina)

    assert [item["reticencia"] for item in itens] == [False, False, False]
    assert [item["numero"] for item in itens] == [1, 2, 3]


def test_intervalo_paginas_com_reticencia_quando_muitas_paginas():
    """30 páginas, na 15ª: `on_each_side=2`/`on_ends=1` mantém a 1ª, a 30ª e
    as páginas 13–17 diretamente acessíveis, com reticência preenchendo os
    dois intervalos distantes."""
    pagina = _pagina(numero_total_itens=30, por_pagina=1, numero_pagina=15)

    itens = intervalo_paginas(pagina)

    assert itens[0] == {"numero": 1, "reticencia": False}
    assert itens[-1] == {"numero": 30, "reticencia": False}
    numeros_presentes = [item["numero"] for item in itens if not item["reticencia"]]
    assert numeros_presentes == [1, 13, 14, 15, 16, 17, 30]
    assert sum(1 for item in itens if item["reticencia"]) == 2


def test_intervalo_paginas_item_de_reticencia_nao_tem_numero():
    """O template distingue reticência de página pelo booleano `reticencia`,
    nunca comparando `numero` com a string mágica `"…"` (`Paginator.ELLIPSIS`)."""
    pagina = _pagina(numero_total_itens=30, por_pagina=1, numero_pagina=15)

    itens = intervalo_paginas(pagina)
    reticencias = [item for item in itens if item["reticencia"]]

    assert reticencias, "esperava ao menos uma reticência com 30 páginas"
    assert all(item["numero"] is None for item in reticencias)


def test_intervalo_paginas_on_each_side_1_gera_lista_mais_estreita():
    """Revisão do gate visual (achado P2, 2026-09-22): a lista compacta de
    celular usa `on_each_side=1` — só um vizinho de cada lado da página
    atual — em vez do padrão de 2 (lista larga), para caber numa linha a
    375px."""
    pagina = _pagina(numero_total_itens=30, por_pagina=1, numero_pagina=15)

    itens = intervalo_paginas(pagina, 1)

    numeros_presentes = [item["numero"] for item in itens if not item["reticencia"]]
    assert numeros_presentes == [1, 14, 15, 16, 30]
    assert sum(1 for item in itens if item["reticencia"]) == 2


# ---------------------------------------------------------------------------
# separador_milhar (revisão do gate visual, achado "Mundo real", 2026-09-22)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (3408, "3.408"),  # milhar com ponto
        (69, "69"),  # sem milhar, não altera
        ("abc", "abc"),  # não numérico, devolvido sem alteração
    ],
)
def test_separador_milhar(valor, esperado):
    assert separador_milhar(valor) == esperado


# ---------------------------------------------------------------------------
# quantidade (Fase C, decisão do usuário): formato de EXIBIÇÃO de saldo/
# quantidade/diferença em pt-BR — milhar ".", decimal ",", só as casas
# significativas (até 3, o `decimal_places` dos models). Antes, "32,500" ao
# lado de "27000" lia como 32 mil. O filtro nunca vale para `value` de
# `<input>`/hidden: "1.500" de exibição não é um formato de entrada aceito
# como 1500.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (27000, "27.000"),
        (Decimal("27000.000"), "27.000"),
        (Decimal("32.500"), "32,5"),
        (Decimal("6.000"), "6"),
        (0.125, "0,125"),
        (-1234.5, "-1.234,5"),
        (0, "0"),
        (Decimal("0.000"), "0"),
        (1234567.891, "1.234.567,891"),
        (Decimal("999.999"), "999,999"),
        (Decimal("1000"), "1.000"),
    ],
)
def test_quantidade_formata_em_pt_br_so_com_as_casas_significativas(valor, esperado):
    assert quantidade(valor) == esperado


def test_quantidade_zero_negativo_nao_vira_menos_zero():
    assert quantidade(-0.0) == "0"
    assert quantidade(Decimal("-0.000")) == "0"


def test_quantidade_nao_arredonda_para_menos_de_3_casas():
    """A exibição nunca esconde saldo: 0,001 continua 0,001 (não vira "0")."""
    assert quantidade(Decimal("0.001")) == "0,001"
    assert quantidade(Decimal("-0.001")) == "-0,001"
    assert quantidade(Decimal("12.345")) == "12,345"


def test_quantidade_float_e_lido_pela_representacao_decimal_nao_pelo_binario():
    """`0.1` como float não pode vazar "0,1000000000000000055…"."""
    assert quantidade(0.1) == "0,1"


def test_quantidade_none_e_vazio_viram_string_vazia():
    assert quantidade(None) == ""
    assert quantidade("") == ""


@pytest.mark.parametrize("valor", ["abc", "12,5x", Decimal("NaN"), Decimal("Infinity")])
def test_quantidade_valor_nao_numerico_e_devolvido_como_esta(valor):
    resultado = quantidade(valor)

    assert resultado is valor or resultado == valor


# ---------------------------------------------------------------------------
# Layout público, mensagens e arquivos vendorizados
# ---------------------------------------------------------------------------


def _publico():
    return render_to_string("interface/base_publico.html", {}, request=RequestFactory().get("/"))


def test_layout_publico_carrega_assets_no_head():
    html = _publico()
    head = html.split("</head>")[0]
    for arquivo in ("interface/css/clean.css",):
        assert arquivo in head
    assert 'src="/static/interface/js/shell.js" defer' in head
    assert 'src="/static/interface/js/dropdown.js" defer' in head
    assert 'src="/static/interface/vendor/htmx/htmx-4.0.0.min.js" defer' in head
    assert '"almox-tema"' not in head  # só tema claro


def test_layout_publico_sem_barra_lateral_e_com_um_main():
    html = _publico()
    assert 'class="app-lateral' not in html
    assert html.count("<main") == 1
    assert 'id="main"' in html
    assert "data-theme-toggle" not in html


@pytest.mark.parametrize(
    ("nivel", "classe", "papel"),
    [
        (constants.ERROR, "aviso aviso-erro", "alert"),
        (constants.SUCCESS, "aviso aviso-ok", "status"),
        (constants.WARNING, "aviso aviso-atencao", "status"),
        (constants.INFO, "aviso aviso-info", "status"),
    ],
)
def test_mensagens_por_nivel(nivel, classe, papel):
    html = render_to_string("interface/_mensagens.html", {"messages": [Message(nivel, "Texto")]})
    assert classe in html and f'role="{papel}"' in html and "Texto" in html


def test_dropdown_js_select_digitavel_so_aceita_uma_opcao_da_lista():
    # `data-dropdown-digitavel`: o controle é um campo de texto que filtra a lista, mas o <select>
    # guarda o valor, o texto não escolhido volta ao escolhido ao fechar e o Enter nunca envia o
    # formulário.
    js = open(finders.find("interface/js/dropdown.js"), encoding="utf-8").read()
    assert 'hasAttribute("data-dropdown-digitavel")' in js and "function montarDigitavel" in js
    assert "if (d.digitavel) atualizarGatilho(d);" in js
    # O aria-activedescendant vai para o campo visível, não para o <select> escondido.
    assert 'return d.tipo === "combo" ? d.controle : d.lista;' in js
    assert 'd.digitavel && k === "Enter"' in js


def test_dropdown_js_repetir_a_mesma_letra_percorre_as_opcoes():
    # "aa" conta como uma letra só e anda pelas opções a partir da ativa (como no <select> nativo);
    # letras diferentes buscam o prefixo inteiro.
    js = open(finders.find("interface/js/dropdown.js"), encoding="utf-8").read()
    trecho = js[js.index("function pularPara") :]
    trecho = trecho[: trecho.index("function aoTeclar")]
    assert r"/^(.)\1+$/.test(d.digitado)" in trecho
    assert "d.digitado = d.digitado.charAt(0)" in trecho  # o acumulado volta à letra repetida
    assert "busca.length === 1 ? d.ativo + 1 : 0" in trecho


@pytest.mark.django_db
def test_dropdown_js_existe_e_o_nativo_continua_na_pagina(client):
    from tests.cenario import montar_cenario

    montar_cenario()
    assert finders.find("interface/js/dropdown.js")
    r = client.get(reverse("pedidos:formulario", args=["limpeza"]))
    # O <select> e o <input list> originais seguem no HTML: são eles que guardam o valor.
    assert '<select id="busca-filtro" class="campo-entrada" name="filtro"' in r.text
    assert 'name="destino" maxlength="200" list="destinos"' in r.text


def test_barra_do_topo_nao_estica_em_pagina_curta():
    # Com a barra lateral colapsada o .app tem duas linhas e min-height de 100vh: a sobra precisa
    # ser da linha do conteúdo, senão a barra do topo vira um bloco em branco.
    css = open(finders.find("interface/css/layouts.css"), encoding="utf-8").read()
    bloco = css[css.index("@media (max-width: 1286px)") :]
    assert "grid-template-rows: auto 1fr" in bloco[: bloco.index("}")]


def test_htmx_e_licenca_vendorizados():
    assert finders.find("interface/vendor/htmx/htmx-4.0.0.min.js")
    assert finders.find("interface/vendor/htmx/LICENSE")


@pytest.mark.django_db
def test_respostas_de_erro_nao_substituem_conteudo(client):
    texto = client.get(reverse("login")).text
    assert '<meta name="htmx-config"' in texto and '"5xx"' in texto


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Decimal("0.0394"), "3,94%"),
        (Decimal("0.78"), "78,00%"),
        (Decimal("1"), "100,00%"),
        (Decimal("0.99999"), "100,00%"),
        (Decimal("0.123456"), "12,35%"),
        ("abc", "abc"),
    ],
)
def test_percentual(valor, esperado):
    assert percentual(valor) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Decimal("1988.96038"), "R$ 1.988,96"),
        (Decimal("63424937.62"), "R$ 63.424.937,62"),
        (Decimal("0"), "R$ 0,00"),
        (Decimal("-5.5"), "-R$ 5,50"),
        (None, None),
    ],
)
def test_dinheiro(valor, esperado):
    assert dinheiro(valor) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("AUTO PECAS", "Auto pecas"),
        ("MATERIAL DE SEGURANÇA E EPI", "Material de segurança e EPI"),
        (
            "MATERIAL PARA ESTAÇÕES DE TRATAMENTO (ETA / ETE)",
            "Material para estações de tratamento (ETA / ETE)",
        ),
        ("PNEUS, CÂMARAS E RODAS", "Pneus, câmaras e rodas"),
        ("", ""),
    ],
)
def test_frase_deixa_so_a_primeira_letra_maiuscula(texto, esperado):
    from pedidos.templatetags.pedidos_extras import frase

    assert frase(texto) == esperado
