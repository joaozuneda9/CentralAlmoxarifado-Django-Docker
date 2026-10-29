"""Apresentação das situações do pedido e no SCPI (classe do selo; o texto vem das regras)."""

import re

from django import template

from pedidos.regras import (
    AUTORIZACAO_AGUARDANDO,
    AUTORIZACAO_AUTORIZADA,
    AUTORIZACAO_RECUSADA,
    LIMPEZA,
    frase_diferenca,
    qtd_br,
)

register = template.Library()

_SITUACAO = {
    "aguardando_autorizacao": "selo-aviso",
    "recusado": "selo-erro",
    "aguardando": "selo-info",
    "atendido": "selo-ok",
    "parcial": "selo-aviso",
}
_SCPI = {
    "sem": "selo-neutro",
    "aguardando": "selo-info",
    "parcial": "selo-aviso",
    "lancado": "selo-ok",
    "atencao": "selo-erro",
}
_AUTORIZACAO = {
    AUTORIZACAO_AGUARDANDO: "selo-aviso",
    AUTORIZACAO_AUTORIZADA: "selo-ok",
    AUTORIZACAO_RECUSADA: "selo-erro",
}


_ORIGEM_CURTA = {LIMPEZA: "Limpeza"}


@register.filter
def origem_curta(pedido) -> str:
    """Nome curto da origem para o selo da lista; o nome inteiro vai no title."""
    return _ORIGEM_CURTA.get(pedido.origem, pedido.get_origem_display())


@register.filter
def badge_situacao(chave: str) -> str:
    return _SITUACAO.get(chave, "selo-neutro")


@register.filter
def badge_scpi(chave: str) -> str:
    return _SCPI.get(chave, "selo-neutro")


@register.filter
def badge_autorizacao(situacao: str) -> str:
    return _AUTORIZACAO.get(situacao, "selo-neutro")


@register.filter
def nome_usuario(usuario) -> str:
    """Nome completo do usuário, ou a matrícula quando não tem nome."""
    return usuario.get_full_name() or usuario.username


@register.filter(name="frase_diferenca")
def frase_diferenca_filtro(diferenca: dict) -> str:
    """Uma diferença do histórico de alterações em frase (`regras.frase_diferenca`)."""
    return frase_diferenca(diferenca)


@register.filter
def qtd_campo(valor) -> str:
    """Quantidade num valor que volta a um campo ou é lido pelo JS (`data-pedido`): pt-BR sem o
    "." do milhar (`regras.qtd_br`), que o `parse_qtd_br` aceita. Para exibir, `quantidade`."""
    return "" if valor in (None, "") else qtd_br(valor)


@register.filter
def obter(dicionario: dict, chave: str):
    """`dicionario|obter:chave`: o valor da chave, ou vazio."""
    return dicionario.get(chave, "")


@register.filter
def por_origem(itens, origem: str) -> list:
    """Itens do pedido de uma origem (`PEDIDO` ou `ALMOXARIFADO`), na ordem do pedido."""
    return [i for i in itens if i.origem == origem]


@register.simple_tag
def proximos_passos(pedido) -> list[str]:
    """O que o almoxarifado ainda precisa fazer neste estágio do pedido (texto da tela; as regras
    de situação ficam em `regras.py`)."""
    chave = pedido.situacao.chave
    if chave == "aguardando_autorizacao":
        return [
            "Aguarde a autorização da Segurança do Trabalho: o pedido ainda não pode ser atendido.",
            "O aviso do pedido chega ao almoxarifado depois que ela autorizar.",
        ]
    if chave == "recusado":
        return ["Pedido recusado pela Segurança do Trabalho: está encerrado e não há o que fazer."]
    if chave == "aguardando":
        return [
            "Confira e preencha as quantidades separadas na tabela de materiais.",
            "Preencha os dados da saída e confirme o atendimento no formulário abaixo.",
        ]
    passos = []
    if chave == "parcial":
        passos.append(
            "Algum material saiu em quantidade menor que a pedida: confira a coluna Entregue."
        )
    if pedido.situacao_scpi.chave == "atencao":
        # O cartão do SCPI saiu do recibo: o que pede ação vira um passo aqui.
        passos.append(
            f"{pedido.situacao_scpi.rotulo}: o robô não concluiu o lançamento. Confira e resolva "
            "em Automações › Lançamento no SCPI."
        )
    atendimento = pedido.atendimento_ou_none
    if atendimento and atendimento.recibo_impresso_em:
        passos.append("Recibo já impresso. Não há mais nada a fazer neste pedido.")
    else:
        passos.append("Imprima o recibo e colha a assinatura de quem recebeu.")
    return passos


# Siglas que continuam em maiúsculas em `frase`; o que está entre parênteses também fica como veio.
_SIGLAS = {"EPI", "ETA", "ETE", "PVC", "PEAD", "PPR", "CPVC", "LED", "GLP", "ABNT"}


@register.filter
def frase(texto: str) -> str:
    """Só a primeira letra maiúscula ("AUTO PECAS" vira "Auto pecas"), para nomes do cadastro que
    vêm todos em maiúsculas. Só apresentação: o valor gravado e filtrado não muda."""
    if not texto:
        return texto
    partes = []
    for trecho in re.split(r"(\([^)]*\))", texto):
        if trecho.startswith("("):
            partes.append(trecho)
            continue
        partes.append(
            re.sub(
                r"[^\W\d_]+",
                lambda m: m.group(0) if m.group(0).upper() in _SIGLAS else m.group(0).lower(),
                trecho,
            )
        )
    junto = "".join(partes)
    primeira = re.search(r"[^\W\d_]", junto)
    if not primeira:
        return junto
    i = primeira.start()
    return junto[:i] + junto[i].upper() + junto[i + 1 :]
