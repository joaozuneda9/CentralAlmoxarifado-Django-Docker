"""SC-001: depois da carga inicial, cada formulário oferece **o mesmo** de antes da configuração.

O "antes" é a regra congelada em `tests/regra_antiga.py` (marca de equipe de manutenção, linhas de
centro, `MaterialOficina` e `MaterialEpi`); o "depois" é o catálogo e os destinos lidos da
configuração que a migration transcreveu.
"""

import importlib

import pytest
from django.apps import apps

from catalogo.catalogos import (
    centros_do_formulario,
    formulario_ab,
    formulario_epis,
    formulario_limpeza,
    formulario_oficina,
    formulario_viaturas,
    regra_de_origem,
)
from catalogo.models import (
    CentroCusto,
    CentroFormulario,
    ExcecaoMaterial,
    Formulario,
    Material,
    MaterialEpi,
    MaterialOficina,
    Opcao,
    PecaViatura,
)
from pedidos.regras import AB, EPIS, LIMPEZA, OFICINA, VIATURAS, opcoes_destino
from tests import regra_antiga
from tests.cenario import montar_cenario
from tests.config_cenario import codigos, material

pytestmark = pytest.mark.django_db

MIGRACAO = importlib.import_module("catalogo.migrations.0007_transcrever_configuracao")


@pytest.fixture(autouse=True)
def estado_de_antes():
    """O banco como estava antes da spec 009: sem configuração, só os cadastros antigos."""
    montar_cenario()
    CentroFormulario.objects.all().delete()
    ExcecaoMaterial.objects.all().delete()
    CentroCusto.objects.create(descricao="ETA I", codigo="13", placa="AAA1A11")
    CentroCusto.objects.create(descricao="EQUIPE NORTE", codigo="52", placa="BBB2B22")
    CentroCusto.objects.create(
        descricao="EQUIPE NORTE", codigo="51", placa="CCC3C33", equipe_manutencao=True
    )
    CentroCusto.objects.create(descricao="EQUIPE SUL", codigo="60", equipe_manutencao=True)
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_OFICINA, valor="Auto Pecas")
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_EPI, valor="Material de Seguranca")
    material("006.002.001", "FILTRO DE OLEO", "AUTO PECAS")
    material("006.000.001", "PNEU", "AUTO PECAS", estoque="0")
    material("999.001.010", "OLEO 15W40", "GERAL", unidade="LT")
    material("999.001.011", "FILTRO OCULTO", "GERAL", oculto=True)
    material("013.005.100", "LUVA DE VAQUETA", "MATERIAL DE SEGURANCA")
    material("013.003.001", "OCULOS DE PROTECAO", "ALMOXARIFADO")
    MaterialOficina.objects.create(material=Material.objects.get(codigo="999.001.010"))
    MaterialOficina.objects.create(material=Material.objects.get(codigo="999.001.011"))
    MaterialEpi.objects.create(material=Material.objects.get(codigo="013.003.001"))
    PecaViatura.objects.create(material=Material.objects.get(codigo="016.005.010"), ordem=1)


def transcrever():
    MIGRACAO.transcrever(apps, None)


def test_os_destinos_de_limpeza_ab_e_epis_sao_todos_os_centros_como_antes():
    antes = {o: opcoes_destino(regra_antiga.centros()) for o in (LIMPEZA, AB, EPIS)}
    transcrever()
    for origem in (LIMPEZA, AB, EPIS):
        assert opcoes_destino(centros_do_formulario(origem)) == antes[origem]
        assert centros_do_formulario(origem) == regra_antiga.centros()


def test_os_destinos_das_viaturas_sao_os_da_marca_de_equipe_como_antes():
    antes = regra_antiga.centros_equipe_manutencao()
    assert [c.descricao for c in antes] == ["EQUIPE NORTE", "EQUIPE SUL"]
    transcrever()
    assert centros_do_formulario(VIATURAS) == antes
    assert opcoes_destino(centros_do_formulario(VIATURAS)) == opcoes_destino(antes)


def test_os_destinos_da_oficina_sao_o_centro_da_oficina_e_cada_viatura_como_antes():
    antes = regra_antiga.centros_oficina()
    assert antes[0].descricao == "OFICINA MECÂNICA" and all(c.so_com_placa for c in antes[1:])
    transcrever()
    assert centros_do_formulario(OFICINA) == antes
    assert opcoes_destino(centros_do_formulario(OFICINA)) == opcoes_destino(antes)


def test_o_catalogo_da_oficina_e_o_de_antes_com_os_avulsos_inclusive_ocultos():
    antes = codigos(regra_antiga.catalogo_oficina())
    assert "999.001.010" in antes and "999.001.011" not in antes  # o oculto nunca aparece
    transcrever()
    assert codigos(formulario_oficina()) == antes


def test_o_catalogo_dos_epis_e_o_de_antes_com_o_avulso():
    antes = codigos(regra_antiga.catalogo_epis())
    assert "013.003.001" in antes
    transcrever()
    assert codigos(formulario_epis()) == antes


def test_limpeza_ab_e_viaturas_nao_mudam_de_catalogo():
    antes = {
        LIMPEZA: codigos(regra_de_origem(LIMPEZA)),
        AB: codigos(regra_de_origem(AB)),
        VIATURAS: codigos(regra_de_origem(VIATURAS)),
    }
    transcrever()
    assert codigos(formulario_limpeza()) == antes[LIMPEZA]
    assert codigos(formulario_ab()) == antes[AB]
    assert codigos(formulario_viaturas()) == antes[VIATURAS]


def test_a_transcricao_nao_cria_configuracao_para_o_que_nao_existia():
    transcrever()
    assert not ExcecaoMaterial.objects.filter(habilitado=False).exists()
    assert set(ExcecaoMaterial.objects.values_list("formulario", flat=True)) <= {
        Formulario.OFICINA,
        Formulario.EPIS,
    }
