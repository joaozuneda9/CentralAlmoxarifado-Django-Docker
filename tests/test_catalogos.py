from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from catalogo.catalogos import (
    catalogo_ab,
    catalogo_avulsa,
    catalogo_limpeza,
    grupos_ocultos_ab,
    materiais_avulsa,
)
from catalogo.models import ConfiguracaoCurva, ItemLimpeza, Material, Opcao, ParDePara, SaidaSCPI

pytestmark = pytest.mark.django_db

HOJE = date(2026, 10, 12)


def saidas(cadpro, n, dia=date(2026, 1, 1)):
    for i in range(n):
        SaidaSCPI.objects.create(
            id_requi=f"{cadpro[-7:]}-{i}-{dia:%m%d}", cadpro=cadpro, data=dia, qtd=1, valor=0
        )


def material(codigo, **campos):
    campos.setdefault("nome", f"MATERIAL {codigo}")
    return Material.objects.create(codigo=codigo, **campos)


def limpeza(codigo, categoria="Limpeza", **campos):
    Opcao.objects.get_or_create(lista="CATEGORIA_LIMPEZA", valor=categoria)
    return ItemLimpeza.objects.create(
        material=Material.objects.get(codigo=codigo), categoria=categoria, **campos
    )


def test_ab_ordena_por_ocorrencias_e_exclui_limpeza_ocultos_e_grupos_ocultos():
    agora = timezone.now()
    material("A", estoque=Decimal("2.5"), estoque_em=agora, grupo="G1", subgrupo="S1")
    material("B", estoque=10, estoque_em=agora)
    material("L", estoque_em=agora)
    material("O", oculto=True, estoque_em=agora)
    material("G", grupo="Material  de Consumo", estoque_em=agora)
    limpeza("L")
    for codigo, n in [("A", 2), ("B", 3), ("L", 5), ("O", 1), ("G", 1), ("Z", 4)]:
        saidas(codigo, n)
    ab = catalogo_ab(HOJE)
    assert [(i.codigo, i.disponivel) for i in ab.itens] == [("B", 10), ("A", 2)]
    assert (ab.codigos, ab.na_limpeza, ab.ocultos, ab.sem_cadastro) == (6, 1, 2, ["Z"])
    a = ab.itens[1]
    assert (a.nome, a.grupo, a.subgrupo, a.estoque, a.categoria, a.duplicado) == (
        "MATERIAL A",
        "G1",
        "S1",
        Decimal("2.5"),
        "",
        False,
    )


def test_ab_empate_desempata_pelo_codigo():
    agora = timezone.now()
    for codigo in ["C", "A", "B"]:
        material(codigo, estoque_em=agora)
        saidas(codigo, 1)
    assert [i.codigo for i in catalogo_ab(HOJE).itens] == ["A", "B", "C"]


def test_ab_marca_duplicado():
    material("D", duplicado=True, estoque_em=timezone.now())
    saidas("D", 1)
    assert catalogo_ab(HOJE).itens[0].duplicado is True


def test_ab_sem_saldo_importado_fica_indisponivel():
    material("A")
    saidas("A", 1)
    assert catalogo_ab(HOJE) is None


def test_ab_com_saldo_mas_sem_saidas_fica_vazio():
    material("A", estoque_em=timezone.now())
    ab = catalogo_ab(HOJE)
    assert ab.itens == [] and ab.codigos == 0


def test_ab_nao_faz_uma_consulta_por_material(django_assert_max_num_queries):
    agora = timezone.now()
    for n in range(30):
        material(f"M{n:02}", estoque_em=agora)
        saidas(f"M{n:02}", 1)
    ConfiguracaoCurva.atual()
    # 7 consultas fixas, mais a lista de unidades fracionáveis (uma por montagem, nunca por item).
    with django_assert_max_num_queries(8):
        assert len(catalogo_ab(HOJE).itens) == 30


def test_grupos_ocultos_padrao():
    assert grupos_ocultos_ab() == {
        "GERAL",
        "MATERIALDEEXPEDIENTE(ESCRITORIO)",
        "MATERIALDECONSUMO",
    }


def test_grupos_ocultos_da_lista_substituem_o_padrao():
    Opcao.objects.create(lista="GRUPO_OCULTO_AB", valor="Ferramentas")
    Opcao.objects.create(lista="GRUPO_OCULTO_AB", valor="Desativado", ativo=False)
    assert grupos_ocultos_ab() == {"FERRAMENTAS"}


def test_limpeza_usa_nome_exibido_e_esconde_oculto():
    material("D", nome="DETERGENTE NEUTRO", unidade="UN", estoque=Decimal("3.7"))
    material("S", nome="SACO", unidade="PCT")
    material("X", oculto=True)
    limpeza("D", nome_exibido="Detergente", ordem=2)
    limpeza("S", categoria="Copa/cozinha", unidade_exibida="Pacote")
    limpeza("X")
    itens = catalogo_limpeza()
    assert [(i.codigo, i.nome, i.unidade, i.categoria) for i in itens] == [
        ("S", "SACO", "Pacote", "Copa/cozinha"),
        ("D", "Detergente", "UN", "Limpeza"),
    ]
    assert itens[1].disponivel == 3


def test_avulsa_so_nao_ocultos_e_com_estoque():
    material("A", estoque=5)
    material("B", estoque=5, oculto=True)
    material("C", estoque=5, duplicado=True)
    material("D")  # estoque 0
    material("E", estoque=Decimal("0.5"))
    assert list(materiais_avulsa().values_list("codigo", flat=True)) == ["A", "C", "E"]


def test_catalogo_avulsa_so_nao_ocultos_e_com_estoque():
    material("A", estoque=5)
    material("B", estoque=5, oculto=True)
    material("C", estoque=5, duplicado=True)
    material("D")
    itens = catalogo_avulsa()
    assert [(i.codigo, i.duplicado) for i in itens] == [("A", False), ("C", True)]


# ---------------------------------------------------------------- consolidação pelo de/para


def par(antigo, novo, **campos):
    return ParDePara.objects.create(antigo=antigo, novo=novo, **campos)


def test_ab_consolida_o_codigo_antigo_no_novo():
    agora = timezone.now()
    material("000.000.001", estoque=7, estoque_em=agora)
    material("001.001.001", estoque=3, estoque_em=agora)
    material("002.002.002", estoque_em=agora)
    saidas("000.000.001", 30)
    saidas("001.001.001", 20)
    saidas("002.002.002", 40)
    sem_par = catalogo_ab(HOJE)
    assert [i.codigo for i in sem_par.itens] == ["002.002.002", "000.000.001", "001.001.001"]

    par("000.000.001", "001.001.001")
    ab = catalogo_ab(HOJE)
    assert [i.codigo for i in ab.itens] == ["001.001.001", "002.002.002"]
    assert ab.itens[0].estoque == 3  # o saldo do canônico, onde a saída será lançada
    assert ab.codigos == 2


def test_ab_segue_a_cadeia_de_pares():
    agora = timezone.now()
    material("003.003.003", estoque_em=agora)
    material("009.009.009", estoque_em=agora)
    par("000.000.001", "001.001.001")
    par("001.001.001", "003.003.003")
    saidas("000.000.001", 1)
    saidas("001.001.001", 1)
    saidas("003.003.003", 1)
    saidas("009.009.009", 2)
    assert [i.codigo for i in catalogo_ab(HOJE).itens] == ["003.003.003", "009.009.009"]


def test_ab_volta_a_separar_quando_o_par_e_removido():
    agora = timezone.now()
    material("000.000.001", estoque_em=agora)
    material("001.001.001", estoque_em=agora)
    saidas("000.000.001", 2)
    saidas("001.001.001", 1)
    p = par("000.000.001", "001.001.001")
    assert [i.codigo for i in catalogo_ab(HOJE).itens] == ["001.001.001"]
    p.delete()
    assert [i.codigo for i in catalogo_ab(HOJE).itens] == ["000.000.001", "001.001.001"]


def test_ab_canonico_oculto_ou_na_limpeza_continua_fora():
    agora = timezone.now()
    material("001.001.001", oculto=True, estoque_em=agora)
    material("002.002.002", estoque_em=agora)
    limpeza("002.002.002")
    par("000.000.001", "001.001.001")
    par("000.000.002", "002.002.002")
    par("000.000.003", "003.003.003")
    saidas("000.000.001", 1)
    saidas("000.000.002", 1)
    saidas("000.000.003", 1)
    ab = catalogo_ab(HOJE)
    assert ab.itens == []
    assert (ab.ocultos, ab.na_limpeza, ab.sem_cadastro) == (1, 1, ["003.003.003"])


def test_ab_so_conta_as_saidas_da_janela():
    agora = timezone.now()
    ConfiguracaoCurva.objects.create(janela_meses=1)
    material("A", estoque_em=agora)
    material("B", estoque_em=agora)
    saidas("A", 5, dia=date(2026, 8, 1))
    saidas("B", 1, dia=date(2026, 10, 1))
    assert [i.codigo for i in catalogo_ab(HOJE).itens] == ["B"]


# ---------------------------------------------------------------- unidade fracionável (spec 005)


@pytest.mark.parametrize(
    ("unidade", "fracionavel"),
    [
        ("KG", True),
        (" kg ", True),
        ("M", True),
        ("M²", True),
        ("M2", True),  # a comparação é por `norm_u`: ² e 2 são o mesmo
        ("T", True),
        ("UN", False),
        ("BR", False),
        ("MC", False),
        ("GL", False),
        ("ML", False),
        ("", False),
    ],
)
def test_fracionavel_pela_unidade_do_scpi(unidade, fracionavel):
    material("X", unidade=unidade, estoque=5)
    assert [i.fracionavel for i in catalogo_avulsa()] == [fracionavel]


def test_limpeza_decide_pela_unidade_do_scpi_e_nao_pela_exibida():
    material("D", nome="DETERGENTE", unidade="UN", estoque=5)
    material("K", nome="CAFÉ", unidade="KG", estoque=5)
    limpeza("D", unidade_exibida="Pacote 500 g")
    limpeza("K", unidade_exibida="Pacote")
    itens = {i.codigo: i for i in catalogo_limpeza()}
    assert (itens["D"].unidade, itens["D"].fracionavel) == ("Pacote 500 g", False)
    assert (itens["K"].unidade, itens["K"].fracionavel) == ("Pacote", True)


def test_ab_decide_pela_unidade_do_codigo_canonico():
    agora = timezone.now()
    material("000.000.001", unidade="UN", estoque=7, estoque_em=agora)
    material("001.001.001", unidade="M", estoque=3, estoque_em=agora)
    saidas("000.000.001", 3)
    saidas("001.001.001", 1)
    par("000.000.001", "001.001.001")
    (item,) = catalogo_ab(HOJE).itens
    assert (item.codigo, item.unidade, item.fracionavel) == ("001.001.001", "M", True)


def test_lista_de_unidades_vazia_deixa_tudo_inteiro():
    Opcao.objects.filter(lista=Opcao.Lista.UNIDADE_FRACIONAVEL).delete()
    material("A", unidade="KG", estoque=5)
    material("B", unidade="M", estoque=5)
    assert [i.fracionavel for i in catalogo_avulsa()] == [False, False]


def test_a_lista_de_unidades_vale_no_proximo_catalogo_sem_reiniciar():
    material("A", unidade="KG", estoque=5)
    assert catalogo_avulsa()[0].fracionavel is True
    Opcao.objects.filter(lista=Opcao.Lista.UNIDADE_FRACIONAVEL, valor="KG").update(ativo=False)
    assert catalogo_avulsa()[0].fracionavel is False
