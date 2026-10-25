"""Proteção dos formulários públicos contra envio automático (spec, fluxo 1).

A página leva um token assinado com o identificador do envio e o momento em que abriu: o
identificador vira o `Pedido.id` (nunca escolhido pelo navegador) e o momento barra o envio
feito em menos de `PEDIDOS_TEMPO_MINIMO` segundos. Um campo isca, invisível para pessoas,
recusa robôs que preenchem tudo.

Cada recusa tem o seu motivo, e só a isca (que uma pessoa nunca preenche) recebe a mensagem
genérica: o token inválido e o envio rápido demais dizem à pessoa o que fazer, com os dados
mantidos.
"""

import time
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core import signing

SALT = "pedidos.envio"
CAMPO_ISCA = "confirmacao_extra"
MOTIVO_ISCA = "isca"
MOTIVO_RAPIDO = "rapido"
MENSAGEM_RECUSA = "Não foi possível registrar o pedido. Procure o almoxarifado."
MENSAGEM_TOKEN_INVALIDO = (
    "Houve um problema ao confirmar o formulário. Seus dados foram mantidos: "
    "toque em Enviar de novo."
)
MENSAGEM_RAPIDO = "Aguarde alguns segundos e toque em Enviar de novo."


@dataclass(frozen=True)
class Envio:
    id: uuid.UUID
    aberto_em: float
    token: str


def emitir(envio_id: uuid.UUID | None = None, aberto_em: float | None = None) -> Envio:
    envio_id = envio_id or uuid.uuid4()
    aberto_em = time.time() if aberto_em is None else aberto_em
    token = signing.dumps({"id": str(envio_id), "aberto_em": aberto_em}, salt=SALT)
    return Envio(envio_id, aberto_em, token)


def ler(token: str) -> Envio | None:
    """O envio do token, ou None se a assinatura ou o conteúdo não valem. O token não tem
    validade: o identificador é único e o reenvio de um pedido igual só o confirma."""
    try:
        dados = signing.loads(token or "", salt=SALT)
        return Envio(uuid.UUID(dados["id"]), float(dados["aberto_em"]), token)
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return None


def recusar(envio: Envio, isca: str, agora: float | None = None) -> str | None:
    """O motivo da recusa (`MOTIVO_ISCA` ou `MOTIVO_RAPIDO`), ou None se o envio pode seguir.
    A isca vale mais: campo isca preenchido recusa mesmo depois do tempo mínimo."""
    agora = time.time() if agora is None else agora
    if (isca or "").strip():
        return MOTIVO_ISCA
    if agora - envio.aberto_em < settings.PEDIDOS_TEMPO_MINIMO:
        return MOTIVO_RAPIDO
    return None
