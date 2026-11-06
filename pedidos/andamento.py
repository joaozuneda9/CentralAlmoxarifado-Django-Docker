"""Uma `ExecucaoRobo` em texto de tela: frase, contadores, duração, "N de M" e a falha explicada.

Funções puras: recebem a execução (ou só os campos que usam) e o momento atual, nunca consultam
o banco. O `resumo` pode estar vazio (`{}`) quando a execução falhou antes de começar, por isso
toda leitura dele passa por `_num`.
"""

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from catalogo.saude import PREFIXO_FALHA_INESPERADA
from scpi.lancamento import LANCAMENTO_BLOQUEADO


def _num(resumo: dict, chave: str) -> int:
    return int(resumo.get(chave) or 0)


def feitas(execucao) -> int:
    """Requisições que a execução fez: simuladas na simulação, lançadas no lançamento real."""
    return _num(execucao.resumo or {}, "simuladas" if execucao.simulacao else "lancadas")


def n_de_m(execucao) -> str | None:
    """Requisições feitas do total, "3 de 3 requisições"; None sem total (falhou antes de
    começar ou não havia nada), nunca "0 de 0"."""
    total = _num(execucao.resumo or {}, "requisicoes")
    if not total:
        return None
    return f"{feitas(execucao)} de {total} {_requisicoes(total)}"


def duracao(inicio: datetime, fim: datetime | None) -> str:
    """Duração curta: "45 s", "2 min 5 s", "1 h 3 min"; "—" sem fim."""
    if fim is None:
        return "—"
    segundos = max(int((fim - inicio).total_seconds()), 0)
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas} h {minutos} min" if minutos else f"{horas} h"
    if minutos:
        return f"{minutos} min {segundos} s" if segundos else f"{minutos} min"
    return f"{segundos} s"


def momento(inicio: datetime, agora: datetime) -> str:
    """Quando começou, no horário local: "hoje, 13:25", "ontem, 13:25" ou "07/10, 13:25"."""
    local = timezone.localtime(inicio)
    hoje = timezone.localtime(agora).date()
    hora = local.strftime("%H:%M")
    if local.date() == hoje:
        return f"hoje, {hora}"
    if local.date() == hoje - timedelta(days=1):
        return f"ontem, {hora}"
    return f"{local.strftime('%d/%m')}, {hora}"


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _requisicoes(n: int) -> str:
    return "requisição" if n == 1 else "requisições"


def _cabeca(execucao, agora: datetime) -> str:
    """Modo e momento: "Simulação de hoje, 13:25" ou "Lançamento de hoje, 13:25"."""
    modo = "Simulação" if execucao.simulacao else "Lançamento"
    return f"{modo} de {momento(execucao.inicio, agora)}"


def _feminino(execucao, palavra: str) -> str:
    """Concorda com o modo: simulação é feminino ("concluída"), lançamento é masculino."""
    return palavra + ("a" if execucao.simulacao else "o")


def contadores(resumo: dict, simulacao: bool) -> list[str]:
    """Os contadores da execução diferentes de zero, já com o rótulo: "3 simuladas"."""
    resumo = resumo or {}
    feitas_ = (
        ("simuladas", "simulada", "simuladas") if simulacao else ("lancadas", "lançada", "lançadas")
    )
    itens = [
        feitas_,
        ("falhas", "com erro", "com erro"),
        ("verificar", "para verificar", "para verificar"),
        ("ignoradas", "deixada de fora", "deixadas de fora"),
    ]
    return [
        _plural(_num(resumo, chave), um, varios)
        for chave, um, varios in itens
        if _num(resumo, chave)
    ]


def precisa_conferir(execucao) -> bool:
    """Se a execução deixou algo nas travas: lote com erro ou para verificar, ou um lançamento
    real que falhou (a simulação não muda nenhuma linha)."""
    resumo = execucao.resumo or {}
    if _num(resumo, "falhas") or _num(resumo, "verificar"):
        return True
    return execucao.situacao == execucao.Situacao.FALHA and not execucao.simulacao


def frase(execucao, agora: datetime, interrompida: bool) -> str:
    """A execução numa frase: modo, momento, situação e "N de M requisições"."""
    resumo = execucao.resumo or {}
    total = _num(resumo, "requisicoes")
    Situacao = execucao.Situacao
    if execucao.situacao == Situacao.ANDAMENTO and not interrompida:
        modo = "Simulação" if execucao.simulacao else "Lançamento"
        if not total:
            return f"{modo} em andamento: preparando a fila."
        atual = min(_num(resumo, "processadas") + 1, total)
        return f"{modo} em andamento: requisição {atual} de {total}."
    cabeca = _cabeca(execucao, agora)
    if interrompida:
        return f"{cabeca}, {_feminino(execucao, 'interrompid')}: o robô parou sem registrar o fim."
    if execucao.situacao == Situacao.FALHA:
        return f"{cabeca}, falhou."
    situacao = _feminino(execucao, "concluíd")
    if execucao.situacao == Situacao.ATENCAO:
        situacao += " com pendências"
    if not total:
        return f"{cabeca}, {situacao}: nada a lançar."
    feito = "preenchida" if execucao.simulacao else "lançada"
    feito += "" if total == 1 else "s"
    return f"{cabeca}, {situacao}: {feitas(execucao)} de {total} {_requisicoes(total)} {feito}."


@dataclass(frozen=True)
class Falha:
    frase: str  # o que aconteceu, em português
    ate_onde: str
    proximo_passo: str
    tecnico: bool  # se há "Detalhe técnico" (o erro original e o registro) a mostrar
    simular_de_novo: bool


ERROS_CONHECIDOS = (LANCAMENTO_BLOQUEADO, "Outro lançamento já está em andamento.")


def _o_que_aconteceu(execucao) -> tuple[str, bool]:
    erro = (execucao.erro or "").strip()
    if erro in ERROS_CONHECIDOS:
        return erro, False
    if erro.startswith(PREFIXO_FALHA_INESPERADA):
        primeira = erro.removeprefix(PREFIXO_FALHA_INESPERADA).strip().splitlines()[0:1]
        if primeira and "Timeout" in primeira[0]:
            return "O SCPI demorou demais para responder e o robô parou.", True
        return "O robô parou por um erro do sistema.", True
    if not (execucao.log or "").strip() and not execucao.resumo:
        # O disparo não conseguiu iniciar o processo e gravou a exceção como veio.
        return "O robô não chegou a iniciar.", True
    return erro, "\n" in erro


def explicar_falha(execucao) -> Falha | None:
    """A falha em português: o que aconteceu, até onde chegou e o próximo passo. O texto gravado
    pelo robô não muda; o técnico fica para o "Detalhe técnico"."""
    if execucao.situacao != execucao.Situacao.FALHA:
        return None
    o_que, tecnico = _o_que_aconteceu(execucao)
    resumo = execucao.resumo or {}
    total = _num(resumo, "requisicoes")
    if total:
        ate_onde = (
            f"Chegou a processar {_num(resumo, 'processadas')} de {total} {_requisicoes(total)}."
        )
    else:
        ate_onde = "Parou antes de começar."
    if execucao.simulacao:
        proximo = (
            "Nenhuma linha mudou de estado. Pode simular de novo; se o erro se repetir, avise "
            "quem cuida do sistema."
        )
    else:
        proximo = "Confira as travas abaixo antes de lançar de novo."
    return Falha(o_que, ate_onde, proximo, tecnico, simular_de_novo=execucao.simulacao)


# --- Acompanhamento por requisição -------------------------------------------------------------
#
# Desde que o robô grava a lista das requisições no `resumo` (`lotes`, `fase`; scpi.lancamento),
# a aba mostra cada uma com o resultado, a etapa atual em português e quanto falta. A execução
# gravada antes disso (sem `lotes`) continua no cartão de uma frase.

PARADO_S = 60  # sem nenhuma linha nova no registro por esse tempo, o cartão avisa
NOMES_FASES = ("Ler o SCPI antes", "Lançar as requisições", "Conferir o que foi gravado")
ORDEM_FASES = ("antes", "lancando", "depois")

# A última linha reconhecida do registro da requisição atual vira a etapa; a primeira regra que
# casar vence (a ordem importa: "conferência final: 17 item(ns)" não é um item).
_ETAPAS = (
    ("reabrindo", "Preparando o SCPI para a próxima requisição"),
    ("[DRY-RUN]", "Descartando sem salvar"),
    ("etapa: salvar no SCPI", "Salvando no SCPI"),
    ("conferência final", "Conferindo o que foi digitado"),
    ("etapa: itens", "Preenchendo os materiais"),
    ("etapa: cabeçalho", "Preenchendo o cabeçalho"),
    ("etapa: abrir formulário", "Abrindo o formulário"),
    ("→ (", "Abrindo o formulário"),
)
_ITEM = re.compile(r"\bitem (\d+)/(\d+)\b")
_HORA = re.compile(r"^(\d\d):(\d\d):(\d\d) ")
_RESPOSTA_SCPI = re.compile(r"respondeu ao Salvar: '([^']+)'")


def etapa_do_log(log: str) -> str:
    """A etapa da requisição atual em português, pela última linha reconhecida do registro."""
    linhas = (log or "").splitlines()
    for linha in reversed(linhas):
        item = _ITEM.search(linha)
        if item and "conferência final" not in linha:
            return f"Preenchendo o item {item.group(1)} de {item.group(2)}"
        for marca, texto in _ETAPAS:
            if marca in linha:
                return texto
        if "→ (" in linha:  # começo da requisição atual: não olha a anterior
            break
    return "Trabalhando nesta requisição"


def ultima_atividade(log: str, agora: datetime) -> int | None:
    """Segundos desde a última linha do registro com horário (a hora vem no começo dela, no
    horário local; o rastro de uma exceção continua em linhas sem ela); None sem nenhuma."""
    hora = next(
        (achada for linha in reversed((log or "").splitlines()) if (achada := _HORA.match(linha))),
        None,
    )
    if hora is None:
        return None
    local = timezone.localtime(agora)
    h, m, s = (int(g) for g in hora.groups())
    momento_ = local.replace(hour=h, minute=m, second=s, microsecond=0)
    if momento_ > local + timedelta(minutes=1):  # linha de antes da meia-noite
        momento_ -= timedelta(days=1)
    return max(int((local - momento_).total_seconds()), 0)


def _quando(texto: str) -> datetime | None:
    return datetime.fromisoformat(texto) if texto else None


def _vai_ao_scpi(item: dict) -> bool:
    """Lote que o robô processa (ou processaria): os travados e inválidos nunca vão."""
    return bool(item.get("inicio")) or item.get("resultado") in ("aguardando", "andamento")


def _segundos(segundos: int) -> str:
    agora = timezone.now()
    return duracao(agora - timedelta(seconds=segundos), agora)


def estimativa(lotes: list[dict], agora: datetime) -> str | None:
    """Quanto falta, pelo tempo médio das requisições já concluídas; None antes da primeira ou
    sem nada por fazer."""
    tempos = [
        (_quando(i["fim"]) - _quando(i["inicio"])).total_seconds()
        for i in lotes
        if i.get("inicio") and i.get("fim")
    ]
    aguardando = sum(1 for i in lotes if i.get("resultado") == "aguardando")
    atual = next((i for i in lotes if i.get("resultado") == "andamento"), None)
    if not tempos or not (aguardando or atual):
        return None
    media = sum(tempos) / len(tempos)
    falta = media * aguardando
    if atual and atual.get("inicio"):
        falta += max(media - (agora - _quando(atual["inicio"])).total_seconds(), 0)
    if falta < 60:
        return "falta menos de 1 min"
    return f"faltam cerca de {math.ceil(falta / 60)} min"


@dataclass(frozen=True)
class Fase:
    nome: str
    estado: str  # "feita", "atual", "parou" ou "" (ainda não)
    texto: str


@dataclass(frozen=True)
class LinhaRequisicao:
    lote: str
    recebedor: str
    centro: str
    itens: int
    estado: str  # ok, aviso, erro, fora, atual, espera
    icone: str  # nome do _icone.html; vazio nas marcas desenhadas (atual, espera)
    texto: str
    requisicao: str
    detalhe: str


@dataclass(frozen=True)
class Agora:
    rotulo: str
    linha: LinhaRequisicao | None
    etapa: str
    atividade: str
    parado: bool


@dataclass(frozen=True)
class Desfecho:
    tipo: str  # "ok" ou "atencao"
    titulo: str
    texto: str
    travas: int  # quantas foram para as travas (botão "Ver as travas")


@dataclass(frozen=True)
class Acompanhamento:
    titulo: str
    iniciado: str  # "Iniciado" ou "Iniciada", concorda com o modo
    quando: str  # "hoje às 12:25"
    tempo: str  # "4 min decorridos", "levou 8 min 35 s"
    em_andamento: bool
    fases: list[Fase]
    feitas: int
    total: int
    barra: dict
    estimativa: str | None
    agora: Agora | None
    linhas: list[LinhaRequisicao]
    contagem: str
    desfecho: Desfecho | None


def _detalhe_verificar(mensagem: str) -> str:
    texto = "O robô não sabe se ela foi gravada."
    if resposta := _RESPOSTA_SCPI.search(mensagem or ""):
        texto += f" O SCPI respondeu: “{resposta.group(1).strip()[:140]}”"
    return texto


def _primeira_linha(mensagem: str, limite: int = 200) -> str:
    linhas = (mensagem or "").strip().splitlines()
    return linhas[0][:limite] if linhas else ""


def _linha(item: dict, simulacao: bool, rodando: bool) -> LinhaRequisicao:
    resultado = item.get("resultado")
    requisicao, detalhe = "", ""
    if resultado == "lancada":
        estado, icone, texto, requisicao = "ok", "check", "Lançada", item.get("requisicao", "")
    elif resultado == "simulada":
        estado, icone, texto = "ok", "check", "Preenchida e conferida"
    elif resultado == "verificar":
        estado, icone, texto = "aviso", "alerta", "Conferir no SCPI"
        detalhe = _detalhe_verificar(item.get("mensagem", ""))
    elif resultado == "erro":
        estado, icone = "erro", "fechar"
        texto = "Não foi possível preencher" if simulacao else "Com erro, não foi salva"
        detalhe = _primeira_linha(item.get("mensagem", ""))
    elif resultado == "ignorada":
        estado, icone, texto = "fora", "menos", "Deixada de fora"
        detalhe = _primeira_linha(item.get("mensagem", ""))
    elif resultado == "andamento" and rodando:
        estado, icone, texto = "atual", "", "Em andamento"
    elif resultado == "andamento":
        estado, icone, texto = "erro", "alerta", "O robô parou nesta requisição"
        detalhe = "Nada foi salvo." if simulacao else "Confira nas travas se ela foi gravada."
    elif rodando:
        estado, icone, texto = "espera", "", "Aguardando"
    else:
        estado, icone, texto = "fora", "menos", "Não chegou a ser processada"
    return LinhaRequisicao(
        lote=item.get("lote", ""),
        recebedor=item.get("recebedor", ""),
        centro=item.get("centro", ""),
        itens=int(item.get("itens") or 0),
        estado=estado,
        icone=icone,
        texto=texto,
        requisicao=requisicao,
        detalhe=detalhe,
    )


def _fases(execucao, rodando: bool, parou: bool, feitas: int, total: int) -> list[Fase]:
    if execucao.simulacao or not total:  # sem requisição para o SCPI, nenhuma fase rodou
        return []
    fase = (execucao.resumo or {}).get("fase") or "lancando"
    atual = ORDEM_FASES.index(fase) if fase in ORDEM_FASES else 1
    fases = []
    for i, nome in enumerate(NOMES_FASES):
        if not rodando and not parou:
            estado = "feita"
        elif i < atual:
            estado = "feita"
        elif i == atual:
            estado = "atual" if rodando else "parou"
        else:
            estado = ""
        if i == 1 and estado in ("feita", "atual"):
            texto = f"{feitas} de {total} feitas"
        else:
            texto = {"feita": "Feito", "atual": "Lendo agora", "parou": "Parou aqui"}.get(
                estado, ""
            )
        fases.append(Fase(nome, estado, texto))
    return fases


def _agora(execucao, linhas, agora: datetime) -> Agora:
    fase = (execucao.resumo or {}).get("fase")
    linha = next((linha for linha in linhas if linha.estado == "atual"), None)
    if fase == "antes":
        rotulo, linha = "Antes de lançar", None
        etapa = "Lendo no SCPI as requisições já gravadas, para conferir tudo depois"
    elif fase == "depois":
        rotulo, linha = "Depois de lançar", None
        etapa = "Lendo no SCPI o que foi gravado, para conferir com o que o robô lançou"
    else:
        rotulo = "Agora"
        etapa = etapa_do_log(execucao.log) if linha else "Abrindo o SCPI"
    segundos = ultima_atividade(execucao.log, agora)
    parado = segundos is not None and segundos >= PARADO_S
    if parado:
        rotulo = f"Sem novidade há {_segundos(segundos)}"
        atividade = (
            "O SCPI às vezes demora para responder. Se passar de 5 min sem novidade, avise quem "
            "cuida do sistema."
        )
    elif segundos is not None:
        atividade = f"Última atividade há {_segundos(segundos)}"
    else:
        atividade = ""
    return Agora(rotulo, linha, etapa, atividade, parado)


def _contagem(linhas, simulacao: bool) -> str:
    def conta(estado_ou_texto):
        return sum(1 for linha in linhas if estado_ou_texto(linha))

    partes = []
    ok = conta(lambda linha: linha.estado == "ok")
    if ok:
        partes.append(
            _plural(ok, "preenchida", "preenchidas")
            if simulacao
            else _plural(ok, "lançada", "lançadas")
        )
    for n, texto in (
        (conta(lambda linha: linha.estado == "aviso"), "para conferir"),
        (conta(lambda linha: linha.estado == "erro"), "com erro"),
    ):
        if n:
            partes.append(f"{n} {texto}")
    fora = conta(lambda linha: linha.estado == "fora")
    if fora:
        partes.append(_plural(fora, "deixada de fora", "deixadas de fora"))
    espera = conta(lambda linha: linha.estado == "espera")
    if espera:
        partes.append(f"{espera} aguardando")
    return " · ".join(partes)


def _desfecho(execucao, linhas) -> Desfecho | None:
    """O resultado da execução com o próximo passo (só depois do fim, sem falha)."""
    if not linhas:
        return None
    verificar = sum(1 for linha in linhas if linha.estado == "aviso")
    erros = sum(1 for linha in linhas if linha.estado == "erro")
    ok = sum(1 for linha in linhas if linha.estado == "ok")
    if execucao.simulacao:
        if erros:
            titulo = (
                "1 requisição não pôde ser preenchida."
                if erros == 1
                else f"{erros} requisições não puderam ser preenchidas."
            )
            return Desfecho("atencao", titulo, "Veja o motivo na lista. Nenhuma linha mudou.", 0)
        if not ok:
            return Desfecho("atencao", "Nenhuma requisição foi preenchida.", NENHUMA, 0)
        if ok == 1:
            return Desfecho(
                "ok",
                "A requisição foi preenchida e conferida no SCPI, sem salvar.",
                "Nenhuma linha mudou: ela continua na fila, pronta para lançar.",
                0,
            )
        return Desfecho(
            "ok",
            f"As {ok} requisições foram preenchidas e conferidas no SCPI, sem salvar.",
            "Nenhuma linha mudou: elas continuam na fila, prontas para lançar.",
            0,
        )
    if verificar or erros:
        textos = []
        if verificar:
            titulo = (
                "1 requisição precisa ser conferida no SCPI."
                if verificar == 1
                else f"{verificar} requisições precisam ser conferidas no SCPI."
            )
            gravada = "ela foi gravada" if verificar == 1 else "elas foram gravadas"
            textos.append(
                f"O robô não sabe se {gravada}. Confira nas travas antes de lançar de novo."
            )
        else:
            titulo = "1 requisição com erro." if erros == 1 else f"{erros} requisições com erro."
        if erros:
            erro = (
                "1 requisição teve erro e não foi salva"
                if erros == 1
                else f"{erros} requisições tiveram erro e não foram salvas"
            )
            textos.append(f"{erro}: veja o motivo na lista e resolva nas travas.")
        return Desfecho("atencao", titulo, " ".join(textos), verificar + erros)
    if not ok:
        return Desfecho("atencao", "Nenhuma requisição foi lançada.", NENHUMA, 0)
    if ok == 1:
        return Desfecho("ok", "A requisição foi lançada no SCPI.", "", 0)
    return Desfecho("ok", f"As {ok} requisições foram lançadas no SCPI.", "", 0)


NENHUMA = "Veja na lista por que cada uma ficou de fora."


def _titulo(execucao, rodando: bool, interrompida: bool) -> str:
    modo = "Simulação" if execucao.simulacao else "Lançamento"
    if rodando:
        return f"{modo} em andamento"
    if interrompida:
        return f"{modo} {_feminino(execucao, 'interrompid')}"
    Situacao = execucao.Situacao
    if execucao.situacao == Situacao.FALHA:
        return f"{modo} falhou"
    titulo = f"{modo} {_feminino(execucao, 'concluíd')}"
    if execucao.situacao == Situacao.ATENCAO:
        titulo += " com pendências"
    return titulo


def acompanhamento(execucao, agora: datetime, interrompida: bool) -> Acompanhamento | None:
    """A execução por requisição, para o cartão da aba Lançamento no SCPI; None na execução
    gravada antes da lista de requisições no `resumo`."""
    resumo = execucao.resumo or {}
    if "lotes" not in resumo:
        return None
    rodando = execucao.situacao == execucao.Situacao.ANDAMENTO and not interrompida
    parou = interrompida or execucao.situacao == execucao.Situacao.FALHA
    itens = resumo["lotes"]
    linhas = [_linha(item, execucao.simulacao, rodando) for item in itens]
    no_scpi = [
        (item, linha) for item, linha in zip(itens, linhas, strict=True) if _vai_ao_scpi(item)
    ]
    total = len(no_scpi)
    feitas = sum(1 for item in itens if item.get("fim"))

    def parte(estado):
        # "fora" só conta a que foi processada (com fim): a não processada não enche a barra.
        n = sum(
            1
            for item, linha in no_scpi
            if linha.estado == estado and (estado != "fora" or item.get("fim"))
        )
        return round(100 * n / total, 2) if total else 0.0

    barra = {estado: parte(estado) for estado in ("ok", "aviso", "erro", "fora", "atual")}
    if rodando:
        tempo = f"{duracao(execucao.inicio, agora)} decorridos"
        prevista = estimativa(itens, agora)
        if prevista is None and total and feitas < total:
            prevista = "a estimativa aparece depois da primeira requisição"
    else:
        tempo = f"levou {duracao(execucao.inicio, execucao.fim)}" if execucao.fim else ""
        prevista = None
    return Acompanhamento(
        titulo=_titulo(execucao, rodando, interrompida),
        iniciado="Iniciada" if execucao.simulacao else "Iniciado",
        quando=momento(execucao.inicio, agora).replace(", ", " às "),
        tempo=tempo,
        em_andamento=rodando,
        fases=_fases(execucao, rodando, parou, feitas, total),
        feitas=feitas,
        total=total,
        barra=barra,
        estimativa=prevista,
        agora=_agora(execucao, linhas, agora) if rodando else None,
        linhas=linhas,
        contagem=_contagem(linhas, execucao.simulacao),
        desfecho=None if (rodando or parou) else _desfecho(execucao, linhas),
    )
