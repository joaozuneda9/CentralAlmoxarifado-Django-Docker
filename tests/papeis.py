"""Papéis da área interna nos testes (spec 012).

Os grupos `Atendimento` e `Gestão` vêm da migration `contas/0004_papeis`, que roda também no banco
de teste. Um "usuário do almoxarifado" de teste tem os dois, como na implantação.
"""

from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from contas.acesso import GRUPO_ATENDIMENTO, GRUPO_GESTAO

TODOS = (GRUPO_ATENDIMENTO, GRUPO_GESTAO)


def _garantir_grupos() -> None:
    """Recria os dois grupos se faltam: o teste `transaction=True` esvazia o banco no fim, e o
    Django só recria as permissões (`post_migrate`), não os dados da `contas/0004_papeis`. Usa as
    funções da própria migration, para os grupos saírem iguais aos da implantação."""
    if Group.objects.filter(name__in=TODOS).count() == len(TODOS):
        return
    papeis = import_module("contas.migrations.0004_papeis")
    papeis.criar_grupos(apps, papeis.criar_permissoes(apps))


def _grupos(nomes) -> list[Group]:
    """Os grupos pedidos; um nome que não existe falha, em vez de dar menos papéis em silêncio."""
    _garantir_grupos()
    grupos = list(Group.objects.filter(name__in=nomes))
    faltam = set(nomes) - {g.name for g in grupos}
    assert not faltam, f"Grupos inexistentes: {sorted(faltam)}"
    return grupos


def dar_papeis(usuario, *nomes: str):
    """Põe o usuário nos grupos (os dois, sem nomes) e devolve o usuário."""
    usuario.groups.add(*_grupos(nomes or TODOS))
    return usuario


def usuario_com(*nomes: str, username: str = "12345", **campos):
    """Cria um usuário só com os papéis dados (sem nomes, nenhum papel)."""
    usuario = get_user_model().objects.create_user(username=username, password="x", **campos)
    if nomes:
        usuario.groups.add(*_grupos(nomes))
    return usuario
