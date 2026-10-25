"""Os serviços que gravam a configuração (spec 009): exceções, lote, centros e estado ativo."""

import pytest
from django.contrib.auth import get_user_model

from catalogo.catalogos import formulario_ab
from catalogo.disponibilidade import (
    ACRESCENTAR,
    RESTAURAR,
    RETIRAR,
    aplicar_em_lote,
    definir_ativo,
    definir_excecao,
    excecao_para,
    habilitar_centros,
    situacao_do_formulario,
)
from catalogo.models import (
    CentroCusto,
    CentroFormulario,
    ExcecaoMaterial,
    Formulario,
    Material,
)
from pedidos.models import Pedido
from tests.cenario import em_paralelo, montar_cenario
from tests.config_cenario import codigos, criar_centro, habilitar, material

pytestmark = pytest.mark.django_db

AB = Formulario.AB
FITA = "016.005.010"  # na regra do AB
BOTINA = "013.006.001"  # na regra do AB


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()


def mat(codigo):
    return Material.objects.get(codigo=codigo)


def excecoes(formulario=AB):
    return {
        e.material.codigo: e.habilitado
        for e in ExcecaoMaterial.objects.filter(formulario=formulario)
    }


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="55555", password="x")


# --- a conta mínima (pura) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("na_regra", "desejado", "esperada"),
    [(True, True, None), (True, False, False), (False, True, True), (False, False, None)],
)
def test_excecao_para(na_regra, desejado, esperada):
    assert excecao_para(na_regra, desejado) is esperada


# --- definir_excecao ---------------------------------------------------------------------------


def test_acrescentar_o_que_a_regra_nao_traz_cria_a_excecao(usuario):
    novo = material("900.000.001", "TESOURA", "ALMOX")
    assert definir_excecao(AB, novo, ACRESCENTAR, usuario) is True
    assert excecoes() == {"900.000.001": True}
    assert ExcecaoMaterial.objects.get().alterado_por == usuario
    assert "900.000.001" in codigos(formulario_ab())


def test_retirar_o_que_a_regra_traz_cria_a_excecao_que_retira():
    assert definir_excecao(AB, mat(FITA), RETIRAR) is True
    assert excecoes() == {FITA: False}
    assert FITA not in codigos(formulario_ab())


def test_acrescentar_de_volta_o_retirado_apaga_a_excecao():
    definir_excecao(AB, mat(FITA), RETIRAR)
    assert definir_excecao(AB, mat(FITA), ACRESCENTAR) is True
    assert excecoes() == {} and FITA in codigos(formulario_ab())


def test_retirar_o_acrescentado_apaga_a_excecao():
    novo = material("900.000.001", "TESOURA", "ALMOX")
    definir_excecao(AB, novo, ACRESCENTAR)
    assert definir_excecao(AB, novo, RETIRAR) is True
    assert excecoes() == {}


def test_restaurar_apaga_a_excecao_e_e_idempotente():
    definir_excecao(AB, mat(FITA), RETIRAR)
    assert definir_excecao(AB, mat(FITA), RESTAURAR) is True
    assert definir_excecao(AB, mat(FITA), RESTAURAR) is False
    assert excecoes() == {}


def test_repetir_a_mesma_acao_nao_muda_nada():
    assert definir_excecao(AB, mat(FITA), RETIRAR) is True
    assert definir_excecao(AB, mat(FITA), RETIRAR) is False
    assert definir_excecao(AB, mat(FITA), ACRESCENTAR) is True
    assert definir_excecao(AB, mat(FITA), ACRESCENTAR) is False


def test_acao_desconhecida_e_erro():
    with pytest.raises(ValueError):
        definir_excecao(AB, mat(FITA), "apagar")


def test_cada_formulario_tem_a_sua_excecao():
    definir_excecao(AB, mat(FITA), RETIRAR)
    assert excecoes(Formulario.VIATURAS) == {}
    assert "016.005.010" in situacao_do_formulario(Formulario.VIATURAS).na_regra


def test_a_excecao_nao_toca_o_material_nem_o_estoque_nem_os_pedidos():
    antes = list(Material.objects.values_list("codigo", "estoque", "oculto", "nome"))
    definir_excecao(AB, mat(FITA), RETIRAR)
    definir_excecao(AB, material("900.000.001", "TESOURA", "ALMOX"), ACRESCENTAR)
    depois = list(
        Material.objects.exclude(codigo="900.000.001").values_list(
            "codigo", "estoque", "oculto", "nome"
        )
    )
    assert depois == antes and not Pedido.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_gravacoes_simultaneas_do_mesmo_material_deixam_uma_linha():
    montar_cenario()
    fita = mat(FITA)
    em_paralelo(
        lambda: definir_excecao(AB, fita, RETIRAR),
        lambda: definir_excecao(AB, fita, RETIRAR),
        lambda: definir_excecao(AB, fita, RETIRAR),
    )
    assert ExcecaoMaterial.objects.filter(formulario=AB, material=fita).count() == 1


# --- aplicar_em_lote ---------------------------------------------------------------------------


def grupo_de_materiais(n=5):
    return [material(f"800.000.{i:03d}", f"PECA {i:02d}", "LOTE") for i in range(n)]


def test_o_lote_vale_para_todos_os_do_filtro_e_so_no_formulario_pedido():
    grupo_de_materiais(5)
    alvo = Material.objects.filter(grupo="LOTE")
    assert aplicar_em_lote(AB, alvo, ACRESCENTAR) == (5, 0)
    assert len(excecoes()) == 5 and set(excecoes().values()) == {True}
    assert excecoes(Formulario.VIATURAS) == {}
    assert excecoes(Formulario.OFICINA) == {}


def test_o_lote_nao_muda_o_que_esta_fora_do_filtro():
    grupo_de_materiais(3)
    aplicar_em_lote(AB, Material.objects.filter(grupo="LOTE"), ACRESCENTAR)
    assert FITA in codigos(formulario_ab()) and BOTINA in codigos(formulario_ab())
    assert set(excecoes()) == {"800.000.000", "800.000.001", "800.000.002"}


def test_retirar_em_lote_so_grava_o_que_a_regra_traz_e_apaga_o_acrescentado():
    grupo_de_materiais(2)
    definir_excecao(AB, mat("800.000.000"), ACRESCENTAR)
    alvo = Material.objects.filter(codigo__in=[FITA, BOTINA, "800.000.000", "800.000.001"])
    # FITA e BOTINA saem (regra); 800.000.000 sai (apaga a exceção); 800.000.001 nunca esteve.
    assert aplicar_em_lote(AB, alvo, RETIRAR) == (3, 1)
    assert excecoes() == {FITA: False, BOTINA: False}


def test_repetir_o_lote_nao_muda_mais_nada():
    grupo_de_materiais(4)
    alvo = Material.objects.filter(grupo="LOTE")
    aplicar_em_lote(AB, alvo, ACRESCENTAR)
    assert aplicar_em_lote(AB, alvo, ACRESCENTAR) == (0, 4)


def test_o_lote_acrescentar_devolve_ao_ab_o_retirado_apagando_a_excecao():
    definir_excecao(AB, mat(FITA), RETIRAR)
    assert aplicar_em_lote(AB, Material.objects.filter(codigo=FITA), ACRESCENTAR) == (1, 0)
    assert excecoes() == {}


def test_o_lote_e_atomico(monkeypatch):
    """Uma falha no segundo bloco desfaz também o primeiro, que já tinha gravado."""
    from catalogo import disponibilidade

    monkeypatch.setattr(disponibilidade, "TAMANHO_DO_BLOCO", 2)
    chamadas = []
    original = disponibilidade.excecao_para

    def falha_na_terceira(*args):
        chamadas.append(args)
        if len(chamadas) == 3:
            raise RuntimeError("falha no meio do lote")
        return original(*args)

    monkeypatch.setattr(disponibilidade, "excecao_para", falha_na_terceira)
    grupo_de_materiais(4)
    with pytest.raises(RuntimeError):
        aplicar_em_lote(AB, Material.objects.filter(grupo="LOTE"), ACRESCENTAR)
    assert excecoes() == {}


def test_lote_com_acao_desconhecida_e_erro():
    with pytest.raises(ValueError):
        aplicar_em_lote(AB, Material.objects.none(), RESTAURAR)


def test_o_lote_trabalha_em_blocos(monkeypatch):
    from catalogo import disponibilidade

    monkeypatch.setattr(disponibilidade, "TAMANHO_DO_BLOCO", 2)
    grupo_de_materiais(5)
    assert aplicar_em_lote(AB, Material.objects.filter(grupo="LOTE"), ACRESCENTAR) == (5, 0)
    assert len(excecoes()) == 5


# --- centros -----------------------------------------------------------------------------------


def test_habilitar_cria_so_as_que_faltam_e_e_idempotente(usuario):
    a = criar_centro("A", "1")
    b = criar_centro("B", "2", formularios=[AB])
    assert habilitar_centros(AB, [a, b], True, usuario) == 1
    assert habilitar_centros(AB, [a, b], True, usuario) == 0
    assert CentroFormulario.objects.get(centro=a, formulario=AB).alterado_por == usuario
    assert CentroFormulario.objects.get(centro=b, formulario=AB).alterado_por is None


def test_desabilitar_apaga_so_as_existentes_daquele_formulario():
    a = criar_centro("A", "1", formularios=[AB, Formulario.LIMPEZA])
    assert habilitar_centros(AB, [a], False) == 1
    assert habilitar_centros(AB, [a], False) == 0
    assert CentroFormulario.objects.filter(centro=a).count() == 1  # a da limpeza fica


def test_habilitar_aceita_ids_e_ignora_id_inexistente():
    a = criar_centro("A", "1")
    antes = CentroFormulario.objects.filter(formulario=AB).count()
    assert habilitar_centros(AB, [a.pk, 999999], True) == 1
    assert CentroFormulario.objects.filter(formulario=AB).count() == antes + 1


def test_inativar_e_reativar_guardam_as_associacoes():
    a = criar_centro("A", "1", formularios=[AB, Formulario.EPIS])
    assert definir_ativo([a], False) == 1
    assert definir_ativo([a], False) == 0
    assert CentroFormulario.objects.filter(centro=a).count() == 2
    assert definir_ativo([a.pk], True) == 1
    assert CentroCusto.objects.get(pk=a.pk).ativo is True


def test_habilitar_depois_de_criar_o_centro_aparece_nos_destinos():
    from catalogo.catalogos import centros_do_formulario

    novo = CentroCusto.objects.create(descricao="SETOR NOVO", codigo="90")
    assert all(c.descricao != "SETOR NOVO" for c in centros_do_formulario(AB))
    habilitar(novo, AB)
    assert any(c.descricao == "SETOR NOVO" for c in centros_do_formulario(AB))
