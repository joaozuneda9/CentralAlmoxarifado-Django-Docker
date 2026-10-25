# Central Almoxarifado (Django)

Sistema de requisições do almoxarifado SAEP, em Django, sem dependência da
plataforma Google. Substituiu o Central Almoxarifado em Google Apps Script, que
hoje é só histórico: o sistema não depende dele nem precisa reproduzi-lo.

Design: [docs/superpowers/specs/2026-10-10-central-almoxarifado-django-design.md](docs/superpowers/specs/2026-10-10-central-almoxarifado-django-design.md)

## O que tem

- **Formulários públicos** (`/`, sem login): pedido de limpeza, copa/cozinha e escritório e
  pedido de materiais AB (limitado ao estoque do SCPI). Cada pedido novo avisa no Telegram
  (`TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` no `.env`).
  O formulário de EPIs passa antes pela autorização da Segurança do Trabalho (grupo
  `Segurança do Trabalho` no admin; `TELEGRAM_CHAT_ID_SEGURANCA` no `.env` avisa a fila dela).
- **Área do almoxarifado** (`/painel/`, login por matrícula): painel com filtros,
  atendimento dos pedidos, saída avulsa, recibo impresso do detalhe do pedido e a página Automações, com as
  importações e o lançamento no SCPI. Cada saída vira linhas que o robô do SCPI lança depois.

## Desenvolvimento

Pré-requisitos: Python 3.13, [uv](https://docs.astral.sh/uv/) e um MySQL 8 ou MariaDB local.

1. Crie o banco e o usuário (num cliente `mysql`/`mariadb` como root). O usuário também
   precisa do banco `test_almoxarifado`, que o pytest cria e apaga. O `DB_HOST` padrão é
   `127.0.0.1` (TCP), por isso o usuário existe também para esse endereço. No `GRANT`, o `_`
   é curinga e por isso vai escapado:

   ```sql
   CREATE DATABASE almoxarifado CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'almox'@'localhost' IDENTIFIED BY '<senha local>';
   CREATE USER 'almox'@'127.0.0.1' IDENTIFIED BY '<senha local>';
   GRANT ALL PRIVILEGES ON almoxarifado.* TO 'almox'@'localhost', 'almox'@'127.0.0.1';
   GRANT ALL PRIVILEGES ON `test\_almoxarifado`.* TO 'almox'@'localhost', 'almox'@'127.0.0.1';
   ```

2. Copie `.env.example` para `.env` e preencha ao menos `DB_PASSWORD`.
3. Instale e prepare:

   ```bash
   uv sync
   uv run python manage.py migrate
   uv run python manage.py createsuperuser
   uv run python manage.py runserver
   ```

4. Testes e lint:

   ```bash
   uv run pytest
   uv run ruff check .
   uv run ruff format --check .
   ```

5. Importações do SCPI (precisam de `SAEP_USER` e `SAEP_PASS` no `.env` e do Chromium do
   Playwright, instalado uma vez com `uv run playwright install chromium`):

   ```bash
   uv run python manage.py importar_cadastro
   uv run python manage.py importar_estoque
   uv run python manage.py importar_saidas_scpi --desde 01/01/2026
   uv run python manage.py atualizar_catalogo      # as três em sequência
   ```

   Com `--arquivo <csv>`, cada comando lê um CSV já baixado do SCPI em vez de abrir o
   navegador (os de exemplo ficam em `tests/fixtures/scpi/`). O resultado de cada execução
   aparece em Automações (aba Visão geral e histórico).

6. Lançamento das saídas no SCPI (mesmos requisitos do item anterior):

   ```bash
   uv run python manage.py lancar_saidas --dry-run --limite 1   # só simula
   uv run python manage.py lancar_saidas                        # lança de verdade
   ```

   **Atenção:** `lancar_saidas` sem `--dry-run` lança de verdade no SCPI, uma requisição por
   lote de saída `PENDENTE`. Sem `LANCAMENTO_REAL=1` no `.env` (o padrão), o lançamento real
   fica bloqueado no comando, na página e no painel: só a simulação roda. Com `--dry-run`, o
   navegador abre, preenche a requisição e a descarta sem salvar, e nenhuma linha muda. O mesmo
   pode ser feito pela página Automações (aba Lançamento no SCPI), que também mostra o andamento e
   resolve os lotes que o robô deixou para conferência. O registro de cada lançamento fica em
   `logs/lancar_saidas_journal.jsonl`.

## Implantação

**Ambiente confirmado:** Windows 10 Pro com Docker Desktop compartilhado. A produção
atual tem dados reais; não reiniciar Windows, WSL ou Docker. A separação da nova
produção está em [deploy/AMBIENTES.md](deploy/AMBIENTES.md), e o fluxo de branches,
PRs e imagens versionadas em [deploy/FLUXO_GIT.md](deploy/FLUXO_GIT.md).
O `compose.yaml` abaixo é legado; o `deploy/atualizar.sh` foi bloqueado para evitar
atualizações no ambiente errado. Os novos ambientes usam Compose e PowerShell
com alvo explícito, sem deploy automático ao fazer push.

O sistema usa Docker Compose: `banco` (MariaDB), `web` (waitress e robôs da página)
e `agendador` (supercronic com `deploy/crontab`: importações e backup). O acesso atual
é HTTP em `45.172.240.231:8010`; Apache e HTTPS não foram confirmados. Apache em
`/almoxarifado` era a proposta anterior, não a topologia atual verificada.
Os comandos de manutenção devem selecionar explicitamente o projeto e os arquivos
do ambiente, conforme `deploy/AMBIENTES.md`.

- [deploy/INSTALACAO.md](deploy/INSTALACAO.md): ambiente Windows confirmado,
  preparação da produção nova e restrições da máquina. Guia para o André.
- [deploy/VIRADA.md](deploy/VIRADA.md): registro histórico da migração do Apps Script, já feita.

Duas coisas a saber:

- `LANCAMENTO_REAL` (no `.env`, padrão `0`) libera o lançamento real no SCPI. Fica `0` em todo
  ambiente que não é o que lança de verdade (desenvolvimento, cópias de teste), para não lançar
  duas vezes as mesmas saídas; só a produção o liga.
- `uv run python manage.py backup_banco` grava o dump comprimido em `BACKUP_DIR` e apaga os com
  mais de 60 dias (roda todo dia pelo agendador do compose).
