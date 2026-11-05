"""Extração da "Relação de Requisições" sem filtro de tipo e registro do bruto (spec 010).

`extrair` é a única camada que grava uma `ExtracaoOficial`, também quando a extração falha. Ela
roda sobre `scpi.execucao.executar` (trava por tipo, transação, `Importacao` com a situação).
Quem pede a extração sabe do resultado pela situação da `Importacao`; a única exceção que sobe é
`ImportacaoEmAndamento` (outra extração segura a trava), sem nenhum registro.
"""

import gzip
import hashlib
from collections.abc import Callable
from datetime import date

from catalogo.models import Importacao
from conciliacao import regras
from conciliacao.models import ExtracaoOficial, ItemOficial, RequisicaoOficial
from pedidos.models import LinhaSaida
from pedidos.regras import LANCADA
from scpi.execucao import Resultado, executar
from scpi.leitura import ErroImportacao, NadaAExibir, RequisicaoLida, ler_requisicoes


def impressao(conteudo: bytes) -> str:
    """Impressão digital dos bytes recebidos do SCPI (SHA-256 em hexadecimal)."""
    return hashlib.sha256(conteudo).hexdigest()


def _bruto(conteudo: bytes | None) -> dict:
    """Campos do arquivo bruto de uma extração nova. Com a mesma impressão de uma extração que
    ainda guarda os bytes, aponta para ela em vez de guardar outra cópia (FR-003); se o bruto
    daquela já foi apagado, guarda o seu."""
    if conteudo is None:
        return {}
    digital = impressao(conteudo)
    origem = (
        ExtracaoOficial.objects.filter(impressao=digital, arquivo__isnull=False)
        .order_by("-pk")
        .first()
    )
    if origem is not None:
        return {"impressao": digital, "arquivo": None, "mesmo_arquivo_que": origem}
    return {"impressao": digital, "arquivo": gzip.compress(conteudo)}


def _conferir_periodo(lidas: list[RequisicaoLida], periodo: tuple[date, date]) -> None:
    """A extração diz cobrir `periodo`, e o relatório filtra por DTPAG: uma requisição com DTPAG
    fora dele (CSV de outro período em `--arquivo`, ou o filtro do SCPI mudou) faz a extração
    inteira falhar, em vez de guardar o que o período não promete."""
    de, ate = periodo
    for lida in lidas:
        if lida.data_filtro is not None and not de <= lida.data_filtro <= ate:
            raise ErroImportacao(
                f"Requisições do SCPI: a requisição {lida.requisicao} tem DTPAG "
                f"{lida.data_filtro:%d/%m/%Y}, fora do período {de:%d/%m/%Y} a {ate:%d/%m/%Y}; "
                "nada foi gravado."
            )


def _vazio(periodo: tuple[date, date]) -> list[RequisicaoLida]:
    """O SCPI respondeu "Nada a exibir" (o download levanta `NadaAExibir`). Num período sem
    nenhum lote lançado isso é possível e vale como extração sem requisições; num período com
    lote lançado, o relatório não pode estar vazio, e a extração falha (FR-005)."""
    de, ate = periodo
    if LinhaSaida.objects.filter(status=LANCADA, data__range=(de, ate)).exists():
        raise ErroImportacao(
            f"Requisições do SCPI: o relatório veio vazio de {de:%d/%m/%Y} a {ate:%d/%m/%Y}, "
            "mas há lotes lançados nesse período; nada foi gravado."
        )
    return []


def _gravar_requisicoes(extracao: ExtracaoOficial, lidas: list[RequisicaoLida]) -> None:
    for lida in lidas:
        requisicao = RequisicaoOficial.objects.create(
            extracao=extracao,
            requisicao=lida.requisicao,
            ano=lida.ano,
            numero=lida.numero,
            id_requi=lida.id_requi,
            data=lida.data,
            data_filtro=lida.data_filtro,
            tipo=lida.tipo,
            cod_ccusto=lida.cod_ccusto,
            centro_nome=lida.centro_nome,
            recebedor=lida.recebedor,
            observacoes=lida.observacoes,
            lote_observado=regras.lote_observado(lida.observacoes),
            responsavel=lida.responsavel,
            entrada=lida.entrada,
        )
        ItemOficial.objects.bulk_create(
            ItemOficial(
                requisicao=requisicao,
                ordem=ordem,
                codigo=item.codigo,
                quantidade=item.quantidade,
                unidade=item.unidade,
                placa=item.placa,
            )
            for ordem, item in enumerate(lida.itens, start=1)
        )


def extrair(
    motivo: str,
    periodo: tuple[date, date],
    obter_csv: Callable[[], bytes],
    *,
    execucao=None,
) -> ExtracaoOficial:
    """Baixa (ou lê) o relatório, guarda o bruto e as requisições e devolve a extração.

    Sucesso ou falha, a extração fica registrada; na falha, sem requisições e com
    `maior_requisicao` nulo (a leitura é tudo ou nada). Levanta só `ImportacaoEmAndamento`
    (e `ValueError` numa chamada errada: `ANTES` e `DEPOIS` exigem a execução do robô)."""
    if motivo in ExtracaoOficial.MOTIVOS_DA_EXECUCAO and execucao is None:
        raise ValueError(f"Extração {motivo} sem a execução do robô.")
    recebido: dict[str, object] = {}

    def baixar() -> bytes:
        try:
            conteudo = obter_csv()
        except NadaAExibir:
            # O SCPI não gerou o relatório; só esse aviso faz o vazio valer (`_vazio`).
            recebido["nada_a_exibir"] = True
            conteudo = b""
        recebido["conteudo"] = conteudo
        return conteudo

    def gravar(conteudo: bytes) -> Resultado:
        if conteudo:
            lidas = ler_requisicoes(conteudo).linhas
        elif recebido.get("nada_a_exibir"):
            lidas = _vazio(periodo)
        else:
            raise ErroImportacao("Requisições do SCPI: o arquivo veio vazio; nada foi gravado.")
        _conferir_periodo(lidas, periodo)
        extracao = ExtracaoOficial.objects.create(
            importacao=recebido["importacao"],
            motivo=motivo,
            execucao=execucao,
            maior_requisicao=regras.maior_requisicao(lida.requisicao for lida in lidas),
            requisicoes=len(lidas),
            **_bruto(conteudo),
        )
        _gravar_requisicoes(extracao, lidas)
        recebido["extracao"] = extracao
        return Resultado(linhas=len(lidas))

    def registrar(importacao: Importacao) -> None:
        recebido["importacao"] = importacao

    importacao = executar(Importacao.Tipo.REQUISICOES, baixar, gravar, periodo, ao_criar=registrar)
    if importacao.situacao == Importacao.Situacao.SUCESSO:
        return recebido["extracao"]
    # A transação da gravação foi desfeita: a falha ganha o seu registro, sem requisições, com o
    # bruto quando ele chegou a ser baixado (um relatório cortado fica guardado para conferência).
    return ExtracaoOficial.objects.create(
        importacao=importacao,
        motivo=motivo,
        execucao=execucao,
        **_bruto(recebido.get("conteudo")),
    )
