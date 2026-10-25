"""A página Formulários (spec 009, US1 e US2): abas, listas, gravações e volta ao mesmo estado."""

import re
from urllib.parse import parse_qs, urlparse

import pytest
from django.urls import reverse

from catalogo import views_formularios
from catalogo.models import (
    CentroCusto,
    CentroFormulario,
    ExcecaoMaterial,
    Formulario,
    Material,
    ParDePara,
)
from tests.cenario import montar_cenario
from tests.config_cenario import criar_centro, material, usuarios

pytestmark = pytest.mark.django_db

PAGINA = reverse("catalogo:formularios")
CENTROS = reverse("catalogo:formularios_centros")
EXCECAO = reverse("catalogo:formularios_excecao")
FITA = "016.005.010"
BOTINA = "013.006.001"
CAPACETE_OCULTO = "030.004.001"


@pytest.fixture(autouse=True)
def cenario():
    montar_cenario()


@pytest.fixture
def admin(client):
    client.force_login(usuarios()["admin"])
    return client


def texto(resposta):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", resposta.text))


def volta(resposta) -> dict:
    assert resposta.status_code == 302
    url = urlparse(resposta["Location"])
    assert url.path == PAGINA
    return {k: v[0] for k, v in parse_qs(url.query).items()}


# --- A página e o seletor de formulário --------------------------------------------------------


def test_a_pagina_abre_no_primeiro_formulario_e_mostra_as_duas_abas(admin):
    r = admin.get(PAGINA)
    assert r.status_code == 200
    assert "Limpeza, copa e escritório" in r.text
    assert 'id="aba-centros"' in r.text and 'id="aba-materiais"' in r.text
    assert 'id="painel-centros"' in r.text and 'id="painel-materiais"' in r.text


def test_filtros_das_duas_abas_se_aplicam_sozinhos_com_javascript(admin):
    # O botão "Filtrar" só existe sem JavaScript; com ele, o filtros.js envia ao mudar um campo.
    for aba in ("centros", "materiais"):
        r = admin.get(PAGINA, {"aba": aba})
        assert len(re.findall(r'<form class="filtros"[^>]*data-filtros-auto>', r.text)) == 1


def test_acoes_por_linha_mantem_a_rolagem_ao_voltar(admin):
    # O rolagem.js guarda a posição no envio e a devolve na página que o redirecionamento abre.
    r = admin.get(PAGINA, {"aba": "materiais"})
    assert "interface/js/rolagem.js" in r.text
    assert re.search(r'<form method="post"[^>]*class="acoes" data-manter-rolagem>', r.text)


def test_formulario_invalido_volta_ao_primeiro_sem_erro(admin):
    r = admin.get(PAGINA, {"formulario": "AVULSA", "aba": "centros"})
    assert r.status_code == 200 and "Destinos de Limpeza, copa e escritório" in r.text


@pytest.mark.parametrize("formulario", Formulario.values)
def test_cada_um_dos_cinco_formularios_abre(admin, formulario):
    r = admin.get(PAGINA, {"formulario": formulario, "aba": "centros"})
    assert r.status_code == 200
    assert f"Destinos de {Formulario(formulario).label}" in r.text
    assert f"formulario={formulario}" in r.text  # a URL das abas leva o formulário


def test_a_aba_vem_da_url_e_o_padrao_e_materiais(admin):
    ativa = 'class="aba aba-ativa" id="aba-'
    assert f'{ativa}materiais"' in admin.get(PAGINA).text
    assert f'{ativa}centros"' in admin.get(PAGINA, {"aba": "centros"}).text
    assert f'{ativa}materiais"' in admin.get(PAGINA, {"aba": "nada"}).text


def test_a_aba_centros_nao_calcula_a_de_materiais(admin, monkeypatch):
    def falha(*args, **kwargs):
        raise AssertionError("a aba Materiais não deve ser calculada")

    monkeypatch.setattr(views_formularios, "situacao_do_formulario", falha)
    monkeypatch.setattr(views_formularios, "_contexto_materiais", falha)
    r = admin.get(PAGINA, {"formulario": "AB", "aba": "centros"})
    assert r.status_code == 200
    assert "Destinos de" in r.text and 'id="painel-materiais"' in r.text
    assert "Abrir a aba Materiais" in r.text


def test_a_aba_materiais_nao_calcula_a_de_centros(admin, monkeypatch):
    def falha(*args, **kwargs):
        raise AssertionError("a aba Centros não deve ser calculada")

    monkeypatch.setattr(views_formularios, "_contexto_centros", falha)
    r = admin.get(PAGINA, {"aba": "materiais"})
    assert r.status_code == 200
    assert "Abrir a aba Centros de custo" in r.text and "Destinos de" not in r.text


def test_o_painel_vazio_carrega_pelo_htmx_com_os_parametros_da_url(admin):
    r = admin.get(PAGINA, {"aba": "materiais", "formulario": "AB", "qc": "novo", "q": "fita"})
    painel = re.search(r'<section[^>]*id="painel-centros"[^>]*>', r.text).group(0)
    # Sem `once`: o pedido só dispara enquanto o painel vazio está à vista, então uma falha na
    # primeira abertura não impede a nova tentativa, e depois de carregado ele não pede mais.
    assert "hx-trigger=\"abas:ativada[this.querySelector('.aba-vazia')]\"" in painel
    assert 'class="cartao pilha aba-vazia"' in r.text
    url = re.search(r'hx-get="([^"]+)"', painel).group(1).replace("&amp;", "&")
    consulta = parse_qs(urlparse(url).query)
    assert urlparse(url).path == PAGINA
    assert consulta == {"formulario": ["AB"], "aba": ["centros"], "qc": ["novo"], "q": ["fita"]}
    # o painel da aba ativa não tem hx-get
    assert "hx-get" not in re.search(r'<section[^>]*id="painel-materiais"[^>]*>', r.text).group(0)
    # sem JavaScript, o mesmo endereço é um link comum
    assert f'href="{url.replace("&", "&amp;")}"' in r.text


def test_o_htmx_com_o_alvo_da_aba_devolve_so_o_parcial(admin):
    dados = {"formulario": "AB", "aba": "materiais"}
    alvo_centros = {"HX-Request": "true", "HX-Target": "section#painel-centros"}
    alvo_materiais = {"HX-Request": "true", "HX-Target": "section#painel-materiais"}
    r = admin.get(PAGINA, dados, headers=alvo_centros)
    assert r.status_code == 200
    assert "<html" not in r.text and "Destinos de" in r.text
    assert "HX-Target" in r["Vary"]
    r = admin.get(PAGINA, {**dados, "aba": "centros"}, headers=alvo_materiais)
    assert "<html" not in r.text and "Destinos de" not in r.text and "filtros" in r.text
    # ao restaurar o histórico o HTMX também manda HX-Request, mas quer a página inteira
    r = admin.get(PAGINA, dados, headers={**alvo_centros, "HX-History-Restore-Request": "true"})
    assert "<html" in r.text


def test_a_pagina_exige_login(client):
    r = client.get(PAGINA)
    assert r.status_code == 302 and "/entrar/" in r["Location"]


def test_o_menu_tem_o_item_formularios(admin):
    r = admin.get(reverse("catalogo:curva"))
    assert f'href="{PAGINA}"' in r.text and "Formulários" in r.text


# --- Aba Centros de custo ----------------------------------------------------------------------


def test_a_aba_de_centros_lista_as_linhas_com_o_estado_em_texto(admin):
    criar_centro("SETOR PARADO", "88", formularios=[Formulario.LIMPEZA], ativo=False)
    criar_centro("SETOR FORA", "89")
    r = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros"})
    painel = r.text.split('id="painel-centros"')[1].split('id="painel-materiais"')[0]
    assert "ETA I" in painel and "Destino" in painel
    assert "PICKUP 01" in painel and "ABC1D23" in painel
    parado = painel.split("SETOR PARADO")[1].split("</tr>")[0]
    assert "Inativo" in parado and "sem efeito: inativo" in parado
    fora = painel.split("SETOR FORA")[1].split("</tr>")[0]
    assert "Não é destino" in fora and "Habilitar" in fora


def test_o_resumo_conta_as_linhas_do_formulario(admin):
    total = CentroCusto.objects.count()
    r = admin.get(PAGINA, {"formulario": "VIATURAS", "aba": "centros"})
    assert f"0 de {total} linhas são destino deste formulário" in texto(r)
    r = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros"})
    assert f"{total} de {total} linhas são destino deste formulário" in texto(r)


def test_a_busca_de_centros_filtra_por_descricao_codigo_ou_placa(admin):
    for termo, esperado, ausente in [
        ("eta ii", "ETA II", "ETA I <span"),
        ("ABC1D23", "PICKUP 01", "RETRO A"),
        ("41", "RETRO A", "PICKUP 01"),
    ]:
        painel = admin.get(PAGINA, {"formulario": "AB", "aba": "centros", "qc": termo}).text
        painel = painel.split('id="painel-centros"')[1].split('id="painel-materiais"')[0]
        assert esperado in painel and ausente not in painel.split("<tbody>")[1]


def test_nas_viaturas_a_escolha_e_pela_descricao_com_todas_as_linhas_juntas(admin):
    from tests.viaturas_cenario import EQUIPE, montar_viaturas

    montar_viaturas()
    r = admin.get(PAGINA, {"formulario": "VIATURAS", "aba": "centros"})
    painel = r.text.split('id="painel-centros"')[1].split('id="painel-materiais"')[0]
    linha = painel.split(EQUIPE)[1].split("</tr>")[0]
    assert "Destino (1 de 2)" in linha and "Habilitar todas" in linha
    assert painel.count('name="centro"') >= 2  # a descrição envia todas as linhas
    # No modo padrão cada linha tem a sua placa e o seu botão.
    r = admin.get(PAGINA, {"formulario": "AB", "aba": "centros"})
    assert "AAA1A11" in r.text and "BBB2B22" in r.text


def test_habilitar_cria_a_associacao_e_volta_ao_mesmo_estado(admin):
    centro = criar_centro("SETOR NOVO", "90")
    r = admin.post(
        CENTROS,
        {"formulario": "AB", "centro": [centro.pk], "habilitado": "1", "qc": "novo"},
    )
    assert volta(r) == {"formulario": "AB", "aba": "centros", "qc": "novo"}
    assert CentroFormulario.objects.filter(centro=centro, formulario="AB").exists()
    assert not CentroFormulario.objects.filter(centro=centro, formulario="LIMPEZA").exists()
    assert ultima_mensagem(r) == "1 linha habilitada em Ferramentas, peças e materiais."


def test_desabilitar_e_idempotente(admin):
    centro = criar_centro("SETOR NOVO", "90", formularios=[Formulario.AB])
    corpo = {"formulario": "AB", "centro": [centro.pk], "habilitado": "0"}
    admin.post(CENTROS, corpo)
    assert not CentroFormulario.objects.filter(centro=centro).exists()
    r = admin.post(CENTROS, corpo)
    assert ultima_mensagem(r) == "Nada mudou: os centros já estavam assim."


def test_id_inexistente_e_ignorado_e_sem_id_avisa(admin):
    r = admin.post(CENTROS, {"formulario": "AB", "centro": ["999999", "x"], "habilitado": "1"})
    assert ultima_mensagem(r) == "Nada mudou: os centros já estavam assim."
    r = admin.post(CENTROS, {"formulario": "AB", "habilitado": "1"})
    assert ultima_mensagem(r) == "Nenhum centro de custo foi escolhido."


def test_formulario_invalido_na_gravacao_e_400(admin):
    assert (
        admin.post(CENTROS, {"formulario": "AVULSA", "centro": [1], "habilitado": "1"}).status_code
        == 400
    )
    assert admin.post(CENTROS, {"centro": [1], "habilitado": "1"}).status_code == 400


def test_as_gravacoes_so_aceitam_post(admin):
    assert admin.get(CENTROS).status_code == 405
    assert admin.get(EXCECAO).status_code == 405


# --- Aba Materiais -----------------------------------------------------------------------------


def linha_de(corpo: str, codigo: str) -> str:
    """A linha (`<tr>`) da tabela que mostra o material de `codigo`."""
    return next(t for t in corpo.split("<tr>") if f'<span class="mono">{codigo}</span>' in t)


def ultima_mensagem(resposta) -> str:
    return [m.message for m in resposta.wsgi_request._messages][-1]


def linhas_da_aba(resposta) -> str:
    painel = resposta.text.split('id="painel-materiais"')[1]
    return painel.split("<tbody>")[1].split("</tbody>")[0]


def test_a_lista_so_tem_material_visivel_e_mostra_estado_e_origem(admin):
    r = admin.get(PAGINA, {"formulario": "AB", "aba": "materiais"})
    corpo = linhas_da_aba(r)
    assert CAPACETE_OCULTO not in corpo  # oculto no cadastro: só na consulta por material
    linha = linha_de(corpo, FITA)
    assert "Disponível" in linha and "pela regra do formulário" in linha and "Retirar" in linha
    detergente = linha_de(corpo, "023.001.002")
    assert "Não disponível" in detergente and "Acrescentar" in detergente  # da limpeza, fora do AB
    assert "fora da regra do formulário" in detergente


def test_a_linha_mostra_unidade_grupo_e_saldo_so_como_informacao(admin):
    corpo = linhas_da_aba(admin.get(PAGINA, {"formulario": "AB", "aba": "materiais"}))
    linha = linha_de(corpo, "013.005.007")  # LUVA NITRÍLICA, sem saldo
    assert "saldo 0" in texto_do(linha) and "Disponível" in linha  # sem estoque, mas oferecido


def texto_do(trecho: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", trecho))


def test_busca_por_codigo_e_por_nome_sem_acento_e_filtros(admin):
    def achados(**filtros):
        r = admin.get(PAGINA, {"formulario": "AB", "aba": "materiais", **filtros})
        return re.findall(
            r'<span class="mono">(\d{3}\.\d{3}\.\d{3})</span>\s*(?:·|<)', linhas_da_aba(r)
        )

    assert FITA in achados(q="veda rosca") and BOTINA not in achados(q="veda rosca")
    assert achados(q="016.005.010") == [FITA]
    assert "023.004.001" in achados(q="papel higienico")  # sem acento
    assert set(achados(grupo="EPI")) == {BOTINA, "013.005.007"}
    assert achados(grupo="EPI", q="botina") == [BOTINA]
    assert achados(estado="disponivel") and FITA in achados(estado="disponivel")
    assert FITA not in achados(estado="indisponivel") and "023.001.002" in achados(
        estado="indisponivel"
    )
    assert achados(estado="excecao") == []


def test_filtro_com_valor_desconhecido_some_e_a_lista_nao_quebra(admin):
    r = admin.get(
        PAGINA, {"formulario": "AB", "aba": "materiais", "grupo": "NAO EXISTE", "estado": "x"}
    )
    assert r.status_code == 200 and FITA in linhas_da_aba(r)


def test_paginacao_de_50_no_servidor(admin):
    for i in range(120):
        material(f"700.000.{i:03d}", f"ITEM {i:03d}", "MUITOS")
    r = admin.get(PAGINA, {"formulario": "AB", "aba": "materiais", "grupo": "MUITOS"})
    assert linhas_da_aba(r).count("<tr ") == 50
    assert "Página 1 de 3" in texto(r) and "120 materiais no total" in texto(r)
    r = admin.get(
        PAGINA, {"formulario": "AB", "aba": "materiais", "grupo": "MUITOS", "pagina": "3"}
    )
    assert linhas_da_aba(r).count("<tr ") == 20
    fora = admin.get(
        PAGINA, {"formulario": "AB", "aba": "materiais", "grupo": "MUITOS", "pagina": "99"}
    )
    assert "Página 3 de 3" in texto(fora)


def test_a_lista_nao_carrega_o_catalogo_inteiro(admin, django_assert_max_num_queries):
    for i in range(200):
        material(f"700.000.{i:03d}", f"ITEM {i:03d}", "MUITOS")
    with django_assert_max_num_queries(40):
        admin.get(PAGINA, {"formulario": "AB", "aba": "materiais"})


def test_excecao_acrescentar_retirar_e_restaurar(admin):
    corpo = {"formulario": "AB", "q": "veda", "grupo": "", "estado": "", "pagina": "1"}
    r = admin.post(EXCECAO, {**corpo, "codigo": FITA, "acao": "retirar"})
    assert volta(r) == {"formulario": "AB", "aba": "materiais", "q": "veda", "pagina": "1"}
    assert ExcecaoMaterial.objects.get().habilitado is False
    assert ultima_mensagem(r) == (
        f"{FITA} — FITA VEDA ROSCA deixou de ser oferecido em Ferramentas, peças e materiais."
    )
    linha = linhas_da_aba(admin.get(PAGINA, {"formulario": "AB", "aba": "materiais", "q": "veda"}))
    # Acrescentar já apaga a exceção (a regra dá o resultado): um botão só na linha.
    assert "retirado pelo administrador" in linha and "Acrescentar" in linha
    assert "Voltar à regra" not in linha
    admin.post(EXCECAO, {**corpo, "codigo": FITA, "acao": "acrescentar"})
    assert not ExcecaoMaterial.objects.exists()  # a regra já oferece: a exceção é apagada
    ExcecaoMaterial.objects.create(
        material=Material.objects.get(codigo=FITA), formulario="AB", habilitado=False
    )
    r = admin.post(EXCECAO, {**corpo, "codigo": FITA, "acao": "restaurar"})
    assert not ExcecaoMaterial.objects.exists()
    assert "voltou à regra" in ultima_mensagem(r)
    novo = material("900.000.001", "TESOURA", "ALMOX")
    admin.post(EXCECAO, {"formulario": "AB", "codigo": novo.codigo, "acao": "acrescentar"})
    assert ExcecaoMaterial.objects.get().habilitado is True
    r = admin.post(EXCECAO, {"formulario": "AB", "codigo": novo.codigo, "acao": "acrescentar"})
    assert "Nada mudou" in ultima_mensagem(r)


def test_acao_invalida_e_400_e_material_inexistente_e_404(admin):
    assert (
        admin.post(EXCECAO, {"formulario": "AB", "codigo": FITA, "acao": "apagar"}).status_code
        == 400
    )
    assert (
        admin.post(EXCECAO, {"formulario": "XX", "codigo": FITA, "acao": "retirar"}).status_code
        == 400
    )
    assert (
        admin.post(
            EXCECAO, {"formulario": "AB", "codigo": "000.000.000", "acao": "retirar"}
        ).status_code
        == 404
    )


def test_a_excecao_vale_so_no_formulario_pedido(admin):
    admin.post(EXCECAO, {"formulario": "AB", "codigo": FITA, "acao": "retirar"})
    assert ExcecaoMaterial.objects.get().formulario == "AB"
    linha = linhas_da_aba(
        admin.get(PAGINA, {"formulario": "VIATURAS", "aba": "materiais", "q": "veda"})
    )
    assert "pela regra do formulário" in linha  # nas viaturas continua


def test_exceção_sem_efeito_e_marcada(admin):
    ExcecaoMaterial.objects.create(
        material=Material.objects.get(codigo=FITA), formulario="AB", habilitado=True
    )
    linha = linhas_da_aba(admin.get(PAGINA, {"formulario": "AB", "aba": "materiais", "q": "veda"}))
    # Sem efeito: restaurar a regra padrão do formulário é que a limpa, não um botão por linha.
    assert "Exceção sem efeito" in linha and "Voltar à regra" not in linha


def test_codigo_antigo_de_um_par_de_para_avisa_o_canonico(admin):
    ParDePara.objects.create(antigo="023.004.001", novo=FITA, fator=1)
    linha = linhas_da_aba(admin.get(PAGINA, {"formulario": "AB", "aba": "materiais", "q": "papel"}))
    assert "Código antigo" in linha and FITA in linha


def test_material_duplicado_e_marcado(admin):
    Material.objects.filter(codigo=FITA).update(duplicado=True)
    linha = linhas_da_aba(admin.get(PAGINA, {"formulario": "AB", "aba": "materiais", "q": "veda"}))
    assert "Cadastro duplicado" in linha


# --- Lote: prévia e confirmação (US3) ----------------------------------------------------------

LOTE = reverse("catalogo:formularios_lote")


def previa(cliente, **parametros):
    return cliente.get(LOTE, {"formulario": "AB", "acao": "retirar", **parametros})


def grupo_do_lote(n=20):
    return [material(f"800.000.{i:03d}", f"PECA {i:02d}", "LOTE") for i in range(n)]


def test_a_previa_mostra_formulario_acao_numero_exato_e_amostra(admin):
    grupo_do_lote(20)
    r = previa(admin, acao="acrescentar", grupo="LOTE")
    assert r.status_code == 200
    t = texto(r)
    assert "Ferramentas, peças e materiais" in t and "Acrescentar ao formulário" in t
    assert "20 materiais" in t
    assert "PECA 00" in t and "PECA 09" in t and "PECA 10" not in t  # a amostra tem 10
    assert 'name="total" value="20"' in r.text
    assert 'name="ciente"' not in r.text  # com filtro, não pede o "ciente"


def test_a_previa_sem_filtro_alcanca_o_catalogo_inteiro_e_pede_o_ciente(admin):
    total = Material.objects.filter(oculto=False).count()
    r = previa(admin)
    assert f"{total} materiais" in texto(r) and "catálogo inteiro" in texto(r)
    assert 'name="ciente"' in r.text and "required" in r.text.split('name="ciente"')[1][:200]


def test_previa_com_acao_ou_formulario_invalido_e_400(admin):
    assert admin.get(LOTE, {"formulario": "AB", "acao": "restaurar"}).status_code == 400
    assert admin.get(LOTE, {"formulario": "AB"}).status_code == 400
    assert admin.get(LOTE, {"formulario": "XX", "acao": "retirar"}).status_code == 400


def test_confirmar_aplica_a_todos_do_filtro_e_so_a_eles(admin):
    grupo_do_lote(20)
    r = admin.post(
        LOTE, {"formulario": "AB", "acao": "acrescentar", "grupo": "LOTE", "total": "20"}
    )
    assert volta(r) == {"formulario": "AB", "aba": "materiais", "grupo": "LOTE"}
    assert ExcecaoMaterial.objects.count() == 20
    assert set(ExcecaoMaterial.objects.values_list("formulario", flat=True)) == {"AB"}
    assert (
        ultima_mensagem(r) == "20 mudaram e 0 já estavam assim em Ferramentas, peças e materiais."
    )
    corpo = linhas_da_aba(
        admin.get(PAGINA, {"formulario": "AB", "aba": "materiais", "grupo": "LOTE"})
    )
    assert corpo.count("acrescentado pelo administrador") == 20


def test_o_lote_vale_para_todas_as_paginas_do_filtro(admin):
    grupo_do_lote(120)
    admin.post(LOTE, {"formulario": "AB", "acao": "acrescentar", "grupo": "LOTE", "total": "120"})
    assert ExcecaoMaterial.objects.count() == 120


def test_total_diferente_recusa_e_volta_a_previa_com_o_numero_atual(admin):
    grupo_do_lote(20)
    r = admin.post(
        LOTE, {"formulario": "AB", "acao": "acrescentar", "grupo": "LOTE", "total": "15"}
    )
    assert r.status_code == 302
    url = urlparse(r["Location"])
    assert url.path == LOTE and parse_qs(url.query)["grupo"] == ["LOTE"]
    assert not ExcecaoMaterial.objects.exists()
    assert (
        "mudou" in ultima_mensagem(r) and "15" in ultima_mensagem(r) and "20" in ultima_mensagem(r)
    )


def test_sem_filtro_exige_o_ciente_para_aplicar(admin):
    total = Material.objects.filter(oculto=False).count()
    corpo = {"formulario": "AB", "acao": "retirar", "total": str(total)}
    r = admin.post(LOTE, corpo)
    assert urlparse(r["Location"]).path == LOTE and not ExcecaoMaterial.objects.exists()
    assert "ciente" in ultima_mensagem(r)
    r = admin.post(LOTE, {**corpo, "ciente": "1"})
    assert urlparse(r["Location"]).path == PAGINA
    assert ExcecaoMaterial.objects.filter(formulario="AB", habilitado=False).exists()


def test_retirar_em_lote_com_filtro_de_estado(admin):
    r = admin.post(
        LOTE, {"formulario": "AB", "acao": "retirar", "estado": "disponivel", "total": "3"}
    )
    assert ultima_mensagem(r).startswith("3 mudaram")
    assert {e.material.codigo for e in ExcecaoMaterial.objects.all()} == {
        FITA,
        BOTINA,
        "013.005.007",
    }


def test_o_lote_nao_mexe_nos_outros_formularios_nem_no_cadastro(admin):
    grupo_do_lote(5)
    antes = list(Material.objects.values_list("codigo", "estoque", "oculto"))
    admin.post(
        LOTE, {"formulario": "OFICINA", "acao": "acrescentar", "grupo": "LOTE", "total": "5"}
    )
    assert set(ExcecaoMaterial.objects.values_list("formulario", flat=True)) == {"OFICINA"}
    assert list(Material.objects.values_list("codigo", "estoque", "oculto")) == antes


def test_a_previa_para_quem_so_ve_nao_tem_o_botao_de_confirmar(client):
    client.force_login(usuarios()["comum"])
    r = previa(client, grupo="EPI")
    assert r.status_code == 200 and 'name="total"' not in r.text
    assert "permissão" in texto(r)


def test_aplicar_sem_permissao_e_403(client):
    client.force_login(usuarios()["comum"])
    r = client.post(LOTE, {"formulario": "AB", "acao": "retirar", "grupo": "EPI", "total": "2"})
    assert r.status_code == 403 and not ExcecaoMaterial.objects.exists()


def test_o_botao_do_lote_aparece_na_aba_para_quem_pode_e_leva_o_filtro(admin):
    r = admin.get(PAGINA, {"formulario": "AB", "aba": "materiais", "grupo": "EPI"})
    assert f'href="{LOTE}?' in r.text and "acao=retirar" in r.text and "acao=acrescentar" in r.text
    assert "grupo=EPI" in r.text and "Retirar todos os 2 resultados" in texto(r)
    assert "Acrescentar todos os 2 resultados" in texto(r)


# --- Onde um material aparece (US4) ------------------------------------------------------------


def onde(codigo):
    return reverse("catalogo:formularios_material", args=[codigo])


def test_a_consulta_mostra_os_cinco_formularios_com_estado_e_origem(admin):
    from tests.config_cenario import excecao

    excecao(Formulario.OFICINA, Material.objects.get(codigo=FITA), True)
    excecao(Formulario.EPIS, Material.objects.get(codigo=FITA), False)
    excecao(Formulario.AB, Material.objects.get(codigo=FITA), True)  # o AB já traz: sem efeito
    r = admin.get(onde(FITA))
    assert r.status_code == 200
    t = texto(r)
    for nome in (
        "Limpeza, copa e escritório",
        "Ferramentas, peças e materiais",
        "Reposição de peças das viaturas",
        "Oficina mecânica",
        "Equipamentos de proteção individual (EPIs)",
    ):
        assert nome in t
    linhas = {
        f: next(x for x in r.text.split("<tr>") if f'data-formulario="{f}"' in x)
        for f in Formulario.values
    }
    assert "pela regra do formulário" in linhas["AB"] and "Disponível" in linhas["AB"]
    assert "pela regra do formulário" in linhas["VIATURAS"]
    assert "acrescentado pelo administrador" in linhas["OFICINA"]
    assert "Não disponível" in linhas["EPIS"] and "fora da regra do formulário" in linhas["EPIS"]
    assert "Exceção sem efeito" in linhas["AB"]


def test_retirado_e_marcado_como_retirado(admin):
    from tests.config_cenario import excecao

    excecao(Formulario.AB, Material.objects.get(codigo=FITA), False)
    linha = next(x for x in admin.get(onde(FITA)).text.split("<tr>") if 'data-formulario="AB"' in x)
    assert "Não disponível" in linha and "retirado pelo administrador" in linha


def test_oculto_e_duplicado_valem_em_todos_os_formularios(admin):
    r = admin.get(onde(CAPACETE_OCULTO))
    assert r.status_code == 200 and r.text.count("Oculto no cadastro") >= 5
    assert "o cadastro do SCPI o oculta em todos os formulários" in texto(r)
    Material.objects.filter(codigo=FITA).update(duplicado=True)
    assert "Cadastro duplicado" in texto(admin.get(onde(FITA)))


def test_codigo_inexistente_e_404(admin):
    assert admin.get(onde("000.000.000")).status_code == 404


def test_a_consulta_e_aberta_a_quem_so_ve_e_exige_login(client):
    assert "/entrar/" in client.get(onde(FITA))["Location"]
    client.force_login(usuarios()["comum"])
    assert client.get(onde(FITA)).status_code == 200


def test_o_link_da_lista_leva_a_consulta_do_material(admin):
    r = admin.get(PAGINA, {"formulario": "AB", "aba": "materiais", "q": "veda"})
    assert f'href="{onde(FITA)}"' in r.text


def test_a_consulta_leva_de_volta_ao_material_na_lista_do_formulario(admin):
    r = admin.get(onde(FITA))
    assert "formulario=AB" in r.text and f"q={FITA}" in r.text


# --- Ativar e inativar o centro (US5) ----------------------------------------------------------

ATIVO = reverse("catalogo:formularios_ativo")


def test_inativar_e_ativar_pela_pagina_e_volta_ao_mesmo_estado(admin):
    centro = criar_centro("SETOR NOVO", "90", formularios=[Formulario.AB, Formulario.EPIS])
    r = admin.post(ATIVO, {"formulario": "AB", "centro": [centro.pk], "ativo": "0", "qc": "novo"})
    assert volta(r) == {"formulario": "AB", "aba": "centros", "qc": "novo"}
    assert CentroCusto.objects.get(pk=centro.pk).ativo is False
    assert ultima_mensagem(r) == "1 linha inativada."
    assert CentroFormulario.objects.filter(centro=centro).count() == 2  # a escolha fica guardada
    r = admin.post(ATIVO, {"formulario": "AB", "centro": [centro.pk], "ativo": "1"})
    assert CentroCusto.objects.get(pk=centro.pk).ativo is True
    assert ultima_mensagem(r) == "1 linha ativada."


def test_inativar_de_novo_nao_muda_nada_e_sem_id_avisa(admin):
    centro = criar_centro("SETOR NOVO", "90", ativo=False)
    r = admin.post(ATIVO, {"formulario": "AB", "centro": [centro.pk], "ativo": "0"})
    assert ultima_mensagem(r) == "Nada mudou: os centros já estavam assim."
    r = admin.post(ATIVO, {"formulario": "AB", "ativo": "0"})
    assert ultima_mensagem(r) == "Nenhum centro de custo foi escolhido."


def test_a_aba_mostra_inativar_ou_ativar_conforme_o_estado(admin):
    criar_centro("SETOR PARADO", "88", formularios=[Formulario.LIMPEZA], ativo=False)
    criar_centro("SETOR VIVO", "89", formularios=[Formulario.LIMPEZA])
    painel = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros"}).text
    painel = painel.split('id="painel-centros"')[1].split('id="painel-materiais"')[0]
    assert "Ativar" in painel.split("SETOR PARADO")[1].split("</tr>")[0]
    assert "Inativar" in painel.split("SETOR VIVO")[1].split("</tr>")[0]


def test_nas_viaturas_inativar_vale_para_todas_as_linhas_da_descricao(admin):
    from tests.viaturas_cenario import EQUIPE, montar_viaturas

    montar_viaturas()
    ids = list(CentroCusto.objects.filter(descricao=EQUIPE).values_list("pk", flat=True))
    admin.post(ATIVO, {"formulario": "VIATURAS", "centro": ids, "ativo": "0"})
    assert not CentroCusto.objects.filter(descricao=EQUIPE, ativo=True).exists()
    painel = admin.get(PAGINA, {"formulario": "VIATURAS", "aba": "centros"}).text
    assert "Ativar" in painel.split(EQUIPE)[1].split("</tr>")[0]


def test_ativar_so_aceita_post_e_exige_a_permissao(client):
    assert usuarios() and client.get(ATIVO).status_code in (302, 405)
    client.force_login(usuarios()["comum"])
    assert client.get(ATIVO).status_code == 405
    centro = criar_centro("SETOR NOVO", "90")
    r = client.post(ATIVO, {"formulario": "AB", "centro": [centro.pk], "ativo": "0"})
    assert r.status_code == 403 and CentroCusto.objects.get(pk=centro.pk).ativo is True


def test_filtro_invalido_no_lote_e_erro_e_nao_alarga_o_alcance(admin):
    """Na lista o filtro desconhecido some; no lote alargaria o alcance sem ninguém ver."""
    assert previa(admin, grupo="GRUPO QUE NAO EXISTE").status_code == 400
    r = admin.post(
        LOTE,
        {
            "formulario": "AB",
            "acao": "retirar",
            "grupo": "GRUPO QUE NAO EXISTE",
            "total": "1",
            "ciente": "1",
        },
    )
    assert r.status_code == 400 and not ExcecaoMaterial.objects.exists()


def test_a_previa_diz_os_filtros_em_palavras(admin):
    r = previa(admin, grupo="EPI", estado="disponivel", q="botina")
    t = texto(r)
    assert (
        "Grupo EPI" in t and "No formulário Disponíveis no formulário" in t and "Busca botina" in t
    )


# --- Convergência: outros formulários do centro e atalho para o admin ---------------------------


def test_cada_linha_mostra_em_quais_outros_formularios_o_centro_e_destino(admin):
    criar_centro(
        "SETOR EM TRES", "70", formularios=[Formulario.LIMPEZA, Formulario.OFICINA, Formulario.EPIS]
    )
    criar_centro("SETOR SO AQUI", "71", formularios=[Formulario.AB])
    painel = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros", "qc": "SETOR"}).text
    painel = painel.split('id="painel-centros"')[1].split('id="painel-materiais"')[0]
    tres = painel.split("SETOR EM TRES")[1].split("</tr>")[0]
    assert "Também em: Oficina mecânica, Equipamentos de proteção individual (EPIs)" in texto_do(
        tres
    )
    aqui = painel.split("SETOR SO AQUI")[1].split("</tr>")[0]
    assert "Não é destino" in aqui and "Também em: Ferramentas, peças e materiais" in texto_do(aqui)


def test_o_centro_so_deste_formulario_nao_tem_a_linha_tambem_em(admin):
    criar_centro("SETOR SOZINHO", "72", formularios=[Formulario.LIMPEZA])
    painel = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros", "qc": "SOZINHO"}).text
    assert "Também em" not in painel


def test_nas_viaturas_o_tambem_em_junta_as_linhas_da_descricao(admin):
    from tests.viaturas_cenario import EQUIPE, montar_viaturas

    montar_viaturas()
    painel = admin.get(PAGINA, {"formulario": "VIATURAS", "aba": "centros", "qc": EQUIPE}).text
    linha = painel.split("<tbody>")[1].split("</tr>")[0]
    assert "Também em: Limpeza, copa e escritório, Ferramentas, peças e materiais" in texto_do(
        linha
    )


def test_o_atalho_de_criar_e_editar_centro_aparece_a_quem_o_admin_permite(client):
    criar_centro("SETOR NOVO", "90", formularios=[Formulario.AB])
    add = reverse("admin:catalogo_centrocusto_add")
    client.force_login(usuarios()["admin"])
    r = client.get(PAGINA, {"formulario": "AB", "aba": "centros", "qc": "SETOR NOVO"})
    assert f'href="{add}"' in r.text and "Criar centro de custo" in texto(r)
    centro = CentroCusto.objects.get(descricao="SETOR NOVO")
    assert f'href="{reverse("admin:catalogo_centrocusto_change", args=[centro.pk])}"' in r.text
    client.force_login(usuarios()["comum"])
    r = client.get(PAGINA, {"formulario": "AB", "aba": "centros", "qc": "SETOR NOVO"})
    assert f'href="{add}"' not in r.text and "Editar" not in texto(r)


def test_o_atalho_nas_viaturas_leva_a_lista_do_admin_filtrada_pela_descricao(admin):
    from tests.viaturas_cenario import EQUIPE, montar_viaturas

    montar_viaturas()
    r = admin.get(PAGINA, {"formulario": "VIATURAS", "aba": "centros", "qc": EQUIPE})
    lista = reverse("admin:catalogo_centrocusto_changelist")
    assert f'href="{lista}?q=EQUIPE%20NORTE"' in r.text


# --- Filtros da aba Centros de custo -----------------------------------------------------------


def _centros_listados(admin, **filtros) -> set[str]:
    """As descrições `FILTRO …` que a aba Centros de custo mostra com estes filtros."""
    parametros = {"formulario": "LIMPEZA", "aba": "centros", "qc": "FILTRO", **filtros}
    painel = admin.get(PAGINA, parametros).text
    tabela = painel.split('id="painel-centros"')[1].split('id="painel-materiais"')[0]
    return set(re.findall(r"FILTRO [A-Z]+", tabela.split("<tbody>")[1]))


@pytest.fixture
def centros_de_filtro():
    criar_centro("FILTRO ALFA", "801", "FIL1A11", formularios=[Formulario.LIMPEZA])
    criar_centro("FILTRO BETA", "802", formularios=[Formulario.AB])
    criar_centro("FILTRO GAMA", "803", "FIL2B22", ativo=False, formularios=[Formulario.LIMPEZA])
    criar_centro("FILTRO DELTA", "804")


def test_filtro_de_centros_por_ser_destino_do_formulario(admin, centros_de_filtro):
    assert _centros_listados(admin, centro_destino="sim") == {"FILTRO ALFA", "FILTRO GAMA"}
    assert _centros_listados(admin, centro_destino="nao") == {"FILTRO BETA", "FILTRO DELTA"}


def test_filtro_de_centros_por_estado(admin, centros_de_filtro):
    assert _centros_listados(admin, centro_estado="inativo") == {"FILTRO GAMA"}
    ativos = _centros_listados(admin, centro_estado="ativo")
    assert ativos == {"FILTRO ALFA", "FILTRO BETA", "FILTRO DELTA"}


def test_filtro_de_centros_por_placa(admin, centros_de_filtro):
    assert _centros_listados(admin, centro_placa="com") == {"FILTRO ALFA", "FILTRO GAMA"}
    assert _centros_listados(admin, centro_placa="sem") == {"FILTRO BETA", "FILTRO DELTA"}


def test_filtro_de_centros_por_uso_nos_formularios(admin, centros_de_filtro):
    # Ativo e sem destino em formulário nenhum: o inativo e o que já tem destino ficam de fora.
    assert _centros_listados(admin, centro_uso="sem_formulario") == {"FILTRO DELTA"}
    assert _centros_listados(admin, centro_uso="outros") == {"FILTRO BETA"}


def test_filtros_de_centros_se_combinam_e_valor_desconhecido_some(admin, centros_de_filtro):
    assert _centros_listados(
        admin, centro_destino="sim", centro_placa="com", centro_estado="ativo"
    ) == {"FILTRO ALFA"}
    todos = {"FILTRO ALFA", "FILTRO BETA", "FILTRO GAMA", "FILTRO DELTA"}
    assert _centros_listados(admin, centro_destino="talvez", centro_uso="x") == todos


def test_busca_de_centro_acha_a_placa_digitada_com_hifen(admin, centros_de_filtro):
    assert _centros_listados(admin, qc="fil1-a11") == {"FILTRO ALFA"}
    assert _centros_listados(admin, qc="filtro 802") == {"FILTRO BETA"}


def test_viaturas_nao_tem_filtro_de_placa(admin, centros_de_filtro):
    r = admin.get(PAGINA, {"formulario": "VIATURAS", "aba": "centros"})
    painel = r.text.split('id="painel-centros"')[1].split('id="painel-materiais"')[0]
    assert 'name="centro_placa"' not in painel and 'name="centro_uso"' in painel
    r = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros"})
    assert 'name="centro_placa"' in r.text


def test_gravar_na_aba_centros_volta_com_os_filtros(admin, centros_de_filtro):
    centro = CentroCusto.objects.get(descricao="FILTRO ALFA")
    r = admin.post(
        CENTROS,
        {
            "formulario": "LIMPEZA",
            "centro": [centro.pk],
            "habilitado": "0",
            "qc": "FILTRO",
            "centro_destino": "sim",
            "centro_estado": "ativo",
        },
    )
    assert volta(r) == {
        "formulario": "LIMPEZA",
        "aba": "centros",
        "qc": "FILTRO",
        "centro_destino": "sim",
        "centro_estado": "ativo",
    }
    # E a página que mostra os filtros os devolve às gravações da lista.
    painel = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros", "centro_uso": "outros"})
    assert 'name="centro_uso" value="outros"' in painel.text


# --- Paginação e linhas da aba Centros de custo ------------------------------------------------


def _tabela_de_centros(resposta) -> str:
    painel = resposta.text.split('id="painel-centros"')[1].split('id="painel-materiais"')[0]
    return painel.split("<tbody>")[1].split("</tbody>")[0]


def test_aba_centros_pagina_por_descricao_e_os_totais_valem_para_tudo(admin):
    for i in range(60):
        criar_centro(f"PAGINADO {i:02d}", f"9{i:02d}", formularios=[Formulario.LIMPEZA])
    base = {"formulario": "LIMPEZA", "aba": "centros", "qc": "PAGINADO"}
    primeira = admin.get(PAGINA, base)
    assert len(re.findall(r'<tr id="centro-', _tabela_de_centros(primeira))) == 50
    assert "60 de 60 linhas são destino" in texto(primeira)
    assert "Página 1 de 2" in texto(primeira)
    segunda = admin.get(PAGINA, {**base, "pagina_centros": 2})
    assert len(re.findall(r'<tr id="centro-', _tabela_de_centros(segunda))) == 10
    assert "PAGINADO 59" in segunda.text and "PAGINADO 00" not in _tabela_de_centros(segunda)
    # Página fora do intervalo cai na última, e a aba Materiais tem a sua própria paginação.
    assert "Página 2 de 2" in texto(admin.get(PAGINA, {**base, "pagina_centros": 99}))
    assert 'name="pagina_centros" value="2"' in segunda.text


def test_gravar_na_aba_centros_volta_para_a_mesma_pagina(admin):
    for i in range(60):
        criar_centro(f"PAGINADO {i:02d}", f"9{i:02d}", formularios=[Formulario.LIMPEZA])
    centro = CentroCusto.objects.get(descricao="PAGINADO 59")
    r = admin.post(
        CENTROS,
        {
            "formulario": "LIMPEZA",
            "centro": [centro.pk],
            "habilitado": "0",
            "qc": "PAGINADO",
            "pagina_centros": "2",
        },
    )
    assert volta(r)["pagina_centros"] == "2"


def test_linhas_das_tabelas_tem_id_para_piscar_depois_de_gravar(admin, centros_de_filtro):
    alfa = CentroCusto.objects.get(descricao="FILTRO ALFA")
    centros = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros", "qc": "FILTRO"})
    assert f'<tr id="centro-{alfa.pk}">' in centros.text
    materiais = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "materiais"})
    assert re.search(r'<tr id="material-\d+">', materiais.text)


def test_coluna_de_acoes_tem_largura_propria_nas_duas_abas(admin, centros_de_filtro):
    # Largura fixa por CSS (`celula-acoes`): a coluna não muda com a linha ter um botão ou dois.
    materiais = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "materiais"})
    assert '<td class="celula-acoes">' in materiais.text
    centros = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros", "qc": "FILTRO"})
    assert '<td class="celula-acoes">' in centros.text


def test_botoes_das_tabelas_tem_forma_e_cor_pelo_significado(admin, centros_de_filtro):
    # Incluir é azul, inativar (afeta todos os formulários) é vermelho, reativar é verde; nenhum é
    # só texto, e o "Editar" também é botão.
    pagina = {"formulario": "LIMPEZA", "aba": "centros", "qc": "FILTRO"}
    centros = admin.get(PAGINA, pagina).text
    assert 'class="botao botao-secundario botao-perigo">Inativar</button>' in centros
    assert 'class="botao botao-secundario botao-ok">Ativar</button>' in centros  # FILTRO GAMA
    assert 'class="botao botao-secundario botao-destaque">Habilitar</button>' in centros
    assert "botao-texto" not in centros.split("<tbody>")[1].split("</tbody>")[0]
    materiais = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "materiais"}).text
    assert 'botao-destaque">Acrescentar</button>' in materiais


# --- Restaurar a regra padrão do formulário -----------------------------------------------------

REGRA = reverse("catalogo:formularios_regra")


def _duas_excecoes(formulario="AB"):
    ExcecaoMaterial.objects.create(
        material=Material.objects.get(codigo=FITA), formulario=formulario, habilitado=False
    )
    novo = material("900.000.002", "TESOURA", "ALMOX")
    ExcecaoMaterial.objects.create(material=novo, formulario=formulario, habilitado=True)


def test_restaurar_regra_padrao_apaga_so_as_excecoes_do_formulario(admin):
    _duas_excecoes("AB")
    outra = Material.objects.get(codigo=BOTINA)
    ExcecaoMaterial.objects.create(material=outra, formulario="LIMPEZA", habilitado=True)
    r = admin.post(REGRA, {"formulario": "AB", "confirmado": "1"})
    assert volta(r) == {"formulario": "AB", "aba": "materiais"}
    assert not ExcecaoMaterial.objects.filter(formulario="AB").exists()
    assert ExcecaoMaterial.objects.filter(formulario="LIMPEZA").count() == 1
    assert ultima_mensagem(r) == (
        "Regra padrão restaurada em Ferramentas, peças e materiais: "
        "1 acrescentado removido e 1 retirado devolvido."
    )
    # Idempotente: sem exceções, nada muda.
    r = admin.post(REGRA, {"formulario": "AB", "confirmado": "1"})
    assert "Nada mudou" in ultima_mensagem(r)


def test_restaurar_regra_padrao_exige_confirmacao_e_formulario_valido(admin):
    _duas_excecoes("AB")
    r = admin.post(REGRA, {"formulario": "AB"})
    assert ExcecaoMaterial.objects.filter(formulario="AB").count() == 2
    assert "Confirme" in ultima_mensagem(r)
    assert admin.post(REGRA, {"formulario": "AVULSA", "confirmado": "1"}).status_code == 400
    assert admin.get(REGRA).status_code == 405
    assert ExcecaoMaterial.objects.filter(formulario="AB").count() == 2


def test_restaurar_regra_padrao_e_recusado_a_quem_nao_pode_alterar(client):
    _duas_excecoes("AB")
    client.force_login(usuarios()["comum"])
    r = client.post(REGRA, {"formulario": "AB", "confirmado": "1"})
    assert r.status_code == 403
    assert ExcecaoMaterial.objects.filter(formulario="AB").count() == 2


def test_aba_materiais_mostra_as_excecoes_e_o_reset_so_a_quem_pode(client):
    client.force_login(usuarios()["admin"])
    sem = client.get(PAGINA, {"formulario": "AB", "aba": "materiais"})
    assert "segue a regra padrão, sem exceções" in texto(sem)
    assert "Restaurar regra padrão" not in sem.text
    _duas_excecoes("AB")
    com = client.get(PAGINA, {"formulario": "AB", "aba": "materiais"})
    assert "2 exceções à regra padrão deste formulário (1 acrescentado e 1 retirado)" in texto(com)
    assert 'data-abrir-dialogo="dialogo-regra-padrao"' in com.text
    assert '<dialog class="dialogo-confirmacao" id="dialogo-regra-padrao"' in com.text
    assert 'name="confirmado" value="1"' in com.text and "data-fechar-dialogo" in com.text
    assert (
        'formmethod="dialog" class="botao botao-secundario" data-fechar-dialogo autofocus>Cancelar'
        in (com.text)
    )
    assert "1 material acrescentado deixa de ser oferecido e 1 retirado volta a ser oferecido" in (
        texto(com)
    )
    assert "Voltar à regra</button>" not in com.text  # nada de botão de restaurar por linha
    client.force_login(usuarios()["comum"])
    leitura = client.get(PAGINA, {"formulario": "AB", "aba": "materiais"})
    assert "2 exceções à regra padrão" in texto(leitura)
    assert "Restaurar regra padrão" not in leitura.text


def test_texto_da_restauracao_concorda_no_plural(admin):
    # Dois acrescentados e dois retirados: "materiais", nunca "materialis".
    for i in range(2):
        novo = material(f"900.000.1{i}0", f"MATERIAL EXTRA {i}", "ALMOX")
        ExcecaoMaterial.objects.create(material=novo, formulario="AB", habilitado=True)
    for codigo in (FITA, BOTINA):
        ExcecaoMaterial.objects.create(
            material=Material.objects.get(codigo=codigo), formulario="AB", habilitado=False
        )
    pagina = texto(admin.get(PAGINA, {"formulario": "AB", "aba": "materiais"}))
    assert "2 materiais acrescentados deixam de ser oferecidos" in pagina
    assert "2 retirados voltam a ser oferecidos" in pagina
    assert "materialis" not in pagina


def test_filtro_de_uso_nao_sugere_destino_do_formulario_aberto(admin):
    pagina = admin.get(PAGINA, {"formulario": "LIMPEZA", "aba": "centros"}).text
    assert "Destino em outro formulário" in pagina and "Destino também em" not in pagina
