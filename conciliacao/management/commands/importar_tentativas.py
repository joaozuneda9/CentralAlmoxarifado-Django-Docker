import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from django.core.management import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from conciliacao.models import TentativaLancamento
from pedidos.models import ExecucaoRobo


def _momento(texto: str) -> datetime:
    momento = datetime.fromisoformat(texto)
    if timezone.is_naive(momento):
        momento = timezone.make_aware(momento)
    return momento


def ler_journal(caminho: Path) -> dict[int, list[dict]]:
    """As tentativas de cada execução, na ordem do journal: o `em_lancamento` dá a ordem e o
    momento; `lancada` dá o número; sem ele (`incerto`, ou nada depois), fica em verificar."""
    por_execucao: dict[int, dict[str, dict]] = defaultdict(dict)
    with open(caminho, encoding="utf-8") as arquivo:
        for numero, linha in enumerate(arquivo, start=1):
            if not linha.strip():
                continue
            try:
                evento = json.loads(linha)
            except json.JSONDecodeError:
                raise CommandError(f"Linha {numero} do journal não é JSON.") from None
            execucao, lote = evento.get("execucao"), evento.get("lote")
            if execucao is None or not lote:
                continue
            tentativas = por_execucao[int(execucao)]
            if evento.get("evento") == "em_lancamento" and lote not in tentativas:
                tentativas[lote] = {
                    "lote": lote,
                    "momento": _momento(evento["ts"]),
                    "resultado": TentativaLancamento.Resultado.VERIFICAR,
                    "requisicao": "",
                }
            elif evento.get("evento") == "lancada" and lote in tentativas:
                tentativas[lote]["resultado"] = TentativaLancamento.Resultado.LANCADA
                tentativas[lote]["requisicao"] = evento.get("requisicao") or ""
    return {
        execucao: sorted(tentativas.values(), key=lambda t: t["momento"])
        for execucao, tentativas in por_execucao.items()
    }


class Command(BaseCommand):
    help = (
        "Cria as tentativas de lançamento das execuções antigas a partir do journal do robô "
        "(lancar_saidas_journal.jsonl), para os lotes em verificar de antes da conciliação "
        "(spec 010, research R15). Idempotente: execução que já tem tentativas fica como está."
    )

    def add_arguments(self, parser):
        parser.add_argument("--journal", required=True, help="Caminho do journal (.jsonl).")
        parser.add_argument("--dry-run", action="store_true", help="Só conta, sem gravar.")

    def handle(self, *args, journal, dry_run=False, **opcoes):
        caminho = Path(journal)
        if not caminho.is_file():
            raise CommandError(f"Journal não encontrado: {caminho}")
        lidas = ler_journal(caminho)
        existentes = set(ExecucaoRobo.objects.filter(pk__in=lidas).values_list("pk", flat=True))
        ja_registradas = set(
            TentativaLancamento.objects.filter(execucao_id__in=existentes)
            .values_list("execucao_id", flat=True)
            .distinct()
        )
        criar = []
        for execucao, tentativas in sorted(lidas.items()):
            if execucao not in existentes or execucao in ja_registradas:
                continue
            criar += [
                TentativaLancamento(
                    execucao_id=execucao,
                    ordem=ordem,
                    lote=t["lote"],
                    momento=t["momento"],
                    resultado=t["resultado"],
                    requisicao=t["requisicao"],
                    historica=True,
                )
                for ordem, t in enumerate(tentativas, start=1)
            ]
        if not dry_run:
            with transaction.atomic():
                TentativaLancamento.objects.bulk_create(criar)
        verbo = "a criar" if dry_run else "criadas"
        sem_registro = len(set(lidas) - existentes)
        self.stdout.write(
            f"Execuções no journal: {len(lidas)}; tentativas {verbo}: {len(criar)}; "
            f"já registradas: {len(ja_registradas)}; sem a execução no banco: {sem_registro}."
        )
