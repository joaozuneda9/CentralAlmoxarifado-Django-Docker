# Data Model: Formulário da oficina mecânica

## Modelos (banco)

### `catalogo.MaterialOficina` (novo)

Material avulso da escolha da oficina (FR-012a).

| Campo | Tipo | Regras |
|---|---|---|
| `material` | `OneToOneField(Material, on_delete=PROTECT, related_name="material_oficina")` | um material no máximo uma vez; não se apaga material em uso |

`Meta.ordering = ["material__nome"]`; `verbose_name` "material da oficina". Material oculto continua
na tabela e só deixa de aparecer no formulário (a saúde avisa).

### `catalogo.Opcao` (alterado)

`Lista.GRUPO_OFICINA = "GRUPO_OFICINA", "Grupos (oficina)"`: cada `valor` é um nome de grupo do
cadastro do SCPI, comparado por `_grupo` (sem acento, maiúsculas, sem espaços). Só a lista de
`choices` muda.

### `pedidos.Pedido` (alterado)

`Origem.OFICINA = regras.OFICINA, "Oficina mecânica"`. Só os `choices` mudam; nenhum campo novo. O
destino continua em `Pedido.destino`: `OFICINA MECÂNICA` ou `"<descrição> — <placa>"`.

### `catalogo.CentroCusto` (sem mudança)

Fonte dos destinos: as linhas sem placa com descrição normalizada `OFICINA MECÂNICA` e todas as
linhas com placa.

## Estruturas puras

### `regras.Centro` (alterado)

| Campo | Padrão | Significado |
|---|---|---|
| `descricao`, `codigo`, `placa` | — | como hoje |
| `so_com_placa` | `False` | o centro é oferecido só como "centro — placa"; a descrição sozinha não é destino |

`opcoes_destino(centros)`: as descrições dos centros com alguma linha `so_com_placa=False`, depois
"descrição — placa" de cada linha com placa. Com todos `False` (o padrão), o resultado é o de hoje.

### `regras.CENTRO_OFICINA` (nova constante)

`"OFICINA MECÂNICA"`, usada por `resolver_centro_custo` (que já tinha o texto) e por
`catalogos.centros_oficina`.

## Funções de catálogo (`catalogo/catalogos.py`)

| Função | Devolve |
|---|---|
| `grupos_oficina()` | os valores de `GRUPO_OFICINA` normalizados por `_grupo` |
| `catalogo_oficina()` | `list[ItemCatalogo]` dos materiais não ocultos da escolha, uma vez cada, pelo nome |
| `formulario_oficina()` | o catálogo, ou `None` sem saldo importado ou sem item |
| `centros_oficina()` | `[Centro(OFICINA MECÂNICA)]` (se cadastrado, sem placa) + um `Centro(..., so_com_placa=True)` por linha com placa |

## Estados

Nenhum estado novo. O pedido da oficina percorre os estados de todo pedido público (pendente →
atendido; linhas de saída `PENDENTE` → lançadas pelo robô).
