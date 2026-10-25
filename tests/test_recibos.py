from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.urls import reverse

from pedidos.models import Pedido
from pedidos.regras import AVULSA
from pedidos.servicos import marcar_recibos_impressos
from tests.cenario import criar_pedido

pytestmark = pytest.mark.django_db
ANTES = datetime(2026, 10, 1, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


@pytest.fixture
def logado(client):
    usuario = get_user_model().objects.create_user(username="12345", password="x")
    client.force_login(usuario)
    return usuario


def test_recibo_nao_mostra_quem_registrou(client):
    registrador = get_user_model().objects.create_user(
        username="77777", password="x", first_name="Registrador"
    )
    client.force_login(registrador)
    numero = criar_pedido(origem=AVULSA, atendido=True, usuario=registrador).numero
    r = client.get(reverse("pedidos:detalhe", args=[numero]))
    # A página (fora do recibo, que é o que sai na impressão) mostra quem registrou; o recibo, não.
    recibo = r.text[r.text.index('<article class="folha-recibo') :]
    recibo = recibo[: recibo.index("</article>")]
    assert numero in recibo
    assert "Registrador" not in recibo and "77777" not in recibo
    assert "Registrador" in r.text


def test_marca_so_os_nao_impressos_e_uma_vez():
    a = criar_pedido(atendido=True).atendimento
    b = criar_pedido(atendido=True).atendimento
    b.recibo_impresso_em = ANTES
    b.save()
    assert marcar_recibos_impressos([a.id, b.id]) == 1
    assert marcar_recibos_impressos([a.id, b.id]) == 0
    b.refresh_from_db()
    assert b.recibo_impresso_em == ANTES


def test_painel_filtra_os_recibos_nao_impressos(client, logado):
    pendente = criar_pedido(atendido=True)
    impresso = criar_pedido(atendido=True)
    impresso.atendimento.recibo_impresso_em = ANTES
    impresso.atendimento.save()
    sem = criar_pedido()
    lista = client.get(reverse("pedidos:painel"), {"recibo": "pendente"}).text
    lista = lista[lista.index("<tbody") :]
    assert pendente.numero in lista
    assert impresso.numero not in lista and sem.numero not in lista
    lista = client.get(reverse("pedidos:painel"), {"recibo": "impresso"}).text
    lista = lista[lista.index("<tbody") :]
    assert impresso.numero in lista and pendente.numero not in lista


def test_marcar_pela_pagina(client, logado):
    a = criar_pedido(atendido=True).atendimento
    b = criar_pedido(atendido=True).atendimento
    url = reverse("pedidos:marcar_impressos")
    voltar = reverse("pedidos:painel") + "?recibo=pendente"
    r = client.post(url, {"atendimento": [str(a.id), "lixo"], "voltar": voltar})
    assert r.status_code == 302 and r.url == voltar
    assert "1 recibo marcado como impresso." in client.get(reverse("pedidos:painel")).text
    client.post(url, {"atendimento": [str(a.id), str(b.id)], "voltar": voltar})
    assert "1 recibo marcado como impresso." in client.get(reverse("pedidos:painel")).text
    c = criar_pedido(atendido=True).atendimento
    d = criar_pedido(atendido=True).atendimento
    client.post(url, {"atendimento": [str(c.id), str(d.id)]})
    assert "2 recibos marcados como impressos." in client.get(reverse("pedidos:painel")).text
    r = client.post(url, {"atendimento": [str(c.id)], "voltar": "https://evil.example/"})
    assert r.url == reverse("pedidos:painel")
    assert (
        "Nenhum recibo novo para marcar: todos já estavam marcados como impressos."
        in client.get(reverse("pedidos:painel")).text
    )


def test_exigem_login_e_marcar_so_por_post(client, logado):
    assert client.get(reverse("pedidos:marcar_impressos")).status_code == 405
    client.logout()
    assert client.post(reverse("pedidos:marcar_impressos")).status_code == 302


def test_links_no_painel_e_no_detalhe(client, logado):
    p = criar_pedido(atendido=True)
    criar_pedido(atendido=True)
    assert "Nenhum recibo pendente" not in client.get(reverse("pedidos:painel")).text
    painel = client.get(reverse("pedidos:painel")).text
    assert "recibos para imprimir" in painel and "?recibo=pendente" in painel
    detalhe = client.get(reverse("pedidos:detalhe", args=[p.numero])).text
    assert "Imprimir recibo" in detalhe


def test_material_do_recibo_em_uma_linha(client, logado):
    numero = criar_pedido(atendido=True).numero
    r = client.get(reverse("pedidos:detalhe", args=[numero]))
    tabela = r.text[r.text.index('class="tabela recibo-itens"') :]
    tabela = tabela[: tabela.index("</table>")]
    assert "<br>" not in tabela
    assert '<span class="mono recibo-codigo">023.001.002</span> <strong>' in tabela


def test_assinaturas_lado_a_lado_e_impressao_compacta(client, logado):
    numero = criar_pedido(atendido=True).numero
    r = client.get(reverse("pedidos:detalhe", args=[numero]))
    assinaturas = r.text[r.text.index('<div class="assinaturas">') :]
    assinaturas = assinaturas[: assinaturas.index("</div>")]
    assert "<p>Entregue por:</p>" in assinaturas and "<p>Recebido por:</p>" in assinaturas
    assert "___" not in assinaturas  # a linha vem do CSS e cabe em meia largura
    texto = Path(finders.find("pedidos/css/pedidos.css")).read_text(encoding="utf-8")
    regra = texto[texto.index(".assinaturas {") :]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in regra[: regra.index("}")]
    impressao = texto[texto.index("@media print") :]
    assert "@page" in impressao and ".recibo-itens td" in impressao


def test_assinaturas_so_aparecem_na_impressao():
    texto = Path(finders.find("pedidos/css/pedidos.css")).read_text(encoding="utf-8")
    base = texto[texto.index(".assinaturas {") :]
    assert "display: none" in base[: base.index("}")]
    impressao = texto[texto.index("@media print") :]
    assert ".assinaturas { display: grid;" in impressao


def test_recibo_mostra_a_requisicao_do_scpi(client, logado):
    numero = criar_pedido(atendido=True, linhas=[("LANCADA", "003354/26")]).numero
    pagina = client.get(reverse("pedidos:detalhe", args=[numero])).text
    assert (
        "<dt>Requisição SCPI</dt>" in pagina
        and '<span class="mono">003354/26</span></dd>' in pagina
    )
    # Sem número ainda, o campo fica só na tela, com o traço; e a tabela não tem mais a coluna SCPI.
    sem = client.get(reverse("pedidos:detalhe", args=[criar_pedido(atendido=True).numero])).text
    assert '<div class="so-tela"><dt>Requisição SCPI</dt><dd><span class="texto-secundario">' in sem
    assert '<th scope="col" class="so-tela">SCPI</th>' not in sem


def test_scpi_com_problema_vira_selo_e_passo_na_situacao(client, logado):
    numero = criar_pedido(atendido=True, linhas=[("VERIFICAR", "")]).numero
    pagina = client.get(reverse("pedidos:detalhe", args=[numero])).text
    assert (
        '<dt>Requisição SCPI</dt><dd><span class="selo selo-erro">Verificar no SCPI</span>'
        in pagina
    )
    assert (
        "<li>Verificar no SCPI: o robô não concluiu o lançamento. "
        "Confira e resolva em Automações › Lançamento no SCPI.</li>" in pagina
    )


def test_detalhe_imprime_o_recibo_e_confirma_a_impressao(client, logado):
    p = criar_pedido(atendido=True)
    url = reverse("pedidos:detalhe", args=[p.numero])
    detalhe = client.get(url).text
    # O botão imprime a própria página; sem JavaScript fica escondido, e a confirmação, à vista
    # (o diálogo vem com `open`; com JavaScript, o pedidos.js o fecha e só o abre ao imprimir).
    assert '<button type="button" class="botao botao-primario" data-imprimir hidden>' in detalhe
    assert '<dialog class="confirmacao-impressao nao-imprimir" open' in detalhe
    assert "data-impressao-adiar" in detalhe
    css = open(finders.find("pedidos/css/pedidos.css"), encoding="utf-8").read()
    assert ".js .confirmacao-impressao:not(:modal) { display: none; }" in css
    assert '<article class="folha-recibo">' in detalhe
    assert f'name="atendimento" value="{p.atendimento.id}"' in detalhe
    r = client.post(
        reverse("pedidos:marcar_impressos"), {"atendimento": p.atendimento.id, "voltar": url}
    )
    assert r.status_code == 302 and r["Location"] == url
    # Já impresso, a confirmação não aparece mais.
    assert "confirmacao-impressao" not in client.get(url).text


# A confirmação de impresso confere a versão do pedido: a impressão de uma versão anterior
# (outra aba, antes de uma edição) não marca a versão nova.


def test_marcar_impresso_com_versao_antiga_e_ignorado():
    p = criar_pedido(atendido=True)
    Pedido.objects.filter(pk=p.pk).update(versao=1)
    a = p.atendimento
    assert marcar_recibos_impressos([a.id], versoes={a.id: 0}) == 0
    a.refresh_from_db()
    assert a.recibo_impresso_em is None
    assert marcar_recibos_impressos([a.id], versoes={a.id: 1}) == 1


def test_detalhe_manda_a_versao_na_confirmacao(client, logado):
    p = criar_pedido(atendido=True)
    r = client.get(reverse("pedidos:detalhe", args=[p.numero]))
    assert f'name="versao-{p.atendimento.id}" value="0"' in r.text


def test_view_avisa_quando_o_pedido_mudou(client, logado):
    p = criar_pedido(atendido=True)
    Pedido.objects.filter(pk=p.pk).update(versao=1)
    a = p.atendimento
    client.post(
        reverse("pedidos:marcar_impressos"), {"atendimento": str(a.id), f"versao-{a.id}": "0"}
    )
    painel = client.get(reverse("pedidos:painel")).text
    assert "O pedido foi alterado depois de abrir esta página; imprima de novo." in painel
    assert "Nenhum recibo novo para marcar" not in painel
    a.refresh_from_db()
    assert a.recibo_impresso_em is None
