"""Cenário do formulário da oficina mecânica (spec 007), sobre `montar_cenario`.

Grupo da oficina: "Auto Peças" (o cadastro diz `AUTO PECAS`), com FILTRO (UN, saldo 4) e PNEU
(sem estoque). Avulso: ÓLEO (LT, saldo 20), do grupo `GERAL`. Fora da escolha: FITA (do AB) e o
resto do cenário. Destinos: OFICINA MECÂNICA e as viaturas do cenário, PICKUP 01 (ABC1D23) e
RETRO A (XYZ9K99).
"""

import time
from decimal import Decimal

from django.urls import reverse

from catalogo.models import Formulario, Material, Opcao
from pedidos.protecao import emitir
from tests.cenario import montar_cenario
from tests.config_cenario import excecao

FILTRO = "006.002.001"
PNEU = "006.000.001"
OLEO = "999.001.010"
FITA = "016.005.010"  # do AB, fora da escolha da oficina
OFICINA = "OFICINA MECÂNICA"
PICKUP = "PICKUP 01 — ABC1D23"
RETRO = "RETRO A — XYZ9K99"


def montar_oficina() -> None:
    montar_cenario()
    referencia = Material.objects.get(codigo=FITA)
    for codigo, nome, unidade, grupo, estoque in [
        (FILTRO, "FILTRO DE ÓLEO LUBRIFICANTE PSL55", "UN", "AUTO PECAS", "4"),
        (PNEU, "PNEU 12.5/80-R18", "UN", "AUTO PECAS", "0"),
        (OLEO, "ÓLEO LUBRIFICANTE 15W40", "LT", "GERAL", "20"),
    ]:
        Material.objects.update_or_create(
            codigo=codigo,
            defaults={
                "nome": nome,
                "unidade": unidade,
                "grupo": grupo,
                "estoque": Decimal(estoque),
                "estoque_em": referencia.estoque_em,
            },
        )
    Opcao.objects.get_or_create(lista=Opcao.Lista.GRUPO_OFICINA, valor="Auto Peças")
    # O avulso da oficina é uma exceção da configuração (spec 009), que acrescenta o óleo.
    excecao(Formulario.OFICINA, Material.objects.get(codigo=OLEO), True)


def enviar(client, itens, *, destino=OFICINA, solicitante="Marcos", token=None):
    """Envia o formulário da oficina como o navegador (HTMX), com o carrinho dado."""
    return client.post(
        reverse("pedidos:formulario", args=["oficina"]),
        {
            "token": (token or emitir(aberto_em=time.time() - 60)).token,
            "solicitante": solicitante,
            "destino": destino,
            "obs": "",
            "confirmacao_extra": "",
            "item_codigo": [c for c, _ in itens],
            "item_qtd": [q for _, q in itens],
        },
        HTTP_HX_REQUEST="true",
    )
