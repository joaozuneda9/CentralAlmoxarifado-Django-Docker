"""Lançamento das saídas no SCPI sobre o banco: trava, um lote por requisição e o resultado.

Vem do laço principal do `lancar_saidas.py` do extrair-relatorio, agora sobre as
`LinhaSaida`. A garantia é nunca lançar um lote duas vezes, e ela vem da ordem das gravações:
- `EM_LANCAMENTO` é confirmado no banco (transação fechada) antes do clique em Salvar, e só
  se todas as linhas do lote ainda estão `PENDENTE`;
- qualquer falha depois do clique vira `VERIFICAR`, nunca `PENDENTE` nem `ERRO`;
- o número da requisição vai para o journal antes de ir para o banco. Se o banco não aceitar
  o resultado, a execução para (`FalhaCritica`) e o lote fica travado para conferência.

A navegação no SCPI fica atrás do protocolo `SCPI` (Playwright na Tarefa 4, simulado nos
testes).
"""

import json
import logging
from collections.abc import Callable, Collection
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.db import Error, transaction
from django.db.models import TextField, Value
from django.db.models.functions import Concat
from django.utils import timezone

from pedidos.models import TRAVA_LANCAMENTO, ExecucaoRobo, LinhaSaida
from pedidos.regras import EM_LANCAMENTO, ERRO, LANCADA, PENDENTE, VERIFICAR, texto
from pedidos.servicos import centros
from scpi.execucao import trava
from scpi.leitura import ErroImportacao
from scpi.requisicoes import ESTADOS_TRAVA, FalhaCritica, Requisicao, selecionar

logger = logging.getLogger("scpi.lancamento")

# Último recurso se o banco cair entre o Salvar e a gravação do número: uma linha JSON por
# acontecimento, em `settings.LOG_DIR`.
JOURNAL = "lancar_saidas_journal.jsonl"

LANCAMENTO_BLOQUEADO = (
    "O lançamento real no SCPI está bloqueado neste ambiente (LANCAMENTO_REAL=0 no .env): "
    "só a simulação roda."
)


class SCPI(Protocol):
    def preencher(self, req: Requisicao) -> None:
        """Preenche o formulário da requisição. Levanta `ErroSCPI` (nada foi lançado)."""

    def salvar(self) -> str:
        """Clica em Salvar e devolve o nº da requisição. Levanta `ResultadoIncerto`."""

    def depois_de_salvar(self) -> None:
        """Volta ao formulário vazio depois de uma requisição salva."""

    def encerrar_simulacao(self) -> None:
        """Pausa para a conferência visual e descarta o formulário, sem salvar."""

    def descartar(self, lote: str) -> None:
        """Depois de `ErroSCPI`: print da tela e volta ao estado limpo."""

    def reiniciar(self) -> None:
        """Recarrega o SCPI depois de uma falha no Salvar ou depois dele."""


AbrirSCPI = Callable[[], AbstractContextManager[SCPI]]


@dataclass
class Resumo:
    """Contagens da execução, todas em lotes (um lote = uma requisição)."""

    requisicoes: int = 0
    processadas: int = 0
    lancadas: int = 0
    simuladas: int = 0
    falhas: int = 0
    verificar: int = 0
    ignoradas: int = 0


class LancamentoEmAndamento(Exception):
    """Outro lançamento está rodando (trava ocupada)."""


class RegistroNaExecucao(logging.Handler):
    """Acrescenta cada mensagem do logger ao `log` da execução, já no banco (a página mostra
    o andamento enquanto o robô roda)."""

    def __init__(self, execucao: ExecucaoRobo):
        super().__init__(level=logging.INFO)
        self.execucao_id = execucao.pk

    def emit(self, record: logging.LogRecord) -> None:
        try:
            linha = f"{timezone.localtime():%H:%M:%S} {record.getMessage()}\n"
            ExecucaoRobo.objects.filter(pk=self.execucao_id).update(
                log=Concat("log", Value(linha), output_field=TextField())
            )
        except Exception:
            self.handleError(record)


def _journal(evento: str, req: Requisicao, execucao_id: int | None, **extra) -> None:
    """Acrescenta um acontecimento ao journal. Falha ao gravá-lo só vai para o log: o journal
    nunca impede que o resultado chegue ao banco."""
    registro = {
        "ts": timezone.localtime().isoformat(),
        "evento": evento,
        "execucao": execucao_id,
        "lote": req.lote,
        "linhas": req.ids,
        **extra,
    }
    try:
        with open(Path(settings.LOG_DIR) / JOURNAL, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
    except OSError:
        logger.exception("Não foi possível gravar %s no journal (%s).", evento, req.lote)


def _gravar(req: Requisicao, status: str, *, execucao_id: int, critico: bool, **campos) -> None:
    """Grava o resultado em todas as linhas do lote, com valores absolutos pelo `id`.

    Se o banco recusar, o que se queria gravar vai para o journal. Com `critico` (resultado de
    um Salvar), a execução para: continuar arriscaria lançar sem registrar."""
    try:
        LinhaSaida.objects.filter(pk__in=req.ids).update(status=status, **campos)
    except Exception as exc:
        _journal(
            "falha_banco", req, execucao_id, valores={"status": status, **campos}, erro=repr(exc)
        )
        if critico:
            raise FalhaCritica(
                f"não foi possível gravar {status} para {req}: {exc}. Registro salvo em "
                f"{JOURNAL} — confira no SCPI e resolva o lote à mão."
            ) from exc
        logger.error("✘ %s — não foi possível gravar %s: %s", req.lote, status, exc)


def _travar(req: Requisicao, execucao: ExecucaoRobo) -> bool:
    """Grava `EM_LANCAMENTO` se todas as linhas do lote ainda estão `PENDENTE` e sem número de
    requisição (travadas com `select_for_update`). A transação fecha aqui, antes do clique em
    Salvar."""
    agora = timezone.localtime()
    try:
        with transaction.atomic():
            atuais = list(
                LinhaSaida.objects.select_for_update()
                .filter(pk__in=req.ids)
                .values_list("status", "requisicao_scpi")
            )
            if len(atuais) != len(req.ids) or any(
                status != PENDENTE or texto(numero) for status, numero in atuais
            ):
                return False
            LinhaSaida.objects.filter(pk__in=req.ids).update(
                status=EM_LANCAMENTO,
                mensagem=f"Em lançamento desde {agora:%d/%m/%Y %H:%M} (execução #{execucao.pk}).",
            )
    except Error as exc:  # inclui InterfaceError (conexão já fechada)
        raise FalhaCritica(f"não foi possível travar o lote {req.lote}: {exc}.") from exc
    return True


def _salvar_resumo(execucao: ExecucaoRobo, resumo: Resumo) -> None:
    ExecucaoRobo.objects.filter(pk=execucao.pk).update(resumo=asdict(resumo))


def _lancar_um(req: Requisicao, scpi: SCPI, execucao: ExecucaoRobo, resumo: Resumo) -> None:
    simulacao = execucao.simulacao
    try:
        scpi.preencher(req)
    except Exception as exc:  # ErroSCPI ou outra: nada foi salvo, seguro tentar de novo
        resumo.falhas += 1
        mensagem = str(exc) or type(exc).__name__
        logger.error("✘ %s — %s", req.lote, mensagem)
        if not simulacao:
            _gravar(req, ERRO, execucao_id=execucao.pk, mensagem=mensagem[:500], critico=False)
        scpi.descartar(req.lote)
        return

    if simulacao:
        scpi.encerrar_simulacao()
        resumo.simuladas += 1
        logger.info("◇ simulação: %s preenchido e descartado, sem salvar", req.lote)
        return

    if not _travar(req, execucao):
        logger.warning("⚠ %s — lote mudou durante a execução; não lançado", req.lote)
        resumo.ignoradas += 1
        scpi.descartar(req.lote)
        return

    _journal("em_lancamento", req, execucao.pk)
    try:
        numero = scpi.salvar()
    except Exception as exc:  # qualquer falha depois do clique: a requisição pode existir
        resumo.verificar += 1
        logger.error("⚠ %s — resultado incerto, conferir no SCPI: %s", req.lote, exc)
        _journal("incerto", req, execucao.pk, erro=repr(exc))
        _gravar(
            req,
            VERIFICAR,
            execucao_id=execucao.pk,
            mensagem=f"Resultado incerto: {exc}"[:500],
            critico=True,
        )
        scpi.reiniciar()
        return

    _journal("lancada", req, execucao.pk, requisicao=numero)
    _gravar(
        req,
        LANCADA,
        execucao_id=execucao.pk,
        requisicao_scpi=numero,
        lancado_em=timezone.now(),
        mensagem="",
        critico=True,
    )
    resumo.lancadas += 1
    logger.info("✔ lançada no SCPI: requisição %s", numero)
    try:
        scpi.depois_de_salvar()
    except Exception as exc:
        logger.warning("Aviso: o SCPI não voltou ao formulário (%s); reiniciando.", exc)
        scpi.reiniciar()


def lancar(execucao: ExecucaoRobo, abrir_scpi: AbrirSCPI, *, lotes: Collection[str]) -> Resumo:
    """Lança no SCPI os `lotes` escolhidos (só os `PENDENTE` válidos), um por requisição, e
    devolve o resumo.

    Lotes com linha esperando conferência ficam de fora; os inválidos viram `ERRO` sem abrir
    o navegador. Na simulação, nenhuma linha muda e o Salvar nunca é chamado."""
    simulacao = execucao.simulacao
    resumo = Resumo()
    linhas = LinhaSaida.objects.filter(status__in=(PENDENTE, *ESTADOS_TRAVA)).order_by("id")
    sel = selecionar(list(linhas), centros())
    escolhidos = set(lotes)

    for lote in sel.travados:
        if lote in escolhidos:
            logger.warning("⚠ lote %s travado — conferir no SCPI", lote)
            resumo.ignoradas += 1
    for req in sel.requisicoes:
        if req.erro and req.lote in escolhidos:
            logger.error("✘ %s — validação: %s", req, req.erro)
            resumo.falhas += 1
            if not simulacao:
                _gravar(req, ERRO, execucao_id=execucao.pk, mensagem=req.erro[:500], critico=False)

    validas = [req for req in sel.requisicoes if not req.erro]
    for lote in sorted(escolhidos - {req.lote for req in sel.requisicoes} - set(sel.travados)):
        logger.warning("⚠ %s não está mais na fila do robô — não será lançada", lote)
    resumo.ignoradas += sum(1 for req in validas if req.lote not in escolhidos)
    validas = [req for req in validas if req.lote in escolhidos]
    resumo.requisicoes = len(validas)
    _salvar_resumo(execucao, resumo)
    if not validas:
        logger.info("Nada a lançar.")
        return resumo

    with abrir_scpi() as scpi:
        for i, req in enumerate(validas, start=1):
            logger.info("→ (%d/%d) %s", i, len(validas), req)
            _lancar_um(req, scpi, execucao, resumo)
            resumo.processadas += 1
            _salvar_resumo(execucao, resumo)
    return resumo


def _encerrar(execucao: ExecucaoRobo, situacao: str, **campos) -> None:
    """Grava o fim da execução sem sobrescrever o `log` e o `resumo` parcial, que foram
    gravados direto no banco durante o laço."""
    execucao.refresh_from_db(fields=["log", "resumo"])
    execucao.situacao = situacao
    execucao.fim = timezone.now()
    for nome, valor in campos.items():
        setattr(execucao, nome, valor)
    execucao.save(update_fields=["situacao", "fim", "resumo", "erro"])


def _encerrar_com_falha(execucao: ExecucaoRobo, erro: str) -> None:
    """Registra a falha sem esconder a exceção original, mesmo se o banco estiver fora."""
    try:
        _encerrar(execucao, ExecucaoRobo.Situacao.FALHA, erro=erro)
    except Exception:
        logger.exception("Não foi possível registrar a falha da execução #%s.", execucao.pk)


def executar_lancamento(
    execucao: ExecucaoRobo, abrir_scpi: AbrirSCPI, *, lotes: Collection[str]
) -> ExecucaoRobo:
    """Roda `lancar` sob a trava única do lançamento e registra o resultado na execução."""
    with trava(TRAVA_LANCAMENTO) as obtida:
        if not obtida:
            _encerrar(
                execucao,
                ExecucaoRobo.Situacao.FALHA,
                erro="Outro lançamento já está em andamento.",
            )
            raise LancamentoEmAndamento(execucao.erro)

        registro = RegistroNaExecucao(execucao)
        logger.addHandler(registro)
        try:
            resumo = lancar(execucao, abrir_scpi, lotes=lotes)
        except (FalhaCritica, ErroImportacao) as exc:
            logger.error("✘ Execução interrompida: %s", exc)
            _encerrar_com_falha(execucao, str(exc))
            raise
        except Exception as exc:
            logger.exception("✘ Falha inesperada no lançamento")
            _encerrar_com_falha(execucao, f"Falha inesperada: {exc}")
            raise
        finally:
            logger.removeHandler(registro)

        pendencias = resumo.falhas or resumo.verificar
        _encerrar(
            execucao,
            ExecucaoRobo.Situacao.ATENCAO if pendencias else ExecucaoRobo.Situacao.SUCESSO,
            resumo=asdict(resumo),
        )
        return execucao
