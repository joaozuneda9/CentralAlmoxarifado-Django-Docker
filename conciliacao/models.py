"""Registro oficial do SCPI para a conciliação dos lançamentos (spec 010).

Cada extração da "Relação de Requisições" sem filtro de tipo é uma `Importacao` do tipo
`REQUISICOES` com uma `ExtracaoOficial`: o arquivo bruto comprimido, a impressão digital e as
requisições lidas. Os modelos de `pedidos` não mudam (Princípio II).
"""

from django.db import models

from catalogo.models import Importacao


class ExtracaoOficial(models.Model):
    """Uma extração da "Relação de Requisições" do SCPI, bem-sucedida ou não."""

    class Motivo(models.TextChoices):
        ANTES = "ANTES", "Antes do lançamento"
        DEPOIS = "DEPOIS", "Depois do lançamento"
        DIARIA = "DIARIA", "Diária"
        MANUAL = "MANUAL", "Manual"

    importacao = models.OneToOneField(
        Importacao, on_delete=models.PROTECT, related_name="extracao_oficial"
    )
    motivo = models.CharField(max_length=10, choices=Motivo.choices)
    execucao = models.ForeignKey(
        "pedidos.ExecucaoRobo",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="extracoes_oficiais",
        verbose_name="execução do robô",
    )
    impressao = models.CharField("impressão digital (SHA-256)", max_length=64, blank=True)
    arquivo = models.BinaryField("arquivo bruto (gzip)", null=True, blank=True)
    mesmo_arquivo_que = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="repeticoes",
        verbose_name="mesmo arquivo que",
    )
    arquivo_apagado_em = models.DateTimeField("bruto apagado em", null=True, blank=True)
    maior_requisicao = models.CharField("maior requisição", max_length=9, null=True, blank=True)
    requisicoes = models.PositiveIntegerField("requisições", default=0)

    class Meta:
        ordering = ["-importacao__inicio"]
        verbose_name = "extração do SCPI"
        verbose_name_plural = "extrações do SCPI"
        indexes = [models.Index(fields=["motivo", "execucao"], name="extracao_motivo_execucao")]
        constraints = [
            # A extração de antes e a de depois pertencem sempre a uma execução real do robô.
            models.CheckConstraint(
                condition=~models.Q(motivo__in=["ANTES", "DEPOIS"])
                | models.Q(execucao__isnull=False),
                name="extracao_execucao_antes_depois",
            )
        ]

    MOTIVOS_DA_EXECUCAO = (Motivo.ANTES, Motivo.DEPOIS)

    def __str__(self):
        return f"{self.get_motivo_display()} · {self.importacao}"

    @property
    def bem_sucedida(self) -> bool:
        return self.importacao.situacao == Importacao.Situacao.SUCESSO


class RequisicaoOficial(models.Model):
    """Uma requisição como o relatório a trouxe numa extração (uma foto por extração)."""

    extracao = models.ForeignKey(
        ExtracaoOficial, on_delete=models.CASCADE, related_name="requisicoes_lidas"
    )
    requisicao = models.CharField("requisição", max_length=9)
    ano = models.PositiveSmallIntegerField()
    numero = models.PositiveIntegerField("número")
    id_requi = models.PositiveIntegerField("identificador interno")
    data = models.DateField()
    data_filtro = models.DateField("data do filtro (DTPAG)", null=True, blank=True)
    tipo = models.CharField(max_length=60, blank=True)
    cod_ccusto = models.CharField("código do centro de custo", max_length=20, blank=True)
    centro_nome = models.CharField("centro de custo", max_length=200, blank=True)
    recebedor = models.CharField(max_length=200, blank=True)
    observacoes = models.TextField("observações", blank=True)
    lote_observado = models.CharField(
        "lote nas observações", max_length=12, blank=True, db_index=True
    )
    responsavel = models.CharField("responsável", max_length=200, blank=True)
    entrada = models.BooleanField(default=False)

    class Meta:
        ordering = ["extracao", "ano", "numero"]
        verbose_name = "requisição do SCPI"
        verbose_name_plural = "requisições do SCPI"
        constraints = [
            models.UniqueConstraint(
                fields=["extracao", "ano", "numero"], name="requisicao_oficial_unica"
            )
        ]

    def __str__(self):
        return self.requisicao


class ItemOficial(models.Model):
    requisicao = models.ForeignKey(
        RequisicaoOficial, on_delete=models.CASCADE, related_name="itens"
    )
    ordem = models.PositiveSmallIntegerField()
    codigo = models.CharField("código", max_length=30)
    quantidade = models.DecimalField(max_digits=14, decimal_places=4)
    unidade = models.CharField(max_length=20, blank=True)
    placa = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["requisicao", "ordem"]
        verbose_name = "item da requisição do SCPI"
        verbose_name_plural = "itens da requisição do SCPI"

    def __str__(self):
        return f"{self.requisicao} · {self.codigo}"
