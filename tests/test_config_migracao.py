"""A carga inicial da configuração (migration 0007 do catálogo, spec 009; o esquema é a 0006).

A migration transcreve as regras antigas para as tabelas novas, confere o resultado no próprio banco
e nunca altera os cadastros antigos. Chamada como em `test_migracao_unidades.py`: a função de módulo
com `apps`.
"""

import importlib

import pytest
from django.apps import apps

from catalogo.models import (
    CentroCusto,
    CentroFormulario,
    ExcecaoMaterial,
    Formulario,
    MaterialEpi,
    MaterialOficina,
)
from tests.config_cenario import material

pytestmark = pytest.mark.django_db

MIGRACAO = importlib.import_module("catalogo.migrations.0007_transcrever_configuracao")


def centros_do(formulario) -> set[tuple[str, str | None]]:
    return {
        (cf.centro.descricao, cf.centro.placa)
        for cf in CentroFormulario.objects.filter(formulario=formulario).select_related("centro")
    }


def cadastro():
    """Centros de todos os tipos: com várias linhas, com placa, de equipe e a oficina."""
    CentroCusto.objects.create(descricao="ETA I", codigo="12")
    CentroCusto.objects.create(descricao="ETA I", codigo="13", placa="AAA1A11")
    CentroCusto.objects.create(descricao="EQUIPE NORTE", codigo="51", equipe_manutencao=True)
    CentroCusto.objects.create(descricao="OFICINA MECÂNICA", codigo="20")
    CentroCusto.objects.create(descricao="PICKUP 01", codigo="31", placa="ABC1D23")


def test_limpeza_ab_e_epis_recebem_todas_as_linhas():
    cadastro()
    MIGRACAO.transcrever(apps, None)
    todas = {(c.descricao, c.placa) for c in CentroCusto.objects.all()}
    for formulario in (Formulario.LIMPEZA, Formulario.AB, Formulario.EPIS):
        assert centros_do(formulario) == todas


def test_viaturas_recebem_so_as_linhas_marcadas_como_equipe():
    cadastro()
    MIGRACAO.transcrever(apps, None)
    assert centros_do(Formulario.VIATURAS) == {("EQUIPE NORTE", None)}


def test_oficina_recebe_a_linha_sem_placa_do_centro_da_oficina_e_toda_linha_com_placa():
    cadastro()
    MIGRACAO.transcrever(apps, None)
    assert centros_do(Formulario.OFICINA) == {
        ("OFICINA MECÂNICA", None),
        ("ETA I", "AAA1A11"),
        ("PICKUP 01", "ABC1D23"),
    }


def test_oficina_usa_a_primeira_linha_sem_placa_por_codigo_e_ignora_acento_e_caixa():
    CentroCusto.objects.create(descricao="oficina mecanica", codigo="21")
    CentroCusto.objects.create(descricao="OFICINA MECÂNICA", codigo="20")
    MIGRACAO.transcrever(apps, None)
    assert [cf.centro.codigo for cf in CentroFormulario.objects.filter(formulario="OFICINA")] == [
        "20"
    ]


def test_sem_o_centro_da_oficina_a_regra_antiga_ja_era_vazia_e_a_transcricao_tambem():
    CentroCusto.objects.create(descricao="ETA I", codigo="12")
    MIGRACAO.transcrever(apps, None)
    assert centros_do(Formulario.OFICINA) == set()
    assert centros_do(Formulario.VIATURAS) == set()


def test_os_avulsos_da_oficina_e_dos_epis_viram_excecao_que_acrescenta():
    oleo = material("001.001.001", "OLEO", "GERAL")
    oculto = material("001.001.002", "FILTRO", "GERAL", oculto=True)
    luva = material("001.001.003", "LUVA", "ALMOX")
    MaterialOficina.objects.create(material=oleo)
    MaterialOficina.objects.create(material=oculto)
    MaterialEpi.objects.create(material=luva)
    MIGRACAO.transcrever(apps, None)
    assert {
        (e.formulario, e.material.codigo, e.habilitado) for e in ExcecaoMaterial.objects.all()
    } == {
        ("OFICINA", "001.001.001", True),
        ("OFICINA", "001.001.002", True),  # o oculto vira exceção, e o cadastro continua vencendo
        ("EPIS", "001.001.003", True),
    }


def test_carga_repetida_nao_duplica():
    cadastro()
    MaterialOficina.objects.create(material=material("001.001.001", "OLEO"))
    MIGRACAO.transcrever(apps, None)
    total = (CentroFormulario.objects.count(), ExcecaoMaterial.objects.count())
    MIGRACAO.transcrever(apps, None)
    assert (CentroFormulario.objects.count(), ExcecaoMaterial.objects.count()) == total


def test_os_cadastros_antigos_ficam_intactos():
    cadastro()
    oleo = material("001.001.001", "OLEO")
    MaterialOficina.objects.create(material=oleo)
    MIGRACAO.transcrever(apps, None)
    assert CentroCusto.objects.filter(equipe_manutencao=True).count() == 1
    assert MaterialOficina.objects.count() == 1


def test_a_reversao_nao_apaga_nada_nem_os_cadastros_antigos():
    """Depois da implantação as tabelas guardam também as escolhas do administrador, que a reversão
    não saberia distinguir das linhas transcritas: ela não apaga nada (as tabelas somem ao desfazer
    a 0006) e reaplicar a transcrição é seguro."""
    cadastro()
    MaterialEpi.objects.create(material=material("001.001.001", "LUVA"))
    MIGRACAO.transcrever(apps, None)
    total = (CentroFormulario.objects.count(), ExcecaoMaterial.objects.count())
    assert total[0] and total[1]
    MIGRACAO.desfazer(apps, None)
    assert (CentroFormulario.objects.count(), ExcecaoMaterial.objects.count()) == total
    assert CentroCusto.objects.count() == 5 and MaterialEpi.objects.count() == 1
    assert CentroCusto.objects.filter(equipe_manutencao=True).count() == 1


def test_reaplicar_com_configuracao_existente_nao_recoloca_o_que_o_administrador_tirou():
    """A carga é de uma vez só: com as tabelas já preenchidas (o administrador pode ter tirado
    linhas e exceções, e a migration ser desfeita e reaplicada), nada é recolocado e nada falha."""
    cadastro()
    MaterialEpi.objects.create(material=material("001.001.001", "LUVA"))
    MIGRACAO.transcrever(apps, None)
    CentroFormulario.objects.filter(formulario="LIMPEZA", centro__codigo="12").delete()
    ExcecaoMaterial.objects.filter(formulario="EPIS").delete()
    MIGRACAO.desfazer(apps, None)
    MIGRACAO.transcrever(apps, None)  # não levanta e não recoloca
    assert not CentroFormulario.objects.filter(formulario="LIMPEZA", centro__codigo="12").exists()
    assert not ExcecaoMaterial.objects.filter(formulario="EPIS").exists()


def test_a_transcricao_e_atomica_se_a_verificacao_falhar_nada_fica_gravado(monkeypatch):
    cadastro()
    MaterialOficina.objects.create(material=material("001.001.001", "OLEO"))

    def falha(apps_):
        raise RuntimeError("a verificação falhou")

    monkeypatch.setattr(MIGRACAO, "conferir", falha)
    with pytest.raises(RuntimeError):
        MIGRACAO.transcrever(apps, None)
    assert not CentroFormulario.objects.exists() and not ExcecaoMaterial.objects.exists()


def test_a_verificacao_levanta_erro_quando_a_transcricao_diverge_dos_centros():
    cadastro()
    MIGRACAO.transcrever(apps, None)
    CentroFormulario.objects.filter(formulario="VIATURAS").delete()
    with pytest.raises(RuntimeError, match="VIATURAS"):
        MIGRACAO.conferir(apps)


def test_a_verificacao_levanta_erro_quando_um_avulso_nao_foi_transcrito():
    MaterialOficina.objects.create(material=material("001.001.001", "OLEO"))
    MIGRACAO.transcrever(apps, None)
    ExcecaoMaterial.objects.all().delete()
    with pytest.raises(RuntimeError, match="OFICINA"):
        MIGRACAO.conferir(apps)
