from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import connection, models
from django.utils import timezone

from catalogo.depara import CicloDePara, Par, resolver_canonicos, validar_par
from pedidos import regras
from pedidos.regras import norm_placa, norm_u


class Material(models.Model):
    """Material do cadastro do SCPI, com o saldo de estoque. Mantido pelos importadores."""

    codigo = models.CharField("código", max_length=30, unique=True)
    nome = models.CharField(max_length=255)
    unidade = models.CharField(max_length=20, blank=True)
    grupo = models.CharField(max_length=120, blank=True)
    subgrupo = models.CharField(max_length=120, blank=True)
    oculto = models.BooleanField(default=False)
    # Código que veio repetido no cadastro do SCPI: fica bloqueado nos formulários.
    duplicado = models.BooleanField(default=False)
    estoque = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    estoque_em = models.DateTimeField("estoque atualizado em", null=True, blank=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "material"
        verbose_name_plural = "materiais"

    def __str__(self):
        return f"{self.codigo} — {self.nome}"


class Opcao(models.Model):
    """Valores das listas mantidas à mão (substitui a aba `Listas`)."""

    class Lista(models.TextChoices):
        TIPO_SAIDA = "TIPO_SAIDA", "Tipos de saída"
        GRUPO_OCULTO_AB = "GRUPO_OCULTO_AB", "Grupos ocultos (AB)"
        CATEGORIA_LIMPEZA = "CATEGORIA_LIMPEZA", "Categorias (limpeza)"
        FUNCIONARIO = "FUNCIONARIO", "Funcionários"
        # Unidades do SCPI em que a quantidade pode ter fração. Lista vazia = tudo inteiro.
        UNIDADE_FRACIONAVEL = "UNIDADE_FRACIONAVEL", "Unidades fracionáveis"
        # Grupos do SCPI cujos materiais o formulário da oficina mecânica oferece (spec 007).
        GRUPO_OFICINA = "GRUPO_OFICINA", "Grupos (oficina)"
        # Grupos do SCPI cujos materiais o formulário de EPIs oferece (spec 008).
        GRUPO_EPI = "GRUPO_EPI", "Grupos (EPIs)"

    lista = models.CharField(max_length=30, choices=Lista.choices)
    valor = models.CharField(max_length=200)
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["lista", "ordem", "valor"]
        verbose_name = "opção"
        verbose_name_plural = "opções"
        constraints = [
            models.UniqueConstraint(fields=["lista", "valor"], name="opcao_unica_na_lista"),
        ]

    def __str__(self):
        return f"{self.get_lista_display()}: {self.valor}"

    @classmethod
    def valores(cls, lista: str) -> list[str]:
        """Valores ativos de `lista`, na ordem de exibição."""
        return list(cls.objects.filter(lista=lista, ativo=True).values_list("valor", flat=True))


class Formulario(models.TextChoices):
    """Os formulários públicos cujas opções a configuração administra (spec 009). O valor é o da
    `Pedido.Origem` do formulário; a saída avulsa, que é do almoxarifado, não entra."""

    LIMPEZA = regras.LIMPEZA, "Limpeza, copa e escritório"
    AB = regras.AB, "Ferramentas, peças e materiais"
    VIATURAS = regras.VIATURAS, "Reposição de peças das viaturas"
    OFICINA = regras.OFICINA, "Oficina mecânica"
    EPIS = regras.EPIS, "Equipamentos de proteção individual (EPIs)"


class CentroCusto(models.Model):
    """Centro de custo do SCPI (substitui a aba `Centros de Custo`, lida pelo robô).

    Um centro pode ter várias linhas, uma por placa; uma placa só pode estar numa linha. A
    placa vazia é gravada como NULL, para o índice único do banco aceitar várias linhas sem
    placa.
    """

    descricao = models.CharField("descrição", max_length=200)
    codigo = models.CharField("código", max_length=20)
    placa = models.CharField(max_length=20, unique=True, null=True, blank=True)
    # Obsoleto desde a spec 009: o destino de cada formulário vem de `CentroFormulario`. A marca
    # foi transcrita pela migration `0006` e fica só como registro (não vale, e saiu do admin).
    equipe_manutencao = models.BooleanField(
        "equipe de manutenção",
        default=False,
        help_text="Não vale mais: os destinos são definidos na página Formulários.",
    )
    # Estado global (spec 009): o centro inativo não é oferecido nem aceito em pedido novo dos
    # formulários públicos nem na saída avulsa nova; atendimento, edição e robô seguem resolvendo.
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["descricao", "placa"]
        verbose_name = "centro de custo"
        verbose_name_plural = "centros de custo"

    def __str__(self):
        texto = f"{self.descricao} ({self.codigo})"
        return f"{texto} — {self.placa}" if self.placa else texto

    def clean(self):
        self.placa = norm_placa(self.placa) or None
        if not self.placa:
            return
        outro = CentroCusto.objects.filter(placa=self.placa).exclude(pk=self.pk).first()
        if outro:
            raise ValidationError(
                {
                    "placa": f"A placa {self.placa} já está cadastrada no centro de custo "
                    f'"{outro.descricao}" ({outro.codigo}).'
                }
            )

    def save(self, *args, **kwargs):
        self.placa = norm_placa(self.placa) or None
        super().save(*args, **kwargs)


class CentroFormulario(models.Model):
    """A linha do cadastro de centros (centro mais placa) que é destino de um formulário (spec 009).

    A presença da linha diz que ela é destino; sem linha, não é. Linha de centro inativo fica
    guardada e sem efeito: reativar o centro a restaura.
    """

    centro = models.ForeignKey(CentroCusto, on_delete=models.CASCADE, related_name="formularios")
    formulario = models.CharField(max_length=20, choices=Formulario.choices)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    alterado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["centro__descricao", "centro__placa"]
        verbose_name = "centro no formulário"
        verbose_name_plural = "centros nos formulários"
        constraints = [
            models.UniqueConstraint(
                fields=["centro", "formulario"], name="centro_unico_no_formulario"
            ),
        ]

    def __str__(self):
        return f"{self.get_formulario_display()}: {self.centro}"


class ItemLimpeza(models.Model):
    """Item do formulário de limpeza, copa/cozinha e escritório (substitui `Lista_Limpeza`).

    Nome e unidade exibidos têm prioridade sobre o cadastro do SCPI quando preenchidos.
    """

    material = models.OneToOneField(Material, on_delete=models.PROTECT, related_name="item_limpeza")
    categoria = models.CharField(max_length=100)
    nome_exibido = models.CharField(max_length=255, blank=True)
    unidade_exibida = models.CharField(max_length=20, blank=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["categoria", "ordem", "material__nome"]
        verbose_name = "item de limpeza"
        verbose_name_plural = "itens de limpeza"

    def __str__(self):
        return self.nome_exibido or str(self.material)

    def clean(self):
        # Só valida categoria nova ou trocada: um item antigo continua editável (e a ordem
        # continua salvando na lista) depois que a categoria dele é desativada.
        if self.pk and ItemLimpeza.objects.filter(pk=self.pk, categoria=self.categoria).exists():
            return
        if self.categoria not in Opcao.valores(Opcao.Lista.CATEGORIA_LIMPEZA):
            raise ValidationError(
                {
                    "categoria": f'A categoria "{self.categoria}" não está na lista de categorias '
                    "de limpeza (Cadastros › Opções)."
                }
            )


class PecaViatura(models.Model):
    """Peça da lista do formulário de reposição de peças das viaturas (spec 006): o quadro
    "Materiais" da folha em papel. Uma linha, um material; o nome exibido, quando preenchido,
    tem prioridade sobre o do cadastro do SCPI."""

    material = models.OneToOneField(Material, on_delete=models.PROTECT, related_name="peca_viatura")
    nome_exibido = models.CharField(max_length=255, blank=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "material__nome"]
        verbose_name = "peça das viaturas"
        verbose_name_plural = "peças das viaturas"

    def __str__(self):
        return self.nome_exibido or str(self.material)


class MaterialOficina(models.Model):
    """Material avulso do formulário da oficina mecânica (spec 007), além dos grupos da lista
    `GRUPO_OFICINA`: serve aos materiais de um grupo que não pode entrar inteiro (os óleos e
    filtros do grupo `GERAL`)."""

    material = models.OneToOneField(
        Material, on_delete=models.PROTECT, related_name="material_oficina"
    )

    class Meta:
        ordering = ["material__nome"]
        verbose_name = "material da oficina"
        verbose_name_plural = "materiais da oficina"

    def __str__(self):
        return str(self.material)


class MaterialEpi(models.Model):
    """Material avulso do formulário de EPIs (spec 008), além dos grupos da lista `GRUPO_EPI`:
    serve ao EPI de um grupo que não pode entrar inteiro."""

    material = models.OneToOneField(Material, on_delete=models.PROTECT, related_name="material_epi")

    class Meta:
        ordering = ["material__nome"]
        verbose_name = "material de EPIs"
        verbose_name_plural = "materiais de EPIs"

    def __str__(self):
        return str(self.material)


class ExcecaoMaterial(models.Model):
    """Decisão do administrador sobre um material num formulário, sobre a regra de origem (009).

    `habilitado` verdadeiro acrescenta o material ao formulário; falso o retira. Sem linha, vale a
    regra de origem de hoje. A disponibilidade efetiva é calculada (`catalogo.disponibilidade`).
    """

    material = models.ForeignKey(
        Material, on_delete=models.PROTECT, related_name="excecoes_formulario"
    )
    formulario = models.CharField(max_length=20, choices=Formulario.choices, db_index=True)
    habilitado = models.BooleanField()
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    alterado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["material__nome"]
        verbose_name = "exceção de material"
        verbose_name_plural = "exceções de material"
        constraints = [
            models.UniqueConstraint(
                fields=["material", "formulario"], name="excecao_unica_no_material_e_formulario"
            ),
        ]

    def __str__(self):
        acao = "acrescenta" if self.habilitado else "retira"
        return f"{self.get_formulario_display()}: {acao} {self.material}"


class SaidaSCPI(models.Model):
    """Linha de requisição de saída do SCPI (equivale à aba `Saídas` da planilha de mapeamento).
    Mantida pelo `importar_saidas_scpi`; consolidada pelo de/para (`ParDePara`), alimenta o
    ranking do formulário AB, a curva ABC e a reposição."""

    id_requi = models.CharField("requisição (ID)", max_length=20)
    cadpro = models.CharField("CADPRO", max_length=30, db_index=True)
    # A mesma requisição pode ter o mesmo material em mais de uma linha (outra placa, outro
    # destino). O relatório do SCPI não numera os itens: `item` é a ordem da linha entre as do
    # mesmo material na requisição (1, 2, ...). Uma requisição vem sempre inteira, com a mesma
    # data, então a reimportação dá a mesma numeração e não duplica.
    item = models.PositiveSmallIntegerField(default=1)
    data = models.DateField()
    qtd = models.DecimalField("quantidade", max_digits=14, decimal_places=4)
    valor = models.DecimalField(max_digits=16, decimal_places=5)

    class Meta:
        ordering = ["-data", "id_requi", "cadpro", "item"]
        verbose_name = "saída do SCPI"
        verbose_name_plural = "saídas do SCPI"
        constraints = [
            models.UniqueConstraint(fields=["id_requi", "cadpro", "item"], name="saida_scpi_unica"),
        ]

    def __str__(self):
        texto = f"{self.id_requi} · {self.cadpro}"
        return f"{texto} · item {self.item}" if self.item > 1 else texto


class ParDePara(models.Model):
    """Código antigo do SCPI e o código para o qual ele aponta (substitui a aba de mapeamento, o
    `DEPARA_MAP` e o `DEPARA` da planilha MAPEAMENTO DE/PARA CONSOLIDADO). Toda contagem de
    saídas usa o canônico, o destino final da cadeia de pares (`catalogo.depara`)."""

    class Origem(models.TextChoices):
        PLANILHA = "PLANILHA", "Planilha"
        SISTEMA = "SISTEMA", "Sistema"

    antigo = models.CharField("código antigo", max_length=30, unique=True)
    novo = models.CharField("código novo", max_length=30)
    fator = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("1"),
        help_text="Quantas unidades do código novo valem uma do antigo (frasco de 5 L virou "
        "item de 1 L: fator 5).",
    )
    observacao = models.CharField("observação", max_length=255, blank=True)
    origem = models.CharField(max_length=10, choices=Origem.choices, default=Origem.SISTEMA)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["antigo"]
        verbose_name = "par de/para"
        verbose_name_plural = "pares de/para"

    def __str__(self):
        return f"{self.antigo} → {self.novo}"

    def clean(self):
        erros = validar_par(self.antigo, self.novo, self.fator)
        if erros:
            raise ValidationError(erros)
        outros = list(ParDePara.objects.exclude(pk=self.pk))
        existente = next((p for p in outros if norm_u(p.antigo) == norm_u(self.antigo)), None)
        if existente:
            raise ValidationError(
                {
                    "antigo": f"O código {self.antigo} já aponta para {existente.novo}. Um "
                    "código antigo tem um só destino."
                }
            )
        try:
            resolver_canonicos(
                [Par(p.antigo, p.novo, p.fator) for p in outros]
                + [Par(self.antigo, self.novo, self.fator)]
            )
        except CicloDePara as ciclo:
            raise ValidationError(
                f"O par {self.antigo} → {self.novo} fecha um ciclo: {' → '.join(ciclo.caminho)}."
            ) from None


class ConfiguracaoCurva(models.Model):
    """Configuração geral da curva ABC e da reposição (linha única, `atual()`)."""

    janela_meses = models.PositiveIntegerField(
        "janela (meses)",
        default=12,
        validators=[MinValueValidator(1)],
        help_text="Período das curvas, da reposição e do formulário AB. Nunca começa antes de "
        "01/01/2026.",
    )
    prazo_entrega_dias = models.PositiveIntegerField(
        "prazo de entrega (dias)", default=30, validators=[MinValueValidator(1)]
    )
    cobertura_alvo_dias = models.PositiveIntegerField(
        "cobertura alvo (dias)",
        default=90,
        validators=[MinValueValidator(1)],
        help_text="Quantos dias de consumo cada compra deve cobrir.",
    )

    class Meta:
        verbose_name = "configuração da curva ABC"
        verbose_name_plural = "configuração da curva ABC"

    def __str__(self):
        return "Configuração da curva ABC"

    @classmethod
    def atual(cls) -> "ConfiguracaoCurva":
        """A linha única, criada com os padrões se ainda não existir."""
        configuracao = cls.objects.order_by("pk").first()
        return configuracao or cls.objects.create()


class ParametroReposicao(models.Model):
    """Prazo de entrega e cobertura alvo próprios de um material (vazio = valor geral)."""

    material = models.OneToOneField(
        Material, on_delete=models.PROTECT, related_name="parametro_reposicao"
    )
    prazo_entrega_dias = models.PositiveIntegerField(
        "prazo de entrega (dias)", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    cobertura_alvo_dias = models.PositiveIntegerField(
        "cobertura alvo (dias)", null=True, blank=True, validators=[MinValueValidator(1)]
    )

    class Meta:
        ordering = ["material__codigo"]
        verbose_name = "parâmetro de reposição"
        verbose_name_plural = "parâmetros de reposição"

    def __str__(self):
        return str(self.material)

    def clean(self):
        if self.prazo_entrega_dias is None and self.cobertura_alvo_dias is None:
            raise ValidationError("Preencha o prazo de entrega, a cobertura alvo ou os dois.")


# Importação recém-criada ainda conta como em andamento mesmo sem a trava (o processo está subindo).
TOLERANCIA_INICIO = timedelta(seconds=60)


def trava_importacao(tipo: str) -> str:
    """Nome da trava `GET_LOCK` que o processo segura enquanto importa o `tipo`."""
    return f"almoxarifado:importar:{tipo}"


class Importacao(models.Model):
    """Registro de cada execução de um importador; alimenta a saúde do catálogo."""

    class Tipo(models.TextChoices):
        CADASTRO = "CADASTRO", "Cadastro"
        ESTOQUE = "ESTOQUE", "Estoque"
        SAIDAS = "SAIDAS", "Saídas do SCPI"
        DEPARA = "DEPARA", "Pares de/para"

    class Situacao(models.TextChoices):
        ANDAMENTO = "ANDAMENTO", "Em andamento"
        SUCESSO = "SUCESSO", "Concluída"
        FALHA = "FALHA", "Falhou"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    inicio = models.DateTimeField("início", default=timezone.now)
    fim = models.DateTimeField(null=True, blank=True)
    situacao = models.CharField(
        "situação", max_length=20, choices=Situacao.choices, default=Situacao.ANDAMENTO
    )
    linhas = models.PositiveIntegerField(default=0)
    avisos = models.JSONField(default=list, blank=True)
    erro = models.TextField(blank=True)
    periodo_de = models.DateField("período de", null=True, blank=True)
    periodo_ate = models.DateField("período até", null=True, blank=True)

    class Meta:
        ordering = ["-inicio"]
        verbose_name = "importação"
        verbose_name_plural = "importações"

    def __str__(self):
        return f"{self.get_tipo_display()} em {timezone.localtime(self.inicio):%d/%m/%Y %H:%M}"

    @staticmethod
    def trava_ocupada(tipo: str) -> bool:
        """Se algum processo segura a trava deste tipo (a importação está rodando)."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT IS_USED_LOCK(%s)", [trava_importacao(tipo)])
            return cursor.fetchone()[0] is not None

    @classmethod
    def em_andamento(cls, agora=None):
        """Importações em andamento de verdade: as sem fim cujo tipo tem a trava ocupada, mais as
        criadas há menos de `TOLERANCIA_INICIO` (o processo ainda está subindo). As demais morreram
        sem registrar o fim (interrompidas, p. ex. com a janela do robô fechada à força)."""
        agora = agora or timezone.now()
        andamento = cls.objects.filter(situacao=cls.Situacao.ANDAMENTO)
        tipos = {
            t for t in andamento.values_list("tipo", flat=True).distinct() if cls.trava_ocupada(t)
        }
        return andamento.filter(
            models.Q(tipo__in=tipos) | models.Q(inicio__gte=agora - TOLERANCIA_INICIO)
        )

    def esta_interrompida(self, agora=None) -> bool:
        """Sem fim registrado e fora de `em_andamento` (mesma regra, para esta importação)."""
        if self.situacao != self.Situacao.ANDAMENTO:
            return False
        if self.inicio >= (agora or timezone.now()) - TOLERANCIA_INICIO:
            return False
        return not self.trava_ocupada(self.tipo)

    @property
    def interrompida(self) -> bool:
        return self.esta_interrompida()
