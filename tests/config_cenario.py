"""Auxiliares dos testes da configuração das opções por formulário (spec 009).

Independente de `tests/cenario.py` (que o importa para habilitar os centros do cenário padrão).
"""

import time
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.utils import timezone

from catalogo.models import CentroCusto, CentroFormulario, ExcecaoMaterial, Material
from contas.acesso import GRUPO_SEGURANCA_TRABALHO
from pedidos.protecao import emitir
from pedidos.regras import (
    AB,
    CENTRO_OFICINA,
    EPIS,
    LIMPEZA,
    OFICINA,
    VIATURAS,
    EnvioPedido,
    ItemEnviado,
    norm_u,
)
from pedidos.servicos import registrar_pedido


def habilitar(centros, *formularios, usuario=None) -> None:
    """Habilita as linhas de centro nos formulários (idempotente; as que faltam, num insert só)."""
    if isinstance(centros, CentroCusto):
        centros = [centros]
    centros = list(centros)
    feitos = {
        (centro_id, str(formulario))
        for centro_id, formulario in CentroFormulario.objects.filter(
            centro__in=centros, formulario__in=formularios
        ).values_list("centro_id", "formulario")
    }
    novos = []
    for centro in centros:
        for formulario in formularios:
            if (centro.pk, str(formulario)) not in feitos:
                feitos.add((centro.pk, str(formulario)))
                novos.append(
                    CentroFormulario(centro=centro, formulario=formulario, alterado_por=usuario)
                )
    CentroFormulario.objects.bulk_create(novos)


def criar_centro(descricao, codigo, placa=None, *, formularios=(), ativo=True) -> CentroCusto:
    """Cria a linha do cadastro e a habilita nos formulários dados (nenhum, por padrão: é o que
    acontece com um centro novo)."""
    centro = CentroCusto.objects.create(
        descricao=descricao, codigo=codigo, placa=placa, ativo=ativo
    )
    habilitar(centro, *formularios)
    return centro


def habilitar_como_antes() -> None:
    """Habilita os centros do cadastro como as regras antigas ofereciam (para os testes de
    comportamento que existiam antes da configuração não mudarem): todos em limpeza, AB e EPIs; na
    oficina, o centro OFICINA MECÂNICA (a primeira linha sem placa) e as linhas com placa; nas
    viaturas, os marcados como equipe de manutenção (a marca antiga, ainda gravada nos testes
    de transição)."""
    todos = list(CentroCusto.objects.all())
    habilitar(todos, LIMPEZA, AB, EPIS)
    oficina = [
        c
        for c in CentroCusto.objects.filter(placa__isnull=True).order_by("codigo")
        if norm_u(c.descricao) == norm_u(CENTRO_OFICINA)
    ][:1]
    habilitar(oficina + list(CentroCusto.objects.filter(placa__isnull=False)), OFICINA)
    habilitar(CentroCusto.objects.filter(equipe_manutencao=True), VIATURAS)


def material(codigo, nome, grupo="", *, estoque="10", oculto=False, unidade="UN") -> Material:
    """Cria (ou atualiza) um material com saldo importado."""
    obj, _ = Material.objects.update_or_create(
        codigo=codigo,
        defaults={
            "nome": nome,
            "unidade": unidade,
            "grupo": grupo,
            "subgrupo": "SUB",
            "oculto": oculto,
            "duplicado": False,
            "estoque": Decimal(estoque),
            "estoque_em": timezone.now(),
        },
    )
    return obj


def excecao(formulario, mat, habilitado, usuario=None) -> ExcecaoMaterial:
    return ExcecaoMaterial.objects.update_or_create(
        material=mat,
        formulario=formulario,
        defaults={"habilitado": habilitado, "alterado_por": usuario},
    )[0]


def codigos(itens) -> list[str]:
    return [i.codigo for i in itens or []]


def usuarios() -> dict:
    """Os usuários do cenário (idempotente): superusuário, staff só com a permissão de centros,
    staff só com a de materiais, staff sem permissão, almoxarifado comum e Segurança do Trabalho."""
    modelo = get_user_model()

    def criar(matricula, **extra):
        return modelo.objects.get_or_create(username=matricula, defaults=extra)[0]

    def permissao(usuario, codename):
        usuario.user_permissions.add(Permission.objects.get(codename=codename))

    admin = criar("80001", is_staff=True, is_superuser=True)
    centros = criar("80002", is_staff=True)
    permissao(centros, "change_centrocusto")
    materiais = criar("80003", is_staff=True)
    permissao(materiais, "change_excecaomaterial")
    staff = criar("80004", is_staff=True)
    comum = criar("80005")
    seguranca = criar("80006")
    seguranca.groups.add(Group.objects.get_or_create(name=GRUPO_SEGURANCA_TRABALHO)[0])
    return {
        "admin": admin,
        "so_centros": centros,
        "so_materiais": materiais,
        "staff": staff,
        "comum": comum,
        "seguranca": seguranca,
    }


def enviar_formulario(
    client, formulario, itens, *, destino, solicitante="Marcos Pereira", token=None, **campos
):
    """Envia o formulário público como o navegador (HTMX), com o carrinho dado. `campos` troca ou
    acrescenta campos do POST (`obs`, `ocorrencia`, `confirmacao_extra`)."""
    dados = {
        "token": (emitir(aberto_em=time.time() - 60) if token is None else token).token,
        "solicitante": solicitante,
        "destino": destino,
        "obs": "",
        "confirmacao_extra": "",
        "item_codigo": [c for c, _ in itens],
        "item_qtd": [q for _, q in itens],
        **campos,
    }
    return client.post(
        reverse("pedidos:formulario", args=[formulario.lower()]), dados, HTTP_HX_REQUEST="true"
    )


def registrar(origem, itens, *, destino, solicitante="Marcos Pereira"):
    """Registra pelo serviço (sem passar pela tela) e devolve a `Resposta`."""
    return registrar_pedido(
        origem,
        uuid.uuid4(),
        EnvioPedido(
            solicitante=solicitante,
            destino=destino,
            itens=tuple(ItemEnviado(c, q) for c, q in itens),
        ),
    )
