"""Saída avulsa e de/para: a busca mostra só o código novo, que lista os antigos, e avisa quando o
saldo ficou num código antigo."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalogo.catalogos import CodigoAntigo, catalogo_avulsa
from catalogo.models import Material, ParDePara
from pedidos.carrinho import motivo_bloqueio
from pedidos.fluxos import FLUXOS, buscar
from pedidos.regras import LIMPEZA
from tests.cenario import criar_pedido, montar_cenario
from tests.papeis import dar_papeis

pytestmark = pytest.mark.django_db
AVULSA = FLUXOS["avulsa"]
NOVO = "900.000.001"
ANTIGO = "000.900.001"
OUTRO_ANTIGO = "000.900.002"


@pytest.fixture
def usuario():
    return dar_papeis(
        get_user_model().objects.create_user(username="12345", password="x", first_name="Ana")
    )


def material(codigo, estoque="0", unidade="UN", **campos):
    campos.setdefault("nome", f"MATERIAL {codigo}")
    return Material.objects.create(
        codigo=codigo, estoque=Decimal(estoque), unidade=unidade, **campos
    )


def par(antigo, novo):
    ParDePara.objects.create(antigo=antigo, novo=novo)


def codigos():
    return [i.codigo for i in catalogo_avulsa()]


def item(codigo):
    return next(i for i in catalogo_avulsa() if i.codigo == codigo)


# ---------------------------------------------------------------- catálogo


def test_codigo_antigo_sai_do_catalogo_e_o_novo_o_lista():
    material(NOVO, "5")
    material(ANTIGO, "3")
    par(ANTIGO, NOVO)
    assert codigos() == [NOVO]
    assert item(NOVO).antigos == (CodigoAntigo(ANTIGO, Decimal("3"), "UN"),)


def test_material_sem_par_nao_muda():
    material(NOVO, "5")
    assert item(NOVO).antigos == ()


def test_novo_zerado_entra_so_quando_algum_antigo_tem_saldo():
    material(NOVO)
    material(ANTIGO, "3")
    par(ANTIGO, NOVO)
    material("900.000.002")
    material(OUTRO_ANTIGO)
    par(OUTRO_ANTIGO, "900.000.002")
    assert codigos() == [NOVO]
    assert item(NOVO).antigos_com_saldo == (CodigoAntigo(ANTIGO, Decimal("3"), "UN"),)


def test_dois_antigos_cada_um_com_seu_saldo_e_unidade():
    material(NOVO, unidade="BR")
    material(ANTIGO, "4", unidade="UN")
    material(OUTRO_ANTIGO, "2", unidade="BR")
    par(OUTRO_ANTIGO, NOVO)
    par(ANTIGO, NOVO)
    assert codigos() == [NOVO]
    assert item(NOVO).antigos == (
        CodigoAntigo(ANTIGO, Decimal("4"), "UN"),
        CodigoAntigo(OUTRO_ANTIGO, Decimal("2"), "BR"),
    )


def test_saldo_de_antigo_oculto_ou_fora_do_cadastro_nao_conta():
    material(NOVO)
    material(ANTIGO, "5", oculto=True)
    par(ANTIGO, NOVO)
    par(OUTRO_ANTIGO, NOVO)  # fora do cadastro
    assert codigos() == []
    Material.objects.filter(codigo=NOVO).update(estoque=2)
    assert item(NOVO).antigos == (
        CodigoAntigo(ANTIGO, Decimal("0"), "UN"),
        CodigoAntigo(OUTRO_ANTIGO, Decimal("0"), ""),
    )


def test_cadeia_de_pares_leva_ao_canonico():
    material("000.900.003", "4")
    material(ANTIGO, "6")
    material(NOVO)
    par("000.900.003", ANTIGO)
    par(ANTIGO, NOVO)
    assert codigos() == [NOVO]
    assert [a.codigo for a in item(NOVO).antigos] == [ANTIGO, "000.900.003"]


def test_novo_oculto_esconde_tambem_o_antigo():
    material(NOVO, "5", oculto=True)
    material(ANTIGO, "3")
    par(ANTIGO, NOVO)
    assert codigos() == []


# ---------------------------------------------------------------- busca e bloqueio


def test_busca_pelo_codigo_antigo_acha_o_novo():
    material(NOVO, "5")
    material(ANTIGO, "3")
    par(ANTIGO, NOVO)
    achados, total = buscar(AVULSA, catalogo_avulsa(), ANTIGO, "")
    assert ([i.codigo for i in achados], total) == ([NOVO], 1)


def test_motivo_do_bloqueio_diz_onde_esta_o_saldo():
    material(NOVO, unidade="BR")
    material(ANTIGO, "4")
    par(ANTIGO, NOVO)
    assert motivo_bloqueio(AVULSA, item(NOVO)) == f"Saldo só no código antigo {ANTIGO}: 4 UN"
    material(OUTRO_ANTIGO, "2.5", unidade="BR")
    par(OUTRO_ANTIGO, NOVO)
    assert motivo_bloqueio(AVULSA, item(NOVO)) == (
        f"Saldo só nos códigos antigos {ANTIGO} (4 UN) e {OUTRO_ANTIGO} (2,5 BR)"
    )


def test_saldo_do_antigo_vem_com_as_quatro_casas_do_cadastro():
    material(NOVO, unidade="KG")
    material(ANTIGO, "0.0004", unidade="KG")
    par(ANTIGO, NOVO)
    assert motivo_bloqueio(AVULSA, item(NOVO)) == f"Saldo só no código antigo {ANTIGO}: 0,0004 KG"


def test_motivo_com_saldo_no_novo_nao_muda():
    material(NOVO, "1")
    material(ANTIGO, "4")
    par(ANTIGO, NOVO)
    assert motivo_bloqueio(AVULSA, item(NOVO)) == ""


# ---------------------------------------------------------------- telas


def resultados_html(client, usuario, q):
    client.force_login(usuario)
    return client.get(reverse("pedidos:avulsa_materiais"), {"q": q}).content.decode()


def test_resultado_mostra_o_que_substitui_e_a_nota_do_saldo_que_sobrou(client, usuario):
    material(NOVO, "5", nome="TUBO NOVO")
    material(ANTIGO, "3", nome="TUBO ANTIGO")
    material(OUTRO_ANTIGO)
    par(ANTIGO, NOVO)
    par(OUTRO_ANTIGO, NOVO)
    html = resultados_html(client, usuario, "tubo")
    assert "TUBO ANTIGO" not in html
    assert (
        f'substitui <span class="mono">{ANTIGO}</span> e <span class="mono">{OUTRO_ANTIGO}</span>'
        in html
    )
    assert f'Ainda há saldo no código antigo <span class="mono">{ANTIGO}</span>: 3 UN.' in html
    assert "aviso-atencao" not in html
    assert "data-adicionar-abrir" in html


def test_resultado_bloqueado_mostra_o_alerta_com_cada_antigo(client, usuario):
    material(NOVO, nome="TUBO NOVO", unidade="BR")
    material(ANTIGO, "4")
    material(OUTRO_ANTIGO, "2", unidade="BR")
    par(ANTIGO, NOVO)
    par(OUTRO_ANTIGO, NOVO)
    html = resultados_html(client, usuario, "tubo")
    assert "aviso aviso-atencao material-alerta" in html
    assert "Saldo só nos códigos antigos:" in html
    assert f'<li><span class="mono">{ANTIGO}</span>: 4 UN</li>' in html
    assert f'<li><span class="mono">{OUTRO_ANTIGO}</span>: 2 BR</li>' in html
    assert "Acerte o saldo no SCPI para dar saída por este código." in html
    assert "material-bloqueado" in html
    assert "data-adicionar-abrir" not in html
    assert "selo-aviso" not in html  # o alerta substitui o selo "Sem estoque"


def test_resultado_bloqueado_com_um_antigo_vem_numa_frase(client, usuario):
    material(NOVO, nome="TUBO NOVO")
    material(ANTIGO, "4")
    par(ANTIGO, NOVO)
    html = resultados_html(client, usuario, "tubo")
    assert f'Saldo só no código antigo <span class="mono">{ANTIGO}</span>: 4 UN.' in html
    assert "material-alerta-lista" not in html


def test_atendimento_recusa_o_novo_sem_saldo_e_nao_acha_o_antigo(client, usuario):
    montar_cenario()
    pedido = criar_pedido(origem=LIMPEZA, itens=(("023.001.002", "2"),))
    material(NOVO, nome="TUBO NOVO")
    material(ANTIGO, "4")
    par(ANTIGO, NOVO)
    client.force_login(usuario)
    url = reverse("pedidos:atendimento_adicionar", args=[pedido.numero])
    r = client.post(url, {"adicionar": NOVO, f"qtd-{NOVO}": "1"})
    assert r["HX-Retarget"] == "#adicionar-erro"
    assert f"Saldo só no código antigo {ANTIGO}: 4 UN" in r.text
    r = client.post(url, {"adicionar": ANTIGO, f"qtd-{ANTIGO}": "1"})
    assert "Material não encontrado no catálogo." in r.text
