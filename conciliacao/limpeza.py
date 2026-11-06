"""Retenção de 60 dias do registro oficial (spec 010, FR-004, SC-007, data-model).

O bruto gzip de uma extração é esvaziado quando ela **e todas as que apontam para ela**
(`mesmo_arquivo_que`) passaram dos 60 dias; a impressão digital e a extração ficam. As requisições
lidas de uma extração com mais de 60 dias são apagadas quando nenhuma conferência as liga (como a
ligada ou a outra do conflito) nem as lista como candidata; as ligadas ficam para sempre, e com elas
todo veredito continua consultável.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Exists, OuterRef
from django.utils import timezone

from catalogo.models import Importacao, trava_importacao
from conciliacao.models import Candidata, ConferenciaLote, ExtracaoOficial, RequisicaoOficial
from conciliacao.servicos import ConciliacaoEmAndamento, trava_conciliacao
from scpi.execucao import trava

RETENCAO = timedelta(days=60)
LOTE_DE_APAGAR = 500


@dataclass(frozen=True)
class Limpeza:
    brutos: int
    requisicoes: int

    @property
    def resumo(self) -> str:
        """O que a limpeza apagou, numa frase para a saída do comando."""
        if not (self.brutos or self.requisicoes):
            return "nada com mais de 60 dias a apagar"
        return (
            f"{self.brutos} {'arquivo bruto' if self.brutos == 1 else 'arquivos brutos'} e "
            f"{self.requisicoes} "
            f"{'requisição sem ligação' if self.requisicoes == 1 else 'requisições sem ligação'} "
            "com mais de 60 dias apagados"
        )


def limpar(agora: datetime | None = None) -> Limpeza | None:
    """Apaga o que passou da retenção. Roda com duas travas: a das extrações de requisições (uma
    extração nova pode estar apontando para um bruto, `mesmo_arquivo_que`, que esta limpeza
    esvaziaria) e a da conciliação, com a espera de sempre (nenhuma conciliação liga uma
    requisição entre a escolha das soltas e a exclusão delas). Com alguma ocupada, não faz nada e
    devolve None: a próxima limpeza faz."""
    agora = agora or timezone.now()
    corte = agora - RETENCAO
    with trava(trava_importacao(Importacao.Tipo.REQUISICOES)) as obtida:
        if not obtida:
            return None
        try:
            with trava_conciliacao():
                return Limpeza(_brutos(corte, agora), _requisicoes(corte))
        except ConciliacaoEmAndamento:
            return None


def _brutos(corte: datetime, agora: datetime) -> int:
    """Esvazia o bruto das extrações de antes do `corte` que nenhuma extração recente usa
    (`mesmo_arquivo_que`), marcando `arquivo_apagado_em`. Devolve quantas esvaziou."""
    recente_apontando = ExtracaoOficial.objects.filter(
        mesmo_arquivo_que=OuterRef("pk"), importacao__inicio__gte=corte
    )
    # A lista antes do update: o MySQL não atualiza uma tabela lida na subconsulta do mesmo UPDATE.
    vencidas = list(
        ExtracaoOficial.objects.filter(arquivo__isnull=False, importacao__inicio__lt=corte)
        .exclude(Exists(recente_apontando))
        .values_list("pk", flat=True)
    )
    if not vencidas:
        return 0
    return ExtracaoOficial.objects.filter(pk__in=vencidas).update(
        arquivo=None, arquivo_apagado_em=agora
    )


def _requisicoes(corte: datetime) -> int:
    """Apaga, em blocos, as requisições de extrações de antes do `corte` que nenhuma conferência
    liga (a ligada ou a outra do conflito) nem lista como candidata. Devolve quantas apagou."""
    soltas = list(
        RequisicaoOficial.objects.filter(extracao__importacao__inicio__lt=corte)
        .exclude(Exists(ConferenciaLote.objects.filter(requisicao=OuterRef("pk"))))
        .exclude(Exists(ConferenciaLote.objects.filter(outra_requisicao=OuterRef("pk"))))
        .exclude(Exists(Candidata.objects.filter(requisicao=OuterRef("pk"))))
        .values_list("pk", flat=True)
    )
    apagadas = 0
    for inicio in range(0, len(soltas), LOTE_DE_APAGAR):
        bloco = soltas[inicio : inicio + LOTE_DE_APAGAR]
        _, por_modelo = RequisicaoOficial.objects.filter(pk__in=bloco).delete()
        apagadas += por_modelo.get(RequisicaoOficial._meta.label, 0)
    return apagadas
