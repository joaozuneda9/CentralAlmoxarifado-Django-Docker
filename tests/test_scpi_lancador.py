import logging
import os
from contextlib import nullcontext

import playwright.sync_api
import pytest
from playwright.sync_api import Error as ErroPlaywright
from playwright.sync_api import TimeoutError as TimeoutPlaywright

from scpi import lancador
from scpi.lancador import ErroAberturaFormulario, NavegadorSCPI, falha_de_abertura, linha_confere
from scpi.lancamento import SCPI
from scpi.requisicoes import ErroSCPI, Item, Requisicao


def test_navegador_implementa_o_protocolo_do_lancamento():
    metodos = {n for n in vars(SCPI) if not n.startswith("_")}
    assert metodos <= set(dir(NavegadorSCPI))


def test_lancador_nao_importa_playwright_no_topo():
    assert "sync_playwright" not in vars(lancador)


def test_navegador_libera_o_orm_enquanto_esta_aberto(monkeypatch):
    # A API síncrona do Playwright mantém um laço asyncio na thread enquanto o navegador está
    # aberto, e o lançamento grava no banco nesse meio (SynchronousOnlyOperation).
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: nullcontext(object()))
    monkeypatch.setattr(lancador.NavegadorSCPI, "abrir", lambda self: None)
    monkeypatch.delenv("DJANGO_ALLOW_ASYNC_UNSAFE", raising=False)
    with lancador.navegador():
        assert os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] == "true"
    assert "DJANGO_ALLOW_ASYNC_UNSAFE" not in os.environ


class _Teclado:
    def __init__(self):
        self.teclas = []

    def press(self, tecla):
        self.teclas.append(tecla)


class _Pagina:
    def __init__(self):
        self.keyboard = _Teclado()
        self.pausas = []

    def wait_for_timeout(self, ms):
        self.pausas.append(ms)


class _Quadro:
    """Frame mínimo: só o que as funções de recuperação tocam."""

    def __init__(self):
        self.page = _Pagina()

    def get_by_role(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    @property
    def first(self):
        return self


class _Entrada:
    def __init__(self, falhas):
        self.falhas = falhas
        self.preenchidos = []

    def fill(self, valor, timeout=None):
        from playwright.sync_api import TimeoutError as TimeoutPlaywright

        if self.falhas:
            self.falhas -= 1
            raise TimeoutPlaywright("Locator.fill: Timeout exceeded [waiting for input:focus]")
        self.preenchidos.append(valor)


def test_preencher_celula_reabre_o_editor_quando_o_foco_some(monkeypatch):
    abertas = []
    entrada = _Entrada(falhas=1)
    monkeypatch.setattr(
        lancador, "editar_celula", lambda frame, linha, coluna: abertas.append(coluna) or entrada
    )
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)

    assert lancador.preencher_celula(_Quadro(), 1, "QTD", "10") is entrada
    assert abertas == ["QTD", "QTD"]
    assert entrada.preenchidos == ["10"]


def test_preencher_celula_desiste_depois_das_tentativas(monkeypatch):
    entrada = _Entrada(falhas=99)
    monkeypatch.setattr(lancador, "editar_celula", lambda frame, linha, coluna: entrada)
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)

    with pytest.raises(TimeoutPlaywright):
        lancador.preencher_celula(_Quadro(), 0, "QTD", "1")
    assert entrada.falhas == 99 - lancador.TENTATIVAS_CELULA


def test_preencher_celula_tenta_de_novo_quando_o_editor_nao_abre(monkeypatch):
    entrada = _Entrada(falhas=0)
    chamadas = []

    def editar(frame, linha, coluna):
        chamadas.append(coluna)
        if len(chamadas) == 1:
            raise ErroSCPI("não consegui abrir a célula 'QTD' da linha 2 do grid")
        return entrada

    monkeypatch.setattr(lancador, "editar_celula", editar)
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)

    assert lancador.preencher_celula(_Quadro(), 1, "QTD", "10") is entrada
    assert chamadas == ["QTD", "QTD"]
    assert entrada.preenchidos == ["10"]


def _limpeza_simulada(monkeypatch, dialogos):
    """Prepara `cancelar_formulario` com Salvar e Cancelar desabilitados e Inserir habilitado
    (o `_Quadro` faz o papel do Inserir); `dialogos` é a sequência de respostas de 'há diálogo
    aberto?' a cada conferência."""

    respostas = iter(dialogos)
    monkeypatch.setattr(lancador, "mensagem_scpi", lambda frame: None)
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)
    monkeypatch.setattr(lancador, "botao_formulario", lambda frame, nome: nome)
    monkeypatch.setattr(lancador, "botao_habilitado", lambda botao: not isinstance(botao, str))
    monkeypatch.setattr(lancador, "dialogo_nova_requisicao_aberto", lambda frame: next(respostas))
    return lancador


def test_limpeza_nao_da_o_estado_por_limpo_com_o_dialogo_aberto(monkeypatch):
    # Inserir fica "habilitado" para o Playwright mesmo atrás do diálogo modal: sem a conferência
    # do diálogo, a limpeza voltava normalmente e o lote seguinte morria no primeiro clique.
    lancador = _limpeza_simulada(monkeypatch, [True, True, True])

    with pytest.raises(ErroSCPI):
        lancador.cancelar_formulario(_Quadro())


def test_limpeza_termina_quando_o_dialogo_fecha(monkeypatch):
    lancador = _limpeza_simulada(monkeypatch, [True, False])
    quadro = _Quadro()

    lancador.cancelar_formulario(quadro)  # 2ª rodada: o Escape fechou o diálogo
    assert quadro.page.keyboard.teclas.count("Escape") == 6


def _item(qtd="5"):
    return Item(cadpro="016.002.018", qtd=qtd, placa="")


def _linha(qtd, desc="ADAPTADOR"):
    return {"Código": "016.002.018", "Descrição do Produto/Serviço": desc, "QTD": qtd}


def test_aguardar_linha_estavel_espera_o_produto_carregar_e_parar_de_mudar(monkeypatch):
    leituras = iter(
        [
            [{"Código": "016.002.018", "Descrição do Produto/Serviço": "", "QTD": "1"}],
            [_linha("1", "ADAPTADOR EM CARGA")],
            [_linha("1")],
            [_linha("1")],
        ]
    )
    monkeypatch.setattr(lancador, "ler_itens", lambda frame: next(leituras))

    assert lancador.aguardar_linha_estavel(_Quadro(), 0, _item()) is True
    assert next(leituras, None) is None  # consumiu as 4 leituras, nem uma a menos


def test_aguardar_linha_estavel_desiste_sem_levantar_erro(monkeypatch):
    monkeypatch.setattr(lancador, "ler_itens", lambda frame: [])

    assert lancador.aguardar_linha_estavel(_Quadro(), 0, _item()) is False


def test_definir_qtd_repreenche_quando_o_grid_volta_para_1(monkeypatch):
    # o SCPI aceita o fill e, depois, redesenha a linha com a QTD padrão (AV-000094 e 103)
    grids = iter([[_linha("1")], [_linha("5")]])
    preenchidos = []

    class Campo:
        def press(self, tecla):
            pass

    monkeypatch.setattr(lancador, "ler_itens", lambda frame: next(grids))
    monkeypatch.setattr(lancador, "aguardar_linha_estavel", lambda frame, i, item: True)
    monkeypatch.setattr(
        lancador,
        "preencher_celula",
        lambda frame, i, coluna, valor, **kw: preenchidos.append(valor) or Campo(),
    )
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)
    monkeypatch.setattr(lancador, "checar_mensagem", lambda frame, etapa: None)

    lancador.definir_qtd(_Quadro(), 0, _item("5"), "item 1/1")
    assert preenchidos == ["5", "5"]


def test_definir_qtd_deixa_a_divergencia_para_a_conferencia_do_item(monkeypatch):
    chamadas = []

    class Campo:
        def press(self, tecla):
            pass

    monkeypatch.setattr(lancador, "ler_itens", lambda frame: [_linha("1")])
    monkeypatch.setattr(lancador, "aguardar_linha_estavel", lambda frame, i, item: True)
    monkeypatch.setattr(
        lancador, "preencher_celula", lambda *a, **kw: chamadas.append(a) or Campo()
    )
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)
    monkeypatch.setattr(lancador, "checar_mensagem", lambda frame, etapa: None)

    lancador.definir_qtd(_Quadro(), 0, _item("5"), "item 1/1")  # não levanta
    assert len(chamadas) == lancador.TENTATIVAS_QTD


def _navegador_com_abertura(monkeypatch, resultados):
    """NavegadorSCPI cujo `abrir_formulario` segue `resultados` (None = abriu, ou a exceção)."""

    nav = lancador.NavegadorSCPI(object())
    nav.frame = _Quadro()
    limpezas = []
    sequencia = iter(resultados)

    def abrir(frame):
        resultado = next(sequencia)
        if resultado:
            raise resultado

    monkeypatch.setattr(lancador, "abrir_formulario", abrir)
    monkeypatch.setattr(lancador, "preencher_cabecalho", lambda frame, req: None)
    monkeypatch.setattr(lancador, "adicionar_itens", lambda frame, req: None)
    monkeypatch.setattr(lancador, "conferir_cabecalho", lambda frame, req: None)
    monkeypatch.setattr(lancador, "localizar_salvar", lambda frame: object())
    monkeypatch.setattr(nav, "limpar", lambda: limpezas.append(1))
    return nav, limpezas


class _Requisicao:
    data = "26/10/2026"
    tipo_saida = "BALCÃO"
    cod_ccusto = "15"


def test_preencher_limpa_e_repete_quando_o_formulario_nao_entra_em_inclusao(monkeypatch):
    erro = ErroAberturaFormulario("formulário não entrou em modo de inclusão")
    nav, limpezas = _navegador_com_abertura(monkeypatch, [erro, erro, None])

    nav.preencher(_Requisicao())
    assert len(limpezas) == 2


def test_preencher_desiste_da_abertura_depois_das_tentativas(monkeypatch):
    erro = ErroAberturaFormulario("formulário não entrou em modo de inclusão")
    nav, limpezas = _navegador_com_abertura(monkeypatch, [erro, erro, erro])

    with pytest.raises(ErroAberturaFormulario):
        nav.preencher(_Requisicao())
    assert len(limpezas) == 2


def test_preencher_nao_repete_erro_que_nao_e_de_abertura(monkeypatch):
    nav, limpezas = _navegador_com_abertura(monkeypatch, [ErroSCPI("SCPI respondeu 'Ajax Error'")])

    with pytest.raises(ErroSCPI):
        nav.preencher(_Requisicao())
    assert limpezas == []


def test_falha_de_abertura_converte_so_o_timeout_do_playwright():
    with pytest.raises(ErroAberturaFormulario, match="botão Inserir não respondeu"):
        with falha_de_abertura("botão Inserir não respondeu"):
            raise TimeoutPlaywright("Locator.click: Timeout 30000ms exceeded")

    # mensagem do SCPI (ErroSCPI comum) não é repetida: passa como está
    with pytest.raises(ErroSCPI) as excecao:
        with falha_de_abertura("x"):
            raise ErroSCPI("SCPI respondeu 'Ajax Error'")
    assert not isinstance(excecao.value, ErroAberturaFormulario)


def test_campo_da_abertura_ausente_vira_erro_de_abertura(monkeypatch):
    def sem_campo(frame, rotulo):
        raise ErroSCPI(f"campo '{rotulo}' não encontrado no formulário")

    monkeypatch.setattr(lancador, "campo", sem_campo)

    with pytest.raises(lancador.ErroAberturaFormulario, match="Recebimento"):
        lancador.campo_da_abertura(_Quadro(), "Recebimento")


def test_definir_qtd_nao_preenche_com_a_linha_instavel(monkeypatch):
    monkeypatch.setattr(lancador, "aguardar_linha_estavel", lambda frame, i, item: False)
    monkeypatch.setattr(
        lancador,
        "preencher_celula",
        lambda *a, **kw: pytest.fail("não deveria preencher a QTD com a linha instável"),
    )

    with pytest.raises(ErroSCPI, match="não estabilizou"):
        lancador.definir_qtd(_Quadro(), 0, _item("5"), "item 1/1")


def test_preencher_registra_a_mensagem_do_scpi_antes_de_limpar(monkeypatch, caplog):
    erro = ErroAberturaFormulario("formulário não entrou em modo de inclusão")
    nav, limpezas = _navegador_com_abertura(monkeypatch, [erro, None])
    monkeypatch.setattr(
        lancador, "mensagem_scpi", lambda frame: {"texto": "Ajax   Error\n500", "botoes": ["OK"]}
    )

    with caplog.at_level(logging.INFO, logger="scpi.lancamento"):
        nav.preencher(_Requisicao())
    assert "SCPI exibiu 'Ajax Error 500' antes da limpeza" in caplog.text
    assert len(limpezas) == 1


def test_preencher_celula_segue_tentando_se_a_mascara_nao_some(monkeypatch):
    entrada = _Entrada(falhas=1)
    abertas = []

    def mascara_presa(frame):
        raise TimeoutPlaywright("Page.wait_for_function: Timeout 60000ms exceeded")

    monkeypatch.setattr(
        lancador, "editar_celula", lambda frame, linha, coluna: abertas.append(coluna) or entrada
    )
    monkeypatch.setattr(lancador, "aguardar_mascara", mascara_presa)

    assert lancador.preencher_celula(_Quadro(), 1, "QTD", "10") is entrada
    assert abertas == ["QTD", "QTD"]


class _CampoQueHabilitaDepois:
    """Campo ExtJS que só fica habilitado na n-ésima consulta (o SCPI habilita depois)."""

    def __init__(self, consultas_ate_habilitar):
        self.restantes = consultas_ate_habilitar

    def is_enabled(self, timeout=None):
        self.timeouts = getattr(self, "timeouts", []) + [timeout]
        if self.restantes > 0:
            self.restantes -= 1
            return False
        return True


def test_aguardar_modo_inclusao_espera_o_scpi_habilitar_os_campos(monkeypatch):
    campos = {
        "Data e Hora da Saída": _CampoQueHabilitaDepois(3),
        "Recebimento": _CampoQueHabilitaDepois(0),
    }
    monkeypatch.setattr(lancador, "campo", lambda frame, rotulo: campos[rotulo])

    lancador.aguardar_modo_inclusao(_Quadro())  # não levanta: habilitou na 4ª consulta
    assert campos["Data e Hora da Saída"].restantes == 0


def test_aguardar_modo_inclusao_desiste_se_os_campos_nunca_habilitam(monkeypatch):
    campo_travado = _CampoQueHabilitaDepois(10**6)
    monkeypatch.setattr(lancador, "campo", lambda frame, rotulo: campo_travado)
    # O `_Quadro` não pausa de verdade: com o prazo real, o laço giraria 6 s no relógio real.
    monkeypatch.setattr(lancador, "ESPERA_MODO_INCLUSAO_MS", 50)

    with pytest.raises(lancador.ErroAberturaFormulario, match="modo de inclusão"):
        lancador.aguardar_modo_inclusao(_Quadro())


def _item_n(cadpro, qtd):
    return Item(cadpro=cadpro, qtd=qtd, placa="")


def _linha_n(cadpro, qtd):
    return {
        "Código": cadpro,
        "Descrição do Produto/Serviço": "X",
        "QTD": qtd,
        "Est. Atual": "100",
        "C.Custo": "7",
    }


class _PedidoDe:
    cod_ccusto = "7"

    def __init__(self, itens):
        self.itens = itens


def test_linha_confere_compara_codigo_qtd_e_placa():
    item = Item(cadpro="016.002.098", qtd="5", placa="")
    assert linha_confere({"Código": "016.002.098", "QTD": "5"}, item)
    assert not linha_confere({"Código": "016.002.098", "QTD": "1"}, item)
    assert not linha_confere({"Código": "016.002.099", "QTD": "5"}, item)

    com_placa = Item(cadpro="006.010.011", qtd="1", placa="R77")
    assert linha_confere({"Código": "006.010.011", "QTD": "1", "Placa (F9)": "R-77"}, com_placa)
    assert not linha_confere({"Código": "006.010.011", "QTD": "1", "Placa (F9)": ""}, com_placa)


def test_aguardar_grid_estavel_exige_leituras_iguais_seguidas(monkeypatch):
    leituras = iter([[1], [2], [2], [2], [2], [2]])
    monkeypatch.setattr(lancador, "ler_itens", lambda frame: next(leituras))

    assert lancador.aguardar_grid_estavel(_Quadro()) is True
    assert next(leituras, None) is None  # parou assim que ficou igual por 2 s


def test_reconciliar_itens_corrige_a_qtd_devolvida_ao_padrao(monkeypatch):
    # AV-000094: itens 3, 5 e 8 voltaram a QTD 1 depois de conferidos
    itens = [_item_n("001.000.001", "3"), _item_n("001.000.002", "5"), _item_n("001.000.003", "4")]
    grids = iter(
        [
            [
                _linha_n("001.000.001", "3"),
                _linha_n("001.000.002", "1"),
                _linha_n("001.000.003", "1"),
            ],
            [
                _linha_n("001.000.001", "3"),
                _linha_n("001.000.002", "5"),
                _linha_n("001.000.003", "4"),
            ],
        ]
    )
    refeitos = []
    monkeypatch.setattr(lancador, "recarregar_grade", lambda frame: True)
    monkeypatch.setattr(lancador, "aguardar_grid_estavel", lambda frame: True)
    monkeypatch.setattr(lancador, "ler_itens", lambda frame: next(grids))
    monkeypatch.setattr(lancador, "definir_qtd", lambda frame, i, item, etapa: refeitos.append(i))

    lancador.reconciliar_itens(_Quadro(), _PedidoDe(itens))
    assert refeitos == [1, 2]


def test_reconciliar_itens_recusa_o_lote_se_a_divergencia_persiste(monkeypatch):
    itens = [_item_n("001.000.001", "3"), _item_n("001.000.002", "5")]
    monkeypatch.setattr(lancador, "recarregar_grade", lambda frame: True)
    monkeypatch.setattr(lancador, "aguardar_grid_estavel", lambda frame: True)
    monkeypatch.setattr(
        lancador,
        "ler_itens",
        lambda frame: [_linha_n("001.000.001", "3"), _linha_n("001.000.002", "1")],
    )
    refeitos = []
    monkeypatch.setattr(lancador, "definir_qtd", lambda frame, i, item, etapa: refeitos.append(i))

    with pytest.raises(ErroSCPI, match="grid mostra QTD 1, esperado 5"):
        lancador.reconciliar_itens(_Quadro(), _PedidoDe(itens))
    assert refeitos == [1] * (lancador.RODADAS_RECONCILIACAO - 1)


def test_aguardar_modo_inclusao_consulta_de_novo_depois_da_ultima_pausa(monkeypatch):
    # habilita só na consulta posterior à última pausa (prazo todo consumido)
    consultas = lancador.ESPERA_MODO_INCLUSAO_MS // lancador.INTERVALO_MODO_INCLUSAO_MS
    campos = {
        "Data e Hora da Saída": _CampoQueHabilitaDepois(consultas),
        "Recebimento": _CampoQueHabilitaDepois(0),
    }
    monkeypatch.setattr(lancador, "campo", lambda frame, rotulo: campos[rotulo])

    lancador.aguardar_modo_inclusao(_Quadro())  # não levanta


def test_reconciliar_itens_recusa_o_lote_se_o_grid_nao_estabiliza(monkeypatch):
    monkeypatch.setattr(lancador, "recarregar_grade", lambda frame: True)
    monkeypatch.setattr(lancador, "aguardar_grid_estavel", lambda frame: False)
    # mesmo com a leitura igual ao pedido, o grid instável não autoriza o salvamento
    monkeypatch.setattr(lancador, "ler_itens", lambda frame: [_linha_n("001.000.001", "3")])

    with pytest.raises(ErroSCPI, match="grid não estabilizou"):
        lancador.reconciliar_itens(_Quadro(), _PedidoDe([_item_n("001.000.001", "3")]))


def test_aguardar_modo_inclusao_espera_o_campo_recebimento_aparecer(monkeypatch):
    chamadas = {"Recebimento": 0}
    data = _CampoQueHabilitaDepois(0)

    def campo(frame, rotulo):
        if rotulo == "Recebimento":
            chamadas["Recebimento"] += 1
            if chamadas["Recebimento"] <= 2:  # ainda não existe no DOM
                raise ErroSCPI("campo 'Recebimento' não encontrado no formulário")
        return data

    monkeypatch.setattr(lancador, "campo", campo)

    lancador.aguardar_modo_inclusao(_Quadro())  # não levanta: segue esperando
    assert chamadas["Recebimento"] == 3


def test_reconciliar_itens_recusa_o_grid_com_linha_a_mais(monkeypatch):
    itens = [_item_n("001.000.001", "3")]
    monkeypatch.setattr(lancador, "recarregar_grade", lambda frame: True)
    monkeypatch.setattr(lancador, "aguardar_grid_estavel", lambda frame: True)
    # o item esperado é um prefixo válido, mas há uma linha codificada a mais
    monkeypatch.setattr(
        lancador,
        "ler_itens",
        lambda frame: [_linha_n("001.000.001", "3"), _linha_n("001.000.009", "1")],
    )

    with pytest.raises(ErroSCPI, match="grid tem 2 item"):
        lancador.reconciliar_itens(_Quadro(), _PedidoDe(itens))


def test_aguardar_modo_inclusao_limita_cada_consulta_ao_prazo(monkeypatch):
    class CampoQueExpiraUmaVez(_CampoQueHabilitaDepois):
        def is_enabled(self, timeout=None):
            if not hasattr(self, "expirou"):
                self.expirou = True
                self.timeouts = [timeout]
                raise TimeoutPlaywright("Locator.is_enabled: Timeout exceeded")  # input trocado
            return super().is_enabled(timeout)

    campo = CampoQueExpiraUmaVez(0)
    monkeypatch.setattr(lancador, "campo", lambda frame, rotulo: campo)

    lancador.aguardar_modo_inclusao(_Quadro())  # a expiração vira "ainda não": consulta de novo
    assert all(t == lancador.CONSULTA_MODO_INCLUSAO_MS for t in campo.timeouts)


def test_aguardar_modo_inclusao_recalcula_o_prazo_antes_de_cada_consulta(monkeypatch):
    agora = [0.0]
    monkeypatch.setattr(lancador.time, "monotonic", lambda: agora[0])
    consultas = []

    class Data:
        def is_enabled(self, timeout=None):
            consultas.append(("data", timeout))
            if len(consultas) == 1:
                agora[0] += 5.9  # a primeira consulta consome quase todo o prazo de 6 s
            return True

    class Recebimento:
        def is_enabled(self, timeout=None):
            consultas.append(("recebimento", timeout))
            raise TimeoutPlaywright("input substituído")

    campos = {"Data e Hora da Saída": Data(), "Recebimento": Recebimento()}
    monkeypatch.setattr(lancador, "campo", lambda frame, rotulo: campos[rotulo])

    quadro = _Quadro()
    quadro.page.wait_for_timeout = lambda ms: agora.__setitem__(0, agora[0] + ms / 1000)

    with pytest.raises(lancador.ErroAberturaFormulario):
        lancador.aguardar_modo_inclusao(quadro)

    # nenhuma consulta espera o prazo inteiro: cada uma tem o teto curto e o laço consulta de novo
    assert consultas[0][1] == lancador.CONSULTA_MODO_INCLUSAO_MS
    assert consultas[1][1] == lancador.CONSULTA_MODO_INCLUSAO_MS
    # o que restava do prazo (100 ms) vira pausa; a volta seguinte também só recebe o mínimo
    assert all(t == lancador.CONSULTA_MODO_INCLUSAO_MS for _, t in consultas[1:])


def test_aguardar_modo_inclusao_limita_a_pausa_ao_prazo(monkeypatch):
    agora = [0.0]
    pausas = []
    monkeypatch.setattr(lancador.time, "monotonic", lambda: agora[0])

    class Quadro(_Quadro):
        def __init__(self):
            super().__init__()
            self.page.wait_for_timeout = lambda ms: (
                pausas.append(ms),
                agora.__setitem__(0, agora[0] + ms / 1000),
            )

    class Campo:
        def is_enabled(self, timeout=None):
            return False

    monkeypatch.setattr(lancador, "campo", lambda frame, rotulo: Campo())

    with pytest.raises(lancador.ErroAberturaFormulario):
        lancador.aguardar_modo_inclusao(Quadro())
    assert pausas and all(0 < p <= lancador.INTERVALO_MODO_INCLUSAO_MS for p in pausas)
    assert sum(pausas) <= lancador.ESPERA_MODO_INCLUSAO_MS


def test_linha_confere_com_quantidade_fracionaria():
    item = Item(cadpro="016.002.098", qtd="0,33", placa="")
    assert linha_confere({"Código": "016.002.098", "QTD": "0,33"}, item)
    assert not linha_confere({"Código": "016.002.098", "QTD": "1"}, item)
    assert not linha_confere({"Código": "016.002.098", "QTD": "0,3"}, item)

    milhar = Item(cadpro="016.002.098", qtd="1.5", placa="")
    assert linha_confere({"Código": "016.002.098", "QTD": "1,5"}, milhar)


def test_aguardar_modo_inclusao_trata_input_desconectado_como_ainda_nao_habilitado(monkeypatch):
    class CampoTrocado:
        chamadas = 0

        def is_enabled(self, timeout=None):
            CampoTrocado.chamadas += 1
            if CampoTrocado.chamadas == 1:
                raise ErroPlaywright("Element is not attached to the DOM")
            return True

    monkeypatch.setattr(lancador, "campo", lambda frame, rotulo: CampoTrocado())

    lancador.aguardar_modo_inclusao(_Quadro())  # não levanta: consulta o input novo


def test_aguardar_modo_inclusao_nao_engole_outros_erros_do_playwright(monkeypatch):
    class CampoComErro:
        def is_enabled(self, timeout=None):
            raise ErroPlaywright("Target page, context or browser has been closed")

    monkeypatch.setattr(lancador, "campo", lambda frame, rotulo: CampoComErro())

    with pytest.raises(ErroPlaywright, match="has been closed"):
        lancador.aguardar_modo_inclusao(_Quadro())


class _QuadroQueRecarrega(_Quadro):
    def __init__(self, resposta):
        super().__init__()
        self.resposta = resposta

    def evaluate(self, js):
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


def test_recarregar_grade_devolve_se_o_servidor_respondeu():
    assert lancador.recarregar_grade(_QuadroQueRecarrega(True)) is True


def test_recarregar_grade_nao_derruba_o_lancamento_se_nao_recarregar(caplog):
    with caplog.at_level(logging.INFO, logger="scpi.lancamento"):
        assert lancador.recarregar_grade(_QuadroQueRecarrega(False)) is False
        assert lancador.recarregar_grade(_QuadroQueRecarrega(RuntimeError("x"))) is False
    assert "não recarregou" in caplog.text and "não consegui recarregar" in caplog.text


def test_reconciliar_recarrega_a_grade_do_servidor_antes_de_cada_conferencia(monkeypatch):
    eventos = []
    monkeypatch.setattr(
        lancador, "recarregar_grade", lambda frame: eventos.append("recarregar") or True
    )
    monkeypatch.setattr(
        lancador, "aguardar_grid_estavel", lambda frame: eventos.append("estavel") or True
    )
    monkeypatch.setattr(lancador, "registrar_servidor", lambda *a, **k: None)
    monkeypatch.setattr(lancador, "ler_itens", lambda frame: [_linha("5")])
    req = Requisicao(lote="AV-1", linhas=[], itens=[_item("5")])

    lancador.reconciliar_itens(_Quadro(), req)
    assert eventos == ["recarregar", "estavel"]


class _EntradaTeclada:
    def __init__(self):
        self.eventos = []

    def press(self, tecla, timeout=None):
        self.eventos.append(("press", tecla))

    def press_sequentially(self, texto, timeout=None):
        self.eventos.append(("digitar", texto))

    def fill(self, valor, timeout=None):
        self.eventos.append(("fill", valor))


def test_preencher_celula_digitando_seleciona_e_digita_sem_usar_fill(monkeypatch):
    entrada = _EntradaTeclada()
    monkeypatch.setattr(lancador, "editar_celula", lambda frame, linha, coluna: entrada)

    assert lancador.preencher_celula(_Quadro(), 0, "QTD", "12,5", digitando=True) is entrada
    assert entrada.eventos == [("press", "ControlOrMeta+a"), ("digitar", "12,5")]


def test_preencher_celula_sem_digitando_continua_usando_fill(monkeypatch):
    entrada = _EntradaTeclada()
    monkeypatch.setattr(lancador, "editar_celula", lambda frame, linha, coluna: entrada)

    lancador.preencher_celula(_Quadro(), 0, "Placa (F9)", "ABC1D23")
    assert entrada.eventos == [("fill", "ABC1D23")]


def test_definir_qtd_digita_a_quantidade(monkeypatch):
    chamadas = []

    class Campo:
        def press(self, tecla):
            pass

    monkeypatch.setattr(lancador, "ler_itens", lambda frame: [_linha("5")])
    monkeypatch.setattr(lancador, "aguardar_linha_estavel", lambda frame, i, item: True)
    monkeypatch.setattr(
        lancador, "preencher_celula", lambda *a, **kw: chamadas.append(kw) or Campo()
    )
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)
    monkeypatch.setattr(lancador, "checar_mensagem", lambda frame, etapa: None)

    lancador.definir_qtd(_Quadro(), 0, _item("5"), "item 1/1")
    assert chamadas == [{"digitando": True}]


def test_reconciliar_recusa_o_lote_se_a_grade_do_servidor_nao_recarrega(monkeypatch):
    monkeypatch.setattr(lancador, "recarregar_grade", lambda frame: False)
    monkeypatch.setattr(
        lancador,
        "aguardar_grid_estavel",
        lambda frame: pytest.fail("não deveria conferir sem a leitura do servidor"),
    )
    req = Requisicao(lote="AV-1", linhas=[], itens=[_item("5")])

    with pytest.raises(ErroSCPI, match="não foi possível recarregar a grade do servidor"):
        lancador.reconciliar_itens(_Quadro(), req)
