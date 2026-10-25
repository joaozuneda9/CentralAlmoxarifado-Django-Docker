import uuid
from decimal import Decimal
from urllib.error import URLError

import pytest

from catalogo.models import CentroCusto
from pedidos import servicos
from pedidos.models import ItemPedido, Pedido, Sequencia
from pedidos.regras import AB, LIMPEZA
from pedidos.servicos import catalogo_de, mensagem_divergente, registrar_pedido
from tests.cenario import em_paralelo, envio_ab, envio_limpeza, itens, montar_cenario

pytestmark = pytest.mark.django_db


@pytest.fixture
def avisos(monkeypatch):
    enviados = []

    def falso(pedido, url_painel=""):
        enviados.append(pedido.numero)
        return "enviado"

    monkeypatch.setattr(servicos, "notificar_pedido", falso)
    return enviados


def test_ab_do_cenario():
    montar_cenario()
    assert [f"{m.codigo}:{m.disponivel}" for m in catalogo_de(AB)] == [
        "016.005.010:10",
        "013.006.001:2",
        "013.005.007:0",
    ]


def test_pedido_de_limpeza_grava_pedido_e_itens(django_capture_on_commit_callbacks, avisos):
    montar_cenario()
    with django_capture_on_commit_callbacks(execute=True):
        r = registrar_pedido(LIMPEZA, uuid.uuid4(), envio_limpeza(), ip="10.0.0.1")
    assert (r.ok, r.numero, r.telegram) == (True, "P-000001", "enviado")
    p = Pedido.objects.get()
    assert (p.origem, p.ip, p.destino, p.solicitante) == ("LIMPEZA", "10.0.0.1", "ETA II", "Ana")
    assert [(i.codigo, i.qtd_pedida) for i in p.itens.all()] == [
        ("023.001.002", Decimal("2")),
        ("008.001.002", Decimal("1.5")),
    ]
    assert p.itens.all()[1].unidade == "Pacote 500 g"
    assert p.itens.all()[1].categoria == "Copa/cozinha"
    assert avisos == ["P-000001"]


def test_destino_fora_dos_centros_de_custo_e_recusado_nos_dois_formularios():
    montar_cenario()
    for origem, envio in (
        (LIMPEZA, envio_limpeza(destino="Portaria")),
        (AB, envio_ab(destino="eta ii")),
    ):
        r = registrar_pedido(origem, uuid.uuid4(), envio)
        assert not r.ok
        assert [e.texto for e in r.erros] == [
            f'Destino "{envio.destino}" não está na lista de centros de custo.'
        ]
    assert not Pedido.objects.exists()


def test_destino_com_placa_grava_o_centro_e_a_placa():
    montar_cenario()
    r = registrar_pedido(AB, uuid.uuid4(), envio_ab(destino="PICKUP 01 — ABC1D23"))
    assert r.ok and Pedido.objects.get().destino == "PICKUP 01 — ABC1D23"


def test_sem_centros_de_custo_nao_ha_destino_possivel():
    montar_cenario()
    CentroCusto.objects.all().delete()
    r = registrar_pedido(LIMPEZA, uuid.uuid4(), envio_limpeza())
    assert not r.ok and "Não há centros de custo cadastrados" in r.mensagem
    assert not Pedido.objects.exists()


def test_reenvio_identico_confirma_sem_gravar_nem_avisar_e_diferente_e_divergente(
    django_capture_on_commit_callbacks, avisos
):
    montar_cenario()
    envio_id = uuid.uuid4()
    with django_capture_on_commit_callbacks(execute=True):
        registrar_pedido(LIMPEZA, envio_id, envio_limpeza())
        r2 = registrar_pedido(LIMPEZA, envio_id, envio_limpeza())
    assert (r2.ok, r2.reenvio, r2.numero) == (True, True, "P-000001")
    assert Pedido.objects.count() == 1 and ItemPedido.objects.count() == 2
    assert avisos == ["P-000001"]
    r3 = registrar_pedido(LIMPEZA, envio_id, envio_limpeza(destino="ETA I"))
    assert (r3.ok, r3.divergente) == (False, True)
    assert r3.mensagem == mensagem_divergente("P-000001")
    assert r3.mensagem == (
        "Uma tentativa anterior deste envio já foi registrada (Nº P-000001), mas com dados "
        "diferentes destes. Avise o almoxarifado antes de enviar de novo."
    )
    assert Pedido.objects.count() == 1


def test_mesmo_id_em_outro_formulario_e_divergente():
    montar_cenario()
    envio_id = uuid.uuid4()
    registrar_pedido(LIMPEZA, envio_id, envio_limpeza())
    assert registrar_pedido(AB, envio_id, envio_ab()).divergente


def test_ab_acima_do_estoque_e_recusado_inteiro():
    montar_cenario()
    r = registrar_pedido(
        AB, uuid.uuid4(), envio_ab(itens=itens(("016.005.010", "3"), ("013.006.001", "3")))
    )
    assert r.ok is False
    assert r.mensagem == "Corrija os itens abaixo e envie de novo."
    assert r.estoque_atual == {"013.006.001": 2}
    assert not Pedido.objects.exists() and not ItemPedido.objects.exists()
    sem = registrar_pedido(AB, uuid.uuid4(), envio_ab(itens=itens(("013.005.007", "1"))))
    assert [e.texto for e in sem.erros] == ["LUVA NITRÍLICA (013.005.007): Sem estoque."]


def test_ab_sem_saldo_importado_fica_indisponivel():
    montar_cenario(com_estoque=False)
    r = registrar_pedido(AB, uuid.uuid4(), envio_ab())
    assert r.ok is False
    assert (
        r.mensagem == "O catálogo deste formulário não está disponível agora. Avise o almoxarifado."
    )


def test_falha_no_telegram_nao_desfaz_o_pedido(
    settings, monkeypatch, django_capture_on_commit_callbacks
):
    montar_cenario()
    settings.TELEGRAM_TOKEN, settings.TELEGRAM_CHAT_ID = "t", "c"

    def falha(req, timeout):
        raise URLError("sem rede")

    monkeypatch.setattr("pedidos.telegram.urlopen", falha)
    with django_capture_on_commit_callbacks(execute=True):
        r = registrar_pedido(AB, uuid.uuid4(), envio_ab())
    assert r.ok and r.telegram == "falhou"
    assert Pedido.objects.count() == 1


def test_falha_inesperada_desfaz_tudo_e_a_retentativa_nao_duplica(monkeypatch):
    montar_cenario()
    envio_id = uuid.uuid4()

    def quebra(pedido, validos):
        raise RuntimeError("queda no meio")

    original = servicos._gravar_itens
    monkeypatch.setattr(servicos, "_gravar_itens", quebra)
    with pytest.raises(RuntimeError):
        registrar_pedido(LIMPEZA, envio_id, envio_limpeza())
    assert not Pedido.objects.exists()
    monkeypatch.setattr(servicos, "_gravar_itens", original)
    r = registrar_pedido(LIMPEZA, envio_id, envio_limpeza())
    assert (r.ok, r.numero) == (True, "P-000001")


@pytest.mark.django_db(transaction=True)
def test_envio_duplo_simultaneo_grava_um_pedido():
    montar_cenario()
    # A linha da numeração já existe, como em produção (a importação das planilhas a cria e
    # ela nunca é apagada). Sem ela, as duas threads a criam ao mesmo tempo, e a marca que o
    # DELETE da limpeza entre testes deixa no índice único faz o InnoDB entrar em impasse.
    Sequencia.objects.create(nome="PEDIDOS")
    envio_id = uuid.uuid4()
    resultados = em_paralelo(
        lambda: registrar_pedido(LIMPEZA, envio_id, envio_limpeza()),
        lambda: registrar_pedido(LIMPEZA, envio_id, envio_limpeza()),
    )
    assert all(r.ok for r in resultados)
    assert sorted(r.reenvio for r in resultados) == [False, True]
    assert Pedido.objects.count() == 1


def test_erros_de_tamanho_dizem_o_campo(settings):
    settings.PEDIDOS_MAX_TEXTO = 3
    settings.PEDIDOS_MAX_ITENS = 1
    erros = servicos.erros_de_tamanho(
        {"Nome completo": "Ana Maria", "Destino": "ETA II", "Observação": "urgente"}, 2
    )
    assert [(e.texto, e.campo) for e in erros] == [
        ("Nome completo: no máximo 3 caracteres.", "solicitante"),
        ("Destino: no máximo 3 caracteres.", "destino"),
        ("Observação: no máximo 3 caracteres.", "obs"),
        ("O pedido pode ter no máximo 1 materiais. Divida em mais de um pedido.", None),
    ]


# --- O catálogo sai da fila única de envios (spec 005, US9) ------------------------------------


def _anotar_chamadas(monkeypatch, *nomes):
    """Registra a ordem em que `servicos` chama cada função, sem mudar o que ela faz."""
    ordem = []
    for nome in nomes:
        original = getattr(servicos, nome)

        def com_registro(*args, _original=original, _nome=nome, **kwargs):
            ordem.append(_nome)
            return _original(*args, **kwargs)

        monkeypatch.setattr(servicos, nome, com_registro)
    return ordem


@pytest.mark.parametrize("origem", [AB, LIMPEZA])
def test_catalogo_e_centros_sao_lidos_antes_de_travar_a_numeracao(monkeypatch, avisos, origem):
    montar_cenario()
    ordem = _anotar_chamadas(monkeypatch, "catalogo_de", "centros_do_fluxo", "travar_sequencia")
    envio = envio_ab() if origem == AB else envio_limpeza()
    assert registrar_pedido(origem, uuid.uuid4(), envio).ok
    # O catálogo do AB é a parte mais pesada: nenhum outro envio espera por ele.
    assert ordem.count("catalogo_de") == 1
    trava = ordem.index("travar_sequencia")
    assert ordem.index("catalogo_de") < trava and ordem.index("centros_do_fluxo") < trava


def test_a_ordem_das_respostas_nao_muda_com_o_catalogo_lido_antes(monkeypatch, avisos, settings):
    montar_cenario()
    envio_id = uuid.uuid4()
    primeira = registrar_pedido(AB, envio_id, envio_ab(), ip="10.0.0.1")
    assert primeira.ok
    # 1) O reenvio igual confirma sem contar no limite, mesmo com o limite estourado.
    settings.PEDIDOS_LIMITE_IP_10_MIN = 1
    assert registrar_pedido(AB, envio_id, envio_ab(), ip="10.0.0.1").reenvio
    # 2) O limite vem antes do catálogo indisponível.
    monkeypatch.setattr(servicos, "catalogo_de", lambda origem: None)
    limite = registrar_pedido(AB, uuid.uuid4(), envio_ab(), ip="10.0.0.1")
    assert limite.mensagem == servicos.MENSAGEM_LIMITE_IP
    # 3) Sem limite, o catálogo indisponível é a resposta.
    outra = registrar_pedido(AB, uuid.uuid4(), envio_ab(), ip="10.0.0.2")
    assert "catálogo deste formulário não está disponível" in outra.mensagem
