from django.db import migrations, models

# Unidades do SCPI em que a quantidade pode ter fração (spec 005). Lista vazia significa que todo
# material aceita só inteiro, então a carga vai nesta migration, para os formulários já aceitarem
# fração em metro, quilo e litro logo depois da implantação. Quem administra o cadastro ajusta a
# lista no admin (Opções), sem nova publicação.
UNIDADES_FRACIONAVEIS = ("M", "MT", "MTS", "KM", "KG", "L", "LT", "M²", "M³", "T")


def carregar_unidades(apps, schema_editor):
    """Idempotente: o que já existe (inclusive desativado pelo admin) fica como está."""
    Opcao = apps.get_model("catalogo", "Opcao")
    for ordem, valor in enumerate(UNIDADES_FRACIONAVEIS):
        Opcao.objects.get_or_create(
            lista="UNIDADE_FRACIONAVEL",
            valor=valor,
            defaults={"ordem": ordem, "ativo": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="opcao",
            name="lista",
            field=models.CharField(
                choices=[
                    ("TIPO_SAIDA", "Tipos de saída"),
                    ("GRUPO_OCULTO_AB", "Grupos ocultos (AB)"),
                    ("CATEGORIA_LIMPEZA", "Categorias (limpeza)"),
                    ("FUNCIONARIO", "Funcionários"),
                    ("UNIDADE_FRACIONAVEL", "Unidades fracionáveis"),
                ],
                max_length=30,
            ),
        ),
        # A reversão não apaga nada: a lista pode ter sido ajustada à mão.
        migrations.RunPython(carregar_unidades, migrations.RunPython.noop),
    ]
