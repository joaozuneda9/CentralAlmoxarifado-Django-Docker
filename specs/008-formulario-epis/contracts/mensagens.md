# Contrato: textos ao usuário e avisos

Textos em pt-BR, no registro dos formulários existentes. O texto final pode ser ajustado na
implementação sem mudar o contrato: o que vale é **o que cada um diz e o que não diz**.

## Tela de sucesso do pedido de EPI (FR-009, FR-031b)

- Título e número do pedido como nos outros formulários (o número em fonte mono, para anotar).
- Frase: o pedido foi **registrado e aguarda a autorização da Segurança do Trabalho**; só depois dela o
  almoxarifado atende, e a entrega depende desse atendimento.
- Frase: para saber o resultado, consulte com o número em `<link da consulta>`.
- **Não diz** "pedido enviado ao almoxarifado" nem sugere que o EPI será entregue.

## Consulta pública (FR-031, FR-031a)

| Situação | Texto |
|----------|-------|
| aguardando | "Pedido <número>: aguardando autorização da Segurança do Trabalho." |
| autorizado | "Pedido <número>: autorizado. O almoxarifado vai atendê-lo; procure o almoxarifado para retirar." |
| recusado | "Pedido <número>: recusado pela Segurança do Trabalho." + "Motivo: <motivo>" |
| não encontrado (inexistente ou de outro formulário) | "Não encontramos um pedido de EPIs com este número." (a mesma nos dois casos) |
| limite atingido | "Muitas consultas desta rede em pouco tempo. Procure o almoxarifado." (não a mensagem do limite de pedidos) |

Nenhum deles mostra nome, destino, observação nem materiais.

## Detalhe e fila da Segurança do Trabalho

- Recusa sem motivo: "Informe o motivo da recusa."
- Decisão já gravada: "Este pedido já foi <autorizado|recusado> por <nome> em <dd/mm/aaaa hh:mm>."
- Usuário fora do grupo ou rota fora da lista: 403 / redirecionamento à fila (rotas-e-acesso.md).

## Detalhe do almoxarifado

- Aguardando: selo "Aguardando autorização"; no lugar do formulário de atendimento, "Este pedido ainda
  não foi autorizado pela Segurança do Trabalho e não pode ser atendido."
- Recusado: selo "Recusado"; "Recusado por <nome> em <data>. Motivo: <motivo>." Encerrado.
- Autorizado: selo e "Autorizado por <nome> em <data>" acima do atendimento de hoje.

## Telegram

- **À Segurança do Trabalho** (ao registrar, chat `TELEGRAM_CHAT_ID_SEGURANCA`): "Pedido de EPIs
  <número> aguardando autorização", nome de quem pediu e os materiais (até 15, como hoje), botão "Abrir
  fila" para `pedidos:autorizacoes`. Vazio o chat: não sai, o pedido segue gravado.
- **Ao almoxarifado** (ao autorizar, chat `TELEGRAM_CHAT_ID`): o aviso de pedido novo de hoje. Não sai
  para pedido aguardando nem recusado.
- Falha de envio nunca desfaz pedido nem decisão.
