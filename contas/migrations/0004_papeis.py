"""Cria os papéis Atendimento e Gestão e os dá a quem já usa a área interna (spec 012).

No dia da implantação ninguém perde acesso: todo usuário ativo que não é da Segurança do Trabalho
fica com os dois papéis, e a migration confere isso no fim (levanta erro e desfaz tudo se faltar).
O administrador restringe depois, no admin.

As permissões do `Meta` do `Usuario` só seriam criadas pelo `post_migrate`, depois de todas as
migrations da execução; por isso esta migration as cria (`get_or_create`, sem duplicar o que o
`post_migrate` faz depois).

Nomes e codinomes copiados de propósito: uma migration não pode mudar de comportamento se as
constantes de `contas.acesso` mudarem um dia.
"""

from django.db import migrations

PERMISSOES = {
    "atender_pedidos": "Atender pedidos (painel, atendimento, edição e saída avulsa)",
    "operar_automacoes": "Operar as automações (SCPI, importações e conferência)",
    "ver_curva": "Ver a Curva ABC",
    "ver_formularios": "Ver a configuração dos formulários",
}
GRUPOS = {
    "Atendimento": ["atender_pedidos"],
    "Gestão": ["operar_automacoes", "ver_curva", "ver_formularios"],
}
SEGURANCA_TRABALHO = "Segurança do Trabalho"


def criar_permissoes(apps):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    tipo, _ = ContentType.objects.get_or_create(app_label="contas", model="usuario")
    return {
        codinome: Permission.objects.get_or_create(
            content_type=tipo, codename=codinome, defaults={"name": nome}
        )[0]
        for codinome, nome in PERMISSOES.items()
    }


def criar_grupos(apps, permissoes):
    Group = apps.get_model("auth", "Group")
    grupos = []
    for nome, codinomes in GRUPOS.items():
        grupo, _ = Group.objects.get_or_create(name=nome)
        grupo.permissions.add(*(permissoes[c] for c in codinomes))
        grupos.append(grupo)
    return grupos


def usuarios_do_almoxarifado(apps):
    Usuario = apps.get_model("contas", "Usuario")
    return Usuario.objects.filter(is_active=True).exclude(groups__name=SEGURANCA_TRABALHO)


def dar_papeis(apps, grupos):
    for usuario in usuarios_do_almoxarifado(apps):
        usuario.groups.add(*grupos)


def conferir(apps):
    Permission = apps.get_model("auth", "Permission")
    faltando = []
    for usuario in usuarios_do_almoxarifado(apps):
        tem = set(
            Permission.objects.filter(
                group__user=usuario, content_type__app_label="contas"
            ).values_list("codename", flat=True)
        )
        if not set(PERMISSOES) <= tem:
            faltando.append(usuario.username)
    if faltando:
        raise RuntimeError(
            "Usuários sem todos os papéis depois da migração: " + ", ".join(sorted(faltando))
        )


def aplicar(apps, schema_editor):
    permissoes = criar_permissoes(apps)
    grupos = criar_grupos(apps, permissoes)
    dar_papeis(apps, grupos)
    conferir(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("contas", "0003_permissoes"),
    ]

    operations = [
        # Reverter não apaga grupos nem permissões: podem já ter sido ajustados à mão.
        migrations.RunPython(aplicar, migrations.RunPython.noop),
    ]
