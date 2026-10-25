"""Telas da Segurança do Trabalho (spec 008): a fila dos pedidos de EPI e a decisão de cada um.

A decisão em si é `servicos.decidir_autorizacao` (a única porta de gravação). Aqui só se lê e se
mostra; quem não é do grupo recebe 403 mesmo que o middleware (`contas.middleware`) não o tenha
barrado, porque o acesso à decisão não pode depender de um filtro só."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from contas.acesso import da_seguranca_trabalho
from pedidos.consultas import decididas_da_autorizacao, fila_de_autorizacao
from pedidos.models import AutorizacaoPedido
from pedidos.servicos import decidir_autorizacao


def _exigir_seguranca_do_trabalho(usuario) -> None:
    if not da_seguranca_trabalho(usuario):
        raise PermissionDenied("Só a Segurança do Trabalho acessa as autorizações.")


def _autorizacao(numero: str) -> AutorizacaoPedido:
    """A autorização do pedido de EPI; 404 para número que não é de um pedido com autorização."""
    consulta = AutorizacaoPedido.objects.select_related("pedido", "decidido_por").prefetch_related(
        "pedido__itens"
    )
    return get_object_or_404(consulta, pedido__numero=numero)


@login_required
def autorizacoes(request):
    """A fila: os que aguardam decisão (do mais antigo ao mais novo) e, abaixo, os já decididos."""
    _exigir_seguranca_do_trabalho(request.user)
    decididas = Paginator(decididas_da_autorizacao(), 25).get_page(request.GET.get("pagina"))
    return render(
        request,
        "pedidos/autorizacoes.html",
        {"aguardando": list(fila_de_autorizacao()), "decididas": decididas},
    )


def _contexto_detalhe(autorizacao: AutorizacaoPedido, **extra) -> dict:
    return {"autorizacao": autorizacao, "pedido": autorizacao.pedido, **extra}


@login_required
def autorizacao(request, numero):
    """O pedido só para leitura (cabeçalho, materiais e quantidades pedidas) e a decisão."""
    _exigir_seguranca_do_trabalho(request.user)
    return render(request, "pedidos/autorizacao.html", _contexto_detalhe(_autorizacao(numero)))


@login_required
@require_POST
def decidir(request, numero):
    """Grava a decisão (`decisao` = autorizar ou recusar; `motivo` obrigatório na recusa)."""
    _exigir_seguranca_do_trabalho(request.user)
    decisao = request.POST.get("decisao", "")
    motivo = request.POST.get("motivo", "")
    resposta = decidir_autorizacao(
        numero,
        decisao,
        motivo,
        request.user,
        url_painel=request.build_absolute_uri(reverse("pedidos:painel")),
    )
    if resposta.ok:
        verbo = "autorizado" if decisao == "autorizar" else "recusado"
        messages.success(request, f"Pedido {numero} {verbo}.")
        return redirect("pedidos:autorizacao", numero=numero)
    if resposta.motivo == "grupo":
        raise PermissionDenied(resposta.mensagem)
    if resposta.motivo == "nao_encontrada":
        raise Http404(resposta.mensagem)
    if resposta.motivo == "ja_decidida":
        # Outra decisão chegou antes: mostra quem decidiu e quando, e nada muda.
        messages.warning(request, resposta.mensagem)
        return redirect("pedidos:autorizacao", numero=numero)
    # Recusa sem motivo, motivo comprido ou decisão inválida: volta ao detalhe com o erro.
    return render(
        request,
        "pedidos/autorizacao.html",
        _contexto_detalhe(_autorizacao(numero), mensagem=resposta.mensagem, motivo=motivo),
    )
