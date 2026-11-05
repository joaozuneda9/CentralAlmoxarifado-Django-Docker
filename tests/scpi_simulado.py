"""SCPI simulado para os testes do lançamento (sem pytest, reaproveitado pelo comando).

Cumpre o protocolo `scpi.lancamento.SCPI` sem navegador: registra as chamadas em
`chamadas`, falha quando pedido (por lote) e numera as requisições salvas em sequência.

Também é o registro oficial dos testes da conciliação (spec 010): guarda o que cada Salvar
gravou (`salvas`) e entrega a "Relação de Requisições" sem filtro no formato real
(`relatorio`), com falhas controladas (relatório que falha, tipo ou observações perdidos,
requisição feita à mão, Salvar que grava e depois falha).
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime

from conciliacao.regras import texto_observacoes
from scpi.leitura import NadaAExibir
from scpi.requisicoes import ResultadoIncerto
from tests.relacao_requisicoes import ItemCSV, RequisicaoCSV, relatorio


class SCPISimulado:
    def __init__(self):
        self.falhas_preencher: dict[str, Exception] = {}
        self.falhas_salvar: dict[str, Exception] = {}
        # Lotes cujo Salvar grava a requisição no SCPI e depois falha (resposta perdida).
        self.salva_e_falha: set[str] = set()
        # Lotes cujo Tipo Saída ou Observações o SCPI deixa de gravar (o formulário reaproveitado).
        self.perde_tipo: set[str] = set()
        self.perde_observacoes: set[str] = set()
        self.ao_salvar: Callable | None = None
        self.chamadas: list[tuple[str, str]] = []
        self.abertas = 0
        self.falhas_relatorio = 0  # quantas extrações seguidas falham antes de funcionar
        self.relatorios: list[tuple[date, date]] = []
        self.salvas: list[RequisicaoCSV] = []  # o que está no SCPI, na ordem dos números
        self._lote = ""  # último lote preenchido (o formulário aberto)
        self._req = None
        self._salvas = 0

    @contextmanager
    def abrir(self) -> Iterator["SCPISimulado"]:
        self.abertas += 1
        yield self

    def preencher(self, req) -> None:
        self._lote = req.lote
        self._req = req
        self.chamadas.append(("preencher", req.lote))
        if req.lote in self.falhas_preencher:
            raise self.falhas_preencher[req.lote]

    def _proximo_numero(self) -> str:
        self._salvas += 1
        return f"{self._salvas:06d}/26"

    def _registrar(self, numero: str, req) -> None:
        self.salvas.append(
            RequisicaoCSV(
                requisicao=numero,
                id_requi=int(numero[:6]) + 100,
                data=datetime.strptime(req.data, "%d/%m/%Y").date(),
                tipo="" if req.lote in self.perde_tipo else req.tipo_saida,
                cod_ccusto=req.cod_ccusto,
                centro=req.linhas[0].centro_custo if req.linhas else "",
                recebedor=req.recebedor,
                observacoes=""
                if req.lote in self.perde_observacoes
                else texto_observacoes(req.lote, req.obs),
                itens=[ItemCSV(i.cadpro, i.qtd, placa=i.placa) for i in req.itens],
            )
        )

    def requisicao_manual(self, data: date, **campos) -> str:
        """Alguém lança uma requisição à mão no SCPI: ela pega o próximo número."""
        numero = self._proximo_numero()
        self.salvas.append(
            RequisicaoCSV(requisicao=numero, id_requi=int(numero[:6]) + 100, data=data, **campos)
        )
        return numero

    def salvar(self) -> str:
        self.chamadas.append(("salvar", self._lote))
        if self._lote in self.falhas_salvar:
            raise self.falhas_salvar[self._lote]
        numero = self._proximo_numero()
        if self._req is not None and self._req.itens:
            self._registrar(numero, self._req)
        if self._lote in self.salva_e_falha:
            raise ResultadoIncerto("o SCPI salvou, mas a resposta se perdeu")
        if self.ao_salvar is not None:
            self.ao_salvar()
        return numero

    def relatorio(self, de: date, ate: date) -> bytes:
        """A "Relação de Requisições" sem filtro, filtrada por DTPAG; sem nenhuma requisição,
        `NadaAExibir`, como em `relatorios.baixar_requisicoes`."""
        self.relatorios.append((de, ate))
        if self.falhas_relatorio:
            self.falhas_relatorio -= 1
            raise RuntimeError("SCPI fora do ar")
        no_periodo = [r for r in self.salvas if de <= (r.data_filtro or r.data) <= ate]
        if not no_periodo:
            raise NadaAExibir("Requisições do SCPI: nada a exibir.")
        return relatorio(no_periodo)

    def depois_de_salvar(self) -> None:
        self.chamadas.append(("depois_de_salvar", self._lote))

    def encerrar_simulacao(self) -> None:
        self.chamadas.append(("simulacao", self._lote))

    def descartar(self, lote: str) -> None:
        self.chamadas.append(("descartar", lote))

    def reiniciar(self) -> None:
        self.chamadas.append(("reiniciar", ""))
