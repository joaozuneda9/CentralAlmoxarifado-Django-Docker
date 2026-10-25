# Quickstart: validar o formulário de EPIs

Guia de validação, sem código. Pré-requisitos como no `CLAUDE.md` (MySQL/MariaDB local, `.env`,
`uv sync`). **Nunca** rode contra a produção; nada aqui lança no SCPI (`LANCAMENTO_REAL` desligado).

## 1. Portões automáticos

```bash
uv run python manage.py makemigrations --check --dry-run
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

Esperado: migrations sem pendência, ruff limpo e a suíte inteira verde, inclusive os testes dos
formulários existentes sem alteração (SC-008).

```bash
uv run pytest tests/test_epis_*.py
```

Esperado: os testes novos de catálogo, registro, autorização, acesso, consulta, painel, Telegram e saúde
passam.

## 2. Preparar o ambiente de desenvolvimento

1. `uv run python manage.py migrate` (cria a tabela de autorizações, o modelo de materiais de EPIs e o
   grupo `Segurança do Trabalho`).
2. No admin (`/admin/`): em **Opções**, uma opção de lista "Grupos (EPIs)" com um grupo do cadastro (por
   exemplo, `MATERIAL DE SEGURANÇA E EPI`); opcionalmente um **Material de EPIs** avulso.
3. Importar o cadastro e o estoque de teste (`importar_cadastro` e `importar_estoque` com os CSV de
   `tests/fixtures/scpi/`, `--arquivo`).
4. Criar dois usuários: um do almoxarifado e um de Segurança do Trabalho (no admin, marcar o grupo).

## 3. Roteiro ponta a ponta (US1 a US6)

| Passo | Ação | Esperado |
|-------|------|----------|
| 1 | Abrir `/pedido/epis/`, buscar um EPI, adicionar, informar o nome, enviar | Tela de sucesso com o número e o aviso de aguardando autorização, sem prometer entrega |
| 2 | Painel do almoxarifado (`/painel/`) | O pedido está "Aguardando autorização", sem atalho de atendimento; o filtro Autorização o acha |
| 3 | No detalhe, tentar atender (inclusive reenviando o formulário de outro pedido) | Nenhum atendimento é criado |
| 4 | Entrar com o usuário da Segurança do Trabalho | Chega à fila; o menu só tem "Autorizações" |
| 5 | Esse usuário abre `/painel/`, `/painel/saida-avulsa/`, `/painel/automacoes/`, `/admin/` | Redireciona à fila (GET) |
| 6 | Recusar sem motivo | Recusa não grava; pede o motivo |
| 7 | Autorizar o pedido | Situação "Autorizado"; quem e quando gravados |
| 8 | Voltar ao almoxarifado e atender | Atendimento, recibo e linhas de saída como nos outros formulários |
| 9 | Enviar um segundo pedido e recusá-lo com motivo | Fica "Recusado", sem atendimento, motivo visível ao almoxarifado |
| 10 | Em `/pedido/epis/consulta/`, consultar os números dos passos 1 e 9 e um número inexistente | Autorizado / Recusado com o motivo / mensagem neutra |

## 4. Telegram (opcional, só com token de teste)

Com `TELEGRAM_TOKEN` de teste e dois chats: ao enviar o pedido, só `TELEGRAM_CHAT_ID_SEGURANCA`
recebe; ao autorizar, só `TELEGRAM_CHAT_ID` recebe; ao recusar, nenhum dos dois.

## 5. Conferências de não regressão

- Os formulários de limpeza, AB, viaturas e oficina enviam, atendem e avisam como antes.
- O atalho "Atender" do painel conta só pedidos que podem ser atendidos.
- A saúde do catálogo mostra a linha do formulário de EPIs; a visão geral de Automações mostra a
  contagem.
