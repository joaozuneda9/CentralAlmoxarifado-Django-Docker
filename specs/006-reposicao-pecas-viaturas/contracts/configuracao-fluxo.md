# Contrato: o `Fluxo` de viaturas e os três campos opcionais novos

> **Nota (spec 009, 2026-10-23):** `centros` agora é definido nas cinco entradas públicas, como
> `partial(catalogos.centros_do_formulario, ORIGEM)`, que lê a configuração da página Formulários (a
> marca `equipe_manutencao` e os avulsos do formulário foram transcritos e saíram do admin). Veja
> [009 / configuracao-fluxo.md](../../009-configuracao-formularios/contracts/configuracao-fluxo.md).

Estende o contrato da spec 005
([configuracao-fluxo.md](../../005-consistencia-formularios-publicos/contracts/configuracao-fluxo.md)),
que continua valendo inteiro. Os campos novos são opcionais e, com o padrão, nada muda nos fluxos
existentes (`limpeza`, `ab`, `avulsa`).

## Campos novos

| Campo | Padrão | Significado |
|---|---|---|
| `folha` | `None` | Função sem argumentos que devolve os códigos da folha, na ordem. Com ela, o passo "Materiais" mostra o botão "Preencher a lista de peças" e o diálogo da folha ([folha.md](folha.md)). Os códigos fora do catálogo do fluxo são ignorados |
| `centros` | `None` | Função sem argumentos que devolve os `regras.Centro` aceitos como destino. `None`: todos os centros cadastrados (como hoje). Lista vazia: formulário indisponível (`sem_destinos`) |
| `pede_ocorrencia` | `False` | Mostra o campo opcional "Nº da ocorrência" no passo de dados, grava-o no pedido e o compara no reenvio |

## A entrada `viaturas`

| Campo | Valor |
|---|---|
| `nome` | `viaturas` (URL `/pedido/viaturas/`) |
| `origem` | `VIATURAS` |
| `titulo` | Reposição de peças das viaturas |
| `catalogo` | `catalogos.formulario_viaturas` (research R3) |
| `exemplo_busca` | Ex.: luva, tubo, registro |
| `exemplo_inicio` | Ex.: cotovelo, luva, tee, registro, tubo |
| `icone` | um ícone já existente em `_icone.html` (escolhido na implementação; nenhum ícone novo de fora) |
| `publico` | `True` |
| `regra_quantidade` | `por_unidade` (padrão) |
| `folha` | `catalogos.folha_viaturas` |
| `centros` | `catalogos.centros_equipe_manutencao` |
| `pede_ocorrencia` | `True` |

## Regras

1. O núcleo continua sem perguntar pelo nome ou pela origem do fluxo: lê `folha`, `centros` e
   `pede_ocorrencia` (regra 2 e 3 do contrato da 005).
2. `centros` vale só para o formulário público (a tela e `registrar_pedido`). Atendimento, edição e
   saída avulsa usam todos os centros (`servicos.centros()`).
3. Com `pede_ocorrencia` falso, um campo `ocorrencia` que chegue no POST é ignorado e o pedido grava "".
4. O rótulo do Telegram vem de `Pedido.get_origem_display()` (some o mapa fixo
   `telegram.FORMULARIOS`, que só conhecia limpeza e AB).
