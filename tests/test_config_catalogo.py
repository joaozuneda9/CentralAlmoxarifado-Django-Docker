"""O catálogo de cada formulário com as exceções aplicadas (spec 009, FR-014 a FR-023a)."""

import pytest

from catalogo.catalogos import (
    catalogo_epis,
    catalogo_oficina,
    formulario_ab,
    formulario_epis,
    formulario_limpeza,
    formulario_oficina,
    formulario_viaturas,
    regra_de_origem,
)
from catalogo.models import Formulario, Material, Opcao, PecaViatura, SaidaSCPI
from tests.cenario import montar_cenario
from tests.config_cenario import codigos, excecao, material

pytestmark = pytest.mark.django_db

FITA = "016.005.010"
BOTINA = "013.006.001"
LUVA_NITRILICA = "013.005.007"
DETERGENTE = "023.001.002"
CAFE = "008.001.002"
PAPEL = "023.004.001"
CAPACETE_OCULTO = "030.004.001"
AB = [FITA, BOTINA, LUVA_NITRILICA]  # pelo número de saídas, do cenário


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()


def mat(codigo):
    return Material.objects.get(codigo=codigo)


def test_sem_excecao_cada_formulario_oferece_a_regra_de_origem():
    assert codigos(formulario_ab()) == AB
    assert codigos(formulario_limpeza()) == codigos(regra_de_origem(Formulario.LIMPEZA))
    assert codigos(regra_de_origem(Formulario.AB)) == AB


def test_retirar_do_ab_o_tira_da_busca_e_nao_mexe_nos_outros_formularios():
    PecaViatura.objects.create(material=mat(FITA))
    excecao(Formulario.AB, mat(FITA), False)
    assert codigos(formulario_ab()) == [BOTINA, LUVA_NITRILICA]
    assert FITA in codigos(formulario_viaturas())  # a exceção é do AB, não das viaturas


def test_retirar_das_viaturas_tira_da_lista_e_do_ab_que_a_completa():
    PecaViatura.objects.create(material=mat(BOTINA), ordem=1)
    assert BOTINA in codigos(formulario_viaturas())
    excecao(Formulario.VIATURAS, mat(BOTINA), False)
    assert BOTINA not in codigos(formulario_viaturas())
    assert BOTINA in codigos(formulario_ab())  # o AB não foi tocado


def test_acrescentar_vem_ao_fim_em_ordem_alfabetica_por_nome_e_codigo():
    tesoura = material("900.000.002", "TESOURA", "ALMOX")
    alicate = material("900.000.001", "ALICATE", "ALMOX")
    excecao(Formulario.AB, tesoura, True)
    excecao(Formulario.AB, alicate, True)
    assert codigos(formulario_ab()) == [*AB, "900.000.001", "900.000.002"]
    assert regra_de_origem(Formulario.AB) and "900.000.001" not in codigos(
        regra_de_origem(Formulario.AB)
    )


def test_acrescentar_o_que_a_regra_ja_traz_nao_duplica():
    excecao(Formulario.AB, mat(FITA), True)
    assert codigos(formulario_ab()) == AB


def test_oculto_no_cadastro_nunca_e_oferecido_mesmo_acrescentado():
    excecao(Formulario.AB, mat(CAPACETE_OCULTO), True)
    assert CAPACETE_OCULTO not in codigos(formulario_ab())


def test_duplicado_acrescentado_aparece_bloqueado():
    duplicado = material("900.000.003", "CADASTRO REPETIDO", "ALMOX")
    Material.objects.filter(pk=duplicado.pk).update(duplicado=True)
    excecao(Formulario.AB, duplicado, True)
    item = next(i for i in formulario_ab() if i.codigo == "900.000.003")
    assert item.duplicado is True


def test_sem_estoque_acrescentado_aparece_para_o_formulario_bloquear():
    zerado = material("900.000.004", "SEM SALDO", "ALMOX", estoque="0")
    excecao(Formulario.AB, zerado, True)
    item = next(i for i in formulario_ab() if i.codigo == "900.000.004")
    assert item.estoque == 0  # quem bloqueia é o carrinho ("Sem estoque"), como em qualquer item


def test_formulario_que_perde_todos_os_itens_fica_indisponivel():
    for codigo in (DETERGENTE, CAFE, PAPEL):
        excecao(Formulario.LIMPEZA, mat(codigo), False)
    assert formulario_limpeza() is None


def test_sem_saldo_importado_continua_indisponivel_com_ou_sem_excecao():
    Material.objects.update(estoque_em=None)
    excecao(Formulario.AB, mat(FITA), True)
    assert formulario_ab() is None and formulario_limpeza() is None
    assert formulario_viaturas() is None and formulario_oficina() is None
    assert formulario_epis() is None


def test_a_excecao_de_um_formulario_nao_aparece_em_outro():
    tesoura = material("900.000.002", "TESOURA", "ALMOX")
    excecao(Formulario.OFICINA, tesoura, True)
    assert "900.000.002" in codigos(formulario_oficina())
    assert "900.000.002" not in codigos(formulario_ab())
    assert "900.000.002" not in codigos(formulario_epis() or [])


def test_o_ab_continua_calculado_com_excecoes_ao_lado():
    excecao(Formulario.AB, mat(BOTINA), False)
    novo = material("900.000.005", "ITEM DE MUITA SAIDA", "ALMOX")
    for n in range(10):
        SaidaSCPI.objects.create(
            id_requi=f"N{n}", cadpro=novo.codigo, qtd=1, valor=1, data="2026-10-01"
        )
    assert codigos(formulario_ab()) == ["900.000.005", FITA, LUVA_NITRILICA]


def test_oficina_e_epis_so_pelos_grupos_o_avulso_entra_so_por_excecao():
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_OFICINA, valor="Auto Pecas")
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_EPI, valor="EPI")
    filtro = material("006.002.001", "FILTRO DE OLEO", "AUTO PECAS")
    oleo = material("999.001.010", "OLEO LUBRIFICANTE", "GERAL")
    assert codigos(catalogo_oficina()) == [filtro.codigo]
    assert codigos(formulario_oficina()) == [filtro.codigo]
    assert BOTINA in codigos(catalogo_epis())  # o grupo EPI do cenário
    excecao(Formulario.OFICINA, oleo, True)
    assert codigos(catalogo_oficina()) == [filtro.codigo]  # a regra de origem continua só os grupos
    assert codigos(formulario_oficina()) == [filtro.codigo, oleo.codigo]


def test_oficina_e_epis_mantem_a_ordem_do_banco_por_nome_com_o_acrescentado_no_lugar():
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_OFICINA, valor="Auto Pecas")
    pneu = material("006.000.001", "PNEU", "AUTO PECAS")
    filtro = material("006.002.001", "FILTRO", "AUTO PECAS")
    oleo = material("999.001.010", "OLEO", "GERAL")
    excecao(Formulario.OFICINA, oleo, True)
    assert codigos(formulario_oficina()) == [filtro.codigo, oleo.codigo, pneu.codigo]


def test_retirar_na_oficina_tira_do_grupo():
    Opcao.objects.create(lista=Opcao.Lista.GRUPO_OFICINA, valor="Auto Pecas")
    filtro = material("006.002.001", "FILTRO", "AUTO PECAS")
    pneu = material("006.000.001", "PNEU", "AUTO PECAS")
    excecao(Formulario.OFICINA, filtro, False)
    assert codigos(formulario_oficina()) == [pneu.codigo]


def test_consultas_do_catalogo_sao_poucas(django_assert_max_num_queries):
    excecao(Formulario.AB, material("900.000.002", "TESOURA", "ALMOX"), True)
    excecao(Formulario.AB, mat(FITA), False)
    formulario_ab()  # esquenta o que o teste não mede
    with django_assert_max_num_queries(12):
        formulario_ab()


def test_retirar_uma_peca_das_viaturas_a_tira_da_folha_e_a_acrescentada_fica_fora_dela():
    """FR-023a: a folha é a lista de peças que está no catálogo; o acrescentado vem depois da lista
    e nunca entra na folha."""
    from catalogo.catalogos import folha_viaturas
    from pedidos import carrinho
    from pedidos.fluxos import FLUXOS

    PecaViatura.objects.create(material=mat(FITA), ordem=1)
    PecaViatura.objects.create(material=mat(BOTINA), ordem=2)
    fluxo = FLUXOS["viaturas"]

    def folha():
        return codigos(carrinho.pecas_da_folha(fluxo, formulario_viaturas()))

    assert folha() == [FITA, BOTINA] == folha_viaturas()
    excecao(Formulario.VIATURAS, mat(FITA), False)
    assert folha() == [BOTINA] and FITA not in codigos(formulario_viaturas())
    novo = material("900.000.007", "TESOURA", "ALMOX")
    excecao(Formulario.VIATURAS, novo, True)
    assert folha() == [BOTINA]  # o acrescentado não entra na folha
    assert codigos(formulario_viaturas())[-1] == "900.000.007"  # e vem depois da lista e do AB
