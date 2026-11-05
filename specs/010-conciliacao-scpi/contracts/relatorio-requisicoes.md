# Contrato: CSV da "Relação de Requisições" sem filtro

Este contrato descreve o que `scpi.leitura.ler_requisicoes` exige e lê do relatório. A referência é o
CSV real extraído pelo usuário de 23/10 a 04/11/2026: 240 linhas, 84 requisições e 65 colunas. Esse
CSV não fica no repositório.

## Origem

SCPI › Relatórios › Requisições › Relação de Requisições, rádio "Requisições de Saída", datas De/Até,
**sem escolher o tipo**. O período filtra pela coluna `DTPAG`.

## Formato

- UTF-8 com BOM, separador `;`, fim de linha CRLF e LF misturados, sem aspas.
- Um registro pode vir quebrado em várias linhas físicas. Ele é recolado pelo número de campos, como
  em `normalizadores.py`.
- Também se aceita o mesmo relatório salvo por uma planilha (cabeçalho com `,`), como em `ler_saidas`.
- Uma linha por item. O cabeçalho da requisição se repete em cada linha.

## Colunas lidas

| Coluna | Obrigatória | Uso |
|---|---|---|
| `REQUI` | sim | número visível, `NNNNNN/AA`; agrupa as linhas da requisição |
| `ID_REQUI` | sim | identificador interno (só registro) |
| `DTLAN` | sim | data da requisição, comparada com a data do lote |
| `DTPAG` | sim | data pela qual o período filtra |
| `TPREQUI` | sim | tipo: "BALCÃO", "OUTRA" ou vazio |
| `CODCCUSTO` | sim | código do centro, sem zeros à esquerda |
| `CCUSTO` | não | nome atual do centro no SCPI (só nota) |
| `RECEBE` | sim | recebedor |
| `PLACA` | não | placa (o SCPI preenche a partir do centro de uma viatura) |
| `OBS_CABECALHO` | sim | campo Observações; leva "Central Almoxarifado <lote>" |
| `CADPRO` | sim | código do material, comparado por `norm_u` e sem de/para (FR-019b) |
| `QUAN2` | sim | quantidade, `decimal_br` |
| `UNID1` | não | unidade (só exibição) |
| `ENTR` | não | "S" nos ajustes e transferências |
| `RESPONSA` | não | usuário do SCPI (só exibição) |

As demais colunas ficam só no arquivo bruto.

## Relatório vazio

Sem nenhuma requisição no período, o SCPI só avisa "Nada a exibir", sem gerar o CSV.
`baixar_requisicoes` levanta `NadaAExibir` (um `ErroImportacao` de `scpi.leitura`) nesse caso, e
`conciliacao.extracao.extrair` captura essa exceção e passa a decisão a `_vazio`. Só esse aviso faz
o vazio valer: um download ou um `--arquivo` com bytes vazios, sem ele, faz a extração falhar ("o
arquivo veio vazio"), e o `_relacao_de_requisicoes` recusa o CSV vazio entregue pelo SCPI. `_vazio`
decide:
- num período sem nenhum lote lançado, vale como extração sem requisições, e o piso fica vazio;
- num período com lote lançado, o relatório não pode estar vazio, e a extração falha (FR-005).

Sem isso, um período sem movimento travaria o robô para sempre na extração de antes.

## Regras de leitura

1. Falta uma coluna obrigatória: `ErroImportacao` com o nome dela.
2. Nenhum registro: `ErroImportacao`. A extração falha (FR-005).
3. `REQUI` fora do formato: `ErroImportacao` com a linha. Nenhuma `RequisicaoOficial` é gravada; a
   `ExtracaoOficial` fica registrada, sem requisições e com `maior_requisicao` nulo, e a `Importacao`
   termina `FALHA` com o motivo. Vale para todo `ErroImportacao` desta lista.
4. Relatório cortado: depois da recolagem, um registro (em geral o último) fica com **menos campos
   que o cabeçalho**. A detecção é só por essa contagem. A quebra de linha no fim do arquivo é
   opcional: um CSV válido pode terminar sem ela, e a falta dela sozinha nunca é erro. É
   `ErroImportacao` com a posição (o número do registro depois do cabeçalho), e vale a regra 3.
5. Um campo de cabeçalho que varia entre as linhas da mesma requisição: `ErroImportacao`. No CSV real,
   isso nunca acontece.
6. Quantidade ilegível: `ErroImportacao`. Quantidade 0 é aceita, porque aparece nos ajustes de
   inventário.
7. O mesmo código repetido numa requisição é aceito e lido como duas linhas. A comparação conta as
   linhas.
8. Uma requisição com `DTPAG` fora do período da extração (um CSV de outro período no
   `--arquivo`, ou o SCPI deixando de filtrar por `DTPAG`) faz a extração inteira falhar, pela regra
   3: a extração só guarda o que o seu período promete.
9. Quantidade que não cabe exata em `ItemOficial.quantidade` (10 dígitos inteiros e 4 casas) é
   erro, como a ilegível: o banco a arredondaria em silêncio.

## Fixture de teste

`tests/relacao_requisicoes.py` gera bytes neste formato a partir de requisições simuladas. Os dados
são sintéticos, sem nomes de pessoas. O gerador usa o cabeçalho real de 65 colunas, BOM, CRLF e ao
menos um registro quebrado em duas linhas.
