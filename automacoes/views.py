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
from django.views.decorators.http import require_POST

from automacoes.historico import FiltrosHistorico, SequenciaHistorico, consultas
from automacoes.visao_geral import linha_lancamento
from catalogo.curva import INICIO_DADOS_CONFIAVEIS
from catalogo.forms import ROBOS, ROBOS_POR_CHAVE
from catalogo.models import Importacao
from catalogo.saude import situacao_do_catalogo
from interface.htmx import regiao_pedida, render_regiao
from pedidos import andamento
from pedidos.consultas import fila_do_robo, lotes_pendentes, lotes_travados
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

LINHAS_POR_PAGINA = 20

# Depois do clique, o processo leva alguns segundos para criar a primeira Importacao; entre
# uma importação e a seguinte também não há nenhuma em andamento. Nessas janelas a página
# continua acompanhando (e, logo após o clique, não oferece um segundo disparo).
CARENCIA = timedelta(seconds=30)
CHAVE_DISPARO = "catalogo_disparo_em"
LINHAS_DO_LOG = 40
JA_EM_ANDAMENTO = "Já há uma importação em andamento. Aguarde terminar."


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


def _terminou_agora(agora: datetime) -> bool:
    """Alguma importação terminou há pouco: a página ainda acompanha, para mostrar o resultado."""
    return Importacao.objects.filter(fim__gte=agora - CARENCIA).exists()


def contexto_catalogo(request) -> dict:
    """Situação do catálogo e as marcas de importação em andamento."""
    agora = timezone.now()
    em_andamento = importacao_em_andamento(request, agora)
    return {
        "situacao": situacao_do_catalogo(agora),
        "importacao_em_andamento": em_andamento,
        "acompanhar_catalogo": em_andamento or _terminou_agora(agora),
        "inicio_dados": INICIO_DADOS_CONFIAVEIS,
        # Fontes com aba de robô: a linha da fonte na situação leva até ela.
        "tipos_com_aba": [r.chave.upper() for r in ROBOS],
    }


def _linha_do_lancamento(execucao, *, interrompida, em_andamento, pendentes, travados) -> dict:
    """O que a situação lê do lançamento: a linha da visão geral e a marca de acompanhamento."""
    return {
        "linha_lancamento": linha_lancamento(
            pendentes=pendentes,
            travados=travados,
            ultima=execucao,
            em_andamento=em_andamento,
            interrompida=interrompida,
            agora=timezone.now(),
        ),
        "acompanhar_lancamento": em_andamento,
        "lancamento_travado": bool(travados),
    }


def contexto_lancamento() -> dict:
    """Lançamento das saídas no SCPI: botões, fila, andamento do robô e travas."""
    agora = timezone.now()
    execucao = ExecucaoRobo.objects.select_related("iniciada_por").first()
    em_andamento = ExecucaoRobo.em_andamento(agora).exists()
    fila = fila_do_robo()
    travados = lotes_travados()
    interrompida = bool(execucao and execucao.interrompida)
    resumo = None
    if execucao:
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
        "log_recente": "\n".join(execucao.log.splitlines()[-LINHAS_DO_LOG:]) if execucao else "",
        "fila": fila,
        "pode_executar": bool(fila.total) and not em_andamento,
        "travados": travados,
        "lancamento_real": settings.LANCAMENTO_REAL,
        **_linha_do_lancamento(
            execucao,
            interrompida=interrompida,
            em_andamento=em_andamento,
            pendentes=fila.total,
            travados=len(travados),
        ),
    }


def _lancamento_resumido() -> dict:
    """Só o que a situação lê do lançamento, sem a fila inteira nem o andamento da aba: a recarga
    da situação não paga o contexto da aba Lançamento no SCPI."""
    execucao = ExecucaoRobo.objects.first()
    return _linha_do_lancamento(
        execucao,
        interrompida=bool(execucao and execucao.interrompida),
        em_andamento=ExecucaoRobo.em_andamento(timezone.now()).exists(),
        pendentes=lotes_pendentes(),
        travados=len(lotes_travados()),
    )


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


def _contexto_situacao(request, lancamento: dict | None = None) -> dict:
    """O que `catalogo/_situacao.html` lê: a situação do catálogo (com o que a visão geral mostra
    do lançamento: a linha e o resumo) e as marcas de acompanhamento. `lancamento` é o contexto
    da aba, quando a página inteira já o montou."""
    catalogo = contexto_catalogo(request)
    lancamento = lancamento or _lancamento_resumido()
    resumo = catalogo["situacao"].resumo
    if lancamento["lancamento_travado"]:
        resumo += f" Lançamento no SCPI: {lancamento['linha_lancamento'].selo}."
    return {**catalogo, **lancamento, "resumo_geral": resumo}


def _contexto_acompanhamento(request) -> dict:
    """Só as duas marcas de acompanhamento que `automacoes/_historico.html` lê, sem montar a
    situação do catálogo nem o lançamento."""
    agora = timezone.now()
    return {
        "acompanhar_catalogo": importacao_em_andamento(request, agora) or _terminou_agora(agora),
        "acompanhar_lancamento": ExecucaoRobo.em_andamento(agora).exists(),
    }


def contexto_pagina(request, aba: str, formularios: dict | None = None) -> dict:
    """Tudo o que a página mostra; também usado quando o formulário de um robô volta com erro
    (`formularios`: o formulário de cada robô com o que a pessoa já preencheu)."""
    situacao = _contexto_situacao(request, contexto_lancamento())
    formularios = formularios or {}
    fontes = {fonte.tipo: fonte for fonte in situacao["situacao"].fontes}
    robos = [
        {
            "robo": robo,
            "form": formularios.get(robo.chave) or robo.novo(),
            "fonte": fontes.get(robo.chave.upper()),
        }
        for robo in ROBOS
    ]
    # A aba mostra o selo quando pede atenção ou está rodando.
    estados = {
        "lancamento": situacao["linha_lancamento"],
        **{item["robo"].chave: item["fonte"] for item in robos},
    }
    return {
        **_contexto_historico(request),
        **situacao,
        "robos": robos,
        "aba": aba,
        "abas": [(chave, rotulo, estados.get(chave)) for chave, rotulo in ABAS],
    }


def _contexto_regiao_historico(request) -> dict:
    return {**_contexto_acompanhamento(request), **_contexto_historico(request)}


# Regiões que o HTMX recarrega, pelo cabeçalho HX-Target (`tag#id` no HTMX 4): o parcial e a função
# que monta só o contexto dele (o mesmo que `contexto_pagina` daria para as variáveis que ele lê;
# a recarga de uma região não paga o contexto das outras).
REGIOES = {
    "section#situacao-catalogo": ("catalogo/_situacao.html", _contexto_situacao),
    "section#lancamentos": ("pedidos/_lancamentos.html", lambda request: contexto_lancamento()),
    "div#historico": ("automacoes/_historico.html", _contexto_regiao_historico),
}


@login_required
def pagina(request):
    # Com HX-Request, só a região pedida (recarga enquanto há algo em andamento), com só o contexto
    # dela; o resto, a página inteira.
    regiao = regiao_pedida(request, REGIOES)
    if regiao:
        modelo, montar = regiao
        return render_regiao(request, modelo, montar(request))
    return render_regiao(
        request, "automacoes/pagina.html", contexto_pagina(request, aba_pedida(request))
    )


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
        messages.warning(request, JA_EM_ANDAMENTO)
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
        messages.warning(request, JA_EM_ANDAMENTO)
        return redirect(destino)
    dados = form.cleaned_data
    enviado = dados.get("arquivo")
    arquivo = guardar_csv_enviado(enviado) if enviado else None
    iniciou = False
    try:
        iniciou = iniciar_importacao(
            robo,
            forcar=bool(dados.get("forcar")),
            completo=bool(dados.get("completo")),
            desde=dados.get("desde"),
            ate=dados.get("ate"),
            arquivo=arquivo,
        )
    finally:
        # O comando apaga o CSV ao fim; se ele não iniciou, ninguém mais o apaga.
        if arquivo and not iniciou:
            arquivo.unlink(missing_ok=True)
    if not iniciou:
        messages.warning(request, JA_EM_ANDAMENTO)
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
    lotes = form.cleaned_data["lotes"]
    if iniciar_lancamento(request.user, simulacao=simulacao, lotes=lotes) is None:
        messages.warning(request, "Já há um lançamento em andamento. Aguarde terminar.")
    else:
        texto = (
            "Simulação iniciada: o robô preenche cada requisição no SCPI e não salva."
            if simulacao
            else "Lançamento iniciado. Acompanhe o andamento abaixo."
        )
        texto += f" {', '.join(lotes)}."
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
