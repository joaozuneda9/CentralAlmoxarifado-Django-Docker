"""Aviso no Telegram a cada pedido novo (traduz `Telegram.gs`).

Sem `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`, o aviso não sai e o pedido segue gravado. É chamado
só depois da gravação (`transaction.on_commit`): falha aqui nunca desfaz o pedido. A URL da
API contém o token e por isso nunca vai para o log.
"""

import json
import logging
from html import escape
from urllib.request import Request, urlopen

from django.conf import settings

from pedidos.models import ItemPedido
from pedidos.regras import qtd_br

logger = logging.getLogger("pedidos")

MAX_ITENS_AVISO = 15


def _esc(valor) -> str:
    return escape("" if valor is None else str(valor), quote=False)


def _quantidade(qtd) -> str:
    """A quantidade exata, em pt-BR e sem zeros à direita, em qualquer origem."""
    return qtd_br(qtd)


def _corpo_do_aviso(pedido) -> str:
    """O que os avisos têm em comum: quem pediu, o destino, os materiais e a observação."""
    # Só o que o funcionário pediu (o aviso sai antes do atendimento; o filtro é por segurança).
    itens = list(pedido.itens.filter(origem=ItemPedido.Origem.PEDIDO))
    linhas = []
    for i in itens[:MAX_ITENS_AVISO]:
        unidade = f" {_esc(i.unidade)}" if i.unidade else ""
        linhas.append(
            f"• {_esc(i.material)} ({_esc(i.codigo)}) — <b>{_quantidade(i.qtd_pedida)}{unidade}</b>"
        )
    if len(itens) > MAX_ITENS_AVISO:
        linhas.append(f"<i>e mais {len(itens) - MAX_ITENS_AVISO} itens</i>")
    texto = f"{_esc(pedido.solicitante)}\nDestino: {_esc(pedido.destino)}\n\n" + "\n".join(linhas)
    if pedido.obs:
        texto += f"\n\n📝 {_esc(pedido.obs)}"
    return texto


def texto_aviso(pedido) -> str:
    return (
        f"📦 <b>Pedido {_esc(pedido.numero)}</b> — {pedido.get_origem_display()}\n"
        + _corpo_do_aviso(pedido)
    )


def texto_aviso_autorizacao(pedido) -> str:
    """O aviso à Segurança do Trabalho: há pedido de EPI esperando a decisão dela (spec 008)."""
    return (
        f"🦺 <b>{pedido.get_origem_display()} {_esc(pedido.numero)}</b> — aguardando autorização\n"
        + _corpo_do_aviso(pedido)
    )


def _enviar(chat_id: str, texto: str, url: str = "", rotulo_botao: str = "Abrir painel") -> str:
    """Envia a mensagem ao chat. Devolve "enviado", "falhou" ou "sem_configuracao"; nunca lança."""
    token = settings.TELEGRAM_TOKEN
    if not token or not chat_id:
        return "sem_configuracao"
    corpo = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}
    if url:
        corpo["reply_markup"] = {"inline_keyboard": [[{"text": rotulo_botao, "url": url}]]}
    requisicao = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(requisicao, timeout=10) as resposta:
            if resposta.status != 200:
                raise RuntimeError(f"Telegram respondeu {resposta.status}")
    except Exception as exc:
        logger.warning("Falha ao avisar no Telegram: %s", exc)
        return "falhou"
    return "enviado"


def notificar_pedido(pedido, url_painel: str = "") -> str:
    """Avisa o almoxarifado de um pedido novo. Devolve "enviado", "falhou" ou "sem_configuracao";
    nunca lança."""
    return _enviar(settings.TELEGRAM_CHAT_ID, texto_aviso(pedido), url_painel, "Abrir painel")


def notificar_autorizacao_pendente(pedido, url_fila: str = "") -> str:
    """Avisa a Segurança do Trabalho (chat próprio) de um pedido de EPI aguardando autorização.
    Mesmo resultado e mesma garantia de `notificar_pedido`."""
    return _enviar(
        settings.TELEGRAM_CHAT_ID_SEGURANCA, texto_aviso_autorizacao(pedido), url_fila, "Abrir fila"
    )
