"""Decisão da Segurança do Trabalho sobre o pedido de EPI (spec 008, US2, FR-011 a FR-016,
FR-021): autorizar ou recusar, uma vez, só quem é do grupo."""

import pytest

from pedidos.models import AutorizacaoPedido, ItemPedido, Pedido, Sequencia
from pedidos.servicos import decidir_autorizacao
from tests.cenario import em_paralelo
from tests.epis_cenario import montar_epis, registrar, usuarios

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cenario():
    montar_epis()


@pytest.fixture
def quem():
    return usuarios()


def recarregar(pedido):
    return AutorizacaoPedido.objects.get(pedido=pedido)


def test_autorizar_grava_quem_e_quando(quem):
    pedido = registrar()
    r = decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    assert r.ok and r.autorizacao.situacao == "AUTORIZADO"
    a = recarregar(pedido)
    assert (a.situacao, a.decidido_por, a.motivo) == ("AUTORIZADO", quem["seguranca"], "")
    assert a.decidido_em is not None
    assert Pedido.objects.get(pk=pedido.pk).situacao.chave == "aguardando"  # a atender


def test_autorizar_ignora_o_motivo_enviado(quem):
    pedido = registrar()
    decidir_autorizacao(pedido.numero, "autorizar", "texto solto", quem["seguranca"])
    assert recarregar(pedido).motivo == ""


def test_recusar_exige_o_motivo(quem):
    pedido = registrar()
    for motivo in ["", "   "]:
        r = decidir_autorizacao(pedido.numero, "recusar", motivo, quem["seguranca"])
        assert not r.ok and r.motivo == "motivo"
        assert r.mensagem == "Informe o motivo da recusa."
    assert recarregar(pedido).situacao == "AGUARDANDO"


def test_recusar_com_motivo_grava_e_encerra(quem):
    pedido = registrar()
    r = decidir_autorizacao(
        pedido.numero, "recusar", " EPI já entregue em março ", quem["seguranca"]
    )
    assert r.ok
    a = recarregar(pedido)
    assert (a.situacao, a.motivo, a.decidido_por) == (
        "RECUSADO",
        "EPI já entregue em março",
        quem["seguranca"],
    )
    assert Pedido.objects.get(pk=pedido.pk).situacao.chave == "recusado"


def test_o_motivo_tem_o_limite_dos_textos(quem, settings):
    pedido = registrar()
    settings.PEDIDOS_MAX_TEXTO = 10  # depois do registro: o nome do pedido já passaria do limite
    r = decidir_autorizacao(pedido.numero, "recusar", "x" * 11, quem["seguranca"])
    assert not r.ok and r.motivo == "motivo" and "no máximo 10" in r.mensagem
    assert recarregar(pedido).situacao == "AGUARDANDO"


def test_a_decisao_e_definitiva(quem):
    pedido = registrar()
    decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    antes = recarregar(pedido)
    for decisao, motivo in [("autorizar", ""), ("recusar", "mudei de ideia")]:
        r = decidir_autorizacao(pedido.numero, decisao, motivo, quem["seguranca"])
        assert not r.ok and r.motivo == "ja_decidida"
        assert r.autorizacao.decidido_por == quem["seguranca"]
        assert r.mensagem.startswith("Este pedido já foi autorizado por Sônia Segura em ")
    depois = recarregar(pedido)
    assert (depois.situacao, depois.decidido_em, depois.motivo) == (
        antes.situacao,
        antes.decidido_em,
        antes.motivo,
    )


def test_recusado_tambem_nao_volta(quem):
    pedido = registrar()
    decidir_autorizacao(pedido.numero, "recusar", "sem laudo", quem["seguranca"])
    r = decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    assert not r.ok and r.motivo == "ja_decidida"
    assert r.mensagem.startswith("Este pedido já foi recusado por Sônia Segura em ")
    assert recarregar(pedido).situacao == "RECUSADO"


@pytest.mark.parametrize("papel", ["almox", "admin"])
def test_so_o_grupo_da_seguranca_do_trabalho_decide(quem, papel):
    """O almoxarifado e até o administrador (superusuário) sem o grupo são negados (FR-021)."""
    pedido = registrar()
    r = decidir_autorizacao(pedido.numero, "autorizar", "", quem[papel])
    assert not r.ok and r.motivo == "grupo"
    assert recarregar(pedido).situacao == "AGUARDANDO"


def test_so_pedido_com_autorizacao_e_decidido(quem):
    import uuid

    from pedidos.regras import AB
    from pedidos.servicos import registrar_pedido
    from tests.cenario import envio_ab

    ab = registrar_pedido(AB, uuid.uuid4(), envio_ab()).pedido
    assert decidir_autorizacao(ab.numero, "autorizar", "", quem["seguranca"]).motivo == (
        "nao_encontrada"
    )
    assert decidir_autorizacao("P-999999", "autorizar", "", quem["seguranca"]).motivo == (
        "nao_encontrada"
    )


def test_decisao_invalida_nao_grava(quem):
    pedido = registrar()
    r = decidir_autorizacao(pedido.numero, "talvez", "", quem["seguranca"])
    assert not r.ok and r.motivo == "decisao"
    assert recarregar(pedido).situacao == "AGUARDANDO"


def test_a_decisao_nao_altera_itens_destino_nem_observacao(quem):
    pedido = registrar()
    antes = (
        pedido.solicitante,
        pedido.destino,
        pedido.obs,
        list(ItemPedido.objects.filter(pedido=pedido).values_list("codigo", "qtd_pedida")),
    )
    decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    pedido = Pedido.objects.get(pk=pedido.pk)
    depois = (
        pedido.solicitante,
        pedido.destino,
        pedido.obs,
        list(ItemPedido.objects.filter(pedido=pedido).values_list("codigo", "qtd_pedida")),
    )
    assert antes == depois


def test_desativar_o_usuario_nao_muda_a_decisao_gravada(quem):
    pedido = registrar()
    decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    quem["seguranca"].is_active = False
    quem["seguranca"].save()
    a = recarregar(pedido)
    assert a.situacao == "AUTORIZADO" and a.decidido_por == quem["seguranca"]


def test_nenhuma_decisao_e_tomada_por_tempo(quem, settings):
    """O pedido sem decisão espera (FR-016): não há rotina que o autorize ou recuse sozinho."""
    pedido = registrar()
    Pedido.objects.filter(pk=pedido.pk).update(criado_em="2020-01-01T00:00:00Z")
    assert recarregar(pedido).situacao == "AGUARDANDO"


@pytest.mark.django_db(transaction=True)
def test_decisoes_simultaneas_valem_so_a_primeira():
    montar_epis()
    Sequencia.objects.get_or_create(nome="PEDIDOS")
    quem = usuarios()
    outro = type(quem["seguranca"]).objects.create_user(username="70009", password="x")
    outro.groups.add(*quem["seguranca"].groups.all())
    pedido = registrar()
    resultados = em_paralelo(
        lambda: decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"]),
        lambda: decidir_autorizacao(pedido.numero, "recusar", "não", outro),
    )
    assert sorted(r.ok for r in resultados) == [False, True]
    perdedor = next(r for r in resultados if not r.ok)
    vencedor = next(r for r in resultados if r.ok)
    assert perdedor.motivo == "ja_decidida"
    final = recarregar(pedido)
    assert final.situacao == vencedor.autorizacao.situacao
    assert final.decidido_por == vencedor.autorizacao.decidido_por
