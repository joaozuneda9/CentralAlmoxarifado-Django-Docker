from datetime import timedelta

from django.core.management import BaseCommand, CommandError
from django.utils import timezone

from catalogo.models import Importacao
from conciliacao import regras
from conciliacao.extracao import extrair
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
        "lotes lançados e os em verificar cobertos. Só lê o SCPI; nunca muda as linhas de saída."
    )

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", help="CSV já baixado do SCPI (não abre o navegador).")
        parser.add_argument("--desde", help="Início do período (dd/mm/aaaa).")
        parser.add_argument("--ate", help="Fim do período (dd/mm/aaaa).")

    def handle(self, *args, arquivo=None, desde=None, ate=None, **opcoes):
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
            extracao = extrair(
                ExtracaoOficial.Motivo.ARQUIVO if arquivo else ExtracaoOficial.Motivo.MANUAL,
                periodo,
                obter_csv(arquivo, lambda: relatorios.baixar_requisicoes(de, ate)),
            )
        except ImportacaoEmAndamento:
            raise CommandError("Extração de requisições do SCPI já em andamento.") from None
        if not extracao.bem_sucedida:
            raise CommandError(extracao.importacao.erro)
        try:
            contagem = conciliar(extracao)
        except ConciliacaoEmAndamento as exc:
            raise CommandError(str(exc)) from None
        except ConciliacaoIncompleta as exc:
            parcial = resumo_da_contagem(exc.contagem) or "nada gravado"
            raise CommandError(f"{exc} (gravado: {parcial}).") from None
        self.stdout.write(
            f"Requisições do SCPI ({de:%d/%m/%Y} a {ate:%d/%m/%Y}): {extracao.requisicoes}. "
            f"Conciliação: {resumo_da_contagem(contagem) or 'nenhum lote a conferir'}."
        )
