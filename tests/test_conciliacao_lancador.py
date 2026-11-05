"""O campo Observações nas funções reais do lançador (spec 010, FR-011), com um formulário falso:
nenhum teste abre o navegador. A prova de que o SCPI gravou o texto é o relatório, não a tela;
aqui se confere só que o robô escreve e relê o que deve."""

import pytest

from scpi import lancador
from scpi.requisicoes import ErroSCPI, Requisicao


class _Campo:
    def __init__(self, valor=""):
        self.valor = valor
        self.eventos = []

    def fill(self, valor):
        self.valor = valor

    def dispatch_event(self, evento):
        self.eventos.append(evento)

    def input_value(self):
        return self.valor


class _Aba:
    def click(self):
        pass


class _Quadro:
    def get_by_role(self, papel, name=None):
        return _Aba()


def _req(obs=""):
    req = Requisicao(lote="AV-000165", linhas=[])
    req.data, req.tipo_saida, req.cod_ccusto, req.recebedor, req.obs = (
        "03/11/2026",
        "BALCÃO",
        "4",
        "Recebedor Sintético",
        obs,
    )
    return req


@pytest.fixture
def formulario(monkeypatch):
    campos: dict[str, _Campo] = {}
    monkeypatch.setattr(
        lancador, "campo", lambda frame, rotulo: campos.setdefault(rotulo, _Campo())
    )
    monkeypatch.setattr(lancador, "sair_do_campo", lambda frame, campo, nome: None)
    monkeypatch.setattr(lancador, "selecionar_combo", lambda frame, rotulo, valor: None)
    return campos


def test_preencher_cabecalho_escreve_o_lote_e_a_obs_nas_observacoes(formulario):
    lancador.preencher_cabecalho(_Quadro(), _req("Entregue; conferido"))
    obs = formulario["Observações"]
    assert obs.valor == "Central Almoxarifado AV-000165\nObs.: Entregue, conferido"
    assert obs.eventos == ["change"]


def test_preencher_cabecalho_sem_obs_escreve_so_o_lote(formulario):
    lancador.preencher_cabecalho(_Quadro(), _req())
    assert formulario["Observações"].valor == "Central Almoxarifado AV-000165"


def test_conferir_cabecalho_aceita_as_observacoes_escritas(formulario):
    req = _req("Entregue")
    lancador.preencher_cabecalho(_Quadro(), req)
    formulario["Tipo Saída"] = _Campo("BALCÃO")
    lancador.conferir_cabecalho(_Quadro(), req)


def test_conferir_cabecalho_recusa_observacoes_que_se_perderam(formulario):
    req = _req("Entregue")
    lancador.preencher_cabecalho(_Quadro(), req)
    formulario["Tipo Saída"] = _Campo("BALCÃO")
    formulario["Observações"].valor = ""
    with pytest.raises(ErroSCPI, match="Observações"):
        lancador.conferir_cabecalho(_Quadro(), req)
