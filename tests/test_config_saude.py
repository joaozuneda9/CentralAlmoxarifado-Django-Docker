"""A saúde do catálogo com a configuração por formulário (spec 009, FR-039): formulário sem destino,
centro ativo sem formulário e exceção sem efeito (formulário sem material já era avisado)."""

import pytest

from catalogo.models import CentroCusto, CentroFormulario, ExcecaoMaterial, Formulario, Material
from catalogo.saude import ItemSaude, saude_do_catalogo, situacao_do_catalogo
from tests.cenario import montar_cenario
from tests.config_cenario import criar_centro, excecao, material

pytestmark = pytest.mark.django_db

FITA = "016.005.010"  # na regra do AB
DETERGENTE = "023.001.002"  # na limpeza


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()


def textos():
    return [(i.nivel, i.texto) for i in saude_do_catalogo()]


def do_formulario(prefixo):
    return [(n, t) for n, t in textos() if t.startswith(prefixo)]


def test_com_destinos_nao_ha_aviso_de_destino():
    for prefixo in ("Formulário de limpeza", "Formulário AB", "Formulário de EPIs"):
        assert all("destino" not in t for _, t in do_formulario(prefixo))


@pytest.mark.parametrize(
    ("formulario", "prefixo"),
    [
        (Formulario.LIMPEZA, "Formulário de limpeza"),
        (Formulario.AB, "Formulário AB"),
        (Formulario.EPIS, "Formulário de EPIs"),
    ],
)
def test_formulario_sem_destino_fica_indisponivel_e_a_saude_avisa(formulario, prefixo):
    CentroFormulario.objects.filter(formulario=formulario).delete()
    esperado = (
        "erro",
        f"{prefixo}: nenhum centro de custo habilitado como destino; o formulário fica "
        "indisponível.",
    )
    assert esperado in textos()


def test_sem_nenhum_centro_so_o_aviso_geral():
    CentroCusto.objects.all().delete()
    ts = [t for _, t in textos()]
    assert any(t.startswith("Nenhum centro de custo cadastrado") for t in ts)
    assert not any("habilitado como destino" in t for t in ts if "viaturas" not in t)


def test_oficina_sem_a_linha_do_centro_da_oficina_diz_que_nao_esta_habilitado():
    CentroFormulario.objects.filter(
        formulario=Formulario.OFICINA, centro__descricao="OFICINA MECÂNICA"
    ).delete()
    texto = next(t for _, t in textos() if t.startswith("Formulário da oficina mecânica: centro"))
    assert "OFICINA MECÂNICA não está habilitado como destino" in texto
    assert "só as viaturas" in texto


def test_centro_ativo_sem_nenhum_formulario_e_aviso():
    criar_centro("SETOR NOVO", "90")
    criar_centro("OUTRO NOVO", "91")
    assert (
        "aviso",
        "Centros de custo ativos sem nenhum formulário (não são destino de nenhum): "
        "OUTRO NOVO, SETOR NOVO.",
    ) in textos()


def test_centro_inativo_sem_formulario_nao_e_aviso_nem_o_habilitado():
    criar_centro("PARADO", "92", ativo=False)
    criar_centro("COM FORMULARIO", "93", formularios=[Formulario.AB])
    assert not any("sem nenhum formulário" in t for _, t in textos())


def test_o_aviso_e_por_linha_do_cadastro_com_a_placa_quando_ha():
    criar_centro("DUAS LINHAS", "94", "AAA1A11", formularios=[Formulario.AB])
    criar_centro("DUAS LINHAS", "94", "BBB2B22")
    avisos = [t for _, t in textos() if "sem nenhum formulário" in t]
    assert avisos and "DUAS LINHAS — BBB2B22" in avisos[0] and "AAA1A11" not in avisos[0]


def test_sem_excecoes_nao_ha_aviso_de_excecao():
    assert not any("sem efeito" in t for _, t in textos())


def test_excecao_sem_efeito_e_aviso_por_formulario():
    excecao(Formulario.AB, Material.objects.get(codigo=FITA), True)  # o AB já traz
    excecao(Formulario.AB, material("900.000.001", "TESOURA", "ALMOX"), False)  # não traz
    excecao(Formulario.LIMPEZA, Material.objects.get(codigo=DETERGENTE), True)  # a limpeza já traz
    ts = [t for n, t in textos() if n == "aviso" and "sem efeito" in t]
    assert (
        "Exceções sem efeito em Ferramentas, peças e materiais (a regra já dá o resultado): "
        "016.005.010, 900.000.001." in ts
    )
    assert (
        "Exceções sem efeito em Limpeza, copa e escritório (a regra já dá o resultado): "
        "023.001.002." in ts
    )


def test_excecao_com_efeito_nao_e_aviso():
    excecao(Formulario.AB, Material.objects.get(codigo=FITA), False)  # retira o que o AB traz
    excecao(Formulario.AB, material("900.000.001", "TESOURA", "ALMOX"), True)  # acrescenta
    assert not any("sem efeito" in t for _, t in textos())


def test_a_visao_geral_conta_o_catalogo_efetivo():
    antes = situacao_do_catalogo()
    excecao(Formulario.LIMPEZA, Material.objects.get(codigo=DETERGENTE), False)
    excecao(Formulario.OFICINA, material("900.000.002", "ALICATE", "ALMOX"), True)
    depois = situacao_do_catalogo()
    assert depois.limpeza == antes.limpeza - 1
    assert depois.oficina == antes.oficina + 1


def test_formulario_sem_material_depois_das_excecoes_e_erro():
    for codigo in ("023.001.002", "008.001.002", "023.004.001"):
        excecao(Formulario.LIMPEZA, Material.objects.get(codigo=codigo), False)
    assert (
        ItemSaude(
            "erro",
            "Formulário de limpeza: nenhum item no catálogo; o formulário fica indisponível.",
        )
        in saude_do_catalogo()
    )
    assert ExcecaoMaterial.objects.count() == 3


def test_viaturas_sem_material_depois_das_excecoes_e_erro():
    from catalogo.catalogos import catalogo_efetivo

    for item in catalogo_efetivo(Formulario.VIATURAS):
        excecao(Formulario.VIATURAS, Material.objects.get(codigo=item.codigo), False)
    criar_centro("EQUIPE", "51", formularios=[Formulario.VIATURAS])
    assert (
        "erro",
        "Formulário de reposição de peças das viaturas: todos os materiais foram retirados do "
        "formulário; o formulário fica indisponível.",
    ) in textos()


def test_viaturas_so_com_materiais_acrescentados_esta_disponivel_e_nao_e_erro():
    """Sem peça na lista e sem material no AB, mas com acrescentado por exceção: o formulário
    oferece algo, então a saúde não pode dizer que ele está indisponível."""
    from catalogo.models import ItemLimpeza, SaidaSCPI

    SaidaSCPI.objects.all().delete()
    ItemLimpeza.objects.all().delete()
    criar_centro("EQUIPE", "51", formularios=[Formulario.VIATURAS])
    excecao(Formulario.VIATURAS, material("900.000.009", "TESOURA", "ALMOX"), True)
    avisos = [(n, t) for n, t in textos() if t.startswith("Formulário de reposição de peças")]
    assert avisos and all(n != "erro" for n, _ in avisos)


# --- O AB pela disponibilidade efetiva -----------------------------------------------------------


def test_ab_com_excecoes_conta_o_que_oferece_e_diz_de_onde_vem():
    excecao(Formulario.AB, Material.objects.get(codigo=FITA), False)  # sai um
    excecao(Formulario.AB, material("900.000.001", "TESOURA", "ALMOX"), True)  # entra um
    textos_ab = [t for n, t in textos() if t.startswith("Formulário AB:")]
    assert len(textos_ab) == 1 and textos_ab[0].startswith(
        "Formulário AB: 3 itens, contadas as exceções"
    )
    assert "3 pela regra" in textos_ab[0]
    assert situacao_do_catalogo().ab_oferecidos == 3


def test_ab_sem_excecao_mantem_o_texto_de_sempre():
    (texto,) = [t for n, t in textos() if t.startswith("Formulário AB:")]
    assert texto.startswith("Formulário AB: 3 itens de ") and "exceções" not in texto


def test_ab_esvaziado_pelas_excecoes_e_erro_e_nao_ok():
    for codigo in (FITA, "013.006.001", "013.005.007"):
        excecao(Formulario.AB, Material.objects.get(codigo=codigo), False)
    assert (
        "erro",
        "Formulário AB: todos os materiais foram retirados do formulário; o formulário fica "
        "indisponível.",
    ) in textos()
    assert situacao_do_catalogo().ab_oferecidos == 0


def test_ab_sem_item_pela_regra_mas_com_acrescentado_esta_disponivel():
    from catalogo.models import SaidaSCPI

    SaidaSCPI.objects.all().delete()
    excecao(Formulario.AB, material("900.000.001", "TESOURA", "ALMOX"), True)
    textos_ab = [(n, t) for n, t in textos() if t.startswith("Formulário AB:")]
    assert textos_ab and all(n == "ok" for n, _ in textos_ab)
    assert situacao_do_catalogo().ab_oferecidos == 1
