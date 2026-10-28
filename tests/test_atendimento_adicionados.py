"""Atendimento com material acrescentado pelo almoxarifado (troca ou acréscimo)."""

import re
import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db.models import RestrictedError
from django.urls import reverse

from catalogo.models import Material
from pedidos.models import Atendimento, ItemPedido, LinhaSaida, Pedido
from pedidos.regras import AB, AVULSA, LIMPEZA, Adicionado
from pedidos.servicos import catalogo_de, centros, confirmar_atendimento, registrar_pedido
from scpi.requisicoes import selecionar
from tests.cenario import (
    criar_pedido,
    dar_saldo,
    envio_ab,
    envio_limpeza,
    montar_cenario,
    registrar,
    saida,
    textos,
)
from tests.test_atendimento import dados_post

pytestmark = pytest.mark.django_db
HOJE = date(2026, 10, 9)
TUDO = {"023.001.002": "2", "008.001.002": "1,5"}


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="12345", password="x", first_name="Ana")


@pytest.fixture
def pedido():
    montar_cenario()
    # A saída avulsa só lista material com saldo: os do pedido e o primeiro livre vêm zerados.
    dar_saldo("023.001.002", "008.001.002", "013.006.001")
    return registrar(LIMPEZA, envio_limpeza()).pedido


def livres(pedido):
    """Materiais da saída avulsa que não estão no pedido, na ordem do catálogo."""
    no_pedido = {i.codigo for i in pedido.itens.all()}
    return [i for i in catalogo_de(AVULSA) if i.codigo not in no_pedido]


def atender(pedido, usuario, qtds, adicionados=(), atendimento_id=None):
    return confirmar_atendimento(
        pedido.id,
        atendimento_id or uuid.uuid4(),
        saida(),
        qtds,
        nao_lancar=False,
        usuario=usuario,
        hoje=HOJE,
        adicionados=adicionados,
    )


def trocar(pedido, usuario, **kw):
    x = livres(pedido)[0].codigo
    qtds = {"023.001.002": "2", "008.001.002": "0", x: "1"}
    return x, atender(pedido, usuario, qtds, [Adicionado(x, "008.001.002")], **kw)


def test_troca_grava_o_acrescentado_e_o_trocado_com_zero(pedido, usuario):
    x, r = trocar(pedido, usuario)
    assert r.ok, textos(r)
    item = ItemPedido.objects.get(pedido=pedido, codigo=x)
    material = Material.objects.get(codigo=x)
    assert item.origem == ItemPedido.Origem.ALMOXARIFADO
    assert item.qtd_pedida is None and item.qtd_entregue == Decimal(1)
    assert item.no_lugar_de.codigo == "008.001.002"
    assert item.adicionado_por == usuario
    assert (item.material, item.unidade, item.grupo, item.subgrupo) == (
        material.nome,
        material.unidade,
        material.grupo,
        material.subgrupo,
    )
    cafe = ItemPedido.objects.get(pedido=pedido, codigo="008.001.002")
    assert cafe.qtd_entregue == 0 and cafe.origem == ItemPedido.Origem.PEDIDO
    linhas = list(LinhaSaida.objects.order_by("seq").values_list("seq", "codigo", "qtd"))
    assert linhas == [(1, "023.001.002", Decimal(2)), (2, x, Decimal(1))]
    assert Pedido.objects.get(pk=pedido.pk).situacao.chave == "atendido"


def test_item_trocado_entregue_e_recusado(pedido, usuario):
    """O item pedido trocado fica com 0 até a troca ser desfeita: entregá-lo junto com o que o
    substitui seria a troca e o original ao mesmo tempo."""
    x = livres(pedido)[0].codigo
    qtds = {"023.001.002": "2", "008.001.002": "1,5", x: "1"}
    r = atender(pedido, usuario, qtds, [Adicionado(x, "008.001.002")])
    assert not r.ok
    assert [(e.codigo, e.texto) for e in r.erros] == [
        (
            "008.001.002",
            "CAFÉ 500 G foi trocado por outro material: a quantidade entregue dele fica 0. "
            "Para entregá-lo, desfaça a troca.",
        )
    ]
    assert not Atendimento.objects.exists() and not LinhaSaida.objects.exists()


def test_acrescimo_sem_vinculo(pedido, usuario):
    x = livres(pedido)[0].codigo
    r = atender(pedido, usuario, {**TUDO, x: "3"}, [Adicionado(x)])
    assert r.ok, textos(r)
    item = ItemPedido.objects.get(pedido=pedido, codigo=x)
    assert item.no_lugar_de is None and item.qtd_entregue == Decimal(3)
    assert LinhaSaida.objects.count() == 3


def _fora_do_catalogo(x, y, nomes):
    adic = [Adicionado("999.999.999")]
    return adic, {**TUDO, "999.999.999": "1"}, "999.999.999", None


def _duplicado(x, y, nomes):
    Material.objects.filter(codigo=x).update(duplicado=True)
    return [Adicionado(x)], {**TUDO, x: "1"}, x, f"Material {x} está com cadastro duplicado."


def _repetido_do_pedido(x, y, nomes):
    return (
        [Adicionado("023.001.002")],
        TUDO,
        "023.001.002",
        "DETERGENTE NEUTRO (023.001.002) já está no pedido: altere a quantidade nele.",
    )


def _repetido_entre_acrescentados(x, y, nomes):
    return (
        [Adicionado(x), Adicionado(x)],
        {**TUDO, x: "1"},
        x,
        f"{nomes[x]} ({x}) já está no pedido: altere a quantidade nele.",
    )


def _trocado_duas_vezes(x, y, nomes):
    return (
        [Adicionado(x, "008.001.002"), Adicionado(y, "008.001.002")],
        {"023.001.002": "2", "008.001.002": "0", x: "1", y: "1"},
        "008.001.002",
        "CAFÉ 500 G já foi trocado por outro material.",
    )


def _troca_por_acrescentado(x, y, nomes):
    return (
        [Adicionado(x), Adicionado(y, x)],
        {**TUDO, x: "1", y: "1"},
        y,
        f"Material de troca inválido para {nomes[y]}.",
    )


def _quantidade_zero(x, y, nomes):
    return [Adicionado(x)], {**TUDO, x: "0"}, x, f"Informe a quantidade de {nomes[x]}."


def _quantidade_texto(x, y, nomes):
    return [Adicionado(x)], {**TUDO, x: "abc"}, x, f"Quantidade inválida para {x}."


def _quantidade_ausente(x, y, nomes):
    return [Adicionado(x)], TUDO, x, f"Informe a quantidade de {nomes[x]}."


def _limpeza_com_ponto(x, y, nomes):
    return [Adicionado(x)], {**TUDO, x: "1.5"}, x, f"Quantidade inválida para {x}."


@pytest.mark.parametrize(
    "caso",
    [
        _fora_do_catalogo,
        _duplicado,
        _repetido_do_pedido,
        _repetido_entre_acrescentados,
        _trocado_duas_vezes,
        _troca_por_acrescentado,
        _quantidade_zero,
        _quantidade_texto,
        _quantidade_ausente,
        _limpeza_com_ponto,
    ],
)
def test_recusas_nao_gravam_nada(pedido, usuario, caso):
    x, y = (i.codigo for i in livres(pedido)[:2])
    nomes = {i.codigo: i.nome for i in catalogo_de(AVULSA)}
    adicionados, qtds, codigo, texto = caso(x, y, nomes)
    r = atender(pedido, usuario, qtds, adicionados)
    assert r.ok is False
    assert [e.codigo for e in r.erros] == [codigo]
    if texto is not None:
        assert textos(r) == [texto]
    assert not Atendimento.objects.exists() and not LinhaSaida.objects.exists()
    assert not ItemPedido.objects.filter(origem=ItemPedido.Origem.ALMOXARIFADO).exists()


def test_fora_do_catalogo_usa_a_mensagem_do_cadastro(pedido, usuario):
    r = atender(pedido, usuario, {**TUDO, "999.999.999": "1"}, [Adicionado("999.999.999")])
    assert textos(r) == ["Material 999.999.999 não encontrado no cadastro."]


def test_ab_acrescentado_aceita_fracao(usuario):
    """A equipe aceita fração em qualquer unidade, também nos pedidos do AB (spec 005)."""
    montar_cenario()
    p = registrar(AB, envio_ab()).pedido
    x = livres(p)[0].codigo
    r = atender(p, usuario, {"016.005.010": "3", x: "1,5"}, [Adicionado(x)])
    assert r.ok, textos(r)
    assert ItemPedido.objects.get(pedido=p, codigo=x).qtd_entregue == Decimal("1.5")


def test_so_acrescentado_entregue_basta(pedido, usuario):
    """Troca de tudo: os pedidos zerados e o acrescentado é o único material entregue."""
    x = livres(pedido)[0].codigo
    qtds = {"023.001.002": "0", "008.001.002": "0", x: "1"}
    r = atender(pedido, usuario, qtds, [Adicionado(x, "023.001.002")])
    assert r.ok, textos(r)
    assert list(LinhaSaida.objects.values_list("codigo", flat=True)) == [x]


def test_lote_com_acrescentado_vira_uma_requisicao(pedido, usuario):
    x, r = trocar(pedido, usuario)
    assert r.ok
    sel = selecionar(list(LinhaSaida.objects.all()), centros())
    (req,) = sel.requisicoes
    assert req.lote == pedido.numero and req.erro == ""
    assert [i.cadpro for i in req.itens] == ["023.001.002", x]


def test_reenvio_com_os_mesmos_acrescentados_confirma(pedido, usuario):
    x, y = (i.codigo for i in livres(pedido)[:2])
    atendimento_id = uuid.uuid4()
    qtds = {"023.001.002": "2", "008.001.002": "0", x: "1", y: "2"}
    primeiro = [Adicionado(x, "008.001.002"), Adicionado(y)]
    assert atender(pedido, usuario, qtds, primeiro, atendimento_id).ok
    de_novo = atender(pedido, usuario, qtds, list(reversed(primeiro)), atendimento_id)
    assert de_novo.ok and de_novo.reenvio is True
    outro = atender(pedido, usuario, {**qtds, y: "3"}, primeiro, atendimento_id)
    assert outro.ok is False
    assert outro.mensagem == "O pedido P-000001 já tem um atendimento registrado. Nada foi gravado."
    sem_troca = atender(pedido, usuario, qtds, [Adicionado(x), Adicionado(y)], atendimento_id)
    assert sem_troca.ok is False
    assert ItemPedido.objects.filter(origem=ItemPedido.Origem.ALMOXARIFADO).count() == 2
    assert LinhaSaida.objects.count() == 3


# --- Views: busca, linha do acrescentado e envio ---------------------------------------------


@pytest.fixture
def logado(client, usuario):
    client.force_login(usuario)
    return usuario


def _url(nome, pedido):
    return reverse(f"pedidos:{nome}", args=[pedido.numero])


def test_busca_do_atendimento_usa_o_catalogo_da_avulsa_e_mira_os_acrescentados(
    client, pedido, logado
):
    r = client.get(_url("atendimento_materiais", pedido), {"q": "café"})
    assert r.status_code == 200
    assert "CAFÉ 500 G" in r.text
    assert f'hx-post="{_url("atendimento_adicionar", pedido)}"' in r.text
    assert 'hx-target="#adicionados"' in r.text and 'hx-swap="beforeend"' in r.text
    # Na troca, a quantidade já vem com a pedida do item trocado.
    x = livres(pedido)[0]
    r = client.get(
        _url("atendimento_materiais", pedido), {"q": x.nome, "no_lugar_de": "023.001.002"}
    )
    assert re.search(rf'name="qtd-{re.escape(x.codigo)}" value="2"', r.text)
    r = client.get(_url("atendimento_materiais", pedido), {"q": x.nome})
    assert re.search(rf'name="qtd-{re.escape(x.codigo)}" value="1"', r.text)


def _botao_confirmar(texto):
    return re.search(r"<button[^>]*data-adicionar-confirmar[^>]*>[^<]*</button>", texto).group(0)


def test_busca_da_troca_diz_trocar_e_a_do_acrescimo_diz_adicionar(client, pedido, logado):
    x = livres(pedido)[0]
    url = _url("atendimento_materiais", pedido)
    troca = client.get(url, {"q": x.nome, "no_lugar_de": "023.001.002"}).text
    botao = _botao_confirmar(troca)
    assert botao.endswith(">Trocar</button>") and "botao-primario" in botao
    assert f'aria-label="Trocar DETERGENTE NEUTRO por {x.nome}"' in botao
    botao = _botao_confirmar(client.get(url, {"q": x.nome}).text)
    assert botao.endswith(">Adicionar</button>") and "botao-secundario" in botao
    assert f'aria-label="Adicionar {x.nome}"' in botao
    # Código que não é item pedido deste pedido: continua "Adicionar".
    botao = _botao_confirmar(client.get(url, {"q": x.nome, "no_lugar_de": x.codigo}).text)
    assert botao.endswith(">Adicionar</button>")


def test_busca_publica_e_avulsa_continuam_mirando_o_carrinho(client, pedido, logado):
    for url in (
        reverse("pedidos:materiais", args=["limpeza"]),
        reverse("pedidos:avulsa_materiais"),
    ):
        texto = client.get(url, {"q": "a"}).text
        assert 'hx-target="#carrinho"' in texto and 'hx-swap="innerHTML"' in texto
        assert "#adicionados" not in texto


def test_adicionar_devolve_a_linha_do_acrescentado(client, pedido, logado):
    x = livres(pedido)[0]
    c = x.codigo
    r = client.post(
        _url("atendimento_adicionar", pedido),
        {"adicionar": c, f"qtd-{c}": "3", "no_lugar_de": "008.001.002"},
    )
    assert r.status_code == 200
    assert "<tr" in r.text and f'data-adicionado="{c}"' in r.text
    assert 'data-no-lugar-de="008.001.002"' in r.text
    assert f'name="adicionado" value="{c}"' in r.text
    assert re.search(rf'name="no-lugar-de-{re.escape(c)}" value="008.001.002"', r.text)
    campo = re.search(rf'<input[^>]*name="entregue-{re.escape(c)}"[^>]*>', r.text).group(0)
    assert 'form="form-atendimento"' in campo and 'value="3"' in campo
    assert 'data-pedido=""' in campo
    assert "No lugar de CAFÉ 500 G" in r.text and "data-desfazer-troca" in r.text
    assert x.nome in r.text
    url = _url("atendimento_adicionar", pedido)
    sem_troca = client.post(url, {"adicionar": c, f"qtd-{c}": "1"})
    assert 'data-no-lugar-de=""' in sem_troca.text
    assert "data-remover-adicionado" in sem_troca.text
    assert "No lugar de" not in sem_troca.text


def _recusa(r):
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#adicionar-erro"
    assert r.headers["HX-Reswap"] == "innerHTML"
    assert "<tr" not in r.text
    return r.text.strip()


def test_adicionar_recusa_material_do_pedido_e_vinculos_invalidos(client, pedido, logado):
    url = _url("atendimento_adicionar", pedido)
    x, y = livres(pedido)[:2]
    r = client.post(url, {"adicionar": "023.001.002", "qtd-023.001.002": "1"})
    assert _recusa(r) == (
        "DETERGENTE NEUTRO (023.001.002) já está no pedido: altere a quantidade nele."
    )
    # Repetido entre os acrescentados já na página.
    r = client.post(url, {"adicionar": x.codigo, f"qtd-{x.codigo}": "1", "adicionado": x.codigo})
    assert _recusa(r) == f"{x.nome} ({x.codigo}) já está no pedido: altere a quantidade nele."
    # Item pedido já trocado por outro acrescentado.
    r = client.post(
        url,
        {
            "adicionar": y.codigo,
            f"qtd-{y.codigo}": "1",
            "no_lugar_de": "008.001.002",
            "adicionado": x.codigo,
            f"no-lugar-de-{x.codigo}": "008.001.002",
        },
    )
    assert _recusa(r) == "CAFÉ 500 G já foi trocado por outro material."
    r = client.post(url, {"adicionar": y.codigo, f"qtd-{y.codigo}": "1", "no_lugar_de": x.codigo})
    assert _recusa(r) == f"Material de troca inválido para {y.nome}."
    r = client.post(url, {"adicionar": "999.999.999", "qtd-999.999.999": "1"})
    assert _recusa(r) == "Material não encontrado no catálogo."
    r = client.post(url, {"adicionar": x.codigo, f"qtd-{x.codigo}": "0"})
    assert _recusa(r) == (
        "Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5)."
    )
    Material.objects.filter(codigo=x.codigo).update(duplicado=True)
    r = client.post(url, {"adicionar": x.codigo, f"qtd-{x.codigo}": "1"})
    assert "não pode ser adicionado" in _recusa(r)


def test_adicionar_e_busca_so_em_atendimento_aberto(client, pedido, logado):
    # Pedido atendido ainda se edita (e acrescenta) até o lançamento; lançado, não.
    x = livres(pedido)[0].codigo
    lancado = criar_pedido(atendido=True, linhas=[("LANCADA", "000001/26")])
    for p in (lancado, criar_pedido(origem=AVULSA, atendido=True)):
        assert client.get(_url("atendimento_materiais", p), {"q": "a"}).status_code == 404
        r = client.post(_url("atendimento_adicionar", p), {"adicionar": x, f"qtd-{x}": "1"})
        assert r.status_code == 404
    assert client.get(_url("atendimento_adicionar", pedido)).status_code == 405


def test_views_dos_acrescentados_exigem_login(client, pedido):
    r = client.get(_url("atendimento_materiais", pedido))
    assert r.status_code == 302 and "/painel/entrar/" in r.url
    r = client.post(_url("atendimento_adicionar", pedido))
    assert r.status_code == 302 and "/painel/entrar/" in r.url


def test_atender_pela_pagina_com_acrescentado(client, pedido, logado):
    x = livres(pedido)[0].codigo
    extra = {
        "adicionado": x,
        f"no-lugar-de-{x}": "008.001.002",
        f"entregue-{x}": "1",
        "entregue-008.001.002": "0",
    }
    r = client.post(_url("atender", pedido), dados_post(uuid.uuid4(), **extra))
    assert r.status_code == 302 and r.url == _url("detalhe", pedido)
    item = ItemPedido.objects.get(pedido=pedido, codigo=x)
    assert item.no_lugar_de.codigo == "008.001.002" and item.qtd_entregue == Decimal(1)


def test_atender_recusado_redesenha_o_acrescentado_com_o_erro(client, pedido, logado):
    c = livres(pedido)[0].codigo
    extra = {
        "adicionado": c,
        f"no-lugar-de-{c}": "008.001.002",
        f"entregue-{c}": "abc",
        "entregue-008.001.002": "0",  # o trocado fica com 0, como a tela deixa
    }
    r = client.post(_url("atender", pedido), dados_post(uuid.uuid4(), **extra))
    assert r.status_code == 200
    assert not ItemPedido.objects.filter(origem=ItemPedido.Origem.ALMOXARIFADO).exists()
    corpo = re.search(r'<tbody id="adicionados">(.*?)</tbody>', r.text, re.S).group(1)
    assert f'data-adicionado="{c}"' in corpo and "No lugar de CAFÉ 500 G" in corpo
    assert f'name="adicionado" value="{c}"' in corpo
    assert 'class="entrega entrega-erro"' in corpo and 'value="abc"' in corpo
    assert f"Quantidade inválida para {c}." in r.text
    assert r.text.count("entrega-erro") == 1


def test_pagina_do_atendimento_tem_o_grupo_e_o_destino_do_erro(client, pedido, logado):
    texto = client.get(_url("detalhe", pedido)).text
    corpo = re.search(r'<tbody id="adicionados">(.*?)</tbody>', texto, re.S).group(1)
    # Só a linha de grupo (o CSS a esconde enquanto não há acrescentado).
    assert "data-adicionado" not in corpo
    assert 'class="recibo-grupo"' in corpo
    assert '<span class="selo selo-info">Adicionado pelo almoxarifado</span>' in corpo
    assert 'id="adicionar-erro"' in texto


# --- Recibo e tabela do atendimento -----------------------------------------------------------


def _recibo(texto):
    """Só o recibo (a casca da página mostra o usuário logado)."""
    padrao = r'<div class="recibo">(.*?)<div class="assinaturas">'
    return re.search(padrao, texto, re.S).group(1)


def test_tabela_pendente_tem_trocar_e_adicionar_escondidos(client, pedido, logado):
    Pedido.objects.filter(pk=pedido.pk).update(obs="mandar também 2 copos")
    texto = client.get(_url("detalhe", pedido)).text
    for codigo, nome in (("023.001.002", "DETERGENTE NEUTRO"), ("008.001.002", "CAFÉ 500 G")):
        botao = re.search(rf'<button[^>]*data-trocar="{re.escape(codigo)}"[^>]*>', texto).group(0)
        assert " hidden" in botao and 'type="button"' in botao and "nao-imprimir" in botao
        assert f'aria-label="Trocar {nome}"' in botao
    adicionar = re.search(r"<button[^>]*data-adicionar-material[^>]*>", texto).group(0)
    assert " hidden" in adicionar and 'type="button"' in adicionar
    assert "para o que veio na observação ou um a mais, sem trocar nenhum" in texto
    # A observação do pedido fica à vista logo acima do "Adicionar material".
    trecho = texto[texto.index("</table>") : texto.index("data-adicionar-material")]
    assert "mandar também 2 copos" in trecho


def test_tabela_pendente_sem_observacao_nao_a_repete(client, pedido, logado):
    texto = client.get(_url("detalhe", pedido)).text
    trecho = texto[texto.index("</table>") : texto.index("data-adicionar-material")]
    assert "Observação do pedido" not in trecho


def test_painel_de_busca_do_atendimento(client, pedido, logado):
    texto = client.get(_url("detalhe", pedido)).text
    painel = re.search(r"<form[^>]*data-atendimento-painel[^>]*>(.*?)</form>", texto, re.S)
    abertura = painel.group(0)[: painel.group(0).index(">") + 1]
    assert 'class="atendimento-painel' in abertura and " hidden" in abertura
    corpo = painel.group(1)
    assert 'name="csrfmiddlewaretoken"' in corpo
    assert "data-painel-titulo" in corpo
    assert "ele fica com 0 entregue, e o pedido original continua registrado." in corpo
    assert re.search(r'<input type="hidden" name="no_lugar_de"', corpo)
    assert f'hx-get="{_url("atendimento_materiais", pedido)}"' in corpo
    assert 'hx-target="#atendimento-resultados"' in corpo
    assert 'id="atendimento-resultados"' in corpo
    assert "data-painel-desistir" in corpo
    assert re.search(r'<label[^>]*for="atendimento-q"[^>]*>Material</label>', corpo)


def test_tabela_pendente_tem_contagem_e_anuncio_para_o_javascript(client, pedido, logado):
    texto = client.get(_url("detalhe", pedido)).text
    # O pedidos.js atualiza a contagem e anuncia troca, acréscimo e remoção numa região só.
    titulo = r'<h2 class="recibo-subtitulo" data-contagem-materiais>Materiais \(2\)</h2>'
    assert re.search(titulo, texto)
    anuncio = re.search(r"<p[^>]*data-anuncio-atendimento[^>]*>", texto).group(0)
    assert 'role="status"' in anuncio and 'aria-atomic="true"' in anuncio
    assert 'class="visually-hidden"' in anuncio


def test_pedido_atendido_nao_tem_trocar_nem_painel(client, pedido, logado):
    client.post(_url("atender", pedido), dados_post(uuid.uuid4()))
    texto = client.get(_url("detalhe", pedido)).text
    for marca in (
        "data-trocar",
        "data-adicionar-material",
        "data-atendimento-painel",
        "data-contagem-materiais",
        "data-anuncio-atendimento",
    ):
        assert marca not in texto


def test_resultados_do_atendimento_incluem_os_acrescentados(client, pedido, logado):
    inclusao = (
        'hx-include="[name=adicionado], [name^=no-lugar-de-], '
        '[data-atendimento-painel] [name=no_lugar_de]"'
    )
    r = client.get(_url("atendimento_materiais", pedido), {"q": "a"})
    assert inclusao in r.text
    for url in (
        reverse("pedidos:materiais", args=["limpeza"]),
        reverse("pedidos:avulsa_materiais"),
    ):
        assert 'hx-include="[name=adicionado]' not in client.get(url, {"q": "a"}).text


@pytest.fixture
def atendente():
    return get_user_model().objects.create_user(
        username="77777", password="x", first_name="Zuleica", last_name="Prado"
    )


def test_recibo_atendido_com_troca_separa_os_grupos(client, pedido, logado, atendente):
    x, r = trocar(pedido, atendente)
    assert r.ok, textos(r)
    nome_x = ItemPedido.objects.get(pedido=pedido, codigo=x).material
    for url in (_url("detalhe", pedido),):
        recibo = _recibo(client.get(url).text)
        assert "Materiais (3)" in recibo
        grupos = re.findall(r'<tr class="recibo-grupo">(.*?)</tr>', recibo, re.S)
        assert len(grupos) == 2
        assert "Pedido pelo solicitante" in grupos[0]
        assert "Adicionado pelo almoxarifado" in grupos[1]
        assert f"Trocado por {nome_x}" in recibo
        assert "No lugar de CAFÉ 500 G" in recibo
        padrao = rf'<tr>\s*<td><span class="mono recibo-codigo">{re.escape(x)}</span>.*?</tr>'
        linha = re.search(padrao, recibo, re.S).group(0)
        pedido_col = re.search(r'<td class="recibo-pedido">(.*?)</td>', linha, re.S).group(1)
        assert pedido_col.strip() == "—"
        for quem in ("Zuleica", "Prado", "77777"):
            assert quem not in recibo


def test_recibo_atendido_sem_acrescentado_fica_como_antes(client, pedido, logado):
    client.post(_url("atender", pedido), dados_post(uuid.uuid4()))
    recibo = _recibo(client.get(_url("detalhe", pedido)).text)
    assert "Materiais (2)" in recibo
    assert "recibo-grupo" not in recibo and "Trocado por" not in recibo


def test_recibo_com_acrescimo_sem_troca_nao_tem_nota(client, pedido, logado, atendente):
    x = livres(pedido)[0].codigo
    r = atender(pedido, atendente, {**TUDO, x: "3"}, [Adicionado(x)])
    assert r.ok, textos(r)
    recibo = _recibo(client.get(_url("detalhe", pedido)).text)
    assert recibo.count('class="recibo-grupo"') == 2
    assert "No lugar de" not in recibo and "Trocado por" not in recibo


# --- Exclusão com troca e as receitas do VIRADA.md -------------------------------------------


def test_pedido_com_troca_pode_ser_apagado(pedido, usuario):
    _, r = trocar(pedido, usuario)
    assert r.ok, textos(r)
    Pedido.objects.filter(numero__in=[pedido.numero]).delete()
    assert not ItemPedido.objects.exists() and not Atendimento.objects.exists()
    _, r = trocar(registrar(LIMPEZA, envio_limpeza()).pedido, usuario)
    assert r.ok, textos(r)
    Pedido.objects.all().delete()
    assert not Pedido.objects.exists()
    # Os itens todos de uma vez (trocado e acrescentado juntos) também.
    outro = registrar(LIMPEZA, envio_limpeza()).pedido
    _, r = trocar(outro, usuario)
    assert r.ok, textos(r)
    ItemPedido.objects.filter(pedido=outro).delete()
    assert not ItemPedido.objects.exists()


def test_item_pedido_trocado_nao_pode_ser_apagado_sozinho(pedido, usuario):
    x, r = trocar(pedido, usuario)
    assert r.ok, textos(r)
    with pytest.raises(RestrictedError):
        ItemPedido.objects.get(pedido=pedido, codigo="008.001.002").delete()
    with pytest.raises(RestrictedError):
        ItemPedido.objects.filter(pedido=pedido, origem=ItemPedido.Origem.PEDIDO).delete()
    assert ItemPedido.objects.get(codigo=x).no_lugar_de.codigo == "008.001.002"


def test_detalhe_pendente_com_acrescentado_sobrando_abre(client, pedido, logado):
    _, r = trocar(pedido, logado)
    assert r.ok, textos(r)
    # Desfeito só o atendimento (a receita antiga do VIRADA.md): o acrescentado sobra.
    Atendimento.objects.filter(pedido=pedido).delete()
    ItemPedido.objects.filter(pedido=pedido).update(qtd_entregue=None)
    assert client.get(_url("detalhe", pedido)).status_code == 200


def test_receita_do_virada_desfaz_atendimento_com_troca(client, pedido, logado):
    x, r = trocar(pedido, logado)
    assert r.ok, textos(r)
    n = [pedido.numero]
    ItemPedido.objects.filter(pedido__numero__in=n, origem="ALMOXARIFADO").delete()
    Atendimento.objects.filter(pedido__numero__in=n).delete()
    ItemPedido.objects.filter(pedido__numero__in=n).update(qtd_entregue=None)
    assert client.get(_url("detalhe", pedido)).status_code == 200
    x, r = trocar(pedido, logado)
    assert r.ok, textos(r)


def test_reenvio_publico_depois_do_atendimento_com_acrescentado_confirma(pedido, usuario):
    x = livres(pedido)[0].codigo
    r = atender(pedido, usuario, {**TUDO, x: "1"}, [Adicionado(x)])
    assert r.ok, textos(r)
    de_novo = registrar_pedido(LIMPEZA, pedido.id, envio_limpeza())
    assert de_novo.ok and de_novo.reenvio is True and de_novo.numero == pedido.numero


def test_so_a_busca_do_atendimento_descarta_o_duplo_clique(client, pedido, logado):
    x = livres(pedido)[0]
    url = _url("atendimento_materiais", pedido)
    for params in ({"q": x.nome}, {"q": x.nome, "no_lugar_de": "023.001.002"}):
        assert 'hx-sync="drop"' in _botao_confirmar(client.get(url, params).text)
    for url in (
        reverse("pedidos:materiais", args=["limpeza"]),
        reverse("pedidos:avulsa_materiais"),
    ):
        texto = client.get(url, {"q": "a"}).text
        assert "data-adicionar-confirmar" in texto and "hx-sync" not in texto


def test_busca_do_atendimento_continua_em_um_passo(client, pedido, logado):
    # O painel do atendimento já é a escolha: cada resultado adiciona (ou troca) direto.
    texto = client.get(_url("atendimento_materiais", pedido), {"q": livres(pedido)[0].nome}).text
    assert "data-adicionar-confirmar" in texto
    assert "data-adicionar>" not in texto and "data-adicionar-abrir" not in texto
