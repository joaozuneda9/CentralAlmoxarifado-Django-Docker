from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.utils import timezone

from pedidos import regras


class Pedido(models.Model):
    """Cabeçalho de um pedido dos formulários (LIMPEZA, AB, VIATURAS) ou de uma saída avulsa
    (AVULSA).

    O `id` é o identificador do envio, gerado quando a página abre: o mesmo em todas as
    tentativas, para um reenvio nunca duplicar o pedido.
    """

    class Origem(models.TextChoices):
        LIMPEZA = regras.LIMPEZA, "Limpeza, copa/cozinha e escritório"
        AB = regras.AB, "Materiais AB"
        VIATURAS = regras.VIATURAS, "Reposição de peças das viaturas"
        OFICINA = regras.OFICINA, "Oficina mecânica"
        EPIS = regras.EPIS, "Pedido de EPIs"
        AVULSA = regras.AVULSA, "Saída avulsa"

    id = models.UUIDField(primary_key=True, editable=False)
    numero = models.CharField("número", max_length=12, unique=True)
    origem = models.CharField(max_length=20, choices=Origem.choices)
    criado_em = models.DateTimeField(default=timezone.now, db_index=True)
    solicitante = models.CharField(max_length=200, blank=True)
    destino = models.CharField(max_length=210, blank=True)
    obs = models.CharField("observação", max_length=200, blank=True)
    # Só o formulário de viaturas pede (`Fluxo.pede_ocorrencia`); nos outros fica vazio.
    ocorrencia = models.CharField("nº da ocorrência", max_length=20, blank=True, default="")
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="saidas_registradas",
    )
    # Endereço de origem do envio público: base dos limites contra abuso.
    ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    # Soma 1 a cada edição salva do atendimento: o formulário de edição a leva, e o salvar
    # recusa quando outra pessoa gravou antes (concorrência otimista).
    versao = models.PositiveIntegerField("versão", default=0)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.numero

    @property
    def atendimento_ou_none(self):
        try:
            return self.atendimento
        except Atendimento.DoesNotExist:
            return None

    @property
    def autorizacao_ou_none(self):
        """A autorização da Segurança do Trabalho, ou None: o pedido de um formulário que não
        exige autorização não tem."""
        try:
            return self.autorizacao
        except AutorizacaoPedido.DoesNotExist:
            return None

    @property
    def atendimento_liberado(self) -> bool:
        """A autorização não impede o atendimento: o formulário não a exige, ou a Segurança do
        Trabalho já autorizou (spec 008)."""
        autorizacao = self.autorizacao_ou_none
        return autorizacao is None or autorizacao.situacao == AutorizacaoPedido.Situacao.AUTORIZADO

    @property
    def linhas(self) -> list:
        atendimento = self.atendimento_ou_none
        return list(atendimento.linhas.all()) if atendimento else []

    @property
    def situacao(self) -> regras.Situacao:
        autorizacao = self.autorizacao_ou_none
        return regras.situacao_pedido(
            self.origem,
            self.atendimento_ou_none is not None,
            self.itens.all(),
            autorizacao.situacao if autorizacao else None,
        )

    @property
    def situacao_scpi(self) -> regras.Situacao:
        return regras.situacao_scpi(self.linhas)


def restringir_troca(collector, field, sub_objs, using):
    """`on_delete` do `no_lugar_de`: o `RESTRICT` do Django, que barra apagar sozinho o item
    trocado (`RestrictedError`) e deixa apagá-lo junto com o acrescentado (o pedido inteiro).
    O `models.RESTRICT` não serve aqui: no auto-relacionamento ele cria uma dependência do
    modelo consigo mesmo, a ordenação da exclusão desiste, e o MySQL recusa apagar o pedido
    antes do atendimento; e o MySQL confere a chave estrangeira linha a linha, então o
    `DELETE` único dos itens falharia no item trocado. Por isso, quando a exclusão segue, o
    `no_lugar_de` dos acrescentados vira nulo antes dos `DELETE`."""
    collector.add_restricted_objects(field, sub_objs)
    collector.add_field_update(field, None, sub_objs)


class ItemPedido(models.Model):
    """Material do pedido, com o retrato do catálogo no momento do aceite."""

    class Origem(models.TextChoices):
        PEDIDO = "PEDIDO", "Pedido pelo solicitante"
        ALMOXARIFADO = "ALMOXARIFADO", "Adicionado pelo almoxarifado"

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    codigo = models.CharField("código", max_length=30)
    material = models.CharField(max_length=255)
    unidade = models.CharField(max_length=20, blank=True)
    categoria = models.CharField(max_length=100, blank=True)
    grupo = models.CharField(max_length=120, blank=True)
    subgrupo = models.CharField(max_length=120, blank=True)
    estoque_no_pedido = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    qtd_pedida = models.DecimalField(
        "quantidade pedida", max_digits=12, decimal_places=3, null=True, blank=True
    )
    qtd_entregue = models.DecimalField(
        "quantidade entregue", max_digits=12, decimal_places=3, null=True, blank=True
    )
    origem = models.CharField(max_length=12, choices=Origem.choices, default=Origem.PEDIDO)
    no_lugar_de = models.ForeignKey(
        "self",
        # Não PROTECT: ele barraria apagar o pedido inteiro (a cascata leva o acrescentado
        # junto); `restringir_troca` só barra apagar o item trocado sozinho.
        on_delete=restringir_troca,
        null=True,
        blank=True,
        related_name="trocado_por",
        verbose_name="no lugar de",
    )
    adicionado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="adicionado por",
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"
        constraints = [
            models.UniqueConstraint(fields=["pedido", "codigo"], name="item_pedido_codigo_unico"),
            models.CheckConstraint(
                condition=(models.Q(origem="ALMOXARIFADO", qtd_pedida__isnull=True))
                | (models.Q(origem="PEDIDO", qtd_pedida__isnull=False)),
                name="item_pedido_qtd_pedida_conforme_origem",
            ),
            models.CheckConstraint(
                condition=(models.Q(origem="ALMOXARIFADO", adicionado_por__isnull=False))
                | (models.Q(origem="PEDIDO", adicionado_por__isnull=True)),
                name="item_pedido_adicionado_por_conforme_origem",
            ),
            models.CheckConstraint(
                condition=models.Q(no_lugar_de__isnull=True) | models.Q(origem="ALMOXARIFADO"),
                name="item_pedido_no_lugar_de_so_acrescentado",
            ),
        ]

    def clean(self):
        super().clean()
        troca = self.no_lugar_de
        if troca is None:
            return
        if troca.pedido_id != self.pedido_id:
            raise ValidationError({"no_lugar_de": "O item trocado precisa ser do mesmo pedido."})
        if troca.origem != self.Origem.PEDIDO:
            raise ValidationError(
                {"no_lugar_de": "Só um item pedido pelo solicitante pode ser trocado."}
            )

    def __str__(self):
        return f"{self.codigo} — {self.material}"


class Atendimento(models.Model):
    """Saída registrada para um pedido (ou a própria saída avulsa)."""

    id = models.UUIDField(primary_key=True, editable=False)
    pedido = models.OneToOneField(Pedido, on_delete=models.CASCADE, related_name="atendimento")
    data_efetiva = models.DateField()
    recebedor = models.CharField(max_length=200)
    centro_custo = models.CharField("centro de custo", max_length=200)
    tipo_saida = models.CharField("tipo de saída", max_length=200)
    placa = models.CharField(max_length=20, blank=True)
    obs = models.CharField("observações", max_length=200, blank=True)
    nao_lancar = models.BooleanField("não lançar no SCPI", default=False)
    atendido_em = models.DateTimeField(default=timezone.now)
    atendido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="atendimentos"
    )
    recibo_impresso_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-atendido_em"]

    def __str__(self):
        return f"Atendimento de {self.pedido.numero}"


class AutorizacaoPedido(models.Model):
    """Autorização da Segurança do Trabalho sobre um pedido de EPI (spec 008): uma linha por
    pedido de formulário com `Fluxo.exige_autorizacao`, criada junto com o pedido. A decisão é
    definitiva (autorizado ou recusado, sem volta) e só o atendimento de pedido autorizado é aceito.
    Os pedidos dos outros formulários não têm esta linha."""

    class Situacao(models.TextChoices):
        AGUARDANDO = regras.AUTORIZACAO_AGUARDANDO, "Aguardando autorização"
        AUTORIZADO = regras.AUTORIZACAO_AUTORIZADA, "Autorizado"
        RECUSADO = regras.AUTORIZACAO_RECUSADA, "Recusado"

    pedido = models.OneToOneField(Pedido, on_delete=models.CASCADE, related_name="autorizacao")
    situacao = models.CharField(
        max_length=12, choices=Situacao.choices, default=Situacao.AGUARDANDO, db_index=True
    )
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="decidido por",
    )
    decidido_em = models.DateTimeField("decidido em", null=True, blank=True)
    motivo = models.CharField("motivo da recusa", max_length=200, blank=True)

    class Meta:
        verbose_name = "autorização do pedido"
        verbose_name_plural = "autorizações dos pedidos"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        situacao="AGUARDANDO",
                        decidido_por__isnull=True,
                        decidido_em__isnull=True,
                        motivo="",
                    )
                    | models.Q(
                        situacao="AUTORIZADO",
                        decidido_por__isnull=False,
                        decidido_em__isnull=False,
                        motivo="",
                    )
                    | (
                        models.Q(
                            situacao="RECUSADO",
                            decidido_por__isnull=False,
                            decidido_em__isnull=False,
                        )
                        & ~models.Q(motivo="")
                    )
                ),
                name="autorizacao_pedido_estado_coerente",
            ),
        ]

    def __str__(self):
        return f"Autorização de {self.pedido.numero}: {self.get_situacao_display()}"


class AlteracaoPedido(models.Model):
    """Uma edição salva do atendimento (ou da saída avulsa): quem, quando e o que mudou. Só a
    tela do pedido mostra; o recibo, nunca."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="alteracoes")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="alteracoes_pedido"
    )
    em = models.DateTimeField(default=timezone.now)
    versao = models.PositiveIntegerField("versão gravada")
    # `regras.diferencas_atendimento`: só textos, para caber no JSON.
    diferencas = models.JSONField("diferenças", default=list)
    # Situação e mensagem das linhas de saída substituídas pela edição.
    scpi_antes = models.JSONField("linhas de saída antes", default=list)

    class Meta:
        ordering = ["-em"]
        verbose_name = "alteração do pedido"
        verbose_name_plural = "alterações dos pedidos"

    def __str__(self):
        return f"{self.pedido.numero} v{self.versao}"


class LinhaSaida(models.Model):
    """Uma linha por material entregue: o contrato com o robô que lança no SCPI."""

    class Status(models.TextChoices):
        PENDENTE = regras.PENDENTE, "Pendente"
        EM_LANCAMENTO = regras.EM_LANCAMENTO, "Em lançamento"
        LANCADA = regras.LANCADA, "Lançada"
        ERRO = regras.ERRO, "Erro"
        VERIFICAR = regras.VERIFICAR, "Verificar no SCPI"
        NAO_LANCAR = regras.NAO_LANCAR, "Não lançar"

    atendimento = models.ForeignKey(Atendimento, on_delete=models.CASCADE, related_name="linhas")
    seq = models.PositiveSmallIntegerField()
    data = models.DateField()
    qtd = models.DecimalField("quantidade", max_digits=12, decimal_places=3)
    codigo = models.CharField("código", max_length=30)
    descricao = models.CharField("descrição", max_length=255)
    recebedor = models.CharField(max_length=200)
    centro_custo = models.CharField("centro de custo", max_length=200)
    tipo_saida = models.CharField("tipo de saída", max_length=200)
    placa = models.CharField(max_length=20, blank=True)
    obs = models.CharField("observações", max_length=200, blank=True)
    lote = models.CharField(max_length=12, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDENTE, db_index=True
    )
    requisicao_scpi = models.CharField("requisição no SCPI", max_length=30, blank=True)
    lancado_em = models.DateTimeField(null=True, blank=True)
    mensagem = models.TextField(blank=True)

    class Meta:
        ordering = ["lote", "seq"]
        verbose_name = "linha de saída"
        verbose_name_plural = "linhas de saída"
        constraints = [
            models.UniqueConstraint(fields=["atendimento", "seq"], name="linha_saida_unica"),
            models.CheckConstraint(condition=models.Q(qtd__gt=0), name="linha_saida_qtd_positiva"),
        ]

    def __str__(self):
        return f"{self.lote} #{self.seq} · {self.codigo}"


class Sequencia(models.Model):
    """Numeração única de pedidos (P-) e saídas avulsas (AV-): uma linha só, "PEDIDOS"."""

    nome = models.CharField(max_length=30, unique=True)
    ultimo = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "sequência"

    def __str__(self):
        return f"{self.nome}: {self.ultimo}"


# Trava nomeada (`GET_LOCK`) que o robô segura enquanto lança: é ela que diz se há execução viva.
TRAVA_LANCAMENTO = "almoxarifado:lancar_saidas"
# Tempo que o processo do robô tem para subir e obter a trava depois que a execução é criada.
TOLERANCIA_INICIO = timedelta(seconds=60)


class ExecucaoRobo(models.Model):
    """Registro de cada execução do robô que lança as saídas no SCPI (ou só a simula)."""

    class Situacao(models.TextChoices):
        ANDAMENTO = "ANDAMENTO", "Em andamento"
        SUCESSO = "SUCESSO", "Concluída"
        ATENCAO = "ATENCAO", "Concluída com pendências"
        FALHA = "FALHA", "Falhou"

    simulacao = models.BooleanField("simulação", default=False)
    iniciada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="execucoes_robo",
    )
    inicio = models.DateTimeField("início", default=timezone.now)
    fim = models.DateTimeField(null=True, blank=True)
    situacao = models.CharField(
        "situação", max_length=20, choices=Situacao.choices, default=Situacao.ANDAMENTO
    )
    resumo = models.JSONField(default=dict, blank=True)
    log = models.TextField(blank=True)
    erro = models.TextField(blank=True)

    class Meta:
        ordering = ["-inicio"]
        verbose_name = "execução do robô"
        verbose_name_plural = "execuções do robô"

    def __str__(self):
        return f"{'Simulação' if self.simulacao else 'Lançamento'} #{self.pk}"

    @staticmethod
    def trava_ocupada() -> bool:
        """Se algum processo segura a trava do lançamento (o robô está rodando)."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT IS_USED_LOCK(%s)", [TRAVA_LANCAMENTO])
            return cursor.fetchone()[0] is not None

    @classmethod
    def em_andamento(cls, agora=None):
        """Execuções em andamento de verdade: com a trava do lançamento ocupada, todas as que
        não terminaram; sem ela, só as criadas há menos de `TOLERANCIA_INICIO` (o processo
        ainda está subindo). As demais morreram sem registrar o fim (interrompidas)."""
        andamento = cls.objects.filter(situacao=cls.Situacao.ANDAMENTO)
        if cls.trava_ocupada():
            return andamento
        agora = agora or timezone.now()
        return andamento.filter(inicio__gte=agora - TOLERANCIA_INICIO)

    @property
    def interrompida(self) -> bool:
        """Sem fim registrado e fora de `em_andamento` (mesma regra, para esta execução)."""
        if self.situacao != self.Situacao.ANDAMENTO:
            return False
        if self.inicio >= timezone.now() - TOLERANCIA_INICIO:
            return False
        return not self.trava_ocupada()
