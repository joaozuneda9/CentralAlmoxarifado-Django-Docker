# Modelo de dados: conciliação com o SCPI

Os modelos novos ficam todos no app `conciliacao` ([research R1](research.md#r1-onde-ficam-os-modelos-novos)).
Do que já existe, só muda o `choices` de `catalogo.Importacao.Tipo`. A `LinhaSaida`, a `SaidaSCPI` e a
`ExecucaoRobo` continuam como estão (FR-006, FR-021).

As migrations são aditivas e novas: `catalogo/0008_importacao_requisicoes` (choices) e
as de `conciliacao` a partir da `0001`, nos PRs que mudam modelo (o PR 1 tem a `0001` e a `0002`, a trava de `ANTES`/`DEPOIS` sem execução) ([plano](plan.md#entrega-em-prs-empilhados)).

```text
ExecucaoRobo (pedidos) 1 ──< TentativaLancamento >── lote (texto; LinhaSaida.lote)
        │ 0..1
        └──< ExtracaoOficial >──1 Importacao (catalogo, tipo REQUISICOES)
                   │
                   ├──< RequisicaoOficial ──< ItemOficial
                   │
                   └──< ConferenciaLote >── RequisicaoOficial (ligada, 0..1)
                              └──< Candidata >── RequisicaoOficial
CorrecaoVinculo >── lote; ── ConferenciaLote (de origem)
```

## `catalogo.Importacao.Tipo` (muda)

Ganha o valor `REQUISICOES = "REQUISICOES", "Requisições do SCPI"`. O histórico de Automações e a trava
por tipo (`trava_importacao`) passam a valer para a extração sem nenhuma outra mudança.

## `ExtracaoOficial` (PR 1)

É uma extração da "Relação de Requisições" sem filtro.

| Campo | Tipo | Regra |
|---|---|---|
| `importacao` | OneToOne → `Importacao` | situação, início, fim, erro e período vêm daqui |
| `motivo` | choices `ANTES`, `DEPOIS`, `DIARIA`, `MANUAL`, `ARQUIVO` | `ANTES` e `DEPOIS` exigem `execucao`; `ARQUIVO` (um CSV já baixado, sem data de exportação conhecida) nunca confere lote em verificar nem revisa veredito |
| `execucao` | FK → `pedidos.ExecucaoRobo`, nula, `PROTECT` | a execução real que a pediu |
| `impressao` | char(64) | SHA-256 dos bytes recebidos |
| `arquivo` | `BinaryField`, nulo | gzip do bruto; vazio se igual ao anterior ou depois de 60 dias |
| `mesmo_arquivo_que` | FK → self, nula | a extração que guarda o mesmo bruto |
| `arquivo_apagado_em` | datetime, nulo | marcado pela limpeza (FR-004); vale também para as extrações que apontam para esta |
| `maior_requisicao` | char(9), nulo | o maior `REQUI` lido, pela chave (ano, número); o piso no `ANTES`; `NULL` em toda extração que não terminou `SUCESSO` |
| `requisicoes` | int | quantas requisições o relatório trouxe |

**Validação**:
- uma extração só conta para veredito ou liberação se a `Importacao` terminou `SUCESSO`;
- extração vazia, cortada ou sem coluna obrigatória é `FALHA` (FR-005);
- a leitura é tudo ou nada: numa falha, nenhuma `RequisicaoOficial` é gravada e `maior_requisicao`
  fica `NULL`, mesmo que parte do arquivo tenha sido lida. Uma extração com falha nunca dá piso, nunca
  conta para "Não encontrado" e nunca libera um lote em verificar;
- um índice em (`motivo`, `execucao`).

**Retenção do bruto**: a limpeza só esvazia o `arquivo` de uma extração quando ela **e todas as que
apontam para ela** (`mesmo_arquivo_que`) têm mais de 60 dias. Uma extração repetida recente segura o
bruto da origem até ela mesma passar dos 60 dias. A deduplicação só aponta para uma extração que
**ainda tem os bytes**; se a única com a mesma impressão já teve o bruto apagado, a extração nova
guarda o seu e passa a ser a origem.

## `RequisicaoOficial` e `ItemOficial` (PR 1)

São uma requisição como o relatório a trouxe numa extração. É uma foto: a mesma requisição aparece de
novo em cada extração que a cobre.

| Campo | Tipo | Coluna |
|---|---|---|
| `extracao` | FK → `ExtracaoOficial`, `CASCADE` | — |
| `requisicao` | char(9) | `REQUI` (`003588/26`) |
| `ano`, `numero` | small int, int | derivados de `REQUI` (chave de ordem, R6) |
| `id_requi` | int | `ID_REQUI` |
| `data` | date | `DTLAN` |
| `data_filtro` | date, nula | `DTPAG` |
| `tipo` | char | `TPREQUI` |
| `cod_ccusto` | char | `CODCCUSTO` |
| `centro_nome` | char | `CCUSTO` |
| `recebedor` | char | `RECEBE` |
| `observacoes` | text | `OBS_CABECALHO` |
| `lote_observado` | char(12), indexado | o lote achado nas observações (R5), ou vazio |
| `responsavel` | char | `RESPONSA` (só exibição, não prova autoria) |
| `entrada` | bool | `ENTR == "S"` (ajustes e transferências) |

`ItemOficial` tem `requisicao` (FK, `CASCADE`), `ordem`, `codigo` (`CADPRO`), `quantidade` (`Decimal`
com 4 casas, de `QUAN2`), `unidade` (`UNID1`) e `placa` (`PLACA`). A placa fica no item, como no
formulário do SCPI e na `LinhaSaida`: numa requisição, cada item pode ter a sua.

**Unicidade**: (`extracao`, `ano`, `numero`).

**Retenção (FR-004)**: a limpeza apaga as requisições de extrações com mais de 60 dias que nenhuma
`ConferenciaLote` liga nem lista como candidata. As ligadas ficam para sempre.

## `TentativaLancamento` (PR 2)

É um lote numa execução real, na ordem em que foi tentado (FR-010).

| Campo | Tipo | Regra |
|---|---|---|
| `execucao` | FK → `ExecucaoRobo`, `PROTECT` | — |
| `ordem` | small int | 1, 2, 3… na execução |
| `lote` | char(12), indexado | — |
| `momento` | datetime | antes do Salvar (o `EM_LANCAMENTO` confirmado) |
| `resultado` | choices `LANCADA`, `VERIFICAR`, `ERRO`, `IGNORADA` | gravado com o resultado |
| `requisicao` | char(9), vazio | o número obtido, quando `LANCADA` |
| `foto` | JSON, nulo | cabeçalho, itens e placa do centro como o robô vai digitar (R11) |
| `historica` | bool | criada por `importar_tentativas` a partir do journal (R15) |

**Unicidade**: (`execucao`, `ordem`) e (`execucao`, `lote`).

**Gravação**:
- a tentativa é criada na mesma transação de `_travar`, que confirma o `EM_LANCAMENTO`, com `resultado`
  `VERIFICAR` (o lado seguro: se o processo morre, a tentativa fica como incerta);
- é atualizada para `LANCADA` na transação de `_gravar`.

Uma tentativa que falha no preenchimento, antes do Salvar, é `ERRO` e não entra no cálculo de
intervalos.

## `ConferenciaLote` e `Candidata` (PR 3)

São o resultado de um lote numa extração (FR-004 da spec, entidade "Conferência de lote").

| Campo | Tipo | Regra |
|---|---|---|
| `lote` | char(12), indexado | — |
| `extracao` | FK → `ExtracaoOficial`, `PROTECT` | — |
| `tipo` | choices `LANCAMENTO`, `REVISAO`, `VERIFICAR` | R13 |
| `veredito` | choices `AGUARDANDO`, `COMPROVADO`, `DIVERGENTE`, `NAO_ENCONTRADO`, `DUPLICADO`, `CONFLITO`, `INTERVALO_VAZIO`, `COM_CANDIDATAS`, `SEM_TENTATIVA` | os três últimos só em `VERIFICAR` |
| `requisicao` | FK → `RequisicaoOficial`, nula, `PROTECT` | a ligada |
| `outra_requisicao` | FK → `RequisicaoOficial`, nula, `PROTECT` | a segunda, em `DUPLICADO` e `CONFLITO` |
| `origem_vinculo` | choices `OBSERVACOES`, `NUMERO`, `AMBOS`, vazio | — |
| `diferencas` | JSON (lista de `{campo, esperado, oficial}`) | — |
| `notas` | JSON (lista de `{campo, texto}`) | nome do centro diferente, de/para que explica um código |
| `alterado_depois` | bool | só em `REVISAO` (FR-017) |
| `intervalo_de`, `intervalo_ate` | char(9), vazios | só em `VERIFICAR` (R14); `intervalo_ate` vazio = aberto |
| `tentativa` | FK → `TentativaLancamento`, nula | a tentativa conferida |
| `criada_em` | datetime | — |

**Unicidade**: (`lote`, `extracao`, `tipo`).

`Candidata` tem `conferencia` (FK, `CASCADE`), `requisicao` (FK → `RequisicaoOficial`, `PROTECT`),
`e_esta` (bool: este lote nas observações) e `ordem` (semelhança, FR-023).

### "Aguardando" nunca vem de uma extração com falha

Só uma extração `SUCESSO` grava `ConferenciaLote`. O "Aguardando conferência" da tela é **derivado**:
é o estado de um lote lançado que ainda não tem **conferência conclusiva** depois do lançamento. Isso
cobre três casos:
- nenhuma extração depois do lançamento;
- só extrações com falha, que ficam registradas (`ExtracaoOficial` com a `Importacao` em `FALHA`) mas
  não gravam `RequisicaoOficial` nem `ConferenciaLote` e não entram em veredito nem em liberação;
- só extrações bem-sucedidas com `veredito=AGUARDANDO`, que ainda não trazem a requisição nem um
  número maior (a latência do SC-008).

Uma `ConferenciaLote` com `AGUARDANDO` vem só desse último caso e mantém o lote nesse estado.

**Tipo da conferência**: enquanto o lote não tem conferência conclusiva, toda conferência dele é do
tipo `LANCAMENTO`, inclusive as `AGUARDANDO`, que são provisórias. A **primeira conferência
`LANCAMENTO` conclusiva** dá o veredito do lançamento (FR-017). Só as conferências seguintes a ela são
`REVISAO`. Assim, a latência do relatório nunca transforma o veredito do lançamento em revisão, e o
"alterado no SCPI depois do lançamento" compara sempre contra esse primeiro veredito conclusivo.

### Estados de um lote lançado

```text
               extração depois do lançamento
(lançado) ──► AGUARDANDO ──► COMPROVADO | DIVERGENTE | NAO_ENCONTRADO | DUPLICADO | CONFLITO
                    ▲              │ revisão: alterado_depois (o veredito fica)
                    │              │ DIVERGENTE ─(revisão igual à entrega)─► COMPROVADO (FR-018)
                    └── correção do número (FR-026), a partir de NAO_ENCONTRADO ou CONFLITO
```

### Estados de um lote em verificar

```text
VERIFICAR ──► SEM_TENTATIVA       (só informar o número ou não lançar)
          ──► COM_CANDIDATAS      (só informar o número, "é esta" ou não lançar)
          ──► INTERVALO_VAZIO     (liberar permitido, com "Conferi no SCPI", só se nenhuma extração
                                   posterior à tentativa registrou candidata; R17, FR-024)
```

Sem extração posterior à tentativa, não existe conferência `VERIFICAR`, e a liberação é recusada.

## `CorrecaoVinculo` (PR 5)

É a correção do número de um lote lançado (FR-026).

| Campo | Tipo |
|---|---|
| `lote` | char(12), indexado |
| `anterior`, `novo` | char(9) |
| `conferencia` | FK → `ConferenciaLote` de origem (`NAO_ENCONTRADO` ou `CONFLITO`), `PROTECT` |
| `usuario` | FK → `AUTH_USER_MODEL`, `PROTECT` |
| `quando` | datetime |

A `LinhaSaida` muda só em `requisicao_scpi` e `mensagem`, por `pedidos.servicos.corrigir_requisicao`
([research R16](research.md#r16-correção-de-um-lote-lançado-fr-026)).
