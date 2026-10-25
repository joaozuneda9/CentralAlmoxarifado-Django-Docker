import re
import time
from urllib.error import URLError

import pytest
from django.urls import reverse

from catalogo.models import CentroCusto
from pedidos import servicos
from pedidos.models import Pedido
from pedidos.protecao import (
    MENSAGEM_RAPIDO,
    MENSAGEM_RECUSA,
    MENSAGEM_TOKEN_INVALIDO,
    emitir,
    ler,
)
from pedidos.servicos import mensagem_divergente
from tests.cenario import montar_cenario

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cenario(monkeypatch):
    montar_cenario()
    monkeypatch.setattr(servicos, "notificar_pedido", lambda pedido, url_painel="": "enviado")


def token():
    return emitir(aberto_em=time.time() - 60).token


def postar(
    client, fluxo, tok, *, solicitante="Ana", destino="ETA II", obs="", itens=(), isca="", htmx=True
):
    dados = {
        "token": tok,
        "solicitante": solicitante,
        "destino": destino,
        "obs": obs,
        "confirmacao_extra": isca,
        "item_codigo": [c for c, _ in itens],
        "item_qtd": [q for _, q in itens],
    }
    extra = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    return client.post(reverse("pedidos:formulario", args=[fluxo]), dados, **extra)


LIMPEZA_ITENS = [("023.001.002", "2"), ("008.001.002", "1,5")]


def test_inicio_mostra_os_dois_formularios(client):
    r = client.get(reverse("pedidos:inicio"))
    assert reverse("pedidos:formulario", args=["limpeza"]) in r.text
    assert reverse("pedidos:formulario", args=["ab"]) in r.text
    assert "Pedir materiais ao almoxarifado" in r.text


def test_formulario_abre_com_token_e_isca_e_sem_barra_lateral(client):
    r = client.get(reverse("pedidos:formulario", args=["limpeza"]))
    assert r.status_code == 200
    assert 'name="token"' in r.text and 'name="confirmacao_extra"' in r.text
    assert 'class="app-lateral' not in r.text
    assert "DETERGENTE NEUTRO" in r.text
    assert 'list="destinos"' in r.text and "ETA II" in r.text


@pytest.mark.parametrize("fluxo", ["limpeza", "ab"])
def test_nome_do_solicitante_nao_sugere_nomes(client, fluxo):
    r = client.get(reverse("pedidos:formulario", args=[fluxo])).text
    campo = re.search(r'<input id="solicitante"[^>]*>', r).group(0)
    assert " list=" not in campo and 'autocomplete="off"' in campo
    assert 'id="funcionarios"' not in r and "Ana Exemplo" not in r
    # A dica dos dados guardados fica logo abaixo do título do passo, e o campo a descreve.
    assert (
        '<h2>Seus dados</h2><p id="solicitante-dica" class="texto-secundario">'
        "Ficam guardados no seu aparelho para o próximo pedido.</p>"
    ) in r
    assert 'aria-describedby="solicitante-dica' in campo


@pytest.mark.parametrize(
    ("fluxo", "itens"),
    [("limpeza", LIMPEZA_ITENS), ("ab", [("016.005.010", "1")])],
)
def test_nome_fora_da_lista_continua_valendo(client, fluxo, itens):
    r = postar(client, fluxo, token(), solicitante="Fulano Fora Da Lista", itens=itens)
    assert r.status_code == 200
    assert Pedido.objects.get().solicitante == "Fulano Fora Da Lista"


def test_fluxo_desconhecido_ou_interno_da_404(client):
    assert client.get(reverse("pedidos:formulario", args=["avulsa"])).status_code == 404
    assert client.get(reverse("pedidos:formulario", args=["xyz"])).status_code == 404


def test_ab_indisponivel_sem_saldo(client):
    montar_cenario(com_estoque=False)
    r = client.get(reverse("pedidos:formulario", args=["ab"]))
    assert "Este formulário está indisponível no momento. Avise o almoxarifado." in r.text
    assert "estoque ou catálogo" not in r.text  # a mesma mensagem da limpeza
    assert 'name="token"' not in r.text


def test_envio_valido_mostra_o_numero(client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        r = postar(client, "limpeza", token(), itens=LIMPEZA_ITENS)
    assert r.status_code == 200 and "<html" not in r.text
    assert "Pedido registrado" in r.text and "P-000001" in r.text
    assert "2 materiais registrados para Ana." in r.text
    assert Pedido.objects.get().ip == "127.0.0.1"


def test_reenvio_mostra_ja_registrado(client, django_capture_on_commit_callbacks):
    t = token()
    with django_capture_on_commit_callbacks(execute=True):
        postar(client, "limpeza", t, itens=LIMPEZA_ITENS)
        r = postar(client, "limpeza", t, itens=LIMPEZA_ITENS)
    assert "Pedido já estava registrado" in r.text
    assert "Reenvio confirmado: nenhum aviso novo foi enviado." in r.text
    assert Pedido.objects.count() == 1


def test_divergente_troca_o_identificador_e_o_novo_envio_grava(client):
    t = token()
    postar(client, "limpeza", t, itens=LIMPEZA_ITENS)
    r = postar(client, "limpeza", t, destino="ETA I", itens=LIMPEZA_ITENS)
    assert mensagem_divergente("P-000001") in r.text
    assert "Já conferi com o almoxarifado — enviar como novo pedido" in r.text
    novo = re.search(r'name="token" value="([^"]+)"', r.text).group(1)
    assert ler(novo).id != ler(t).id
    assert "P-000002" in postar(client, "limpeza", novo, destino="ETA I", itens=LIMPEZA_ITENS).text


def test_isca_recusa_com_a_mensagem_generica(client):
    r = postar(client, "limpeza", token(), itens=LIMPEZA_ITENS, isca="http://spam")
    assert MENSAGEM_RECUSA in r.text and MENSAGEM_RAPIDO not in r.text
    assert not Pedido.objects.exists()


def test_envio_rapido_demais_diz_para_esperar_e_mantem_os_dados(client):
    rapido = emitir().token
    r = postar(client, "limpeza", rapido, solicitante="Ana Paula", itens=LIMPEZA_ITENS)
    assert MENSAGEM_RAPIDO == "Aguarde alguns segundos e toque em Enviar de novo."
    assert MENSAGEM_RAPIDO in r.text and MENSAGEM_RECUSA not in r.text
    assert 'value="Ana Paula"' in r.text
    assert 'name="item_codigo" value="023.001.002"' in r.text
    assert "expirou" not in r.text
    assert not Pedido.objects.exists()


def test_token_invalido_mantem_os_dados_e_o_envio_seguinte_entra(client, settings):
    r = postar(client, "limpeza", "adulterado", solicitante="Ana Paula", itens=LIMPEZA_ITENS)
    assert MENSAGEM_TOKEN_INVALIDO == (
        "Houve um problema ao confirmar o formulário. Seus dados foram mantidos: "
        "toque em Enviar de novo."
    )
    assert MENSAGEM_TOKEN_INVALIDO in r.text and "expirou" not in r.text
    assert 'value="Ana Paula"' in r.text
    assert 'name="item_codigo" value="023.001.002"' in r.text
    novo = re.search(r'name="token" value="([^"]+)"', r.text).group(1)
    assert ler(novo) is not None
    assert not Pedido.objects.exists()
    # Reenviar logo depois cai no tempo mínimo (o ingresso novo nasce agora)...
    assert MENSAGEM_RAPIDO in postar(client, "limpeza", novo, itens=LIMPEZA_ITENS).text
    # ...e, passado o prazo, o pedido é aceito.
    settings.PEDIDOS_TEMPO_MINIMO = 0
    assert "Pedido registrado" in postar(client, "limpeza", novo, itens=LIMPEZA_ITENS).text


def test_erros_mantem_o_preenchido_e_marcam_o_item(client):
    r = postar(
        client,
        "ab",
        token(),
        solicitante="Bruno",
        destino="Elevatória",
        itens=[("016.005.010", "3"), ("013.006.001", "3")],
    )
    assert "BOTINA (013.006.001): Quantidade acima do estoque. Estoque disponível: 2 UN." in r.text
    assert 'value="Bruno"' in r.text and 'value="Elevatória"' in r.text
    assert 'name="item_codigo" value="013.006.001"' in r.text
    assert "Corrigir" in r.text
    assert not Pedido.objects.exists()


def test_destino_fora_dos_centros_de_custo_e_recusado(client):
    r = postar(client, "limpeza", token(), destino="Portaria", itens=LIMPEZA_ITENS)
    assert "Destino &quot;Portaria&quot; não está na lista de centros de custo." in r.text
    assert 'value="Portaria"' in r.text
    assert not Pedido.objects.exists()


def test_destino_digitado_e_gravado_como_esta_no_cadastro(client):
    postar(client, "limpeza", token(), destino="eta  ii", itens=LIMPEZA_ITENS)
    postar(client, "limpeza", token(), destino="pickup 01 — abc1d23", itens=LIMPEZA_ITENS)
    postar(client, "limpeza", token(), destino="abc-1d23", itens=LIMPEZA_ITENS)
    assert list(Pedido.objects.order_by("numero").values_list("destino", flat=True)) == [
        "ETA II",
        "PICKUP 01 — ABC1D23",
        "PICKUP 01 — ABC1D23",
    ]


def test_destino_fica_junto_do_nome_com_a_orientacao(client):
    for fluxo in ("limpeza", "ab"):
        r = client.get(reverse("pedidos:formulario", args=[fluxo]))
        passo1 = r.text[r.text.index("<h2>Seus dados</h2>") : r.text.index("<h2>Materiais</h2>")]
        assert 'name="solicitante"' in passo1 and 'name="destino"' in passo1
        assert 'list="destinos"' in passo1
        assert "O que pôr aqui?" not in passo1 and "<details" not in passo1
        # A orientação é a dica dentro do próprio campo (placeholder), sem parágrafo embaixo.
        campo = re.search(r'<input id="destino"[^>]*>', passo1).group(0)
        assert 'placeholder="Posto de trabalho, placa do veículo ou setor"' in campo
        assert "destino-dica" not in passo1
        assert 'name="destino"' not in r.text[r.text.index('<h2 id="obs-titulo">') :]
        for opcao in ("ETA I", "ETA II", "PICKUP 01 — ABC1D23"):
            assert f'<option value="{opcao}">' in r.text


def test_formulario_indisponivel_sem_centros_de_custo(client):
    CentroCusto.objects.all().delete()
    r = client.get(reverse("pedidos:formulario", args=["limpeza"]))
    assert "Este formulário está indisponível no momento. Avise o almoxarifado." in r.text
    assert 'name="token"' not in r.text


@pytest.mark.django_db(transaction=True)
def test_aviso_do_telegram_que_falhou_aparece(client, settings, monkeypatch):
    # Com transação de verdade, o on_commit roda antes da resposta, como no servidor.
    monkeypatch.undo()
    settings.TELEGRAM_TOKEN, settings.TELEGRAM_CHAT_ID = "t", "c"

    def falha(req, timeout):
        raise URLError("sem rede")

    monkeypatch.setattr("pedidos.telegram.urlopen", falha)
    r = postar(client, "limpeza", token(), itens=LIMPEZA_ITENS)
    assert "O aviso ao almoxarifado pelo Telegram falhou, mas o pedido está gravado." in r.text


def test_sem_htmx_devolve_a_pagina_inteira(client):
    r = postar(client, "limpeza", token(), itens=LIMPEZA_ITENS, htmx=False)
    assert "<html" in r.text and "P-000001" in r.text


def test_inicio_no_estilo_clean(client):
    r = client.get(reverse("pedidos:inicio"))
    # Limpeza, AB, reposição de peças das viaturas (spec 006), oficina mecânica (spec 007) e EPIs
    # (spec 008).
    assert r.text.count('class="cartao cartao-opcao"') == 5
    assert '<p class="rotulo-secao">Almoxarifado SAEP</p>' in r.text


def test_filtro_por_grupo_e_subgrupo_igual_nos_dois_formularios(client):

    seletores = []

    for fluxo in ("limpeza", "ab"):
        r = client.get(reverse("pedidos:formulario", args=[fluxo]))

        seletor = r.text[r.text.index('id="busca-filtro"') : r.text.index("</select>")]

        assert "Grupo e subgrupo" in r.text and "Categoria" not in r.text

        assert "Todos os grupos" in seletor and "Todas as categorias" not in seletor

        assert "data-busca-filtro-limpar" in r.text  # "Limpar" ao lado do resumo do filtro

        seletores.append(seletor)

    assert '<option value="">Todos os grupos</option>' in seletores[0]

    # Os nomes aparecem só com a primeira letra maiúscula; os valores seguem como no cadastro.
    assert '<optgroup label="Limpeza">' in seletores[0]

    assert '<option value="LIMPEZA › SUB">Limpeza › Sub</option>' in seletores[0]

    assert '<optgroup label="Redes de água">' in seletores[1]

    assert all("data-dropdown-arvore" in s for s in seletores)


def test_grupo_com_um_subgrupo_de_mesmo_nome_fica_sem_filhos(client, monkeypatch):
    from pedidos.views import publico

    monkeypatch.setattr(
        publico,
        "opcoes_filtro",
        lambda fluxo, catalogo: [("HIDRAULICO", ["HIDRAULICO"]), ("COPA", ["BEBIDAS"])],
    )
    r = client.get(reverse("pedidos:formulario", args=["ab"]))
    seletor = r.text[r.text.index('id="busca-filtro"') : r.text.index("</select>")]
    assert '<option value="HIDRAULICO">Todo o grupo Hidraulico</option>' in seletor
    assert "HIDRAULICO › HIDRAULICO" not in seletor
    assert '<option value="COPA › BEBIDAS">Copa › Bebidas</option>' in seletor


def test_exemplo_da_busca_combina_com_o_formulario(client):
    limpeza = client.get(reverse("pedidos:formulario", args=["limpeza"]))
    ab = client.get(reverse("pedidos:formulario", args=["ab"]))
    assert 'placeholder="Ex.: detergente, café"' in limpeza.text
    assert 'placeholder="Ex.: luva, fita veda rosca"' in ab.text


def test_formulario_em_tres_passos(client):
    r = client.get(reverse("pedidos:formulario", args=["limpeza"]))
    for numero, titulo in (
        ("01", "Seus dados"),
        ("02", "Materiais"),
        ("03", 'Observações <span class="texto-secundario">(opcional)</span>'),
    ):
        assert f'<span class="passo-numero" aria-hidden="true">{numero}</span>' in r.text
        assert re.search(rf"<h2[^>]*>{re.escape(titulo)}</h2>", r.text)
    assert '<label class="campo-rotulo" for="obs">' not in r.text  # o título já diz o que é
    assert 'name="obs"' in r.text and 'aria-labelledby="obs-titulo"' in r.text
    assert 'class="campo-busca"' in r.text and 'class="lista-materiais"' in r.text
    assert 'data-quantidade="mais"' in r.text and 'data-quantidade="menos"' in r.text
    # O único <details> é o filtro de grupo, recolhido acima da busca.
    assert r.text.count("<details") == 1 and '<details class="busca-filtro"' in r.text
    assert r.text.index('<details class="busca-filtro"') < r.text.index('id="busca-q"')
    assert r.text.index("data-erro-envio") < r.text.index('class="passo"')


def test_sucesso_no_estilo_clean(client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        r = postar(client, "limpeza", token(), itens=LIMPEZA_ITENS)
    assert 'class="cartao sucesso-pedido"' in r.text
    assert '<p class="sucesso-numero mono">P-000001</p>' in r.text


def test_resposta_do_envio_leva_ao_topo_do_formulario(client):
    # Os erros ficam no topo: a troca do HTMX rola até lá, senão quem enviou lá de baixo não vê.
    r = client.get(reverse("pedidos:formulario", args=["limpeza"]))
    assert 'hx-target="#formulario" hx-swap="innerHTML show:top"' in r.text


def test_barra_do_pedido_avisa_o_que_corrigir(client):
    r = postar(
        client,
        "ab",
        token(),
        solicitante="Bruno",
        destino="Elevatória",
        itens=[("016.005.010", "3"), ("013.006.001", "3")],
    )
    barra = r.text[r.text.index('class="carrinho-barra"') : r.text.index("<dialog")]
    assert '<span class="selo selo-erro">Corrigir</span>' in barra


def test_resultados_em_painel_preso_a_busca(client):
    r = client.get(reverse("pedidos:formulario", args=["ab"]))
    area = r.text[r.text.index('<div class="busca-area" data-busca-area>') :]
    busca = area[: area.index('id="resultados"')]
    assert 'aria-expanded="false" aria-controls="resultados"' in busca
    assert '<div class="campo busca-principal">' in busca
    assert '<div id="resultados" class="painel-flutuante busca-painel" aria-live="polite">' in area
    assert 'class="lista-materiais"' in area


def test_pedido_em_secao_propria_ao_lado_dos_passos_no_desktop(client):
    from django.contrib.staticfiles import finders

    r = client.get(reverse("pedidos:formulario", args=["limpeza"]))
    assert '<body class="ritmo-publico pagina-larga">' in r.text
    html = r.text
    # Os três passos ficam numa coluna e o "Seu pedido" numa seção própria ao lado deles.
    assert html.index('class="pedido-passos') < html.index('<aside class="pedido-lado"')
    passos = html[html.index('class="pedido-passos') : html.index('<aside class="pedido-lado"')]
    assert passos.count('class="passo"') == 3 and 'id="carrinho"' not in passos
    lado = html[html.index('<aside class="pedido-lado"') : html.index("</aside>")]
    # O carrinho e o botão de envio ficam dentro do cartão do pedido.
    assert 'id="carrinho"' in lado and 'class="pedido-enviar"' in lado
    assert 'type="submit"' in lado and "Enviar pedido" in lado
    # E a gaveta (celular/tablet) usa o botão do fim do formulário.
    assert html.index("</aside>") < html.index('class="acoes acoes-final"')
    layouts = open(finders.find("interface/css/layouts.css"), encoding="utf-8").read()
    assert ".pagina-larga .publico-conteudo" in layouts and "1080px" in layouts
    pedidos = open(finders.find("pedidos/css/pedidos.css"), encoding="utf-8").read()
    regra = pedidos[pedidos.index("@container (min-width: 960px)") :]
    assert "minmax(0, 1fr) 340px" in regra and "position: sticky" in regra
    assert "html:not([data-gaveta]) .acoes-final { display: none; }" in pedidos
    assert ".js[data-gaveta] .pedido-enviar { display: none; }" in pedidos


def test_envio_recusado_agrupa_os_erros_por_campo(client):
    r = postar(client, "limpeza", token(), solicitante="", destino="", itens=LIMPEZA_ITENS)
    assert r.context["erros_por_campo"] == {
        "solicitante": ["Informe o nome completo."],
        "destino": ["Escolha o destino dos materiais na lista de centros de custo."],
    }
    assert client.get(reverse("pedidos:formulario", args=["ab"])).context["erros_por_campo"] == {}


def _resumo(html):
    inicio = html.index("data-resumo-erros")
    return html[html.rindex("<div", 0, inicio) : html.index("</div></div>", inicio)]


def test_envio_recusado_mostra_resumo_com_links_e_o_erro_em_cada_campo(client):
    r = postar(client, "limpeza", token(), solicitante="", destino="", itens=LIMPEZA_ITENS).text
    resumo = _resumo(r)
    assert 'role="alert"' in resumo and 'tabindex="-1"' in resumo
    assert "Faltam 2 coisas para enviar" in resumo
    assert "Corrija os itens abaixo e envie de novo." in resumo
    assert '<a href="#solicitante">Informe o nome completo.</a>' in resumo
    assert (
        '<a href="#destino">Escolha o destino dos materiais na lista de centros de custo.</a>'
        in resumo
    )
    for nome, texto in (
        ("solicitante", "Informe o nome completo."),
        ("destino", "Escolha o destino dos materiais na lista de centros de custo."),
    ):
        campo = re.search(rf'<input id="{nome}"[^>]*>', r).group(0)
        assert 'aria-invalid="true"' in campo and f"{nome}-erro" in campo
        erro = r[r.index(f'<p id="{nome}-erro" class="campo-erro">') :]
        erro = erro[: erro.index("</p>")]
        assert texto in erro and "<svg" in erro
        bloco = r[: r.index(f'<input id="{nome}"')]
        assert "campo-com-erro" in bloco[bloco.rindex('<div class="campo') :]


def test_um_erro_so_e_erro_de_material_ficam_no_resumo(client):
    r = postar(client, "limpeza", token(), solicitante="", itens=LIMPEZA_ITENS).text
    assert "Falta 1 coisa para enviar" in _resumo(r)
    r = postar(client, "ab", token(), itens=[("013.006.001", "3")]).text
    resumo = _resumo(r)
    assert "Falta 1 coisa para enviar" in resumo
    assert (
        "<li>BOTINA (013.006.001): Quantidade acima do estoque. Estoque disponível: 2 UN.</li>"
        in resumo
    )
    assert 'aria-invalid="true"' not in r and "Corrigir" in r


def test_campos_sem_erro_nao_ficam_marcados(client):
    r = client.get(reverse("pedidos:formulario", args=["limpeza"])).text
    assert "data-resumo-erros" not in r and 'aria-invalid="true"' not in r
    assert "campo-com-erro" not in r


def test_mensagem_sem_lista_fica_so_no_resumo(client):
    r = postar(client, "limpeza", "adulterado", itens=LIMPEZA_ITENS).text
    resumo = _resumo(r)
    assert MENSAGEM_TOKEN_INVALIDO in resumo and "coisa" not in resumo


def test_pedidos_js_foca_o_resumo_e_limpa_o_erro_ao_corrigir():
    from django.contrib.staticfiles import finders

    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    assert "[data-resumo-erros]" in js and "preventScroll" in js
    assert 'removeAttribute("aria-invalid")' in js and "campo-com-erro" in js


def test_inicio_fala_pelo_conteudo_com_exemplos(client):
    r = client.get(reverse("pedidos:inicio")).text
    for termo in ("Formulário 1", "Formulário 2", "Materiais AB"):
        assert termo not in r
    limpeza = r[r.index("Limpeza, copa e escritório") :]
    assert "Ex.: café, copo descartável, água sanitária, caneta" in limpeza
    ab = r[r.index("Ferramentas, peças e materiais") :]
    assert "Ex.: luva, botina, fita veda-rosca, cimento" in ab


@pytest.mark.parametrize(
    "fluxo,titulo",
    [("limpeza", "Limpeza, copa e escritório"), ("ab", "Ferramentas, peças e materiais")],
)
def test_formulario_tem_o_titulo_publico(client, fluxo, titulo):
    r = client.get(reverse("pedidos:formulario", args=[fluxo])).text
    assert f"<title>{titulo} — Central Almoxarifado</title>" in r
    assert f"<h1>{titulo}</h1>" in r
    assert '<p class="rotulo-secao">Pedido de materiais</p>' in r
    assert "Formulário" not in r[: r.index("<h1>")].split("<body", 1)[-1]


def test_formulario_oferece_limpar_nome_e_destino_dentro_do_campo(client):
    r = client.get(reverse("pedidos:formulario", args=["limpeza"])).text
    for campo in ("solicitante", "destino"):
        i = r.index(f'data-limpar-campo="{campo}"')
        botao = r[r.rindex("<button", 0, i) : r.index("</button>", i)]
        assert 'type="button"' in botao and "hidden" in botao  # o pedidos.js mostra com valor
        # O botão fica dentro do campo (.com-acao), logo depois do input.
        antes = r[: r.rindex("<button", 0, i)]
        assert antes.rstrip().endswith(">") and f'id="{campo}"' in antes[antes.rindex("com-acao") :]


def test_sucesso_diz_o_que_lembrar_no_aparelho(client, django_capture_on_commit_callbacks):
    t = token()
    with django_capture_on_commit_callbacks(execute=True):
        r = postar(
            client, "limpeza", t, solicitante="Ana Paula", destino="eta  ii", itens=LIMPEZA_ITENS
        )
        reenvio = postar(
            client, "limpeza", t, solicitante="Ana Paula", destino="eta  ii", itens=LIMPEZA_ITENS
        )
    for html in (r.text, reenvio.text):
        assert 'data-lembrar-solicitante="Ana Paula"' in html
        assert 'data-lembrar-destino="ETA II"' in html
    recusado = postar(client, "limpeza", token(), solicitante="", itens=LIMPEZA_ITENS).text
    assert "data-lembrar-solicitante" not in recusado


def test_pedidos_js_lembra_so_no_aparelho_e_com_cuidado():
    from django.contrib.staticfiles import finders

    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    assert '"almoxarifado.solicitante"' in js
    assert "[data-lembrar-solicitante]" in js and "[data-limpar-campo]" in js
    # O nome é gravado enquanto se digita, não só depois do envio.
    digitar = js[js.index("// O último nome escrito, mesmo sem enviar o pedido") :]
    digitar = digitar[: digitar.index("\n  });")]
    assert 'nome.id !== "solicitante"' in digitar
    assert "gravarLembrado(dados)" in digitar and "esquecerLembrado()" in digitar
    # Todo acesso ao localStorage fica dentro de try/catch (aba anônima, armazenamento bloqueado).
    linhas = [linha.strip() for linha in js.splitlines() if "localStorage" in linha]
    assert linhas and all(linha.startswith("try {") and "catch (e)" in linha for linha in linhas)


def test_pedidos_js_pergunta_antes_de_sair_com_pedido_em_montagem(client):
    from django.contrib.auth import get_user_model
    from django.contrib.staticfiles import finders

    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    assert '"beforeunload"' in js
    assert "[data-formulario-pedido] .carrinho-linha[data-codigo]" in js
    # A saída avulsa (área interna) não tem o atributo, então não ganha o aviso.
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    assert "data-formulario-pedido" not in client.get(reverse("pedidos:avulsa")).text


def test_rotulos_sem_asterisco(client):
    r = client.get(reverse("pedidos:formulario", args=["ab"])).text
    assert '<label class="campo-rotulo" for="solicitante">Nome completo</label>' in r
    assert '<label class="campo-rotulo" for="destino">Destino dos materiais</label>' in r
    passos = r[r.index("<h2>Seus dados</h2>") : r.index('<div class="acoes acoes-final">')]
    assert " *<" not in passos


def test_cabecalho_publico_sem_link_da_area_interna(client):
    for url in (reverse("pedidos:inicio"), reverse("pedidos:formulario", args=["ab"])):
        r = client.get(url).text
        topo = r[r.index('<header class="publico-topo">') : r.index("</header>")]
        assert "Área do almoxarifado" not in topo
        rodape = r[r.index('<footer class="publico-rodape">') :]
        assert "Área do almoxarifado" in rodape


def test_sucesso_lista_o_destino_e_os_materiais(client, django_capture_on_commit_callbacks):
    t = token()
    with django_capture_on_commit_callbacks(execute=True):
        r = postar(client, "limpeza", t, itens=LIMPEZA_ITENS).text
        reenvio = postar(client, "limpeza", t, itens=LIMPEZA_ITENS).text
    for html in (r, reenvio):
        lista = html[html.index('<ul class="sucesso-itens">') :]
        lista = lista[: lista.index("</ul>")]
        assert lista.count("<li>") == 2
        assert "<span>DETERGENTE NEUTRO</span> <strong>2" in lista
        assert "<span>CAFÉ 500 G</span> <strong>1,5" in lista
        assert "Destino: <strong>ETA II</strong>" in html


def test_botao_do_fim_so_aparece_sem_javascript(client):
    # No celular o envio é pela gaveta; o botão do fim continua na página (a gaveta envia por
    # ele, e sem JavaScript é o único envio), escondido pelo CSS quando há JavaScript.
    from django.contrib.staticfiles import finders

    r = client.get(reverse("pedidos:formulario", args=["ab"])).text
    final = r[r.index('<div class="acoes acoes-final">') :]
    assert 'type="submit"' in final[: final.index("</div>")]
    css = open(finders.find("pedidos/css/pedidos.css"), encoding="utf-8").read()
    assert ".js .acoes-final { display: none; }" in css


def test_pedidos_js_so_cancela_a_alteracao_aberta_com_hx_post_de_botao():
    # O próprio <form hx-post> é ancestral de todo clique dentro do pedido: sem excluí-lo, o −, o +
    # e o "Confirmar" da quantidade aberta a cancelariam (e restaurariam o valor) antes de agirem.
    from django.contrib.staticfiles import finders

    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    trecho = js[js.index('closest("[hx-post]")') :]
    trecho = trecho[: trecho.index("forEach")]
    assert 'matches("form")' in trecho


# --- itens com problema ficam no pedido (spec 005, US4) ----------------------------------------


def _linha_do_pedido(html, codigo):
    """O <li> do item no pedido (na gaveta e na coluna), com o que o funcionário vê."""
    inicio = html.index('<li class="carrinho-linha')
    lista = html[inicio : html.index("</ul>", inicio)]
    (item,) = [i for i in re.split(r"(?=<li class=\"carrinho-linha)", lista) if codigo in i]
    return item


def test_recusa_por_estoque_mantem_o_pedido_e_corrigir_envia(client):
    t = token()
    r = postar(client, "ab", t, itens=[("016.005.010", "3"), ("013.006.001", "3")])
    texto = "BOTINA (013.006.001): Quantidade acima do estoque. Estoque disponível: 2 UN."
    assert texto in r.text
    assert 'name="item_codigo" value="016.005.010"' in r.text  # o item sem problema fica
    assert "Corrigir" in _linha_do_pedido(r.text, "013.006.001")
    assert "Corrigir" not in _linha_do_pedido(r.text, "016.005.010")
    # Corrigir a quantidade e reenviar com o mesmo ingresso registra o pedido.
    r = postar(client, "ab", t, itens=[("016.005.010", "3"), ("013.006.001", "2")])
    assert "Pedido registrado" in r.text


def test_quantidade_ilegivel_continua_no_pedido_com_o_texto_digitado(client):
    r = postar(client, "limpeza", token(), itens=[("023.001.002", "2"), ("008.001.002", "1,5x")])
    assert (
        "CAFÉ 500 G (008.001.002): "
        "Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5)." in r.text
    )
    linha = _linha_do_pedido(r.text, "008.001.002")
    assert 'name="item_codigo" value="008.001.002"' in linha
    assert 'value="1,5x"' in linha and "Corrigir" in linha
    assert "Corrigir" not in _linha_do_pedido(r.text, "023.001.002")
    assert not Pedido.objects.exists()


def test_fracao_em_material_contado_continua_no_pedido_marcada(client):
    r = postar(client, "limpeza", token(), itens=[("023.004.001", "2,5")])  # PAPEL, em UN
    assert "Este material só é pedido em quantidade inteira (unidade: UN)." in r.text
    linha = _linha_do_pedido(r.text, "023.004.001")
    assert 'value="2,5"' in linha and "Corrigir" in linha


def _itens_do_carrinho(html):
    codigos = re.findall(r'name="item_codigo" value="([^"]*)"', html)
    quantidades = re.findall(r'name="item_qtd" value="([^"]*)"', html)
    return list(zip(codigos, quantidades, strict=True))


@pytest.mark.parametrize(
    ("fluxo", "codigo", "invalida", "corrigida"),
    [
        ("limpeza", "008.001.002", "1,5x", "1,5"),
        ("limpeza", "023.004.001", "2,5", "2"),
        ("ab", "013.006.001", "1,5", "1"),
    ],
)
def test_corrigir_linha_invalida_pelo_carrinho_permite_reenviar(
    client, fluxo, codigo, invalida, corrigida
):
    t = token()
    recusado = postar(client, fluxo, t, itens=[(codigo, invalida)])
    assert _itens_do_carrinho(recusado.text) == [(codigo, invalida)]
    assert "Corrigir" in _linha_do_pedido(recusado.text, codigo)
    assert not Pedido.objects.exists()

    r = client.post(
        reverse("pedidos:carrinho", args=[fluxo]),
        {
            "item_codigo": [codigo],
            "item_qtd": [corrigida],
            "alterar": codigo,
            "anterior": invalida,
        },
    )
    assert _itens_do_carrinho(r.text) == [(codigo, corrigida)]
    assert "Corrigir" not in r.text and "data-carrinho-alerta" not in r.text
    enviado = postar(client, fluxo, t, itens=_itens_do_carrinho(r.text))
    assert "Pedido registrado" in enviado.text
    assert Pedido.objects.get().itens.get().codigo == codigo


@pytest.mark.parametrize(
    ("acao", "esperados"),
    [
        ({"remover": "023.001.002"}, [("008.001.002", "1,5x")]),
        (
            {"adicionar": "023.004.001", "qtd-023.004.001": "1"},
            [("023.001.002", "2"), ("008.001.002", "1,5x"), ("023.004.001", "1")],
        ),
        (
            {"alterar": "023.001.002", "anterior": "2"},
            [("023.001.002", "3"), ("008.001.002", "1,5x")],
        ),
        (
            {"adicionar": "008.001.002", "qtd-008.001.002": "1"},
            [("023.001.002", "2"), ("008.001.002", "1,5x")],
        ),
        ({"remover": "008.001.002"}, [("023.001.002", "2")]),
    ],
    ids=["remover-outro", "adicionar-outro", "alterar-outro", "somar-invalido", "remover-invalido"],
)
def test_operacoes_do_carrinho_preservam_linha_invalida_ate_corrigir_ou_remover(
    client, acao, esperados
):
    recusado = postar(
        client, "limpeza", token(), itens=[("023.001.002", "2"), ("008.001.002", "1,5x")]
    )
    itens = _itens_do_carrinho(recusado.text)
    if "alterar" in acao:
        itens[0] = ("023.001.002", "3")
    r = client.post(
        reverse("pedidos:carrinho", args=["limpeza"]),
        {"item_codigo": [c for c, _ in itens], "item_qtd": [q for _, q in itens], **acao},
    )
    assert _itens_do_carrinho(r.text) == esperados
    if ("008.001.002", "1,5x") in esperados:
        assert "Corrigir" in _linha_do_pedido(r.text, "008.001.002")
    else:
        assert "Corrigir" not in r.text
    if acao.get("adicionar") == "008.001.002":
        assert "data-carrinho-alerta" in r.text
    assert not Pedido.objects.exists()


def test_nova_correcao_invalida_mantem_o_texto_anterior_para_corrigir(client):
    codigo = "008.001.002"
    r = client.post(
        reverse("pedidos:carrinho", args=["limpeza"]),
        {"item_codigo": [codigo], "item_qtd": ["x"], "alterar": codigo, "anterior": "1,5x"},
    )
    assert _itens_do_carrinho(r.text) == [(codigo, "1,5x")]
    assert "Corrigir" in _linha_do_pedido(r.text, codigo)
    assert "data-carrinho-alerta" in r.text


# --- JavaScript é requisito dos formulários públicos (spec 005, US7) ---------------------------

AVISO_SEM_JS = (
    "Este formulário precisa de JavaScript para funcionar. Ative o JavaScript no navegador, "
    "use outro navegador ou procure o almoxarifado."
)


@pytest.mark.parametrize("fluxo", ["limpeza", "ab"])
def test_pagina_traz_o_aviso_de_javascript_dentro_de_noscript(client, fluxo):
    html = client.get(reverse("pedidos:formulario", args=[fluxo])).text
    noscript = html[html.index("<noscript>") : html.index("</noscript>")]
    assert AVISO_SEM_JS in noscript
    assert 'role="alert"' in noscript
    # O aviso vem antes do formulário.
    assert html.index("<noscript>") < html.index('id="formulario"')


def test_css_esconde_o_formulario_publico_sem_a_classe_js():
    from django.contrib.staticfiles import finders

    css = open(finders.find("pedidos/css/pedidos.css"), encoding="utf-8").read()
    assert "html:not(.js) .formulario-pedido { display: none; }" in css


@pytest.mark.parametrize("modelo", ["_materiais.html", "_carrinho.html", "_resultados.html"])
def test_modelos_nao_prometem_funcionar_sem_javascript(modelo):
    """Texto do arquivo, não o navegador: o formulário público (e a saída avulsa, que usa os
    mesmos trechos) depende do HTMX para buscar, adicionar, alterar e remover."""
    from pathlib import Path

    texto = (Path("pedidos/templates/pedidos") / modelo).read_text(encoding="utf-8")
    assert "sem javascript" not in texto.lower()


def test_formulario_ab_e_limpeza_so_escondem_o_formulario_quando_nao_ha_javascript(client):
    """Com JavaScript (a classe `js` no <html>), nada muda: o aviso fica dentro de <noscript>."""
    html = client.get(reverse("pedidos:formulario", args=["ab"])).text
    assert 'document.documentElement.classList.add("js")' in html
    assert html.count("<noscript>") == 1
