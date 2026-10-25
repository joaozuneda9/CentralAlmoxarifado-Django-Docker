# Modelo de dados: Configuração das opções por formulário

Aplicação `catalogo`. Duas migrations aditivas (`0006_configuracao_formularios`, o esquema, e `0007_transcrever_configuracao`, a
carga dos dados), sem alterar nem apagar
coluna existente.

## `Formulario` (TextChoices, sem tabela)

`LIMPEZA`, `AB`, `VIATURAS`, `OFICINA`, `EPIS`: os valores de `Pedido.Origem` correspondentes. `AVULSA` não
entra.

## `CentroCusto` (existente) + `ativo`

| Campo | Tipo | Observação |
|---|---|---|
| `ativo` | booleano, padrão `True` | Estado global (FR-008). Inativo: não é oferecido nem aceito em pedido novo dos formulários públicos nem na saída avulsa nova; atendimento, edição e robô seguem resolvendo. |
| `equipe_manutencao` | existente | **Deixa de valer** e sai do admin; o dado fica (R6). |

## `CentroFormulario` (novo)

A presença da linha diz: "esta linha do cadastro de centros é destino neste formulário".

| Campo | Tipo | Regras |
|---|---|---|
| `centro` | FK `CentroCusto`, `CASCADE`, `related_name="formularios"` | A linha (centro mais placa). Apagar o centro no admin leva as associações, que só têm sentido com ele. |
| `formulario` | texto, `choices=Formulario` | |
| `alterado_por` | FK usuário, `SET_NULL`, nula | Quem alterou por último (FR-031). |
| `alterado_em` | data e hora, `auto_now` | |

- **Única** por (`centro`, `formulario`) (`centro_unico_no_formulario`).
- Ordenação: `centro__descricao`, `centro__placa`.
- Sem linha = não é destino. Linha com o centro **inativo** = guardada e sem efeito (reativar a restaura).

## `ExcecaoMaterial` (novo)

Uma decisão do administrador sobre um material num formulário, sobre a regra de origem.

| Campo | Tipo | Regras |
|---|---|---|
| `material` | FK `Material`, `PROTECT`, `related_name="excecoes_formulario"` | O catálogo continua sendo o único cadastro; o material não pode ser apagado enquanto houver exceção (o importador nunca apaga, só oculta). |
| `formulario` | texto, `choices=Formulario` | |
| `habilitado` | booleano | `True` acrescenta o material ao formulário; `False` o retira. |
| `alterado_por` | FK usuário, `SET_NULL`, nula | |
| `alterado_em` | data e hora, `auto_now` | |

- **Única** por (`material`, `formulario`) (`excecao_unica_no_material_e_formulario`).
- Índice por `formulario` (a consulta do catálogo filtra por ele).
- Sem linha = vale a regra de origem. **Restaurar** = apagar a linha.
- Ordenação: `material__nome`.

## Estado efetivo (calculado, não guardado)

Função pura em `catalogo/disponibilidade.py`:

```
estado(oculto: bool, na_regra: bool, excecao: bool | None) -> Estado

Estado.disponivel : bool
Estado.origem     : "regra" | "acrescentado" | "retirado" | "fora"
Estado.sem_efeito : bool    # exceção que não muda nada: retirar o que a regra não traz,
                            # acrescentar o que a regra já traz
```

| `oculto` | `na_regra` | `excecao` | `disponivel` | `origem` | `sem_efeito` |
|---|---|---|---|---|---|
| sim | qualquer | qualquer | não | (a que seria) | (o que seria) |
| não | sim | nenhuma | sim | `regra` | não |
| não | sim | retira | não | `retirado` | não |
| não | sim | acrescenta | sim | `regra` | **sim** |
| não | não | nenhuma | não | `fora` | não |
| não | não | acrescenta | sim | `acrescentado` | não |
| não | não | retira | não | `fora` | **sim** |

`oculto` e `duplicado` são do cadastro e valem em todos os formulários (FR-018, FR-019); `duplicado` não
muda `disponivel` (aparece bloqueado).

## Regra de origem (existente, comentada)

| Formulário | Regra de origem | Mudança nesta feature |
|---|---|---|
| limpeza | `ItemLimpeza` com material visível | nenhuma |
| AB | curva ABC, menos grupos ocultos e itens da limpeza | nenhuma |
| viaturas | `PecaViatura` mais o AB sem repetir | nenhuma |
| oficina | grupos de `GRUPO_OFICINA` | **só os grupos** (o avulso vira exceção) |
| EPIs | grupos de `GRUPO_EPI` | **só os grupos** (o avulso vira exceção) |

## Transcrição inicial (migration de dados)

| De | Para |
|---|---|
| todas as linhas de `CentroCusto` | `CentroFormulario` em `LIMPEZA`, `AB`, `EPIS` |
| linhas com `equipe_manutencao=True` | `CentroFormulario` em `VIATURAS` |
| a linha sem placa de "OFICINA MECÂNICA" (a primeira por código) e toda linha com placa | `CentroFormulario` em `OFICINA` |
| `MaterialOficina` | `ExcecaoMaterial(OFICINA, habilitado=True)` |
| `MaterialEpi` | `ExcecaoMaterial(EPIS, habilitado=True)` |

Reversão: a carga (`0007`) **não apaga nada** (as tabelas guardam também as escolhas do administrador,
que ela não saberia distinguir); desfazer o esquema (`0006`) remove as tabelas e `ativo`. Os cadastros
antigos nunca foram tocados. A carga é atômica e só roda com as tabelas vazias: com configuração já feita, é do administrador e a
carga não recoloca nada.

## Relações e o que NÃO muda

- `Pedido`, `ItemPedido`, `Atendimento`, `LinhaSaida`, `AutorizacaoPedido`: **nenhuma coluna nova**;
  destino e centro continuam texto, e o item continua com o retrato do material.
- `Material`, `SaidaSCPI`, `ParDePara`, `Opcao`, `ItemLimpeza`, `PecaViatura`: sem mudança.
- Não há chave estrangeira de pedido para a configuração: a configuração pode mudar sem alcançar o
  histórico (FR-033).
