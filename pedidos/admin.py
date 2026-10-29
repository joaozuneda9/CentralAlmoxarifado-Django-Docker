from django.contrib import admin

from catalogo.admin import SoLeituraAdmin
from pedidos.models import (
    AlteracaoPedido,
    Atendimento,
    ExecucaoRobo,
    ItemPedido,
    LinhaSaida,
    Pedido,
)


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    fields = [
        "codigo",
        "material",
        "unidade",
        "qtd_pedida",
        "qtd_entregue",
        "origem",
        "no_lugar_de",
        "adicionado_por",
    ]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Pedido)
class PedidoAdmin(SoLeituraAdmin):
    list_display = ["numero", "origem", "criado_em", "solicitante", "destino"]
    list_filter = ["origem"]
    search_fields = ["numero", "solicitante"]
    inlines = [ItemPedidoInline]


@admin.register(Atendimento)
class AtendimentoAdmin(SoLeituraAdmin):
    list_display = ["pedido", "data_efetiva", "recebedor", "centro_custo", "recibo_impresso_em"]
    search_fields = ["pedido__numero", "recebedor"]


@admin.register(AlteracaoPedido)
class AlteracaoPedidoAdmin(SoLeituraAdmin):
    list_display = ["pedido", "versao", "em", "usuario"]
    search_fields = ["pedido__numero"]


@admin.register(LinhaSaida)
class LinhaSaidaAdmin(admin.ModelAdmin):
    """Só o superusuário corrige o resultado do lançamento; o resto espelha o atendimento."""

    list_display = ["lote", "seq", "codigo", "qtd", "status", "requisicao_scpi"]
    list_filter = ["status"]
    search_fields = ["lote", "codigo"]
    editaveis = ("status", "requisicao_scpi", "lancado_em", "mensagem")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        return [campo.name for campo in self.model._meta.fields if campo.name not in self.editaveis]


@admin.register(ExecucaoRobo)
class ExecucaoRoboAdmin(SoLeituraAdmin):
    list_display = ["inicio", "simulacao", "situacao", "iniciada_por", "fim"]
    list_select_related = ["iniciada_por"]
    list_filter = ["simulacao", "situacao"]
