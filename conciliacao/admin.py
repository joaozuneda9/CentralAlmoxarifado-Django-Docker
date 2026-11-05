from django.contrib import admin

from catalogo.admin import SoLeituraAdmin

from .models import (
    Candidata,
    ConferenciaLote,
    CorrecaoVinculo,
    ExtracaoOficial,
    ItemOficial,
    RequisicaoOficial,
    TentativaLancamento,
)


@admin.register(ExtracaoOficial)
class ExtracaoOficialAdmin(SoLeituraAdmin):
    list_display = ("importacao", "motivo", "execucao", "requisicoes", "maior_requisicao")
    list_filter = ("motivo",)
    list_select_related = ("importacao", "execucao")
    exclude = ("arquivo",)


class ItemOficialInline(admin.TabularInline):
    model = ItemOficial
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RequisicaoOficial)
class RequisicaoOficialAdmin(SoLeituraAdmin):
    list_display = ("requisicao", "data", "tipo", "cod_ccusto", "lote_observado", "extracao")
    search_fields = ("requisicao", "lote_observado", "recebedor")
    inlines = [ItemOficialInline]


@admin.register(TentativaLancamento)
class TentativaLancamentoAdmin(SoLeituraAdmin):
    list_display = ("execucao", "ordem", "lote", "resultado", "requisicao", "momento")
    list_filter = ("resultado", "historica")
    list_select_related = ("execucao",)
    search_fields = ("lote", "requisicao")


class CandidataInline(admin.TabularInline):
    model = Candidata
    extra = 0
    can_delete = False
    fields = ("ordem", "requisicao", "e_esta")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ConferenciaLote)
class ConferenciaLoteAdmin(SoLeituraAdmin):
    list_display = ("lote", "tipo", "veredito", "requisicao", "extracao", "criada_em")
    list_filter = ("tipo", "veredito")
    list_select_related = ("requisicao", "extracao__importacao")
    search_fields = ("lote",)
    inlines = [CandidataInline]


@admin.register(CorrecaoVinculo)
class CorrecaoVinculoAdmin(SoLeituraAdmin):
    list_display = ("lote", "anterior", "novo", "usuario", "quando")
    search_fields = ("lote", "anterior", "novo")
    list_select_related = ("usuario",)
