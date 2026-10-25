"""Recarga de uma região da página pelo HTMX: a view devolve só o parcial do alvo pedido."""

from django.shortcuts import render
from django.utils.cache import patch_vary_headers

# Os cabeçalhos que `regiao_pedida` lê: a resposta varia com eles, para um cache nunca servir o
# parcial no lugar da página.
CABECALHOS_DA_REGIAO = ["HX-Request", "HX-Target", "HX-History-Restore-Request"]


def regiao_pedida(request, regioes: dict):
    """O valor de `regioes` para o alvo do pedido (`HX-Target`, `tag#id` no HTMX 4), ou None quando
    é a página inteira: sem HX-Request, alvo desconhecido ou restauração do histórico (o botão
    Voltar também manda HX-Request, mas precisa da página inteira)."""
    if not request.headers.get("HX-Request") or request.headers.get("HX-History-Restore-Request"):
        return None
    return regioes.get(request.headers.get("HX-Target", ""))


def render_regiao(request, modelo: str, contexto: dict):
    """`render` com o Vary dos cabeçalhos de `regiao_pedida`."""
    resposta = render(request, modelo, contexto)
    patch_vary_headers(resposta, CABECALHOS_DA_REGIAO)
    return resposta
