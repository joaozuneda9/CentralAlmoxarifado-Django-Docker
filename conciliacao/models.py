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


class TentativaLancamento(models.Model):
    """Um lote numa execução real do robô, na ordem em que foi tentado (FR-010).

    É a afirmação do robô, nunca a prova: liga a execução ao piso e permite calcular o intervalo
    de números de uma tentativa que ficou em verificar. A `foto` guarda o que o robô ia digitar."""

    class Resultado(models.TextChoices):
        LANCADA = "LANCADA", "Lançada"
        VERIFICAR = "VERIFICAR", "Verificar no SCPI"
        ERRO = "ERRO", "Erro antes do Salvar"
        IGNORADA = "IGNORADA", "Ignorada (o lote mudou)"

    execucao = models.ForeignKey(
        "pedidos.ExecucaoRobo",
        on_delete=models.PROTECT,
        related_name="tentativas",
        verbose_name="execução do robô",
    )
    ordem = models.PositiveSmallIntegerField()
    lote = models.CharField(max_length=12, db_index=True)
    momento = models.DateTimeField()
    resultado = models.CharField(max_length=10, choices=Resultado.choices)
    requisicao = models.CharField("requisição", max_length=9, blank=True)
    foto = models.JSONField(null=True, blank=True)
    historica = models.BooleanField("histórica (do journal)", default=False)

    class Meta:
        ordering = ["execucao", "ordem"]
        verbose_name = "tentativa de lançamento"
        verbose_name_plural = "tentativas de lançamento"
        constraints = [
            models.UniqueConstraint(fields=["execucao", "ordem"], name="tentativa_ordem_unica"),
            models.UniqueConstraint(fields=["execucao", "lote"], name="tentativa_lote_unico"),
        ]

    def __str__(self):
        return f"#{self.execucao_id}.{self.ordem} {self.lote} · {self.get_resultado_display()}"


class ConferenciaLote(models.Model):
    """O resultado de um lote numa extração bem-sucedida (spec 010, entidade "Conferência de
    lote"). Uma extração com falha nunca grava conferência. Os vereditos dos lotes lançados vêm
    no PR 4; o PR 3 grava só as de `VERIFICAR`, com as candidatas."""

    class Tipo(models.TextChoices):
        LANCAMENTO = "LANCAMENTO", "Lançamento"
        REVISAO = "REVISAO", "Revisão"
        VERIFICAR = "VERIFICAR", "Verificar no SCPI"

    class Veredito(models.TextChoices):
        AGUARDANDO = "AGUARDANDO", "Aguardando conferência"
        COMPROVADO = "COMPROVADO", "Comprovado"
        DIVERGENTE = "DIVERGENTE", "Divergente"
        NAO_ENCONTRADO = "NAO_ENCONTRADO", "Não encontrado"
        DUPLICADO = "DUPLICADO", "Duplicado"
        CONFLITO = "CONFLITO", "Vínculo em conflito"
        INTERVALO_VAZIO = "INTERVALO_VAZIO", "Nenhuma requisição no intervalo"
        COM_CANDIDATAS = "COM_CANDIDATAS", "Com candidatas"
        SEM_TENTATIVA = "SEM_TENTATIVA", "Sem tentativa registrada"

    class Origem(models.TextChoices):
        OBSERVACOES = "OBSERVACOES", "Lote nas observações"
        NUMERO = "NUMERO", "Número gravado"
        AMBOS = "AMBOS", "Observações e número"

    lote = models.CharField(max_length=12, db_index=True)
    extracao = models.ForeignKey(
        ExtracaoOficial, on_delete=models.PROTECT, related_name="conferencias"
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    veredito = models.CharField(max_length=16, choices=Veredito.choices)
    requisicao = models.ForeignKey(
        RequisicaoOficial,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="conferencias",
        verbose_name="requisição ligada",
    )
    outra_requisicao = models.ForeignKey(
        RequisicaoOficial,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="outra requisição",
    )
    origem_vinculo = models.CharField(
        "origem do vínculo", max_length=12, choices=Origem.choices, blank=True
    )
    diferencas = models.JSONField("diferenças", default=list, blank=True)
    notas = models.JSONField(default=list, blank=True)
    alterado_depois = models.BooleanField("alterado no SCPI depois", default=False)
    intervalo_de = models.CharField("intervalo de", max_length=9, blank=True)
    intervalo_ate = models.CharField("intervalo até", max_length=9, blank=True)
    tentativa = models.ForeignKey(
        TentativaLancamento,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="conferencias",
    )
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criada_em", "-pk"]
        verbose_name = "conferência de lote"
        verbose_name_plural = "conferências de lote"
        constraints = [
            models.UniqueConstraint(
                fields=["lote", "extracao", "tipo"], name="conferencia_lote_unica"
            )
        ]

    def __str__(self):
        return f"{self.lote} · {self.get_veredito_display()}"


class Candidata(models.Model):
    """Uma requisição oficial que pode ser do lote em verificar (FR-022, FR-023)."""

    conferencia = models.ForeignKey(
        ConferenciaLote, on_delete=models.CASCADE, related_name="candidatas"
    )
    requisicao = models.ForeignKey(
        RequisicaoOficial, on_delete=models.PROTECT, related_name="candidaturas"
    )
    e_esta = models.BooleanField("é esta (lote nas observações)", default=False)
    ordem = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["conferencia", "ordem"]
        verbose_name = "candidata"
        verbose_name_plural = "candidatas"

    def __str__(self):
        return f"{self.conferencia.lote} → {self.requisicao}"
