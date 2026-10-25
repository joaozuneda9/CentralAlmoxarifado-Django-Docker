"""Destinos do formulário da oficina mecânica (spec 007, FR-006 a FR-009; research R5): a OFICINA
MECÂNICA ou uma viatura, só como "centro — placa"; os outros formulários não mudam."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalogo.catalogos import centros_do_formulario
from catalogo.models import CentroCusto, Formulario
from pedidos.models import Pedido
from pedidos.regras import Centro, opcoes_destino, resolver_destino
from tests.oficina_cenario import FILTRO, OFICINA, PICKUP, RETRO, enviar, montar_oficina

INDISPONIVEL = "Este formulário está indisponível no momento. Avise o almoxarifado."

# Regras puras


VIATURA = Centro("PICKUP 01", "31", "ABC1D23", so_com_placa=True)


def test_viatura_marcada_so_aparece_com_a_placa():
    assert opcoes_destino([Centro(OFICINA, "20"), VIATURA]) == [OFICINA, PICKUP]


def test_sem_a_marca_o_destino_e_o_de_antes():
    centros = [
        Centro("ETA I", "12"),
        Centro("EQUIPE", "51", "AAA1A11"),
        Centro("EQUIPE", "51", "BBB2B22"),
    ]
    assert opcoes_destino(centros) == [
        "ETA I",
        "EQUIPE",
        "EQUIPE — AAA1A11",
        "EQUIPE — BBB2B22",
    ]


def test_centro_com_uma_linha_sem_a_marca_continua_oferecido_sozinho():
    centros = [Centro("EQUIPE", "51", "AAA1A11", so_com_placa=True), Centro("EQUIPE", "51")]
    assert opcoes_destino(centros) == ["EQUIPE", "EQUIPE — AAA1A11"]


@pytest.mark.parametrize("digitado", ["abc-1d23", "ABC1D23", "pickup 01 — abc1d23"])
def test_a_placa_digitada_acha_a_viatura(digitado):
    assert resolver_destino(digitado, [VIATURA]) == PICKUP


def test_a_descricao_sozinha_da_viatura_nao_e_destino():
    assert resolver_destino("PICKUP 01", [VIATURA]) == ""


# Com o banco


@pytest.mark.django_db
def test_centros_da_oficina():
    montar_oficina()
    assert opcoes_destino(centros_do_formulario(Formulario.OFICINA)) == [OFICINA, PICKUP, RETRO]


@pytest.mark.django_db
def test_sem_o_centro_da_oficina_so_as_viaturas():
    montar_oficina()
    CentroCusto.objects.filter(descricao=OFICINA).delete()
    assert opcoes_destino(centros_do_formulario(Formulario.OFICINA)) == [PICKUP, RETRO]


@pytest.mark.django_db
class TestFormulario:
    @pytest.fixture(autouse=True)
    def cenario(self):
        montar_oficina()

    def destinos(self, client, nome):
        html = client.get(reverse("pedidos:formulario", args=[nome])).text
        return html.split('<datalist id="destinos">')[1].split("</datalist>")[0]

    def test_o_formulario_lista_so_a_oficina_e_as_viaturas(self, client):
        opcoes = re.findall(r'<option value="([^"]+)">', self.destinos(client, "oficina"))
        assert opcoes == [OFICINA, PICKUP, RETRO]

    @pytest.mark.parametrize("destino", ["ETA II", "PICKUP 01"])
    def test_outro_centro_ou_a_descricao_sozinha_sao_recusados(self, client, destino):
        r = enviar(client, [(FILTRO, "1")], destino=destino)
        assert "não está na lista de centros de custo" in r.text
        assert not Pedido.objects.exists()
        assert f'name="item_codigo" value="{FILTRO}"' in r.text  # o pedido é mantido

    def test_a_placa_digitada_grava_centro_e_placa(self, client):
        assert "Pedido registrado" in enviar(client, [(FILTRO, "1")], destino="abc-1d23").text
        assert Pedido.objects.get().destino == PICKUP

    def test_sem_destino_o_formulario_fica_indisponivel(self, client):
        CentroCusto.objects.filter(descricao=OFICINA).delete()
        CentroCusto.objects.exclude(placa=None).delete()
        html = client.get(reverse("pedidos:formulario", args=["oficina"])).text
        assert INDISPONIVEL in html

    def test_viatura_descadastrada_depois_do_envio_nao_muda_o_pedido(self, client):
        assert "Pedido registrado" in enviar(client, [(FILTRO, "1")], destino=PICKUP).text
        CentroCusto.objects.filter(placa="ABC1D23").delete()
        assert Pedido.objects.get().destino == PICKUP

    @pytest.mark.parametrize(
        ("destino", "placa", "centro"),
        [(PICKUP, "ABC1D23", "PICKUP 01"), (OFICINA, "", OFICINA)],
    )
    def test_o_atendimento_sugere_centro_e_placa(self, client, destino, placa, centro):
        assert "Pedido registrado" in enviar(client, [(FILTRO, "1")], destino=destino).text
        pedido = Pedido.objects.get()
        client.force_login(get_user_model().objects.create_user(username="12345", password="x"))
        html = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
        assert re.search(rf'<option value="{re.escape(centro)}"[^>]*selected', html)
        selecionadas = re.findall(r'<option value="([A-Z0-9]+)" data-centro="[^"]*" selected', html)
        assert selecionadas == ([placa] if placa else [])
        assert destino in html  # o detalhe mostra o destino

    def test_os_outros_formularios_continuam_com_todos_os_centros(self, client):
        for nome in ("limpeza", "ab"):
            opcoes = self.destinos(client, nome)
            assert '<option value="ETA II">' in opcoes
            assert '<option value="PICKUP 01">' in opcoes and PICKUP in opcoes
