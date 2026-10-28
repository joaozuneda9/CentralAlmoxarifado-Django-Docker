from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.utils import timezone

from pedidos.models import ExecucaoRobo
from scpi.lancador import navegador
from scpi.lancamento import LANCAMENTO_BLOQUEADO, LancamentoEmAndamento, executar_lancamento
from scpi.requisicoes import FalhaCritica


class Command(BaseCommand):
    help = "Lança no SCPI as saídas pendentes, uma requisição por lote (ou só as simula)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execucao",
            type=int,
            help="Execução já criada pelo botão da página (em andamento).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preenche o formulário e descarta, sem salvar nem alterar nenhuma linha.",
        )
        parser.add_argument(
            "--lote",
            action="append",
            dest="lotes",
            default=[],
            metavar="NÚMERO",
            help="Número da requisição (P-0123, AV-0004) a processar; repita para mais de uma.",
        )

    def handle(self, *args, execucao=None, dry_run=False, lotes=(), **opcoes):
        lotes = [lote.strip() for lote in lotes if lote.strip()]
        if not lotes:
            raise CommandError("Informe ao menos uma requisição com --lote (ex.: --lote P-0123).")
        registro = None
        if execucao is not None:
            registro = ExecucaoRobo.objects.filter(
                pk=execucao, situacao=ExecucaoRobo.Situacao.ANDAMENTO
            ).first()
            if registro is None:
                raise CommandError(f"Execução {execucao} não encontrada ou já encerrada.")

        # A simulação nunca vira lançamento real: um dos dois basta, e o que valer fica gravado.
        simulacao = dry_run or (registro is not None and registro.simulacao)

        # O modo é decidido antes de qualquer trabalho: com o lançamento real bloqueado, só a
        # simulação segue. Sem execução do botão, nada é criado; com ela, ela termina em falha.
        if not simulacao and not settings.LANCAMENTO_REAL:
            if registro is not None:
                registro.situacao = ExecucaoRobo.Situacao.FALHA
                registro.erro = LANCAMENTO_BLOQUEADO
                registro.fim = timezone.now()
                registro.save(update_fields=["situacao", "erro", "fim"])
            raise CommandError(LANCAMENTO_BLOQUEADO)

        if registro is None:
            registro = ExecucaoRobo.objects.create(iniciada_por=None)
        registro.simulacao = simulacao
        registro.save(update_fields=["simulacao"])

        try:
            registro = executar_lancamento(registro, navegador, lotes=lotes)
        except LancamentoEmAndamento as exc:
            raise CommandError("Outro lançamento já está em andamento.") from exc
        except FalhaCritica as exc:
            raise CommandError(str(exc), returncode=2) from exc

        if registro.situacao == ExecucaoRobo.Situacao.ATENCAO:
            raise CommandError("Lançamento terminou com erros ou linhas a verificar.")
        r = registro.resumo
        self.stdout.write(
            f"Lançadas: {r['lancadas']} · simuladas: {r['simuladas']} · falhas: {r['falhas']} · "
            f"verificar: {r['verificar']} · ignoradas: {r['ignoradas']}"
        )
