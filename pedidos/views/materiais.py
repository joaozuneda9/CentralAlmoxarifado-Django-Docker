"""Busca de materiais e carrinho via HTMX, comuns aos formulários públicos e à saída avulsa.

As views só devolvem trechos (`_resultados.html`, `_carrinho.html` e, nos formulários com folha,
`_folha.html`) e não guardam estado.
"""

import uuid
from dataclasses import replace

from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from pedidos import carrinho as carrinho_mod
from pedidos.fluxos import Fluxo, buscar, fluxo_publico, resultados
from pedidos.models import ItemPedido
from pedidos.regras import AVULSA
from pedidos.servicos import catalogo_de, item_catalogo_gravado


def urls_do_fluxo(fluxo: Fluxo) -> dict:
    if fluxo.publico:
        return {
            "url_materiais": reverse("pedidos:materiais", args=[fluxo.nome]),
            "url_carrinho": reverse("pedidos:carrinho", args=[fluxo.nome]),
        }
    return {
        "url_materiais": reverse("pedidos:avulsa_materiais"),
        "url_carrinho": reverse("pedidos:avulsa_carrinho"),
    }


def contexto_busca(fluxo: Fluxo, catalogo, q: str = "", filtro: str = "") -> dict:
    achados, total = buscar(fluxo, catalogo, q, filtro)
    return {"resultados": resultados(fluxo, achados), "total": total}


def _materiais(request, fluxo: Fluxo):
    catalogo = catalogo_de(fluxo.origem) or []
    contexto = {
        "fluxo": fluxo,
        **contexto_busca(fluxo, catalogo, request.GET.get("q", ""), request.GET.get("filtro", "")),
        **urls_do_fluxo(fluxo),
    }
    return render(request, "pedidos/_resultados.html", contexto)


def _item_da_edicao(post, fluxo: Fluxo, codigo: str, item):
    """Na edição de uma saída avulsa (o formulário leva `versao` e o `pedido`), quem já está na
    saída vale pelo que foi gravado: o teto é o maior entre o saldo e a quantidade gravada, como
    no envio (`servicos._limites_de_estoque`), e o material que saiu do catálogo segue aceito.
    Só na saída avulsa: os endpoints públicos não exigem login, e `versao` e `pedido` vêm do
    navegador, então não podem levantar o teto de um formulário público."""
    if fluxo.origem != AVULSA or "versao" not in post:
        return item
    gravado = ItemPedido.objects.filter(
        pedido__numero=post.get("pedido", ""), pedido__origem=AVULSA, codigo=codigo
    ).first()
    if gravado is None:
        return item
    if item is None:
        return item_catalogo_gravado(gravado)
    return replace(item, estoque=max(item.estoque, gravado.qtd_entregue or 0))


def _carrinho(request, fluxo: Fluxo):
    catalogo = catalogo_de(fluxo.origem) or []
    linhas = carrinho_mod.ler(request.POST, fluxo, catalogo, manter_ilegiveis=fluxo.publico)
    if "adicionar" in request.POST:
        codigo = request.POST["adicionar"]
        item = next((i for i in catalogo if i.codigo == codigo), None)
        resultado = carrinho_mod.adicionar(
            linhas, fluxo, item, request.POST.get(f"qtd-{codigo}", "")
        )
    elif "alterar" in request.POST:
        codigo = request.POST["alterar"]
        enviados = dict(
            zip(request.POST.getlist("item_codigo"), request.POST.getlist("item_qtd"), strict=False)
        )
        linhas = carrinho_mod.ler(
            request.POST,
            fluxo,
            catalogo,
            {codigo: request.POST.get("anterior", "")},
            manter_ilegiveis=fluxo.publico,
        )
        item = next((i for i in catalogo if i.codigo == codigo), None)
        item = _item_da_edicao(request.POST, fluxo, codigo, item)
        resultado = carrinho_mod.alterar(linhas, fluxo, item, enviados.get(codigo, ""))
    elif "remover" in request.POST:
        resultado = carrinho_mod.remover(linhas, request.POST["remover"])
    elif fluxo.folha is not None and "folha_abrir" in request.POST:
        return _folha(request, fluxo, catalogo, carrinho_mod.Carrinho(linhas))
    elif fluxo.folha is not None and "folha" in request.POST:
        digitado = {
            chave.removeprefix("folha-"): valor
            for chave, valor in request.POST.items()
            if chave.startswith("folha-")
        }
        resultado = carrinho_mod.aplicar_folha(linhas, fluxo, catalogo, digitado)
        if resultado.erros_folha or resultado.erro:
            # A folha volta para o diálogo, com o que foi digitado e os erros; o carrinho fica.
            resposta = _folha(request, fluxo, catalogo, resultado, digitado)
            resposta["HX-Retarget"] = "#folha-conteudo"
            resposta["HX-Reswap"] = "innerHTML"
            return resposta
    else:
        resultado = carrinho_mod.Carrinho(linhas)
    contexto = {
        "fluxo": fluxo,
        "carrinho": resultado,
        "codigos_erro": {linha.codigo for linha in resultado.linhas if linha.quantidade is None},
        # Na edição da saída avulsa o formulário leva a versão: o envio diz "Salvar alterações".
        "editando": "versao" in request.POST,
        **urls_do_fluxo(fluxo),
    }
    resposta = render(request, "pedidos/_carrinho.html", contexto)
    if "folha" in request.POST and fluxo.folha is not None:
        # O pedidos.js fecha o diálogo e anuncia quantas peças ficaram no pedido.
        resposta["HX-Trigger"] = "folha-aplicada"
    return resposta


def _folha(request, fluxo: Fluxo, catalogo, carrinho, digitado=None):
    """O conteúdo do diálogo da folha (spec 006): uma linha por peça, com a quantidade que ela tem
    no pedido ou, depois de uma recusa, a que foi digitada, e o erro de cada linha."""
    no_pedido = {linha.codigo: linha.texto for linha in carrinho.linhas}
    linhas = [
        {
            "r": r,
            "valor": digitado.get(r.item.codigo, "")
            if digitado is not None
            else (no_pedido.get(r.item.codigo, "")),
            "erro": carrinho.erros_folha.get(r.item.codigo, ""),
        }
        for r in resultados(fluxo, carrinho_mod.pecas_da_folha(fluxo, catalogo))
    ]
    contexto = {
        "fluxo": fluxo,
        "linhas": linhas,
        # Os ids dos campos mudam a cada desenho: com o mesmo id, o "settle" do HTMX 4 copiaria no
        # campo novo o valor do antigo, por cima do que o servidor devolveu.
        "desenho": uuid.uuid4().hex[:8],
        "n_erros": sum(1 for linha in linhas if linha["erro"]),
        "erro_geral": carrinho.erro,
        **urls_do_fluxo(fluxo),
    }
    return render(request, "pedidos/_folha.html", contexto)


@require_GET
def materiais(request, fluxo):
    return _materiais(request, fluxo_publico(fluxo))


@require_POST
def carrinho(request, fluxo):
    return _carrinho(request, fluxo_publico(fluxo))
