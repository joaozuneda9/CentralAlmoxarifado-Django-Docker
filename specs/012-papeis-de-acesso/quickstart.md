# Quickstart: validar os papéis de acesso

**Spec**: [spec.md](spec.md) · **Contratos**: [tabela-de-rotas.md](contracts/tabela-de-rotas.md),
[recusa.md](contracts/recusa.md)

## Pré-requisitos

- MariaDB ou MySQL local e `.env` de desenvolvimento (README).
- Branch da implementação com `develop` atualizada.

## 1. Portões automáticos

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
uv run python manage.py makemigrations --check --dry-run
```

Esperado: tudo limpo, inclusive `tests/test_papeis_acesso.py` (matriz de rotas) e o teste da
migration `contas/0004_papeis`.

## 2. Migração sem perda de acesso (banco local com usuários)

```bash
uv run python manage.py migrate contas
```

Esperado: a migration termina sem erro; no admin, em Grupos, existem **Atendimento** e **Gestão**, e
cada usuário ativo que não é da Segurança do Trabalho está nos dois. Abrir o painel, Automações, Curva
ABC e Formulários com um desses usuários: tudo como antes.

## 3. Restringir um funcionário

1. No admin, tirar **Gestão** de um usuário de teste (deixar só **Atendimento**).
2. Entrar com ele: o menu mostra só **Painel** e **Saída avulsa**; o painel não tem o cartão do
   lançamento nem "Ver automações".
3. Atender um pedido, imprimir o recibo, editar o atendimento e registrar uma saída avulsa: nenhuma
   recusa.
4. Digitar `/painel/automacoes/`, `/painel/catalogo/curva/` e `/painel/catalogo/formularios/`: página
   "Sem acesso a esta página", com "Voltar ao painel".
5. Conferir no `logs/almoxarifado.log` uma linha `contas.acesso` por recusa, no formato de
   [recusa.md](contracts/recusa.md).

## 4. Usuário sem papel

Criar um usuário sem grupo e entrar: página "Seu usuário ainda não tem acesso", só com Sair.

## 5. Implantação

Seguir `deploy/AMBIENTES.md` (o `atualizar.ps1` faz o backup antes do `migrate`). Depois, em produção,
o chefe tira **Gestão** dos 2 funcionários no admin (SC-004). Nada disso roda sem pedido do usuário.
