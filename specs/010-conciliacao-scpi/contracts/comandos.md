# Contrato: comandos e robô

## Comandos novos

### `extrair_requisicoes` (PR 1)

```text
manage.py extrair_requisicoes --desde DD/MM/AAAA --ate DD/MM/AAAA [--arquivo CSV]
```

- Abre o SCPI (`relatorios.baixar_requisicoes`) ou lê o `--arquivo`. Grava uma `ExtracaoOficial` com
  `motivo=MANUAL` e não concilia nada.
- Sai com erro se a extração falhar. A `Importacao` fica `FALHA`, com o motivo.
- Recusa se já houver uma extração em andamento (trava do tipo `REQUISICOES`).
- Serve à verificação manual da navegação no SCPI real (quickstart, passo 2).

### `conciliar_lancamentos` (PR 4)

```text
manage.py conciliar_lancamentos [--arquivo CSV] [--desde DD/MM/AAAA --ate DD/MM/AAAA]
manage.py conciliar_lancamentos ... --sem-limpeza        # a partir do PR 6
```

- Sem `--arquivo`, extrai o período de R9 (hoje − 9 dias, mais as datas dos lotes em verificar
  abertos). Com `--arquivo`, usa o período dado ou o que o próprio CSV cobre.
- Concilia os lotes lançados e os lotes em verificar cobertos.
- A partir do PR 6, roda em seguida a limpeza de 60 dias, salvo com `--sem-limpeza`. A opção nasce no
  PR 6, junto com a limpeza; no PR 4 o comando não limpa nada e não tem a opção.
- Recusa com lançamento ou importação em andamento (FR-029).
- É o que a tela dispara pelo botão "Conferir agora" (`scpi.disparo.iniciar_conciliacao`, log
  `conciliar_lancamentos.log`). Com `--arquivo`, é também o que repassa o CSV real numa cópia do
  banco (quickstart, passo 6).

### `importar_tentativas` (PR 3)

```text
manage.py importar_tentativas --journal CAMINHO [--dry-run]
```

- Lê o `lancar_saidas_journal.jsonl` e cria as `TentativaLancamento` históricas (R15).
- É idempotente por (`execucao`, `lote`). O `--dry-run` só conta.
- Roda uma vez por ambiente, depois do deploy do PR 3, e só a pedido do usuário em produção.

## Mudanças no robô (PR 2)

### `executar_lancamento(execucao, abrir_scpi, *, lotes, extrair)`

O parâmetro novo é `extrair: Callable[[date, date], bytes]`. Em produção ele é
`relatorios.baixar_requisicoes`; nos testes, `SCPISimulado.relatorio`. Ele só baixa: devolve os bytes
ou levanta exceção, e não grava nada.

**Como a falha chega ao lançamento.** Cada tentativa de extração passa por
`conciliacao.extracao.extrair(motivo, periodo, obter_csv, execucao) -> ExtracaoOficial`, com
`obter_csv = lambda: extrair(de, ate)`. É essa camada, e não o lançamento, que grava:
- ela chama `scpi.execucao.executar`, que cria a `Importacao` do tipo `REQUISICOES` e, numa transação,
  lê o CSV (`ler_requisicoes`) e grava a `ExtracaoOficial` com as requisições;
- se o download levantar exceção ou a leitura der `ErroImportacao`, o `executar` captura e marca a
  `Importacao` como `FALHA`, com o motivo. Ainda assim, `extrair` grava a `ExtracaoOficial` daquela
  tentativa, fora da transação desfeita: sem requisições, com `maior_requisicao` nulo e o `motivo`
  `ANTES` ou `DEPOIS`;
- o sinal para o lançamento é o **resultado**, não uma exceção: `extracao.importacao.situacao ==
  SUCESSO`. A única exceção que sobe é `ImportacaoEmAndamento` (a trava do tipo está com outra
  extração). Nesse caso não há `Importacao` nem `ExtracaoOficial`; a tentativa conta como falha e só
  vai para o log.

A ordem de uma execução **real** é:

1. A trava `TRAVA_LANCAMENTO` (como hoje).
2. A seleção dos lotes (como hoje). Sem lote válido, termina sem extrair.
3. A **extração de antes**: o período de R9, até 3 tentativas. Se falhar, a execução termina `FALHA`
   ("não foi possível extrair as requisições do SCPI antes de lançar"), sem abrir o navegador do
   lançamento e sem mudar nenhuma `LinhaSaida`, lote, tentativa ou conferência (FR-009). Ficam
   gravados só os registros da execução (`ExecucaoRobo` em `FALHA`) e das extrações. Cada tentativa que falha no download ou na leitura
   fica registrada como uma `ExtracaoOficial` `ANTES` com a `Importacao` em `FALHA` e o motivo, que a
   tela mostra. A tentativa recusada por `ImportacaoEmAndamento` não cria registro: só vai para o log
   e conta entre as 3.
4. O piso = `maior_requisicao` da extração de antes.
5. O laço `_lancar_um` como hoje, com a `TentativaLancamento` criada no `_travar` e fechada no
   `_gravar` (data-model).
6. Com o navegador do lançamento fechado, a **extração de depois** (mesmo período). Ela é seguida da
   conciliação dos lotes da execução a partir do PR 3 (candidatas) e do PR 4 (vereditos). Se falhar,
   a `ExtracaoOficial` `DEPOIS` fica registrada com a `Importacao` em `FALHA` e o motivo, gera um
   aviso no log e nenhuma `ConferenciaLote` é gravada; os lotes aparecem "Aguardando" porque
   ainda não têm conferência de uma extração bem-sucedida depois do lançamento (FR-012; ver
   data-model, "Aguardando"). A situação da execução não piora por isso.

A **simulação** (`--dry-run`) não extrai nem concilia (FR-013), mas preenche as Observações.

### `lancador.preencher_cabecalho`

Depois do centro de custo e antes do Recebimento, preenche o campo **Observações** com
`Central Almoxarifado <lote>` e, se a saída tem observação no Central, `Obs.: <observação>` num
parágrafo novo (FR-011, `regras.texto_observacoes`). Se o campo não for achado, é `ErroSCPI` antes do
Salvar: o lote vira `ERRO`, seguro para tentar de novo. O `conferir_cabecalho` relê o campo.

### Protocolo `SCPI` e `SCPISimulado`

O protocolo não muda: o lote já chega no `preencher(req)`. O simulado ganha:
- o registro de cada requisição salva (número, cabeçalho, itens, observações, tipo);
- `relatorio(de, ate) -> bytes` no formato de [relatorio-requisicoes.md](relatorio-requisicoes.md);
- falhas configuráveis: as de R20, mais `falhas_relatorio` (quantas vezes o relatório falha antes de
  funcionar).

### Garantias que não mudam (FR-014, Princípio III)

- O `EM_LANCAMENTO` continua confirmado no banco antes do Salvar.
- Uma falha depois do clique continua virando `VERIFICAR`.
- O número continua indo ao journal antes do banco.
- Os testes atuais do lançamento continuam passando sem mudança de expectativa. A única mudança é o
  `extrair` simulado nas chamadas.
