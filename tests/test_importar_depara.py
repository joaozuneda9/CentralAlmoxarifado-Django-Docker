from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError, call_command
from django.db import DatabaseError
from django.utils import timezone

from catalogo.models import Importacao, Material, ParDePara
from implantacao.depara import ler_pares
from tests.depara_exemplo import ABA_MAPEAMENTO, abas_depara, salvar_depara, salvar_xlsx

ACEITOS = {
    ("000.029.872", "016.001.021", Decimal("1")),
    ("010.000.113", "023.004.001", Decimal("5")),
    ("000.000.020", "000.000.021", Decimal("1")),
    ("003.000.025", "003.001.002", Decimal("1")),
    ("004.000.019", "004.001.019", Decimal("1")),
}


@pytest.fixture
def planilha(tmp_path):
    return salvar_depara(tmp_path / "mapeamento.xlsx")


def importar(caminho, *extra):
    saida = StringIO()
    call_command("importar_depara", "--arquivo", str(caminho), *extra, stdout=saida)
    return saida.getvalue()


# ---------------------------------------------------------------- leitura (sem banco)


def test_leitura_combina_mapeamento_e_correcoes(planilha):
    carga = ler_pares(planilha)
    assert {(p.antigo, p.novo, p.fator) for p in carga.pares} == ACEITOS
    assert carga.observacoes["010.000.113"] == "álcool 5 L virou 1 L"
    assert carga.lidos_mapeamento == 10
    assert carga.ignorados == 4
    assert carga.correcoes == 3


def test_leitura_lista_cada_recusado_com_aba_linha_e_motivo(planilha):
    carga = ler_pares(planilha)
    assert carga.recusados == [
        "DEPARA, linha 4: 004.000.022 → 004.001.022: fator inválido ('zero').",
        f"{ABA_MAPEAMENTO}, linha 6: 000.029.872 → 016.009.999: o código antigo já aparece na "
        "linha 2; vale a primeira ocorrência.",
        f"{ABA_MAPEAMENTO}, linha 10: 000.000.021 → 000.000.020: fecha um ciclo: "
        "000.000.021 → 000.000.020 → 000.000.021.",
    ]


@pytest.mark.parametrize("bruto", ["NaN", "inf", "-Infinity"])
def test_leitura_recusa_fator_que_nao_e_finito(tmp_path, bruto):
    abas = abas_depara()
    abas["DEPARA"][1]["Fator p/ Qtd"] = bruto
    carga = ler_pares(salvar_xlsx(abas, tmp_path / "x.xlsx"))
    assert "004.000.019" not in {p.antigo for p in carga.pares}
    assert f"DEPARA, linha 3: 004.000.019 → 004.001.019: fator inválido ('{bruto}')." in (
        carga.recusados
    )


def test_leitura_guarda_a_observacao_da_primeira_ocorrencia(tmp_path):
    abas = abas_depara()
    abas["DEPARA"].append(abas["DEPARA"][0] | {"Observação": "outra"})
    carga = ler_pares(salvar_xlsx(abas, tmp_path / "x.xlsx"))
    assert carga.observacoes["010.000.113"] == "álcool 5 L virou 1 L"


def test_leitura_recusa_observacao_maior_que_o_campo(tmp_path):
    abas = abas_depara()
    abas["DEPARA"][1]["Observação"] = "x" * 256
    carga = ler_pares(salvar_xlsx(abas, tmp_path / "x.xlsx"))
    assert "004.000.019" not in {p.antigo for p in carga.pares}
    assert (
        "DEPARA, linha 3: 004.000.019 → 004.001.019: observação com 256 caracteres (máximo 255)."
        in carga.recusados
    )


def test_leitura_aceita_outro_nome_que_comece_por_planilha_de_mapeamento(tmp_path):
    # O .xlsx não aceita "/" no nome da aba: o Google tira a barra de "de/para" ao exportar.
    caminho = salvar_xlsx(abas_depara("Planilha de mapeamento de para"), tmp_path / "x.xlsx")
    assert len(ler_pares(caminho).pares) == 5


def test_leitura_sem_a_aba_de_mapeamento_e_erro(tmp_path):
    abas = abas_depara()
    del abas[ABA_MAPEAMENTO]
    from implantacao.planilha import ErroPlanilha

    with pytest.raises(ErroPlanilha, match="aba de mapeamento"):
        ler_pares(salvar_xlsx(abas, tmp_path / "x.xlsx"))


def test_leitura_sem_coluna_obrigatoria_e_erro(tmp_path):
    abas = abas_depara()
    for linha in abas["DEPARA"]:
        del linha["Código Novo"]
    from implantacao.planilha import ErroPlanilha

    with pytest.raises(ErroPlanilha, match='DEPARA: coluna "Código Novo" não encontrada.'):
        ler_pares(salvar_xlsx(abas, tmp_path / "x.xlsx"))


# ---------------------------------------------------------------- comando (com banco)


@pytest.mark.django_db
def test_ensaio_nao_grava_nada(planilha):
    texto = importar(planilha, "--dry-run")
    assert ParDePara.objects.count() == 0
    assert not Importacao.objects.exists()
    assert "Pares que seriam gravados: 5." in texto
    assert "Simulação: nada foi gravado." in texto
    assert "fecha um ciclo" in texto
    # O console do Windows (cp1252) não imprime "→".
    assert "→" not in texto and "000.000.021 -> 000.000.020" in texto
    texto.encode("cp1252")


@pytest.mark.django_db
def test_carga_substitui_os_pares_e_registra_a_importacao(planilha):
    Material.objects.create(codigo="016.001.021", nome="TUBO PEAD")
    ParDePara.objects.create(antigo="000.000.099", novo="001.001.099", origem="PLANILHA")
    texto = importar(planilha)
    assert {(p.antigo, p.novo, p.fator) for p in ParDePara.objects.all()} == ACEITOS
    assert set(ParDePara.objects.values_list("origem", flat=True)) == {"PLANILHA"}
    assert ParDePara.objects.get(antigo="010.000.113").observacao == "álcool 5 L virou 1 L"
    imp = Importacao.objects.get()
    assert (imp.tipo, imp.situacao, imp.linhas) == ("DEPARA", "SUCESSO", 5)
    assert imp.fim is not None
    assert len(imp.avisos) == 3
    assert "Pares gravados: 5." in texto
    assert "Código novo ainda fora do cadastro (4):" in texto


@pytest.mark.django_db
def test_falha_ao_registrar_a_importacao_desfaz_a_carga(planilha, monkeypatch):
    ParDePara.objects.create(antigo="000.000.099", novo="001.001.099", origem="PLANILHA")

    def falhar(**campos):
        raise DatabaseError("conexão perdida")

    monkeypatch.setattr(Importacao.objects, "create", falhar)
    with pytest.raises(CommandError, match="nada foi gravado"):
        importar(planilha)
    assert list(ParDePara.objects.values_list("antigo", flat=True)) == ["000.000.099"]


@pytest.mark.django_db
def test_recusa_com_par_criado_no_sistema(planilha):
    ParDePara.objects.create(antigo="000.000.099", novo="001.001.099", origem="SISTEMA")
    with pytest.raises(CommandError, match="criados ou alterados no sistema"):
        importar(planilha)
    assert ParDePara.objects.count() == 1
    assert not Importacao.objects.exists()


@pytest.mark.django_db
def test_recusa_com_alteracao_no_admin_depois_da_ultima_carga(planilha):
    importar(planilha)
    par = ParDePara.objects.first()
    usuario = get_user_model().objects.create_user(username="1", password="x")
    LogEntry.objects.create(
        user=usuario,
        content_type=ContentType.objects.get_for_model(ParDePara),
        object_id=str(par.pk),
        object_repr=str(par),
        action_flag=CHANGE,
        action_time=timezone.now() + timedelta(seconds=1),
    )
    with pytest.raises(CommandError, match="criados ou alterados no sistema"):
        importar(planilha)
    assert Importacao.objects.count() == 1


@pytest.mark.django_db
def test_recarga_sem_alteracao_no_sistema_e_aceita(planilha):
    importar(planilha)
    importar(planilha)
    assert ParDePara.objects.count() == 5
    assert Importacao.objects.count() == 2


@pytest.mark.django_db
def test_recusa_com_outra_carga_em_andamento(planilha, trava_importacao_ocupada):
    trava_importacao_ocupada("DEPARA")
    with pytest.raises(CommandError, match="em andamento"):
        importar(planilha)
    assert ParDePara.objects.count() == 0


@pytest.mark.django_db
def test_arquivo_inexistente(tmp_path):
    with pytest.raises(CommandError, match="Arquivo não encontrado"):
        importar(tmp_path / "nao-existe.xlsx")
