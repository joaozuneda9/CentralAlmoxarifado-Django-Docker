import re
from contextlib import contextmanager

from django.core.management import BaseCommand, CommandError

from pedidos.models import ExecucaoRobo
from scpi.lancador import navegador
from scpi.lancamento import LancamentoEmAndamento, executar_lancamento
from scpi.requisicoes import FalhaCritica

RE_QTD_DO_SERVIDOR = re.compile(r"servidor devolveu QTD \S+ no item (\d+)")


@contextmanager
def sessao_ja_aberta(sessao):
    """O `abrir_scpi` do lançamento sem abrir nem fechar nada: cada repetição começa do zero no
    formulário, mas na mesma sessão do SCPI (a `limpar` do fim de cada simulação o devolve à
    tela de saída)."""
    yield sessao


def medir(registro: ExecucaoRobo) -> dict:
    """O que a repetição registrou no log: itens que o servidor devolveu com QTD diferente do
    pedido, rodadas de correção da conferência final e se ela terminou igual ao pedido."""
    log = registro.log
    return {
        "resetados": sorted({int(n) for n in RE_QTD_DO_SERVIDOR.findall(log)}),
        "correcoes": log.count("corrigindo ("),
        "final_ok": "grid iguais ao pedido" in log,
        "falhas": (registro.resumo or {}).get("falhas", 0),
        "segundos": round((registro.fim - registro.inicio).total_seconds()) if registro.fim else 0,
    }


class Command(BaseCommand):
    help = (
        "Só para testes do robô: simula a mesma requisição várias vezes seguidas, abrindo o SCPI "
        "uma vez só. Nunca salva nada no SCPI nem altera nenhuma linha."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--lote",
            required=True,
            metavar="NÚMERO",
            help="Requisição (P-0123, AV-0004) a simular em todas as repetições.",
        )
        parser.add_argument("--vezes", type=int, default=10, help="Quantas repetições (padrão 10).")
        parser.add_argument(
            "--manter-registros",
            action="store_true",
            help="Mantém as execuções no histórico de Automações (por padrão são apagadas).",
        )

    def handle(self, *args, lote, vezes, manter_registros, **opcoes):
        if vezes < 1:
            raise CommandError("--vezes precisa ser um inteiro maior que zero.")
        registros: list[ExecucaoRobo] = []
        medidas: list[dict] = []
        try:
            with navegador() as sessao:
                for n in range(1, vezes + 1):
                    registro = ExecucaoRobo.objects.create(iniciada_por=None, simulacao=True)
                    registros.append(registro)
                    try:
                        registro = executar_lancamento(
                            registro, lambda: sessao_ja_aberta(sessao), lotes=[lote]
                        )
                    except LancamentoEmAndamento as exc:
                        raise CommandError("Outro lançamento já está em andamento.") from exc
                    except FalhaCritica as exc:
                        raise CommandError(str(exc), returncode=2) from exc
                    medida = medir(registro)
                    medidas.append(medida)
                    self.stdout.write(self._linha(n, vezes, medida))
        finally:
            if not manter_registros:
                ExecucaoRobo.objects.filter(pk__in=[r.pk for r in registros]).delete()
        self.stdout.write(self._resumo(medidas))

    @staticmethod
    def _linha(n: int, vezes: int, m: dict) -> str:
        resets = f"itens {m['resetados']}" if m["resetados"] else "nenhum"
        return (
            f"repetição {n}/{vezes}: reset da QTD no servidor: {resets} · "
            f"rodadas de correção: {m['correcoes']} · "
            f"conferência final {'ok' if m['final_ok'] else 'NÃO fechou'} · {m['segundos']} s"
        )

    @staticmethod
    def _resumo(medidas: list[dict]) -> str:
        total = len(medidas)
        com_reset = sum(1 for m in medidas if m["resetados"])
        sem_fechar = sum(1 for m in medidas if not m["final_ok"])
        itens = sum(len(m["resetados"]) for m in medidas)
        return (
            f"{total} repetição(ões): {com_reset} com reset da QTD ({itens} itens no total), "
            f"{sem_fechar} sem fechar a conferência final."
        )
