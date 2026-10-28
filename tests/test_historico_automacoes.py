from datetime import date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from automacoes.historico import (
    FiltrosHistorico,
    SequenciaHistorico,
    consultas,
    linha_de_execucao,
    linha_de_importacao,
)
from catalogo.models import Importacao
from pedidos.models import ExecucaoRobo

AGORA = timezone.now()


def imp(**campos):
    padrao = {"tipo": "ESTOQUE", "situacao": "SUCESSO", "inicio": AGORA - timedelta(minutes=5)}
    padrao["fim"] = padrao["inicio"] + timedelta(minutes=3)
    return Importacao(**{**padrao, **campos})


def exe(**campos):
    padrao = {"situacao": "SUCESSO", "inicio": AGORA - timedelta(minutes=5), "simulacao": True}
    padrao["fim"] = padrao["inicio"] + timedelta(seconds=45)
    return ExecucaoRobo(**{**padrao, **campos})


# Conversão em linha do histórico (pura: só o registro e os ids em andamento).


@pytest.mark.parametrize(
    "registro, modo",
    [
        (
            imp(tipo="CADASTRO", periodo_de=date(2026, 10, 1), periodo_ate=date(2026, 10, 8)),
            "Só os novos (01/10 a 08/10)",
        ),
        (imp(tipo="CADASTRO"), "Recarga completa"),
        (
            imp(tipo="SAIDAS", periodo_de=date(2026, 10, 1), periodo_ate=date(2026, 10, 8)),
            "Período 01/10 a 08/10",
        ),
        (imp(tipo="ESTOQUE"), "Saldos"),
        (imp(tipo="DEPARA"), "Carga da planilha"),
    ],
)
def test_modo_da_importacao(registro, modo):
    assert linha_de_importacao(registro, set()).modo == modo


def test_modo_da_execucao():
    assert linha_de_execucao(exe(simulacao=True), set()).modo == "Simulação"
    assert linha_de_execucao(exe(simulacao=False), set()).modo == "Lançamento real"


@pytest.mark.parametrize(
    "registro, situacao, selo",
    [
        (imp(), "concluida", "Concluída"),
        (imp(avisos=["Linhas repetidas: 1."]), "com_avisos", "Com avisos"),
        (imp(situacao="FALHA", erro="Estoque: falhou."), "falhou", "Falhou"),
        (imp(situacao="ANDAMENTO", fim=None, pk=7), "andamento", "Em andamento"),
        (imp(situacao="ANDAMENTO", fim=None, pk=8), "interrompida", "Interrompida"),
    ],
)
def test_situacao_da_importacao(registro, situacao, selo):
    linha = linha_de_importacao(registro, {7})
    assert (linha.situacao, linha.selo) == (situacao, selo)


@pytest.mark.parametrize(
    "registro, situacao, selo",
    [
        (exe(), "concluida", "Concluída"),
        (exe(situacao="ATENCAO"), "com_avisos", "Com pendências"),
        (exe(situacao="FALHA", erro="x"), "falhou", "Falhou"),
        (exe(situacao="ANDAMENTO", fim=None, pk=3), "andamento", "Em andamento"),
        (exe(situacao="ANDAMENTO", fim=None, pk=4), "interrompida", "Interrompida"),
    ],
)
def test_situacao_da_execucao(registro, situacao, selo):
    linha = linha_de_execucao(registro, {3})
    assert (linha.situacao, linha.selo) == (situacao, selo)


def test_linha_da_importacao_traz_duracao_linhas_avisos_e_erro():
    linha = linha_de_importacao(
        imp(
            linhas=11597,
            avisos=[f"Texto cortado em nome (255 caracteres): 000.00{i}." for i in range(3)],
        ),
        set(),
    )
    assert linha.robo == "Estoque" and linha.duracao == "3 min"
    assert linha.resumo == "11.597 linhas"
    assert len(linha.avisos) == 1 and linha.n_avisos == 3
    erro = linha_de_importacao(
        imp(situacao="FALHA", erro="Falha inesperada: Locator.click: Timeout 30000ms\nCall log:"),
        set(),
    )
    assert erro.erro == "O SCPI demorou demais para responder e a importação parou."
    assert erro.resumo == ""  # falhou sem gravar nada: sem "0 linhas"
    assert "Call log:" in erro.erro_tecnico
    assert (
        linha_de_importacao(imp(situacao="FALHA", erro="Estoque: falhou."), set()).erro_tecnico
        == ""
    )


def test_linha_da_execucao_traz_requisicoes_duracao_quem_e_falha():
    usuario = get_user_model()(username="12345", first_name="Ana")
    linha = linha_de_execucao(
        exe(
            simulacao=False,
            situacao="ATENCAO",
            resumo={"requisicoes": 3, "lancadas": 2},
            iniciada_por=usuario,
        ),
        set(),
    )
    assert linha.robo == "Lançamento no SCPI" and linha.duracao == "45 s"
    assert linha.resumo == "2 de 3 requisições"
    assert linha.iniciada_por == "Ana"
    assert linha_de_execucao(exe(situacao="ANDAMENTO", fim=None), set()).duracao == "—"
    falha = linha_de_execucao(exe(situacao="FALHA", erro="TimeoutError: page.goto"), set())
    assert falha.erro and "TimeoutError" in falha.erro_tecnico


# Consultas, filtros e paginação (banco real).


def criar_imp(minutos, **campos):
    inicio = AGORA - timedelta(minutes=minutos)
    padrao = {"tipo": "ESTOQUE", "situacao": "SUCESSO", "inicio": inicio, "fim": inicio}
    return Importacao.objects.create(**{**padrao, **campos})


def criar_exe(minutos, **campos):
    inicio = AGORA - timedelta(minutes=minutos)
    padrao = {"situacao": "SUCESSO", "inicio": inicio, "fim": inicio, "simulacao": True}
    return ExecucaoRobo.objects.create(**{**padrao, **campos})


def historico(**dados):
    form = FiltrosHistorico(dados)
    return SequenciaHistorico(*consultas(form.filtros(), AGORA))


@pytest.mark.django_db
def test_intercala_pelos_inicios_mais_recentes_primeiro():
    criar_imp(30, tipo="CADASTRO")
    criar_exe(20)
    criar_imp(10, tipo="SAIDAS")
    criar_exe(10, simulacao=False)
    linhas = historico()[0:10]
    assert [linha.robo for linha in linhas] == [
        "Lançamento no SCPI",  # empate no início: o lançamento vem antes
        "Saídas",
        "Lançamento no SCPI",
        "Cadastro",
    ]


@pytest.mark.django_db
def test_filtro_por_robo():
    criar_imp(5, tipo="ESTOQUE")
    criar_imp(6, tipo="CADASTRO")
    criar_exe(7)
    assert [linha.robo for linha in historico(robo="estoque")[0:10]] == ["Estoque"]
    assert [linha.robo for linha in historico(robo="lancamento")[0:10]] == ["Lançamento no SCPI"]
    assert historico(robo="inexistente").count() == 3  # valor desconhecido é ignorado


@pytest.mark.django_db
def test_filtro_por_situacao_nos_dois_modelos():
    criar_imp(1, avisos=[])
    criar_imp(2, avisos=["Linhas repetidas: 1."])
    criar_imp(3, situacao="FALHA", erro="x")
    criar_imp(4, situacao="ANDAMENTO", fim=None, inicio=AGORA - timedelta(seconds=10))
    criar_imp(5, situacao="ANDAMENTO", fim=None, inicio=AGORA - timedelta(hours=2))
    criar_exe(6)
    criar_exe(7, situacao="ATENCAO")
    criar_exe(8, situacao="FALHA", erro="y")
    contagem = {
        chave: historico(situacao=chave).count()
        for chave in ("concluida", "com_avisos", "falhou", "andamento", "interrompida")
    }
    assert contagem == {
        "concluida": 2,
        "com_avisos": 2,
        "falhou": 2,
        "andamento": 1,
        "interrompida": 1,
    }
    assert historico(situacao="talvez").count() == 8


@pytest.mark.django_db
def test_filtro_por_periodo_inclui_o_dia_inteiro():
    hoje = timezone.localdate(AGORA)
    meia_noite = timezone.make_aware(datetime.combine(hoje, datetime.min.time()))
    Importacao.objects.create(
        tipo="ESTOQUE", situacao="SUCESSO", inicio=meia_noite + timedelta(hours=23, minutes=59)
    )
    Importacao.objects.create(
        tipo="ESTOQUE", situacao="SUCESSO", inicio=meia_noite - timedelta(minutes=1)
    )
    assert historico(de=hoje.isoformat(), ate=hoje.isoformat()).count() == 1
    assert historico(ate=(hoje - timedelta(days=1)).isoformat()).count() == 1


@pytest.mark.django_db
def test_busca_no_erro_nos_avisos_e_no_registro():
    criar_imp(1, situacao="FALHA", erro="Estoque: arquivo VAZIO.")
    criar_imp(2, avisos=["Texto cortado em nome: 000.001."])
    criar_exe(3, log="10:00 → P-000123 lançada")
    assert historico(q="vazio").count() == 1
    assert historico(q="CORTADO").count() == 1
    assert historico(q="p-000123").count() == 1
    assert historico(q="nada disso").count() == 0


@pytest.mark.django_db
def test_paginas_seguintes_intercalam_certo():
    for i in range(25):
        criar_imp(2 * i + 1)
        criar_exe(2 * i + 2)
    seq = historico()
    assert seq.count() == len(seq) == 50
    segunda = seq[20:40]
    assert len(segunda) == 20
    assert [linha.robo for linha in segunda[:2]] == ["Estoque", "Lançamento no SCPI"]
    inicios = [linha.inicio for linha in seq[0:50]]
    assert inicios == sorted(inicios, reverse=True)


# A página: o cartão Histórico na visão geral.

URL = reverse("automacoes:pagina")


def trecho_historico(html):
    inicio = html.index('<div id="historico"')
    return html[inicio : html.index("<!-- /historico -->", inicio)]


@pytest.mark.django_db
def test_visao_geral_tem_o_formulario_de_filtros_do_painel(client, usuario_logado):
    html = client.get(URL).text
    form = html[html.index('<form class="filtros-recolhiveis"') :]
    form = form[: form.index("</form>")]
    assert "data-filtros" in form and f'action="{URL}"' in form
    assert 'hx-target="#historico"' in form and 'hx-push-url="true"' in form
    assert '<input type="hidden" name="aba" value="visao-geral">' in form
    for campo in ('name="q"', 'name="robo"', 'name="situacao"', 'name="de"', 'name="ate"'):
        assert campo in form, campo
    assert "data-filtros-alternar" in form and "data-filtros-chips" in form
    assert f'href="{URL}?aba=visao-geral#historico"' in form  # Limpar filtros


@pytest.mark.django_db
def test_historico_filtrado_mostra_so_o_que_corresponde(client, usuario_logado):
    criar_imp(5, situacao="FALHA", erro="Estoque: falhou.")
    criar_imp(6, tipo="CADASTRO")
    criar_exe(7)
    html = trecho_historico(client.get(URL, {"robo": "estoque", "situacao": "falhou"}).text)
    assert "1 execução" in html and "filtrada" in html
    assert "Estoque: falhou." in html and "Cadastro" not in html


@pytest.mark.django_db
def test_historico_sem_resultado_oferece_limpar(client, usuario_logado):
    criar_imp(5)
    html = trecho_historico(client.get(URL, {"situacao": "falhou"}).text)
    assert "Nenhuma execução corresponde aos filtros." in html
    assert f'href="{URL}?aba=visao-geral#historico"' in html


@pytest.mark.django_db
def test_historico_vazio_sem_filtro(client, usuario_logado):
    html = trecho_historico(client.get(URL).text)
    assert "Nenhuma execução ainda." in html


@pytest.mark.django_db
def test_regiao_do_historico_com_paginacao(client, usuario_logado):
    for i in range(25):
        criar_imp(i + 1)
    r = client.get(URL, {"pagina": "2"}, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="div#historico")
    assert r.text.lstrip().startswith('<div id="historico"') and "<html" not in r.text
    assert 'aria-label="Paginação do histórico"' in r.text
    assert "25 execuções" in r.text


@pytest.mark.django_db
def test_acompanhamento_do_historico_mantem_filtros_e_pagina(client, usuario_logado):
    criar_imp(1, tipo="SAIDAS", situacao="ANDAMENTO", fim=None, inicio=timezone.now())
    html = client.get(URL, {"aba": "visao-geral", "robo": "saidas", "pagina": "2"}).text
    abertura = html[html.index('<div id="historico"') :]
    abertura = abertura[: abertura.index(">")]
    assert 'hx-trigger="every 5s"' in abertura
    assert "robo=saidas" in abertura and "pagina=2" in abertura
    Importacao.objects.update(situacao="SUCESSO", fim=timezone.now() - timedelta(minutes=5))
    html = client.get(URL).text
    abertura = html[html.index('<div id="historico"') :]
    assert "hx-trigger" not in abertura[: abertura.index(">")]


@pytest.mark.django_db
@pytest.mark.parametrize("chave", ["lancamento", "cadastro", "estoque", "saidas"])
def test_cada_aba_tem_ver_historico(client, usuario_logado, chave):
    html = client.get(URL).text
    painel = html[html.index(f'id="painel-{chave}"') :]
    fim = painel.find('role="tabpanel"', 1)
    painel = painel[: fim if fim > 0 else len(painel)]
    # Navegação de verdade, sem data-abrir-aba: só trocar de aba perderia o filtro do robô.
    assert f'href="{URL}?aba=visao-geral&amp;robo={chave}#historico">Ver histórico' in painel


@pytest.mark.django_db
def test_historicos_antigos_nao_aparecem(client, usuario_logado):
    criar_imp(5)
    criar_exe(6)
    html = client.get(URL).text
    assert "Últimas execuções" not in html
    assert html.count(">Histórico</h2>") == 1
