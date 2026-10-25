"""O atendimento só aceita o pedido de EPI autorizado (spec 008, US3, FR-023 a FR-025, SC-002):
nenhum atendimento nem linha de saída para o robô antes da autorização, nem para o recusado."""

import re
import uuid
from datetime import date

import pytest
from django.urls import reverse

from pedidos.consultas import lotes_pendentes
from pedidos.models import Atendimento, LinhaSaida
from pedidos.regras import edicao_permitida
from pedidos.servicos import confirmar_atendimento, decidir_autorizacao
from tests.cenario import saida
from tests.epis_cenario import LUVA, montar_epis, registrar, usuarios

pytestmark = pytest.mark.django_db

HOJE = date(2026, 10, 9)
NAO_AUTORIZADO = "ainda não foi autorizado pela Segurança do Trabalho e não pode ser atendido"
RECUSADO = "foi recusado pela Segurança do Trabalho e está encerrado"


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


@pytest.fixture
def quem():
    return usuarios()


def texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def atender(pedido, usuario, qtds=None):
    return confirmar_atendimento(
        pedido.id,
        uuid.uuid4(),
        saida(),
        qtds or {LUVA: "2"},
        nao_lancar=False,
        usuario=usuario,
        hoje=HOJE,
    )


def nada_foi_gravado():
    assert not Atendimento.objects.exists() and not LinhaSaida.objects.exists()
    assert lotes_pendentes() == 0


def autorizar(pedido, quem):
    assert decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"]).ok


def recusar(pedido, quem):
    assert decidir_autorizacao(pedido.numero, "recusar", "Sem laudo", quem["seguranca"]).ok


def test_pedido_aguardando_nao_e_atendido(quem):
    pedido = registrar()
    r = atender(pedido, quem["almox"])
    assert not r.ok and NAO_AUTORIZADO in r.mensagem
    nada_foi_gravado()


def test_pedido_recusado_nao_e_atendido(quem):
    pedido = registrar()
    recusar(pedido, quem)
    r = atender(pedido, quem["almox"])
    assert not r.ok and RECUSADO in r.mensagem
    nada_foi_gravado()


def test_pedido_autorizado_atende_como_os_outros(quem):
    pedido = registrar()
    autorizar(pedido, quem)
    r = atender(pedido, quem["almox"])
    assert r.ok
    linha = LinhaSaida.objects.get()
    assert (linha.codigo, linha.status, str(linha.qtd)) == (LUVA, "PENDENTE", "2.000")
    assert lotes_pendentes() == 1  # o robô passa a ver o lote
    atendimento = Atendimento.objects.get()
    assert edicao_permitida(True, [linha]).permitida  # a edição de sempre, sem nova autorização
    assert atendimento.pedido == pedido


def test_o_reenvio_do_atendimento_autorizado_segue_idempotente(quem):
    pedido = registrar()
    autorizar(pedido, quem)
    identificador = uuid.uuid4()
    for _ in range(2):
        r = confirmar_atendimento(
            pedido.id,
            identificador,
            saida(),
            {LUVA: "2"},
            nao_lancar=False,
            usuario=quem["almox"],
            hoje=HOJE,
        )
        assert r.ok
    assert Atendimento.objects.count() == 1 and LinhaSaida.objects.count() == 1


def post_atender(client, pedido, **extra):
    return client.post(
        reverse("pedidos:atender", args=[pedido.numero]),
        {
            "atendimento_id": str(uuid.uuid4()),
            "data": date.today().isoformat(),
            "recebedor": "Marcos Pereira",
            "centro_custo": "ETA II",
            "tipo": "BALCÃO",
            f"entregue-{LUVA}": "2",
            **extra,
        },
    )


def test_post_forjado_de_atendimento_nao_grava_aguardando_nem_recusado(client, quem):
    client.force_login(quem["almox"])
    aguardando = registrar()
    recusado = registrar(solicitante="Bia Recusada")
    recusar(recusado, quem)
    for pedido in (aguardando, recusado):
        r = post_atender(client, pedido)
        assert r.status_code == 302 and r["Location"] == reverse(
            "pedidos:detalhe", args=[pedido.numero]
        )
    nada_foi_gravado()


def test_post_de_atendimento_do_autorizado_grava(client, quem):
    client.force_login(quem["almox"])
    pedido = registrar()
    autorizar(pedido, quem)
    r = post_atender(client, pedido)
    assert r.status_code == 302
    assert Atendimento.objects.get().pedido == pedido


def test_o_detalhe_aguardando_tem_o_bloqueio_e_nao_tem_o_formulario(client, quem):
    client.force_login(quem["almox"])
    pedido = registrar()
    r = client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
    html = texto(r.text)
    assert "Aguardando autorização" in html
    assert (
        "Este pedido ainda não foi autorizado pela Segurança do Trabalho e não pode ser atendido."
        in html
    )
    assert 'id="form-atendimento"' not in r.text and "Confirmar atendimento" not in html


def test_o_detalhe_recusado_mostra_quem_recusou_e_o_motivo_e_encerra(client, quem):
    client.force_login(quem["almox"])
    pedido = registrar()
    recusar(pedido, quem)
    r = client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
    html = texto(r.text)
    assert "Recusado por Sônia Segura em " in html and "Motivo: Sem laudo" in html
    assert 'id="form-atendimento"' not in r.text


def test_o_detalhe_autorizado_mostra_a_autorizacao_e_o_formulario(client, quem):
    client.force_login(quem["almox"])
    pedido = registrar()
    autorizar(pedido, quem)
    r = client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
    assert "Autorizado por Sônia Segura em " in texto(r.text)
    assert 'id="form-atendimento"' in r.text


def test_busca_e_acrescimo_de_material_so_no_pedido_autorizado(client, quem):
    client.force_login(quem["almox"])
    pedido = registrar()
    materiais = reverse("pedidos:atendimento_materiais", args=[pedido.numero])
    adicionar = reverse("pedidos:atendimento_adicionar", args=[pedido.numero])
    assert client.get(materiais, {"q": "luva"}).status_code == 404
    assert client.post(adicionar, {"codigo": LUVA, "qtd": "1"}).status_code == 404
    autorizar(pedido, quem)
    assert client.get(materiais, {"q": "luva"}).status_code == 200


def test_o_recibo_impresso_nao_muda(client, quem):
    client.force_login(quem["almox"])
    pedido = registrar()
    autorizar(pedido, quem)
    atender(pedido, quem["almox"])
    r = client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
    recibo = r.text.partition('<article class="folha-recibo">')[2]
    assert "Autorizado por" not in recibo.partition("</article>")[0]


def test_a_edicao_nao_abre_caminho_para_atender_o_nao_autorizado(client, quem):
    """POST em `editar` não pode virar atendimento de pedido aguardando ou recusado (FR-023)."""
    client.force_login(quem["almox"])
    aguardando = registrar()
    recusado = registrar(solicitante="Bia Recusada")
    recusar(recusado, quem)
    for pedido in (aguardando, recusado):
        r = client.post(
            reverse("pedidos:editar", args=[pedido.numero]),
            {
                "versao": "0",
                "data": date.today().isoformat(),
                "recebedor": "Marcos Pereira",
                "centro_custo": "ETA II",
                "tipo": "BALCÃO",
                f"entregue-{LUVA}": "2",
            },
        )
        assert r.status_code in (200, 302), pedido.numero
    nada_foi_gravado()
