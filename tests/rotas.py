"""As rotas nomeadas do projeto, para os testes de acesso (specs 008 e 012)."""

from django.urls import URLPattern, URLResolver, get_resolver, reverse


def rotas_nomeadas():
    """Toda rota com nome do projeto (com o namespace), com uma URL concreta de teste."""
    achadas = {}

    def andar(padroes, namespace):
        for p in padroes:
            if isinstance(p, URLResolver):
                novo = f"{namespace}{p.namespace}:" if p.namespace else namespace
                andar(p.url_patterns, novo)
            elif isinstance(p, URLPattern) and p.name:
                nome = f"{namespace}{p.name}"
                parametros = list(p.pattern.regex.groupindex) or list(
                    getattr(p.pattern, "converters", {})
                )
                kwargs = {k: "1" for k in parametros}
                try:
                    achadas.setdefault(nome, reverse(nome, kwargs=kwargs))
                except Exception:  # rota que o reverse não monta com um valor qualquer
                    continue

    andar(get_resolver().url_patterns, "")
    return achadas
