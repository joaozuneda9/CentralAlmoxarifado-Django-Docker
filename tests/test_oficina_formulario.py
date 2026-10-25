"""O formulário da oficina mecânica de ponta a ponta (spec 007, US1; FR-001 a FR-005, FR-010,
FR-011): página inicial, busca, regra de quantidade, envio, painel, aviso e atendimento."""

import re
import time
import uuid
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalogo.models import ExcecaoMaterial, Material, Opcao
from pedidos.models import LinhaSaida, Pedido
from pedidos.protecao import emitir
from pedidos.regras import OFICINA as ORIGEM
from pedidos.servicos import confirmar_atendimento
from pedidos.telegram import texto_aviso
from tests.cenario import saida
from tests.oficina_cenario import FILTRO, FITA, OFICINA, OLEO, PNEU, enviar, montar_oficina

pytestmark = pytest.mark.django_db

URL = reverse("pedidos:formulario", args=["oficina"])
BUSCA = reverse("pedidos:materiais", args=["oficina"])
INDISPONIVEL = "Este formulário está indisponível no momento. Avise o almoxarifado."


@pytest.fixture(autouse=True)
def cenario():
    montar_oficina()


def texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_a_pagina_inicial_lista_o_formulario(client):
    html = texto(client.get(reverse("pedidos:inicio")).text)
    assert "Oficina mecânica" in html
    assert "Ex.: filtro, óleo, pneu, aditivo, lâmpada" in html


def test_o_formulario_abre_sem_campos_dos_outros(client):
    html = client.get(URL).text
    assert "Ex.: filtro de óleo, pneu" in html
    assert 'placeholder="Oficina mecânica ou placa da viatura"' in html
    assert 'name="ocorrencia"' not in html and "Preencher a lista de peças" not in html


def test_a_busca_so_acha_a_escolha_da_oficina(client):
    filtro = client.get(BUSCA, {"q": "filtro"}).text
    assert filtro.count(f'data-codigo="{FILTRO}"') == 1
    assert f'data-codigo="{OLEO}"' in client.get(BUSCA, {"q": "15w40"}).text  # avulso do GERAL
    assert f'data-codigo="{FITA}"' not in client.get(BUSCA, {"q": "fita"}).text
    assert "Sem estoque" in texto(client.get(BUSCA, {"q": "pneu"}).text)


def test_sem_escolha_o_formulario_fica_indisponivel(client):
    Opcao.objects.filter(lista=Opcao.Lista.GRUPO_OFICINA).delete()
    ExcecaoMaterial.objects.all().delete()
    assert INDISPONIVEL in client.get(URL).text


def test_o_envio_registra_o_pedido_da_oficina(client):
    r = enviar(client, [(FILTRO, "2"), (OLEO, "1,5")])
    assert "Pedido registrado" in r.text
    pedido = Pedido.objects.get()
    assert pedido.origem == ORIGEM and pedido.numero.startswith("P-")
    assert pedido.destino == OFICINA
    assert {i.codigo for i in pedido.itens.all()} == {FILTRO, OLEO}


def test_reenvio_igual_confirma_sem_duplicar(client):
    token = emitir(aberto_em=time.time() - 60)
    assert "Pedido registrado" in enviar(client, [(FILTRO, "1")], token=token).text
    assert "Pedido já estava registrado" in enviar(client, [(FILTRO, "1")], token=token).text
    assert Pedido.objects.count() == 1


@pytest.mark.parametrize(
    ("itens", "erro"),
    [
        ([(FILTRO, "1,5")], "Este material só é pedido em quantidade inteira (unidade: UN)."),
        ([(FILTRO, "5")], "Estoque disponível"),
        ([(PNEU, "1")], "Sem estoque"),
    ],
)
def test_a_regra_de_quantidade_e_a_dos_formularios_publicos(client, itens, erro):
    r = enviar(client, itens)
    assert erro in texto(r.text) and not Pedido.objects.exists()


def test_material_retirado_da_escolha_antes_do_envio_e_recusado(client):
    client.get(URL)
    ExcecaoMaterial.objects.all().delete()
    r = enviar(client, [(OLEO, "1")])
    assert "não está mais no catálogo" in r.text and not Pedido.objects.exists()


def test_painel_e_aviso(client):
    enviar(client, [(FILTRO, "2")])
    pedido = Pedido.objects.get()
    client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
    filtrado = client.get(reverse("pedidos:painel"), {"origem": ORIGEM}).text
    assert pedido.numero in filtrado and 'title="Oficina mecânica">Oficina mecânica<' in filtrado
    assert pedido.numero not in client.get(reverse("pedidos:painel"), {"origem": "AB"}).text
    assert "Oficina mecânica" in texto_aviso(pedido)


def test_o_atendimento_gera_as_linhas_de_saida(client):
    enviar(client, [(FILTRO, "2"), (OLEO, "1,5")])
    pedido = Pedido.objects.get()
    usuario = get_user_model().objects.create_user(username="12345", password="x")
    r = confirmar_atendimento(
        pedido.id,
        uuid.uuid4(),
        saida(centro_custo=OFICINA),
        {FILTRO: "2", OLEO: "1,5"},
        nao_lancar=False,
        usuario=usuario,
        hoje=date(2026, 10, 9),
    )
    assert r.ok, r.erros
    linhas = LinhaSaida.objects.filter(atendimento__pedido=pedido)
    assert {linha.codigo for linha in linhas} == {FILTRO, OLEO}
    assert all(linha.status == LinhaSaida.Status.PENDENTE for linha in linhas)


def test_o_estoque_vem_do_cadastro(client):
    Material.objects.filter(codigo=FILTRO).update(estoque=1)
    assert "Pedido registrado" not in enviar(client, [(FILTRO, "2")]).text
