"""Telas da Segurança do Trabalho (spec 008, US2, FR-011 a FR-014): fila, detalhe e decisão."""

import uuid

import pytest
from django.urls import reverse

from pedidos.models import AutorizacaoPedido, Pedido
from pedidos.regras import AB
from pedidos.servicos import registrar_pedido
from tests.cenario import envio_ab
from tests.epis_cenario import CAPACETE, LUVA, montar_epis, registrar
from tests.paginas import texto

pytestmark = pytest.mark.django_db

FILA = reverse("pedidos:autorizacoes")


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


@pytest.fixture
def seguranca(client, quem):
    client.force_login(quem["seguranca"])
    return quem["seguranca"]


def detalhe(numero):
    return reverse("pedidos:autorizacao", args=[numero])


def decidir(numero):
    return reverse("pedidos:decidir", args=[numero])


def test_a_fila_exige_login(client):
    r = client.get(FILA)
    assert r.status_code == 302 and r["Location"].startswith(reverse("login"))


def test_o_almoxarifado_nao_abre_a_fila_nem_decide(client, quem):
    pedido = registrar()
    client.force_login(quem["almox"])
    assert client.get(FILA).status_code == 403
    assert client.get(detalhe(pedido.numero)).status_code == 403
    assert client.post(decidir(pedido.numero), {"decisao": "autorizar"}).status_code == 403
    assert AutorizacaoPedido.objects.get(pedido=pedido).situacao == "AGUARDANDO"


def test_o_administrador_sem_o_grupo_nao_decide(client, quem):
    pedido = registrar()
    client.force_login(quem["admin"])
    assert client.post(decidir(pedido.numero), {"decisao": "autorizar"}).status_code == 403


def test_a_fila_lista_so_pedido_de_epi_aguardando_do_mais_antigo_ao_mais_novo(client, seguranca):
    velho = registrar(solicitante="Ana Velha")
    novo = registrar(solicitante="Bia Nova")
    Pedido.objects.filter(pk=velho.pk).update(criado_em="2026-01-01T10:00:00Z")
    ab = registrar_pedido(AB, uuid.uuid4(), envio_ab()).pedido
    html = client.get(FILA).text
    assert ab.numero not in html
    assert html.index(velho.numero) < html.index(novo.numero)
    assert "Ana Velha" in html and "Bia Nova" in html


def test_a_fila_mostra_os_decididos_em_leitura_separados(client, seguranca):
    aberto = registrar(solicitante="Ana Aberta")
    decidido = registrar(solicitante="Bia Decidida")
    client.post(decidir(decidido.numero), {"decisao": "recusar", "motivo": "Sem laudo"})
    # A mensagem "Pedido … recusado." da decisão aparece no topo da página: só as seções contam.
    html = client.get(FILA).text.partition('id="titulo-aguardando"')[2]
    aguardando, _, ja_decididos = html.partition("Já decididos")
    assert aberto.numero in aguardando and decidido.numero not in aguardando
    assert decidido.numero in ja_decididos and "Sem laudo" in ja_decididos
    assert "Recusado" in ja_decididos


def test_o_detalhe_mostra_cabecalho_materiais_e_quantidades_so_de_leitura(client, seguranca):
    pedido = registrar(itens=[(LUVA, "2"), (CAPACETE, "1")])
    html = client.get(detalhe(pedido.numero)).text
    assert pedido.numero in html and "Marcos Pereira" in html and "ETA I" in html
    assert "LUVA DE VAQUETA" in html and "CAPACETE DE SEGURANÇA" in html
    assert 'name="entregue-' not in html and 'name="adicionado"' not in html  # sem atendimento
    assert 'name="decisao"' in html and 'name="motivo"' in html


def test_o_detalhe_de_pedido_que_nao_e_de_epi_da_404(client, seguranca):
    ab = registrar_pedido(AB, uuid.uuid4(), envio_ab()).pedido
    assert client.get(detalhe(ab.numero)).status_code == 404
    assert client.get(detalhe("P-999999")).status_code == 404


def test_o_formulario_avisa_que_o_motivo_e_visto_pelo_servidor_e_pelo_almoxarifado(
    client, seguranca
):
    pedido = registrar()
    html = texto(client.get(detalhe(pedido.numero)).text)
    assert "O motivo será visto pelo servidor, na consulta, e pelo almoxarifado" in html
    assert "não escreva dado sensível" in html.lower()


def test_autorizar_pela_tela_grava_e_volta_ao_detalhe(client, seguranca):
    pedido = registrar()
    r = client.post(decidir(pedido.numero), {"decisao": "autorizar"})
    assert r.status_code == 302 and r["Location"] == detalhe(pedido.numero)
    assert AutorizacaoPedido.objects.get(pedido=pedido).situacao == "AUTORIZADO"
    html = texto(client.get(detalhe(pedido.numero)).text)
    assert "Autorizado" in html and "Sônia Segura" in html
    assert 'name="decisao"' not in client.get(detalhe(pedido.numero)).text  # decidido: sem botões


def test_recusar_sem_motivo_volta_com_o_erro_e_nada_muda(client, seguranca):
    pedido = registrar()
    r = client.post(decidir(pedido.numero), {"decisao": "recusar", "motivo": " "})
    assert r.status_code == 200 and "Informe o motivo da recusa." in texto(r.text)
    assert AutorizacaoPedido.objects.get(pedido=pedido).situacao == "AGUARDANDO"


def test_recusar_com_motivo_encerra_o_pedido(client, seguranca):
    pedido = registrar()
    client.post(decidir(pedido.numero), {"decisao": "recusar", "motivo": "EPI já entregue"})
    a = AutorizacaoPedido.objects.get(pedido=pedido)
    assert (a.situacao, a.motivo) == ("RECUSADO", "EPI já entregue")
    assert "EPI já entregue" in client.get(detalhe(pedido.numero)).text


def test_decidir_de_novo_mostra_a_decisao_gravada_e_nao_muda(client, seguranca):
    pedido = registrar()
    client.post(decidir(pedido.numero), {"decisao": "autorizar"})
    r = client.post(decidir(pedido.numero), {"decisao": "recusar", "motivo": "x"}, follow=True)
    assert "Este pedido já foi autorizado por Sônia Segura" in texto(r.text)
    assert AutorizacaoPedido.objects.get(pedido=pedido).situacao == "AUTORIZADO"


def test_decidir_so_aceita_post(client, seguranca):
    pedido = registrar()
    assert client.get(decidir(pedido.numero)).status_code == 405


def test_a_decisao_pela_tela_exige_o_csrf(client, seguranca):
    from django.test import Client

    pedido = registrar()
    estrito = Client(enforce_csrf_checks=True)
    estrito.force_login(seguranca)
    r = estrito.post(decidir(pedido.numero), {"decisao": "autorizar"})
    assert r.status_code == 403
    assert AutorizacaoPedido.objects.get(pedido=pedido).situacao == "AGUARDANDO"
