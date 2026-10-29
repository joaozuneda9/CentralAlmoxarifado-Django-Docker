from decimal import Decimal

import pytest

from catalogo.depara import (
    CicloDePara,
    LinhaSaidas,
    Par,
    canonico_de,
    consolidar,
    resolver_canonicos,
    validar_par,
)
from catalogo.models import ParDePara

# ---------------------------------------------------------------- validar_par (puro)


def test_par_valido_nao_tem_erros():
    assert validar_par("000.029.872", "016.001.021", Decimal("1")) == []


@pytest.mark.parametrize(
    ("antigo", "novo", "erro"),
    [
        ("29.872", "016.001.021", 'O código antigo "29.872" não está no formato 000.000.000.'),
        (
            "000.029.872",
            "PRODUTO NOVO",
            'O código novo "PRODUTO NOVO" não está no formato 000.000.000.',
        ),
        ("", "016.001.021", 'O código antigo "" não está no formato 000.000.000.'),
    ],
)
def test_par_fora_do_formato(antigo, novo, erro):
    assert validar_par(antigo, novo, Decimal("1")) == [erro]


def test_par_com_codigos_iguais():
    assert validar_par("016.001.021", "016.001.021", Decimal("1")) == [
        "O código antigo e o código novo são iguais."
    ]


@pytest.mark.parametrize("fator", [Decimal("0"), Decimal("-1"), None])
def test_par_com_fator_invalido(fator):
    assert validar_par("000.029.872", "016.001.021", fator) == [
        "O fator precisa ser maior que zero."
    ]


def test_par_junta_todos_os_erros():
    assert validar_par("x", "x", Decimal("0")) == [
        'O código antigo "x" não está no formato 000.000.000.',
        'O código novo "x" não está no formato 000.000.000.',
        "O código antigo e o código novo são iguais.",
        "O fator precisa ser maior que zero.",
    ]


# ---------------------------------------------------------------- resolver_canonicos (puro)


def test_codigo_sem_par_e_canonico_de_si_mesmo():
    assert canonico_de("003.001.001", resolver_canonicos([])) == ("003.001.001", Decimal("1"))


def test_par_simples():
    canonicos = resolver_canonicos([Par("000.000.001", "001.001.001")])
    assert canonico_de("000.000.001", canonicos) == ("001.001.001", Decimal("1"))
    assert canonico_de("001.001.001", canonicos) == ("001.001.001", Decimal("1"))


def test_cadeia_e_resolvida_ate_o_fim_e_multiplica_os_fatores():
    canonicos = resolver_canonicos(
        [
            Par("000.000.001", "001.001.001", Decimal("5")),
            Par("001.001.001", "002.002.002", Decimal("2")),
        ]
    )
    assert canonico_de("000.000.001", canonicos) == ("002.002.002", Decimal("10"))
    assert canonico_de("001.001.001", canonicos) == ("002.002.002", Decimal("2"))


def test_varios_antigos_para_o_mesmo_novo():
    canonicos = resolver_canonicos(
        [Par("000.000.001", "001.001.001"), Par("000.000.002", "001.001.001")]
    )
    assert canonico_de("000.000.001", canonicos)[0] == "001.001.001"
    assert canonico_de("000.000.002", canonicos)[0] == "001.001.001"


def test_ciclo_e_erro_citando_os_codigos():
    with pytest.raises(CicloDePara) as erro:
        resolver_canonicos(
            [
                Par("000.000.001", "000.000.002"),
                Par("000.000.002", "000.000.003"),
                Par("000.000.003", "000.000.001"),
            ]
        )
    assert "000.000.001 → 000.000.002 → 000.000.003 → 000.000.001" in str(erro.value)


def test_compara_os_codigos_por_norm_u():
    canonicos = resolver_canonicos([Par("000.000.00a", "001.001.001")])
    assert canonico_de("000.000.00A", canonicos)[0] == "001.001.001"


# ---------------------------------------------------------------- consolidar (puro)


def test_consolidar_soma_pelo_canonico_e_aplica_o_fator_so_na_quantidade():
    canonicos = resolver_canonicos([Par("000.000.001", "001.001.001", Decimal("5"))])
    linhas = [
        LinhaSaidas("000.000.001", 30, Decimal("2"), Decimal("10.5")),
        LinhaSaidas("001.001.001", 20, Decimal("7"), Decimal("3")),
        LinhaSaidas("003.003.003", 1, Decimal("1"), Decimal("1")),
    ]
    resultado = {c.canonico: c for c in consolidar(linhas, canonicos)}
    assert set(resultado) == {"001.001.001", "003.003.003"}
    novo = resultado["001.001.001"]
    assert (novo.ocorrencias, novo.qtd, novo.valor) == (50, Decimal("17"), Decimal("13.5"))


def test_consolidar_vazio():
    assert consolidar([], {}) == []


# ---------------------------------------------------------------- admin dos pares (com banco)


def criar_pelo_admin(client, antigo, novo, fator="1"):
    from django.urls import reverse

    return client.post(
        reverse("admin:catalogo_pardepara_add"),
        {"antigo": antigo, "novo": novo, "fator": fator, "observacao": ""},
        follow=True,
    )


@pytest.mark.django_db
def test_admin_cria_par_com_origem_sistema_e_registra_no_historico(admin_client):
    from django.contrib.admin.models import LogEntry

    from catalogo.models import Material, ParDePara

    Material.objects.create(codigo="016.001.021", nome="TUBO PEAD")
    resposta = criar_pelo_admin(admin_client, "000.029.872", "016.001.021")
    assert resposta.status_code == 200
    par = ParDePara.objects.get()
    assert (par.antigo, par.novo, par.origem) == ("000.029.872", "016.001.021", "SISTEMA")
    assert LogEntry.objects.filter(object_id=str(par.pk)).exists()
    assert "ainda não está no cadastro" not in resposta.text


@pytest.mark.django_db
def test_admin_avisa_quando_o_novo_nao_tem_cadastro(admin_client):
    resposta = criar_pelo_admin(admin_client, "000.029.872", "016.001.021")
    assert ParDePara.objects.count() == 1
    assert "O código 016.001.021 ainda não está no cadastro do SCPI." in resposta.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("antigo", "novo", "fator", "erro"),
    [
        ("29.872", "016.001.021", "1", "não está no formato 000.000.000."),
        ("016.001.021", "016.001.021", "1", "O código antigo e o código novo são iguais."),
        ("000.029.872", "016.001.021", "0", "O fator precisa ser maior que zero."),
    ],
)
def test_admin_recusa_par_invalido(admin_client, antigo, novo, fator, erro):
    resposta = criar_pelo_admin(admin_client, antigo, novo, fator)
    assert ParDePara.objects.count() == 0
    assert erro in resposta.text


@pytest.mark.django_db
def test_admin_recusa_segundo_destino_para_o_mesmo_antigo(admin_client):
    ParDePara.objects.create(antigo="000.029.872", novo="016.001.021")
    resposta = criar_pelo_admin(admin_client, "000.029.872", "016.001.099")
    assert ParDePara.objects.count() == 1
    assert (
        "O código 000.029.872 já aponta para 016.001.021. Um código antigo tem um só destino."
        in resposta.text
    )


@pytest.mark.django_db
def test_admin_recusa_ciclo(admin_client):
    ParDePara.objects.create(antigo="000.000.001", novo="000.000.002")
    resposta = criar_pelo_admin(admin_client, "000.000.002", "000.000.001")
    assert ParDePara.objects.count() == 1
    assert "O par 000.000.002 → 000.000.001 fecha um ciclo" in resposta.text


@pytest.mark.django_db
def test_admin_alterar_par_da_planilha_marca_origem_sistema(admin_client):
    from django.urls import reverse

    par = ParDePara.objects.create(antigo="000.000.001", novo="001.001.001", origem="PLANILHA")
    admin_client.post(
        reverse("admin:catalogo_pardepara_change", args=[par.pk]),
        {"antigo": "000.000.001", "novo": "001.001.002", "fator": "1", "observacao": ""},
    )
    par.refresh_from_db()
    assert (par.novo, par.origem) == ("001.001.002", "SISTEMA")
