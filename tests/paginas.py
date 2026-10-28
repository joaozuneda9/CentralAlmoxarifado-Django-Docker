"""Leitura do HTML das respostas nos testes das telas."""

import re


def texto(html):
    """O texto visível da página, sem as tags e com os espaços juntados."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def item_atual(html, url, rotulo):
    """O item do menu marcado como a página atual (`aria-current`)."""
    return re.search(
        rf'<a class="app-menu-item" href="{re.escape(url)}" aria-current="page">'
        rf'<svg class="icone".*?</svg><span>{rotulo}</span></a>',
        html,
        re.S,
    )
