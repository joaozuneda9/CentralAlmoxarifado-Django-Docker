import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Importacao
from pedidos.consultas import OPCOES_SCPI, OPCOES_SITUACAO, filtrar_scpi, filtrar_situacao
from pedidos.models import ExecucaoRobo, ItemPedido, Pedido
from pedidos.regras import AB, AVULSA
from tests.cenario import criar_pedido

pytestmark = pytest.mark.django_db

LANCAMENTOS = reverse("automacoes:pagina") + "?aba=lancamento"
SP = ZoneInfo("America/Sao_Paulo")

COMBINACOES_SCPI = [
    None,
    [],
    [("NAO_LANCAR", "")],
    [("PENDENTE", ""), ("PENDENTE", "")],
    [("LANCADA", "003354/26"), ("PENDENTE", "")],
    [("LANCADA", "1/26"), ("LANCADA", "2/26")],
    [("VERIFICAR", ""), ("LANCADA", "1/26")],
    [("ERRO", "")],
    [("EM_LANCAMENTO", "")],
    [("NAO_LANCAR", ""), ("LANCADA", "1/26")],
    [("PENDENTE", "9/26")],
    [("ERRO", "9/26")],
]


@pytest.fixture
def logado(client):
    usuario = get_user_model().objects.create_user(username="12345", password="x")
    client.force_login(usuario)
    return usuario


def _acrescentar(pedido, no_lugar_de, entregue):
    usuario = get_user_model().objects.get_or_create(username="almox")[0]
    return ItemPedido.objects.create(
        pedido=pedido,
        codigo="999.999.999",
        material="MATERIAL EXTRA",
        unidade="UN",
        origem=ItemPedido.Origem.ALMOXARIFADO,
        qtd_pedida=None,
        qtd_entregue=entregue,
        adicionado_por=usuario,
        no_lugar_de=no_lugar_de,
    )


def test_filtros_de_situacao_concordam_com_as_regras():
    for linhas in COMBINACOES_SCPI:
        criar_pedido(atendido=linhas is not None, linhas=linhas or ())
    criar_pedido(atendido=True, entregues=("1",))
    criar_pedido(origem=AVULSA, atendido=True)
    # Trocas: acrescentado entregue no lugar do item (atendido), entregue 0 (parcial) e só extra.
    trocas = []
    for entregue_extra in (Decimal("1"), Decimal("0")):
        p = criar_pedido(atendido=True, entregues=("0",))
        _acrescentar(p, p.itens.get(), entregue_extra)
        trocas.append(p)
    p = criar_pedido(atendido=True)
    _acrescentar(p, None, Decimal("3"))
    trocas.append(p)
    todos = list(Pedido.objects.all())
    for chave, _ in OPCOES_SCPI:
        esperado = {p for p in todos if p.situacao_scpi.chave == chave}
        assert set(filtrar_scpi(Pedido.objects.all(), chave)) == esperado, chave
    for chave, _ in OPCOES_SITUACAO:
        esperado = {p for p in todos if p.situacao.chave == chave}
        assert set(filtrar_situacao(Pedido.objects.all(), chave)) == esperado, chave
    chaves = [Pedido.objects.get(pk=p.pk).situacao.chave for p in trocas]
    assert chaves == ["atendido", "parcial", "atendido"]
    assert {c for c, _ in OPCOES_SCPI} == {"sem", "aguardando", "lancado", "parcial", "atencao"}


def test_painel_exige_login(client):
    r = client.get(reverse("pedidos:painel"))
    assert r.status_code == 302


def test_lista_mais_recentes_primeiro_com_situacao_e_scpi(client, logado):
    agora = timezone.now()
    antigo = criar_pedido(criado_em=agora - timedelta(days=2))
    novo = criar_pedido(criado_em=agora)
    r = client.get(reverse("pedidos:painel"))
    assert r.text.index(novo.numero) < r.text.index(antigo.numero)
    assert "Aguardando atendimento" in r.text and "Aguarda o atendimento" in r.text


def test_filtro_por_origem(client, logado):
    limpeza = criar_pedido()
    ab = criar_pedido(origem=AB)
    r = client.get(reverse("pedidos:painel"), {"origem": "AB"})
    assert ab.numero in r.text and limpeza.numero not in r.text


def test_busca_por_numero_solicitante_e_recebedor_sem_acento(client, logado):
    a = criar_pedido(solicitante="Mariana")
    b = criar_pedido(atendido=True, recebedor="João")
    c = criar_pedido(solicitante="Zé")
    url = reverse("pedidos:painel")
    assert a.numero in client.get(url, {"q": "mariana"}).text
    texto = client.get(url, {"q": "joao"}).text
    assert b.numero in texto and a.numero not in texto
    assert c.numero in client.get(url, {"q": c.numero}).text


def test_periodo_inclui_o_dia_final_inteiro(client, logado):
    dentro = criar_pedido(criado_em=datetime(2026, 10, 5, 23, 30, tzinfo=SP))
    fora = criar_pedido(criado_em=datetime(2026, 10, 6, 0, 10, tzinfo=SP))
    antes = criar_pedido(criado_em=datetime(2026, 10, 3, 23, 59, tzinfo=SP))
    texto = client.get(reverse("pedidos:painel"), {"de": "2026-10-04", "ate": "2026-10-05"}).text
    assert dentro.numero in texto
    assert fora.numero not in texto and antes.numero not in texto


def test_paginacao_de_25(client, logado):
    for _ in range(30):
        criar_pedido()
    r = client.get(reverse("pedidos:painel"))
    assert "Página 1 de 2" in r.text
    r2 = client.get(reverse("pedidos:painel"), {"pagina": 2}, HTTP_HX_REQUEST="true")
    assert r2.text.count('class="mono numero-pedido"') == 5


def test_htmx_devolve_so_a_lista(client, logado):
    criar_pedido()
    r = client.get(reverse("pedidos:painel"), HTTP_HX_REQUEST="true")
    assert 'class="app-lateral' not in r.text and "P-000001" in r.text


def test_quadro_de_saude(client, logado):
    assert "Catálogo em dia." not in client.get(reverse("pedidos:painel")).text
    Importacao.objects.create(
        tipo="ESTOQUE", situacao="FALHA", erro="Estoque: deu errado.", fim=timezone.now()
    )
    r = client.get(reverse("pedidos:painel"))
    assert "Saúde do catálogo" in r.text and "Estoque: deu errado." in r.text


def test_catalogo_em_dia(client, logado, monkeypatch):
    monkeypatch.setattr("pedidos.views.almoxarifado.saude_do_catalogo", lambda: [])
    assert "Catálogo em dia." in client.get(reverse("pedidos:painel")).text


def test_consultas_limitadas(client, logado, django_assert_max_num_queries):
    for _ in range(25):
        criar_pedido(atendido=True, linhas=[("PENDENTE", ""), ("LANCADA", "1/26")])
    with django_assert_max_num_queries(12):
        r = client.get(reverse("pedidos:painel"), HTTP_HX_REQUEST="true")
    assert r.status_code == 200


def test_painel_no_estilo_clean(client, logado):
    criar_pedido()
    r = client.get(reverse("pedidos:painel"))
    assert 'class="filtros-recolhiveis"' in r.text and 'class="campo-busca"' in r.text
    assert 'class="selo selo-info"' in r.text
    tabela = r'<div class="tabela-rolagem">\s*<table class="tabela tabela-pedidos">'
    assert re.search(tabela, r.text)
    assert 'class="campo-entrada"' in r.text  # widgets do FiltrosPainel


def test_selo_de_origem_da_lista_e_curto_com_o_nome_inteiro_no_title(client, logado):
    criar_pedido()
    criar_pedido(origem=AB)
    r = client.get(reverse("pedidos:painel"))
    assert (
        '<span class="selo selo-neutro" title="Limpeza, copa/cozinha e escritório">Limpeza</span>'
        in r.text
    )
    assert '<span class="selo selo-neutro" title="Materiais AB">Materiais AB</span>' in r.text


def test_saude_do_catalogo_fica_no_fim_do_painel(client, logado):
    texto = client.get(reverse("pedidos:painel")).text
    assert texto.index('id="lista-pedidos"') < texto.index("Saúde do catálogo")
    assert texto.index("Atalhos") < texto.index("Saúde do catálogo")


def _atalhos(client):
    texto = client.get(reverse("pedidos:painel")).text
    corpo = texto[texto.index('<section class="cartao atalhos">') :]
    return texto, corpo[: corpo.index("</section>")]


def _botao_desabilitado(atalhos, rotulo):
    botao = re.search(r"<button[^>]*>(?:(?!</button>).)*" + rotulo, atalhos, re.S)
    assert botao, rotulo
    return " disabled" in botao.group(0).split(">", 1)[0]


def test_atalhos_sao_cartoes_com_contador_e_o_cabecalho_fica_sem_botoes(client, logado):
    criar_pedido()
    criar_pedido(atendido=True)
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    texto, atalhos = _atalhos(client)
    assert re.findall(r'<p class="atalho-numero">([0-9]+)</p>', atalhos) == ["1", "2", "1"]
    assert atalhos.count("atalho-pendente") == 3
    # Os atalhos que filtram a lista abrem a página rolada até ela (`#pedidos`).
    assert f"{reverse('pedidos:painel')}?situacao=aguardando#pedidos" in atalhos
    assert f"{reverse('pedidos:painel')}?recibo=pendente#pedidos" in atalhos
    assert 'id="pedidos"' in client.get(reverse("pedidos:painel")).text
    # Os dois chegam com a lista à vista (rolagem animada) e o painel de filtros recolhido.
    assert atalhos.count('data-rolar-ate="pedidos" data-fechar-filtros') == 2
    for rota in ("automacoes:lancar", "pedidos:avulsa"):
        assert reverse(rota) in atalhos
    cabecalho = texto[texto.index("<header") : texto.index("</header>")]
    assert "Saída avulsa" not in cabecalho and "Imprimir recibos" not in cabecalho
    # com requisição aguardando o robô, lançar fica habilitado; simular e atualizar o catálogo
    # ficam na página Automações
    assert not _botao_desabilitado(atalhos, "Lançar no SCPI")
    assert "Simular lançamento" not in atalhos and "Atualizar catálogo" not in atalhos


def test_atalhos_em_dia_ficam_apagados_e_sem_destino(client, logado):
    _, atalhos = _atalhos(client)
    assert "atalho-pendente" not in atalhos
    assert re.findall(r'<p class="atalho-numero">([0-9]+)</p>', atalhos) == ["0", "0", "0"]
    assert "Nenhum pedido aguardando." in atalhos and "Nenhum recibo pendente." in atalhos
    assert atalhos.count('aria-disabled="true"') == 2
    assert "?recibo=pendente" not in atalhos
    # sem requisição aguardando o robô, não há o que lançar
    assert _botao_desabilitado(atalhos, "Lançar no SCPI")


def test_atalho_avisa_lotes_para_conferir(client, logado):
    criar_pedido(atendido=True, linhas=[("ERRO", "")])
    _, atalhos = _atalhos(client)
    assert "1 para conferir" in atalhos and f'href="{LANCAMENTOS}#travas"' in atalhos


def test_saude_leva_a_automacoes(client, logado):
    texto = client.get(reverse("pedidos:painel")).text
    assert f'href="{reverse("automacoes:pagina")}">Ver automações' in texto


def test_cartao_conta_as_requisicoes_pela_regra_do_robo(client, logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", ""), ("VERIFICAR", "")])
    _, atalhos = _atalhos(client)
    assert "Nada aguardando o robô." in atalhos and "1 para conferir" in atalhos
    assert _botao_desabilitado(atalhos, "Lançar no SCPI")
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    _, atalhos = _atalhos(client)
    assert "requisição aguardando o robô" in atalhos
    assert not _botao_desabilitado(atalhos, "Lançar no SCPI")
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    _, atalhos = _atalhos(client)
    assert "requisições aguardando o robô" in atalhos and "lote" not in atalhos


def test_lancar_fica_desabilitado_com_execucao_em_andamento(client, logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    ExecucaoRobo.objects.create(log="10:00:01")
    _, atalhos = _atalhos(client)
    assert _botao_desabilitado(atalhos, "Lançar no SCPI")


def test_filtros_de_situacao_concordam_com_a_autorizacao_da_seguranca_do_trabalho():
    """Pedido de EPI: aguardando ou recusado não é "aguardando atendimento" em lugar nenhum
    (spec 008); autorizado segue a regra de sempre (e a sem autorização não muda)."""
    from pedidos.models import AutorizacaoPedido

    usuario = get_user_model().objects.create_user(username="70001", password="x")
    for situacao, atendido in [
        (None, False),
        (None, True),
        ("AGUARDANDO", False),
        ("RECUSADO", False),
        ("AUTORIZADO", False),
        ("AUTORIZADO", True),
    ]:
        pedido = criar_pedido(origem="EPIS" if situacao else AB, atendido=atendido)
        if situacao:
            decidido = situacao != "AGUARDANDO"
            AutorizacaoPedido.objects.create(
                pedido=pedido,
                situacao=situacao,
                decidido_por=usuario if decidido else None,
                decidido_em=timezone.now() if decidido else None,
                motivo="Sem laudo" if situacao == "RECUSADO" else "",
            )
    todos = list(Pedido.objects.all())
    chaves = {p.situacao.chave for p in todos}
    assert {"aguardando_autorizacao", "recusado"} <= chaves
    for chave, _ in OPCOES_SITUACAO:
        esperado = {p for p in todos if p.situacao.chave == chave}
        assert set(filtrar_situacao(Pedido.objects.all(), chave)) == esperado, chave
    # Quem aguarda ou foi recusado não aparece em filtro de situação algum.
    for chave, _ in OPCOES_SITUACAO:
        achados = {p.situacao.chave for p in filtrar_situacao(Pedido.objects.all(), chave)}
        assert not achados & {"aguardando_autorizacao", "recusado"}
