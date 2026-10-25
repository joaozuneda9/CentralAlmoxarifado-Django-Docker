# Contrato: catálogo único de mensagens

Cada causa tem **um texto só**, o mesmo ao adicionar, ao alterar e ao enviar, nos dois formulários
(FR-022). `{u}` é a unidade (omitida, com o parêntese, quando o material não tem); `{N}` é o número
sem zeros à direita; `{nome}` e `{codigo}` são do material.

## Quantidade

| Causa | Material | Texto |
|---|---|---|
| ilegível ou zero | fracionável | Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5). |
| ilegível ou zero | contado | Informe um número inteiro maior que zero. |
| fração em contado | contado | Este material só é pedido em quantidade inteira (unidade: {u}). |
| acima de 999.999 | qualquer | A quantidade máxima é 999.999. |
| acima do estoque | qualquer | Quantidade acima do estoque. Estoque disponível: {N} {u}. |
| sem estoque | qualquer | Sem estoque. |
| já há no pedido (cabe parte) | qualquer | Já há {N} {u} no pedido; é possível acrescentar no máximo {N} {u}. |
| já há no pedido (não cabe) | qualquer | Já há {N} {u} no pedido, que é todo o estoque disponível. |
| mais de 40 materiais | qualquer | O pedido pode ter no máximo 40 materiais. |
| material repetido (aviso) | qualquer | {nome} já estava no pedido: {N} {u} + {N} {u} = {N} {u}. |

Na validação do envio, cada texto vem precedido do nome do material quando for um erro de item
(`{nome} ({codigo}): …`), para o resumo no topo; o texto da causa é o da tabela.

## Bloqueio na lista

| Motivo | Texto do selo |
|---|---|
| Cadastro duplicado | Cadastro duplicado — avise o almoxarifado |
| Máximo pedível zero | Sem estoque |

## Estados do formulário

| Estado | Texto |
|---|---|
| Indisponível (os dois formulários) | Este formulário está indisponível no momento. Avise o almoxarifado. |
| Sem estoque agora | Nenhum material deste formulário tem estoque agora. |
| Sem JavaScript | Este formulário precisa de JavaScript para funcionar. Ative o JavaScript no navegador, use outro navegador ou procure o almoxarifado. |

## Proteções

| Motivo | Texto |
|---|---|
| Ingresso inválido | Houve um problema ao confirmar o formulário. Seus dados foram mantidos: toque em Enviar de novo. |
| Envio rápido demais | Aguarde alguns segundos e toque em Enviar de novo. |
| Isca preenchida | Não foi possível registrar o pedido. Procure o almoxarifado. |
| Limite por IP / por nome | Sem mudança (`MENSAGEM_LIMITE_IP`, `MENSAGEM_LIMITE_SOLICITANTE`) |
| Reenvio divergente | Sem mudança (`mensagem_divergente`) |

Nenhuma mensagem diz que o formulário "expirou" (FR-027).

## Saúde do catálogo (painel)

| Situação | Nível | Texto |
|---|---|---|
| Saldo nunca importado | erro | Sem saldo importado: os formulários de limpeza e AB ficam indisponíveis até a próxima importação de estoque. |
| Formulário sem itens | erro | Limpeza: "Formulário de limpeza: nenhum item no catálogo; o formulário fica indisponível." AB: "Formulário AB: nenhum item no catálogo ({N} códigos com saída no SCPI; {N} também na lista de limpeza, que prevalece; {N} ocultos ou em grupo oculto); o formulário fica indisponível." |
| Formulário com itens | ok | Os textos atuais ("Formulário de limpeza: N itens." etc.) |

## Equipe (sem mudança de texto, exceto o corte da fração)

- "Entrega de {codigo} maior que a quantidade pedida." — igual.
- "Saída de {codigo} maior que o estoque ({N})." — {N} passa a ser o teto truncado a 3 casas.
- "Pedido AB: a quantidade de {codigo} deve ser inteira." — **removida**.
