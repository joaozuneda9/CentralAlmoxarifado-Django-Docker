"""Regras da tabela de rotas (spec 012, research R3): `pode`, `regra_da_rota`, `pode_abrir` e
`sem_papel`, com os usuários e grupos reais do banco."""

import pytest
from django.contrib.auth.models import AnonymousUser, Group, Permission

from contas.acesso import (
    ADMIN,
    AUTOMACOES,
    GRUPO_ATENDIMENTO,
    GRUPO_GESTAO,
    GRUPO_SEGURANCA_TRABALHO,
    PUBLICA,
    SEGURANCA,
    Regra,
    pode,
    pode_abrir,
    regra_da_rota,
    sem_papel,
)
from tests.papeis import usuario_com

pytestmark = pytest.mark.django_db

AUTOMACOES_REGRA = Regra((AUTOMACOES,), "motivo")
DE_STAFF = Regra(("catalogo.change_centrocusto",), "motivo", exige_staff=True)


def test_pode_recusa_anonimo_e_inativo():
    assert not pode(AnonymousUser(), AUTOMACOES_REGRA)
    inativo = usuario_com(GRUPO_GESTAO, is_active=False)
    assert not pode(inativo, AUTOMACOES_REGRA)


def test_pode_segue_as_permissoes_dos_grupos():
    assert not pode(usuario_com(GRUPO_ATENDIMENTO), AUTOMACOES_REGRA)
    assert pode(usuario_com(GRUPO_GESTAO, username="2"), AUTOMACOES_REGRA)


def test_pode_exige_staff_quando_a_regra_pede():
    sem_staff = usuario_com(username="1")
    sem_staff.user_permissions.add(Permission.objects.get(codename="change_centrocusto"))
    com_staff = usuario_com(username="2", is_staff=True)
    com_staff.user_permissions.add(Permission.objects.get(codename="change_centrocusto"))
    assert not pode(sem_staff, DE_STAFF)
    assert pode(com_staff, DE_STAFF)


def test_superusuario_passa_em_toda_regra():
    chefe = usuario_com(is_superuser=True, is_staff=True)
    assert pode(chefe, AUTOMACOES_REGRA) and pode(chefe, DE_STAFF)


def test_regra_da_rota_por_categoria():
    assert regra_da_rota("pedidos:inicio") == PUBLICA
    assert regra_da_rota("admin:index") == ADMIN
    assert regra_da_rota("admin:contas_usuario_changelist") == ADMIN
    assert regra_da_rota("pedidos:decidir") == SEGURANCA
    assert isinstance(regra_da_rota("automacoes:lancar"), Regra)
    assert regra_da_rota("rota:que_nao_existe") is None
    assert regra_da_rota(None) is None


def test_pode_abrir_rota_fora_da_tabela_so_o_superusuario():
    assert not pode_abrir(usuario_com(GRUPO_ATENDIMENTO, GRUPO_GESTAO), "rota:nova")
    assert pode_abrir(usuario_com(username="2", is_superuser=True), "rota:nova")


def test_pode_abrir_publica_admin_e_seguranca():
    comum = usuario_com(GRUPO_ATENDIMENTO)
    assert pode_abrir(AnonymousUser(), "pedidos:inicio")
    assert not pode_abrir(comum, "admin:index")
    assert pode_abrir(usuario_com(username="2", is_staff=True), "admin:index")
    assert not pode_abrir(comum, "pedidos:autorizacoes")


def test_sem_papel():
    assert sem_papel(usuario_com(username="1"))
    assert not sem_papel(usuario_com(GRUPO_ATENDIMENTO, username="2"))
    assert not sem_papel(usuario_com(GRUPO_GESTAO, username="3"))
    seguranca = usuario_com(username="4")
    seguranca.groups.add(Group.objects.get_or_create(name=GRUPO_SEGURANCA_TRABALHO)[0])
    assert not sem_papel(seguranca)
    assert not sem_papel(AnonymousUser())
    assert not sem_papel(usuario_com(username="5", is_superuser=True))
