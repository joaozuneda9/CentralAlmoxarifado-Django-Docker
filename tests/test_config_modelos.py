"""Os modelos da configuração das opções por formulário (spec 009, data-model.md)."""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from catalogo.models import CentroCusto, CentroFormulario, ExcecaoMaterial, Formulario, Material
from tests.config_cenario import criar_centro, material

pytestmark = pytest.mark.django_db


def test_formularios_sao_os_cinco_publicos_sem_a_avulsa():
    assert set(Formulario.values) == {"LIMPEZA", "AB", "VIATURAS", "OFICINA", "EPIS"}
    assert "AVULSA" not in Formulario.values


def test_centro_novo_nasce_ativo_e_sem_formulario():
    centro = CentroCusto.objects.create(descricao="SETOR NOVO", codigo="90")
    assert centro.ativo is True
    assert not centro.formularios.exists()


def test_centro_unico_no_formulario():
    centro = criar_centro("ETA I", "12")
    CentroFormulario.objects.create(centro=centro, formulario=Formulario.AB)
    with pytest.raises(IntegrityError), transaction.atomic():
        CentroFormulario.objects.create(centro=centro, formulario=Formulario.AB)
    # O mesmo centro em outro formulário e outro centro no mesmo formulário valem.
    CentroFormulario.objects.create(centro=centro, formulario=Formulario.LIMPEZA)
    outro = criar_centro("ETA II", "14")
    CentroFormulario.objects.create(centro=outro, formulario=Formulario.AB)


def test_apagar_o_centro_leva_as_associacoes():
    centro = criar_centro("ETA I", "12", formularios=[Formulario.AB, Formulario.EPIS])
    centro.delete()
    assert not CentroFormulario.objects.exists()


def test_excecao_unica_no_material_e_formulario():
    mat = material("001.001.001", "LUVA")
    ExcecaoMaterial.objects.create(material=mat, formulario=Formulario.AB, habilitado=False)
    with pytest.raises(IntegrityError), transaction.atomic():
        ExcecaoMaterial.objects.create(material=mat, formulario=Formulario.AB, habilitado=True)
    ExcecaoMaterial.objects.create(material=mat, formulario=Formulario.OFICINA, habilitado=True)


def test_o_material_com_excecao_nao_pode_ser_apagado():
    mat = material("001.001.001", "LUVA")
    ExcecaoMaterial.objects.create(material=mat, formulario=Formulario.AB, habilitado=True)
    with pytest.raises(ProtectedError):
        Material.objects.filter(pk=mat.pk).delete()


def test_alterado_em_muda_ao_salvar_e_alterado_por_vira_nulo_sem_o_usuario():
    usuario = get_user_model().objects.create_user(username="55555", password="x")
    mat = material("001.001.001", "LUVA")
    exc = ExcecaoMaterial.objects.create(
        material=mat, formulario=Formulario.AB, habilitado=True, alterado_por=usuario
    )
    antes = exc.alterado_em
    exc.habilitado = False
    exc.save()
    exc.refresh_from_db()
    assert exc.alterado_em >= antes and exc.habilitado is False
    usuario.delete()
    exc.refresh_from_db()
    assert exc.alterado_por is None


def test_ordenacao_das_associacoes_e_das_excecoes():
    b = criar_centro("B", "2", formularios=[Formulario.AB])
    a = criar_centro("A", "1", formularios=[Formulario.AB])
    assert [cf.centro_id for cf in CentroFormulario.objects.all()] == [a.pk, b.pk]
    luva = material("001.001.001", "LUVA")
    capa = material("001.001.002", "CAPA")
    ExcecaoMaterial.objects.create(material=luva, formulario=Formulario.AB, habilitado=True)
    ExcecaoMaterial.objects.create(material=capa, formulario=Formulario.AB, habilitado=True)
    assert [e.material.nome for e in ExcecaoMaterial.objects.all()] == ["CAPA", "LUVA"]
