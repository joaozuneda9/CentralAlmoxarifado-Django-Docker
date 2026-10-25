from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.urls import reverse
from django.utils.html import strip_tags

from catalogo.catalogos import ItemCatalogo
from pedidos.carrinho import LinhaCarrinho, adicionar, alterar, remover
from pedidos.fluxos import FLUXOS, LIMITE_RESULTADOS, buscar, opcoes_filtro
from pedidos.regras import estoque_inteiro
from pedidos.servicos import catalogo_de
from tests.cenario import dar_saldo, montar_cenario

LIMPEZA_F = FLUXOS["limpeza"]
AB_F = FLUXOS["ab"]


def item(codigo, nome="X", disponivel=0, **extra):
    campos = {
        "codigo": codigo,
        "nome": nome,
        "unidade": "UN",
        "categoria": "",
        "grupo": "G",
        "subgrupo": "S",
        "estoque": Decimal(disponivel),
        "disponivel": estoque_inteiro(disponivel),
        "duplicado": False,
    }
    campos.update(extra)
    return ItemCatalogo(**campos)


# Fracionável: nos testes de quantidade, o `fracionavel` do item é quem decide a fração.
DETERGENTE = item("023.001.002", "DETERGENTE", 100, categoria="Limpeza", fracionavel=True)


def item_ab(codigo, disponivel):
    return item(codigo, "FITA", disponivel)


def test_adicionar_novo():
    c = adicionar([], LIMPEZA_F, DETERGENTE, "1,5")
    assert [(linha.codigo, linha.texto) for linha in c.linhas] == [("023.001.002", "1,5")]
    assert (c.erro, c.aviso) == ("", "")


def test_soma_com_o_que_ja_estava_avisa():
    c = adicionar(
        [LinhaCarrinho("023.001.002", Decimal(2), DETERGENTE)], LIMPEZA_F, DETERGENTE, "1,5"
    )
    assert [linha.texto for linha in c.linhas] == ["3,5"]
    assert c.aviso == "DETERGENTE já estava no pedido: 2 UN + 1,5 UN = 3,5 UN."


def test_ab_estoque_mensagens():
    fita = item_ab("016.005.010", 10)
    assert adicionar([], AB_F, fita, "11").erro == (
        "Quantidade acima do estoque. Estoque disponível: 10 UN."
    )
    assert adicionar([LinhaCarrinho(fita.codigo, 8, fita)], AB_F, fita, "3").erro == (
        "Já há 8 UN no pedido; é possível acrescentar no máximo 2 UN."
    )
    assert adicionar([LinhaCarrinho(fita.codigo, 10, fita)], AB_F, fita, "1").erro == (
        "Já há 10 UN no pedido, que é todo o estoque disponível."
    )


def test_quantidades_invalidas():
    # Material contado: fração é recusada com o texto único; o resto pede inteiro.
    assert adicionar([], AB_F, item_ab("1", 10), "1,5").erro == (
        "Este material só é pedido em quantidade inteira (unidade: UN)."
    )
    assert adicionar([], AB_F, item_ab("1", 10), "abc").erro == (
        "Informe um número inteiro maior que zero."
    )
    # Material fracionável: o texto pede a vírgula.
    texto = "Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5)."
    assert adicionar([], LIMPEZA_F, DETERGENTE, "1.5").erro == texto
    assert adicionar([], LIMPEZA_F, DETERGENTE, "0").erro == texto
    assert adicionar([], LIMPEZA_F, DETERGENTE, "1000000").erro == "A quantidade máxima é 999.999."


def test_bloqueados_nao_entram():
    duplicado = item("1", "SABÃO", duplicado=True)
    c = adicionar([], LIMPEZA_F, duplicado, "1")
    assert c.linhas == []
    assert (
        c.erro == "SABÃO (1): Cadastro duplicado — avise o almoxarifado — não pode ser adicionado."
    )
    assert adicionar([], AB_F, item("2", "LUVA", 0), "1").erro == (
        "LUVA (2): Sem estoque — não pode ser adicionado."
    )
    assert adicionar([], AB_F, None, "1").erro == "Material não encontrado no catálogo."


def test_maximo_de_itens(settings):
    settings.PEDIDOS_MAX_ITENS = 2
    linhas = [LinhaCarrinho(str(n), Decimal(1), item(str(n), disponivel=10)) for n in range(2)]
    assert adicionar(linhas, LIMPEZA_F, item("9", disponivel=10), "1").erro == (
        "O pedido pode ter no máximo 2 materiais."
    )
    assert adicionar(linhas, LIMPEZA_F, item("0", disponivel=10), "1").erro == ""


def test_remover():
    linhas = [LinhaCarrinho("1", Decimal(1), item("1")), LinhaCarrinho("2", Decimal(1), item("2"))]
    assert [linha.codigo for linha in remover(linhas, "1").linhas] == ["2"]


CATALOGO = [
    item("008.001.002", "CAFÉ 500 G", categoria="Copa/cozinha"),
    item("016.005.010", "FITA VEDA ROSCA", grupo="REDES DE ÁGUA", subgrupo="VEDAÇÃO"),
    item("013.006.001", "BOTINA", grupo="EPI", subgrupo="CALÇADOS"),
    item("013.005.007", "LUVA NITRÍLICA", grupo="EPI", subgrupo="LUVAS"),
]


def test_buscar_sem_acento_e_em_qualquer_ordem():
    assert [i.nome for i in buscar(LIMPEZA_F, CATALOGO, "cafe", "")[0]] == ["CAFÉ 500 G"]
    assert [i.nome for i in buscar(AB_F, CATALOGO, "rosca fita", "")[0]] == ["FITA VEDA ROSCA"]


def test_codigo_so_entra_na_busca_da_saida_avulsa():
    # O público busca só pelo nome; a equipe, na saída avulsa, também pelo código.
    assert buscar(AB_F, CATALOGO, "016.005", "")[0] == []
    assert buscar(LIMPEZA_F, CATALOGO, "008.001", "")[0] == []
    assert [i.nome for i in buscar(FLUXOS["avulsa"], CATALOGO, "016.005", "")[0]] == [
        "FITA VEDA ROSCA"
    ]


def test_buscar_filtro_ab_por_grupo_e_subgrupo():
    assert [i.nome for i in buscar(AB_F, CATALOGO, "", "EPI")[0]] == ["BOTINA", "LUVA NITRÍLICA"]
    assert [i.nome for i in buscar(AB_F, CATALOGO, "", "EPI › LUVAS")[0]] == ["LUVA NITRÍLICA"]
    assert [i.nome for i in buscar(LIMPEZA_F, CATALOGO, "", "EPI")[0]] == [
        "BOTINA",
        "LUVA NITRÍLICA",
    ]
    assert [i.nome for i in buscar(LIMPEZA_F, CATALOGO, "", "EPI › LUVAS")[0]] == ["LUVA NITRÍLICA"]
    assert buscar(LIMPEZA_F, CATALOGO, "", "Copa/cozinha")[0] == []


def test_opcoes_de_filtro_sao_os_grupos_e_subgrupos_nos_dois_formularios():
    esperado = [("EPI", ["CALÇADOS", "LUVAS"]), ("G", ["S"]), ("REDES DE ÁGUA", ["VEDAÇÃO"])]
    assert opcoes_filtro(LIMPEZA_F, CATALOGO) == esperado
    assert opcoes_filtro(AB_F, CATALOGO) == esperado
    assert opcoes_filtro(FLUXOS["avulsa"], CATALOGO) == []


def test_buscar_limita_a_50_com_total():
    muitos = [item(f"000.000.{n:03d}", f"ITEM {n}") for n in range(70)]
    achados, total = buscar(LIMPEZA_F, muitos, "item", "")
    assert len(achados) == LIMITE_RESULTADOS == 50 and total == 70


@pytest.mark.django_db
def test_catalogo_do_cenario_no_fluxo_ab():
    montar_cenario()
    assert [i.codigo for i in buscar(AB_F, catalogo_de("AB"), "", "")[0]] == [
        "016.005.010",
        "013.006.001",
        "013.005.007",
    ]


@pytest.mark.django_db
def test_endpoint_de_busca_ab(client):
    montar_cenario()
    r = client.get(reverse("pedidos:materiais", args=["ab"]), {"q": "fita"})
    assert r.status_code == 200
    assert "FITA VEDA ROSCA" in r.text and "Estoque 10 · UN" in r.text
    assert '"adicionar": "016.005.010"' in r.text
    assert "BOTINA" not in r.text
    assert client.get(reverse("pedidos:materiais", args=["avulsa"])).status_code == 404
    assert client.get(reverse("pedidos:materiais", args=["xyz"])).status_code == 404


@pytest.mark.django_db
def test_endpoint_do_carrinho(client):
    montar_cenario()
    url = reverse("pedidos:carrinho", args=["ab"])
    r = client.post(url, {"adicionar": "016.005.010", "qtd-016.005.010": "3"})
    assert 'name="item_codigo" value="016.005.010"' in r.text
    assert 'name="item_qtd" value="3"' in r.text
    r = client.post(
        url,
        {
            "item_codigo": "016.005.010",
            "item_qtd": "3",
            "adicionar": "016.005.010",
            "qtd-016.005.010": "8",
        },
    )
    assert "Já há 3 UN no pedido; é possível acrescentar no máximo 7 UN." in r.text
    r = client.post(url, {"item_codigo": "016.005.010", "item_qtd": "3", "remover": "016.005.010"})
    assert "Nenhum material adicionado ainda." in r.text
    assert client.get(url).status_code == 405


@pytest.mark.django_db
def test_carrinho_no_vocabulario_novo(client):
    montar_cenario()
    r = client.post(
        reverse("pedidos:carrinho", args=["ab"]),
        {"adicionar": "016.005.010", "qtd-016.005.010": "3"},
    )
    assert 'class="carrinho"' in r.text and 'class="carrinho-linha"' in r.text
    assert "Seu pedido (1)" in r.text


@pytest.mark.django_db
def test_carrinho_tem_barra_e_gaveta(client):
    # No celular o pedido fica numa gaveta (<dialog>) aberta pela barra fixa; a barra vem no
    # mesmo trecho que o HTMX troca, então a contagem se atualiza sozinha.
    montar_cenario()
    url = reverse("pedidos:carrinho", args=["ab"])
    r = client.post(url, {"adicionar": "016.005.010", "qtd-016.005.010": "3"})
    barra = r.text[r.text.index('class="carrinho-barra"') : r.text.index("<dialog")]
    assert "Seu pedido</span><span>1 material</span>" in barra
    assert (
        'data-carrinho-abrir aria-haspopup="dialog" aria-controls="carrinho-gaveta" '
        'aria-expanded="false"' in barra
    )
    assert (
        '<dialog id="carrinho-gaveta" class="carrinho-gaveta" aria-labelledby="carrinho-titulo">'
        in r.text
    )
    assert 'data-codigo="016.005.010" data-qtd="3 UN"' in r.text
    assert "data-carrinho-alerta" not in r.text
    r = client.post(url, {"adicionar": "016.005.010", "qtd-016.005.010": "11"})
    assert "data-carrinho-alerta" in r.text  # o JS abre a gaveta para mostrar o motivo


@pytest.mark.django_db
def test_resultados_marcaveis_pelo_codigo(client):
    montar_cenario()
    r = client.get(reverse("pedidos:materiais", args=["ab"]), {"q": "fita"})
    assert "Resultados da busca" not in r.text  # o painel não tem legenda
    assert 'data-codigo="016.005.010"' in r.text
    # O "no pedido" vai no selo `data-selo-pedido` (escondido; o pedidos.js o mostra), não num
    # atributo da linha, também na saída avulsa.
    assert "data-no-pedido" not in r.text
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    avulsa = client.get(reverse("pedidos:avulsa_materiais"), {"q": "item"}).text
    assert "data-no-pedido" not in avulsa


@pytest.mark.django_db
def test_resultados_publicos_sem_codigo_nem_classe(client):
    montar_cenario()
    r = client.get(reverse("pedidos:materiais", args=["ab"]), {"q": "fita"})
    dados = r.text[r.text.index('<div class="material-dados">') :]
    dados = dados[: dados.index("</div>")]
    assert "FITA VEDA ROSCA" in dados and "Estoque 10 · UN" in dados
    assert "016.005.010" not in dados and "REDES DE" not in dados


def test_alterar_substitui_a_quantidade():
    linhas = [LinhaCarrinho("023.001.002", Decimal(2), DETERGENTE)]
    c = alterar(linhas, LIMPEZA_F, DETERGENTE, "0,5")
    assert [linha.texto for linha in c.linhas] == ["0,5"]
    assert (c.erro, c.aviso) == ("", "")


def test_alterar_recusa_e_mantem_a_anterior():
    fita = item_ab("016.005.010", 10)
    linhas = [LinhaCarrinho(fita.codigo, 3, fita)]
    casos = {
        "11": "Quantidade acima do estoque. Estoque disponível: 10 UN.",
        "1,5": "Este material só é pedido em quantidade inteira (unidade: UN).",
        "0": "Informe um número inteiro maior que zero.",
        "abc": "Informe um número inteiro maior que zero.",
    }
    for texto, erro in casos.items():
        c = alterar(linhas, AB_F, fita, texto)
        assert c.erro == erro and [linha.texto for linha in c.linhas] == ["3"]
    detergente = [LinhaCarrinho("023.001.002", Decimal(2), DETERGENTE)]
    assert alterar(detergente, LIMPEZA_F, DETERGENTE, "1.5").erro == (
        "Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5)."
    )
    assert alterar(detergente, LIMPEZA_F, None, "1").erro == "Material não encontrado no catálogo."


def test_alterar_recusa_material_que_nao_esta_no_pedido():
    fita = item_ab("016.005.010", 10)
    c = alterar([], AB_F, fita, "2")
    assert c.erro == "Material não está no pedido." and c.linhas == []


@pytest.mark.django_db
def test_endpoint_altera_a_quantidade_do_pedido(client):
    montar_cenario()
    url = reverse("pedidos:carrinho", args=["ab"])
    pedido = {"item_codigo": "016.005.010", "alterar": "016.005.010", "anterior": "3"}
    r = client.post(url, {**pedido, "item_qtd": "5"})
    assert 'name="item_qtd" value="5"' in r.text and "data-carrinho-alerta" not in r.text
    r = client.post(url, {**pedido, "item_qtd": "50"})
    assert 'name="item_qtd" value="3"' in r.text  # volta para a anterior
    assert "Quantidade acima do estoque. Estoque disponível: 10 UN." in r.text
    assert "data-carrinho-alerta" in r.text


@pytest.mark.django_db
def test_endpoint_alterar_corrige_anterior_invalido_sem_sumir_com_a_linha(client):
    montar_cenario()
    url = reverse("pedidos:carrinho", args=["ab"])
    pedido = {"item_codigo": "016.005.010", "alterar": "016.005.010", "item_qtd": "5"}
    r = client.post(url, {**pedido, "anterior": "lixo"})
    assert 'name="item_codigo" value="016.005.010"' in r.text
    assert 'name="item_qtd" value="5"' in r.text
    assert "data-carrinho-alerta" not in r.text


@pytest.mark.django_db
def test_aviso_de_material_repetido_tem_cara_de_aviso(client):
    montar_cenario()
    url = reverse("pedidos:carrinho", args=["ab"])
    pedido = {"item_codigo": "016.005.010", "item_qtd": "1", "adicionar": "016.005.010"}
    r = client.post(url, {**pedido, "qtd-016.005.010": "1"})
    aviso = r.text[r.text.index('class="aviso aviso-atencao"') :]
    aviso = aviso[: aviso.index("</div>")]
    assert "FITA VEDA ROSCA já estava no pedido: 1 UN + 1 UN = 2 UN." in aviso
    assert 'class="icone"' in aviso and "aviso-info" not in r.text


def test_gaveta_segue_a_largura_da_area_dos_passos_e_nao_a_da_janela():
    # O pedido fica na coluna ao lado dos passos só com 960px de largura (@container em
    # pedidos.css). Sem esse espaço, vira gaveta: `data-gaveta` no <html>, posto no <head>
    # (celular, sem piscar) e acompanhado pelo pedidos.js (ResizeObserver) conforme a área muda.
    css = open(finders.find("interface/css/componentes.css"), encoding="utf-8").read()
    assert "@media (max-width: 767px)" not in css and ".js[data-gaveta] .carrinho-barra" in css
    pedidos = open(finders.find("pedidos/css/pedidos.css"), encoding="utf-8").read()
    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    assert "@container (min-width: 960px)" in pedidos and "LARGURA_LADO_A_LADO = 960" in js
    # Só o ponteiro de toque da busca usa matchMedia, nunca a largura.
    assert "ResizeObserver" in js and 'matchMedia("(max-width' not in js


@pytest.mark.django_db
def test_botoes_do_pedido_tem_icone(client):
    montar_cenario()
    html = client.get(reverse("pedidos:formulario", args=["ab"])).text

    def botao(texto):
        trecho = html[: html.index(texto)]
        return trecho[trecho.rindex("<button") :]

    # Formulário aberto, pedido vazio: envio (send) e o "Adicionar mais materiais" da gaveta, sem
    # "Revisar e enviar" (não há o que revisar) nem o envio da gaveta.
    assert "<svg" in botao("Enviar pedido")
    assert "Nenhum material adicionado" in html and "data-carrinho-abrir" not in html
    assert "data-carrinho-enviar" not in html
    continuar = html[html.index("data-carrinho-continuar>") :]
    assert continuar.startswith("data-carrinho-continuar>Adicionar mais materiais")


@pytest.mark.django_db
def test_head_marca_o_celular_com_data_gaveta(client):
    montar_cenario()
    r = client.get(reverse("pedidos:formulario", args=["ab"]))
    assert 'matchMedia("(max-width: 767px)").matches' in r.text and "data-gaveta" in r.text


@pytest.mark.django_db
def test_quantidade_editavel_no_pedido(client):
    montar_cenario()
    url = reverse("pedidos:carrinho", args=["ab"])
    r = client.post(url, {"adicionar": "016.005.010", "qtd-016.005.010": "3"})
    linha = r.text[r.text.index('<li class="carrinho-linha') : r.text.index("</li>")]
    assert 'type="hidden" name="item_qtd"' not in linha
    assert 'type="text" name="item_qtd" value="3"' in linha
    # Formulário público: a alteração só vai ao servidor no "Confirmar" (evento do pedidos.js).
    assert 'hx-trigger="confirmar-quantidade"' in linha and "data-qtd-carrinho" in linha
    assert """hx-vals='{"alterar": "016.005.010", "anterior": "3"}'""" in linha
    assert 'data-quantidade="menos"' in linha and 'data-quantidade="mais"' in linha


def _barra(html):
    return html[html.index('class="carrinho-barra"') : html.index("<dialog")]


@pytest.mark.django_db
def test_barra_e_gaveta_do_formulario_publico(client):
    # Sem material, a barra só diz isso; com material, conta e leva a revisar e enviar. A gaveta
    # envia (botão principal, que o pedidos.js liga ao envio do formulário) e deixa continuar.
    montar_cenario()
    url = reverse("pedidos:carrinho", args=["ab"])
    vazio = client.post(url, {}).text
    assert "Nenhum material adicionado" in _barra(vazio)
    assert "data-carrinho-abrir" not in vazio and "data-carrinho-enviar" not in vazio
    r = client.post(url, {"adicionar": "016.005.010", "qtd-016.005.010": "3"}).text
    barra = _barra(r)
    assert "Seu pedido</span><span>1 material</span>" in barra
    abrir = barra[barra.index("<button") :]
    assert "data-carrinho-abrir" in abrir and "Revisar e enviar" in abrir
    assert abrir.index("<svg") < abrir.index("Revisar e enviar")  # ícone antes do texto
    enviar = r[: r.index("Enviar pedido")]
    enviar = enviar[enviar.rindex("<button") :]
    assert 'type="button"' in enviar and "botao-primario" in enviar
    assert "data-carrinho-enviar" in enviar and "<svg" in enviar
    continuar = r[: r.index("Adicionar mais materiais")]
    continuar = continuar[continuar.rindex("<button") :]
    assert "data-carrinho-continuar" in continuar and "botao-secundario" in continuar
    assert r.index("data-carrinho-enviar") < r.index("data-carrinho-continuar")
    dois = client.post(
        url,
        {
            "item_codigo": "016.005.010",
            "item_qtd": "3",
            "adicionar": "013.006.001",
            "qtd-013.006.001": "1",
        },
    ).text
    assert "<span>2 materiais</span>" in _barra(dois)


@pytest.mark.django_db
def test_barra_e_gaveta_da_saida_avulsa_seguem_o_formulario_com_os_textos_da_saida(client):
    montar_cenario()
    dar_saldo("000.000.900")
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    r = client.post(
        reverse("pedidos:avulsa_carrinho"), {"adicionar": "000.000.900", "qtd-000.000.900": "1"}
    ).text
    barra = _barra(r)
    assert "Materiais da saída</span><span>1 material</span>" in barra
    assert "Revisar e registrar" in barra and "Seu pedido" not in r
    assert "Materiais da saída (1)" in r
    enviar = r[r.index("data-carrinho-enviar") :]
    assert "<span data-carrinho-enviar-rotulo>Registrar saída</span>" in enviar
    assert "data-carrinho-continuar>Adicionar mais materiais" in r
    vazio = client.get(reverse("pedidos:avulsa")).text
    assert "Nenhum material adicionado" in _barra(vazio[vazio.index('class="carrinho-barra"') :])


def test_pedidos_js_envia_pela_gaveta():
    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    assert "[data-carrinho-enviar]" in js and "requestSubmit" in js
    assert ".acoes-final button[type=submit]" in js


def test_buscar_poe_os_que_podem_ser_pedidos_primeiro():
    catalogo = [
        item("1", "LUVA A", 0),
        item("2", "LUVA B", 5),
        item("3", "LUVA C", 0),
        item("4", "LUVA D", 2),
    ]
    assert [i.codigo for i in buscar(AB_F, catalogo, "luva", "")[0]] == ["2", "4", "1", "3"]
    # Na limpeza também bloqueiam o cadastro duplicado e o saldo zerado.
    catalogo[1] = item("2", "LUVA B", 5, duplicado=True)
    assert [i.codigo for i in buscar(LIMPEZA_F, catalogo, "luva", "")[0]] == ["4", "1", "2", "3"]


def test_buscar_ordena_antes_de_cortar_em_50():
    sem = [item(f"000.000.{n:03d}", f"ITEM {n}", 0) for n in range(60)]
    com = [item("999.000.001", "ITEM COM ESTOQUE", 3)]
    achados, total = buscar(AB_F, sem + com, "item", "")
    assert total == 61 and achados[0].codigo == "999.000.001"


def test_texto_de_estoque_do_ab():
    from pedidos.fluxos import resultados

    # A mesma linha nos dois formulários: "Estoque N · UN" (sem a unidade quando não há).
    assert resultados(AB_F, [item("1", "LUVA", 356, unidade="UN")])[0].linha_publica == (
        "Estoque 356 · UN"
    )
    assert resultados(AB_F, [item("1", "LUVA", 3, unidade="")])[0].linha_publica == "Estoque 3"


def test_estoque_na_linha_da_avulsa_e_da_limpeza():
    from pedidos.fluxos import resultados

    avulsa = FLUXOS["avulsa"]
    assert resultados(avulsa, [item("1", "LUVA", 12)])[0].estoque == "Estoque 12"
    assert resultados(avulsa, [item("1", "LUVA", Decimal("2.5"))])[0].estoque == "Estoque 2,5"
    # O saldo tem 4 casas: não se arredonda para as 3 da quantidade.
    # O estoque mostrado é o máximo aceito: o saldo de 4 casas é cortado em 3, nunca arredondado.
    assert resultados(avulsa, [item("1", "LUVA", Decimal("0.0004"))])[0].estoque == "Estoque 0"
    assert resultados(avulsa, [item("1", "LUVA", Decimal("2.4996"))])[0].estoque == "Estoque 2,499"
    assert resultados(AB_F, [item("1", "LUVA", 12)])[0].estoque == "Estoque 12"
    # Formulário público: o estoque vem antes da unidade, sem o "—" de quem não tem unidade.
    com_unidade = item("1", "SACO", 7, unidade="Pacote 500 g")
    assert resultados(LIMPEZA_F, [com_unidade])[0].linha_publica == "Estoque 7 · Pacote 500 g"
    sem_unidade = item("1", "SACO", 7, unidade="")
    assert resultados(LIMPEZA_F, [sem_unidade])[0].linha_publica == "Estoque 7"
    assert resultados(AB_F, [item("1", "LUVA", 3, unidade="")])[0].linha_publica == "Estoque 3"


@pytest.mark.django_db
def test_telas_mostram_o_estoque_entre_o_codigo_e_a_unidade(client):
    montar_cenario()
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    avulsa = client.get(reverse("pedidos:avulsa_materiais"), {"q": "fita"}).text
    assert '<span class="mono">016.005.010</span> · Estoque 10 · UN · REDES DE ÁGUA' in avulsa
    botina = client.get(reverse("pedidos:avulsa_materiais"), {"q": "botina"}).text
    assert "Estoque 2,5 · UN" in botina
    limpeza = client.get(reverse("pedidos:materiais", args=["limpeza"]), {"q": "papel"}).text
    visivel = strip_tags(limpeza)
    assert "Estoque 50 · UN" in visivel and "023.004.001" not in visivel


@pytest.mark.django_db
def test_unidade_so_embaixo_do_nome_e_anuncio_do_adicionado(client):
    montar_cenario()
    r = client.get(reverse("pedidos:materiais", args=["ab"]), {"q": "fita"}).text
    acao = r[r.index('<div class="material-acao"') :]
    acao = acao[: acao.index("</li>")]
    assert ">UN<" not in acao and "Estoque 10 · UN" in r
    pagina = client.get(reverse("pedidos:formulario", args=["ab"])).text
    assert pagina.count("data-anuncio-adicionado") == 1
    anuncio = pagina[: pagina.index("data-anuncio-adicionado")]
    assert 'role="status"' in anuncio[anuncio.rindex("<") :]
    assert pagina.index("data-anuncio-adicionado") > pagina.index('id="resultados"')
    resultados_ = pagina[pagina.index('id="resultados"') : pagina.index("data-anuncio-adicionado")]
    assert resultados_.count("<div") <= resultados_.count("</div>")  # fora do #resultados


@pytest.mark.django_db
def test_codigo_so_aparece_no_carrinho_da_avulsa(client):
    montar_cenario()
    dar_saldo("000.000.900")
    r = client.post(
        reverse("pedidos:carrinho", args=["ab"]),
        {"adicionar": "016.005.010", "qtd-016.005.010": "1"},
    ).text
    linha = r[r.index('<li class="carrinho-linha') : r.index("</li>")]
    assert "FITA VEDA ROSCA" in linha and "016.005.010</span>" not in linha
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    r = client.post(
        reverse("pedidos:avulsa_carrinho"), {"adicionar": "000.000.900", "qtd-000.000.900": "1"}
    ).text
    assert "000.000.900</span>" in r


def test_pedidos_js_avisa_o_adicionado():
    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    assert "[data-anuncio-adicionado]" in js and '"Adicionado"' in js


@pytest.mark.django_db
def test_resultado_publico_adiciona_em_dois_passos(client):
    # Com JavaScript, tocar na linha do material (o botão `material-abrir`, dentro dos dados) abre a
    # quantidade, que se confirma; o selo "no pedido" fica ao lado da informação. Sem JavaScript, a
    # quantidade e o botão (que diz "Adicionar") ficam à vista.
    montar_cenario()
    r = client.get(reverse("pedidos:materiais", args=["ab"]), {"q": "fita"}).text
    item = r[r.index('<li class="material"') :]
    item = item[: item.index("</li>")]
    dados = item[: item.index('<div class="material-acao"')]
    abrir = dados[dados.index('<button type="button" class="material-abrir"') :]
    abrir = abrir[: abrir.index("</button>")]
    assert "data-adicionar-abrir" in abrir and 'aria-expanded="false"' in abrir
    assert 'aria-controls="qtd-area-1"' in abrir and ">Adicionar" in abrir
    assert "data-selo-pedido" in dados and "hidden" in dados[dados.index("data-selo-pedido") :]
    assert 'class="material-mais" aria-hidden="true"' in dados
    acao = item[item.index('<div class="material-acao" data-adicionar>') :]
    assert "data-adicionar-abrir" not in acao  # o botão não está mais na linha da ação
    area = acao[acao.index('<div class="material-qtd" id="qtd-area-1">') :]
    assert '<div class="quantidade">' in area
    confirmar = area[area.index("data-adicionar-confirmar") :]
    confirmar = confirmar[: confirmar.index("</button>")]
    assert "hx-post" in area and ">Adicionar" in confirmar
    cancelar = area[area.index("data-adicionar-cancelar") :]
    assert 'aria-label="Cancelar"' in cancelar[: cancelar.index(">")]


@pytest.mark.django_db
def test_resultado_da_avulsa_tambem_adiciona_em_dois_passos(client):
    montar_cenario()
    dar_saldo("000.000.900")
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    r = client.get(reverse("pedidos:avulsa_materiais"), {"q": "item"}).text
    assert '<div class="material-acao" data-adicionar>' in r
    assert "data-adicionar-abrir" in r and "data-adicionar-cancelar" in r
    # A busca da área interna continua mostrando o código.
    assert '<span class="mono">' in r


def test_painel_de_resultados_fica_no_fluxo_com_cinco_linhas_em_qualquer_tela():
    # O painel não flutua (absoluto): fica no fluxo, o cartão do passo cresce com ele e a altura é a
    # do cabeçalho e de 5 linhas, a mesma no computador, no tablet e no celular.
    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    assert "var LINHAS_VISIVEIS = 5;" in js and "function alturaDoPainel" in js
    assert 'trazerAoTopo(document.querySelector(".busca-principal"))' in js
    assert "estreito" not in js and "posicionarPainel" not in js and "caberNaTela" not in js
    css = open(finders.find("pedidos/css/pedidos.css"), encoding="utf-8").read()
    regra = css[css.index(".js .busca-painel {") :]
    regra = regra[: regra.index("}")]
    assert "position: relative" in regra and "absolute" not in regra and "vh" not in regra


def test_pedidos_js_abre_confirma_e_cancela_a_quantidade():
    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    for gancho in (
        "[data-adicionar-abrir]",
        "[data-adicionar-cancelar]",
        "[data-adicionar-confirmar]",
    ):
        assert gancho in js
    assert '"Confirmar"' in js and '"Atualizar"' in js and '"Escape"' in js
    assert '" no pedido"' in js  # selo "N no pedido" ao lado da informação


@pytest.mark.django_db
def test_quantidade_do_pedido_altera_em_dois_passos_no_formulario_publico(client):
    # No mesmo desenho do resultado da busca: a linha inteira é o botão (`material-abrir`) que
    # abre o − / + com "Confirmar" e ✕, o lápis só indica que clica e o "Remover" fica embaixo.
    # Sem JavaScript, o − / + fica à vista e vai com o envio do formulário.
    montar_cenario()
    r = client.post(
        reverse("pedidos:carrinho", args=["ab"]),
        {"adicionar": "016.005.010", "qtd-016.005.010": "3"},
    ).text
    linha = r[r.index('<li class="carrinho-linha') : r.index("</li>")]
    abrir = linha[linha.index("data-alterar-abrir") :]
    abrir = abrir[: abrir.index("</button>")]
    assert 'class="material-abrir"' in linha and "Alterar a quantidade de" in abrir
    assert 'aria-expanded="false"' in abrir and 'aria-controls="carrinho-qtd-area-1"' in abrir
    assert '<span class="material-mais" aria-hidden="true">' in linha  # o lápis
    acoes = linha[linha.index("data-alterar>") :]
    assert "data-alterar-abrir" not in acoes  # o botão da linha está fora da ação
    assert '<span class="carrinho-qtd-texto"><strong>3</strong> UN</span>' in acoes
    area = acoes[acoes.index('id="carrinho-qtd-area-1"') :]
    assert 'name="item_qtd"' in area and "data-alterar-confirmar" in area
    cancelar = area[area.index("data-alterar-cancelar") :]
    assert 'aria-label="Cancelar"' in cancelar[: cancelar.index(">")]
    assert "Remover" in acoes


@pytest.mark.django_db
def test_quantidade_do_pedido_na_avulsa_tambem_se_confirma(client):
    montar_cenario()
    dar_saldo("000.000.900")
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    r = client.post(
        reverse("pedidos:avulsa_carrinho"), {"adicionar": "000.000.900", "qtd-000.000.900": "1"}
    ).text
    linha = r[r.index('<li class="carrinho-linha') : r.index("</li>")]
    assert 'hx-trigger="confirmar-quantidade"' in linha and "data-alterar" in linha


def test_pedidos_js_altera_a_quantidade_do_pedido_so_ao_confirmar():
    js = open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8").read()
    for gancho in ("[data-alterar-abrir]", "[data-alterar-cancelar]", "[data-alterar-confirmar]"):
        assert gancho in js
    assert '"confirmar-quantidade"' in js
