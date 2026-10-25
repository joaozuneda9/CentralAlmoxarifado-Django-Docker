"""Cria o grupo da Segurança do Trabalho (spec 008), para o administrador só marcá-lo no usuário."""

from django.db import migrations

# O mesmo texto de `contas.acesso.GRUPO_SEGURANCA_TRABALHO`, copiado de propósito: uma migration
# não pode mudar de comportamento se a constante mudar um dia.
NOME = "Segurança do Trabalho"


def criar_grupo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=NOME)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contas", "0001_initial"),
    ]

    operations = [
        # Reverter não apaga o grupo: ele pode já ter usuários.
        migrations.RunPython(criar_grupo, migrations.RunPython.noop),
    ]
