"""Cenário do formulário de reposição de peças das viaturas (spec 006), sobre `montar_cenario`.

Lista: TUBO (M, fora do AB), FITA (UN, no AB), BOTINA (UN, saldo 2,5) e LUVA (sem estoque).
Só no AB, fora da lista: ISOLANTE. Destino: "EQUIPE NORTE", com duas linhas (uma por placa), uma
só habilitada nas viaturas (spec 009).
"""

from decimal import Decimal

from django.utils import timezone

from catalogo.models import CentroCusto, Formulario, Material, PecaViatura, SaidaSCPI
from tests.cenario import montar_cenario
from tests.config_cenario import enviar_formulario, habilitar

TUBO = "016.020.001"
FITA = "016.005.010"
BOTINA = "013.006.001"
LUVA = "013.005.007"
ISOLANTE = "016.030.001"  # no AB (tem saídas), fora da lista
EQUIPE = "EQUIPE NORTE"


def montar_viaturas() -> None:
    montar_cenario()
    referencia = Material.objects.get(codigo=FITA)
    Material.objects.update_or_create(
        codigo=TUBO,
        defaults={
            "nome": "TUBO PVC 3/4 SOLDÁVEL",
            "unidade": "M",
            "grupo": "REDES DE ÁGUA",
            "estoque": Decimal("12.5"),
            "estoque_em": referencia.estoque_em,
        },
    )
    Material.objects.update_or_create(
        codigo=ISOLANTE,
        defaults={
            "nome": "FITA ISOLANTE",
            "unidade": "UN",
            "grupo": "ELÉTRICA",
            "estoque": Decimal("5"),
            "estoque_em": referencia.estoque_em,
        },
    )
    SaidaSCPI.objects.update_or_create(
        id_requi=f"T0-{ISOLANTE}",
        cadpro=ISOLANTE,
        defaults={"data": timezone.localdate(), "qtd": Decimal(1), "valor": Decimal(1)},
    )
    for ordem, (codigo, nome) in enumerate(
        [(TUBO, "Tubo PVC 3/4 Soldável Marrom (metro)"), (FITA, ""), (BOTINA, ""), (LUVA, "")]
    ):
        PecaViatura.objects.update_or_create(
            material=Material.objects.get(codigo=codigo),
            defaults={"ordem": ordem, "nome_exibido": nome},
        )
    if not CentroCusto.objects.filter(descricao=EQUIPE).exists():
        linhas = [
            CentroCusto.objects.create(descricao=EQUIPE, codigo="51", placa="AAA1A11"),
            CentroCusto.objects.create(descricao=EQUIPE, codigo="51", placa="BBB2B22"),
        ]
        # Como antes: todo centro é destino de limpeza, AB e EPIs; só uma linha, das viaturas.
        habilitar(linhas, Formulario.LIMPEZA, Formulario.AB, Formulario.EPIS)
        habilitar(linhas[1], Formulario.VIATURAS)


def enviar(client, itens, *, destino=EQUIPE, ocorrencia="", solicitante="Carlos", token=None):
    """Envia o formulário de viaturas como o navegador (HTMX), com o carrinho dado."""
    return enviar_formulario(
        client,
        "viaturas",
        itens,
        destino=destino,
        solicitante=solicitante,
        token=token,
        ocorrencia=ocorrencia,
    )
