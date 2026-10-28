import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.urls import reverse
from django.utils import timezone

from pedidos.models import TRAVA_LANCAMENTO, ExecucaoRobo, LinhaSaida
from tests.cenario import criar_pedido

pytestmark = pytest.mark.django_db

LANCAMENTOS = reverse("automacoes:pagina") + "?aba=lancamento"


@pytest.fixture
def usuario_logado(client):
    usuario = get_user_model().objects.create_user(username="12345", password="x")
    client.force_login(usuario)
    return usuario


def test_pagina_exige_login(client):
    r = client.get(LANCAMENTOS)
    assert r.status_code == 302 and "entrar" in r.url


def test_pagina_mostra_pendentes_travas_e_formulario(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    p = criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    LinhaSaida.objects.filter(lote=p.numero).update(mensagem="Resultado incerto: Timeout")
    texto = client.get(LANCAMENTOS).text
    assert "1 requisição aguardando o robô" in texto
    assert p.numero in texto and "Resultado incerto: Timeout" in texto
    assert "Conferi no SCPI: a requisição não foi gravada" in texto
    assert reverse("automacoes:resolver", args=[p.numero]) in texto
    assert "every 3s" not in texto


def test_em_andamento_desabilita_botoes_esconde_resolucao_e_acompanha(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    ExecucaoRobo.objects.create(log="10:00:01 → (1/2) P-000001\n")
    texto = client.get(LANCAMENTOS).text
    assert 'hx-trigger="every 3s"' in texto and "→ (1/2) P-000001" in texto
    assert "A resolução fica disponível quando o lançamento terminar." in texto
    assert " disabled" in abertura(botao(form_de_acao(texto), "Lançar no SCPI"))


def painel_lancamento(html):
    """Só a aba Lançamento no SCPI (as outras abas têm seus próprios formulários)."""
    inicio = html.index('id="painel-lancamento"')
    return html[inicio : html.index('role="tabpanel"', inicio + 1)]


def form_de_acao(html):
    """O formulário único do lançamento (a fila com as caixas de marcar e os botões)."""
    achado = re.search(r"<form[^>]*data-fila-robo.*?</form>", html, re.S)
    assert achado, html
    return achado.group(0)


def botao(html, rotulo):
    achado = re.search(rf"<button[^>]*>(?:(?!</button>).)*{rotulo}.*?</button>", html, re.S)
    assert achado, html
    return achado.group(0)


def abertura(tag_html):
    return tag_html[: tag_html.index(">") + 1]


def test_bloqueado_simular_e_a_acao_principal_e_lancar_mostra_o_motivo(
    client, usuario_logado, settings
):
    settings.LANCAMENTO_REAL = False
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    form = form_de_acao(client.get(LANCAMENTOS).text)
    assert form.count("botao-primario") == 1
    assert "botao-primario" in abertura(botao(form, "Simular"))
    lancar = abertura(botao(form, "Lançar no SCPI"))
    assert 'type="button"' in lancar and 'aria-disabled="true"' in lancar
    assert 'aria-describedby="dica-lancamento-real"' in lancar and " disabled" not in lancar
    assert '<rect width="18" height="11"' in botao(form, "Lançar no SCPI")  # cadeado
    assert (
        '<span class="dica-flutuante-texto" role="tooltip" id="dica-lancamento-real">'
        "Lançamento real bloqueado neste ambiente: só a simulação roda.</span>"
    ) in form


def test_liberado_lancar_e_a_acao_principal(client, usuario_logado, settings):
    settings.LANCAMENTO_REAL = True
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    form = form_de_acao(client.get(LANCAMENTOS).text)
    lancar = abertura(botao(form, "Lançar no SCPI"))
    assert 'type="submit"' in lancar and 'name="modo"' in lancar and 'value="lancar"' in lancar
    assert "botao-primario" in lancar and form.count("botao-primario") == 1
    assert "botao-secundario" in abertura(botao(form, "Simular"))
    assert "dica-lancamento-real" not in form


def test_um_formulario_so_com_a_fila_marcavel_e_sem_limite(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    html = painel_lancamento(client.get(LANCAMENTOS).text)
    assert "Executar com opções" not in html and 'type="radio"' not in html
    assert 'name="limite"' not in html and "Só as primeiras" not in html
    assert html.count(f'action="{reverse("automacoes:lancar")}"') == 1
    form = form_de_acao(html)
    caixa = re.search(r"<input[^>]*name=\"lotes\"[^>]*>", form).group(0)
    assert f'value="{p.numero}"' in caixa and " disabled" not in caixa
    assert "data-fila-todas" in form and "Marcar todas as requisições" in form
    simular = abertura(botao(form, "Simular"))
    assert 'name="modo"' in simular and 'value="simular"' in simular
    assert "data-requer-selecao" in simular


def test_em_andamento_desabilita_botoes_e_caixas_e_diz_o_motivo(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    ExecucaoRobo.objects.create()
    form = form_de_acao(client.get(LANCAMENTOS).text)
    assert " disabled" in abertura(botao(form, "Simular"))
    assert " disabled" in abertura(botao(form, "Lançar no SCPI"))
    assert re.search(r"<input[^>]*name=\"lotes\"[^>]*disabled", form)
    assert "botao-primario" not in form and "Há uma execução em andamento." in form


def test_fila_vazia_desabilita_botoes_e_diz_o_motivo(client, usuario_logado):
    html = client.get(LANCAMENTOS).text
    form = form_de_acao(html)
    assert " disabled" in abertura(botao(form, "Simular"))
    assert 'name="lotes"' not in form
    assert "botao-primario" not in form and "Nada aguardando o robô." in fila_da_pagina(html)


def test_lotes_marcados_valem_para_o_botao_escolhido(client, usuario_logado, monkeypatch):
    a = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    b = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    chamadas = []
    monkeypatch.setattr(
        "automacoes.views.iniciar_lancamento",
        lambda u, **k: chamadas.append(k) or object(),
    )
    url = reverse("automacoes:lancar")
    client.post(url, {"modo": "simular", "lotes": [b.numero]})
    assert chamadas == [{"simulacao": True, "lotes": [b.numero]}]
    client.post(url, {"modo": "simular", "lotes": [a.numero, b.numero]})
    assert chamadas[1]["lotes"] == [a.numero, b.numero]


def test_sem_lote_marcado_o_envio_e_recusado(client, usuario_logado, monkeypatch):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    monkeypatch.setattr(
        "automacoes.views.iniciar_lancamento", lambda *a, **k: pytest.fail("não deveria iniciar")
    )
    r = client.post(reverse("automacoes:lancar"), {"modo": "simular"}, follow=True)
    assert "Marque ao menos uma requisição da fila." in r.text


def test_lote_que_saiu_da_fila_e_recusado(client, usuario_logado, monkeypatch):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    LinhaSaida.objects.filter(lote=p.numero).update(status="LANCADA", requisicao_scpi="000001/26")
    monkeypatch.setattr(
        "automacoes.views.iniciar_lancamento", lambda *a, **k: pytest.fail("não deveria iniciar")
    )
    r = client.post(
        reverse("automacoes:lancar"), {"modo": "simular", "lotes": [p.numero]}, follow=True
    )
    assert f"A requisição {p.numero} não está mais na fila do robô." in r.text


def test_lancamento_real_liberado_tem_confirmacao_que_envia_o_mesmo_formulario(
    client, usuario_logado, settings
):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    settings.LANCAMENTO_REAL = True
    html = client.get(LANCAMENTOS).text
    assert "data-confirmar-lancamento" in form_de_acao(html)
    dialogo = re.search(r'<dialog[^>]*id="dialogo-lancar".*?</dialog>', html, re.S).group(0)
    assert 'form="fila-form"' in dialogo and 'value="lancar"' in dialogo
    assert 'id="fila-form"' in form_de_acao(html)
    settings.LANCAMENTO_REAL = False
    assert 'id="dialogo-lancar"' not in client.get(LANCAMENTOS).text


def fila_da_pagina(html):
    """A região da fila: a barra com a contagem e a tabela, até o marcador `/fila`."""
    achado = re.search(r"<form[^>]*data-fila-robo.*?<!-- /fila -->", html, re.S)
    assert achado, html
    return achado.group(0)


def test_fila_lista_as_requisicoes_que_o_robo_lancaria(client, usuario_logado):
    a = criar_pedido(atendido=True, linhas=[("PENDENTE", ""), ("PENDENTE", "")], recebedor="Bia")
    b = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    travado = criar_pedido(atendido=True, linhas=[("PENDENTE", ""), ("VERIFICAR", "")])
    html = client.get(LANCAMENTOS).text
    fila = fila_da_pagina(html)
    assert "2 requisições aguardando o robô" in fila
    for pedido in (a, b):
        link = f'<a class="mono" href="{reverse("pedidos:detalhe", args=[pedido.numero])}">'
        assert link + pedido.numero + "</a>" in fila
    assert travado.numero not in fila and travado.numero in html
    linha_a = re.search(rf"<tr[^>]*>(?:(?!</tr>).)*{a.numero}.*?</tr>", fila, re.S).group(0)
    hoje = timezone.localdate().strftime("%d/%m/%Y")
    for dado in (hoje, "Bia", "ETA II", ">2<"):
        assert dado in linha_a, dado


def test_fila_mostra_todas_as_requisicoes(client, usuario_logado):
    for _ in range(21):
        criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    fila = fila_da_pagina(client.get(LANCAMENTOS).text)
    assert "21 requisições aguardando o robô" in fila
    assert fila.count('<a class="mono"') == 21 and "e mais" not in fila
    assert fila.count('name="lotes"') == 21


def test_fila_vazia_nao_tem_tabela(client, usuario_logado):
    fila = fila_da_pagina(client.get(LANCAMENTOS).text)
    assert "Nada aguardando o robô." in fila and "<table" not in fila


def test_htmx_recebe_so_o_trecho(client, usuario_logado):
    r = client.get(LANCAMENTOS, headers={"HX-Request": "true", "HX-Target": "section#lancamentos"})
    assert r.text.lstrip().startswith("<section") and "app-menu" not in r.text


def test_lancar_inicia_e_avisa(client, usuario_logado, monkeypatch):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    chamadas = []
    monkeypatch.setattr(
        "automacoes.views.iniciar_lancamento",
        lambda u, simulacao, lotes: chamadas.append((u, simulacao)) or object(),
    )
    r = client.post(
        reverse("automacoes:lancar"), {"simulacao": "1", "lotes": [p.numero]}, follow=True
    )
    assert chamadas == [(usuario_logado, True)]
    assert "Simulação iniciada" in r.text


def test_lancar_recusa_em_andamento(client, usuario_logado, monkeypatch):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    monkeypatch.setattr("automacoes.views.iniciar_lancamento", lambda u, simulacao, lotes: None)
    r = client.post(reverse("automacoes:lancar"), {"lotes": [p.numero]}, follow=True)
    assert "Já há um lançamento em andamento" in r.text


def test_lancar_e_resolver_so_por_post(client, usuario_logado):
    assert client.get(reverse("automacoes:lancar")).status_code == 405
    assert client.get(reverse("automacoes:resolver", args=["P-000001"])).status_code == 405


def test_resolver_mostra_o_resultado(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    url = reverse("automacoes:resolver", args=[p.numero])
    r = client.post(url, {"acao": "lancada", "requisicao": "3354/26"}, follow=True)
    assert "Informe o número da requisição no formato 000000/00." in r.text
    r = client.post(url, {"acao": "lancada", "requisicao": "003354/26"}, follow=True)
    assert f"Lote {p.numero}: requisição 003354/26 registrada." in r.text


def test_painel_mostra_cartao_de_lancamentos(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    criar_pedido(atendido=True, linhas=[("ERRO", "")])
    texto = client.get(reverse("pedidos:painel")).text
    assert "requisição aguardando o robô" in texto and "1 para conferir" in texto
    assert reverse("automacoes:lancar") in texto and LANCAMENTOS in texto


def test_detalhe_com_trava_aponta_para_a_resolucao(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("ERRO", "")])
    texto = client.get(reverse("pedidos:detalhe", args=[p.numero])).text
    assert f'href="{LANCAMENTOS}#travas">Resolver em Automações</a>' in texto


def test_execucao_recem_terminada_nao_recarrega_e_mostra_a_resolucao(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    ExecucaoRobo.objects.create(situacao="SUCESSO", fim=timezone.now() - timedelta(seconds=5))
    texto = client.get(LANCAMENTOS).text
    assert "every 3s" not in texto
    assert reverse("automacoes:resolver", args=[p.numero]) in texto
    assert "Informar requisição" in texto


def test_execucao_longa_com_a_trava_segue_acompanhada_e_sem_trava_e_interrompida(
    client, usuario_logado
):
    ExecucaoRobo.objects.create(inicio=timezone.now() - timedelta(hours=2))
    outra = connections.create_connection("default")
    try:
        with outra.cursor() as c:
            c.execute("SELECT GET_LOCK(%s, 0)", [TRAVA_LANCAMENTO])
        texto = painel_lancamento(client.get(LANCAMENTOS).text)
        assert 'hx-trigger="every 3s"' in texto and "Interrompida" not in texto
    finally:
        outra.close()
    texto = painel_lancamento(client.get(LANCAMENTOS).text)
    assert "every 3s" not in texto and "Interrompida" in texto


def test_nao_lancar_sem_confirmacao_e_recusado(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    LinhaSaida.objects.filter(lote=p.numero).update(mensagem="Resultado incerto")
    url = reverse("automacoes:resolver", args=[p.numero])
    r = client.post(url, {"acao": "nao_lancar"}, follow=True)
    assert "Confirme antes de marcar para não lançar." in r.text
    linha = LinhaSaida.objects.get(lote=p.numero)
    assert (linha.status, linha.mensagem) == ("VERIFICAR", "Resultado incerto")
    r = client.post(url, {"acao": "nao_lancar", "confirmado": "1"}, follow=True)
    assert f"Lote {p.numero} marcado para não lançar no SCPI." in r.text
    assert LinhaSaida.objects.get(lote=p.numero).status == "NAO_LANCAR"


def test_liberar_e_informar_nao_pedem_a_confirmacao(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("ERRO", "")])
    url = reverse("automacoes:resolver", args=[p.numero])
    client.post(url, {"acao": "liberar"})
    assert LinhaSaida.objects.get(lote=p.numero).status == "PENDENTE"


def test_nao_lancar_vem_num_segundo_passo_com_formulario_proprio(client, usuario_logado):
    p = criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    html = client.get(LANCAMENTOS).text
    assert "every 3s" not in html
    confirmar = re.search(r'<details class="confirmar-nao-lancar">.*?</details>', html, re.S).group(
        0
    )
    assert re.search(r"<summary[^>]*>\s*Não lançar", confirmar)
    assert (
        f'A requisição de <span class="mono">{p.numero}</span> não será lançada no SCPI.'
        in confirmar
    )
    form = re.search(r"<form.*?</form>", confirmar, re.S).group(0)
    assert f'action="{reverse("automacoes:resolver", args=[p.numero])}"' in form
    assert "csrfmiddlewaretoken" in form
    assert '<input type="hidden" name="acao" value="nao_lancar">' in form
    assert '<input type="hidden" name="confirmado" value="1">' in form
    assert "Confirmar: não lançar" in form
    resolucao = re.search(r'<form[^>]*class="resolucao".*?</form>', html, re.S).group(0)
    assert 'value="nao_lancar"' not in resolucao and "Liberar para relançar" in resolucao


def test_confirmacao_nunca_fica_num_trecho_recarregado(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    ExecucaoRobo.objects.create()
    html = client.get(LANCAMENTOS).text
    assert "every 3s" in html and "confirmar-nao-lancar" not in html


def test_desistir_fecha_a_confirmacao_e_aparece_depois_da_recarga():
    from django.contrib.staticfiles import finders

    with open(finders.find("pedidos/js/pedidos.js"), encoding="utf-8") as f:
        js = f.read()
    assert "[data-desistir]" in js and ".open = false" in js
    assert re.search(r'addEventListener\("htmx:after:swap", mostrarDesistir\)', js)
    assert re.search(r'addEventListener\("DOMContentLoaded", mostrarDesistir\)', js)


def andamento_da_pagina(html):
    achado = re.search(r'<div[^>]*id="andamento".*?<!-- /andamento -->', html, re.S)
    assert achado, html
    return achado.group(0)


def test_falha_de_simulacao_explicada_com_detalhe_e_simular_de_novo(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    ExecucaoRobo.objects.create(
        simulacao=True,
        situacao="FALHA",
        fim=timezone.now(),
        erro="Falha inesperada: You cannot call this from an async context",
        resumo={"requisicoes": 3, "processadas": 1},
        log="10:00:01 → (1/3) P-000001\n",
    )
    andamento = andamento_da_pagina(client.get(LANCAMENTOS).text)
    aviso = re.search(r'<div class="aviso aviso-erro" role="alert">.*?</div>', andamento, re.S)
    assert aviso and "O robô parou por um erro do sistema." in aviso.group(0)
    assert "Chegou a processar 1 de 3 requisições." in andamento
    assert "Nenhuma linha mudou de estado." in andamento and "Falhou" in andamento
    detalhe = re.search(
        r"<details[^>]*>\s*<summary>Detalhe técnico</summary>.*?</details>", andamento, re.S
    )
    assert detalhe and " open>" not in detalhe.group(0)
    assert "You cannot call this from an async context" in detalhe.group(0)
    assert "→ (1/3) P-000001" in detalhe.group(0)
    assert "<form" not in andamento and "Simular de novo" not in andamento


def test_falha_de_lancamento_real_nao_tem_atalho_para_relancar(client, usuario_logado):
    ExecucaoRobo.objects.create(
        simulacao=False,
        situacao="FALHA",
        fim=timezone.now(),
        erro="Falha inesperada: x",
        resumo={"requisicoes": 2, "processadas": 1},
        log="x\n",
    )
    html = client.get(LANCAMENTOS).text
    andamento = andamento_da_pagina(html)
    assert "Simular de novo" not in andamento and 'value="lancar"' not in andamento
    assert "Confira as travas abaixo antes de lançar de novo." in andamento
    assert 'href="#travas"' in andamento and 'id="travas"' in html


def test_andamento_de_simulacao_concluida_numa_frase(client, usuario_logado):
    inicio = timezone.now() - timedelta(minutes=2)
    ExecucaoRobo.objects.create(
        simulacao=True,
        situacao="SUCESSO",
        inicio=inicio,
        fim=inicio + timedelta(minutes=2),
        iniciada_por=usuario_logado,
        resumo={"requisicoes": 3, "processadas": 3, "simuladas": 3},
    )
    andamento = andamento_da_pagina(client.get(LANCAMENTOS).text)
    assert re.search(
        r"Simulação de hoje, \d\d:\d\d, concluída: 3 de 3 requisições preenchidas.", andamento
    )
    assert "Iniciada por 12345" in andamento and "2 min" in andamento
    assert "3 simuladas" in andamento
    for antigo in ("Falhas", "Ignoradas", "Lançadas", '<dl class="dados">', "#travas"):
        assert antigo not in andamento, antigo


def test_andamento_com_pendencias_mostra_contadores_e_atalho(client, usuario_logado):
    ExecucaoRobo.objects.create(
        situacao="ATENCAO",
        fim=timezone.now(),
        resumo={"requisicoes": 2, "processadas": 2, "lancadas": 1, "verificar": 1},
    )
    andamento = andamento_da_pagina(client.get(LANCAMENTOS).text)
    assert "1 lançada" in andamento and "1 para verificar" in andamento
    assert 'href="#travas"' in andamento


def test_andamento_em_execucao_mostra_o_progresso_e_acompanha(client, usuario_logado):
    ExecucaoRobo.objects.create(resumo={"requisicoes": 5, "processadas": 1}, log="10:00 → (2/5)\n")
    html = client.get(LANCAMENTOS).text
    assert "requisição 2 de 5" in andamento_da_pagina(html)
    assert 'hx-trigger="every 3s"' in html
    assert re.search(
        r"<details[^>]* open>\s*<summary>Registro da execução", andamento_da_pagina(html)
    )


def test_textos_falam_em_requisicao_e_sem_rotulo_repetido(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    criar_pedido(atendido=True, linhas=[("VERIFICAR", "")])
    ExecucaoRobo.objects.create(
        situacao="SUCESSO", fim=timezone.now(), log="", resumo={"requisicoes": 1, "lancadas": 1}
    )
    html = client.get(LANCAMENTOS).text
    visivel = re.sub(r"<[^>]+>", " ", html[html.index("<main") :])
    assert not re.search(r"\blotes?\b", visivel, re.I), re.findall(
        r".{40}\blote.{40}", visivel, re.I
    )
    assert '<p class="rotulo-secao">SCPI</p>' not in html
    assert '<p class="rotulo-secao"></p>' in html


def test_sem_travas_uma_linha_so(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    html = client.get(LANCAMENTOS).text
    assert re.search(r'<p[^>]*id="travas"[^>]*>Nenhuma trava para conferir.</p>', html)
    assert "Travas para conferir" not in html


def test_pagina_vazia_sem_cartoes_vazios(client, usuario_logado):
    html = client.get(LANCAMENTOS).text
    assert "Nada aguardando o robô." in html and "Nenhuma execução ainda." in html
    for titulo in ("Andamento", "Últimas execuções", "Travas para conferir"):
        assert f">{titulo}</h2>" not in html, titulo


@pytest.mark.parametrize("quantas", [1, 2])
def test_mensagem_diz_quais_requisicoes_foram_escolhidas(
    client, usuario_logado, monkeypatch, quantas
):
    numeros = [
        criar_pedido(atendido=True, linhas=[("PENDENTE", "")]).numero for _ in range(quantas)
    ]
    monkeypatch.setattr("automacoes.views.iniciar_lancamento", lambda u, **k: object())
    r = client.post(
        reverse("automacoes:lancar"), {"modo": "simular", "lotes": numeros}, follow=True
    )
    assert f"{', '.join(numeros)}." in r.text
