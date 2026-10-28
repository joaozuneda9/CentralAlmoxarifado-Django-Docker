"""Formulário do lançamento no SCPI: o modo (vem do botão clicado, "Simular" ou "Lançar no SCPI")
e as requisições escolhidas na fila."""

from django import forms
from django.conf import settings

from pedidos.consultas import fila_do_robo
from scpi.lancamento import LANCAMENTO_BLOQUEADO

MODOS = [("lancar", "Lançar no SCPI"), ("simular", "Simular (preenche e descarta, sem salvar)")]


class LancamentoForm(forms.Form):
    modo = forms.ChoiceField(label="Modo", choices=MODOS)
    lotes = forms.MultipleChoiceField(
        label="Requisições",
        error_messages={
            "required": "Marque ao menos uma requisição da fila.",
            "invalid_choice": "A requisição %(value)s não está mais na fila do robô.",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Só o que está na fila agora: uma requisição lançada ou travada depois de a página abrir
        # é recusada aqui, não chega ao robô.
        self.fields["lotes"].choices = [(r.lote, r.lote) for r in fila_do_robo().requisicoes]

    def clean_modo(self):
        modo = self.cleaned_data["modo"]
        if modo == "lancar" and not settings.LANCAMENTO_REAL:
            raise forms.ValidationError(LANCAMENTO_BLOQUEADO)
        return modo

    @classmethod
    def da_requisicao(cls, post):
        """Aceita também o formato antigo dos botões (`simulacao=1`, sem `modo`)."""
        dados = post.copy()
        if not dados.get("modo"):
            dados["modo"] = "simular" if dados.get("simulacao") else "lancar"
        return cls(dados)
