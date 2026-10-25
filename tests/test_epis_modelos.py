"""Modelos do formulário de EPIs (spec 008): autorização, material avulso e origem."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from catalogo.models import Material, MaterialEpi
from pedidos.models import AutorizacaoPedido, Pedido

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="70001", password="x")


@pytest.fixture
def pedido():
    return Pedido.objects.create(
        id=uuid.uuid4(), numero="P-9001", origem=Pedido.Origem.EPIS, solicitante="Marcos"
    )


def autorizacao(pedido, **campos):
    return AutorizacaoPedido(pedido=pedido, **campos)


def gravar_invalido(obj):
    with pytest.raises(IntegrityError), transaction.atomic():
        obj.save()


def test_a_origem_nova_tem_rotulo():
    assert Pedido.Origem.EPIS.value == "EPIS"
    assert Pedido.Origem.EPIS.label == "Pedido de EPIs"


def test_nasce_aguardando_sem_decisao(pedido):
    a = AutorizacaoPedido.objects.create(pedido=pedido)
    assert a.situacao == AutorizacaoPedido.Situacao.AGUARDANDO
    assert a.decidido_por is None and a.decidido_em is None and a.motivo == ""
    assert pedido.autorizacao_ou_none == a


def test_pedido_sem_autorizacao_devolve_none(pedido):
    assert pedido.autorizacao_ou_none is None


def test_autorizado_exige_quem_e_quando_e_nao_tem_motivo(pedido, usuario):
    agora = timezone.now()
    gravar_invalido(autorizacao(pedido, situacao="AUTORIZADO"))
    gravar_invalido(autorizacao(pedido, situacao="AUTORIZADO", decidido_por=usuario))
    gravar_invalido(
        autorizacao(
            pedido, situacao="AUTORIZADO", decidido_por=usuario, decidido_em=agora, motivo="x"
        )
    )
    autorizacao(pedido, situacao="AUTORIZADO", decidido_por=usuario, decidido_em=agora).save()


def test_recusado_exige_quem_quando_e_motivo(pedido, usuario):
    agora = timezone.now()
    gravar_invalido(autorizacao(pedido, situacao="RECUSADO", decidido_por=usuario))
    gravar_invalido(
        autorizacao(pedido, situacao="RECUSADO", decidido_por=usuario, decidido_em=agora)
    )
    autorizacao(
        pedido, situacao="RECUSADO", decidido_por=usuario, decidido_em=agora, motivo="Sem laudo"
    ).save()


def test_aguardando_nao_aceita_decisao_gravada(pedido, usuario):
    gravar_invalido(autorizacao(pedido, situacao="AGUARDANDO", decidido_por=usuario))
    gravar_invalido(autorizacao(pedido, situacao="AGUARDANDO", decidido_em=timezone.now()))
    gravar_invalido(autorizacao(pedido, situacao="AGUARDANDO", motivo="x"))


def test_uma_autorizacao_por_pedido(pedido):
    AutorizacaoPedido.objects.create(pedido=pedido)
    gravar_invalido(autorizacao(pedido))


def test_apagar_o_pedido_leva_a_autorizacao(pedido):
    AutorizacaoPedido.objects.create(pedido=pedido)
    pedido.delete()
    assert AutorizacaoPedido.objects.count() == 0


def test_quem_decidiu_nao_pode_ser_apagado(pedido, usuario):
    AutorizacaoPedido.objects.create(
        pedido=pedido,
        situacao="AUTORIZADO",
        decidido_por=usuario,
        decidido_em=timezone.now(),
    )
    with pytest.raises(ProtectedError):
        usuario.delete()


def test_material_epi_e_um_por_material_e_protege_o_material():
    material = Material.objects.create(codigo="013.009.001", nome="BOTA", grupo="G")
    MaterialEpi.objects.create(material=material)
    gravar_invalido(MaterialEpi(material=material))
    with pytest.raises(ProtectedError):
        material.delete()


def test_a_migration_cria_o_grupo_da_seguranca_do_trabalho_uma_vez():
    """Chama a função da migration (um teste transacional pode ter esvaziado o grupo)."""
    import importlib

    from django.apps import apps

    from contas.acesso import GRUPO_SEGURANCA_TRABALHO

    migracao = importlib.import_module("contas.migrations.0002_grupo_seguranca_trabalho")
    Group.objects.filter(name=GRUPO_SEGURANCA_TRABALHO).delete()
    migracao.criar_grupo(apps, None)
    migracao.criar_grupo(apps, None)
    assert Group.objects.filter(name=GRUPO_SEGURANCA_TRABALHO).count() == 1
    assert migracao.NOME == GRUPO_SEGURANCA_TRABALHO
