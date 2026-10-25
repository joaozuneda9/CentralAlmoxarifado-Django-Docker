# Data Model: Consistência dos formulários públicos de pedido

Nenhuma tabela nova e nenhuma coluna nova. A única mudança de dados é uma carga na tabela `Opcao`
(com a atualização das `choices` da coluna `lista`). `Pedido`, `ItemPedido`, `Atendimento` e
`LinhaSaida` continuam como estão (FR-034, FR-041).

## Entidades persistidas

### Opcao (catalogo) — um valor novo de lista

| Campo | Observação |
|---|---|
| `lista` | Ganha o valor `UNIDADE_FRACIONAVEL` ("Unidades fracionáveis"); só `choices` muda |
| `valor` | A sigla da unidade como vem do cadastro do SCPI (ex.: `KG`) |
| `ordem`, `ativo` | Como nas demais listas |

- **Carga inicial** (migration de dados `0002_unidades_fracionaveis`): `M`, `MT`, `MTS`, `KM`, `KG`,
  `L`, `LT`, `M²`, `M³`, `T`, todas `ativo=True`, com `ordem` na sequência. É idempotente (usa
  `get_or_create` por `lista` + `valor`, respeitando a restrição de unicidade
  `opcao_unica_na_lista`) e não apaga nada na reversão.
- **Regra de leitura:** `Opcao.valores(Opcao.Lista.UNIDADE_FRACIONAVEL)` devolve só as ativas. Lista
  vazia significa que **nada** é fracionável (todo material aceita só inteiro).
- **Comparação:** pela forma normalizada (`norm_u`) dos dois lados.

### Material (catalogo) — sem mudança

`unidade` (até 20 caracteres, texto livre do SCPI) e `estoque` (até 4 casas) são a base da regra.

## Valores derivados (não persistidos)

### ItemCatalogo — um campo novo

| Campo | Tipo | Origem |
|---|---|---|
| `fracionavel` | `bool`, padrão `False` | `norm_u(Material.unidade)` está na lista de unidades fracionáveis |

- No AB, o `Material` é o do código **canônico** (depois do de/para); na limpeza, o do
  `ItemLimpeza`, e `unidade` (texto exibido) pode diferir da unidade que decide a regra.
- O campo `disponivel` (parte inteira do saldo) deixa de ser usado pelos formulários; sai quando
  nada mais o referenciar (candidato a remoção na tarefa de limpeza do código).

### Máximo pedível

`maximo_pedivel(estoque, fracionavel, regra)`:

| Regra do fluxo | Unidade | Máximo pedível |
|---|---|---|
| `por_unidade` (público) | fracionável | `truncar_qtd(estoque)` (3 casas, para baixo) |
| `por_unidade` (público) | contável ou sem unidade | `floor(estoque)` |
| `livre` (equipe) | qualquer | `truncar_qtd(estoque)` |

- O material cujo máximo pedível é 0 (ou menos) é bloqueado como "Sem estoque".
- É o mesmo número na lista ("Estoque N · UN"), no teto de adicionar e alterar, na validação do
  envio e no texto "Estoque disponível".

### Causas de erro de quantidade

Enumeração usada por `interpretar_quantidade` e pela tabela de textos
([contracts/mensagens.md](contracts/mensagens.md)):

| Causa | Quando |
|---|---|
| `ilegivel` | Vazio, texto, ponto decimal, mais de 3 casas ou negativo |
| `zero` | Quantidade igual a zero |
| `fracao_em_contavel` | Fração em material de unidade contável |
| `acima_do_maximo` | Acima de 999.999 |
| `acima_do_estoque` | Acima do máximo pedível |
| `ja_no_pedido` | O que já está no pedido consome o saldo (textos atuais, FR-014) |

### Estado de um formulário público

```text
                         ┌── saldo nunca importado ───────────────┐
catalogo_de(origem) ──►  ├── catálogo sem nenhum item ────────────┴─► INDISPONÍVEL (bloqueia; aviso de saúde)
                         └── há itens
                               ├── todos com máximo pedível 0 ───────► SEM ESTOQUE AGORA (abre, aviso no topo)
                               └── algum com máximo pedível > 0 ─────► NORMAL
```

- A situação é recalculada a cada abertura; não há estado gravado.
- `ItemSaude` (painel) acompanha: "sem itens" é `erro`; "saldo antigo" continua `aviso`.

### Fluxo (configuração, em código)

Campos descritos em [contracts/configuracao-fluxo.md](contracts/configuracao-fluxo.md). Não é
persistido: é a entrada de `FLUXOS` em `pedidos/fluxos.py`.

### Resposta do envio (`servicos.Resposta`) — sem mudança de forma

Continua com `ok`, `mensagem`, `erros`, `estoque_atual` (agora o máximo pedível), `numero`, `reenvio`,
`divergente`, `pedido`, `telegram`, `motivo`, `diferencas`.

## Validações (resumo)

| Onde | Regra |
|---|---|
| Adicionar e alterar (carrinho) | `interpretar_quantidade` + `maximo_pedivel`; soma o que já está no pedido; limite de 40 materiais |
| Envio (`validar_pedido`) | Nome e destino obrigatórios; destino no cadastro; ao menos um item; por código: ilegível, fora do catálogo, duplicado, sem estoque, acima do máximo; soma de linhas repetidas |
| Equipe (`validar_saida`, atendimento) | `livre`: fração em qualquer unidade; entrega não maior que a pedida; saída não maior que o teto da equipe |

## Compatibilidade com dados existentes

- Pedidos e itens gravados não mudam. `qtd_pedida` e `qtd_entregue` já são `Decimal(12,3)`.
- Um pedido antigo do AB com inteiros abre igual (o formatador tira zeros à direita).
- `ItemPedido.unidade` continua guardando o texto exibido no momento do pedido.
- Nenhuma conversão, nenhum recálculo e nenhuma reimportação são necessários.
