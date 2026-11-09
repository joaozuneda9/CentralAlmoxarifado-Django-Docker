# Implementation Plan: Papéis de acesso na área interna

**Branch**: `claude/papeis-de-acesso` | **Date**: 2026-11-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-papeis-de-acesso/spec.md`

## Summary

Tirar da área interna o "todo usuário logado faz tudo". O código passa a perguntar por quatro
permissões próprias (`contas.atender_pedidos`, `operar_automacoes`, `ver_curva`, `ver_formularios`),
agrupadas nos papéis **Atendimento** e **Gestão**. Um middleware novo lê uma tabela única de rota para
regra e nega por padrão o que não está nela; a mesma tabela monta o menu e é conferida por um teste
que percorre todas as rotas. O disparo do lançamento confere a permissão de novo. Toda recusa vira
uma linha no log. Uma migration de dados dá os dois papéis a todos os usuários ativos fora da
Segurança do Trabalho, para ninguém perder acesso no deploy; o chefe restringe depois, no admin.
Decisões em [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Django 6.x (auth, grupos e permissões nativos, admin), HTMX 4.0.0
(vendorizado). Nenhuma dependência nova.

**Storage**: MySQL 8 / MariaDB 11.4. Sem tabela nova: `Meta.permissions` em `contas.Usuario` e dados
em `auth_permission`, `auth_group` e `auth_user_groups` (via `contas.Usuario.groups`).

**Testing**: pytest + pytest-django contra MariaDB (`config.settings_test`), sem navegador.

**Target Platform**: servidor Windows 10 com Docker Desktop (waitress no container `web`).

**Project Type**: aplicação web Django (monólito com apps).

**Performance Goals**: sem meta nova; uma consulta de permissões a mais por requisição autenticada
(research R10).

**Constraints**: produção com dados reais (migrations novas, nunca regeneradas); nenhum usuário perde
acesso no deploy (FR-015); a Segurança do Trabalho não muda (FR-011); `check --deploy` sem avisos.

**Scale/Scope**: 3 usuários internos (o chefe e 2 funcionários), 25 rotas internas classificadas, 4
permissões, 2 papéis.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Regras puras | Cumpre | `contas.acesso.pode(usuario, regra)` e a tabela são puras (sem ORM; o `has_perm` é do objeto). |
| II. Uma porta de gravação | Cumpre | Nada novo grava pedidos; `servicos.py` não muda. A migration grava só grupos e permissões. |
| III. Nunca lançar duas vezes | Reforça | O lançamento ganha uma barreira de pessoa (rota e disparo), além do `LANCAMENTO_REAL`; nenhuma trava, estado ou ordem de gravação do robô muda. |
| IV. Dados importados | Não se aplica | Nenhuma importação muda. |
| V. Testes contra o banco real | Cumpre | Matriz de rotas, migration e recusas testadas no MariaDB; os testes existentes ganham os papéis pela fixture. |
| VI. pt-BR, acessível, sem dependências externas | Cumpre | Página de recusa em pt-BR no design Clean; estado nunca só por cor; Sair por POST com CSRF; nenhuma biblioteca nova. |
| Restrições técnicas | Cumpre | Migrations novas (`contas/0003`, `0004`); nenhuma variável nova no `.env`. |
| Fluxo | Cumpre | Spec e plano antes do código; branch própria; `CLAUDE.md` atualizado no mesmo PR (seções Arquitetura, `contas`, `interface` e Automações). |

**Resultado**: passa, sem exceções. **Depois do design (Phase 1)**: passa; nenhum artefato introduziu
gravação fora de `servicos.py`, dependência externa ou mudança nas travas do SCPI.

## Project Structure

### Documentation (this feature)

```text
specs/012-papeis-de-acesso/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── tabela-de-rotas.md
│   └── recusa.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
contas/
├── models.py                  # Meta.permissions do Usuario
├── acesso.py                  # Regra, REGRAS_POR_ROTA, pode, pode_abrir, registrar_recusa (+ o que já existe da spec 008)
├── middleware.py              # ExigirPermissao (novo) e RestringirSegurancaTrabalho (passa a registrar a recusa)
└── migrations/
    ├── 0003_permissoes.py     # AlterModelOptions
    └── 0004_papeis.py         # grupos, permissões, usuários e a verificação
config/settings.py             # MIDDLEWARE (ExigirPermissao depois do da Segurança) e o logger contas.acesso
interface/
├── navegacao.py               # menu pela tabela (sai o so_equipe)
└── templates/
    ├── 403.html               # PermissionDenied fora do middleware
    └── interface/acesso_negado.html
catalogo/acesso.py             # exige(...) passa a chamar registrar_recusa
pedidos/
├── views/almoxarifado.py      # painel só calcula o cartão do lançamento com a permissão
├── views/autorizacao.py       # registrar_recusa no 403
└── templates/pedidos/
    ├── painel.html            # cartão do lançamento e links condicionados
    └── detalhe.html           # "Resolver em Automações" condicionado
scpi/disparo.py                # iniciar_lancamento confere a permissão
tests/
├── rotas.py                   # rotas_nomeadas() movida de test_epis_acesso.py
├── papeis.py                  # dar_papeis(usuario, *nomes)
├── conftest.py                # usuario_logado com os dois papéis
├── epis_cenario.py            # almoxarifado com os dois papéis
├── test_papeis_acesso.py      # matriz de rotas, menu, painel, recusa, log
├── test_papeis_migracao.py    # contas/0004_papeis
└── test_lancar_saidas.py      # disparo recusa sem a permissão
```

**Structure Decision**: o monólito Django de sempre. O controle de acesso fica todo em `contas`
(que já tem o da spec 008), e os outros apps só leem `contas.acesso` ou o `{{ perms }}`.

## Ordem de implementação sugerida

1. Permissões, grupos e a migration que se verifica (com o teste dela).
2. `contas.acesso` (regras puras e tabela) com testes unitários.
3. Middleware, página de recusa e log; fixture e helper dos testes; suíte inteira verde.
4. Menu, painel e detalhe.
5. Disparo do lançamento.
6. `CLAUDE.md` e o quickstart rodado à mão.

## Complexity Tracking

Sem violações da constituição a justificar.
