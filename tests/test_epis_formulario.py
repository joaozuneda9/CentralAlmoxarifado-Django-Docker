"""Formulário público de EPIs (spec 008, US1, FR-001 a FR-010): pedido sem login que nasce
aguardando a autorização da Segurança do Trabalho."""

import time

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalogo.models import ExcecaoMaterial, Opcao
from pedidos.models import AutorizacaoPedido, Pedido
from pedidos.protecao import emitir
from tests.config_cenario import enviar_formulario
from tests.epis_cenario import CAPACETE, DESTINO, FITA, LUVA, OCULOS, PROTETOR, enviar, montar_epis
from tests.paginas import texto

pytestmark = pytest.mark.django_db

URL = reverse("pedidos:formulario", args=["epis"])
BUSCA = reverse("pedidos:materiais", args=["epis"])
INDISPONIVEL = "Este formulário está indisponível no momento. Avise o almoxarifado."


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


def test_a_pagina_inicial_lista_o_formulario(client):
    html = texto(client.get(reverse("pedidos:inicio")).text)
    assert "Equipamentos de proteção individual (EPIs)" in html
    assert "Ex.: luva, botina, capacete, protetor auricular" in html


def test_o_formulario_abre_com_o_cabecalho_comum(client):
    r = client.get(URL)
    assert r.status_code == 200
    html = r.text
    assert 'name="solicitante"' in html and 'name="destino"' in html and 'name="obs"' in html
    assert 'name="ocorrencia"' not in html and "Preencher a lista de peças" not in html
    # Um servidor por pedido: nada de lista de destinatários nem de matrícula (FR-003).
    assert 'name="matricula"' not in html and 'name="destinatarios"' not in html


def test_a_busca_so_acha_a_escolha_dos_epis(client):
    assert f'data-codigo="{LUVA}"' in client.get(BUSCA, {"q": "luva"}).text
    assert f'data-codigo="{OCULOS}"' in client.get(BUSCA, {"q": "óculos"}).text  # avulso
    assert f'data-codigo="{FITA}"' not in client.get(BUSCA, {"q": "fita"}).text
    assert "Sem estoque" in texto(client.get(BUSCA, {"q": "protetor"}).text)


def test_sem_escolha_o_formulario_fica_indisponivel(client):
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_EPI).delete()
    ExcecaoMaterial.objects.all().delete()
    assert INDISPONIVEL in client.get(URL).text


def test_o_envio_registra_o_pedido_aguardando_autorizacao(client):
    r = enviar(client, [(LUVA, "2"), (CAPACETE, "1")])
    assert "Pedido registrado" in r.text
    pedido = Pedido.objects.get()
    assert pedido.origem == "EPIS" and pedido.numero.startswith("P-")
    assert pedido.solicitante == "Marcos Pereira" and pedido.destino == DESTINO
    assert {i.codigo for i in pedido.itens.all()} == {LUVA, CAPACETE}
    autorizacao = pedido.autorizacao
    assert autorizacao.situacao == AutorizacaoPedido.Situacao.AGUARDANDO
    assert autorizacao.decidido_por is None and autorizacao.decidido_em is None
    assert pedido.situacao.chave == "aguardando_autorizacao"


def test_a_tela_de_sucesso_diz_que_aguarda_e_nao_promete_entrega(client):
    html = texto(enviar(client, [(LUVA, "1")]).text)
    assert "aguardando a autorização da segurança do trabalho" in html.lower()
    assert "só depois dela o almoxarifado atende" in html.lower()
    assert "a entrega só acontece nesse atendimento" in html.lower()
    # O texto dos outros formulários sugere o atendimento direto: aqui não pode aparecer.
    assert "O almoxarifado vai conferir e separar" not in html


def test_os_outros_formularios_nao_ganham_autorizacao(client):
    r = enviar_formulario(client, "ab", [(FITA, "1")], destino=DESTINO)
    assert "Pedido registrado" in r.text
    pedido = Pedido.objects.get()
    assert pedido.origem == "AB" and pedido.autorizacao_ou_none is None
    assert not AutorizacaoPedido.objects.exists()
    assert "O almoxarifado vai conferir e separar" in texto(r.text)


def test_reenvio_igual_confirma_sem_duplicar_a_autorizacao(client):
    token = emitir(aberto_em=time.time() - 60)
    assert "Pedido registrado" in enviar(client, [(LUVA, "1")], token=token).text
    assert "Pedido já estava registrado" in enviar(client, [(LUVA, "1")], token=token).text
    assert Pedido.objects.count() == 1 and AutorizacaoPedido.objects.count() == 1


@pytest.mark.parametrize(
    ("itens", "erro"),
    [
        ([(LUVA, "1,5")], "Este material só é pedido em quantidade inteira (unidade: UN)."),
        ([(LUVA, "21")], "Estoque disponível"),
        ([(PROTETOR, "1")], "Sem estoque"),
    ],
)
def test_a_regra_de_quantidade_e_a_dos_formularios_publicos(client, itens, erro):
    r = enviar(client, itens)
    assert erro in texto(r.text) and not Pedido.objects.exists()
    assert not AutorizacaoPedido.objects.exists()


def test_material_retirado_da_escolha_antes_do_envio_e_recusado(client):
    client.get(URL)
    ExcecaoMaterial.objects.all().delete()
    r = enviar(client, [(OCULOS, "1")])
    assert "não está mais no catálogo" in r.text and not Pedido.objects.exists()


def test_destino_fora_dos_centros_e_recusado(client):
    r = enviar(client, [(LUVA, "1")], destino="Lua")
    assert not Pedido.objects.exists()
    assert "destino" in texto(r.text).lower()


def test_o_limite_por_nome_soma_todos_os_formularios_publicos(client, settings):
    settings.PEDIDOS_LIMITE_SOLICITANTE_DIA = 2
    settings.PEDIDOS_LIMITE_IP_10_MIN = 99
    settings.PEDIDOS_LIMITE_IP_DIA = 99
    Pedido.objects.create(
        id="00000000-0000-0000-0000-000000000001",
        numero="P-900001",
        origem="LIMPEZA",
        solicitante="Marcos Pereira",
        destino=DESTINO,
    )
    assert "Pedido registrado" in enviar(client, [(LUVA, "1")]).text
    r = enviar(client, [(LUVA, "1")], token=emitir(aberto_em=time.time() - 60))
    assert "Limite de pedidos por dia atingido" in r.text
    assert Pedido.objects.filter(origem="EPIS").count() == 1


def test_painel_mostra_o_pedido_aguardando_autorizacao(client):
    enviar(client, [(LUVA, "2")])
    pedido = Pedido.objects.get()
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    filtrado = client.get(reverse("pedidos:painel"), {"origem": "EPIS"}).text
    assert pedido.numero in filtrado and "Aguardando autorização" in filtrado
    assert pedido.numero not in client.get(reverse("pedidos:painel"), {"origem": "AB"}).text
