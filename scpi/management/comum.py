"""Parte comum dos comandos de importação."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from django.core.management import BaseCommand, CommandError

from catalogo.models import Importacao
from scpi import execucao

logger = logging.getLogger("scpi")

NOMES = {
    Importacao.Tipo.CADASTRO: "cadastro",
    Importacao.Tipo.ESTOQUE: "estoque",
    Importacao.Tipo.SAIDAS: "saídas do SCPI",
    Importacao.Tipo.REQUISICOES: "requisições do SCPI",
}


def data_opcao(texto: str | None) -> date | None:
    """Data da linha de comando (dd/mm/aaaa); vazio é None."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        raise CommandError(f"Use a data no formato dd/mm/aaaa: {texto}") from None


def obter_csv(arquivo: str | None, baixar: Callable[[], bytes]) -> Callable[[], bytes]:
    """Lê o CSV de `arquivo` (já baixado do SCPI) ou, sem ele, baixa pelo navegador."""
    if arquivo:
        return lambda: Path(arquivo).read_bytes()
    return baixar


@contextmanager
def descartar_arquivo(arquivo: str | None, apagar: bool) -> Iterator[None]:
    """Com `apagar`, remove `arquivo` ao fim, mesmo se a importação falhar ou for recusada pela
    trava: é o CSV que a tela enviou e que só existe para esta execução."""
    try:
        yield
    finally:
        if apagar and arquivo:
            Path(arquivo).unlink(missing_ok=True)


def rodar_importacao(
    comando: BaseCommand,
    tipo: str,
    obter_csv: Callable[[], bytes],
    gravar: Callable[[bytes], execucao.Resultado],
    resumo: Callable[[Importacao], str],
    periodo: tuple[date | None, date | None] = (None, None),
) -> Importacao:
    """Executa a importação e relata no terminal; falha vira `CommandError` (código 1)."""
    try:
        importacao = execucao.executar(tipo, obter_csv, gravar, periodo)
    except execucao.ImportacaoEmAndamento:
        # Não vira registro em Importacao (a outra execução é que está registrada): fica no log.
        mensagem = f"Importação de {NOMES[tipo]} já em andamento."
        logger.warning(mensagem)
        raise CommandError(mensagem) from None
    if importacao.situacao == Importacao.Situacao.FALHA:
        raise CommandError(importacao.erro)
    comando.stdout.write(resumo(importacao))
    for aviso in importacao.avisos:
        comando.stdout.write(f"  Aviso: {aviso}")
    return importacao
