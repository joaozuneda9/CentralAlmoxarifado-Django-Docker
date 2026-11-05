# Quickstart: validar a conciliação

Este roteiro valida cada PR da [pilha](plan.md#entrega-em-prs-empilhados). Os passos 1, 3, 4 e 5 são
automáticos. Os passos 2 e 6 são manuais e só o usuário os roda, porque abrem o SCPI real ou usam dados
de produção.

## Pré-requisitos

- MySQL 8 ou MariaDB local, `.env` de desenvolvimento, `uv sync`.
- `LANCAMENTO_REAL` desligado no `.env` local (o padrão).
- Para os passos 2 e 6: o Playwright instalado (`uv run playwright install chromium`), acesso ao SCPI
  entre 7h e 17h, uma cópia recente do banco de produção restaurada localmente e o CSV real fora do
  repositório.

## 1. Portões de cada PR

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
uv run python manage.py makemigrations --check --dry-run
```

O resultado esperado é tudo limpo. Os testes do lançamento que já existiam (`tests/test_lancamento.py`,
`tests/test_lancamento_real.py`, `tests/test_lancar_saidas.py`) passam sem mudar de expectativa
(FR-014).

## 2. Navegação do relatório e das Observações no SCPI real (PRs 1 e 2, manual)

```bash
uv run python manage.py extrair_requisicoes --desde 23/10/2026 --ate 05/11/2026
```

Esperado:
- uma `Importacao` "Requisições do SCPI" concluída, com o número de requisições do período;
- a `ExtracaoOficial` com a impressão e o arquivo;
- o `TPREQUI` com "BALCÃO", "OUTRA" e vazio.

Depois do PR 2, rode a simulação de um lote pendente:

```bash
uv run python manage.py lancar_saidas --dry-run --lote <lote pendente>
```

No log, o campo Observações aparece preenchido com `Central Almoxarifado <lote>` antes do descarte.
Nenhuma requisição é salva no SCPI, nenhuma linha de saída muda e nenhuma extração é feita; só fica
registrada a execução da simulação (`ExecucaoRobo` com `simulacao`), como em todo `--dry-run`.

## 3. Robô com o SCPI simulado (PR 2)

Os testes `tests/test_conciliacao_robo.py` cobrem:
- a extração de antes falha 3 vezes: a execução termina `FALHA` e nenhuma linha muda (SC-004);
- falha 2 vezes e funciona na terceira: o piso é gravado e os lotes são lançados;
- cada lote salvo tem `Central Almoxarifado <lote>` nas observações do simulado;
- a ordem das tentativas e as fotos ficam gravadas;
- a extração de depois falha: os lotes ficam lançados e "Aguardando".

## 4. Verificar sem risco (PR 3)

Os testes `tests/test_conciliacao_verificar.py` cobrem:
- um `salvar` que registra e depois levanta: o lote fica `VERIFICAR`, a extração de depois traz a
  requisição com o lote nas observações, a candidata vem "é esta" e a liberação é recusada;
- um `salvar` que levanta sem registrar, com o lote seguinte lançado (+1): o intervalo sai vazio e a
  liberação é aceita com "Conferi no SCPI";
- uma requisição "à mão" no simulado no meio da execução cai no intervalo: a liberação é recusada;
- liberar sem extração depois da tentativa: recusado (o caso de 03/11, 15h26);
- as execuções 8 e 28 reproduzidas com números sintéticos vizinhos: o intervalo sai vazio (SC-003);
- `importar_tentativas` sobre um journal de fixture cria as tentativas na ordem e é idempotente.

## 5. Vereditos (PR 4)

Os testes `tests/test_conciliacao_vereditos.py` cobrem:
- os seis vereditos;
- a revisão "alterado no SCPI depois do lançamento";
- a volta de Divergente para Comprovado;
- os casos sintéticos do SC-002a:
  - tipo vazio;
  - código trocado com par de/para mostrado só como nota;
  - centro renomeado com o mesmo código;
  - acentos decompostos;
  - placa vinda do centro;
  - item a mais e quantidade diferente;
  - data diferente;
- três lotes idênticos no mesmo dia, cada um ligado à sua requisição pelas observações e pelo número
  (SC-005);
- uma requisição recém-salva que ainda não está no relatório fica "Aguardando" (SC-008).

## 6. Repasse sobre dados reais (PR 4, manual, numa cópia local)

Com a cópia de produção restaurada e o journal de produção copiado para fora do repositório:

```bash
uv run python manage.py importar_tentativas --journal <cópia do journal> --dry-run
```

```bash
uv run python manage.py conciliar_lancamentos --arquivo "<CSV real de 23/10 a 04/11>"
```

Esperado (SC-002a), conferido em 05/11/2026: dos 75 lotes lançados com data no período do CSV,
- 72 saem "Comprovado" (o AV-000129 com a nota do centro renomeado);
- AV-000083 e AV-000084 saem "Divergente: código";
- AV-000081 sai "Divergente: itens" (no SCPI, `023.002.010 × 4` a mais e `023.003.004 × 3` no lugar
  de 5).

Os lotes com data fora do período do CSV (o AV-000058 e os de 21 e 22/10) não são conferidos por ele.
Para o SC-002 (tipo vazio de AV-000014 a 073), repita com um CSV sem filtro que cubra de 09/10 a 22/10.

## 7. Tela e avisos (PR 5)

`tests/test_conciliacao_tela.py` cobre:
- a aba mostra veredito, diferenças e candidatas;
- "Conferir agora" é recusado com lançamento em andamento;
- a correção do número só vale para Não encontrado ou Vínculo em conflito e é recusada para um número de
  outro lote;
- a Segurança do Trabalho recebe 403 ou redirecionamento nas rotas novas (`tests/test_epis_acesso.py`
  já percorre todas);
- os avisos de saúde aparecem.

Confira também pelo navegador local no `runserver`: em 375 px, sem rolagem horizontal, e o estado legível
sem cor.

## 8. Diária e retenção (PR 6)

`tests/test_conciliacao_diaria.py` cobre:
- o `atualizar_catalogo` com o quarto passo;
- uma falha nele que não desfaz os três primeiros;
- a limpeza que esvazia o bruto com mais de 60 dias e mantém os vereditos e as requisições ligadas
  (SC-007);
- uma extração igual à anterior que não guarda arquivo novo;
- a origem que só perde o bruto quando ela e todas as que apontam para ela passaram dos 60 dias;
- uma extração igual a uma origem já sem bruto, que guarda o seu.

O `deploy/crontab` mostra o `atualizar_catalogo` às 07:15. Daqui em diante, um novo repasse do
passo 6 leva `--sem-limpeza`, para não apagar brutos da cópia local.
