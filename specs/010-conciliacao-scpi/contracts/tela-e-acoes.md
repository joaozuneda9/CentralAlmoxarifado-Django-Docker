# Contrato: tela, ações e permissões

Tudo fica na aba **Lançamento no SCPI** de Automações (`automacoes:pagina?aba=lancamento`, parcial
`pedidos/_lancamentos.html`). Nenhuma rota pública nova. As rotas novas ficam fora de
`contas.acesso.ROTAS_SEGURANCA_TRABALHO`, então a Segurança do Trabalho continua negada pelo middleware
(FR-030).

## O que a aba mostra (PR 5)

| Onde | O quê |
|---|---|
| Lotes lançados | o veredito atual como selo com texto; a requisição ligada (mono); a origem do vínculo; as diferenças nomeadas ("Tipo: esperado BALCÃO, no SCPI vazio"); as notas; "alterado no SCPI depois do lançamento" quando houver; filtro por veredito, com "Divergências" como padrão |
| Lotes em verificar | dentro do painel de resolução que já existe: a extração usada (quando), o intervalo, as candidatas na ordem (requisição, data, tipo, centro, itens), com "é esta" destacado em texto; ou "Nenhuma requisição no intervalo"; ou "Sem extração depois da tentativa" |
| Cabeçalho da aba | a última extração (quando, situação, quantas requisições) e o botão **Conferir agora** |

## Ações

| Ação | Rota | Método | Quem | Regra |
|---|---|---|---|---|
| Conferir agora | `automacoes:conferir` (nova, PR 5) | POST com CSRF | usuário do almoxarifado | dispara `conciliar_lancamentos`; recusada com lançamento ou importação em andamento; volta para a aba |
| Liberar para relançar | `automacoes:resolver` (existe) | POST | como hoje | passa a exigir a conferência de R17 (PR 3); a recusa explica o motivo e lista as candidatas |
| É esta | `automacoes:resolver`, `acao=lancada` (existe) | POST | como hoje | manda o número da candidata (FR-025) |
| Corrigir número | `automacoes:corrigir` (nova, PR 5) | POST com CSRF | usuário do almoxarifado | só lote lançado com veredito Não encontrado ou Vínculo em conflito; `servicos.corrigir_requisicao` (R16); no conflito, a pessoa escolhe uma das duas requisições; no não encontrado, digita o número |

Todas as ações respondem com mensagem e redirecionamento à aba, como as de hoje. Sem JavaScript,
funcionam por formulário comum.

## Avisos de saúde (PR 5, FR-028)

Linhas novas na lista curta do painel e na visão geral de Automações (`conciliacao/saude.py`, chamado
pelo `catalogo.saude._demais`). Na interface, a saída do Central se chama "requisição", nunca "lote"
(`tests/test_pagina_lancamentos.py`):

- "N requisições lançadas com divergência no SCPI: <números>." (Divergente, Duplicado, Vínculo em
  conflito)
- "N requisições lançadas não encontradas no SCPI: <números>."
- "N requisições aguardando conferência há mais de um dia útil: <números>." (vence no mesmo horário,
  no fuso local, do dia útil seguinte ao lançamento ou à correção do número: Sábado e Domingo não
  contam, e o lançado na sexta às 15h só vence na segunda às 15h)
- "Requisições do SCPI: a última extração falhou em <quando>: <motivo resumido>"

## Mensagens de recusa (textos)

- Liberar sem extração: "Ainda não há uma extração do SCPI feita depois desta tentativa. Use
  “Conferir agora” e tente de novo."
- Liberar com candidata: "Há N requisições no SCPI que podem ser esta: <números>. Confira e informe o
  número, ou marque para não lançar."
- Liberar sem tentativa registrada: "Esta requisição não tem a tentativa registrada; não dá para provar
  que o SCPI não a salvou. Informe o número ou marque para não lançar."
- Corrigir com número de outro lote: "A requisição <n> do SCPI já está em <lote>."
- Corrigir fora de Não encontrado ou Vínculo em conflito: "Só a requisição lançada com o veredito Não
  encontrado ou Vínculo em conflito tem o número corrigido."
- Corrigir o conflito com um número que não é nenhum dos dois: "No vínculo em conflito, escolha uma das
  requisições apontadas: <números>."
