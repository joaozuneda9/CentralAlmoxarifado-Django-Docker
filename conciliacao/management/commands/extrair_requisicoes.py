from django.core.management import BaseCommand, CommandError

from catalogo.models import Importacao
from conciliacao.extracao import extrair
from conciliacao.models import ExtracaoOficial
from conciliacao.robo import resumo_da_contagem
from conciliacao.servicos import ConciliacaoEmAndamento, ConciliacaoIncompleta, conciliar
from scpi import relatorios
from scpi.execucao import ImportacaoEmAndamento
from scpi.management.comum import data_opcao, obter_csv


class Command(BaseCommand):
    help = (
        "Extrai do SCPI a Relação de Requisições de saída de todos os tipos no período, a guarda "
        "(arquivo bruto e requisições) e concilia os lotes lançados e em verificar. Só lê o SCPI."
    )

    def add_arguments(self, parser):
        parser.add_argument("--desde", required=True, help="Início do período (dd/mm/aaaa).")
        parser.add_argument("--ate", required=True, help="Fim do período (dd/mm/aaaa).")
        parser.add_argument("--arquivo", help="CSV já baixado do SCPI (não abre o navegador).")

    def handle(self, *args, desde, ate, arquivo=None, **opcoes):
        de, ate = data_opcao(desde), data_opcao(ate)
        if de > ate:
            raise CommandError("O início do período é depois do fim.")
        try:
            extracao = extrair(
                ExtracaoOficial.Motivo.ARQUIVO if arquivo else ExtracaoOficial.Motivo.MANUAL,
                (de, ate),
                obter_csv(arquivo, lambda: relatorios.baixar_requisicoes(de, ate)),
            )
        except ImportacaoEmAndamento:
            raise CommandError("Extração de requisições do SCPI já em andamento.") from None
        importacao = extracao.importacao
        if importacao.situacao != Importacao.Situacao.SUCESSO:
            raise CommandError(importacao.erro)
        maior = extracao.maior_requisicao or "nenhuma"
        self.stdout.write(
            f"Requisições do SCPI ({de:%d/%m/%Y} a {ate:%d/%m/%Y}): {extracao.requisicoes} "
            f"requisições, a maior {maior}."
        )
        try:
            contagem = conciliar(extracao)
        except ConciliacaoEmAndamento as exc:
            raise CommandError(str(exc)) from None
        except ConciliacaoIncompleta as exc:
            parcial = resumo_da_contagem(exc.contagem) or "nada gravado"
            raise CommandError(f"{exc} (gravado: {parcial}).") from None
        if contagem:
            self.stdout.write(f"  Conciliação: {resumo_da_contagem(contagem)}.")
