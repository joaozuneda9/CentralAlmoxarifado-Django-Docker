"""Início das importações e do lançamento no SCPI em segundo plano, pelos botões da página."""

import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from catalogo.models import Importacao
from pedidos.models import ExecucaoRobo


def iniciar_atualizacao(carga_inicial: bool = False) -> bool:
    """Inicia `manage.py atualizar_catalogo` (com `--carga-inicial`, a carga inicial completa)
    num processo separado.

    Devolve False, sem iniciar nada, se já houver importação em andamento. Dois cliques quase
    juntos ainda podem iniciar dois processos; nesse caso a trava por tipo
    (`scpi.execucao.trava`) faz o segundo recusar cada importação sem tocar nos dados.
    """
    if Importacao.em_andamento().exists():
        return False
    if carga_inicial:
        argumentos, titulo = ["atualizar_catalogo", "--carga-inicial"], "Carga inicial completa"
    else:
        argumentos, titulo = ["atualizar_catalogo"], "Atualizar agora"
    _iniciar_comando(argumentos, "atualizar_catalogo.log", titulo)
    return True


COMANDOS_IMPORTACAO = {
    "cadastro": "importar_cadastro",
    "estoque": "importar_estoque",
    "saidas": "importar_saidas_scpi",
}


def guardar_csv_enviado(arquivo) -> Path:
    """Grava o CSV enviado pela tela numa pasta própria e devolve o caminho. O comando o apaga ao
    terminar (`--apagar-arquivo`); quem chama apaga se o processo não chegar a subir."""
    pasta = Path(settings.LOG_DIR) / "uploads"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{uuid.uuid4().hex}.csv"
    with open(caminho, "wb") as destino:
        for pedaco in arquivo.chunks():
            destino.write(pedaco)
    return caminho


def iniciar_importacao(
    tipo: str,
    *,
    forcar: bool = False,
    completo: bool = False,
    desde: date | None = None,
    ate: date | None = None,
    arquivo: Path | None = None,
) -> bool:
    """Inicia `manage.py importar_<tipo>` num processo separado, com os parâmetros escolhidos.

    `tipo` é "cadastro", "estoque" ou "saidas". `completo` e `forcar` valem só para o cadastro
    (e não com período); `desde` e `ate` valem para o cadastro (importação parcial) e para as
    saídas. Com
    `arquivo` (CSV já baixado), o navegador não é aberto e o arquivo é apagado ao fim. Devolve
    False, sem iniciar nada, se já houver importação em andamento.
    """
    if Importacao.em_andamento().exists():
        return False
    argumentos = [COMANDOS_IMPORTACAO[tipo]]
    if tipo == "cadastro":
        if completo:
            argumentos.append("--completo")
        if forcar:
            argumentos.append("--forcar")
    if tipo in ("cadastro", "saidas"):
        if desde:
            argumentos += ["--desde", f"{desde:%d/%m/%Y}"]
        if ate:
            argumentos += ["--ate", f"{ate:%d/%m/%Y}"]
    if arquivo:
        argumentos += ["--arquivo", str(arquivo), "--apagar-arquivo"]
    _iniciar_comando(argumentos, f"importar_{tipo}.log", f"Importar {tipo}")
    return True


def iniciar_lancamento(usuario, *, simulacao: bool, lotes: list[str]) -> ExecucaoRobo | None:
    """Cria a `ExecucaoRobo` e inicia `manage.py lancar_saidas` num processo separado.

    O robô processa só as requisições de `lotes` (`--lote` de cada uma).

    Devolve None, sem criar nada, se já houver lançamento em andamento. Dois cliques quase
    juntos ainda podem criar duas execuções; a trava do lançamento (`GET_LOCK`) faz a segunda
    terminar como falha sem tocar em nenhuma linha.
    """
    if ExecucaoRobo.em_andamento().exists():
        return None
    execucao = ExecucaoRobo.objects.create(iniciada_por=usuario, simulacao=simulacao)
    argumentos = ["lancar_saidas", "--execucao", str(execucao.pk)]
    if simulacao:
        argumentos.append("--dry-run")
    for lote in lotes:
        argumentos += ["--lote", lote]
    try:
        _iniciar_comando(
            argumentos, "lancar_saidas.log", "Simular no SCPI" if simulacao else "Lançar no SCPI"
        )
    except Exception as exc:
        # O processo não subiu: a execução não pode ficar "em andamento" à toa.
        ExecucaoRobo.objects.filter(pk=execucao.pk).update(
            situacao=ExecucaoRobo.Situacao.FALHA, erro=str(exc), fim=timezone.now()
        )
        raise
    return execucao


def _iniciar_comando(argumentos: list[str], arquivo_log: str, titulo: str) -> None:
    """Inicia `manage.py <argumentos>` num processo separado, com a saída em `LOG_DIR`."""
    # No Windows, o processo precisa de grupo próprio e sem console para sobreviver ao fim da
    # requisição (e ao reinício do waitress). No Linux (o container), uma sessão própria faz o
    # mesmo papel: o robô não recebe os sinais do grupo do waitress.
    flags = 0
    windows = sys.platform == "win32"
    if windows:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    # Tudo o que o processo escreve (resumos, recusa pela trava, falhas, erro ao subir o
    # Django) vai para este arquivo, que o processo herda; o pai fecha a sua cópia.
    with open(Path(settings.LOG_DIR) / arquivo_log, "a", encoding="utf-8") as saida:
        saida.write(f"\n=== {timezone.localtime():%d/%m/%Y %H:%M:%S} {titulo} ===\n")
        saida.flush()
        subprocess.Popen(
            [sys.executable, str(settings.BASE_DIR / "manage.py"), *argumentos],
            cwd=settings.BASE_DIR,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            stdin=subprocess.DEVNULL,
            stdout=saida,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=flags,
            start_new_session=not windows,
        )
