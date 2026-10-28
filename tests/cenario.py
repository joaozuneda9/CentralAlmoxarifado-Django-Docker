"""Cenário de teste dos pedidos (os dados de `tests/cenario.cjs` do Apps Script).

Módulo comum, sem pytest: também serve para preparar o banco local na conferência visual
(`uv run python manage.py shell -c "from tests.cenario import montar_cenario; montar_cenario()"`).
"""

import threading
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from catalogo.models import CentroCusto, ItemLimpeza, Material, Opcao, SaidaSCPI
from pedidos.models import Atendimento, ItemPedido, LinhaSaida, Pedido
from pedidos.regras import AVULSA, LIMPEZA, DadosSaida, EnvioPedido, ItemEnviado
from tests.config_cenario import habilitar_como_antes

MATERIAIS = [
    # código, nome, grupo, estoque, oculto
    # Os itens de limpeza têm saldo: o formulário público nega pedido acima do estoque.
    ("023.001.002", "DETERGENTE NEUTRO", "LIMPEZA", "100", False),
    ("008.001.002", "CAFÉ 500 G", "GÊNEROS", "100", False),
    ("023.004.001", "PAPEL HIGIÊNICO", "LIMPEZA", "50", False),
    ("016.005.010", "FITA VEDA ROSCA", "REDES DE ÁGUA", "10", False),
    ("013.006.001", "BOTINA", "EPI", "2.5", False),
    ("013.005.007", "LUVA NITRÍLICA", "EPI", "0", False),
    ("000.000.900", "ITEM ANTIGO", "GERAL", "0", False),
    ("030.004.001", "CAPACETE", "EPI", "9", True),
]
UNIDADES_FRACIONAVEIS = ("M", "MT", "MTS", "KM", "KG", "L", "LT", "M²", "M³", "T")
# Unidade do SCPI de cada material (o resto é "UN", contado). O café é vendido a peso: é a
# unidade de medida dos pedidos de limpeza com fração (1,5).
UNIDADES = {"008.001.002": "KG"}
SAIDAS = {
    "016.005.010": 3,
    "013.006.001": 2,
    "013.005.007": 1,
    "000.000.900": 1,
    "030.004.001": 1,
    "023.004.001": 1,
}


def montar_cenario(*, com_estoque: bool = True) -> None:
    """Listas, materiais, itens de limpeza, saídas do SCPI e centros de custo (idempotente)."""
    opcoes = {
        Opcao.Lista.FUNCIONARIO: ["Ana Exemplo", "João Fictício", "Motorista Teste"],
        Opcao.Lista.CATEGORIA_LIMPEZA: ["Limpeza", "Copa/cozinha"],
        # A migration carrega estas unidades, mas o teste com `transaction=True` esvazia as
        # tabelas ao terminar: quem monta o cenário garante a lista (idempotente).
        Opcao.Lista.UNIDADE_FRACIONAVEL: list(UNIDADES_FRACIONAVEIS),
    }
    _gravar(
        Opcao,
        Opcao.objects.filter(lista__in=opcoes),
        lambda o: (o.lista, o.valor),
        {
            (lista, valor): {"lista": lista, "valor": valor, "ordem": ordem, "ativo": True}
            for lista, valores in opcoes.items()
            for ordem, valor in enumerate(valores)
        },
    )
    agora = timezone.now() if com_estoque else None
    codigos = [codigo for codigo, *_ in MATERIAIS]
    _gravar(
        Material,
        Material.objects.filter(codigo__in=codigos),
        lambda m: m.codigo,
        {
            codigo: {
                "codigo": codigo,
                "nome": nome,
                "unidade": UNIDADES.get(codigo, "UN"),
                "grupo": grupo,
                "subgrupo": "SUB",
                "oculto": oculto,
                "duplicado": False,
                "estoque": Decimal(estoque),
                "estoque_em": agora,
            }
            for codigo, nome, grupo, estoque, oculto in MATERIAIS
        },
    )
    materiais = {m.codigo: m for m in Material.objects.filter(codigo__in=codigos)}
    limpeza = [
        ("023.001.002", "Limpeza", ""),
        ("008.001.002", "Copa/cozinha", "Pacote 500 g"),
        ("023.004.001", "Limpeza", ""),
    ]
    _gravar(
        ItemLimpeza,
        ItemLimpeza.objects.filter(material__in=materiais.values()),
        lambda i: i.material_id,
        {
            materiais[codigo].pk: {
                "material": materiais[codigo],
                "categoria": categoria,
                "unidade_exibida": unidade,
                "ordem": ordem,
            }
            for ordem, (codigo, categoria, unidade) in enumerate(limpeza)
        },
    )
    _gravar(
        SaidaSCPI,
        SaidaSCPI.objects.filter(cadpro__in=SAIDAS),
        lambda s: (s.id_requi, s.cadpro),
        {
            (f"T{n}-{codigo}", codigo): {
                "id_requi": f"T{n}-{codigo}",
                "cadpro": codigo,
                "data": timezone.localdate(),
                "qtd": Decimal(1),
                "valor": Decimal(1),
            }
            for codigo, vezes in SAIDAS.items()
            for n in range(vezes)
        },
    )
    centros = [
        ("ETA I", "12", None),
        ("ETA II", "14", None),
        ("Elevatória", "16", None),
        ("OFICINA MECÂNICA", "20", None),
        ("PICKUP 01", "31", "ABC1D23"),
        ("RETRO A", "41", "XYZ9K99"),
    ]
    existentes = set(CentroCusto.objects.values_list("descricao", "codigo"))
    for descricao, codigo, placa in centros:
        if (descricao, codigo) not in existentes:
            # `create` um a um: o `save` do centro normaliza a placa.
            CentroCusto.objects.create(descricao=descricao, codigo=codigo, placa=placa)
    # Os centros do cenário são destino onde as regras antigas os ofereciam (spec 009).
    habilitar_como_antes()


def _gravar(modelo, existentes, chave, linhas: dict) -> None:
    """`update_or_create` em lote: `linhas` vai da chave aos campos; as linhas que já existem
    (o cenário montado de novo) são atualizadas e as que faltam, criadas num insert só."""
    atuais = {chave(obj): obj for obj in existentes}
    novos = []
    for k, campos in linhas.items():
        obj = atuais.get(k)
        if obj is None:
            novos.append(modelo(**campos))
            continue
        for campo, valor in campos.items():
            setattr(obj, campo, valor)
        obj.save()
    modelo.objects.bulk_create(novos)


def dar_saldo(*codigos: str, saldo: int = 10) -> None:
    """Dá saldo a materiais do cenário que vêm zerados: a saída avulsa só lista material com
    estoque."""
    Material.objects.filter(codigo__in=codigos).update(estoque=Decimal(saldo))


def itens(*pares) -> tuple[ItemEnviado, ...]:
    return tuple(ItemEnviado(c, q) for c, q in pares)


def textos(resposta) -> list[str]:
    """Os textos dos erros de uma `Resposta` (ou de um resultado de validação)."""
    return [e.texto for e in resposta.erros]


def envio_limpeza(**extra) -> EnvioPedido:
    campos = {
        "solicitante": "Ana",
        "destino": "ETA II",
        "itens": itens(("023.001.002", "2"), ("008.001.002", "1,5")),
    }
    campos.update(extra)
    return EnvioPedido(**campos)


def envio_ab(**extra) -> EnvioPedido:
    campos = {
        "solicitante": "Bruno",
        "destino": "Elevatória",
        "itens": itens(("016.005.010", "3")),
    }
    campos.update(extra)
    return EnvioPedido(**campos)


def saida(**extra) -> DadosSaida:
    campos = {
        "data": "2026-10-09",
        "recebedor": "João",
        "centro_custo": "ETA II",
        "tipo": "BALCÃO",
        "placa": "",
    }
    campos.update(extra)
    return DadosSaida(**campos)


def registrar(origem, envio, **kw):
    """`registrar_pedido` com um identificador novo. Nos testes, o TELEGRAM_* vazio faz o
    aviso dar "sem_configuracao" sem acessar a rede."""
    from pedidos.servicos import registrar_pedido

    return registrar_pedido(origem, uuid.uuid4(), envio, **kw)


def criar_pedido(
    *,
    ip=None,
    solicitante="Ana",
    criado_em=None,
    origem=LIMPEZA,
    numero=None,
    itens=(("023.001.002", "2"),),
    atendido=False,
    entregues=None,
    linhas=(),
    usuario=None,
    recebedor="João",
):
    """Pedido gravado direto pelo ORM (sem passar pelas regras), para montar cenários.

    Com `atendido`, grava o atendimento (entregues iguais aos pedidos, salvo `entregues`) e
    uma `LinhaSaida` do primeiro item para cada par (status, requisição) de `linhas`."""
    from pedidos.servicos import proximo_numero, travar_sequencia

    if numero is None:
        with transaction.atomic():
            numero = proximo_numero(travar_sequencia(), origem)
    pedido = Pedido.objects.create(
        id=uuid.uuid4(),
        numero=numero,
        origem=origem,
        ip=ip,
        solicitante=solicitante,
        destino="ETA II",
        criado_em=criado_em or timezone.now(),
        registrado_por=usuario if origem == AVULSA else None,
    )
    entregues = entregues or [None] * len(itens)
    criados = [
        ItemPedido.objects.create(
            pedido=pedido,
            codigo=codigo,
            material=f"MATERIAL {codigo}",
            unidade="UN",
            qtd_pedida=Decimal(qtd.replace(",", ".")),
            qtd_entregue=(Decimal((entregue or qtd).replace(",", ".")) if atendido else None),
        )
        for (codigo, qtd), entregue in zip(itens, entregues, strict=True)
    ]
    if atendido:
        if usuario is None:
            usuario, _ = get_user_model().objects.get_or_create(username="00099")
        atendimento = Atendimento.objects.create(
            id=uuid.uuid4(),
            pedido=pedido,
            data_efetiva=timezone.localdate(),
            recebedor=recebedor,
            centro_custo="ETA II",
            tipo_saida="BALCÃO",
            atendido_por=usuario,
        )
        for seq, (status, requisicao) in enumerate(linhas, start=1):
            LinhaSaida.objects.create(
                atendimento=atendimento,
                seq=seq,
                data=atendimento.data_efetiva,
                qtd=criados[0].qtd_pedida,
                codigo=criados[0].codigo,
                descricao=criados[0].material,
                recebedor=recebedor,
                centro_custo="ETA II",
                tipo_saida="BALCÃO",
                lote=numero,
                status=status,
                requisicao_scpi=requisicao,
            )
    return pedido


def em_paralelo(*funcoes) -> list:
    """Roda as funções ao mesmo tempo (uma thread e uma conexão cada) e devolve os resultados."""
    barreira = threading.Barrier(len(funcoes))
    resultados: list = [None] * len(funcoes)
    erros: list = []

    def rodar(i, funcao):
        try:
            barreira.wait()
            resultados[i] = funcao()
        except Exception as exc:  # repassado ao teste
            erros.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=rodar, args=(i, f)) for i, f in enumerate(funcoes)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    if erros:
        raise erros[0]
    return resultados
