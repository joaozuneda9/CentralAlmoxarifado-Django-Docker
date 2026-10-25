"""Filtro de rotas do usuário da Segurança do Trabalho (spec 008, FR-017).

O sistema não tem papéis; este filtro é o único lugar que separa o que o usuário do grupo enxerga.
Nega por padrão: só abre as rotas de `contas.acesso.ROTAS_SEGURANCA_TRABALHO`, e uma rota criada
amanhã já nasce fechada para ele. As views existentes não mudam, e quem não é do grupo passa direto.

Roda em `process_view`, quando a rota já foi resolvida (`request.resolver_match`); URL que não
resolve nem chega aqui e segue ao 404 do Django, onde não há o que proteger.
"""

from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse

from contas.acesso import ROTAS_SEGURANCA_TRABALHO, da_seguranca_trabalho


class RestringirSegurancaTrabalho:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not da_seguranca_trabalho(getattr(request, "user", None)):
            return None
        if request.resolver_match.view_name in ROTAS_SEGURANCA_TRABALHO:
            return None
        if request.method in ("GET", "HEAD"):
            return HttpResponseRedirect(reverse("pedidos:autorizacoes"))
        return HttpResponseForbidden("Acesso restrito às autorizações de EPIs.")
