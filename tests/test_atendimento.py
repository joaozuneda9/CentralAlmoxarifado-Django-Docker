import re
import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Material, Opcao
from pedidos.models import Atendimento, LinhaSaida, Pedido
from pedidos.regras import AB, AVULSA, LIMPEZA
from pedidos.servicos import confirmar_atendimento
from tests.cenario import (
    criar_pedido,
    em_paralelo,
    envio_ab,
    envio_limpeza,
    montar_cenario,
    registrar,
    saida,
    textos,
)

pytestmark = pytest.mark.django_db
HOJE = date(2026, 10, 9)
TUDO = {"023.001.002": "2", "008.001.002": "1,5"}


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="12345", password="x", first_name="Ana")


@pytest.fixture
def pedido():
    montar_cenario()
    return registrar(LIMPEZA, envio_limpeza()).pedido


def atender(pedido, usuario, dados=None, qtds=None, atendimento_id=None, nao_lancar=False):
    return confirmar_atendimento(
        pedido.id,
        atendimento_id or uuid.uuid4(),
        dados or saida(),
        TUDO if qtds is None else qtds,
        nao_lancar=nao_lancar,
        usuario=usuario,
        hoje=HOJE,
    )


def test_atendimento_grava_as_linhas_no_contrato_do_robo(pedido, usuario):
    r = atender(pedido, usuario, saida(data="2026-10-01"), {"023.001.002": "2", "008.001.002": "0"})
    assert r.ok and r.numero == "P-000001"
    linha = LinhaSaida.objects.get()
    assert (
        linha.data,
        linha.qtd,
        linha.codigo,
        linha.descricao,
        linha.recebedor,
        linha.centro_custo,
        linha.tipo_saida,
        linha.lote,
        linha.seq,
        linha.status,
    ) == (
        date(2026, 10, 1),
        Decimal("2"),
        "023.001.002",
        "DETERGENTE NEUTRO",
        "João",
        "ETA II",
        "BALCÃO",
        "P-000001",
        1,
        "PENDENTE",
    )
    p = Pedido.objects.get(pk=pedido.pk)
    assert [i.qtd_entregue for i in p.itens.all()] == [Decimal("2"), Decimal("0")]
    assert (p.situacao.chave, p.situacao_scpi.chave) == ("parcial", "aguardando")
    assert p.atendimento.atendido_por == usuario


def test_reenvio_igual_confirma_e_outro_atendimento_e_recusado(pedido, usuario):
    atendimento_id = uuid.uuid4()
    assert atender(pedido, usuario, atendimento_id=atendimento_id).ok
    assert atender(pedido, usuario, atendimento_id=atendimento_id).reenvio
    outro = atender(pedido, usuario)
    assert outro.ok is False
    assert outro.mensagem == "O pedido P-000001 já tem um atendimento registrado. Nada foi gravado."
    assert Atendimento.objects.count() == 1 and LinhaSaida.objects.count() == 2


def test_entrega_maior_que_a_pedida_e_aceita(pedido, usuario):
    r = atender(pedido, usuario, qtds={"023.001.002": "3", "008.001.002": "1"})
    assert r.ok, textos(r)
    assert LinhaSaida.objects.get(codigo="023.001.002").qtd == Decimal("3")


def test_entrega_acima_do_pedido_e_do_estoque_e_recusada(pedido, usuario):
    r = atender(pedido, usuario, qtds={"023.001.002": "101", "008.001.002": "1"})
    assert textos(r) == [
        "Entrega de 023.001.002 acima do máximo de 100 (o maior entre o pedido e o estoque)."
    ]
    assert not LinhaSaida.objects.exists()


def test_sem_saldo_o_teto_e_o_proprio_pedido(pedido, usuario):
    """Material sem saldo (ou fora do catálogo da avulsa) entrega o pedido, nunca mais que ele."""
    Material.objects.filter(codigo="023.001.002").update(estoque=Decimal(0))
    r = atender(pedido, usuario, qtds={"023.001.002": "3", "008.001.002": "1"})
    assert textos(r) == [
        "Entrega de 023.001.002 acima do máximo de 2 (o maior entre o pedido e o estoque)."
    ]
    assert atender(pedido, usuario, qtds={"023.001.002": "2", "008.001.002": "1"}).ok


def test_campo_da_entrega_leva_o_teto_para_a_tela(client, pedido, logado):
    html = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    for codigo in ("023.001.002", "008.001.002"):
        campo = re.search(rf'<input[^>]*name="entregue-{codigo}"[^>]*>', html).group(0)
        assert 'data-maximo="100"' in campo


def test_placa_fora_da_lista_e_recusada(pedido, usuario):
    r = atender(pedido, usuario, saida(placa="ZZZ0000"))
    assert textos(r) == ["A placa ZZZ0000 não está na lista de centros de custo."]
    assert not LinhaSaida.objects.exists() and not Atendimento.objects.exists()


def test_placa_de_outro_centro_e_recusada_e_a_do_proprio_centro_passa(pedido, usuario):
    r = atender(pedido, usuario, saida(placa="ABC1D23"))
    assert textos(r) == [
        'A placa ABC1D23 pertence ao centro de custo "PICKUP 01". Escolha esse centro ou '
        "limpe a placa."
    ]
    assert atender(pedido, usuario, saida(centro_custo="PICKUP 01", placa="abc-1d23")).ok
    assert set(LinhaSaida.objects.values_list("placa", flat=True)) == {"ABC1D23"}


def test_ab_aceita_fracao_na_entrega(usuario):
    """A equipe aceita fração em qualquer unidade, também nos pedidos do AB (spec 005)."""
    montar_cenario()
    p = registrar(AB, envio_ab()).pedido
    r = atender(p, usuario, qtds={"016.005.010": "1,5"})
    assert r.ok, textos(r)


def test_nao_lancar(pedido, usuario):
    r = atender(pedido, usuario, saida(obs="FORA DE ESTOQUE"))
    assert textos(r) == [
        'Para não lançar no SCPI, marque a opção "Não lançar no SCPI" (a observação não basta).'
    ]
    assert atender(pedido, usuario, saida(obs="FORA DE ESTOQUE"), nao_lancar=True).ok
    assert set(LinhaSaida.objects.values_list("status", flat=True)) == {"NAO_LANCAR"}
    assert Pedido.objects.get(pk=pedido.pk).situacao_scpi.rotulo == "Não será lançado"


def test_avulsa_nao_e_atendida(usuario):
    p = criar_pedido(origem=AVULSA)
    assert atender(p, usuario).mensagem == "Pedido não encontrado."


@pytest.mark.django_db(transaction=True)
def test_atendimentos_simultaneos_gravam_um():
    montar_cenario()
    usuario = get_user_model().objects.create_user(username="1", password="x")
    p = registrar(LIMPEZA, envio_limpeza()).pedido
    resultados = em_paralelo(lambda: atender(p, usuario), lambda: atender(p, usuario))
    assert sorted(r.ok for r in resultados) == [False, True]
    recusado = next(r for r in resultados if not r.ok)
    assert "já tem um atendimento registrado" in recusado.mensagem
    assert Atendimento.objects.count() == 1 and LinhaSaida.objects.count() == 2


@pytest.fixture
def logado(client, usuario):
    client.force_login(usuario)
    return usuario


def test_detalhe_exige_login_e_404(client, pedido, usuario):
    url = reverse("pedidos:detalhe", args=[pedido.numero])
    assert client.get(url).status_code == 302
    client.force_login(usuario)
    assert client.get(reverse("pedidos:detalhe", args=["P-999999"])).status_code == 404


def test_detalhe_mostra_formulario_so_quando_cabe(client, pedido, logado):
    r = client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
    assert "Confirmar atendimento" in r.text
    assert f'value="{timezone.localdate().isoformat()}"' in r.text
    assert "Quem recebe é o solicitante (Ana)" in r.text
    assert "DETERGENTE NEUTRO" in r.text
    avulsa = criar_pedido(origem=AVULSA, atendido=True)
    atendido = criar_pedido(atendido=True)
    for p in (avulsa, atendido):
        assert (
            "Confirmar e registrar saída"
            not in client.get(reverse("pedidos:detalhe", args=[p.numero])).text
        )


def dados_post(atendimento_id, **extra):
    dados = {
        "atendimento_id": str(atendimento_id),
        "data": timezone.localdate().isoformat(),
        "recebedor": "Carla",
        "centro_custo": "ETA II",
        "tipo": "BALCÃO",
        "placa": "",
        "obs": "",
        "entregue-023.001.002": "2",
        "entregue-008.001.002": "1,5",
    }
    dados.update(extra)
    return dados


def test_atender_pela_pagina(client, pedido, logado):
    url = reverse("pedidos:atender", args=[pedido.numero])
    detalhe = reverse("pedidos:detalhe", args=[pedido.numero])
    r = client.post(url, dados_post(uuid.uuid4(), **{"entregue-023.001.002": "-1"}))
    assert r.status_code == 200
    assert "Quantidade inválida" in r.text and 'value="Carla"' in r.text
    r = client.post(url, dados_post("x"))
    assert r.status_code == 302 and r.url == detalhe
    assert "Identificador do atendimento inválido. Recarregue a página." in client.get(detalhe).text
    r = client.post(url, dados_post(uuid.uuid4()))
    assert r.status_code == 302 and r.url == detalhe
    texto = client.get(detalhe).text
    assert "Atendimento do pedido P-000001 registrado." in texto
    assert "Carla" in texto


def test_painel_liga_o_numero_ao_detalhe(client, pedido, logado):
    texto = client.get(reverse("pedidos:painel")).text
    assert f'href="{reverse("pedidos:detalhe", args=[pedido.numero])}"' in texto


def test_detalhe_no_estilo_clean(client, pedido, logado):
    r = client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
    assert 'class="cartao recibo-bloco"' in r.text and '<dl class="dados">' in r.text
    assert 'class="grade-saida"' in r.text and 'class="campo-check campo-check-caixa"' in r.text
    assert re.search(r'<div class="tabela-rolagem">\s*<table class="tabela', r.text)


def test_quantidade_entregue_fica_na_tabela_e_vai_no_formulario(client, pedido, logado):
    texto = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert 'id="form-atendimento"' in texto and "data-entregar-tudo" in texto
    for codigo, qtd in TUDO.items():
        campo = re.search(rf'<input[^>]*name="entregue-{re.escape(codigo)}"[^>]*>', texto).group(0)
        assert 'form="form-atendimento"' in campo and 'class="entrega-campo"' in campo
        assert f'value="{qtd}"' in campo and f'data-pedido="{qtd}"' in campo
    assert 'class="entregue"' not in texto


def test_area_interna_mostra_a_unidade_do_scpi(client, pedido, logado):
    """No formulário de limpeza o café é "Pacote 500 g" (unidade exibida); na área interna, a
    unidade é a do SCPI, também dentro do campo da quantidade entregue."""
    assert pedido.itens.get(codigo="008.001.002").unidade == "Pacote 500 g"
    texto = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    linha = re.search(r"<tr>(?:(?!</tr>).)*?008\.001\.002.*?</tr>", texto, re.S).group(0)
    assert "Pacote 500 g" not in linha
    assert '<span class="recibo-un">KG</span>' in linha
    assert '<span class="entrega-un" aria-hidden="true">KG</span>' in linha
    assert 'aria-label="Quantidade entregue de CAFÉ 500 G, em KG"' in linha
    assert "data-entrega-confirmar" in linha and "data-entrega-alterar" in linha


def test_item_recusado_fica_marcado_na_tabela(client, pedido, logado):
    url = reverse("pedidos:atender", args=[pedido.numero])
    texto = client.post(url, dados_post(uuid.uuid4(), **{"entregue-023.001.002": "-1"})).text
    marcado = re.search(
        r'entrega-erro">(?:(?!<div class="entrega[ "]).)*?name="([^"]+)"', texto, re.S
    )
    assert marcado and marcado.group(1) == "entregue-023.001.002"
    assert 'value="-1"' in texto
    assert texto.count("entrega-erro") == 1


def test_recibo_sem_atendimento_pendente_nao_tem_campos(client, pedido, logado):
    client.post(reverse("pedidos:atender", args=[pedido.numero]), dados_post(uuid.uuid4()))
    texto = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert "entrega-campo" not in texto and "data-entregar-tudo" not in texto


def test_atendimento_sugere_o_centro_de_custo_do_destino(client, pedido, logado):
    texto = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert re.search(r'<option value="ETA II" selected>', texto)
    assert not re.search(r'<option value="[^"]+"[^>]*data-centro[^>]*selected', texto)


def test_atendimento_sugere_a_placa_do_destino(client, logado):
    montar_cenario()
    p = registrar(LIMPEZA, envio_limpeza(destino="PICKUP 01 — ABC1D23")).pedido
    texto = client.get(reverse("pedidos:detalhe", args=[p.numero])).text
    assert re.search(r'<option value="ABC1D23" data-centro="PICKUP 01" selected>', texto)
    assert re.search(r'<option value="PICKUP 01" selected>', texto)


def test_atendimento_fixa_o_tipo_em_balcao(client, pedido, logado):
    texto = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    campo = re.search(r'<select id="tipo"[^>]*>(.*?)</select>', texto, re.S)
    assert "data-travado" in campo.group(0)
    assert re.findall(r"<option[^>]*>", campo.group(1)) == ['<option value="BALCÃO" selected>']


def test_saida_avulsa_segue_com_o_tipo_livre(client, logado):
    montar_cenario()
    texto = client.get(reverse("pedidos:avulsa")).text
    assert "data-travado" not in re.search(r'<select id="tipo"[^>]*>', texto).group(0)


def _passos(client, p):
    texto = client.get(reverse("pedidos:detalhe", args=[p.numero])).text
    return re.findall(
        r"<li>(.*?)</li>",
        re.search(r'<ul class="recibo-passos[^>]*>(.*?)</ul>', texto, re.S).group(1),
    )


def test_cartao_de_situacao_diz_o_que_fazer_em_cada_estagio(client, logado):
    montar_cenario()
    aguardando = criar_pedido()
    assert _passos(client, aguardando) == [
        "Confira e preencha as quantidades separadas na tabela de materiais.",
        "Preencha os dados da saída e confirme o atendimento no formulário abaixo.",
    ]
    atendido = criar_pedido(atendido=True)
    assert _passos(client, atendido) == ["Imprima o recibo e colha a assinatura de quem recebeu."]
    parcial = criar_pedido(atendido=True, itens=(("023.001.002", "2"),), entregues=("1",))
    assert _passos(client, parcial)[0].startswith("Algum material saiu em quantidade menor")
    assert _passos(client, parcial)[1].startswith("Imprima o recibo")


def test_cartao_de_situacao_com_recibo_impresso(client, logado):
    montar_cenario()
    p = criar_pedido(atendido=True)
    Atendimento.objects.filter(pedido=p).update(recibo_impresso_em=timezone.now())
    assert _passos(client, p) == ["Recibo já impresso. Não há mais nada a fazer neste pedido."]


def test_cartao_de_situacao_tem_o_mesmo_destaque_em_todo_estado(client, logado):
    montar_cenario()

    def destacado(p):
        return (
            "recibo-quadro-destaque" in client.get(reverse("pedidos:detalhe", args=[p.numero])).text
        )

    assert destacado(criar_pedido())
    atendido = criar_pedido(atendido=True)
    assert destacado(atendido)
    Atendimento.objects.filter(pedido=atendido).update(recibo_impresso_em=timezone.now())
    assert destacado(atendido)


def test_cartao_de_situacao_e_subtitulo_h3_e_o_do_scpi_saiu(client, pedido, logado):
    texto = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert '<h3 class="rotulo-secao">Situação do pedido</h3>' in texto
    assert "Integração com o SCPI" not in texto
    # O estado no SCPI fica no campo da requisição.
    assert (
        '<dt>Requisição SCPI</dt><dd><span class="texto-secundario">Aguarda o atendimento' in texto
    )


def test_campo_de_quantidade_usa_a_silhueta_definida_uma_vez(client, pedido, logado):
    texto = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    for forma in ("entrega-corpo", "entrega-barra-topo", "entrega-barra-base"):
        assert texto.count(f'id="{forma}"') == 1
        assert texto.count(f'href="#{forma}"') == len(TUDO)
    # Depois do atendimento não há campos, e a silhueta não vai na página.
    client.post(reverse("pedidos:atender", args=[pedido.numero]), dados_post(uuid.uuid4()))
    atendido = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert "entrega-corpo" not in atendido


def test_tabela_de_materiais_nao_mostra_grupo_nem_subgrupo(client, pedido, logado):
    texto = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    celulas = re.findall(r"<td>(<span class=\"mono recibo-codigo\">.*?)</td>", texto, re.S)
    assert len(celulas) == len(TUDO)
    for celula in celulas:
        # O botão "Trocar" fica na célula do material, mas não é texto do cadastro.
        celula = re.sub(r" <button[^>]*data-trocar=.*?</button>", "", celula, flags=re.S)
        assert re.fullmatch(
            r"<span class=\"mono recibo-codigo\">[^<]+</span> <strong>[^<]+</strong>", celula
        )


def test_atendimento_grava_balcao_mesmo_com_outro_tipo_no_post(client, pedido, logado):
    url = reverse("pedidos:atender", args=[pedido.numero])
    r = client.post(url, dados_post(uuid.uuid4(), tipo="ENTREGA"))
    assert r.status_code == 302
    assert {
        linha.tipo_saida for linha in LinhaSaida.objects.filter(atendimento__pedido=pedido)
    } == {"BALCÃO"}


def test_sem_balcao_nas_opcoes_o_tipo_enviado_vale(client, pedido, logado):
    Opcao.objects.create(lista=Opcao.Lista.TIPO_SAIDA, valor="ENTREGA")
    texto = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert "data-travado" not in re.search(r'<select id="tipo"[^>]*>', texto).group(0)
    url = reverse("pedidos:atender", args=[pedido.numero])
    assert client.post(url, dados_post(uuid.uuid4(), tipo="ENTREGA")).status_code == 302
    assert {
        linha.tipo_saida for linha in LinhaSaida.objects.filter(atendimento__pedido=pedido)
    } == {"ENTREGA"}
