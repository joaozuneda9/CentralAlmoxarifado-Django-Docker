import logging
from datetime import timedelta

from django.core.management import BaseCommand, CommandError
from django.utils import timezone

from catalogo.models import Importacao
from conciliacao import regras
from conciliacao.extracao import extrair
from conciliacao.limpeza import limpar
from conciliacao.models import ExtracaoOficial
from conciliacao.robo import resumo_da_contagem
from conciliacao.servicos import (
    TRAVADOS,
    ConciliacaoEmAndamento,
    ConciliacaoIncompleta,
    conciliar,
)
from pedidos.models import ExecucaoRobo, LinhaSaida
from scpi import relatorios
from scpi.execucao import ImportacaoEmAndamento
from scpi.leitura import ErroImportacao, ler_requisicoes
from scpi.management.comum import data_opcao, obter_csv

logger = logging.getLogger("scpi")
LIMPEZA_ADIADA = "adiada (extração ou conciliação em andamento)"

# A extração diária e a conferência pela tela voltam 9 dias (spec 010, decisão 8).
DIAS_DE_REVISAO = 9


def periodo_padrao(hoje):
    """De 9 dias atrás (e dos lotes em verificar abertos) até amanhã, com a folga de um dia."""
    datas = [hoje - timedelta(days=DIAS_DE_REVISAO)]
    datas += LinhaSaida.objects.filter(status__in=TRAVADOS).values_list("data", flat=True)
    return regras.periodo(datas, hoje)


def periodo_do_arquivo(arquivo: str):
    """O período que um CSV já baixado cobre: as datas de filtro (DTPAG) que ele traz."""
    with open(arquivo, "rb") as aberto:
        lidas = ler_requisicoes(aberto.read()).linhas
    datas = [lida.data_filtro or lida.data for lida in lidas]
    return min(datas), max(datas)


class Command(BaseCommand):
    help = (
        "Extrai do SCPI a Relação de Requisições sem filtro (ou lê o --arquivo) e concilia os "
        "lotes lançados e os em verificar cobertos; depois, a limpeza de 60 dias (salvo com "
        "--sem-limpeza). Só lê o SCPI; nunca muda as linhas de saída."
    )

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", help="CSV já baixado do SCPI (não abre o navegador).")
        parser.add_argument("--desde", help="Início do período (dd/mm/aaaa).")
        parser.add_argument("--ate", help="Fim do período (dd/mm/aaaa).")
        parser.add_argument(
            "--sem-limpeza",
            action="store_true",
            help="Não roda a limpeza de 60 dias depois da conciliação (repasse numa cópia local).",
        )
        parser.add_argument(
            "--diaria",
            action="store_true",
            help="Extração diária (o passo Requisições do atualizar_catalogo).",
        )

    def handle(
        self,
        *args,
        arquivo=None,
        desde=None,
        ate=None,
        sem_limpeza=False,
        diaria=False,
        **opcoes,
    ):
        if ExecucaoRobo.em_andamento().exists() or Importacao.em_andamento().exists():
            raise CommandError("Há lançamento ou importação em andamento; tente depois.")
        if bool(desde) != bool(ate):
            raise CommandError("Informe --desde e --ate juntos.")
        if desde:
            periodo = (data_opcao(desde), data_opcao(ate))
            if periodo[0] > periodo[1]:
                raise CommandError("O início do período é depois do fim.")
        elif arquivo:
            try:
                periodo = periodo_do_arquivo(arquivo)
            except ErroImportacao as exc:
                raise CommandError(str(exc)) from None
            except OSError as exc:
                raise CommandError(f"Não foi possível ler {arquivo}: {exc.strerror}.") from None
        else:
            periodo = periodo_padrao(timezone.localdate())
        de, ate = periodo
        try:
            if arquivo:
                motivo = ExtracaoOficial.Motivo.ARQUIVO
            elif diaria:
                motivo = ExtracaoOficial.Motivo.DIARIA
            else:
                motivo = ExtracaoOficial.Motivo.MANUAL
            extracao = extrair(
                motivo,
                periodo,
                obter_csv(arquivo, lambda: relatorios.baixar_requisicoes(de, ate)),
            )
        except ImportacaoEmAndamento:
            raise CommandError("Extração de requisições do SCPI já em andamento.") from None
        if not extracao.bem_sucedida:
            raise CommandError(extracao.importacao.erro)
        erros = []
        contagem = {}
        try:
            contagem = conciliar(extracao)
        except ConciliacaoEmAndamento as exc:
            erros.append(str(exc))
        except ConciliacaoIncompleta as exc:
            parcial = resumo_da_contagem(exc.contagem) or "nada gravado"
            erros.append(f"{exc} (gravado: {parcial}).")
        except Exception as exc:
            logger.exception("Conciliação com o SCPI falhou")
            erros.append(f"Conciliação com o SCPI falhou: {exc}.")
        # A limpeza roda mesmo com a conciliação com falha: ela não depende dos vereditos de
        # agora, e uma falha que se repetisse todo dia nunca deixaria apagar nada. A falha dela
        # também não esconde a da conciliação: as duas saem no erro do comando.
        if not sem_limpeza:
            try:
                limpeza = limpar()
            except Exception as exc:
                logger.exception("Limpeza de 60 dias da conciliação falhou")
                erros.append(f"Limpeza de 60 dias falhou: {exc}.")
            else:
                resumo = limpeza.resumo if limpeza else LIMPEZA_ADIADA
                self.stdout.write(f"Limpeza: {resumo}.")
        if erros:
            raise CommandError(" ".join(erros))
        self.stdout.write(
            f"Requisições do SCPI ({de:%d/%m/%Y} a {ate:%d/%m/%Y}): {extracao.requisicoes}. "
            f"Conciliação: {resumo_da_contagem(contagem) or 'nenhum lote a conferir'}."
        )
