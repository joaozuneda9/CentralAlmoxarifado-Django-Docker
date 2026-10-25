from django.urls import path

from pedidos.views import almoxarifado, autorizacao, materiais, publico

app_name = "pedidos"

urlpatterns = [
    path("", publico.inicio, name="inicio"),
    path("pedido/epis/consulta/", publico.consulta_epi, name="consulta_epi"),
    path("pedido/<str:fluxo>/", publico.formulario, name="formulario"),
    path("pedido/<str:fluxo>/materiais/", materiais.materiais, name="materiais"),
    path("pedido/<str:fluxo>/carrinho/", materiais.carrinho, name="carrinho"),
    path("painel/", almoxarifado.painel, name="painel"),
    path("painel/pedidos/<str:numero>/", almoxarifado.detalhe, name="detalhe"),
    path("painel/pedidos/<str:numero>/atender/", almoxarifado.atender, name="atender"),
    path("painel/pedidos/<str:numero>/editar/", almoxarifado.editar, name="editar"),
    path(
        "painel/pedidos/<str:numero>/materiais/",
        almoxarifado.atendimento_materiais,
        name="atendimento_materiais",
    ),
    path(
        "painel/pedidos/<str:numero>/adicionar/",
        almoxarifado.atendimento_adicionar,
        name="atendimento_adicionar",
    ),
    path("painel/saida-avulsa/", almoxarifado.avulsa, name="avulsa"),
    path(
        "painel/saida-avulsa/materiais/",
        almoxarifado.avulsa_materiais,
        name="avulsa_materiais",
    ),
    path("painel/saida-avulsa/carrinho/", almoxarifado.avulsa_carrinho, name="avulsa_carrinho"),
    path("painel/recibos/impressos/", almoxarifado.marcar_impressos, name="marcar_impressos"),
    path("painel/autorizacoes/", autorizacao.autorizacoes, name="autorizacoes"),
    path("painel/autorizacoes/<str:numero>/", autorizacao.autorizacao, name="autorizacao"),
    path(
        "painel/autorizacoes/<str:numero>/decidir/",
        autorizacao.decidir,
        name="decidir",
    ),
]
