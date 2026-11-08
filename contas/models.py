from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """Usuário da área do almoxarifado. Entra pela matrícula (guardada em `username`)."""

    username = models.CharField(
        "matrícula",
        max_length=30,
        unique=True,
        error_messages={"unique": "Já existe um usuário com esta matrícula."},
    )

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        # Papéis da área interna (spec 012): o código pergunta por estas permissões, e os grupos
        # Atendimento e Gestão as reúnem (`contas.acesso`).
        permissions = [
            ("atender_pedidos", "Atender pedidos (painel, atendimento, edição e saída avulsa)"),
            ("operar_automacoes", "Operar as automações (SCPI, importações e conferência)"),
            ("ver_curva", "Ver a Curva ABC"),
            ("ver_formularios", "Ver a configuração dos formulários"),
        ]
