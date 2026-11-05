"""Leituras da conciliação para as outras partes do sistema (spec 010)."""

from dataclasses import dataclass, field

from conciliacao import regras
from conciliacao.models import Candidata, ConferenciaLote
from conciliacao.servicos import ultima_tentativa

SEM_TENTATIVA = (
    "Este lote não tem a tentativa registrada; não dá para provar que nada foi salvo. "
    "Informe o número ou marque para não lançar."
)
SEM_EXTRACAO = (
    "Ainda não há uma extração do SCPI feita depois desta tentativa. Extraia as requisições do "
    "SCPI e tente de novo."
)


@dataclass(frozen=True)
class Liberacao:
    permitida: bool
    motivo: str = ""
    candidatas: list[str] = field(default_factory=list)


def liberacao(lote: str) -> Liberacao:
    """Se um lote em verificar pode voltar para a fila (FR-024, research R17).

    Exige, para a tentativa mais recente do lote, ao menos uma conferência de uma extração
    bem-sucedida feita depois dela e cobrindo a data do lote, e nenhuma candidata em nenhuma
    delas: uma candidata vista uma vez continua bloqueando (Princípio III)."""
    tentativa = ultima_tentativa(lote)
    if tentativa is None:
        return Liberacao(False, SEM_TENTATIVA)
    conferencias = ConferenciaLote.objects.filter(
        lote=lote, tipo=ConferenciaLote.Tipo.VERIFICAR, tentativa=tentativa
    )
    if not conferencias.exists():
        return Liberacao(False, SEM_EXTRACAO)
    numeros = sorted(
        set(
            Candidata.objects.filter(conferencia__in=conferencias).values_list(
                "requisicao__requisicao", flat=True
            )
        ),
        key=regras.chave,
    )
    if numeros:
        quantas = "uma requisição" if len(numeros) == 1 else f"{len(numeros)} requisições"
        return Liberacao(
            False,
            f"Há {quantas} no SCPI que podem ser deste lote: {', '.join(numeros)}. Confira e "
            "informe o número, ou marque para não lançar.",
            numeros,
        )
    return Liberacao(True)
