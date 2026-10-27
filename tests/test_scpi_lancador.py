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
