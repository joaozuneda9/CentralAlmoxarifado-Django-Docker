# Contrato: interface pública dos formulários

O que muda e o que não muda para quem usa os formulários e para os testes que chamam as rotas.

## Rotas (sem mudança)

| Método | Rota | Resposta |
|---|---|---|
| GET | `/pedido/<fluxo>/` | Página do formulário (ou aviso de indisponível) |
| POST | `/pedido/<fluxo>/` | Sucesso, ou o formulário de volta com os erros; em HTMX só o trecho `#formulario` |
| GET | `/pedido/<fluxo>/materiais/` | Trecho `_resultados.html`, com `q` e `filtro` |
| POST | `/pedido/<fluxo>/carrinho/` | Trecho `_carrinho.html`, com `adicionar`, `alterar` ou `remover` |

`<fluxo>` é o nome de um formulário público de `FLUXOS` (`fluxos.fluxo_publico`): `limpeza` e `ab`
e, desde as specs 006 e 007, `viaturas` e `oficina`; nome desconhecido ou de fluxo não público dá 404. Os nomes das rotas
(`pedidos:formulario`, `pedidos:materiais`, `pedidos:carrinho`) não mudam. Os códigos HTTP também não:
recusas de negócio voltam com 200 (o `htmx-config` não troca 4xx/5xx).

## Campos do envio (sem mudança)

`token`, `confirmacao_extra` (isca), `solicitante`, `destino`, `obs`, e os pares repetidos
`item_codigo` / `item_qtd`. A quantidade continua enviada como texto pt-BR; o servidor interpreta.

## Contexto dos modelos de página

| Chave | Antes | Depois |
|---|---|---|
| `indisponivel` | `catalogo is None` (AB vazio abria o formulário) | `catalogo is None` para os dois; catálogo vazio vira `None` |
| `sem_estoque_agora` | não existia | `True` quando todos os itens têm máximo pedível 0; mostra o aviso no topo |
| `mensagem` (recusa) | `MENSAGEM_EXPIRADO`, `MENSAGEM_RECUSA` | `MENSAGEM_TOKEN_INVALIDO`, `MENSAGEM_RAPIDO`, `MENSAGEM_RECUSA` (só a isca) |
| `carrinho.linhas` na recusa | descartava linhas ilegíveis | mantém a linha com o texto digitado |
| `fluxo.*` | `inteiro`, `com_estoque`, `limita_estoque` | `regra_quantidade`, `exemplo_busca` e os demais campos de [configuracao-fluxo.md](configuracao-fluxo.md) |

## Trecho de resultados (`_resultados.html`)

- **Linha de estoque (formulário público):** `Estoque {N} · {UN}` (ou `Estoque {N}` sem unidade), com `{N}`
  igual ao máximo pedível. A frase "N UN disponíveis" some.
- **Linha da saída avulsa:** código, estoque, unidade e classe, como hoje, mas o estoque é o saldo
  truncado a 3 casas, sem zeros à direita (decisão do usuário, ver [research.md](../research.md)).
- **Quantidade:** `inputmode="decimal"` para todos (a regra é do servidor); o campo de quantidade
  continua começando em 1.

## Aviso de JavaScript

`<noscript>` no `formulario.html` com o texto de [mensagens.md](mensagens.md); o formulário fica
escondido enquanto o `<html>` não tiver a classe `js`.

## O que não muda

- Cabeçalho do pedido, token assinado, isca e tempo mínimo de 5 segundos.
- Limites por IP, por nome, por itens (40) e por tamanho de texto (200 caracteres).
- Numeração (`P-`, `AV-`), gravação, Telegram em `on_commit`, recibo e painel.
- A área do almoxarifado (atendimento, saída avulsa, edição), exceto as regras de quantidade e os
  formatadores descritos em [research.md](../research.md) (R8 e R9).
