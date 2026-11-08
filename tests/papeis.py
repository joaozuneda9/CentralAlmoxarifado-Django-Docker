"""Papéis da área interna nos testes (spec 012).

Os grupos `Atendimento` e `Gestão` vêm da migration `contas/0004_papeis`, que roda também no banco
de teste. Um "usuário do almoxarifado" de teste tem os dois, como na implantação.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from contas.acesso import GRUPO_ATENDIMENTO, GRUPO_GESTAO

TODOS = (GRUPO_ATENDIMENTO, GRUPO_GESTAO)


def dar_papeis(usuario, *nomes: str):
    """Põe o usuário nos grupos (os dois, sem nomes) e devolve o usuário."""
    usuario.groups.add(*Group.objects.filter(name__in=nomes or TODOS))
    return usuario


def usuario_com(*nomes: str, username: str = "12345", **campos):
    """Cria um usuário só com os papéis dados (sem nomes, nenhum papel)."""
    usuario = get_user_model().objects.create_user(username=username, password="x", **campos)
    if nomes:
        usuario.groups.add(*Group.objects.filter(name__in=nomes))
    return usuario
