"""A carga das unidades fracionáveis (migration 0002 do catálogo, spec 005)."""

import importlib

import pytest
from django.apps import apps

from catalogo.models import Opcao

pytestmark = pytest.mark.django_db

MIGRACAO = importlib.import_module("catalogo.migrations.0002_unidades_fracionaveis")
LISTA = Opcao.Lista.UNIDADE_FRACIONAVEL
UNIDADES = ["M", "MT", "MTS", "KM", "KG", "L", "LT", "M²", "M³", "T"]


def test_depois_de_migrar_as_dez_unidades_estao_ativas_na_ordem():
    assert Opcao.valores(LISTA) == UNIDADES


def test_carga_repetida_nao_duplica():
    MIGRACAO.carregar_unidades(apps, None)
    MIGRACAO.carregar_unidades(apps, None)
    assert Opcao.objects.filter(lista=LISTA).count() == len(UNIDADES)


def test_desativar_uma_unidade_a_tira_da_lista_e_a_carga_nao_a_reativa():
    Opcao.objects.filter(lista=LISTA, valor="KG").update(ativo=False)
    assert "KG" not in Opcao.valores(LISTA)
    MIGRACAO.carregar_unidades(apps, None)
    assert "KG" not in Opcao.valores(LISTA)


def test_a_carga_so_mexe_na_lista_de_unidades():
    antes = Opcao.objects.exclude(lista=LISTA).count()
    MIGRACAO.carregar_unidades(apps, None)
    assert Opcao.objects.exclude(lista=LISTA).count() == antes
