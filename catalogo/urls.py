from django.urls import path

from catalogo import views, views_formularios

app_name = "catalogo"

urlpatterns = [
    path("curva/", views.curva, name="curva"),
    path("formularios/", views_formularios.formularios, name="formularios"),
    path(
        "formularios/centros/",
        views_formularios.formularios_centros,
        name="formularios_centros",
    ),
    path(
        "formularios/material/<str:codigo>/",
        views_formularios.formularios_material,
        name="formularios_material",
    ),
    path("formularios/lote/", views_formularios.formularios_lote, name="formularios_lote"),
    path(
        "formularios/centros/ativo/", views_formularios.formularios_ativo, name="formularios_ativo"
    ),
    path(
        "formularios/excecao/",
        views_formularios.formularios_excecao,
        name="formularios_excecao",
    ),
    path("formularios/regra/", views_formularios.formularios_regra, name="formularios_regra"),
]
