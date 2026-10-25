"""Itens da barra lateral da área do almoxarifado.

Cada subprojeto acrescenta seus destinos a `ITENS_MENU`. A barra só espelha o que cada rota
permite; quem decide o acesso continua sendo a própria rota.
"""

from dataclasses import dataclass

from django.urls import reverse

from contas.acesso import da_seguranca_trabalho


@dataclass(frozen=True)
class ItemMenu:
    rotulo: str
    rota: str
    icone: str = ""
    so_equipe: bool = False
    # Quem vê o item: o almoxarifado (os usuários de sempre) ou a Segurança do Trabalho (spec 008).
    para: str = "almoxarifado"


ITENS_MENU: tuple[ItemMenu, ...] = (
    ItemMenu("Painel", "pedidos:painel", "painel"),
    ItemMenu("Saída avulsa", "pedidos:avulsa", "saida"),
    ItemMenu("Automações", "automacoes:pagina", "robo"),
    ItemMenu("Curva ABC", "catalogo:curva", "grafico"),
    ItemMenu("Formulários", "catalogo:formularios", "caixa-check"),
    ItemMenu("Cadastros", "admin:index", "cadastros", so_equipe=True),
    ItemMenu("Autorizações", "pedidos:autorizacoes", "escudo", para="seguranca"),
)


def menu(request) -> dict:
    """Context processor: `menu` para usuário autenticado; nada para anônimo."""
    usuario = getattr(request, "user", None)  # ausente se o middleware de auth não rodou
    if usuario is None or not usuario.is_authenticated:
        return {}
    correspondencia = getattr(request, "resolver_match", None)
    atual = correspondencia.view_name if correspondencia else None
    seguranca = da_seguranca_trabalho(usuario)
    return {
        "menu": [
            {
                "rotulo": item.rotulo,
                "url": reverse(item.rota),
                "icone": item.icone,
                "atual": item.rota == atual,
            }
            for item in ITENS_MENU
            # A Segurança do Trabalho só vê o que é dela; os demais, o que viam, sem o dela.
            if (item.para == "seguranca") == seguranca
            and (seguranca or usuario.is_staff or not item.so_equipe)
        ],
        # A marca do menu leva ao ponto de partida de cada um: o painel, ou a fila de autorização.
        "menu_inicio": reverse("pedidos:autorizacoes" if seguranca else "pedidos:painel"),
    }
