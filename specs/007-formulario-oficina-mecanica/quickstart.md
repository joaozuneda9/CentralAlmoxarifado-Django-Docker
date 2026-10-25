# Quickstart: validar o formulário da oficina mecânica

Roteiro de validação de ponta a ponta. Nenhum passo lança no SCPI nem roda importador contra o SCPI
real. Detalhes em [data-model.md](data-model.md) e [contracts/](contracts/).

## Pré-requisitos

- MariaDB/MySQL local e `.env` de desenvolvimento (README); `uv sync`.
- Branch `claude/oficina-mecanica`.

```bash
uv run python manage.py migrate
uv run python manage.py runserver
```

## 1. Portões automáticos

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
```

Esperado: tudo limpo; `catalogo/0004_oficina` e `pedidos/0004_oficina` aplicadas; a suíte inteira
passa (SC-005).

## 2. Configuração (admin)

1. Cadastros › Opções: lista "Grupos (oficina)" com `AUTO PECAS`.
2. Cadastros › Materiais da oficina: incluir um óleo do grupo `GERAL`. Incluir de novo: recusado.

## 3. Saúde do catálogo

- Sem nenhum grupo nem material: erro "nada a oferecer"; `/pedido/oficina/` indisponível.
- Com a configuração do passo 2: "Formulário da oficina mecânica: N materiais."
- Um grupo inexistente na lista: aviso "Grupos da oficina sem material visível".

## 4. Formulário (`/pedido/oficina/`, no celular e no computador)

1. O cartão "Oficina mecânica" aparece na página inicial.
2. Buscar "filtro": aparecem só materiais da escolha, os sem estoque bloqueados no fim; o óleo do
   `GERAL` incluído aparece; um material do `GERAL` não incluído, não.
3. O destino lista `OFICINA MECÂNICA` e as viaturas como "descrição — placa", sem a descrição
   sozinha e sem outros centros. Digitar a placa sem hífen escolhe a viatura.
4. Enviar com destino numa viatura: tela de sucesso com o número.

## 5. Almoxarifado

1. O pedido aparece no painel com a origem "Oficina mecânica" e filtra por ela.
2. Atender: centro de custo e placa já vêm da viatura; o recibo mostra o destino.
3. Um pedido com destino `OFICINA MECÂNICA`: o atendimento sugere esse centro, sem placa.
4. Simular o lançamento (`Simular`, sem `LANCAMENTO_REAL`): o lote aparece como os demais.

## Fica para a operação

- SC-001 (tempo no celular) e a escolha real dos grupos e dos materiais avulsos, depois da
  implantação.
