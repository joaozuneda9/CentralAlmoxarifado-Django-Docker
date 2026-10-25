# Contrato: textos novos

Só o que é novo. Quantidade, estoque, destino inválido, indisponibilidade, proteções, limites, tela
de sucesso, painel, detalhe e recibo usam os textos de hoje (specs 005 e 006).

## Formulário (página inicial e formulário)

| Onde | Texto |
|---|---|
| Cartão da página inicial | Oficina mecânica — Ex.: filtro, óleo, pneu, aditivo, lâmpada |
| Exemplo da busca | Ex.: filtro de óleo, pneu |
| Placeholder do destino | Oficina mecânica ou placa da viatura |

## Almoxarifado

| Onde | Texto |
|---|---|
| Origem (painel, filtro, detalhe, Telegram) | Oficina mecânica |
| Admin, Opções | lista "Grupos (oficina)" |
| Admin, materiais avulsos | "Materiais da oficina" (material) |

## Saúde do catálogo

| Situação | Nível | Texto |
|---|---|---|
| Disponível | ok | Formulário da oficina mecânica: N materiais. |
| Sem destino | erro | Formulário da oficina mecânica: nenhum destino (nem o centro OFICINA MECÂNICA nem centro com placa); o formulário fica indisponível. |
| Nada a oferecer | erro | Formulário da oficina mecânica: nenhum material nos grupos nem entre os materiais da oficina; o formulário fica indisponível. |
| Grupo sem material | aviso | Grupos da oficina sem material visível: nomes. |
| Avulsos ocultos | aviso | Materiais da oficina ocultos no SCPI (não aparecem): códigos. |
| Sem o centro OFICINA MECÂNICA, com viaturas | aviso | Formulário da oficina mecânica: centro OFICINA MECÂNICA não cadastrado; só as viaturas são oferecidas como destino. |

Os avisos de saúde só aparecem com o saldo já importado, como os da 006.
