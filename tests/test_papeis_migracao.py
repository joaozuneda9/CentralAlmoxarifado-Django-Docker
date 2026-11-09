"""A migration `contas/0004_papeis` (spec 012, US4, FR-015 e FR-016): todo usuário ativo fora da
Segurança do Trabalho fica com os dois papéis, e a migration confere isso no fim.

A função da migration roda de novo sobre um cenário montado no banco de teste (que já passou por
ela uma vez, sem usuários): é como a produção, com usuários de antes da mudança.
"""

import importlib

import pytest
from django.apps import apps
from django.contrib.auth.models import Group, Permission

from contas.acesso import GRUPO_ATENDIMENTO, GRUPO_GESTAO, GRUPO_SEGURANCA_TRABALHO
from tests.papeis import usuario_com

pytestmark = pytest.mark.django_db

migracao = importlib.import_module("contas.migrations.0004_papeis")
PERMISSOES = {"atender_pedidos", "operar_automacoes", "ver_curva", "ver_formularios"}


def grupos(usuario):
    return set(usuario.groups.values_list("name", flat=True))


def permissoes(usuario):
    return {p.split(".", 1)[1] for p in usuario.get_all_permissions() if p.startswith("contas.")}


@pytest.fixture
def cenario():
    seguranca = Group.objects.get_or_create(name=GRUPO_SEGURANCA_TRABALHO)[0]
    da_seguranca = usuario_com(username="70001")
    da_seguranca.groups.add(seguranca)
    return {
        "comum": usuario_com(username="1"),
        "chefe": usuario_com(username="2", is_superuser=True, is_staff=True),
        "ja_atende": usuario_com(GRUPO_ATENDIMENTO, username="3"),
        "planilha": usuario_com(username="planilha", is_active=False),
        "seguranca": da_seguranca,
    }


def test_da_os_dois_papeis_a_quem_usa_a_area_interna(cenario):
    migracao.aplicar(apps, None)
    for nome in ("comum", "chefe", "ja_atende"):
        usuario = type(cenario[nome]).objects.get(pk=cenario[nome].pk)
        assert grupos(usuario) == {GRUPO_ATENDIMENTO, GRUPO_GESTAO}, nome
        assert permissoes(usuario) >= PERMISSOES, nome


def test_inativo_e_seguranca_do_trabalho_nao_ganham_nada(cenario):
    migracao.aplicar(apps, None)
    assert grupos(cenario["planilha"]) == set()
    assert grupos(cenario["seguranca"]) == {GRUPO_SEGURANCA_TRABALHO}


def test_os_grupos_tem_as_permissoes_do_contrato():
    migracao.aplicar(apps, None)
    atendimento = Group.objects.get(name=GRUPO_ATENDIMENTO)
    gestao = Group.objects.get(name=GRUPO_GESTAO)
    assert set(atendimento.permissions.values_list("codename", flat=True)) == {"atender_pedidos"}
    assert set(gestao.permissions.values_list("codename", flat=True)) == {
        "operar_automacoes",
        "ver_curva",
        "ver_formularios",
    }


def test_rodar_de_novo_nao_duplica(cenario):
    migracao.aplicar(apps, None)
    migracao.aplicar(apps, None)
    assert Group.objects.filter(name__in=[GRUPO_ATENDIMENTO, GRUPO_GESTAO]).count() == 2
    assert Permission.objects.filter(codename__in=PERMISSOES).count() == 4


def test_a_conferencia_levanta_erro_quando_falta_permissao(cenario, monkeypatch):
    original = migracao.criar_grupos

    def sem_uma(apps_, permissoes_):
        grupos_ = original(apps_, permissoes_)
        Group.objects.get(name=GRUPO_GESTAO).permissions.remove(
            Permission.objects.get(codename="ver_curva")
        )
        return grupos_

    monkeypatch.setattr(migracao, "criar_grupos", sem_uma)
    with pytest.raises(RuntimeError, match="sem todos os papéis"):
        migracao.aplicar(apps, None)


def test_reverter_nao_apaga_nada():
    operacao = migracao.Migration.operations[0]
    assert operacao.reverse_code is migracao.migrations.RunPython.noop
