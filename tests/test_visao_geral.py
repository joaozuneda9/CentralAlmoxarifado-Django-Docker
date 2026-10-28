import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from automacoes.visao_geral import linha_lancamento
from catalogo.models import Importacao
from pedidos.models import ExecucaoRobo
from tests.cenario import criar_pedido

URL = reverse("automacoes:pagina")
SITUACAO = "section#situacao-catalogo"


def linhas(html):
    """Linhas da visão geral, pelo nome: {nome: html da linha}."""
    return {
        re.search(r'class="fonte-nome">([^<]+)<', li).group(1): li
        for li in re.findall(r'<li class="fonte[^"]*">(.*?)</li>', html, re.S)
    }


def regiao(html, id_):
    inicio = html.index(f'id="{id_}"')
    return html[html.rindex("<", 0, inicio) : html.index(">", inicio) + 1]


# linha_lancamento é pura: recebe os números e a última execução, sem consultar o banco.

AGORA = timezone.now()


def execucao(**campos):
    padrao = {"situacao": "SUCESSO", "inicio": AGORA - timedelta(minutes=20), "simulacao": True}
    padrao["fim"] = padrao["inicio"] + timedelta(minutes=2)
    return ExecucaoRobo(**{**padrao, **campos})


@pytest.mark.parametrize(
    "kwargs, nivel, selo",
    [
        ({"ultima": None}, "neutro", "Sem execuções"),
        ({"ultima": execucao()}, "ok", "Em dia"),
        ({"ultima": execucao(situacao="ATENCAO")}, "aviso", "Com pendências"),
        ({"ultima": execucao(situacao="FALHA", erro="TimeoutError: x")}, "erro", "Falhou"),
        (
            {"ultima": execucao(situacao="ANDAMENTO", fim=None), "interrompida": True},
            "aviso",
            "Interrompida",
        ),
        (
            {"ultima": execucao(situacao="ANDAMENTO", fim=None), "em_andamento": True},
            "andamento",
            "Em andamento",
        ),
        ({"ultima": execucao(), "travados": 2}, "aviso", "2 para conferir"),
    ],
)
def test_linha_lancamento_nivel_e_selo(kwargs, nivel, selo):
    argumentos = {"pendentes": 0, "travados": 0, "em_andamento": False, "interrompida": False}
    linha = linha_lancamento(**{**argumentos, **kwargs}, agora=AGORA)
    assert (linha.nivel, linha.selo) == (nivel, selo)


def test_linha_lancamento_resumo_quando_e_acao():
    linha = linha_lancamento(
        pendentes=3,
        travados=1,
        ultima=execucao(),
        em_andamento=False,
        interrompida=False,
        agora=AGORA,
    )
    assert linha.resumo == "3 requisições aguardando o robô"
    assert linha.complemento == "última: simulação"
    assert linha.ha_quanto == "há 18 min"
    assert linha.acao_rotulo == "Conferir travas"
    assert linha.acao_url == f"{URL}?aba=lancamento#travas" and not linha.acao_discreta
    vazia = linha_lancamento(
        pendentes=0, travados=0, ultima=None, em_andamento=False, interrompida=False, agora=AGORA
    )
    assert vazia.resumo == "Nada aguardando o robô" and vazia.ha_quanto == ""
    assert vazia.acao_rotulo == "Abrir" and vazia.acao_discreta


def test_linha_lancamento_que_falhou_explica_o_erro():
    linha = linha_lancamento(
        pendentes=1,
        travados=0,
        ultima=execucao(situacao="FALHA", erro="TimeoutError: x", simulacao=False),
        em_andamento=False,
        interrompida=False,
        agora=AGORA,
    )
    assert linha.erro and "Timeout" not in linha.erro
    assert linha.complemento == "último: lançamento real"


# A página: a linha do lançamento junto das fontes do SCPI.


@pytest.mark.django_db
def test_visao_geral_tem_o_lancamento_antes_das_fontes(client, usuario_logado):
    html = client.get(URL).text
    nomes = list(linhas(html))
    assert nomes[:4] == ["Lançamento no SCPI", "Cadastro", "Estoque", "Saídas do SCPI"]
    assert ">Sem execuções<" in linhas(html)["Lançamento no SCPI"]
    assert ">Sem dados<" in linhas(html)["Cadastro"]


@pytest.mark.django_db
def test_estoque_que_falhou_leva_a_aba_do_robo(client, usuario_logado):
    Importacao.objects.create(
        tipo="ESTOQUE", situacao="FALHA", erro="TimeoutError: x", fim=timezone.now()
    )
    estoque = linhas(client.get(URL).text)["Estoque"]
    assert ">Falhou<" in estoque and "Tentar de novo" in estoque
    assert f'href="{URL}?aba=estoque"' in estoque


@pytest.mark.django_db
def test_lote_travado_aparece_na_linha_e_na_aba(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    html = client.get(URL).text
    lancamento = linhas(html)["Lançamento no SCPI"]
    assert ">1 para conferir<" in lancamento
    assert "1 requisição aguardando o robô" in lancamento
    assert f'href="{URL}?aba=lancamento#travas"' in lancamento and "Conferir travas" in lancamento
    aba = re.search(r'<button[^>]*id="aba-lancamento"[^>]*>(.*?)</button>', html, re.S).group(1)
    assert 'class="selo selo-aviso aba-selo"' in aba and '<svg class="icone"' in aba
    assert '<span class="aba-selo-texto">1 para conferir</span>' in aba
    assert "Lançamento no SCPI: 1 para conferir." in html


@pytest.mark.django_db
def test_lancamento_em_andamento_faz_a_visao_geral_acompanhar(client, usuario_logado):
    ExecucaoRobo.objects.create()
    html = client.get(URL).text
    assert ">Em andamento<" in linhas(html)["Lançamento no SCPI"]
    assert 'hx-trigger="every 5s"' in regiao(html, "situacao-catalogo")
    aba = re.search(r'<button[^>]*id="aba-lancamento"[^>]*>(.*?)</button>', html, re.S).group(1)
    assert 'class="selo selo-info aba-selo"' in aba and '<svg class="icone"' in aba
    assert '<span class="aba-selo-texto">Em andamento</span>' in aba


@pytest.mark.django_db
def test_importacao_e_lancamento_juntos_um_terminar_nao_para_o_outro(client, usuario_logado):
    imp = Importacao.objects.create(tipo="SAIDAS")
    exe = ExecucaoRobo.objects.create()
    html = client.get(URL).text
    assert ">Em andamento<" in linhas(html)["Lançamento no SCPI"]
    assert ">Em andamento<" in linhas(html)["Saídas do SCPI"]
    # A importação termina (há mais de 30 s): o lançamento segue sendo acompanhado.
    imp.situacao, imp.fim = "SUCESSO", timezone.now() - timedelta(minutes=1)
    imp.save()
    html = client.get(URL).text
    assert 'hx-trigger="every 5s"' in regiao(html, "situacao-catalogo")
    assert 'hx-trigger="every 3s"' in regiao(html, "lancamentos")
    # O lançamento termina e a importação volta a rodar: só a visão geral acompanha.
    exe.situacao, exe.fim = "SUCESSO", timezone.now() - timedelta(minutes=1)
    exe.save()
    Importacao.objects.create(tipo="ESTOQUE")
    html = client.get(URL).text
    assert 'hx-trigger="every 5s"' in regiao(html, "situacao-catalogo")
    assert "hx-trigger" not in regiao(html, "lancamentos")


@pytest.mark.django_db
def test_regiao_da_visao_geral_traz_a_linha_do_lancamento(client, usuario_logado):
    r = client.get(URL, HTTP_HX_REQUEST="true", HTTP_HX_TARGET=SITUACAO)
    assert "Lançamento no SCPI" in linhas(r.text)
