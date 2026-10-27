def test_navegador_implementa_o_protocolo_do_lancamento():
    from scpi.lancador import NavegadorSCPI
    from scpi.lancamento import SCPI

    metodos = {n for n in vars(SCPI) if not n.startswith("_")}
    assert metodos <= set(dir(NavegadorSCPI))


def test_lancador_nao_importa_playwright_no_topo():
    import scpi.lancador

    assert "sync_playwright" not in vars(scpi.lancador)


def test_navegador_libera_o_orm_enquanto_esta_aberto(monkeypatch):
    # A API síncrona do Playwright mantém um laço asyncio na thread enquanto o navegador está
    # aberto, e o lançamento grava no banco nesse meio (SynchronousOnlyOperation).
    import os
    from contextlib import nullcontext

    import playwright.sync_api

    from scpi import lancador

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

    def wait_for_timeout(self, ms):
        pass


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
    from scpi import lancador

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
    import pytest
    from playwright.sync_api import TimeoutError as TimeoutPlaywright

    from scpi import lancador

    entrada = _Entrada(falhas=99)
    monkeypatch.setattr(lancador, "editar_celula", lambda frame, linha, coluna: entrada)
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)

    with pytest.raises(TimeoutPlaywright):
        lancador.preencher_celula(_Quadro(), 0, "QTD", "1")
    assert entrada.falhas == 99 - lancador.TENTATIVAS_CELULA


def test_preencher_celula_tenta_de_novo_quando_o_editor_nao_abre(monkeypatch):
    from scpi import lancador
    from scpi.requisicoes import ErroSCPI

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
    from scpi import lancador

    respostas = iter(dialogos)
    monkeypatch.setattr(lancador, "mensagem_scpi", lambda frame: None)
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)
    monkeypatch.setattr(lancador, "botao_formulario", lambda frame, nome: nome)
    monkeypatch.setattr(lancador, "botao_habilitado", lambda botao: not isinstance(botao, str))
    monkeypatch.setattr(lancador, "dialogo_nova_requisicao_aberto", lambda frame: next(respostas))
    return lancador


def test_limpeza_nao_da_o_estado_por_limpo_com_o_dialogo_aberto(monkeypatch):
    import pytest

    from scpi.requisicoes import ErroSCPI

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
    from scpi.requisicoes import Item

    return Item(cadpro="016.002.018", qtd=qtd, placa="")


def _linha(qtd, desc="ADAPTADOR"):
    return {"Código": "016.002.018", "Descrição do Produto/Serviço": desc, "QTD": qtd}


def test_aguardar_linha_estavel_espera_o_produto_carregar_e_parar_de_mudar(monkeypatch):
    from scpi import lancador

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
    from scpi import lancador

    monkeypatch.setattr(lancador, "ler_itens", lambda frame: [])

    assert lancador.aguardar_linha_estavel(_Quadro(), 0, _item()) is False


def test_definir_qtd_repreenche_quando_o_grid_volta_para_1(monkeypatch):
    from scpi import lancador

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
        lambda frame, i, coluna, valor: preenchidos.append(valor) or Campo(),
    )
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)
    monkeypatch.setattr(lancador, "checar_mensagem", lambda frame, etapa: None)

    lancador.definir_qtd(_Quadro(), 0, _item("5"), "item 1/1")
    assert preenchidos == ["5", "5"]


def test_definir_qtd_deixa_a_divergencia_para_a_conferencia_do_item(monkeypatch):
    from scpi import lancador

    chamadas = []

    class Campo:
        def press(self, tecla):
            pass

    monkeypatch.setattr(lancador, "ler_itens", lambda frame: [_linha("1")])
    monkeypatch.setattr(lancador, "aguardar_linha_estavel", lambda frame, i, item: True)
    monkeypatch.setattr(lancador, "preencher_celula", lambda *a: chamadas.append(a) or Campo())
    monkeypatch.setattr(lancador, "aguardar_mascara", lambda frame: None)
    monkeypatch.setattr(lancador, "checar_mensagem", lambda frame, etapa: None)

    lancador.definir_qtd(_Quadro(), 0, _item("5"), "item 1/1")  # não levanta
    assert len(chamadas) == lancador.TENTATIVAS_QTD


def _navegador_com_abertura(monkeypatch, resultados):
    """NavegadorSCPI cujo `abrir_formulario` segue `resultados` (None = abriu, ou a exceção)."""
    from scpi import lancador

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
    from scpi.lancador import ErroAberturaFormulario

    erro = ErroAberturaFormulario("formulário não entrou em modo de inclusão")
    nav, limpezas = _navegador_com_abertura(monkeypatch, [erro, erro, None])

    nav.preencher(_Requisicao())
    assert len(limpezas) == 2


def test_preencher_desiste_da_abertura_depois_das_tentativas(monkeypatch):
    import pytest

    from scpi.lancador import ErroAberturaFormulario

    erro = ErroAberturaFormulario("formulário não entrou em modo de inclusão")
    nav, limpezas = _navegador_com_abertura(monkeypatch, [erro, erro, erro])

    with pytest.raises(ErroAberturaFormulario):
        nav.preencher(_Requisicao())
    assert len(limpezas) == 2


def test_preencher_nao_repete_erro_que_nao_e_de_abertura(monkeypatch):
    import pytest

    from scpi.requisicoes import ErroSCPI

    nav, limpezas = _navegador_com_abertura(monkeypatch, [ErroSCPI("SCPI respondeu 'Ajax Error'")])

    with pytest.raises(ErroSCPI):
        nav.preencher(_Requisicao())
    assert limpezas == []


def test_falha_de_abertura_converte_so_o_timeout_do_playwright():
    import pytest
    from playwright.sync_api import TimeoutError as TimeoutPlaywright

    from scpi.lancador import ErroAberturaFormulario, falha_de_abertura
    from scpi.requisicoes import ErroSCPI

    with pytest.raises(ErroAberturaFormulario, match="botão Inserir não respondeu"):
        with falha_de_abertura("botão Inserir não respondeu"):
            raise TimeoutPlaywright("Locator.click: Timeout 30000ms exceeded")

    # mensagem do SCPI (ErroSCPI comum) não é repetida: passa como está
    with pytest.raises(ErroSCPI) as excecao:
        with falha_de_abertura("x"):
            raise ErroSCPI("SCPI respondeu 'Ajax Error'")
    assert not isinstance(excecao.value, ErroAberturaFormulario)


def test_campo_da_abertura_ausente_vira_erro_de_abertura(monkeypatch):
    import pytest

    from scpi import lancador
    from scpi.requisicoes import ErroSCPI

    def sem_campo(frame, rotulo):
        raise ErroSCPI(f"campo '{rotulo}' não encontrado no formulário")

    monkeypatch.setattr(lancador, "campo", sem_campo)

    with pytest.raises(lancador.ErroAberturaFormulario, match="Recebimento"):
        lancador.campo_da_abertura(_Quadro(), "Recebimento")
