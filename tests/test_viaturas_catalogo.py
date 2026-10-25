"""Catálogo, folha e destinos do formulário de reposição de peças das viaturas (spec 006,
research R3 e R6)."""

from decimal import Decimal

import pytest

from catalogo.catalogos import (
    catalogo_ab,
    centros_do_formulario,
    folha_viaturas,
    formulario_viaturas,
)
from catalogo.models import CentroCusto, ItemLimpeza, Material, PecaViatura, SaidaSCPI
from pedidos.regras import VIATURAS, Centro
from tests.cenario import montar_cenario
from tests.config_cenario import criar_centro, habilitar

pytestmark = pytest.mark.django_db

TEE = "016.010.001"  # na lista, sem saída no SCPI (fora do AB)
FITA = "016.005.010"  # no AB (cenário) e posta na lista
CAFE = "008.001.002"  # da lista de limpeza, posta também na lista das viaturas
CAPACETE = "030.004.001"  # oculto no SCPI


def peca(codigo, ordem, nome_exibido=""):
    return PecaViatura.objects.create(
        material=Material.objects.get(codigo=codigo), ordem=ordem, nome_exibido=nome_exibido
    )


@pytest.fixture
def lista():
    montar_cenario()
    Material.objects.create(
        codigo=TEE,
        nome="TEE PVC 3/4 ROSCA",
        unidade="UN",
        grupo="REDES DE ÁGUA",
        estoque=Decimal("4"),
        estoque_em=Material.objects.get(codigo=FITA).estoque_em,
    )
    peca(TEE, 2, "Tee Branco 3/4 Rosca")
    peca(FITA, 1)
    peca(CAFE, 3)
    peca(CAPACETE, 4)


def codigos(itens):
    return [i.codigo for i in itens]


def test_sem_saldo_importado_o_formulario_fica_indisponivel():
    montar_cenario(com_estoque=False)
    assert formulario_viaturas() is None


def test_sem_lista_e_sem_ab_o_formulario_fica_indisponivel():
    assert formulario_viaturas() is None


def test_primeiro_a_lista_na_ordem_depois_o_ab_sem_repetir(lista):
    itens = formulario_viaturas()
    ab = codigos(catalogo_ab().itens)
    assert codigos(itens)[:3] == [FITA, TEE, CAFE]
    assert codigos(itens)[3:] == [c for c in ab if c != FITA]
    assert len(codigos(itens)) == len(set(codigos(itens)))


def test_a_lista_usa_o_nome_exibido_e_a_unidade_do_scpi(lista):
    por_codigo = {i.codigo: i for i in formulario_viaturas()}
    assert por_codigo[TEE].nome == "Tee Branco 3/4 Rosca"
    assert por_codigo[FITA].nome == "FITA VEDA ROSCA"
    # O café é vendido a peso (KG) e é da lista de limpeza, com unidade exibida "Pacote 500 g":
    # aqui vale a unidade do SCPI.
    assert por_codigo[CAFE].unidade == "KG" and por_codigo[CAFE].fracionavel


def test_peca_fora_do_ab_aparece_e_oculta_nao(lista):
    assert ItemLimpeza.objects.filter(material__codigo=CAFE).exists()
    itens = codigos(formulario_viaturas())
    assert TEE in itens and CAFE in itens and CAPACETE not in itens


def test_peca_duplicada_aparece_para_o_carrinho_bloquear(lista):
    Material.objects.filter(codigo=TEE).update(duplicado=True)
    assert {i.codigo: i for i in formulario_viaturas()}[TEE].duplicado


def test_so_a_lista_sem_ab_basta(lista):
    SaidaSCPI.objects.all().delete()
    assert codigos(formulario_viaturas()) == [FITA, TEE, CAFE]


def test_a_folha_e_a_lista_visivel_na_ordem(lista):
    assert folha_viaturas() == [FITA, TEE, CAFE]


def test_centros_de_equipe_sao_os_habilitados_sem_placa():
    montar_cenario()
    assert centros_do_formulario(VIATURAS) == []
    habilitar(CentroCusto.objects.filter(descricao="ETA I"), VIATURAS)
    # Centro com placa: uma linha habilitada basta, e a placa não vai para o destino.
    criar_centro("EQUIPE NORTE", "51", "AAA1A11")
    criar_centro("EQUIPE NORTE", "51", "BBB2B22", formularios=[VIATURAS])
    assert centros_do_formulario(VIATURAS) == [Centro("EQUIPE NORTE", "51"), Centro("ETA I", "12")]
