"""O centro de custo inativo (spec 009, US5; FR-008, FR-012): some dos formulários públicos e da
saída avulsa **nova**; atendimento, edição (inclusive de saída avulsa já registrada) e robô seguem
resolvendo qualquer centro, para pedido e lote pendente não travarem."""

import uuid
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalogo.models import CentroCusto, Formulario, Material
from pedidos.models import LinhaSaida, Pedido
from pedidos.regras import LIMPEZA, EnvioSaida
from pedidos.servicos import (
    centros,
    centros_ativos,
    confirmar_atendimento,
    editar_atendimento,
    editar_saida_avulsa,
    registrar_saida_avulsa,
)
from scpi.requisicoes import selecionar
from tests.cenario import envio_limpeza, itens, montar_cenario, registrar, saida
from tests.config_cenario import criar_centro

pytestmark = pytest.mark.django_db

HOJE = date(2026, 10, 9)
TUDO = {"023.001.002": "2", "008.001.002": "1,5"}


@pytest.fixture
def usuario():
    montar_cenario()
    return get_user_model().objects.create_user(username="12345", password="x", first_name="Ana")


def inativar(descricao="ETA II"):
    CentroCusto.objects.filter(descricao=descricao).update(ativo=False)


def atender(usuario, **extra):
    pedido = registrar(LIMPEZA, envio_limpeza()).pedido
    r = confirmar_atendimento(
        pedido.id, uuid.uuid4(), saida(**extra), TUDO, nao_lancar=False, usuario=usuario, hoje=HOJE
    )
    assert r.ok, r.erros
    pedido.refresh_from_db()
    return pedido


def nova_avulsa(usuario, **extra):
    return registrar_saida_avulsa(
        uuid.uuid4(),
        EnvioSaida(saida(**extra), itens(("023.004.001", "1"))),
        usuario=usuario,
        hoje=HOJE,
    )


# --- Quem continua resolvendo ------------------------------------------------------------------


def test_o_atendimento_resolve_o_centro_inativo(usuario):
    pedido = registrar(LIMPEZA, envio_limpeza()).pedido
    inativar()
    r = confirmar_atendimento(
        pedido.id, uuid.uuid4(), saida(), TUDO, nao_lancar=False, usuario=usuario, hoje=HOJE
    )
    assert r.ok, r.erros
    assert {linha.centro_custo for linha in LinhaSaida.objects.all()} == {"ETA II"}


def test_a_edicao_do_atendimento_mantem_o_centro_inativo(usuario):
    pedido = atender(usuario)
    inativar()
    r = editar_atendimento(
        pedido.id,
        pedido.versao,
        saida(recebedor="Maria"),
        TUDO,
        nao_lancar=False,
        adicionados=(),
        usuario=usuario,
        hoje=HOJE,
    )
    assert r.ok, r.erros
    assert LinhaSaida.objects.first().centro_custo == "ETA II"


def test_a_edicao_de_saida_avulsa_ja_registrada_mantem_o_centro_inativo(usuario):
    avulsa = nova_avulsa(usuario).pedido
    inativar()
    r = editar_saida_avulsa(
        avulsa.id,
        avulsa.versao,
        EnvioSaida(saida(recebedor="Maria"), itens(("023.004.001", "2"))),
        usuario=usuario,
        hoje=HOJE,
    )
    assert r.ok, r.erros


def test_o_robo_resolve_o_lote_pendente_de_centro_inativo(usuario):
    atender(usuario)
    inativar()
    sel = selecionar(list(LinhaSaida.objects.all()), centros())
    (req,) = sel.requisicoes
    assert not req.erro and req.cod_ccusto == "14"


def test_o_pedido_antigo_continua_com_o_destino_de_um_centro_inativo(usuario, client):
    criar_centro("SETOR PARADO", "88", formularios=[Formulario.LIMPEZA])
    r = registrar(
        LIMPEZA,
        envio_limpeza(),
    )
    assert r.ok
    pedido = Pedido.objects.get()
    CentroCusto.objects.filter(descricao="SETOR PARADO").update(ativo=False)
    pedido.refresh_from_db()
    assert pedido.destino == r.pedido.destino


# --- Quem deixa de oferecer --------------------------------------------------------------------


def test_centros_ativos_deixa_de_fora_so_o_inativo(usuario):
    assert {c.descricao for c in centros_ativos()} == {c.descricao for c in centros()}
    inativar()
    assert "ETA II" not in {c.descricao for c in centros_ativos()}
    assert "ETA II" in {c.descricao for c in centros()}


def test_a_saida_avulsa_nova_recusa_o_centro_inativo(usuario):
    assert nova_avulsa(usuario).ok
    inativar()
    r = nova_avulsa(usuario)
    assert not r.ok
    assert any('O centro de custo "ETA II" não está na lista' in e.texto for e in r.erros)
    assert Pedido.objects.filter(origem="AVULSA").count() == 1


def test_a_tela_da_saida_avulsa_nova_nao_oferece_o_centro_inativo(usuario, client):
    inativar()
    client.force_login(usuario)
    html = client.get(reverse("pedidos:avulsa")).text
    assert "ETA I" in html and '<option value="ETA II"' not in html


def test_a_edicao_da_saida_avulsa_ainda_oferece_o_centro_inativo(usuario, client):
    avulsa = nova_avulsa(usuario).pedido
    inativar()
    client.force_login(usuario)
    html = client.get(reverse("pedidos:editar", args=[avulsa.numero])).text
    assert '<option value="ETA II"' in html


def test_o_detalhe_do_atendimento_ainda_oferece_o_centro_inativo(usuario, client):
    pedido = registrar(LIMPEZA, envio_limpeza()).pedido
    inativar()
    client.force_login(usuario)
    html = client.get(reverse("pedidos:detalhe", args=[pedido.numero])).text
    assert '<option value="ETA II"' in html


def test_reativar_devolve_o_centro_a_saida_avulsa_nova(usuario):
    inativar()
    assert not nova_avulsa(usuario).ok
    CentroCusto.objects.filter(descricao="ETA II").update(ativo=True)
    assert nova_avulsa(usuario).ok


def test_o_material_nao_depende_do_estado_do_centro(usuario):
    inativar()
    assert Material.objects.filter(codigo="023.004.001").exists()
