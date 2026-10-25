# Contrato: o que muda em `FLUXOS` e nos catálogos

Usa o contrato da spec 005
([configuracao-fluxo.md](../../005-consistencia-formularios-publicos/contracts/configuracao-fluxo.md)) e os
das specs 006, 007 e 008. **Nenhum campo novo no `Fluxo`**; muda de onde vêm o catálogo e os centros.

## `Fluxo.catalogo`

Continua `Callable[[], list[ItemCatalogo] | None]` (`None` = indisponível). Cada `formulario_*` passa a
devolver a **base** da regra de origem **com as exceções aplicadas**:

| Formulário | Função | Base (regra de origem) |
|---|---|---|
| limpeza | `formulario_limpeza` | `catalogo_limpeza()` |
| AB | `formulario_ab` | `catalogo_ab().itens` |
| viaturas | `formulario_viaturas` | `catalogo_viaturas()` mais o AB sem repetir |
| oficina | `formulario_oficina` | `catalogo_oficina()` (**só os grupos**) |
| EPIs | `formulario_epis` | `catalogo_epis()` (**só os grupos**) |

`None` continua significando: saldo nunca importado (limpeza, AB, viaturas, oficina, EPIs) ou nenhum item
**depois** das exceções. O resto do núcleo (busca, carrinho, `validar_pedido`, `registrar_pedido`) não
muda.

## `Fluxo.centros`

Continua `Callable[[], list[Centro]] | None`. Agora **as cinco entradas públicas** o definem:

```python
centros = partial(centros_do_formulario, LIMPEZA)  # idem AB, VIATURAS, OFICINA, EPIS
```

A avulsa segue com `centros=None` (todos), porque não faz parte da configuração. As funções
`centros_equipe_manutencao` e `centros_oficina` saem (a regra delas foi transcrita para a tabela).

## Modo de destino (propriedade do formulário, em `catalogos.py`)

| Origem | Modo | Descrição |
|---|---|---|
| `LIMPEZA`, `AB`, `EPIS` | `padrao` | cada linha habilitada e ativa, com a placa; `opcoes_destino` gera "descrição" e "descrição — placa" |
| `VIATURAS` | `sem_placa` | uma por descrição (a primeira por código), sem placa |
| `OFICINA` | `oficina` | linha com placa vira `so_com_placa=True`; linha sem placa é o centro simples |

## Regras

1. O núcleo continua sem perguntar pelo nome nem pela origem do formulário; a única tabela por origem é o
   modo de destino, em `catalogos.py`.
2. Um formulário novo continua sendo uma entrada de `FLUXOS`, uma função de catálogo e um valor em
   `Pedido.Origem`; ganha também um valor em `Formulario` e uma entrada do modo de destino. A configuração
   por formulário passa a valer para ele sem mais código.
3. Centro inativo nunca sai de `centros_do_formulario`. `servicos.centros()` continua devolvendo todas as
   linhas (atendimento, edição, robô) e `servicos.centros_ativos()` serve só à saída avulsa nova.
