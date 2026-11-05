import gzip
import hashlib
from datetime import date

import pytest
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from automacoes.historico import ROTULO_DO_TIPO, linha_de_importacao
from catalogo.models import Importacao
from conciliacao.extracao import extrair
from conciliacao.models import ExtracaoOficial, ItemOficial, RequisicaoOficial
from pedidos.models import ExecucaoRobo
from scpi.execucao import ImportacaoEmAndamento
from tests.relacao_requisicoes import ItemCSV, RequisicaoCSV, relatorio

pytestmark = pytest.mark.django_db

DIA = date(2026, 10, 23)
PERIODO = (date(2026, 10, 22), date(2026, 10, 24))


def _csv(*numeros, **campos):
    return relatorio([RequisicaoCSV(f"{n:06d}/26", n + 100, DIA, **campos) for n in numeros])


def _extrair(conteudo, motivo=ExtracaoOficial.Motivo.MANUAL, **opcoes):
    return extrair(motivo, PERIODO, lambda: conteudo, **opcoes)


def test_sucesso_guarda_bruto_impressao_e_requisicoes():
    conteudo = _csv(
        3588,
        3590,
        observacoes="Central Almoxarifado AV-000083",
        itens=[ItemCSV("006.011.020", "2"), ItemCSV("023.003.004", "1")],
    )
    extracao = _extrair(conteudo)
    extracao.refresh_from_db()
    imp = extracao.importacao
    assert (imp.tipo, imp.situacao, imp.linhas) == ("REQUISICOES", "SUCESSO", 2)
    assert (imp.periodo_de, imp.periodo_ate) == PERIODO
    assert gzip.decompress(bytes(extracao.arquivo)) == conteudo
    assert extracao.impressao == hashlib.sha256(conteudo).hexdigest()
    assert (extracao.requisicoes, extracao.maior_requisicao) == (2, "003590/26")
    req = RequisicaoOficial.objects.get(extracao=extracao, requisicao="003588/26")
    assert (req.ano, req.numero, req.id_requi, req.lote_observado) == (
        2026,
        3588,
        3688,
        "AV-000083",
    )
    assert list(req.itens.values_list("ordem", "codigo")) == [
        (1, "006.011.020"),
        (2, "023.003.004"),
    ]


def test_mesma_impressao_aponta_para_a_extracao_que_guarda_o_bruto():
    conteudo = _csv(3588)
    origem = _extrair(conteudo)
    repetida = _extrair(conteudo)
    repetida.refresh_from_db()
    assert repetida.arquivo is None
    assert repetida.mesmo_arquivo_que == origem
    assert repetida.requisicoes == 1  # as requisições são lidas de novo, uma foto por extração


def test_mesma_impressao_de_uma_origem_sem_bytes_guarda_o_seu():
    conteudo = _csv(3588)
    origem = _extrair(conteudo)
    ExtracaoOficial.objects.filter(pk=origem.pk).update(
        arquivo=None, arquivo_apagado_em=timezone.now()
    )
    nova = _extrair(conteudo)
    nova.refresh_from_db()
    assert gzip.decompress(bytes(nova.arquivo)) == conteudo
    assert nova.mesmo_arquivo_que is None


def test_relatorio_cortado_registra_a_falha_sem_requisicoes_e_guarda_o_bruto():
    texto = _csv(3588, 3589).decode("utf-8-sig").rstrip("\r\n")
    cortado = texto[: texto.rindex("BALCÃO")].encode("utf-8-sig")
    extracao = _extrair(cortado)
    extracao.refresh_from_db()
    assert extracao.importacao.situacao == "FALHA"
    assert "cortado" in extracao.importacao.erro
    assert (extracao.requisicoes, extracao.maior_requisicao) == (0, None)
    assert not RequisicaoOficial.objects.exists() and not ItemOficial.objects.exists()
    assert gzip.decompress(bytes(extracao.arquivo)) == cortado
    assert not extracao.bem_sucedida


def test_falha_no_download_registra_a_extracao_sem_bruto():
    def baixar():
        raise RuntimeError("SCPI fora do ar")

    extracao = extrair(ExtracaoOficial.Motivo.MANUAL, PERIODO, baixar)
    extracao.refresh_from_db()
    assert extracao.importacao.situacao == "FALHA"
    assert extracao.importacao.erro == "Falha inesperada: SCPI fora do ar"
    assert (extracao.impressao, extracao.arquivo, extracao.maior_requisicao) == ("", None, None)


def test_extracao_ligada_a_execucao_do_robo():
    execucao = ExecucaoRobo.objects.create()
    extracao = _extrair(_csv(3588), ExtracaoOficial.Motivo.ANTES, execucao=execucao)
    assert (extracao.motivo, extracao.execucao) == ("ANTES", execucao)


def test_trava_ocupada_nao_cria_registro(trava_importacao_ocupada):
    trava_importacao_ocupada("REQUISICOES")
    with pytest.raises(ImportacaoEmAndamento):
        _extrair(_csv(3588))
    assert not Importacao.objects.exists() and not ExtracaoOficial.objects.exists()


def test_comando_com_arquivo(tmp_path, capsys):
    arquivo = tmp_path / "requisicoes.csv"
    arquivo.write_bytes(_csv(3588, 3589))
    call_command("extrair_requisicoes", desde="22/10/2026", ate="24/10/2026", arquivo=str(arquivo))
    assert "2 requisições, a maior 003589/26" in capsys.readouterr().out
    assert ExtracaoOficial.objects.get().motivo == "MANUAL"


def test_comando_com_falha_sai_com_erro(tmp_path):
    arquivo = tmp_path / "requisicoes.csv"
    arquivo.write_bytes(relatorio([]))
    with pytest.raises(CommandError, match="nenhuma requisição"):
        call_command(
            "extrair_requisicoes", desde="22/10/2026", ate="24/10/2026", arquivo=str(arquivo)
        )


def test_historico_rotula_a_extracao():
    assert ROTULO_DO_TIPO["REQUISICOES"] == "Requisições do SCPI"


@pytest.mark.parametrize("motivo", ["ANTES", "DEPOIS"])
def test_antes_e_depois_exigem_a_execucao(motivo):
    with pytest.raises(ValueError, match="sem a execução"):
        _extrair(_csv(3588), motivo)
    assert not Importacao.objects.exists()


def test_banco_recusa_extracao_de_antes_sem_execucao():
    imp = Importacao.objects.create(tipo="REQUISICOES")
    with pytest.raises(IntegrityError), transaction.atomic():
        ExtracaoOficial.objects.create(importacao=imp, motivo="ANTES")


def test_historico_mostra_o_periodo_da_extracao():
    extracao = _extrair(_csv(3588))
    assert linha_de_importacao(extracao.importacao, set()).modo == "Período 22/10 a 24/10"


def test_dtpag_fora_do_periodo_faz_a_extracao_falhar():
    conteudo = _csv(3588, data_filtro=date(2026, 10, 25))
    extracao = _extrair(conteudo)
    extracao.refresh_from_db()
    assert extracao.importacao.situacao == "FALHA"
    assert "fora do período 22/10/2026 a 24/10/2026" in extracao.importacao.erro
    assert not RequisicaoOficial.objects.exists()
    assert gzip.decompress(bytes(extracao.arquivo)) == conteudo


def test_dtpag_nas_pontas_do_periodo_vale():
    _extrair(_csv(3588, data_filtro=date(2026, 10, 22)))
    extracao = _extrair(_csv(3589, data_filtro=date(2026, 10, 24)))
    assert extracao.importacao.situacao == "SUCESSO"
