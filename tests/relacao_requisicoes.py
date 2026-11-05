"""Gerador do CSV da "Relação de Requisições" sem filtro, no formato real do SCPI (spec 010).

Dados sintéticos, sem nomes de pessoas reais. O formato segue o CSV real descrito em
`specs/010-conciliacao-scpi/contracts/relatorio-requisicoes.md`: UTF-8 com BOM, `;`, CRLF, as 65
colunas do cabeçalho (mais o `;` final) e uma linha por item, com o cabeçalho da requisição
repetido. A descrição longa (DISCR1) pode quebrar o registro em duas linhas, como no SCPI.
"""

from dataclasses import dataclass, field
from datetime import date

COLUNAS = (
    "GRUPO;GRUPO_1;ID_REQUI;REQUI;CODIF;NOME;DTLAN;DATAE;DTEMISSAONF;DTPAG;ENTR;SAID;COMP;"
    "OBS_CABECALHO;CADPRO;DISC1;UNID1;DISCR1;NOME_GRUPO;NOME_SUBGRUPO;QUAN2;VAUN2;VATO2;COD;DESTI;"
    "CODCCUSTO;CCUSTO;DOCUM;RECEBE;NEMPG_REQUI;ANOEMP_REQUI;EMPENHO;PROCESSO_REQUI;PLACA;MODELO;OBS;"
    "GRUP;SUB;EMPRESA_TRAB;NOME_EMPRESA_TRAB;REGISTRO_TRAB;MATRICULA_TRAB;CONTRATO_TRAB;NOME_TRAB;"
    "CARGOATUAL_TRAB;CARGOATUAL_NOME_TRAB;SIP_EMPRESA;SIP_EMP_NOME;SIP_REGISTRO;SIP_MATRICULA;"
    "SIP_CONTRATO;SIP_TRAB_NOME;SIP_CARGOATUAL;SIP_CARGOATUAL_NOME;TPREQUI;LOTE;VALIDADE;BALCO;"
    "BALCO_TCE;BALCO_TCE_SAIDA;NUMPED;NPEDFILHO;HORAE;HORAS;RESPONSA"
).split(";")


@dataclass
class ItemCSV:
    codigo: str
    quantidade: str = "1"  # como o SCPI escreve: "2", "1,5"
    unidade: str = "UN"
    placa: str = ""
    descricao_longa: str = "Material sintético para teste"


@dataclass
class RequisicaoCSV:
    requisicao: str  # 003588/26
    id_requi: int
    data: date
    tipo: str = "BALCÃO"
    cod_ccusto: str = "15"
    centro: str = "MANUTENÇÃO DE REDE DE ÁGUA"
    recebedor: str = "Recebedor Sintético"
    observacoes: str = ""
    data_filtro: date | None = None  # DTPAG; padrão: a mesma data
    entrada: bool = False
    responsavel: str = "USUARIO DO ROBO"
    itens: list[ItemCSV] = field(default_factory=lambda: [ItemCSV("016.005.010")])


def _br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _linha(req: RequisicaoCSV, item: ItemCSV) -> str:
    valores = dict.fromkeys(COLUNAS, "")
    valores.update(
        GRUPO=_br(req.data),
        ID_REQUI=str(req.id_requi),
        REQUI=req.requisicao,
        DTLAN=_br(req.data),
        DTPAG=_br(req.data_filtro or req.data),
        ENTR="S" if req.entrada else "",
        SAID="S",
        COMP="P",
        OBS_CABECALHO=req.observacoes,
        CADPRO=item.codigo,
        DISC1=f"MATERIAL {item.codigo}",
        UNID1=item.unidade,
        DISCR1=item.descricao_longa,
        QUAN2=item.quantidade,
        VAUN2="1,5",
        VATO2="1,5",
        CODCCUSTO=req.cod_ccusto,
        CCUSTO=req.centro,
        RECEBE=req.recebedor,
        PLACA=item.placa,
        TPREQUI=req.tipo,
        LOTE="00000000",
        RESPONSA=req.responsavel,
    )
    return ";".join(valores[c] for c in COLUNAS) + ";"


def relatorio(requisicoes: list[RequisicaoCSV], *, quebra_final: bool = True) -> bytes:
    """Bytes do CSV como o SCPI o entrega. Uma `descricao_longa` com "\\n" quebra o registro."""
    linhas = [";".join(COLUNAS) + ";"]
    linhas += [_linha(req, item) for req in requisicoes for item in req.itens]
    texto = "\r\n".join(linhas) + ("\r\n" if quebra_final else "")
    return texto.encode("utf-8-sig")
