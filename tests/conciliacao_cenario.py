"""Cenários da conciliação para testes fora dela (spec 010)."""

from datetime import timedelta

from django.utils import timezone

from catalogo.models import Importacao
from conciliacao.models import ConferenciaLote, ExtracaoOficial, TentativaLancamento
from pedidos.models import ExecucaoRobo, LinhaSaida


def tentativa_em_verificar(lote: str, *, horas_atras: int = 2) -> TentativaLancamento:
    """A tentativa que deixou o lote em verificar, numa execução real que já terminou."""
    momento = timezone.now() - timedelta(hours=horas_atras)
    execucao = ExecucaoRobo.objects.create(inicio=momento, fim=momento, situacao="ATENCAO")
    return TentativaLancamento.objects.create(
        execucao=execucao,
        ordem=1,
        lote=lote,
        momento=momento,
        resultado=TentativaLancamento.Resultado.VERIFICAR,
    )


def liberacao_comprovada(lote: str) -> ConferenciaLote:
    """O lote em verificar tem a tentativa registrada e uma extração bem-sucedida, posterior a
    ela e cobrindo a data do lote, sem nenhuma candidata: a liberação é permitida."""
    tentativa = tentativa_em_verificar(lote)
    data = LinhaSaida.objects.filter(lote=lote).values_list("data", flat=True).first()
    importacao = Importacao.objects.create(
        tipo=Importacao.Tipo.REQUISICOES,
        situacao=Importacao.Situacao.SUCESSO,
        periodo_de=data - timedelta(days=1),
        periodo_ate=data + timedelta(days=1),
        fim=timezone.now(),
    )
    extracao = ExtracaoOficial.objects.create(
        importacao=importacao, motivo=ExtracaoOficial.Motivo.MANUAL
    )
    return ConferenciaLote.objects.create(
        lote=lote,
        extracao=extracao,
        tipo=ConferenciaLote.Tipo.VERIFICAR,
        veredito=ConferenciaLote.Veredito.INTERVALO_VAZIO,
        tentativa=tentativa,
    )
