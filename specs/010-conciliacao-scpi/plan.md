# Implementation Plan: Conciliação dos lançamentos do robô com o SCPI

**Branch**: `010-conciliacao-scpi` (branch de trabalho: `claude/conciliacao-scpi`, base da pilha) | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-conciliacao-scpi/spec.md`

## Summary

O sistema passa a comprovar cada lançamento do robô com uma evidência que não depende dele: a "Relação
de Requisições" do SCPI, **sem filtro de tipo**, extraída em outra sessão do navegador. A entrega é
feita em seis PRs empilhados ([abaixo](#entrega-em-prs-empilhados)), na ordem de consequência:

- **Registro oficial guardado** (PR 1): cada extração vira uma `Importacao` do tipo `REQUISICOES` com
  uma `ExtracaoOficial`. O bruto vai comprimido no banco, com a impressão digital, e as requisições e
  os itens são lidos pelo nome das colunas.
- **Execução real com piso e tentativas** (PR 2): extração antes de lançar (sem ela, nada é lançado) e
  depois do último lote. Cada tentativa fica registrada com a foto do que o robô digitou, e o robô
  escreve `Central Almoxarifado <lote>` nas Observações.
- **Verificar sem risco** (PR 3): as candidatas de um lote em verificar são todas as requisições no
  intervalo de números da tentativa. A liberação para relançar é recusada no servidor sem extração
  posterior ou com candidata.
- **Vereditos** (PR 4): Comprovado, Divergente, Não encontrado, Duplicado, Vínculo em conflito e
  Aguardando, com a revisão "alterado no SCPI depois do lançamento" e o comando de conferência.
- **Tela, avisos e correção** (PR 5): a aba Lançamento no SCPI mostra vereditos e candidatas, com
  "Conferir agora" e a correção do número de um lote lançado (FR-026).
- **Diária e retenção** (PR 6): quarto passo do `atualizar_catalogo`, que passa para 07:15, e a
  limpeza de 60 dias.

Decisões técnicas em [research.md](research.md); modelo em [data-model.md](data-model.md); contratos em
[contracts/](contracts/); roteiro de validação em [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python 3.13 (`>=3.13,<3.14`), Django 6.x

**Primary Dependencies**: Django, Playwright (o que já existe), HTMX 4.0.0 (vendorizado, só nos
componentes existentes), waitress; nenhuma dependência nova (`gzip`, `hashlib`, `unicodedata` são da
biblioteca padrão)

**Storage**: MariaDB 11.4 / MySQL 8. App novo `conciliacao` com migrations `0001` a `0004`, mais
`catalogo/0008` (só `choices`); todas aditivas. O bruto fica em `BinaryField` (cerca de 6 MB em 60
dias).

**Testing**: pytest contra MySQL/MariaDB (`config.settings_test`), sem navegador. O SCPI simulado
(`tests/scpi_simulado.py`) ganha o registro do que foi salvo, o relatório no formato real e falhas
controladas. As fixtures de CSV são sintéticas (R20).

**Target Platform**: Docker Compose em Windows 10 com Docker Desktop; robôs no container `web`,
agendador no `agendador`

**Project Type**: aplicação web Django com HTMX (monólito; apps `pedidos`, `catalogo`, `scpi`,
`automacoes`, `interface`, `contas`, `implantacao` e o novo `conciliacao`)

**Performance Goals**: extração de 10 a 14 dias em segundos (cerca de 250 linhas); conciliação de
algumas centenas de lotes em menos de 1 s; a aba lê só o veredito atual de cada lote (uma consulta por
lista)

**Constraints**:
- O Princípio III não admite exceção.
- O SCPI só é estável das 7h às 17h.
- `LinhaSaida` e `SaidaSCPI` sem mudança de contrato.
- `servicos.py` continua o único lugar que grava pedidos.
- Nenhum teste abre navegador nem usa o CSV real.
- Produção com dados reais: migrations novas, nunca regeneradas.
- `check --deploy` sem avisos.
- Nada de CDN ou npm.

**Scale/Scope**: cerca de 7 requisições do robô por dia útil e 150 lotes lançados até 03/11; 6 modelos
novos, 3 comandos novos, 2 rotas POST, mudanças em `scpi/lancamento.py`, `scpi/lancador.py`,
`scpi/relatorios.py`, `scpi/leitura.py`, `pedidos/servicos.py`, `catalogo/saude.py`, na aba Lançamento
no SCPI e no `deploy/crontab`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Verificação | Situação |
|---|---|---|
| I. Regras puras | Leitura do CSV (`scpi.leitura.ler_requisicoes`), chave e período, vínculo, comparação, veredito, intervalo e candidatas em `conciliacao/regras.py`, sem ORM e com teste próprio. Códigos por `norm_u`, quantidades `Decimal` exatas. | Passa |
| II. Uma porta de gravação | A conciliação grava só no app `conciliacao`. A única mudança em `LinhaSaida` fora do robô é a correção do número (FR-026), em `pedidos.servicos.corrigir_requisicao`. O robô continua gravando só `status`, `requisicao_scpi`, `lancado_em` e `mensagem`. | Passa |
| III. Nunca lançar duas vezes | `EM_LANCAMENTO` antes do Salvar, `VERIFICAR` depois do clique e o journal antes do banco ficam intactos (FR-014). As salvaguardas novas só bloqueiam: sem extração de antes não há lançamento; a liberação de verificar exige extração posterior e intervalo vazio; o lote lançado nunca volta à fila (FR-026). Os testes atuais do lançamento continuam. | Passa |
| IV. Dados importados não se perdem | Extração em `Importacao` com transação e trava por tipo; vazia ou cortada é falha e não gera veredito (FR-005); a `SaidaSCPI` não muda (FR-006); o bruto guardado 60 dias e as ligações para sempre. | Passa |
| V. Testes no banco real, sem navegador | SCPI simulado com falhas controladas e CSV sintético no formato real. A navegação nova (relatório sem filtro, campo Observações) só pelo comando de extração e pelo `--dry-run`, feitos à mão. | Passa |
| VI. pt-BR, acessível, sem dependências | Textos em pt-BR; veredito em texto, não só cor; números e lotes em mono; nada externo; UI com `clean-design` + `docs/DESIGN.md`, `ui-ux-pro-max` e `frontend-design`. | Passa |
| Fluxo | Spec e plano antes do código; branch `claude/*` por PR; `CLAUDE.md` atualizado no PR que muda o que ele descreve; portões em cada PR. | Passa |

Sem exceções.

**Reverificação depois da Fase 1**: o modelo põe as tentativas e as conferências fora de `pedidos`.
O contrato do robô mantém a ordem das gravações e só acrescenta passos antes e depois do laço. A
correção do número passa por `servicos.py`. O desenho continua passando.

## Project Structure

### Documentation (this feature)

```text
specs/010-conciliacao-scpi/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # R1–R22
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── relatorio-requisicoes.md
│   ├── comandos.md
│   └── tela-e-acoes.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (não criado aqui)
```

### Source Code (repository root)

```text
conciliacao/                         # app novo
├── models.py                        # ExtracaoOficial, RequisicaoOficial, ItemOficial,
│                                    # TentativaLancamento, ConferenciaLote, Candidata, CorrecaoVinculo
├── regras.py                        # puro: chave, periodo, lote_observado, comparar, veredito,
│                                    # intervalo, candidatas
├── extracao.py                      # extrair(motivo, periodo, obter_csv) via scpi.execucao.executar
├── servicos.py                      # conciliar(extracao), registrar tentativas, limpeza
├── consultas.py                     # veredito atual por lote, liberacao(lote), avisos
├── admin.py                         # só leitura
├── migrations/0001…0004
└── management/commands/
    ├── extrair_requisicoes.py
    ├── conciliar_lancamentos.py
    └── importar_tentativas.py

scpi/
├── leitura.py                       # + ler_requisicoes
├── relatorios.py                    # + baixar_requisicoes
├── lancamento.py                    # executar_lancamento(..., extrair); tentativas; antes/depois
├── lancador.py                      # Observações no cabeçalho
├── disparo.py                       # + iniciar_conciliacao
└── management/commands/
    ├── lancar_saidas.py             # passa extrair=baixar_requisicoes
    └── atualizar_catalogo.py        # + passo Requisições (PR 6)

catalogo/models.py                   # Importacao.Tipo.REQUISICOES (+ migration 0008)
catalogo/saude.py                    # avisos do FR-028
pedidos/servicos.py                  # liberar com R17; corrigir_requisicao
automacoes/views.py, urls.py         # conferir, corrigir
pedidos/templates/pedidos/_lancamentos.html (+ parciais da conciliação)
automacoes/historico.py              # rótulo do tipo REQUISICOES
deploy/crontab                       # atualizar_catalogo às 07:15
CLAUDE.md                            # seções de lançamento, catálogo, automações e app novo

tests/
├── scpi_simulado.py                 # + registro, relatorio(), falhas novas
├── relacao_requisicoes.py           # gerador de CSV sintético
├── test_scpi_leitura_requisicoes.py
├── test_conciliacao_regras.py
├── test_conciliacao_extracao.py
├── test_conciliacao_robo.py
├── test_conciliacao_verificar.py
├── test_conciliacao_vereditos.py
├── test_conciliacao_tela.py
└── test_conciliacao_diaria.py
```

**Structure Decision**: monólito Django, como os subprojetos anteriores. O app novo guarda o estado da
conciliação. O código de SCPI continua em `scpi`; a gravação de pedidos, em `pedidos/servicos.py`; a
apresentação, na aba que já existe.

## Entrega em PRs empilhados

### Regras da pilha

- **Base da pilha**: o PR 0, `claude/conciliacao-scpi` → `develop`, só com a spec e este plano. Cada PR
  seguinte tem como base a branch do anterior e mostra só o próprio diff.
- **Cada PR passa os portões sozinho**: `pytest`, `ruff check`, `ruff format --check` e
  `makemigrations --check`. Cada um deixa o sistema funcionando em produção se o deploy parar nele e
  atualiza o `CLAUDE.md` no que muda.
- **Merge de baixo para cima, um de cada vez, pelo usuário**, em `develop`. Nunca se mergeia a pilha
  inteira pelo botão de stack do GitHub nem pelo `merge-async`: isso já fez squash direto em `main` e
  deixou `develop` sem o PR de cima.
- **Depois que o PR k entra**: troca-se a base do PR k+1 para `develop` e rebaseia-se a branch dele
  sobre `origin/develop` (`git rebase --onto origin/develop <ponta antiga de k> <branch k+1>`). Em
  seguida, `git push --force-with-lease`, só na própria branch `claude/*`. O mesmo vale para os PRs
  acima.
- **Correção de revisão num PR do meio**: commit na branch dele, depois rebase das de cima (como
  acima).
- **O PR 2 só começa depois que o [PR #53](https://github.com/joaozuneda9/CentralAlmoxarifado-Django-Docker/pull/53)
  (Tipo Saída) estiver em `develop`**, porque os dois mexem em `scpi/lancador.py`. A pilha é rebaseada
  sobre ele antes.
- **Produção** continua por tag e imagem aprovada (`deploy/FLUXO_GIT.md`), num pedido explícito. A
  pilha pode ir em partes. O mínimo recomendado para a garantia de não duplicar é PR 1 + 2 + 3, e
  `importar_tentativas` roda em produção só a pedido do usuário depois do PR 3.

### Os PRs

| # | Branch | Base | Entrega | Requisitos | Migration |
|---|---|---|---|---|---|
| 0 | `claude/conciliacao-scpi` | `develop` | spec, checklist, plano, pesquisa, modelo, contratos, quickstart | — | — |
| 1 | `claude/conciliacao-1-extracao` | 0 | registro oficial guardado | FR-001, 003, 005, parte de 004 | `catalogo/0008`, `conciliacao/0001` |
| 2 | `claude/conciliacao-2-robo` | 1 | execução real com piso, tentativas e Observações | FR-002, 008–014 | `conciliacao/0002` |
| 3 | `claude/conciliacao-3-verificar` | 2 | verificar sem risco | FR-022–025, US2 | `conciliacao/0003` |
| 4 | `claude/conciliacao-4-vereditos` | 3 | vereditos e revisão | FR-015–021, US1, US4, US5 | — |
| 5 | `claude/conciliacao-5-tela` | 4 | tela, avisos, conferência pela tela e correção | FR-026–031 | `conciliacao/0004` |
| 6 | `claude/conciliacao-6-diaria` | 5 | extração diária às 07:15 e retenção | FR-004, 006, 007, US6 | — |

#### PR 1. Registro oficial guardado

- **O quê**:
  - app `conciliacao` com `ExtracaoOficial`, `RequisicaoOficial` e `ItemOficial`;
  - `Importacao.Tipo.REQUISICOES` e o rótulo dele no histórico de Automações;
  - `scpi.leitura.ler_requisicoes` (pura) e `scpi.relatorios.baixar_requisicoes`;
  - `conciliacao.extracao.extrair`, sobre `scpi.execucao.executar`, que guarda o bruto gzip com a
    impressão e não repete o arquivo de impressão igual;
  - `regras.chave` e `regras.periodo`;
  - comando `extrair_requisicoes`; admin só leitura;
  - gerador de CSV sintético (`tests/relacao_requisicoes.py`).
- **Não muda**: robô, `SaidaSCPI`, telas.
- **Testes**:
  - leitura: colunas obrigatórias, registro quebrado (recolado), relatório cortado (falha), planilha,
    cabeçalho variando, vazio, quantidade 0;
  - extração: sucesso, falha (sem requisições gravadas e com `maior_requisicao` nulo), impressão igual
    (aponta para a origem), impressão igual a uma origem já sem bytes (guarda o seu), trava ocupada;
  - chave na virada do ano.
- **Pronto quando**: os portões passam e o quickstart, passo 2 (primeira parte), foi feito pelo usuário
  no SCPI real.
- **Risco**: o relatório sem tipo trazer algo diferente do CSV que o usuário extraiu. Ele é detectado
  pelo passo 2 antes do PR 2.

#### PR 2. Execução real com piso, tentativas e Observações

- **O quê**:
  - `TentativaLancamento` com foto;
  - `executar_lancamento(..., extrair)`: extração de antes com 3 tentativas, piso, laço com tentativas
    e extração de depois (só guarda, sem conciliar ainda);
  - Observações em `lancador.preencher_cabecalho`;
  - `lancar_saidas` passa `baixar_requisicoes`;
  - `SCPISimulado` com o registro do que foi salvo, o `relatorio()` e as falhas de relatório.
- **Não muda**: a ordem das gravações do Princípio III; a simulação não extrai.
- **Testes**: quickstart, passo 3; todos os testes atuais do lançamento.
- **Pronto quando**: os portões passam e o usuário fez o `--dry-run` com as Observações preenchidas
  (quickstart, passo 2, segunda parte).
- **Risco**:
  - O SCPI recusar ou truncar o texto nas Observações. Aparece no `--dry-run`. Se acontecer, o
    preenchimento vira `ErroSCPI` e o lote fica `ERRO`, sem salvar.
  - O lançamento parar quando o SCPI está instável. É a decisão 6, com mensagem explicada.

#### PR 3. Verificar sem risco

- **O quê**:
  - `ConferenciaLote` e `Candidata` (o modelo inteiro, já com os vereditos do PR 4);
  - `regras.intervalo` e `regras.candidatas`;
  - `conciliacao.servicos.conciliar_verificar`, chamado depois da extração de depois e pela extração
    manual;
  - `consultas.liberacao`, e a recusa em `_resolver_com_a_trava` (R17), com a mensagem que lista as
    candidatas;
  - comando `importar_tentativas`.
- **Não muda**: as ações "informar número" e "não lançar" continuam como hoje.
- **Testes**: quickstart, passo 4.
- **Pronto quando**: os portões passam e o `--dry-run` do `importar_tentativas` contra uma cópia do
  journal de produção conta as execuções esperadas (8, 28 e 49 entre elas).
- **Risco**: lotes em verificar antigos sem journal ficarem presos. É o lado seguro: eles se resolvem
  informando o número ou marcando "não lançar".

#### PR 4. Vereditos e revisão

- **O quê**:
  - `regras.comparar` e `regras.veredito` (R10, R12), com normalização de texto, centro pelo código,
    placa do centro e de/para só como nota;
  - `conciliacao.servicos.conciliar` para os lotes lançados (lançamento e revisão, R13), chamado depois
    da extração de depois;
  - comando `conciliar_lancamentos` (com `--arquivo`);
  - foto recalculada para os lotes lançados antes do PR 2.
- **Não muda**: `LinhaSaida` (FR-021).
- **Testes**: quickstart, passo 5.
- **Pronto quando**: os portões passam e o repasse do quickstart, passo 6, deu os números do SC-002a
  numa cópia local.
- **Risco**: diferenças falsas que ainda não apareceram no CSV de amostra. O repasse sobre os dados
  reais as mostra antes da tela existir.

#### PR 5. Tela, avisos, conferência pela tela e correção

- **O quê**:
  - na aba Lançamento no SCPI, vereditos, diferenças, candidatas e a última extração;
  - `automacoes:conferir` com `scpi.disparo.iniciar_conciliacao`;
  - `automacoes:corrigir` com `pedidos.servicos.corrigir_requisicao` e a `CorrecaoVinculo`;
  - avisos de saúde do FR-028;
  - textos de recusa do contrato.
- **Não muda**: as ações existentes da aba.
- **Testes**: quickstart, passo 7; `tests/test_epis_acesso.py` cobre as rotas novas.
- **Pronto quando**: os portões passam e a conferência visual no navegador local foi feita (375 px, sem
  depender de cor).
- **Risco**: a aba ficar carregada. Mitigação: as divergências aparecem primeiro e os comprovados ficam
  recolhidos.

#### PR 6. Diária e retenção

- **O quê**:
  - passo "Requisições" no `atualizar_catalogo` (mesma sessão, período R9, conciliação e limpeza);
  - limpeza de 60 dias (bruto e requisições sem ligação);
  - `deploy/crontab` às 07:15;
  - `CLAUDE.md` com o horário e o passo.
- **Não muda**: os três passos atuais nem a `SaidaSCPI` (FR-006).
- **Testes**: quickstart, passo 8.
- **Pronto quando**: os portões passam.
- **Risco**: o `atualizar_catalogo` ficar mais longo. É mais um relatório de poucos segundos na mesma
  sessão.

### Dependências entre os PRs

```text
0 ─► 1 ─► 2 ─► 3 ─► 4 ─► 5 ─► 6
          ▲
     PR #53 em develop
```

A pilha é linear. Cada PR usa modelos ou funções do anterior. Nenhum par se troca de ordem sem
reescrever um deles.

## Complexity Tracking

Sem violações da constituição a justificar.
