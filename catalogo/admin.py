from django import forms
from django.contrib import admin, messages
from django.db.models import OuterRef, Subquery

from catalogo.models import (
    CentroCusto,
    ConfiguracaoCurva,
    Importacao,
    ItemLimpeza,
    Material,
    Opcao,
    ParametroReposicao,
    ParDePara,
    PecaViatura,
    SaidaSCPI,
)


class SoLeituraAdmin(admin.ModelAdmin):
    """Só consulta: o conteúdo vem do SCPI pelos importadores."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Material)
class MaterialAdmin(SoLeituraAdmin):
    list_display = ["codigo", "nome", "unidade", "grupo", "estoque", "oculto", "duplicado"]
    search_fields = ["codigo", "nome"]
    list_filter = ["oculto", "duplicado", "grupo"]


@admin.register(SaidaSCPI)
class SaidaSCPIAdmin(SoLeituraAdmin):
    list_display = ["id_requi", "cadpro", "data", "qtd", "valor"]
    search_fields = ["cadpro", "id_requi"]
    date_hierarchy = "data"


@admin.register(Importacao)
class ImportacaoAdmin(SoLeituraAdmin):
    list_display = ["tipo", "inicio", "fim", "situacao", "linhas"]
    list_filter = ["tipo", "situacao"]


class ItemLimpezaForm(forms.ModelForm):
    categoria = forms.ChoiceField()

    class Meta:
        model = ItemLimpeza
        fields = ["material", "categoria", "nome_exibido", "unidade_exibida", "ordem"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categorias = Opcao.valores(Opcao.Lista.CATEGORIA_LIMPEZA)
        atual = self.instance.categoria if self.instance.pk else ""
        if atual and atual not in categorias:
            categorias.append(atual)  # não perde a categoria de um item antigo
        self.fields["categoria"].choices = [("", "---------")] + [(c, c) for c in categorias]


@admin.register(ItemLimpeza)
class ItemLimpezaAdmin(admin.ModelAdmin):
    form = ItemLimpezaForm
    autocomplete_fields = ["material"]
    list_display = ["material", "categoria", "nome_exibido", "unidade_exibida", "ordem"]
    list_editable = ["ordem"]
    list_filter = ["categoria"]
    search_fields = ["material__codigo", "material__nome", "nome_exibido"]


@admin.register(PecaViatura)
class PecaViaturaAdmin(admin.ModelAdmin):
    """A lista de peças do formulário de reposição de peças das viaturas (spec 006): uma linha por
    material, com o nome que a equipe conhece e a ordem da folha."""

    autocomplete_fields = ["material"]
    list_display = ["material", "nome_exibido", "ordem"]
    list_editable = ["ordem"]
    search_fields = ["material__codigo", "material__nome", "nome_exibido"]


@admin.register(CentroCusto)
class CentroCustoAdmin(admin.ModelAdmin):
    """Os centros de custo: criar, editar e ativar ou inativar. Onde cada linha é destino se define
    na página Formulários (spec 009); a marca antiga de equipe de manutenção saiu."""

    list_display = ["descricao", "codigo", "placa", "ativo"]
    list_editable = ["ativo"]
    list_filter = ["ativo"]
    exclude = ["equipe_manutencao"]
    search_fields = ["descricao", "codigo", "placa"]


@admin.register(Opcao)
class OpcaoAdmin(admin.ModelAdmin):
    list_display = ["valor", "lista", "ordem", "ativo"]
    list_editable = ["ordem", "ativo"]
    list_filter = ["lista", "ativo"]
    search_fields = ["valor"]


@admin.register(ParDePara)
class ParDeParaAdmin(admin.ModelAdmin):
    fields = ["antigo", "novo", "fator", "observacao", "origem", "atualizado_em"]
    readonly_fields = ["origem", "atualizado_em"]
    list_display = ["antigo", "novo", "nome_do_novo", "fator", "origem", "atualizado_em"]
    list_filter = ["origem"]
    search_fields = ["antigo", "novo"]

    def get_queryset(self, request):
        nome = Material.objects.filter(codigo=OuterRef("novo")).values("nome")[:1]
        return super().get_queryset(request).annotate(nome_novo=Subquery(nome))

    @admin.display(description="material novo")
    def nome_do_novo(self, obj):
        return obj.nome_novo or "—"

    def save_model(self, request, obj, form, change):
        obj.origem = ParDePara.Origem.SISTEMA
        super().save_model(request, obj, form, change)
        if not Material.objects.filter(codigo=obj.novo).exists():
            messages.warning(request, f"O código {obj.novo} ainda não está no cadastro do SCPI.")


@admin.register(ConfiguracaoCurva)
class ConfiguracaoCurvaAdmin(admin.ModelAdmin):
    """Linha única: sem incluir uma segunda nem excluir a existente."""

    list_display = ["__str__", "janela_meses", "prazo_entrega_dias", "cobertura_alvo_dias"]

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not ConfiguracaoCurva.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ParametroReposicao)
class ParametroReposicaoAdmin(admin.ModelAdmin):
    autocomplete_fields = ["material"]
    list_display = ["material", "prazo_entrega_dias", "cobertura_alvo_dias"]
    search_fields = ["material__codigo", "material__nome"]
