from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from catalogo.models import ConfiguracaoCurva, Material, ParDePara, SaidaSCPI
from tests.papeis import dar_papeis

pytestmark = pytest.mark.django_db

URL = reverse("catalogo:curva")


@pytest.fixture(autouse=True)
def hoje(monkeypatch):
    monkeypatch.setattr("catalogo.views.hoje", lambda: date(2026, 10, 12))


@pytest.fixture
def usuario(django_user_model):
    return dar_papeis(django_user_model.objects.create_user(username="12345", password="x"))


@pytest.fixture
def logado(client, usuario):
    client.force_login(usuario)
    return client


def saida(id_requi, cadpro, valor="1", qtd="1", dia=date(2026, 3, 1)):
    SaidaSCPI.objects.create(
        id_requi=id_requi, cadpro=cadpro, data=dia, qtd=Decimal(qtd), valor=Decimal(valor)
    )


@pytest.fixture
def cenario():
    Material.objects.create(codigo="000.029.872", nome="TUBO VELHO", oculto=True)
    Material.objects.create(codigo="016.001.021", nome="TUBO PEAD 20MM", unidade="M")
    Material.objects.create(codigo="003.001.001", nome="CIMENTO", unidade="SC")
    ParDePara.objects.create(antigo="000.029.872", novo="016.001.021")
    for n in range(3):
        saida(f"a{n}", "000.029.872", valor="10")
    saida("b1", "016.001.021", valor="10")
    saida("c1", "003.001.001", valor="500")
    saida("p1", "003.000.025", valor="7")  # sem cadastro e sem par: pendente


def test_exige_login(client):
    resposta = client.get(URL)
    assert resposta.status_code == 302 and reverse("login") in resposta.url


def test_frequencia_consolidada_com_classe_em_texto(logado, cenario):
    texto = logado.get(URL).text
    assert '<span class="mono">016.001.021</span>' in texto
    assert "TUBO PEAD 20MM" in texto
    assert "000.029.872</span></td>" not in texto.split('id="painel-pendentes"')[0]
    assert '<span class="selo selo-neutro">A</span>' in texto


def test_periodo_e_aviso_dos_dados_confiaveis(logado, cenario):
    texto = logado.get(URL).text
    assert "Os dados anteriores a 01/01/2026 não entram nos cálculos." in texto
    assert "de 01/01/2026 a" in texto


def test_reconciliacao_na_pagina(logado, cenario):
    texto = logado.get(URL).text
    assert "6 ocorrências antes e 6 depois" in texto
    assert "4 códigos viraram 3 canônicos" in texto


def test_pendentes(logado, cenario):
    texto = logado.get(URL + "?aba=pendentes").text
    pendentes = texto.split('id="painel-pendentes"')[1]
    assert "003.000.025" in pendentes and "sem cadastro" in pendentes
    assert reverse("admin:catalogo_pardepara_add") not in pendentes


def test_pendentes_com_link_para_a_equipe(admin_client, cenario):
    texto = admin_client.get(URL + "?aba=pendentes").text
    pendentes = texto.split('id="painel-pendentes"')[1]
    assert f"{reverse('admin:catalogo_pardepara_add')}?antigo=003.000.025" in pendentes


def test_aba_inicial_vem_da_url(logado, cenario):
    texto = logado.get(URL + "?aba=valor").text
    assert (
        'id="aba-valor" data-aba="valor" aria-controls="painel-valor" aria-selected="true"' in texto
    )
    texto = logado.get(URL + "?aba=qualquer").text
    assert 'aria-controls="painel-frequencia" aria-selected="true"' in texto


def test_meses_valido_e_invalido(logado, cenario):
    ConfiguracaoCurva.objects.create(janela_meses=12)
    texto = logado.get(URL + "?meses=2").text
    assert 'name="meses" value="2"' in texto
    texto = logado.get(URL + "?meses=abc").text
    assert 'name="meses" value="12"' in texto
    assert "Janela inválida; usando a padrão de 12 meses." in texto


def test_sem_saidas_no_periodo(logado):
    texto = logado.get(URL).text
    assert "Nenhuma saída no período." in texto


def test_item_curva_abc_no_menu(logado):
    texto = logado.get(reverse("pedidos:painel")).text
    assert f'href="{URL}"' in texto


def test_reposicao_soma_o_saldo_dos_antigos_e_marca_o_prazo_proprio(logado, cenario):
    from catalogo.models import ParametroReposicao

    Material.objects.filter(codigo="000.029.872").update(estoque=5)
    Material.objects.filter(codigo="016.001.021").update(estoque=7)
    ParametroReposicao.objects.create(
        material=Material.objects.get(codigo="016.001.021"), prazo_entrega_dias=45
    )
    texto = logado.get(URL + "?aba=reposicao").text
    reposicao = texto.split('id="painel-reposicao"')[1].split('id="painel-pendentes"')[0]
    linha = reposicao.split('<span class="mono">016.001.021</span>')[1].split("</tr>")[0]
    assert "<td>12</td>" in linha  # 5 do código antigo + 7 do canônico
    assert '45 <span class="texto-secundario">(próprio)</span>' in linha
    assert '<span class="selo selo-' in linha
    assert "000.029.872</span>" not in reposicao  # o antigo não tem linha própria
    assert "003.000.025" not in reposicao  # sem cadastro: fica nos pendentes


def test_reposicao_situacao_em_texto(logado, cenario):
    texto = logado.get(URL + "?aba=reposicao").text
    reposicao = texto.split('id="painel-reposicao"')[1].split('id="painel-pendentes"')[0]
    assert "Esgotado" in reposicao
