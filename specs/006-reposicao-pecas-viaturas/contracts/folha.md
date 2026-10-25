# Contrato: a folha (lista de peças em diálogo)

Interface do diálogo que reproduz o quadro "Materiais" da folha em papel (FR-003, research R4).
Existe em qualquer fluxo com `Fluxo.folha`; hoje, só em `viaturas`.

## Na página do formulário

- No passo "Materiais", antes da busca: botão `button.botao-primario` "Preencher a lista de peças"
  (`data-folha-abrir`), com a dica "N peças, como na folha de papel". Sem JavaScript o formulário
  inteiro já fica escondido (spec 005), então não há caminho sem JavaScript a manter.
- O diálogo é um `<dialog id="folha" aria-labelledby="folha-titulo">`: tela cheia em largura de
  celular; painel centrado e rolável no computador. Título "Lista de peças"; texto de apoio
  "Preencha só as peças que precisa repor. As que ficarem em branco não entram no pedido."

## Abrir

`hx-post` ao endpoint do carrinho do fluxo (`pedidos:carrinho`, o mesmo de hoje) com os campos do
carrinho atual (`item_codigo`/`item_qtd`) e `folha_abrir=1`. Resposta: `_folha.html`, com uma linha por
código de `Fluxo.folha()` que está no catálogo, na ordem:

| Coluna | Conteúdo |
|---|---|
| Material | nome (exibido) e, abaixo, "Estoque N · UN" (o mesmo texto da busca) |
| Quantidade | `input` (`name="folha-<código>"`, `inputmode="decimal"` se fracionável, senão `numeric`), já com a quantidade que a peça tem no pedido; rótulo acessível com o nome da peça |
| Bloqueada | no lugar do campo, o motivo ("Sem estoque", "Cadastro duplicado — avise o almoxarifado"), em texto |

O foco vai para o primeiro campo. Esc ou "Fechar" fecha sem mudar nada e devolve o foco ao botão.

## Pôr no pedido

`hx-post` ao mesmo endpoint com os campos do carrinho, todos os `folha-<código>` e `folha=1`.
O servidor (`carrinho.aplicar_folha`) aplica **tudo ou nada**:

| Linha | Efeito |
|---|---|
| vazia ou "0" | a peça sai do pedido, se estava |
| quantidade válida | a peça fica no pedido com essa quantidade (substitui) |
| código fora da folha ou do catálogo | ignorado |

- Sem erro: resposta é o `_carrinho.html` atualizado (mesmo alvo de hoje) e um evento HTMX
  (`folha-aplicada`) que fecha o diálogo, devolve o foco ao botão e anuncia no `role="status"` do
  carrinho "Lista posta no pedido: N materiais."
- Com erro: resposta é o `_folha.html`, posta no conteúdo do diálogo pelos cabeçalhos
  `HX-Retarget` e `HX-Reswap` (lidos pelo HTMX 4.0.0 vendorizado), com os valores digitados, o erro embaixo de cada linha
  (`aria-describedby`, `aria-invalid`), um resumo no topo ("Corrija N linhas para pôr no pedido.") e o
  foco no resumo; o carrinho não muda. Os textos de erro são os de sempre:
  `texto_erro_quantidade` (quantidade ilegível, fração em unidade contada, acima de 999.999),
  `texto_acima_do_estoque` e "O pedido pode ter no máximo 40 materiais." (`PEDIDOS_MAX_ITENS`).

## Ids dos campos

Os `id`s dos campos (`folha-<desenho>-<n>`) mudam a cada desenho da folha. Com o mesmo `id`, o
"settle" do HTMX 4 copiava para o campo novo o valor do campo antigo que tinha o foco, por cima do
valor devolvido pelo servidor (achado na conferência no navegador, 2026-10-22).

## Relação com o resto

- O carrinho continua sendo o único estado do pedido; o envio final revalida tudo
  (`regras.validar_pedido`), como em qualquer formulário público.
- Uma peça da folha posta no pedido pela busca aparece preenchida na próxima abertura da folha; uma
  peça removida no carrinho aparece em branco.
- A confirmação ao sair da página (`beforeunload`) continua valendo para o pedido com materiais.
