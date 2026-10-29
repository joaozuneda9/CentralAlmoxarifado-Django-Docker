import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Material
from pedidos.models import LinhaSaida, Pedido
from pedidos.regras import AB, EnvioSaida
from pedidos.servicos import registrar_saida_avulsa
from tests.cenario import envio_ab, itens, montar_cenario, registrar, saida, textos

pytestmark = pytest.mark.django_db
HOJE = date(2026, 10, 9)


@pytest.fixture
def usuario():
    montar_cenario()
    # A saída avulsa só lista material com saldo: o "ITEM ANTIGO" do cenário vem zerado.
    Material.objects.filter(codigo="000.000.900").update(estoque=Decimal(10))
    return get_user_model().objects.create_user(username="12345", password="x")


def avulsa(envio_id, envio, usuario):
    return registrar_saida_avulsa(envio_id, envio, usuario=usuario, hoje=HOJE)


def test_avulsa_na_mesma_sequencia_e_reenvio_sem_duplicar(usuario):
    registrar(AB, envio_ab())  # P-000001
    envio_id = uuid.uuid4()
    s = EnvioSaida(saida(data="2026-10-01"), itens(("000.000.900", "1,5")))
    r = avulsa(envio_id, s, usuario)
    assert (r.ok, r.numero) == (True, "AV-000002")
    assert avulsa(envio_id, s, usuario).reenvio
    linha = LinhaSaida.objects.get()
    assert (linha.qtd, linha.lote, linha.status, linha.descricao) == (
        Decimal("1.5"),
        "AV-000002",
        "PENDENTE",
        "ITEM ANTIGO",
    )
    p = Pedido.objects.get(numero="AV-000002")
    assert (p.registrado_por, p.solicitante, p.situacao.chave, p.atendimento.id) == (
        usuario,
        "",
        "atendido",
        envio_id,
    )
    item = p.itens.get()
    assert (item.qtd_pedida, item.qtd_entregue, item.grupo) == (
        Decimal("1.5"),
        Decimal("1.5"),
        "GERAL",
    )


def test_divergente(usuario):
    envio_id = uuid.uuid4()
    avulsa(envio_id, EnvioSaida(saida(), itens(("000.000.900", "1"))), usuario)
    r = avulsa(envio_id, EnvioSaida(saida(obs="outra"), itens(("000.000.900", "1"))), usuario)
    assert (r.ok, r.divergente) == (False, True)
    assert Pedido.objects.count() == 1


def test_recusas(usuario):
    um = itens(("000.000.900", "1"))
    r = avulsa(uuid.uuid4(), EnvioSaida(saida(placa="ABC1D23"), um), usuario)
    assert textos(r) == [
        'A placa ABC1D23 pertence ao centro de custo "PICKUP 01". Escolha esse centro ou '
        "limpe a placa."
    ]
    assert r.mensagem == "Corrija os itens abaixo."
    r = avulsa(uuid.uuid4(), EnvioSaida(saida(), itens(("030.004.001", "1"))), usuario)
    assert textos(r) == ["Material 030.004.001 não encontrado no cadastro."]
    r = avulsa(uuid.uuid4(), EnvioSaida(saida(), itens(("000.000.900", "1.5"))), usuario)
    assert "Quantidade inválida para 000.000.900 (use vírgula para decimais)." in textos(r)
    r = avulsa(uuid.uuid4(), EnvioSaida(saida()), usuario)
    assert "Adicione ao menos um material." in textos(r)
    assert not Pedido.objects.exists()


def test_pagina_exige_login(client):
    for nome in ("pedidos:avulsa", "pedidos:avulsa_materiais"):
        assert client.get(reverse(nome)).status_code == 302
    assert client.post(reverse("pedidos:avulsa_carrinho")).status_code == 302


def dados_post(envio_id, **extra):
    dados = {
        "envio_id": str(envio_id),
        "data": timezone.localdate().isoformat(),
        "recebedor": "João Fictício",
        "centro_custo": "ETA II",
        "tipo": "BALCÃO",
        "placa": "",
        "obs": "",
        "item_codigo": ["000.000.900"],
        "item_qtd": ["2"],
    }
    dados.update(extra)
    return dados


def test_pagina_registra_e_leva_ao_detalhe(client, usuario):
    client.force_login(usuario)
    r = client.get(reverse("pedidos:avulsa"))
    assert 'name="envio_id"' in r.text and reverse("pedidos:avulsa_materiais") in r.text
    r = client.post(reverse("pedidos:avulsa"), dados_post(uuid.uuid4()))
    assert r.status_code == 302 and r.url == reverse("pedidos:detalhe", args=["AV-000001"])
    texto = client.get(r.url).text
    assert "Saída avulsa registrada: Nº AV-000001." in texto
    assert "Registrar outra saída" in texto


def test_pedido_em_secao_propria_com_o_botao_dentro_do_cartao(client, usuario):
    client.force_login(usuario)
    html = client.get(reverse("pedidos:avulsa")).text
    inicio = html.index('<aside class="pedido-lado"')
    fim = html.index("</aside>", inicio)  # o primeiro </aside> da página é o da barra lateral
    passos = html[html.index('class="pedido-passos') : inicio]
    assert passos.count('class="passo cartao"') == 2 and 'id="carrinho"' not in passos
    lado = html[inicio:fim]
    assert 'id="carrinho"' in lado and "Registrar saída" in lado and 'class="pedido-enviar"' in lado
    assert fim < html.index('class="acoes acoes-final"')


def test_centro_de_custo_tem_dica_para_quando_a_placa_o_define(client, usuario):
    # O pedidos.js trava o dropdown do centro enquanto há placa; o <select> segue habilitado
    # (campo desabilitado não iria no envio) e a dica começa escondida.
    client.force_login(usuario)
    r = client.get(reverse("pedidos:avulsa"))
    assert '<span id="centro_custo-dica" class="campo-nota" hidden>' in r.text
    centro = '<select id="centro_custo" class="campo-entrada" name="centro_custo"'
    assert centro + " data-dropdown-digitavel>" in r.text
    # A placa também é um select digitável (campo de texto como o do recebedor, que filtra a lista).
    assert 'name="placa" data-dropdown-digitavel>' in r.text


def test_pagina_com_erro_mantem_o_carrinho(client, usuario):
    client.force_login(usuario)
    r = client.post(reverse("pedidos:avulsa"), dados_post(uuid.uuid4(), tipo=""))
    assert r.status_code == 200
    assert "Selecione o Tipo Saída do SCPI." in r.text
    assert 'name="item_codigo" value="000.000.900"' in r.text
    assert 'value="João Fictício"' in r.text
    r = client.post(reverse("pedidos:avulsa"), dados_post("x"))
    assert "Identificador do envio inválido. Recarregue a página." in r.text


def test_busca_da_avulsa_traz_o_cadastro_sem_ocultos(client, usuario):
    client.force_login(usuario)
    texto = client.get(reverse("pedidos:avulsa_materiais"), {"q": "a"}).text
    assert "ITEM ANTIGO" in texto and "CAPACETE" not in texto
    r = client.post(
        reverse("pedidos:avulsa_carrinho"), {"adicionar": "000.000.900", "qtd-000.000.900": "1,5"}
    )
    assert 'name="item_qtd" value="1,5"' in r.text


def test_avulsa_em_dois_passos(client, usuario):
    client.force_login(usuario)
    r = client.get(reverse("pedidos:avulsa"))
    for numero, titulo in (("01", "Dados da saída"), ("02", "Materiais")):
        assert f'<span class="passo-numero" aria-hidden="true">{numero}</span>' in r.text
        assert f"<h2>{titulo}</h2>" in r.text


def test_resultados_da_avulsa_mantem_o_codigo(client, usuario):
    client.force_login(usuario)
    texto = client.get(reverse("pedidos:avulsa_materiais"), {"q": "000.000.900"}).text
    dados = texto[texto.index('<div class="material-dados">') :]
    assert "ITEM ANTIGO" in dados[: dados.index("</div>")]
    assert "000.000.900" in dados[: dados.index("</div>")]
