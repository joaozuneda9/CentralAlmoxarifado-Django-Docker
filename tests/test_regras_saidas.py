"""Regras das saídas, situações e reenvio (casos de `tests/regras.test.cjs` do Apps Script)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from pedidos.regras import (
    AB,
    AVULSA,
    EM_LANCAMENTO,
    ERRO,
    LANCADA,
    LIMPEZA,
    NAO_LANCAR,
    PENDENTE,
    VERIFICAR,
    Centro,
    EnvioPedido,
    EnvioSaida,
    ItemEnviado,
    ItemSaida,
    atendimento_confere,
    cabecalho_enviado,
    cabecalho_saida,
    marcado_nao_lancar,
    registro_confere,
    resolver_centro_custo,
    situacao_pedido,
    situacao_scpi,
    validar_saida,
)
from tests.cenario import saida

CENTROS = [
    Centro("ETA II", "14", ""),
    Centro("OFICINA MECÂNICA", "20", ""),
    Centro("PICKUP 01", "31", "ABC1D23"),
    Centro("RETRO A", "41", "XYZ9K99"),
    Centro("RETRO B", "42", "XYZ9K99"),
]
HOJE = date(2026, 10, 9)
UM = (ItemSaida("023.001.002", 1),)


def textos(d, itens=UM, **ctx):
    r = validar_saida(d, list(itens), centros=CENTROS, hoje=HOJE, **ctx)
    return [e.texto for e in r.erros]


def test_saida_valida():
    assert textos(saida()) == []


def test_centro_e_placa_so_valem_se_estiverem_na_lista():
    assert textos(saida(centro_custo="INEXISTENTE")) == [
        'O centro de custo "INEXISTENTE" não está na lista.'
    ]
    assert textos(saida(placa="ZZZ0000")) == [
        "A placa ZZZ0000 não está na lista de centros de custo."
    ]


def test_placa_com_centro_proprio_prevalece_e_placa_em_dois_centros_e_recusada():
    r = validar_saida(saida(placa="abc-1d23"), list(UM), centros=CENTROS, hoje=HOJE)
    assert not r.erros and r.centro.codigo == "31" and r.centro.via_placa
    assert textos(saida(centro_custo="RETRO A", placa="XYZ9K99")) == [
        "Centro de custo: placa 'XYZ9K99' cadastrada em mais de um centro de custo."
    ]


def test_data_tipo_codigo_entrega_e_inteira():
    assert textos(saida(data="2026-10-10")) == ["A data da saída não pode ser futura."]
    assert textos(saida(data="2026-02-30")) == ["Informe a data efetiva da saída."]
    assert textos(saida(tipo="XPTO")) == ["Selecione o Tipo Saída do SCPI."]
    assert textos(saida(), [ItemSaida("23.1.2", 1)]) == [
        "Código '23.1.2' fora do padrão 000.000.000."
    ]
    assert textos(saida(), [ItemSaida("023.001.002", 0)]) == [
        "Informe ao menos um material com quantidade maior que zero."
    ]
    # A equipe aceita fração em qualquer unidade e em pedido de qualquer origem (spec 005).
    assert textos(saida(), [ItemSaida("023.001.002", Decimal("1.5"))]) == []
    assert textos(saida(), [ItemSaida("023.001.002", None), ItemSaida("023.001.003", 1)]) == [
        "Quantidade inválida para 023.001.002."
    ]


def test_tipos_da_lista_substituem_o_padrao():
    assert textos(saida(tipo="BALCÃO"), tipos=["BALCÃO"]) == []
    assert textos(saida(tipo="ENTREGA"), tipos=["BALCÃO"]) == ["Selecione o Tipo Saída do SCPI."]


def test_catalogo_da_avulsa():
    catalogo = {"023.001.002": SimpleNamespace(duplicado=True)}
    assert textos(saida(), [ItemSaida("000.000.001", 1)], catalogo=catalogo) == [
        "Material 000.000.001 não encontrado no cadastro."
    ]
    assert textos(saida(), catalogo=catalogo) == [
        "Material 023.001.002 está com cadastro duplicado."
    ]


def test_resolver_centro_custo():
    r = resolver_centro_custo("", "AAA0000", CENTROS)
    assert (r.descricao, r.codigo, r.via_placa) == ("OFICINA MECÂNICA", "20", False)
    assert resolver_centro_custo("", "", CENTROS).erro == "'Centro de Custo' vazio"
    assert (
        resolver_centro_custo("Lua", "", CENTROS).erro
        == "centro de custo 'Lua' não existe no cadastro de centros de custo"
    )
    assert resolver_centro_custo("eta  ii", "", CENTROS).codigo == "14"


def L(status=PENDENTE, requisicao=""):
    return SimpleNamespace(status=status, requisicao_scpi=requisicao)


def test_situacao_scpi():
    sem = situacao_scpi([])
    assert (sem.chave, sem.rotulo) == ("sem", "Aguarda o atendimento")
    assert situacao_scpi([L(), L()]).chave == "aguardando"
    assert situacao_scpi([L(), L()]).desc == "Saídas registradas, ainda sem número oficial do SCPI."
    assert situacao_scpi([L(LANCADA, "003354/26"), L()]).rotulo == "Parcial 003354/26"
    dois = situacao_scpi([L(LANCADA, "003354/26"), L(LANCADA, "003355/26")])
    assert (dois.chave, dois.rotulo) == ("lancado", "Lançado 003354/26, 003355/26")
    assert dois.desc == "Itens lançados em requisições diferentes do SCPI."
    um = situacao_scpi([L(LANCADA, "003400/26"), L(LANCADA, "003400/26")])
    assert um.numeros == ("003400/26",) and um.desc == "Todos os itens confirmados pelo robô."
    for linhas in ([L(VERIFICAR), L(LANCADA, "1/26")], [L(EM_LANCAMENTO)]):
        s = situacao_scpi(linhas)
        assert (s.chave, s.rotulo) == ("atencao", "Verificar no SCPI")
    erro = situacao_scpi([L(ERRO)])
    assert (erro.chave, erro.rotulo) == ("atencao", "Erro no lançamento")
    assert situacao_scpi([L(NAO_LANCAR)]).rotulo == "Não será lançado"
    assert situacao_scpi([L(NAO_LANCAR), L(LANCADA, "1/26")]).chave == "lancado"
    assert situacao_scpi([L(PENDENTE, "9/26")]).chave == "lancado"


def I(pedida, entregue, id=None):  # noqa: E743
    return SimpleNamespace(
        id=id,
        origem="PEDIDO",
        qtd_pedida=Decimal(pedida),
        qtd_entregue=entregue,
        no_lugar_de_id=None,
    )


def X(entregue, no_lugar_de_id=None):
    """Item acrescentado pelo almoxarifado (sem quantidade pedida)."""
    return SimpleNamespace(
        id=None,
        origem="ALMOXARIFADO",
        qtd_pedida=None,
        qtd_entregue=entregue,
        no_lugar_de_id=no_lugar_de_id,
    )


def test_situacao_pedido():
    assert situacao_pedido(AVULSA, True, []).chave == "atendido"
    assert situacao_pedido(AVULSA, True, []).rotulo == "Atendido"
    assert situacao_pedido(LIMPEZA, False, [I(2, None)]).chave == "aguardando"
    assert situacao_pedido(LIMPEZA, True, [I(2, Decimal(2))]).chave == "atendido"
    assert situacao_pedido(AB, True, [I(2, Decimal(1))]).rotulo == "Atendido parcialmente"
    assert situacao_pedido(AB, True, [I(2, None)]).chave == "parcial"


def test_situacao_pedido_com_troca():
    # Item pedido em 0, trocado por um acrescentado entregue: atendido.
    assert situacao_pedido(AB, True, [I(2, Decimal(0), id=7), X(Decimal(1), 7)]).chave == "atendido"
    # O acrescentado entregue 0 não substitui nada: parcial.
    assert situacao_pedido(AB, True, [I(2, Decimal(0), id=7), X(Decimal(0), 7)]).chave == "parcial"
    # Item abaixo sem troca: parcial, mesmo com acrescentado de outro item.
    itens = [I(2, Decimal(1), id=7), I(1, Decimal(0), id=8), X(Decimal(1), 8)]
    assert situacao_pedido(AB, True, itens).chave == "parcial"
    # Só acrescentados a mais e pedidos completos: atendido.
    assert situacao_pedido(AB, True, [I(2, Decimal(2), id=7), X(Decimal(3))]).chave == "atendido"
    assert situacao_pedido(AB, True, [I(2, Decimal(2), id=7), X(None)]).chave == "atendido"


def envio_ab(q="2", **extra):
    campos = {
        "solicitante": "Maria",
        "destino": "ETA II",
        "itens": (ItemEnviado("001.000.010", q),),
    }
    campos.update(extra)
    return EnvioPedido(**campos)


def test_reenvio_confere():
    gravado = ("Maria", "ETA II", "", "")  # nome, destino, observação, ocorrência
    itens = [("001.000.010", Decimal(2))]
    assert registro_confere(AB, gravado, itens, envio_ab()) is True
    assert registro_confere(AB, gravado, itens, envio_ab("3")) is False
    assert registro_confere(AB, gravado, itens, envio_ab(destino="ETA I")) is False
    assert registro_confere(AB, gravado, [], envio_ab()) is False
    assert registro_confere(AB, gravado, itens, envio_ab("x")) is False
    limpeza = EnvioPedido(
        solicitante="Ana",
        destino="ETA III",
        itens=(ItemEnviado("023.001.002", "1,5"),),
    )
    assert registro_confere(
        LIMPEZA, ("Ana", "ETA III", "", ""), [("023.001.002", Decimal("1.500"))], limpeza
    )


def test_avulsa_compara_dados_da_saida_e_nao_lancar():
    dados = saida(placa="abc-1d23", obs="x")
    envio = EnvioSaida(dados, (ItemEnviado("023.001.002", "1"),))
    gravado = cabecalho_saida(saida(placa="ABC1D23", obs="x"), False)
    itens = [("023.001.002", Decimal(1))]
    assert cabecalho_enviado(AVULSA, envio) == gravado
    assert registro_confere(AVULSA, gravado, itens, envio)
    for mudado in (
        EnvioSaida(saida(placa="", obs="x"), envio.itens),
        EnvioSaida(saida(placa="abc-1d23", obs="y"), envio.itens),
        EnvioSaida(dados, envio.itens, nao_lancar=True),
    ):
        assert not registro_confere(AVULSA, gravado, itens, mudado)


def test_atendimento_confere():
    gravado = cabecalho_saida(saida(), False)
    entregues = {"023.001.002": Decimal(2), "008.001.002": Decimal(0)}
    qtds = {"023.001.002": 2, "008.001.002": 0}
    assert atendimento_confere(gravado, entregues, saida(), False, qtds)
    assert not atendimento_confere(gravado, entregues, saida(), False, {**qtds, "023.001.002": 1})
    assert not atendimento_confere(gravado, entregues, saida(recebedor="Carla"), False, qtds)


def test_marcado_nao_lancar():
    assert marcado_nao_lancar("Fora de estoque")
    assert marcado_nao_lancar("não lançar")
    assert not marcado_nao_lancar("lançar amanhã")


def test_situacao_pedido_com_autorizacao_da_seguranca_do_trabalho():
    # Aguardando ou recusada vale por cima de tudo; sem autorização, a regra de sempre.
    aguardando = situacao_pedido("EPIS", False, [I(2, None)], "AGUARDANDO")
    assert (aguardando.chave, aguardando.rotulo) == (
        "aguardando_autorizacao",
        "Aguardando autorização",
    )
    recusado = situacao_pedido("EPIS", False, [I(2, None)], "RECUSADO")
    assert (recusado.chave, recusado.rotulo) == ("recusado", "Recusado")
    # Autorizado segue a regra do atendimento.
    assert situacao_pedido("EPIS", False, [I(2, None)], "AUTORIZADO").chave == "aguardando"
    assert situacao_pedido("EPIS", True, [I(2, Decimal(2))], "AUTORIZADO").chave == "atendido"
    assert situacao_pedido("EPIS", True, [I(2, Decimal(1))], "AUTORIZADO").chave == "parcial"
    # None (formulário sem autorização) não muda nada.
    assert situacao_pedido(AB, False, [I(2, None)], None).chave == "aguardando"
