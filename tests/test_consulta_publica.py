"""Consulta pública da situação do pedido, sem login (spec 011).

As expectativas desta matriz vêm das regras de negócio (spec 011, seção 3), escritas por extenso:
nenhuma é calculada pela função que a consulta usa. Cada estado é montado pelos serviços reais
(registrar, decidir a autorização, atender e editar o atendimento)."""

import re
import uuid
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from pedidos.models import Atendimento, AutorizacaoPedido, LinhaSaida, Pedido
from pedidos.regras import AB, AVULSA, EPIS, LIMPEZA, OFICINA, VIATURAS, Adicionado, nome_confere
from pedidos.servicos import (
    catalogo_de,
    confirmar_atendimento,
    decidir_autorizacao,
    editar_atendimento,
)
from tests.cenario import criar_pedido, dar_saldo, envio_ab, envio_limpeza, registrar, saida
from tests.cenario import textos as erros_de
from tests.config_cenario import enviar_formulario
from tests.epis_cenario import LUVA, montar_epis
from tests.epis_cenario import registrar as registrar_epi
from tests.paginas import texto

pytestmark = pytest.mark.django_db

URL = reverse("pedidos:consulta")
URL_ANTIGA = reverse("pedidos:consulta_epi")
HOJE = date(2026, 10, 9)

VAZIO = "Informe o número do pedido."
INVALIDO = (
    "Este não é um número de pedido. O número começa com P, como P-000123, e aparece na tela de "
    "confirmação do envio."
)
SEM_NOME = "Informe o seu primeiro nome, como foi escrito no pedido."
NAO_ACHADO = (
    "Não encontramos um pedido com este número e este nome. Confira os dois na tela de confirmação "
    "do envio."
)
LIMITE = (
    "Muitas consultas desta rede em pouco tempo. Tente de novo daqui a 10 minutos ou procure o "
    "almoxarifado."
)

# As frases da tabela de estados (spec 011, seção 3).
AGUARDANDO = "O almoxarifado ainda não registrou o atendimento deste pedido."
AGUARDANDO_AUTORIZACAO = (
    "A Segurança do Trabalho ainda não decidiu este pedido. O almoxarifado só pode atendê-lo "
    "depois da autorização."
)
RECUSADO = "A Segurança do Trabalho recusou este pedido. Ele está encerrado e não será atendido."
ATENDIDO_EM_1_10 = "O almoxarifado registrou a saída dos materiais deste pedido em 01/10/2026."
PARCIAL_EM_1_10 = (
    "O almoxarifado registrou a saída dos materiais deste pedido em 01/10/2026, com algum material "
    "em quantidade menor que a pedida. O que faltou não fica pendente neste pedido."
)
# Frases que nenhuma consulta pode trazer: prometem o que o sistema não registra.
PROMESSAS = ["procure o almoxarifado para retirar", "vai atendê-lo", "será entregue", "retirar"]

TITULOS = {
    LIMPEZA: "Limpeza, copa e escritório",
    AB: "Ferramentas, peças e materiais",
    VIATURAS: "Reposição de peças das viaturas",
    OFICINA: "Oficina mecânica",
    EPIS: "Equipamentos de proteção individual (EPIs)",
}


@pytest.fixture(autouse=True)
def cenario():
    cache.clear()  # o limite vive no cache: cada teste começa do zero
    montar_epis()  # o cenário geral (limpeza e AB) mais o dos EPIs


@pytest.fixture
def almox():
    return get_user_model().objects.create_user(
        username="12345", password="x", first_name="Zuleica", last_name="Atendente"
    )


def hoje_br() -> str:
    return timezone.localdate().strftime("%d/%m/%Y")


def consultar(client, numero, nome=None):
    """Consulta com o número e o nome. Sem `nome`, o nome como o solicitante o escreveu no pedido
    (é a entrada da consulta, nunca a expectativa); sem pedido com o número, "Ana"."""
    if nome is None:
        pedido = Pedido.objects.filter(numero=numero).first()
        nome = pedido.solicitante if pedido else "Ana"
    return client.post(URL, {"numero": numero, "nome": nome})


def selo(resposta) -> str | None:
    casou = re.search(r'<span class="selo [^"]*" data-situacao>([^<]+)</span>', resposta.text)
    return casou.group(1) if casou else None


def itens_da_consulta(resposta) -> list[tuple[str, str]]:
    """A lista "Materiais pedidos" da consulta: (material, quantidade com a unidade)."""
    lista = re.search(
        r'<ul class="sucesso-itens" aria-labelledby="consulta-itens-titulo">(.*?)</ul>',
        resposta.text,
        re.S,
    )
    if not lista:
        return []
    return [
        (texto(m), texto(q))
        for m, q in re.findall(
            r"<li><span>(.*?)</span>\s*<strong>(.*?)</strong></li>", lista.group(1)
        )
    ]


def atender(pedido, usuario, qtds, *, data="2026-10-01", adicionados=()):
    r = confirmar_atendimento(
        pedido.id,
        uuid.uuid4(),
        saida(data=data),
        qtds,
        nao_lancar=False,
        usuario=usuario,
        hoje=HOJE,
        adicionados=adicionados,
    )
    assert r.ok, erros_de(r)
    return r


def editar(pedido, usuario, qtds, *, data):
    r = editar_atendimento(
        pedido.id,
        Pedido.objects.get(pk=pedido.pk).versao,
        saida(data=data),
        qtds,
        nao_lancar=False,
        usuario=usuario,
        hoje=HOJE,
    )
    assert r.ok, erros_de(r)
    return r


# Cenários: cada um monta o estado pelos serviços e devolve o pedido.


def limpeza_aguardando(quem, almox):
    return registrar(LIMPEZA, envio_limpeza()).pedido


def limpeza_atendido(quem, almox):
    pedido = limpeza_aguardando(quem, almox)
    atender(pedido, almox, {"023.001.002": "2", "008.001.002": "1,5"})
    return pedido


def limpeza_parcial(quem, almox):
    pedido = limpeza_aguardando(quem, almox)
    atender(pedido, almox, {"023.001.002": "2", "008.001.002": "0"})
    return pedido


def limpeza_com_troca(quem, almox):
    """O almoxarifado trocou um material pedido por outro entregue: não é parcial."""
    dar_saldo("023.001.002", "008.001.002", "013.006.001")
    pedido = limpeza_aguardando(quem, almox)
    no_pedido = {i.codigo for i in pedido.itens.all()}
    outro = next(i.codigo for i in catalogo_de(AVULSA) if i.codigo not in no_pedido)
    atender(
        pedido,
        almox,
        {"023.001.002": "2", "008.001.002": "0", outro: "1"},
        adicionados=[Adicionado(outro, "008.001.002")],
    )
    return pedido


def ab_aguardando(quem, almox):
    return registrar(AB, envio_ab()).pedido


def epi_aguardando(quem, almox):
    return registrar_epi()


def epi_recusado(quem, almox):
    pedido = registrar_epi()
    decidir_autorizacao(pedido.numero, "recusar", "Sem laudo do médico", quem["seguranca"])
    return pedido


def epi_autorizado(quem, almox):
    pedido = registrar_epi()
    decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    return pedido


def epi_atendido(quem, almox):
    pedido = epi_autorizado(quem, almox)
    atender(pedido, almox, {LUVA: "2"})
    return pedido


def epi_parcial(quem, almox):
    pedido = epi_autorizado(quem, almox)
    atender(pedido, almox, {LUVA: "1"})
    return pedido


MATRIZ = [
    # (cenário, formulário, selo, frases presentes, frases ausentes)
    (limpeza_aguardando, LIMPEZA, "Aguardando atendimento", [AGUARDANDO], ["registrou a saída"]),
    (limpeza_atendido, LIMPEZA, "Atendido", [ATENDIDO_EM_1_10], [AGUARDANDO, "menor que"]),
    (limpeza_parcial, LIMPEZA, "Atendido parcialmente", [PARCIAL_EM_1_10], [AGUARDANDO]),
    (limpeza_com_troca, LIMPEZA, "Atendido", [ATENDIDO_EM_1_10], ["menor que"]),
    (ab_aguardando, AB, "Aguardando atendimento", [AGUARDANDO], ["Segurança do Trabalho"]),
    (
        epi_aguardando,
        EPIS,
        "Aguardando autorização",
        [AGUARDANDO_AUTORIZACAO],
        ["autorizou", "registrou a saída"],
    ),
    (
        epi_recusado,
        EPIS,
        "Recusado",
        [RECUSADO, "Motivo: Sem laudo do médico"],
        ["autorizou", AGUARDANDO],
    ),
    (
        epi_autorizado,
        EPIS,
        "Autorizado",
        ["A Segurança do Trabalho autorizou este pedido em {hoje}. " + AGUARDANDO],
        ["registrou a saída", "ainda não decidiu"],
    ),
    (epi_atendido, EPIS, "Atendido", [ATENDIDO_EM_1_10], [AGUARDANDO, "ainda não decidiu"]),
    (epi_parcial, EPIS, "Atendido parcialmente", [PARCIAL_EM_1_10], [AGUARDANDO]),
]


@pytest.mark.parametrize(
    ("montar", "origem", "rotulo", "presentes", "ausentes"),
    MATRIZ,
    ids=[m[0].__name__ for m in MATRIZ],
)
def test_matriz_de_estados(client, quem, almox, montar, origem, rotulo, presentes, ausentes):
    pedido = montar(quem, almox)
    r = consultar(client, pedido.numero)
    assert r.status_code == 200
    html = texto(r.text)
    assert selo(r) == rotulo
    assert f"Pedido {pedido.numero}" in html
    assert TITULOS[origem] in html
    assert f"Enviado em {hoje_br()}" in html
    for frase in presentes:
        assert frase.format(hoje=hoje_br()) in html, frase
    for frase in ausentes + PROMESSAS:
        assert frase not in html, frase


@pytest.mark.parametrize("origem", [LIMPEZA, AB, VIATURAS, OFICINA, EPIS])
def test_todo_formulario_publico_e_consultado_com_o_seu_titulo(client, origem):
    pedido = criar_pedido(origem=origem)
    if origem == EPIS:
        AutorizacaoPedido.objects.create(pedido=pedido)
    html = texto(consultar(client, pedido.numero).text)
    assert f"Pedido {pedido.numero}" in html and TITULOS[origem] in html


def test_acompanha_o_atendimento_e_a_edicao(client, quem, almox):
    pedido = limpeza_aguardando(quem, almox)
    r = consultar(client, pedido.numero)
    assert selo(r) == "Aguardando atendimento" and AGUARDANDO in texto(r.text)

    atender(pedido, almox, {"023.001.002": "2", "008.001.002": "1,5"})
    r = consultar(client, pedido.numero)
    assert selo(r) == "Atendido" and ATENDIDO_EM_1_10 in texto(r.text)

    # A edição muda a quantidade e a data efetiva: a consulta segue o que está gravado.
    editar(pedido, almox, {"023.001.002": "2", "008.001.002": "1"}, data="2026-10-02")
    r = consultar(client, pedido.numero)
    assert selo(r) == "Atendido parcialmente"
    assert "registrou a saída dos materiais deste pedido em 02/10/2026" in texto(r.text)

    editar(pedido, almox, {"023.001.002": "2", "008.001.002": "1,5"}, data="2026-10-03")
    r = consultar(client, pedido.numero)
    assert selo(r) == "Atendido"
    assert "deste pedido em 03/10/2026." in texto(r.text)


def test_acompanha_a_autorizacao_e_depois_o_atendimento(client, quem, almox):
    pedido = registrar_epi()
    assert selo(consultar(client, pedido.numero)) == "Aguardando autorização"
    decidir_autorizacao(pedido.numero, "autorizar", "", quem["seguranca"])
    assert selo(consultar(client, pedido.numero)) == "Autorizado"
    atender(pedido, almox, {LUVA: "2"})
    r = consultar(client, pedido.numero)
    assert selo(r) == "Atendido"
    # Atendido, a autorização já não é a notícia: a frase é a do atendimento.
    assert "autorizou" not in texto(r.text)


# Limites de exposição (spec 011, seção 4).


def test_nao_expoe_dados_do_pedido_nem_do_atendimento(client, almox):
    pedido = registrar(
        LIMPEZA, envio_limpeza(solicitante="Ana Distinta Exposta", obs="Sala do diretor")
    ).pedido
    atender(pedido, almox, {"023.001.002": "2", "008.001.002": "1,5"})
    Atendimento.objects.filter(pedido=pedido).update(recebedor="Recebedora Fulana", placa="XYZ9A99")
    LinhaSaida.objects.filter(atendimento__pedido=pedido).update(requisicao_scpi="009876/26")
    # O nome digitado em minúsculas: o gravado ("Ana Distinta Exposta") não pode voltar na resposta.
    r = consultar(client, pedido.numero, "ana distinta exposta")
    assert selo(r) == "Atendido"
    proibidos = [
        "Ana Distinta",
        "Exposta",
        "Sala do diretor",
        "ETA II",  # destino e centro de custo
        "Recebedora",
        "Zuleica",  # quem atendeu
        "BALCÃO",
        "XYZ9A99",
        "009876/26",
        "023.001.002",
        "008.001.002",
        "Destino",
        "Recebedor",
        "SCPI",
    ]
    for dado in proibidos:
        assert dado not in r.text, dado
    # Os materiais pedidos aparecem (com número e primeiro nome), os códigos não.
    assert itens_da_consulta(r) == LIMPEZA_PEDIDA


def test_nao_expoe_a_ocorrencia_nem_quem_decidiu(client, quem):
    viatura = criar_pedido(origem=VIATURAS, solicitante="Carlos Motorista")
    Pedido.objects.filter(pk=viatura.pk).update(ocorrencia="OC-55443", obs="Viatura 12")
    r = consultar(client, viatura.numero, "carlos motorista")
    for dado in ["OC-55443", "Viatura 12", "Carlos", "ocorrência"]:
        assert dado not in r.text, dado

    epi = epi_recusado(quem, None)
    r = consultar(client, epi.numero, "marcos pereira")
    assert "Sem laudo do médico" in r.text
    for dado in ["Marcos", "Pereira", "Sônia", "Sônia Segura", "70001", LUVA, "ETA I"]:
        assert dado not in r.text, dado


# Respostas que não são de um pedido.


@pytest.mark.parametrize("digitado", ["", "   "])
def test_em_branco_pede_o_numero(client, digitado):
    r = consultar(client, digitado)
    assert VAZIO in texto(r.text) and selo(r) is None


@pytest.mark.parametrize("digitado", ["AV-000002", "003588/26", "abc", "P-", "P-12a", "OC-55443"])
def test_numero_invalido(client, digitado):
    r = consultar(client, digitado)
    assert r.status_code == 200
    assert INVALIDO in texto(r.text) and selo(r) is None


def test_saida_avulsa_existente_e_inexistente_tem_a_mesma_resposta(client, almox):
    avulsa = criar_pedido(origem=AVULSA, usuario=almox)
    assert avulsa.numero.startswith("AV-")
    inexistente = "AV-999999"
    a = consultar(client, avulsa.numero)
    b = consultar(client, inexistente)
    assert texto(a.text.replace(avulsa.numero, inexistente)) == texto(b.text)
    assert INVALIDO in texto(a.text)


def test_nao_achado_e_o_mesmo_para_inexistente_e_para_pedido_interno(client, almox):
    # Defesa em profundidade: mesmo um pedido interno com número P- não é respondido.
    interno = criar_pedido(origem=AVULSA, numero="P-000777", usuario=almox)
    a = consultar(client, interno.numero)
    b = consultar(client, "P-999999")
    assert a.status_code == b.status_code == 200
    assert NAO_ACHADO in texto(a.text) and NAO_ACHADO in texto(b.text)
    assert texto(a.text.replace("P-000777", "P-999999")) == texto(b.text)


@pytest.mark.parametrize("digitado", ["p1", "P1", " P-1 ", "P-0001", "p - 000001", "P-000001"])
def test_o_numero_digitado_e_normalizado(client, quem, almox, digitado):
    pedido = limpeza_aguardando(quem, almox)
    assert pedido.numero == "P-000001"
    r = consultar(client, digitado, "Ana")
    assert selo(r) == "Aguardando atendimento", digitado
    assert "Pedido P-000001" in texto(r.text)


def test_o_numero_digitado_fica_no_campo(client):
    r = consultar(client, "P-999999")
    assert 'value="P-999999"' in r.text


def test_excesso_de_tentativas(client, settings, quem, almox):
    settings.PEDIDOS_CONSULTA_LIMITE_IP_10_MIN = 2
    pedido = limpeza_aguardando(quem, almox)
    consultar(client, "abc")  # toda consulta conta, também a inválida
    assert selo(consultar(client, pedido.numero)) == "Aguardando atendimento"
    r = consultar(client, pedido.numero)
    assert r.status_code == 429
    assert LIMITE in texto(r.text) and selo(r) is None
    assert AGUARDANDO not in texto(r.text)
    # O limite é por origem.
    outro = Client(REMOTE_ADDR="10.9.9.9")
    assert (
        selo(outro.post(URL, {"numero": pedido.numero, "nome": "Ana"})) == "Aguardando atendimento"
    )


def test_a_rota_antiga_dos_epis_e_a_mesma_consulta(client, quem, almox):
    pedido = limpeza_aguardando(quem, almox)
    assert URL == "/pedido/consulta/" and URL_ANTIGA == "/pedido/epis/consulta/"
    r = client.post(URL_ANTIGA, {"numero": pedido.numero, "nome": "Ana"})
    assert selo(r) == "Aguardando atendimento"
    pagina = client.get(URL_ANTIGA)
    assert pagina.status_code == 200 and f'action="{URL}#resultado"' in pagina.text


def test_get_mostra_so_o_formulario(client):
    r = client.get(URL)
    assert r.status_code == 200
    assert 'name="numero"' in r.text and 'name="csrfmiddlewaretoken"' in r.text
    assert selo(r) is None and "Pedido P-" not in r.text


def test_nao_vai_para_o_cache_do_navegador(client):
    assert "no-store" in consultar(client, "P-000001")["Cache-Control"]
    assert "no-store" in client.get(URL)["Cache-Control"]


def test_exige_o_csrf():
    estrito = Client(enforce_csrf_checks=True)
    assert estrito.post(URL, {"numero": "P-000001", "nome": "Ana"}).status_code == 403


def test_outro_metodo_nao_e_aceito(client):
    assert client.put(URL).status_code == 405 and client.delete(URL).status_code == 405


def test_so_le_o_banco(client, quem, almox):
    pedido = epi_atendido(quem, almox)
    with CaptureQueriesContext(connection) as consultas:
        r = consultar(client, pedido.numero)
    assert selo(r) == "Atendido"
    escritas = [
        q["sql"]
        for q in consultas.captured_queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert escritas == []
    assert len(consultas.captured_queries) <= 4


# A jornada: da confirmação do envio à consulta (spec 011, seção 5).


def test_a_tela_de_sucesso_leva_a_consulta_sem_o_numero_na_url(client):
    r = enviar_formulario(
        client, "limpeza", [("023.001.002", "1")], destino="ETA II", solicitante="Ana"
    )
    assert r.status_code == 200
    numero = re.search(r'class="sucesso-numero mono">([^<]+)<', r.text).group(1)
    formulario = re.search(
        r'<form[^>]*action="([^"]+)"[^>]*data-ver-situacao.*?</form>', r.text, re.S
    )
    # Nem o número nem o nome vão na URL; a âncora rola até o resultado.
    assert formulario and formulario.group(1) == URL + "#resultado"
    assert f'name="numero" value="{numero}"' in formulario.group(0)
    assert 'name="nome" value="Ana"' in formulario.group(0)
    assert "csrfmiddlewaretoken" in formulario.group(0)
    html = texto(r.text)
    assert "Ver a situação agora" in html
    assert "de qualquer aparelho" in html and "Consultar pedido" in html
    assert "com este número e o seu primeiro nome, como foi escrito no pedido" in html
    # Em outro aparelho: só o número, digitado.
    outro = Client(REMOTE_ADDR="10.1.1.1")
    assert selo(outro.post(URL, {"numero": numero, "nome": "Ana"})) == "Aguardando atendimento"


def test_a_tela_de_sucesso_do_epi_mantem_o_aviso_da_autorizacao(client):
    r = enviar_formulario(client, "epis", [(LUVA, "1")], destino="ETA I")
    html = texto(r.text)
    assert "Aguardando a autorização da Segurança do Trabalho." in html
    assert f'action="{URL}#resultado"' in r.text and "Ver a situação agora" in html


def test_a_pagina_inicial_leva_a_consulta(client):
    r = client.get(reverse("pedidos:inicio"))
    assert f'href="{URL}"' in r.text and "Consultar um pedido" in texto(r.text)
    # No topo, antes dos formulários (quem volta não precisa passar por eles).
    assert r.text.index(f'href="{URL}"') < r.text.index('class="opcoes-formulario"')


# O número digitado (regras puras).


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("P-000123", "P-000123"),
        ("p-123", "P-000123"),
        (" P123 ", "P-000123"),
        ("p - 7", "P-000007"),
        ("P-123456789", "P-123456789"),
        ("P-1234567890", None),  # mais de 9 algarismos
        ("AV-000002", None),
        ("003588/26", None),
        ("abc", None),
        ("P-", None),
        ("", None),
        ("  ", None),
    ],
)
def test_numero_de_pedido_publico(digitado, esperado):
    from pedidos.regras import numero_de_pedido_publico

    assert numero_de_pedido_publico(digitado) == esperado


# A tradução de cada situação (regra pura), com as frases da spec escritas por extenso.


@pytest.mark.parametrize(
    ("chave", "extra", "rotulo", "frase", "motivo"),
    [
        ("aguardando_autorizacao", {}, "Aguardando autorização", AGUARDANDO_AUTORIZACAO, ""),
        (
            "recusado",
            {"autorizacao": "RECUSADO", "motivo": "Sem laudo"},
            "Recusado",
            RECUSADO,
            "Sem laudo",
        ),
        ("aguardando", {}, "Aguardando atendimento", AGUARDANDO, ""),
        (
            "aguardando",
            {"autorizacao": "AUTORIZADO", "decidido_em": date(2026, 11, 5)},
            "Autorizado",
            "A Segurança do Trabalho autorizou este pedido em 05/11/2026. " + AGUARDANDO,
            "",
        ),
        ("atendido", {"saida_em": date(2026, 10, 1)}, "Atendido", ATENDIDO_EM_1_10, ""),
        ("parcial", {"saida_em": date(2026, 10, 1)}, "Atendido parcialmente", PARCIAL_EM_1_10, ""),
        # Atendido de EPI: a autorização já não é a notícia.
        (
            "atendido",
            {
                "autorizacao": "AUTORIZADO",
                "decidido_em": date(2026, 9, 30),
                "saida_em": date(2026, 10, 1),
            },
            "Atendido",
            ATENDIDO_EM_1_10,
            "",
        ),
    ],
)
def test_texto_de_cada_situacao(chave, extra, rotulo, frase, motivo):
    from pedidos.regras import Situacao, texto_consulta_publica

    consulta = texto_consulta_publica(Situacao(chave, "interno", "interno"), **extra)
    assert (consulta.chave, consulta.rotulo, consulta.frase, consulta.motivo) == (
        chave,
        rotulo,
        frase,
        motivo,
    )


def test_situacao_sem_texto_publico_e_erro():
    from pedidos.regras import Situacao, texto_consulta_publica

    with pytest.raises(ValueError):
        texto_consulta_publica(Situacao("desconhecida", "", ""))


# O primeiro nome do solicitante (spec 011, seção 4: número e primeiro nome).


@pytest.mark.parametrize(
    "digitado",
    ["Marcos", "marcos", "  MARCOS ", "Márcos", "Marcos Pereira", "marcos da silva"],
)
def test_basta_o_primeiro_nome_sem_diferenca_de_maiusculas_acentos_e_espacos(client, digitado):
    pedido = registrar_epi(solicitante="Marcos Pereira")
    assert selo(consultar(client, pedido.numero, digitado)) == "Aguardando autorização"


@pytest.mark.parametrize(
    "digitado",
    ["Pereira", "Marc", "Marcosa", "Ana", "MarcosPereira", "Pereira Marcos"],
)
def test_nome_que_nao_confere_responde_como_numero_inexistente(client, digitado):
    pedido = registrar_epi(solicitante="Marcos Pereira")
    errado = consultar(client, pedido.numero, digitado)
    inexistente = consultar(client, "P-999999", digitado)
    assert errado.status_code == inexistente.status_code == 200
    assert selo(errado) is None and NAO_ACHADO in texto(errado.text)
    assert texto(errado.text.replace(pedido.numero, "P-999999")) == texto(inexistente.text)
    assert "aguardando" not in texto(errado.text).lower()


def test_o_nome_de_outro_pedido_nao_abre_este(client, quem, almox):
    ana = limpeza_aguardando(quem, almox)  # solicitante "Ana"
    bruno = ab_aguardando(quem, almox)  # solicitante "Bruno"
    assert NAO_ACHADO in texto(consultar(client, ana.numero, "Bruno").text)
    assert NAO_ACHADO in texto(consultar(client, bruno.numero, "Ana").text)


@pytest.mark.parametrize("nome", ["", "   "])
def test_sem_o_nome_pede_o_nome(client, quem, almox, nome):
    pedido = limpeza_aguardando(quem, almox)
    r = consultar(client, pedido.numero, nome)
    assert SEM_NOME in texto(r.text) and selo(r) is None


def test_o_nome_digitado_fica_no_campo(client):
    r = consultar(client, "P-999999", "Fulano de Tal")
    assert 'value="Fulano de Tal"' in r.text


def test_tentativas_com_nome_errado_contam_no_limite(client, settings, quem, almox):
    settings.PEDIDOS_CONSULTA_LIMITE_IP_10_MIN = 2
    pedido = limpeza_aguardando(quem, almox)
    consultar(client, pedido.numero, "Beatriz")
    consultar(client, pedido.numero, "Carla")
    r = consultar(client, pedido.numero, "Ana")  # o certo, mas depois do limite
    assert r.status_code == 429 and LIMITE in texto(r.text) and selo(r) is None


@pytest.mark.parametrize(
    ("digitado", "gravado", "confere"),
    [
        ("Ana", "Ana", True),
        (" ana ", "Ana Maria", True),
        ("JOSÉ", "José da Silva", True),
        ("jose", "José da Silva", True),
        ("José Souza", "José da Silva", True),  # só o primeiro nome é comparado
        ("Jos", "José", False),
        ("Silva", "José da Silva", False),
        ("", "", False),  # pedido sem nome nunca é consultado
        ("  ", "", False),
        ("Ana", "", False),
    ],
)
def test_nome_confere(digitado, gravado, confere):
    assert nome_confere(digitado, gravado) is confere


# A lista de materiais e das quantidades pedidas (spec 011, seção 4).

# A unidade é a exibida da lista de limpeza ou, sem ela, a do cadastro
# (catalogos.formulario_limpeza).
LIMPEZA_PEDIDA = [("DETERGENTE NEUTRO", "2 UN"), ("CAFÉ 500 G", "1,5 Pacote 500 g")]


@pytest.mark.parametrize(
    ("montar", "esperado"),
    [
        (limpeza_aguardando, LIMPEZA_PEDIDA),
        (limpeza_atendido, LIMPEZA_PEDIDA),
        # Parcial: a quantidade é a pedida, nunca a entregue (o café saiu com 0).
        (limpeza_parcial, LIMPEZA_PEDIDA),
        # Troca: o acrescentado pelo almoxarifado não aparece; o trocado continua como pedido.
        (limpeza_com_troca, LIMPEZA_PEDIDA),
        (ab_aguardando, [("FITA VEDA ROSCA", "3 UN")]),
        (epi_aguardando, [("LUVA DE VAQUETA", "2 UN")]),
        (epi_recusado, [("LUVA DE VAQUETA", "2 UN")]),
        (epi_parcial, [("LUVA DE VAQUETA", "2 UN")]),
    ],
    ids=lambda v: v.__name__ if callable(v) else "",
)
def test_lista_os_materiais_e_as_quantidades_pedidas(client, quem, almox, montar, esperado):
    pedido = montar(quem, almox)
    r = consultar(client, pedido.numero)
    assert itens_da_consulta(r) == esperado
    assert "Materiais pedidos" in texto(r.text)
    for palavra in ["Entregue", "entregue:", "Trocado", "Adicionado pelo almoxarifado"]:
        assert palavra not in r.text, palavra


def test_sem_o_nome_certo_a_lista_nao_aparece(client, quem, almox):
    pedido = limpeza_aguardando(quem, almox)
    for nome in ["Bruno", ""]:
        r = consultar(client, pedido.numero, nome)
        assert itens_da_consulta(r) == [] and "DETERGENTE" not in r.text and "CAFÉ" not in r.text
    r = consultar(client, "P-999999", "Ana")
    assert itens_da_consulta(r) == [] and "Materiais pedidos" not in texto(r.text)


def test_a_lista_nao_custa_consulta_a_mais(client, quem, almox, django_assert_max_num_queries):
    pedido = limpeza_com_troca(quem, almox)
    with django_assert_max_num_queries(2):
        r = consultar(client, pedido.numero, "Ana")
    assert len(itens_da_consulta(r)) == 2


def test_a_lista_e_a_mesma_da_tela_de_sucesso(client):
    """A consulta reaproveita a lista da confirmação do envio (`_itens_pedidos.html`)."""
    sucesso = enviar_formulario(
        client,
        "limpeza",
        [("023.001.002", "2"), ("008.001.002", "1,5")],
        destino="ETA II",
        solicitante="Ana",
    )
    numero = re.search(r'class="sucesso-numero mono">([^<]+)<', sucesso.text).group(1)
    lista_sucesso = re.search(r'<ul class="sucesso-itens">(.*?)</ul>', sucesso.text, re.S).group(1)
    consulta = consultar(client, numero, "Ana")
    lista_consulta = re.search(
        r'<ul class="sucesso-itens" aria-labelledby="consulta-itens-titulo">(.*?)</ul>',
        consulta.text,
        re.S,
    ).group(1)
    assert lista_consulta == lista_sucesso
    assert itens_da_consulta(consulta) == LIMPEZA_PEDIDA


def test_a_ancora_leva_ao_resultado_ou_ao_formulario_com_o_erro(client, quem, almox):
    """O envio vai para `#resultado`: com sucesso, o navegador rola até o cartão do pedido; com
    erro, até o formulário, que tem o aviso logo abaixo. Uma só âncora por página."""
    pedido = limpeza_aguardando(quem, almox)
    r = consultar(client, pedido.numero, "Ana")
    assert r.text.count('id="resultado"') == 1
    assert re.search(r'<section class="cartao pilha consulta-resultado" id="resultado"', r.text)
    for numero, nome in [("P-999999", "Ana"), ("abc", "Ana"), (pedido.numero, "Bruno"), ("", "")]:
        r = consultar(client, numero, nome)
        assert r.text.count('id="resultado"') == 1, (numero, nome)
        assert re.search(r'<form [^>]*consulta-formulario" id="resultado"', r.text), (numero, nome)
    # Sem envio (GET), nada para rolar.
    assert 'id="resultado"' not in client.get(URL).text


def test_nenhum_comentario_de_template_vaza_na_pagina(client, quem, almox):
    """`{# #}` só vale numa linha: em várias, o Django o mostra como texto."""
    pedido = limpeza_aguardando(quem, almox)
    paginas = [
        client.get(URL),
        consultar(client, pedido.numero, "Ana"),
        consultar(client, "P-999999", "Ana"),
        client.get(reverse("pedidos:inicio")),
        enviar_formulario(client, "limpeza", [("023.001.002", "1")], destino="ETA II"),
    ]
    for r in paginas:
        assert "{#" not in r.text and "#}" not in r.text and "{%" not in r.text
