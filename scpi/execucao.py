"""Execução de uma importação: trava por tipo, download, gravação numa transação e registro.

O download (Playwright) roda fora da transação; a gravação roda dentro dela, então uma falha
deixa os dados anteriores intactos. Toda execução que obtém a trava vira uma `Importacao`.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date

from django.db import Error, connection, transaction
from django.utils import timezone

from catalogo.models import Importacao, trava_importacao
from scpi.leitura import ErroImportacao

logger = logging.getLogger("scpi")

# Começo do erro gravado quando a falha não foi prevista (Playwright, rede): o texto que vem
# depois é técnico, e a tela o resume (`saude.resumo_do_erro`, `andamento.explicar_falha`).
PREFIXO_FALHA_INESPERADA = "Falha inesperada:"


@dataclass
class Resultado:
    linhas: int
    avisos: list[str] = field(default_factory=list)


class ImportacaoEmAndamento(Exception):
    """Outra importação do mesmo tipo está rodando (trava ocupada)."""


@contextmanager
def trava(nome: str) -> Iterator[bool]:
    """Trava nomeada do MySQL/MariaDB (`GET_LOCK`), sem espera. Entrega se foi obtida.

    Vale entre processos e é liberada sozinha se o processo morrer (a conexão cai).
    Falha de banco ao liberar só vai para o log: a trava cai com a conexão, e a exceção de
    dentro do bloco (a que importa) não fica escondida atrás dela.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, 0)", [nome])
        obtida = cursor.fetchone()[0] == 1
    try:
        yield obtida
    finally:
        if obtida:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", [nome])
            except Error:  # inclui InterfaceError (conexão já fechada)
                logger.warning("Não foi possível liberar a trava %s.", nome, exc_info=True)


def executar(
    tipo: str,
    obter_csv: Callable[[], bytes],
    gravar: Callable[[bytes], Resultado],
    periodo: tuple[date | None, date | None] = (None, None),
) -> Importacao:
    with trava(trava_importacao(tipo)) as obtida:
        if not obtida:
            raise ImportacaoEmAndamento(tipo)
        importacao = Importacao.objects.create(
            tipo=tipo, periodo_de=periodo[0], periodo_ate=periodo[1]
        )
        try:
            conteudo = obter_csv()
            with transaction.atomic():
                resultado = gravar(conteudo)
        except ErroImportacao as exc:
            importacao.situacao = Importacao.Situacao.FALHA
            importacao.erro = str(exc)
            logger.warning("Importação %s falhou: %s", tipo, exc)
        except Exception as exc:
            importacao.situacao = Importacao.Situacao.FALHA
            importacao.erro = f"{PREFIXO_FALHA_INESPERADA} {exc}"
            logger.exception("Importação %s falhou", tipo)
        else:
            importacao.situacao = Importacao.Situacao.SUCESSO
            importacao.linhas = resultado.linhas
            importacao.avisos = resultado.avisos
        importacao.fim = timezone.now()
        importacao.save()
        return importacao
