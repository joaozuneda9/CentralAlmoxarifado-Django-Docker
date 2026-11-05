"""O que a execução real do robô faz pela conciliação (spec 010, PR 2): as extrações antes e depois
do lançamento e o registro de cada tentativa.

Nada aqui muda a ordem das gravações que impede lançar duas vezes (Princípio III): a extração de
antes só acrescenta uma condição para começar, e a tentativa é gravada na mesma transação que
confirma o `EM_LANCAMENTO`, antes do Salvar.
"""

import logging
import time
from collections.abc import Callable, Iterable
from datetime import date

from django.utils import timezone

from catalogo.models import Importacao
from conciliacao import regras
from conciliacao.extracao import extrair
from conciliacao.models import ConferenciaLote, ExtracaoOficial, TentativaLancamento
from conciliacao.servicos import conciliar
from pedidos.models import LinhaSaida
from pedidos.regras import EM_LANCAMENTO, VERIFICAR
from scpi.execucao import ImportacaoEmAndamento
from scpi.leitura import ErroImportacao
from scpi.requisicoes import Requisicao

logger = logging.getLogger("scpi.lancamento")

# A extração de antes tenta algumas vezes: as falhas do SCPI dentro da janela das 7h às 17h vêm
# em surtos de minutos (spec 010, research R7).
TENTATIVAS_EXTRACAO = 3
PAUSA_EXTRACAO_S = 30

Extrair = Callable[[date, date], bytes]


class ExtracaoAntesFalhou(ErroImportacao):
    """A extração de antes não deu certo em nenhuma tentativa: a execução não lança nada."""


def _dormir(segundos: float) -> None:
    time.sleep(segundos)


def periodo_da_execucao(requisicoes: Iterable[Requisicao], hoje: date) -> tuple[date, date]:
    """Do dia anterior à data mais antiga envolvida (os lotes da execução e os lotes em
    verificar ainda abertos) até o dia seguinte a hoje (FR-002)."""
    datas = [linha.data for req in requisicoes for linha in req.linhas]
    datas += LinhaSaida.objects.filter(status__in=(VERIFICAR, EM_LANCAMENTO)).values_list(
        "data", flat=True
    )
    return regras.periodo(datas, hoje)


def _uma_extracao(motivo, periodo, baixar: Extrair, execucao) -> ExtracaoOficial | None:
    """Uma tentativa: a extração registrada, ou None quando outra extração segurava a trava."""
    de, ate = periodo
    try:
        return extrair(motivo, periodo, lambda: baixar(de, ate), execucao=execucao)
    except ImportacaoEmAndamento:
        logger.warning("⚠ outra extração de requisições do SCPI está em andamento")
        return None


def extrair_antes(execucao, periodo: tuple[date, date], baixar: Extrair) -> ExtracaoOficial:
    """A extração de antes, com até `TENTATIVAS_EXTRACAO` tentativas. Sem nenhuma bem-sucedida,
    levanta `ExtracaoAntesFalhou` antes de qualquer lote mudar (FR-009)."""
    ultimo_erro = "outra extração estava em andamento"
    for tentativa in range(1, TENTATIVAS_EXTRACAO + 1):
        if tentativa > 1:
            _dormir(PAUSA_EXTRACAO_S)
        logger.info(
            "→ extraindo as requisições do SCPI antes de lançar (%d/%d), %s a %s",
            tentativa,
            TENTATIVAS_EXTRACAO,
            f"{periodo[0]:%d/%m/%Y}",
            f"{periodo[1]:%d/%m/%Y}",
        )
        extracao = _uma_extracao(ExtracaoOficial.Motivo.ANTES, periodo, baixar, execucao)
        if extracao is not None and extracao.bem_sucedida:
            logger.info(
                "✔ %d requisições no SCPI; a maior é %s (o piso desta execução)",
                extracao.requisicoes,
                extracao.maior_requisicao or "nenhuma",
            )
            return extracao
        if extracao is not None:
            ultimo_erro = extracao.importacao.erro
            logger.warning("⚠ extração de antes falhou: %s", ultimo_erro)
    raise ExtracaoAntesFalhou(
        "Não foi possível extrair as requisições do SCPI antes de lançar "
        f"({TENTATIVAS_EXTRACAO} tentativas; a última: {ultimo_erro}). Nenhum lote foi lançado."
    )


def extrair_depois(execucao, periodo: tuple[date, date], baixar: Extrair) -> None:
    """A extração de depois, uma tentativa. Qualquer falha, inclusive do banco ao registrá-la,
    só vai para o log: os lotes já lançados ficam aguardando conferência, e a situação da
    execução não piora (FR-012)."""
    logger.info("→ extraindo as requisições do SCPI depois do lançamento")
    try:
        extracao = _uma_extracao(ExtracaoOficial.Motivo.DEPOIS, periodo, baixar, execucao)
    except Exception:
        logger.exception(
            "⚠ extração de depois não pôde ser registrada; os lotes ficam aguardando conferência"
        )
        return
    if extracao is None:
        return
    if extracao.importacao.situacao == Importacao.Situacao.SUCESSO:
        logger.info("✔ %d requisições no SCPI depois do lançamento", extracao.requisicoes)
        try:
            contagem = conciliar(extracao)
        except Exception:
            logger.exception("⚠ não foi possível conciliar os lotes desta execução")
        else:
            if contagem:
                logger.info("✔ conciliação: %s", resumo_da_contagem(contagem))
    else:
        logger.warning(
            "⚠ extração de depois falhou (%s); os lotes ficam aguardando conferência",
            extracao.importacao.erro,
        )


def resumo_da_contagem(contagem: dict[str, int]) -> str:
    """'COMPROVADO': 2, 'DIVERGENTE': 1 → "2 comprovados, 1 divergente"."""
    rotulos = dict(ConferenciaLote.Veredito.choices)
    return ", ".join(
        f"{n} {rotulos.get(v, 'em verificar conferidos').lower()}" for v, n in contagem.items()
    )


def foto(req: Requisicao) -> dict:
    """O que o robô vai digitar no SCPI: a entrega confirmada como ele a leu (research R11)."""
    return {
        "data": req.data,
        "tipo_saida": req.tipo_saida,
        "cod_ccusto": req.cod_ccusto,
        "recebedor": req.recebedor,
        "observacoes": regras.texto_observacoes(req.lote, req.obs),
        "placa_centro": req.placa_centro,
        "itens": [
            {"codigo": item.cadpro, "qtd": item.qtd, "placa": item.placa} for item in req.itens
        ],
    }


def registrar_tentativa(execucao, ordem: int, req: Requisicao, resultado: str, **campos) -> None:
    """Cria a tentativa. Chamada dentro da transação do `_travar` (resultado VERIFICAR, o lado
    seguro se o processo morrer) ou, sem ela, para o lote que falhou antes do Salvar."""
    TentativaLancamento.objects.create(
        execucao=execucao,
        ordem=ordem,
        lote=req.lote,
        momento=timezone.now(),
        resultado=resultado,
        foto=foto(req),
        **campos,
    )


def tentativa_lancada(execucao, lote: str, numero: str) -> None:
    """Marca a tentativa como lançada com o número obtido. Falha aqui só vai para o log: o lote
    já está gravado e o journal tem o número; sem o número, o intervalo de um verificar
    seguinte fica mais largo, o que só bloqueia mais (lado seguro)."""
    try:
        TentativaLancamento.objects.filter(execucao=execucao, lote=lote).update(
            resultado=TentativaLancamento.Resultado.LANCADA, requisicao=numero
        )
    except Exception:
        logger.exception("Não foi possível registrar o número %s na tentativa de %s.", numero, lote)
