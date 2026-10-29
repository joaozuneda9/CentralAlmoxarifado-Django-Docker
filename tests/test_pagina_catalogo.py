import re
from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Importacao
from tests.paginas import item_atual

pytestmark = pytest.mark.django_db

SITUACAO = "section#situacao-catalogo"


def catalogo(resposta):
    """A página sem a aba do lançamento, que tem seus próprios botões desabilitados."""
    html = resposta.text
    if 'id="painel-lancamento"' not in html:
        return html
    inicio = html.index('id="painel-lancamento"')
    return html[:inicio] + html[html.index('role="tabpanel"', inicio + 1) :]


def test_pagina_exige_login(client):
    r = client.get(reverse("automacoes:pagina"))
    assert r.status_code == 302 and r.url.startswith(reverse("login"))


def test_pagina_mostra_saude_e_importacoes(client, usuario_logado):
    Importacao.objects.create(
        tipo="ESTOQUE",
        situacao="FALHA",
        erro="Estoque: falhou.",
        fim=timezone.now() - timedelta(minutes=5),
    )
    Importacao.objects.create(
        tipo="SAIDAS",
        situacao="SUCESSO",
        fim=timezone.now() - timedelta(minutes=5),
        linhas=12,
        periodo_de=date(2026, 1, 1),
        periodo_ate=date(2026, 1, 31),
        avisos=["Linhas repetidas no CSV ignoradas: 1."],
    )
    r = client.get(reverse("automacoes:pagina"))
    assert r.status_code == 200
    assert "Nenhuma importação ainda" in catalogo(r)  # o cadastro, na linha da fonte
    assert (
        ">Sem dados<" in catalogo(r) and ">Falhou<" in catalogo(r) and ">Concluída<" in catalogo(r)
    )
    assert "Estoque: falhou." in catalogo(r)
    assert "01/01/2026 a 31/01/2026" in catalogo(r)
    assert "Linhas repetidas no CSV ignoradas" in catalogo(r)
    assert "Precisa de atenção: Cadastro e Estoque." in catalogo(r)
    assert "Atualizar agora" in catalogo(r) and "disabled" not in catalogo(r)
    assert item_atual(catalogo(r), reverse("automacoes:pagina"), "Automações")
    assert "every 5s" not in catalogo(r)


def test_sem_importacoes_mostra_estado_vazio(client, usuario_logado):
    r = client.get(reverse("automacoes:pagina"))
    assert "Nenhuma importação ainda" in catalogo(r)


def test_em_andamento_desabilita_o_botao_e_atualiza_sozinho(client, usuario_logado):
    Importacao.objects.create(tipo="SAIDAS")
    r = client.get(reverse("automacoes:pagina"))
    assert "Importação em andamento" in catalogo(r) and ">Em andamento<" in catalogo(r)
    assert 'hx-trigger="every 5s"' in catalogo(r) and "disabled" in catalogo(r)


def test_interrompida_aparece_como_tal_e_libera_o_botao(client, usuario_logado):
    Importacao.objects.create(tipo="SAIDAS", inicio=timezone.now() - timedelta(hours=2))
    r = client.get(reverse("automacoes:pagina"))
    assert ">Interrompida<" in catalogo(r)
    assert "disabled" not in catalogo(r) and "every 5s" not in catalogo(r)


def test_htmx_recebe_so_o_trecho(client, usuario_logado):
    r = client.get(reverse("automacoes:pagina"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET=SITUACAO)
    assert 'id="situacao-catalogo"' in catalogo(r)
    assert 'class="app-lateral' not in catalogo(r) and "<html" not in catalogo(r)


def test_atualizar_so_por_post(client, usuario_logado):
    assert client.get(reverse("automacoes:atualizar")).status_code == 405


def test_atualizar_exige_login(client):
    r = client.post(reverse("automacoes:atualizar"))
    assert r.status_code == 302 and r.url.startswith(reverse("login"))


def test_atualizar_inicia_e_avisa(client, usuario_logado, monkeypatch):
    monkeypatch.setattr("automacoes.views.iniciar_atualizacao", lambda *a: True)
    r = client.post(reverse("automacoes:atualizar"), follow=True)
    assert r.redirect_chain[-1][0] == reverse("automacoes:pagina") + "?aba=visao-geral"
    assert "Atualização iniciada." in catalogo(r)


def test_atualizar_recusa_quando_ja_em_andamento(client, usuario_logado, monkeypatch):
    monkeypatch.setattr("automacoes.views.iniciar_atualizacao", lambda *a: False)
    r = client.post(reverse("automacoes:atualizar"), follow=True)
    assert "Já há uma importação em andamento. Aguarde terminar." in catalogo(r)


def test_logo_depois_do_disparo_a_pagina_acompanha_e_trava_o_botao(
    client, usuario_logado, monkeypatch
):
    """O processo leva alguns segundos para criar a Importacao: a página seguinte ao clique
    já precisa acompanhar o andamento e não oferecer um segundo disparo."""
    monkeypatch.setattr("automacoes.views.iniciar_atualizacao", lambda *a: True)
    r = client.post(reverse("automacoes:atualizar"), follow=True)
    assert 'hx-trigger="every 5s"' in catalogo(r) and "disabled" in catalogo(r)


def test_segundo_clique_logo_depois_nao_dispara_de_novo(client, usuario_logado, monkeypatch):
    disparos = []
    monkeypatch.setattr(
        "automacoes.views.iniciar_atualizacao", lambda *a: disparos.append(1) or True
    )
    client.post(reverse("automacoes:atualizar"))
    r = client.post(reverse("automacoes:atualizar"), follow=True)
    assert disparos == [1]
    assert "Já há uma importação em andamento. Aguarde terminar." in catalogo(r)


def test_carencia_do_disparo_acaba(client, usuario_logado, monkeypatch):
    monkeypatch.setattr("automacoes.views.iniciar_atualizacao", lambda *a: True)
    client.post(reverse("automacoes:atualizar"))
    sessao = client.session
    sessao["catalogo_disparo_em"] = (timezone.now() - timedelta(minutes=2)).isoformat()
    sessao.save()
    r = client.get(reverse("automacoes:pagina"))
    assert "every 5s" not in catalogo(r) and "disabled" not in catalogo(r)


def test_trecho_do_htmx_traz_o_botao_reabilitado_quando_termina(client, usuario_logado):
    Importacao.objects.create(
        tipo="SAIDAS",
        situacao="SUCESSO",
        inicio=timezone.now() - timedelta(minutes=5),
        fim=timezone.now() - timedelta(minutes=4),
    )
    r = client.get(reverse("automacoes:pagina"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET=SITUACAO)
    assert "Atualizar agora" in catalogo(r) and "disabled" not in catalogo(r)
    assert "every 5s" not in catalogo(r)


def test_continua_acompanhando_logo_depois_de_uma_importacao_terminar(client, usuario_logado):
    """Entre uma importação e a seguinte do mesmo disparo não há nenhuma em andamento."""
    Importacao.objects.create(tipo="CADASTRO", situacao="SUCESSO", fim=timezone.now())
    r = client.get(reverse("automacoes:pagina"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET=SITUACAO)
    assert 'hx-trigger="every 5s"' in catalogo(r) and "disabled" not in catalogo(r)


def test_catalogo_no_estilo_clean(client, usuario_logado):
    r = client.get(reverse("automacoes:pagina"))
    assert 'class="botao botao-primario"' in catalogo(r)


def test_carga_inicial_inicia_com_a_opcao_e_avisa(client, usuario_logado, monkeypatch):
    pedidos = []
    monkeypatch.setattr(
        "automacoes.views.iniciar_atualizacao",
        lambda carga_inicial=False: pedidos.append(carga_inicial) or True,
    )
    r = client.post(
        reverse("automacoes:atualizar"), {"modo": "carga-inicial", "confirmar": "1"}, follow=True
    )
    assert pedidos == [True]
    assert "Carga inicial completa iniciada" in catalogo(r) and "01/01/2026" in catalogo(r)


def test_atualizar_sem_modo_nao_e_carga_inicial(client, usuario_logado, monkeypatch):
    pedidos = []
    monkeypatch.setattr(
        "automacoes.views.iniciar_atualizacao",
        lambda carga_inicial=False: pedidos.append(carga_inicial) or True,
    )
    client.post(reverse("automacoes:atualizar"))
    assert pedidos == [False]


def test_carga_inicial_sem_confirmar_nao_inicia(client, usuario_logado, monkeypatch):
    pedidos = []
    monkeypatch.setattr(
        "automacoes.views.iniciar_atualizacao",
        lambda carga_inicial=False: pedidos.append(carga_inicial) or True,
    )
    r = client.post(reverse("automacoes:atualizar"), {"modo": "carga-inicial"}, follow=True)
    assert pedidos == []
    assert "marque que está ciente" in catalogo(r)


def test_carga_inicial_fica_recolhida_e_explica_o_que_faz(client, usuario_logado):
    r = client.get(reverse("automacoes:pagina"))
    trecho = catalogo(r)[catalogo(r).index('<details class="mais-opcoes">') :]
    trecho = trecho[: trecho.index("</details>")]
    assert 'name="modo" value="carga-inicial"' in trecho
    assert 'name="confirmar" value="1" required' in trecho
    assert "as saídas desde 01/01/2026" in trecho


def test_atualizar_agora_diz_o_que_traz(client, usuario_logado):
    r = client.get(reverse("automacoes:pagina"))
    assert 'aria-describedby="atualizar-o-que-faz"' in catalogo(r)
    assert "Traz os cadastros novos, o saldo de estoque e as saídas" in catalogo(r)


def test_erro_tecnico_vira_uma_frase_com_os_detalhes_recolhidos(client, usuario_logado):
    Importacao.objects.create(
        tipo="CADASTRO",
        situacao="FALHA",
        erro="Falha inesperada: Locator.click: Timeout 30000ms exceeded.\nCall log:\n  - waiting",
        fim=timezone.now(),
    )
    r = client.get(reverse("automacoes:pagina"))
    assert "O SCPI demorou demais para responder e a importação parou." in catalogo(r)
    detalhes = catalogo(r)[catalogo(r).index("<summary>Detalhes técnicos</summary>") :]
    assert detalhes.index("Call log:") < detalhes.index("</details>")


def test_avisos_repetidos_aparecem_agrupados(client, usuario_logado):
    Importacao.objects.create(
        tipo="CADASTRO",
        situacao="SUCESSO",
        fim=timezone.now(),
        linhas=11597,
        avisos=[f"Texto cortado em nome (255 caracteres): 000.00{i}." for i in range(3)],
    )
    r = client.get(reverse("automacoes:pagina"))
    # Uma vez em cada lugar: para conferir, histórico e aba do cadastro.
    assert catalogo(r).count("Texto cortado em nome (255 caracteres)") == 3
    assert "<summary>Ver os 3</summary>" in catalogo(r)
    assert "000.000, 000.001, 000.002" in catalogo(r)
    assert "11.597" in catalogo(r)  # milhar separado no histórico
    assert ">3 avisos<" in catalogo(r)


def test_aba_do_robo_mostra_o_selo_quando_pede_atencao(client, usuario_logado):
    Importacao.objects.create(tipo="ESTOQUE", situacao="FALHA", erro="x.", fim=timezone.now())
    r = client.get(reverse("automacoes:pagina"))
    aba = re.search(r'<button[^>]*id="aba-estoque"[^>]*>(.*?)</button>', catalogo(r), re.S).group(1)
    assert 'class="selo selo-erro aba-selo"' in aba and '<svg class="icone"' in aba
    assert '<span class="aba-selo-texto">Falhou</span>' in aba
    aba = re.search(r'<button[^>]*id="aba-saidas"[^>]*>(.*?)</button>', catalogo(r), re.S).group(1)
    assert 'class="selo selo-erro aba-selo"' in aba and '<svg class="icone"' in aba
    assert '<span class="aba-selo-texto">Sem dados</span>' in aba
    Importacao.objects.create(tipo="SAIDAS", situacao="SUCESSO", fim=timezone.now())
    r = client.get(reverse("automacoes:pagina"))
    aba = re.search(r'<button[^>]*id="aba-saidas"[^>]*>(.*?)</button>', catalogo(r), re.S).group(1)
    assert "selo" not in aba  # em dia: a aba fica limpa


def test_linha_da_fonte_que_falhou_leva_a_aba_do_robo(client, usuario_logado):
    agora = timezone.now()
    Importacao.objects.create(
        tipo="ESTOQUE", situacao="SUCESSO", linhas=10, inicio=agora, fim=agora
    )
    Importacao.objects.create(
        tipo="SAIDAS",
        situacao="SUCESSO",
        linhas=4,
        periodo_de=date(2026, 10, 5),
        periodo_ate=date(2026, 10, 12),
        inicio=agora,
        fim=agora,
    )
    Importacao.objects.create(
        tipo="ESTOQUE",
        situacao="FALHA",
        erro="x.",
        inicio=agora + timedelta(minutes=1),
        fim=agora + timedelta(minutes=1),
    )
    r = client.get(reverse("automacoes:pagina"))
    url = reverse("automacoes:pagina")
    linhas = dict(
        (re.search(r'class="fonte-nome">([^<]+)<', li).group(1), li)
        for li in re.findall(r'<li class="fonte">(.*?)</li>', catalogo(r), re.S)
    )
    # Falhou: o erro vem embaixo e a ação é tentar de novo na aba do robô.
    estoque = linhas["Estoque"]
    assert f'href="{url}?aba=estoque" data-abrir-aba="estoque"' in estoque
    assert "Tentar de novo" in estoque and 'class="fonte-erro"' in estoque
    # Em dia: o número fica separado do complemento, e a ação é discreta.
    saidas = linhas["Saídas do SCPI"]
    assert "4 saídas" in saidas and "· de 05/10/2026 a 12/10/2026" in saidas
    assert 'class="fonte-acao-discreta">Importar' in saidas
    # Sem nenhuma importação: importar, não "tentar de novo".
    assert "Importar" in linhas["Cadastro"] and "Tentar de novo" not in linhas["Cadastro"]


def test_historico_mostra_a_duracao(client, usuario_logado):
    agora = timezone.now()
    Importacao.objects.create(
        tipo="CADASTRO", situacao="SUCESSO", inicio=agora - timedelta(minutes=3), fim=agora
    )
    r = client.get(reverse("automacoes:pagina"))
    assert ">3 min<" in catalogo(r)


def test_aba_do_robo_em_andamento_nao_apresenta_o_inicio_como_dados_em_uso(client, usuario_logado):
    Importacao.objects.create(tipo="SAIDAS")
    r = client.get(reverse("automacoes:pagina"))
    ultima = re.search(r'<div class="robo-ultima">(.*?)</div>', catalogo(r), re.S).group(1)
    assert ", em andamento." in ultima
    assert "Os dados em uso" not in ultima and "Começou às" not in ultima
