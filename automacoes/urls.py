from django.urls import path

from automacoes import views

app_name = "automacoes"

urlpatterns = [
    path("", views.pagina, name="pagina"),
    path("atualizar/", views.atualizar, name="atualizar"),
    path("importar/<str:robo>/", views.importar, name="importar"),
    path("lancar/", views.lancar, name="lancar"),
    path("lancamento/<str:lote>/resolver/", views.resolver, name="resolver"),
    path("lancamento/conferir/", views.conferir, name="conferir"),
    path("lancamento/<str:lote>/corrigir/", views.corrigir, name="corrigir"),
]
