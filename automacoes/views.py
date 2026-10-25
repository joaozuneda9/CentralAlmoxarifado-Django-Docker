"""Página Automações: uma aba de visão geral, a do lançamento no SCPI e uma por robô de importação.

A página só lê. As ações (atualizar o catálogo, importar, lançar e resolver uma trava) validam e
chamam `scpi.disparo` e `servicos.resolver_lote`, como faziam nas páginas que esta substituiu, e
voltam para a aba de onde vieram.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_POST

from automacoes.historico import FiltrosHistorico, SequenciaHistorico, consultas
from automacoes.visao_geral import linha_lancamento
from catalogo.curva import INICIO_DADOS_CONFIAVEIS
from catalogo.forms import ROBOS, ROBOS_POR_CHAVE
from catalogo.models import Importacao
from catalogo.saude import situacao_do_catalogo
from pedidos import andamento
from pedidos.consultas import fila_do_robo, lotes_travados
from pedidos.forms import LancamentoForm
from pedidos.models import ExecucaoRobo
from pedidos.servicos import resolver_lote
from scpi.disparo import (
    guardar_csv_enviado,
    iniciar_atualizacao,
    iniciar_importacao,
    iniciar_lancamento,
)

ABAS = [
    ("visao-geral", "Visão geral"),
    ("lancamento", "Lançamento no SCPI"),
    *((robo.chave, robo.rotulo) for robo in ROBOS),
]
CHAVES_ABAS = [chave for chave, _ in ABAS]

# Regiões que o HTMX recarrega, pelo cabeçalho HX-Target (`tag#id` no HTMX 4).
REGIOES = {
    "section#situacao-catalogo": "catalogo/_situacao.html",
    "section#lancamentos": "pedidos/_lancamentos.html",
    "div#historico": "automacoes/_historico.html",
}
LINHAS_POR_PAGINA = 20

# Depois do clique, o processo leva alguns segundos para criar a primeira Importacao; entre
# uma importação e a seguinte também não há nenhuma em andamento. Nessas janelas a página
# continua acompanhando (e, logo após o clique, não oferece um segundo disparo).
CARENCIA = timedelta(seconds=30)
CHAVE_DISPARO = "catalogo_disparo_em"
LINHAS_DO_LOG = 40


def aba_pedida(request) -> str:
    """A aba de `?aba=`; desconhecida, ausente ou `situacao` (o nome antigo) é a visão geral."""
    aba = request.GET.get("aba", "")
    return aba if aba in CHAVES_ABAS else "visao-geral"


def url_da_aba(aba: str) -> str:
    return f"{reverse('automacoes:pagina')}?aba={aba}"


def _disparo_recente(request, agora: datetime) -> bool:
    try:
        momento = datetime.fromisoformat(request.session.get(CHAVE_DISPARO, ""))
    except ValueError:
        return False
    return momento > agora - CARENCIA


def importacao_em_andamento(request, agora: datetime | None = None) -> bool:
    """Há importação rodando ou recém-disparada por esta sessão (o processo ainda está subindo e
    não criou a primeira `Importacao`). É o que os botões que iniciam importações respeitam."""
    agora = agora or timezone.now()
    return Importacao.em_andamento(agora).exists() or _disparo_recente(request, agora)


def _acompanhar_importacoes(request, agora: datetime) -> tuple[bool, bool]:
    """(há importação em andamento, a página deve seguir acompanhando as importações): só duas
    consultas, sem montar a situação do catálogo."""
    em_andamento = importacao_em_andamento(request, agora)
    terminou_agora = Importacao.objects.filter(fim__gte=agora - CARENCIA).exists()
    return em_andamento, em_andamento or terminou_agora


def contexto_catalogo(request, formularios: dict | None = None) -> dict:
    """Situação do catálogo e, por robô, o formulário (com o que a pessoa já preencheu, se houver
    erro) e a última importação daquele tipo."""
    agora = timezone.now()
    em_andamento, acompanhar = _acompanhar_importacoes(request, agora)
    formularios = formularios or {}
    situacao = situacao_do_catalogo(agora)
    fontes = {fonte.tipo: fonte for fonte in situacao.fontes}
    return {
        "situacao": situacao,
        "fontes": fontes,
        "importacao_em_andamento": em_andamento,
        "acompanhar_catalogo": acompanhar,
        "inicio_dados": INICIO_DADOS_CONFIAVEIS,
        # Fontes com aba de robô: a linha da fonte na situação leva até ela.
        "tipos_com_aba": [r.chave.upper() for r in ROBOS],
        "robos": [
            {
                "robo": robo,
                "form": formularios.get(robo.chave) or robo.novo(),
                "fonte": fontes.get(robo.chave.upper()),
            }
            for robo in ROBOS
        ],
    }


def contexto_lancamento() -> dict:
    """Lançamento das saídas no SCPI: botões, fila, andamento do robô e travas."""
    agora = timezone.now()
    execucao = ExecucaoRobo.objects.select_related("iniciada_por").first()
    em_andamento = ExecucaoRobo.em_andamento(agora).exists()
    fila = fila_do_robo()
    resumo = None
    if execucao:
        interrompida = execucao.interrompida
        resumo = {
            "frase": andamento.frase(execucao, agora, interrompida),
            "interrompida": interrompida,
            "contadores": andamento.contadores(execucao.resumo, execucao.simulacao),
            "duracao": andamento.duracao(execucao.inicio, execucao.fim),
            "precisa_conferir": andamento.precisa_conferir(execucao),
            "falha": andamento.explicar_falha(execucao),
        }
    return {
        "execucao": execucao,
        "andamento": resumo,
        "lancamento_em_andamento": em_andamento,
        "acompanhar_lancamento": em_andamento,
        "log_recente": "\n".join(execucao.log.splitlines()[-LINHAS_DO_LOG:]) if execucao else "",
        "fila": fila,
        "pode_executar": bool(fila.total) and not em_andamento,
        "travados": lotes_travados(),
        "lancamento_real": settings.LANCAMENTO_REAL,
    }


def _contexto_historico(request) -> dict:
    """Lista paginada do histórico, com os filtros da query."""
    filtros = FiltrosHistorico(request.GET)
    ativos = filtros.filtros()
    historico = SequenciaHistorico(*consultas(ativos, timezone.now()))
    return {
        "filtros_historico": filtros,
        "historico_filtrado": bool(ativos),
        "pagina_historico": Paginator(historico, LINHAS_POR_PAGINA).get_page(
            request.GET.get("pagina")
        ),
    }


def _linha_do_lancamento(lancamento: dict):
    execucao = lancamento["execucao"]
    return linha_lancamento(
        pendentes=lancamento["fila"].total,
        travados=len(lancamento["travados"]),
        ultima=execucao,
        em_andamento=lancamento["lancamento_em_andamento"],
        interrompida=bool(execucao and execucao.interrompida),
        agora=timezone.now(),
    )


def _contexto_situacao(request, formularios: dict | None = None) -> dict:
    """O que `catalogo/_situacao.html` lê: a situação do catálogo (com o que a visão geral mostra
    do lançamento: a linha e o resumo) e o acompanhamento, que também segue o lançamento."""
    catalogo = contexto_catalogo(request, formularios)
    lancamento = contexto_lancamento()
    linha = _linha_do_lancamento(lancamento)
    resumo = catalogo["situacao"].resumo
    if lancamento["travados"]:
        resumo += f" Lançamento no SCPI: {linha.selo}."
    return {
        **catalogo,
        **lancamento,
        "linha_lancamento": linha,
        "resumo_geral": resumo,
        # A visão geral também acompanha o lançamento, para a linha dele se atualizar.
        "acompanhar_catalogo": catalogo["acompanhar_catalogo"]
        or lancamento["lancamento_em_andamento"],
    }


def _contexto_acompanhamento(request) -> dict:
    """Só as duas marcas de acompanhamento que `automacoes/_historico.html` lê, sem montar a
    situação do catálogo nem o lançamento."""
    agora = timezone.now()
    lancamento = ExecucaoRobo.em_andamento(agora).exists()
    return {
        "acompanhar_catalogo": _acompanhar_importacoes(request, agora)[1] or lancamento,
        "acompanhar_lancamento": lancamento,
    }


def contexto_pagina(request, aba: str, formularios: dict | None = None) -> dict:
    """Tudo o que a página mostra; também usado quando o formulário de um robô volta com erro."""
    situacao = _contexto_situacao(request, formularios)
    fontes = situacao["fontes"]
    return {
        **_contexto_historico(request),
        **situacao,
        "aba": aba,
        # (chave, rótulo, estado): a aba mostra o selo quando pede atenção ou está rodando.
        "abas": [
            ("visao-geral", "Visão geral", None),
            ("lancamento", "Lançamento no SCPI", situacao["linha_lancamento"]),
            *((r.chave, r.rotulo, fontes.get(r.chave.upper())) for r in ROBOS),
        ],
    }


# Região → função que monta só o contexto do seu parcial (o mesmo que `contexto_pagina` daria
# para as variáveis que ele lê; a recarga de uma região não paga o contexto das outras).
CONTEXTO_DAS_REGIOES = {
    "section#situacao-catalogo": lambda request: _contexto_situacao(request),
    "section#lancamentos": lambda request: contexto_lancamento(),
    "div#historico": lambda request: {
        **_contexto_acompanhamento(request),
        **_contexto_historico(request),
    },
}


@login_required
def pagina(request):
    # Com HX-Request, só a região pedida (recarga enquanto há algo em andamento), com só o contexto
    # dela; ao restaurar o histórico (botão Voltar) o HTMX também manda HX-Request, mas precisa da
    # página inteira. Alvo desconhecido também devolve a página inteira.
    alvo = request.headers.get("HX-Target", "")
    if (
        request.headers.get("HX-Request")
        and not request.headers.get("HX-History-Restore-Request")
        and alvo in REGIOES
    ):
        modelo = REGIOES[alvo]
        contexto = CONTEXTO_DAS_REGIOES[alvo](request)
    else:
        modelo = "automacoes/pagina.html"
        contexto = contexto_pagina(request, aba_pedida(request))
    resposta = render(request, modelo, contexto)
    patch_vary_headers(resposta, ["HX-Request", "HX-Target", "HX-History-Restore-Request"])
    return resposta


@login_required
@require_POST
def atualizar(request):
    agora = timezone.now()
    carga_inicial = request.POST.get("modo") == "carga-inicial"
    destino = url_da_aba("visao-geral")
    if carga_inicial and not request.POST.get("confirmar"):
        messages.warning(
            request, "Para a carga inicial completa, marque que está ciente do que ela faz."
        )
        return redirect(destino)
    if not _disparo_recente(request, agora) and iniciar_atualizacao(carga_inicial):
        request.session[CHAVE_DISPARO] = agora.isoformat()
        messages.success(
            request,
            (
                "Carga inicial completa iniciada: o cadastro inteiro, o estoque e as saídas desde "
                f"{INICIO_DADOS_CONFIAVEIS:%d/%m/%Y}; acompanhe abaixo."
            )
            if carga_inicial
            else (
                "Atualização iniciada. Cadastro, estoque e saídas são importados em sequência; "
                "acompanhe abaixo."
            ),
        )
    else:
        messages.warning(request, "Já há uma importação em andamento. Aguarde terminar.")
    return redirect(destino)


@login_required
@require_POST
def importar(request, robo):
    """Roda um robô de importação sozinho, com os parâmetros do formulário da sua aba."""
    definicao = ROBOS_POR_CHAVE.get(robo)
    if definicao is None:
        raise Http404
    form = definicao.novo(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request, "automacoes/pagina.html", contexto_pagina(request, robo, {robo: form})
        )
    agora = timezone.now()
    destino = url_da_aba(robo)
    if importacao_em_andamento(request, agora):
        messages.warning(request, "Já há uma importação em andamento. Aguarde terminar.")
        return redirect(destino)
    dados = form.cleaned_data
    enviado = dados.get("arquivo")
    arquivo = guardar_csv_enviado(enviado) if enviado else None
    try:
        iniciou = iniciar_importacao(
            robo,
            forcar=bool(dados.get("forcar")),
            completo=bool(dados.get("completo")),
            desde=dados.get("desde"),
            ate=dados.get("ate"),
            arquivo=arquivo,
        )
    except Exception:
        if arquivo:
            arquivo.unlink(missing_ok=True)
        raise
    if not iniciou:
        if arquivo:
            arquivo.unlink(missing_ok=True)
        messages.warning(request, "Já há uma importação em andamento. Aguarde terminar.")
        return redirect(destino)
    request.session[CHAVE_DISPARO] = agora.isoformat()
    messages.success(
        request,
        f"Importação de {definicao.rotulo.lower()} iniciada. Acompanhe na Visão geral.",
    )
    return redirect(destino)


@login_required
@require_POST
def lancar(request):
    destino = url_da_aba("lancamento")
    form = LancamentoForm.da_requisicao(request.POST)
    if not form.is_valid():
        for erros in form.errors.values():
            messages.error(request, " ".join(erros))
        return redirect(destino)
    simulacao = form.cleaned_data["modo"] == "simular"
    limite = form.cleaned_data["limite"]
    if iniciar_lancamento(request.user, simulacao=simulacao, limite=limite) is None:
        messages.warning(request, "Já há um lançamento em andamento. Aguarde terminar.")
    else:
        texto = (
            "Simulação iniciada: o robô preenche cada requisição no SCPI e não salva."
            if simulacao
            else "Lançamento iniciado. Acompanhe o andamento abaixo."
        )
        if limite:
            texto += f" Limite: {limite} {'requisição' if limite == 1 else 'requisições'}."
        messages.success(request, texto)
    return redirect(destino)


@login_required
@require_POST
def resolver(request, lote):
    destino = url_da_aba("lancamento")
    # "Não lançar" tira a requisição do lançamento: só com a confirmação do segundo passo.
    if request.POST.get("acao") == "nao_lancar" and request.POST.get("confirmado") != "1":
        messages.error(request, "Confirme antes de marcar para não lançar.")
        return redirect(destino)
    resposta = resolver_lote(
        lote,
        request.POST.get("acao", ""),
        usuario=request.user,
        requisicao=request.POST.get("requisicao", ""),
        conferido=bool(request.POST.get("conferido")),
    )
    mensagem = messages.success if resposta.ok else messages.error
    mensagem(request, resposta.mensagem)
    return redirect(destino)
