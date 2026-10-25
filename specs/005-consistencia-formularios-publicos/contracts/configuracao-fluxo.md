# Contrato: o que um formulário informa (`Fluxo`)

> **Nota (spec 009, 2026-10-23):** `centros` agora é definido nas cinco entradas públicas, como
> `partial(catalogos.centros_do_formulario, ORIGEM)`, que lê a configuração da página Formulários (a
> marca `equipe_manutencao` e os avulsos do formulário foram transcritos e saíram do admin). Veja
> [009 / configuracao-fluxo.md](../../009-configuracao-formularios/contracts/configuracao-fluxo.md).

Cada formulário, atual ou novo, é uma entrada de `FLUXOS` em `pedidos/fluxos.py`. O núcleo
(busca, carrinho, envio, proteções, recibo, atendimento) lê só isto. Criar um formulário novo exige
**esta entrada, uma função de catálogo e (fora desta funcionalidade) um valor novo em
`Pedido.Origem`**, sem alterar o núcleo (FR-041, SC-007; provado por `tests/test_fluxo_configuravel.py`).

| Campo | Obrigatório | Significado | limpeza | AB | avulsa |
|---|---|---|---|---|---|
| `nome` | sim | Parte da URL (`/pedido/<nome>/`) e do nome das rotas | `limpeza` | `ab` | `avulsa` |
| `origem` | sim | Valor gravado em `Pedido.origem` | `LIMPEZA` | `AB` | `AVULSA` |
| `titulo` | sim | Nome mostrado ao funcionário | Limpeza, copa e escritório | Ferramentas, peças e materiais | Saída avulsa |
| `catalogo` | sim | Função sem argumentos: devolve a lista de `ItemCatalogo` ou `None` (indisponível). Nunca devolve lista vazia | `formulario_limpeza` | `formulario_ab` | `formulario_avulsa` |
| `exemplo_busca` | sim | Texto do exemplo no campo de busca | Ex.: detergente, café | Ex.: luva, fita veda rosca | Ex.: luva, fita veda rosca, 016.005.010 |
| `exemplo_inicio` | não | Exemplo no cartão da página inicial | Ex.: café, copo descartável, água sanitária, caneta | Ex.: luva, botina, fita veda-rosca, cimento | — |
| `icone` | não (`caixa`) | Ícone do cartão da página inicial | `caixa` | `catalogo` | — |
| `publico` | não (`True`) | Sem login e com proteções, ou área do almoxarifado | sim | sim | não |
| `regra_quantidade` | não (`por_unidade`) | `por_unidade` (fração só em unidade fracionável) ou `livre` | `por_unidade` | `por_unidade` | `livre` |
| rótulos do carrinho e do envio | derivados de `publico` | "Seu pedido / Revisar e enviar / Enviar pedido" ou "Materiais da saída / Revisar e registrar / Registrar saída" | derivados | derivados | derivados |

## Regras de contrato

1. **Catálogo.** Devolve `None` quando o formulário está indisponível (saldo nunca importado ou
   nenhum item); devolve lista não vazia caso contrário. As funções `formulario_*` ficam em
   `catalogo/catalogos.py`, e `servicos.catalogo_de(origem)` apenas consulta o `Fluxo` da origem.
2. **Regra de quantidade.** O núcleo nunca pergunta pelo nome nem pela origem do formulário; só por
   `regra_quantidade` e por `publico`. A mesma regra vale no carrinho e na validação do envio
   (`regras.aceita_fracao`, `validar_pedido(..., regra_quantidade)`): um formulário público com a
   regra `livre` aceita fração em qualquer unidade nos dois (`tests/test_fluxo_configuravel.py`).
3. **Texto.** Nenhum modelo de página escolhe texto por `fluxo.nome`; o que muda por formulário
   (título, exemplos, ícone, rótulos) está nesta entrada.
4. **Cabeçalho.** Solicitante, destino (centro de custo cadastrado) e observação; igual para todos.
5. **Lançamento.** O lançamento no SCPI não depende do formulário; só o centro de custo, que vem do
   destino, muda.
6. **Origem pública.** Toda origem diferente de `AVULSA` é pública (`regras.origem_publica`), sujeita
   ao limite por nome e à conferência de reenvio, e numerada `P-` (a avulsa, `AV-`).

## Fora desta funcionalidade

Criar a origem nova (migration de `choices` em `Pedido.Origem`), os destinos aceitos de cada
formulário futuro e um limite próprio de quantidade (por exemplo, o estoque-padrão de um kit) são
tratados na especificação de cada formulário novo. Hoje o limite de todos é `maximo_pedivel`.

## Campos acrescentados depois

A spec 006 acrescentou três campos opcionais, com padrão neutro: `folha`, `centros` e
`pede_ocorrencia` ([contrato](../../006-reposicao-pecas-viaturas/contracts/configuracao-fluxo.md)).
