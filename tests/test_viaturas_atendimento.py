"""O pedido de viaturas segue o caminho comum do almoxarifado (spec 006, FR-010, SC-002):
atendimento com troca e acréscimo, linhas de saída para o robô, edição e recibo, sem regra
própria."""

import re
import uuid
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from pedidos.consultas import fila_do_robo
from pedidos.models import LinhaSaida, Pedido
from pedidos.regras import VIATURAS, Adicionado
from pedidos.servicos import confirmar_atendimento, editar_atendimento
from tests.cenario import saida
from tests.paginas import texto
from tests.viaturas_cenario import BOTINA, EQUIPE, FITA, ISOLANTE, enviar, montar_viaturas

pytestmark = pytest.mark.django_db
HOJE = date(2026, 10, 9)


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="12345", password="x", first_name="Ana")


@pytest.fixture
def pedido(client):
    montar_viaturas()
    assert "Pedido registrado" in enviar(client, [(FITA, "2"), (BOTINA, "1")], ocorrencia="77").text
    return Pedido.objects.get()


def test_o_atendimento_sugere_o_centro_da_equipe(client, pedido, usuario):
    client.force_login(usuario)
    html = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert re.search(rf'name="centro_custo"[^>]*value="{EQUIPE}"', html) or (
        f'value="{EQUIPE}" selected' in html
    )


def test_atender_trocar_acrescentar_lancar_editar_e_imprimir(client, pedido, usuario):
    assert pedido.origem == VIATURAS
    # A botina é trocada pela fita isolante; a fita veda rosca sai como pedida.
    qtds = {FITA: "2", BOTINA: "0", ISOLANTE: "1"}
    r = confirmar_atendimento(
        pedido.id,
        uuid.uuid4(),
        saida(centro_custo=EQUIPE),
        qtds,
        nao_lancar=False,
        usuario=usuario,
        hoje=HOJE,
        adicionados=[Adicionado(ISOLANTE, BOTINA)],
    )
    assert r.ok, [e.texto for e in r.erros]
    linhas = LinhaSaida.objects.filter(atendimento__pedido=pedido)
    assert {(linha.codigo, linha.centro_custo, linha.status) for linha in linhas} == {
        (FITA, EQUIPE, LinhaSaida.Status.PENDENTE),
        (ISOLANTE, EQUIPE, LinhaSaida.Status.PENDENTE),
    }
    assert pedido.numero in [req.lote for req in fila_do_robo().requisicoes]

    antes = set(linhas.values_list("id", flat=True))
    pedido.refresh_from_db()
    editado = editar_atendimento(
        pedido.id,
        pedido.versao,
        saida(centro_custo="ETA II"),  # o almoxarifado pode trocar o centro, como sempre
        {FITA: "1", BOTINA: "0", ISOLANTE: "1"},
        nao_lancar=False,
        adicionados=[Adicionado(ISOLANTE, BOTINA)],
        usuario=usuario,
        hoje=HOJE,
    )
    assert editado.ok, [e.texto for e in editado.erros]
    depois = LinhaSaida.objects.filter(atendimento__pedido=pedido)
    assert antes.isdisjoint(set(depois.values_list("id", flat=True)))  # recriadas
    assert {linha.centro_custo for linha in depois} == {"ETA II"}
    assert Pedido.objects.get().ocorrencia == "77"  # o que veio do encarregado não muda

    client.force_login(usuario)
    recibo = texto(client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text)
    assert "Pedido pelo solicitante" in recibo and "Adicionado pelo almoxarifado" in recibo
    assert "Nº da ocorrência 77" in recibo


def test_o_detalhe_mostra_o_nome_do_scpi_e_nao_o_do_formulario(client, pedido, usuario):
    from catalogo.models import Material

    item = pedido.itens.get(codigo=FITA)
    item.material = "Nome só do formulário"
    item.save()
    nome_scpi = Material.objects.get(codigo=FITA).nome
    client.force_login(usuario)
    html = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert f"<strong>{nome_scpi}</strong>" in html
    assert "Nome só do formulário" not in html


def test_a_edicao_mostra_o_nome_do_scpi_do_material_acrescentado(client, pedido, usuario):
    from catalogo.models import Material

    r = confirmar_atendimento(
        pedido.id,
        uuid.uuid4(),
        saida(centro_custo=EQUIPE),
        {FITA: "2", BOTINA: "0", ISOLANTE: "1"},
        nao_lancar=False,
        usuario=usuario,
        hoje=HOJE,
        adicionados=[Adicionado(ISOLANTE, BOTINA)],
    )
    assert r.ok, [e.texto for e in r.erros]
    Material.objects.filter(codigo=ISOLANTE).update(nome="NOME NOVO NO SCPI")
    client.force_login(usuario)
    html = client.get(reverse("pedidos:editar", args=[pedido.numero])).text
    assert "NOME NOVO NO SCPI" in html
