"""Quem pode alterar a configuração dos formulários (spec 009, FR-028 a FR-032).

Ver a página é de todo usuário do almoxarifado (a Segurança do Trabalho é barrada pelo middleware de
lista fechada). Alterar exige o critério do admin: `is_staff` mais a permissão do cadastro afetado.
Nenhum papel novo. O servidor recusa a gravação de quem não pode, qualquer que seja a tela.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied


def _pode(usuario, permissao: str) -> bool:
    return bool(
        usuario is not None
        and usuario.is_authenticated
        and usuario.is_staff
        and usuario.has_perm(permissao)
    )


def pode_alterar_centros(usuario) -> bool:
    """Habilitar e desabilitar centros por formulário, e ativar ou inativar centro."""
    return _pode(usuario, "catalogo.change_centrocusto")


def pode_criar_centros(usuario) -> bool:
    """Criar centro de custo (no admin, a partir da aba Centros de custo)."""
    return _pode(usuario, "catalogo.add_centrocusto")


def pode_alterar_materiais(usuario) -> bool:
    """Exceções de material (acrescentar, retirar, restaurar) e operações em lote."""
    return _pode(usuario, "catalogo.change_excecaomaterial")


def exige(pode):
    """Decorador de view: 403 para quem `pode(request.user)` recusa."""

    def decorador(view):
        @wraps(view)
        def envolvida(request, *args, **kwargs):
            if not pode(request.user):
                raise PermissionDenied("Sem permissão para alterar a configuração dos formulários.")
            return view(request, *args, **kwargs)

        return envolvida

    return decorador
