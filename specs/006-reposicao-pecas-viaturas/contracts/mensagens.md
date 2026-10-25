# Contrato: textos novos

Só o que é novo. Os textos de quantidade, estoque, destino, indisponibilidade, proteções e limites
são os da spec 005 e não mudam.

## Formulário (encarregado)

| Onde | Texto |
|---|---|
| Rótulo do campo | Nº da ocorrência (opcional) |
| Dica do campo | Se as peças foram usadas numa ocorrência, o número dela. |
| Erro do campo | Nº da ocorrência: no máximo 20 caracteres. |
| Botão da folha | Preencher a lista de peças |
| Dica do botão | N peças, como na folha de papel |
| Título do diálogo | Lista de peças |
| Apoio do diálogo | Preencha só as peças que precisa repor. As que ficarem em branco não entram no pedido. |
| Ação do diálogo | Pôr no pedido |
| Fechar o diálogo | Fechar |
| Resumo de erros da folha | Corrija 1 linha para pôr no pedido. / Corrija N linhas para pôr no pedido. |
| Anúncio depois de aplicar | Lista posta no pedido: N materiais. |
| Tela de sucesso | Nº da ocorrência: o valor (só quando preenchido) |

## Almoxarifado

| Onde | Texto |
|---|---|
| Detalhe do pedido e recibo | Nº da ocorrência — o valor (só quando preenchido) |
| Lista do painel | "Ocorrência" e o valor, na linha do pedido (só quando preenchido) |
| Dica da busca do painel | Nº, solicitante, recebedor ou ocorrência |
| Admin, lista de centros de custo | coluna e filtro "Equipe de manutenção" |
| Admin, lista de peças | "Peças das viaturas" (nome exibido, material, ordem) |

## Saúde do catálogo

| Situação | Nível | Texto |
|---|---|---|
| Formulário disponível | ok | Formulário de reposição de peças das viaturas: N peças na lista e M materiais do AB. |
| Nenhum centro marcado | erro | Formulário de reposição de peças das viaturas: nenhum centro de custo marcado como de equipe de manutenção; o formulário fica indisponível. |
| Nada a oferecer | erro | Formulário de reposição de peças das viaturas: nenhuma peça na lista nem material no AB; o formulário fica indisponível. |
| Peças da lista ocultas | aviso | Peças das viaturas ocultas no SCPI (não aparecem): códigos. |
| Sem saldo importado (texto existente, generalizado) | erro | Sem saldo importado: os formulários públicos ficam indisponíveis até a próxima importação de estoque. |
