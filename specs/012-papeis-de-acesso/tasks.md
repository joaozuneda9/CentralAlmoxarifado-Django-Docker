---

description: "Tarefas da funcionalidade 012: papéis de acesso na área interna"
---

# Tasks: Papéis de acesso na área interna

**Input**: documentos de design em `specs/012-papeis-de-acesso/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **incluídos**. A constituição (Princípio V) exige teste automatizado para toda mudança de comportamento. Os testes rodam contra MariaDB/MySQL, sem navegador, e nunca abrem o SCPI.

**Organization**: tarefas agrupadas pelas histórias da spec (US1 a US5). O que todas usam (permissões, grupos, tabela de rotas, middleware, página de recusa e a adaptação dos testes antigos) fica no Foundational: sem ele, a suíte da área interna inteira recebe 403.

**Entrega**: o corte mínimo publicável é Foundational + US4 + US1 + US2 (ninguém perde acesso no deploy, Automações fica restringível e o atendimento segue igual). US3 e US5 completam a spec antes do PR; nada vai a produção sem as cinco.

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec; Setup, Foundational e Polish não têm
- Comandos: `uv run pytest <arquivo>`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`. **Banco de desenvolvimento apenas; nada de lançamento no SCPI; nada de `docker compose` na produção; nenhum `migrate` no banco real.**

## Regras gerais para todas as tarefas

- Código Python: investigar com o Serena antes (`find_symbol`, `find_referencing_symbols`), conforme o `CLAUDE.md`.
- Migrations sempre novas (`contas/0003`, `contas/0004`), nunca regeneradas; nomes e codinomes copiados como literais dentro da migration (como em `contas/0002_grupo_seguranca_trabalho.py`).
- Textos de interface e mensagens em pt-BR, no design Clean (`docs/DESIGN.md`); estado nunca só por cor; Sair por POST com CSRF, um só por página.
- A Segurança do Trabalho (spec 008) não muda: `tests/test_epis_acesso.py` tem de continuar verde sem mudança de expectativa.

---

## Phase 1: Setup

**Purpose**: branch e ponto de partida

- [X] T001 (feito na própria `claude/papeis-de-acesso`, specs e código no mesmo PR; suíte de partida: 2324 aprovados, 1 pulado) Criar a branch de implementação a partir de `develop` atualizada (`git switch develop && git pull --ff-only origin develop && git switch -c claude/papeis-de-acesso-impl`, ou seguir na `claude/papeis-de-acesso` se as specs já tiverem sido integradas) e rodar `uv run pytest` para registrar a suíte verde de partida

---

## Phase 2: Foundational (pré-requisitos bloqueantes)

**Purpose**: permissões, grupos, tabela, middleware e página de recusa, mais os testes antigos com papéis

**⚠️ CRITICAL**: nenhuma história começa antes desta fase

### Permissões e grupos

- [X] T002 Acrescentar ao `Meta` de `Usuario` em `contas/models.py` as permissões `("atender_pedidos", "Atender pedidos (painel, atendimento, edição e saída avulsa)")`, `("operar_automacoes", "Operar as automações (SCPI, importações e conferência)")`, `("ver_curva", "Ver a Curva ABC")` e `("ver_formularios", "Ver a configuração dos formulários")`, e gerar `contas/migrations/0003_permissoes.py` com `uv run python manage.py makemigrations contas --name permissoes` (só `AlterModelOptions`)
- [X] T003 Criar `contas/migrations/0004_papeis.py` (depende de `0003_permissoes` e `auth.0012`): `RunPython` que (a) cria as quatro permissões com `get_or_create` sobre o `ContentType` de `contas.usuario` (`app_label="contas"`, `model="usuario"`, criado com `get_or_create` se faltar), porque o `post_migrate` só as cria depois de todas as migrations (research R5); (b) cria os grupos `Atendimento` (com `atender_pedidos`) e `Gestão` (com `operar_automacoes`, `ver_curva`, `ver_formularios`); (c) põe nos dois todo usuário com `is_active=True` que não está no grupo `Segurança do Trabalho`; (d) confere que cada um desses usuários tem as quatro permissões pelos grupos e, senão, levanta `RuntimeError` com as matrículas; reverso `migrations.RunPython.noop`. Literais copiados, sem importar `contas.acesso`

### Regras puras e tabela

- [X] T004 Em `contas/acesso.py`, acrescentar (sem mexer no que é da spec 008): as constantes das quatro permissões e dos nomes dos grupos `Atendimento` e `Gestão`; o `@dataclass(frozen=True) Regra(permissoes: tuple[str, ...], motivo: str, exige_staff: bool = False)`; as categorias `PUBLICA`, `ADMIN` e `SEGURANCA`; a tabela `REGRAS_POR_ROTA` exatamente como em `specs/012-papeis-de-acesso/contracts/tabela-de-rotas.md` (25 rotas com `Regra`, mais as categorias); a função pura `pode(usuario, regra) -> bool` (autenticado, ativo, `is_staff` se `exige_staff`, `usuario.has_perms(regra.permissoes)`); `regra_da_rota(view_name)` que devolve a regra, a categoria ou `None` (namespace `admin` inteiro é `ADMIN`); `pode_abrir(usuario, view_name) -> bool` (rota fora da tabela: só superusuário); `sem_papel(usuario) -> bool` (autenticado, sem nenhuma das quatro permissões e fora da Segurança do Trabalho)
- [X] T005 Em `contas/acesso.py`, `registrar_recusa(request, falta: str) -> None` no logger `logging.getLogger("contas.acesso")`, nível `WARNING`, mensagem exatamente `"Acesso recusado: matricula=%s rota=%s metodo=%s falta=%s"` com `request.user.get_username()`, `request.resolver_match.view_name` (ou `"-"` sem rota), `request.method` e `falta`; nunca o corpo, a query string, cookies ou cabeçalhos (contrato `contracts/recusa.md`)

### Middleware e página de recusa

- [X] T006 Criar `interface/templates/interface/acesso_negado.html` (estende `interface/base_almoxarifado.html`, bloco `voltar` vazio) com os dois casos de `contracts/recusa.md`: `sem_papel` ("Seu usuário ainda não tem acesso" e o texto do administrador, só Sair) e o motivo da regra ("Sem acesso a esta página", o `motivo`, "Voltar ao painel" só se `pode_abrir(usuario, "pedidos:painel")`, e Sair); e `interface/templates/403.html` com o mesmo visual e a mensagem de `exception` para os `PermissionDenied` levantados fora do middleware
- [X] T007 Criar `ExigirPermissao` em `contas/middleware.py` (`process_view`): rota `PUBLICA`, `ADMIN` ou `SEGURANCA` passa; anônimo em rota interna ou fora da tabela segue (`return None`, o `login_required` redireciona) e, se a view não tiver `login_required`, devolve `redirect_to_login`; logado sem `pode(...)` ou em rota fora da tabela sem ser superusuário recebe `TemplateResponse(request, "interface/acesso_negado.html", contexto, status=403)` com `add_never_cache_headers`, depois de `registrar_recusa` com as permissões que faltam (`"is_staff"` incluído quando for o caso) ou `"rota-fora-da-tabela"`
- [X] T008 Registrar `contas.middleware.ExigirPermissao` em `MIDDLEWARE` de `config/settings.py` logo depois de `contas.middleware.RestringirSegurancaTrabalho`, com comentário (spec 012), e acrescentar ao `LOGGING` o logger `contas.acesso` (handlers `console` e `arquivo`, nível `WARNING`, `propagate=False`)

### Testes: helpers e testes antigos

- [X] T009 [P] Mover `rotas_nomeadas()` de `tests/test_epis_acesso.py` para `tests/rotas.py` e importá-la de lá em `tests/test_epis_acesso.py` (sem mudar nenhuma expectativa)
- [X] T010 [P] Criar `tests/papeis.py` com `dar_papeis(usuario, *nomes)` (padrão: `"Atendimento"` e `"Gestão"`; busca os grupos criados pela migration, `Group.objects.get(name=...)`) e `usuario_com(*nomes, username="12345")`
- [X] T011 Dar os dois papéis à fixture `usuario_logado` em `tests/conftest.py` e ao usuário do almoxarifado de `usuarios_epis` em `tests/epis_cenario.py` (o da Segurança do Trabalho e o anônimo não mudam)
- [X] T012 Rodar `uv run pytest` e, em cada teste que loga (`force_login`/`client.login`) um usuário criado à mão numa rota interna e agora recebe 403, chamar `dar_papeis` logo depois do `create_user` (há 67 criações em 48 arquivos; só mudam as que abrem rota interna). Não afrouxar nenhuma expectativa: um teste que deixa de passar por outro motivo é investigado, não ajustado
- [X] T013 [P] Testes unitários das regras em `tests/test_papeis_regras.py`: `pode` com anônimo, inativo, sem permissão, com permissão, `exige_staff` com e sem `is_staff`, superusuário; `regra_da_rota` para uma rota de cada categoria e para `admin:index`; `pode_abrir` em rota fora da tabela (só superusuário); `sem_papel` com cada papel, com nenhum e com o grupo da Segurança do Trabalho

**Checkpoint**: suíte inteira verde com os papéis; a área interna já nega por padrão.

---

## Phase 3: User Story 4 - Nada muda para ninguém no dia da implantação (Priority: P1) 🎯 primeiro

**Goal**: a migration dá os dois papéis a todos os usuários ativos fora da Segurança do Trabalho e se verifica (FR-015, FR-016)

**Independent Test**: num banco com usuários de antes da mudança, aplicar a `contas/0004` e conferir os grupos de cada usuário; forçar uma falta e ver o erro

### Testes

- [X] T014 [US4] Em `tests/test_papeis_migracao.py`, importar a função de `contas/migrations/0004_papeis.py` com `importlib.import_module("contas.migrations.0004_papeis")` e chamá-la com `django.apps.apps` sobre um cenário com: usuário ativo comum, superusuário ativo, usuário inativo (como o `planilha`), usuário da Segurança do Trabalho e usuário já com um dos grupos. Conferir: os dois primeiros e o último ficam com `Atendimento` e `Gestão` e com as quatro permissões; inativo e Segurança do Trabalho não ganham nada; rodar duas vezes não duplica grupos nem permissões
- [X] T015 [US4] No mesmo arquivo, testar que a verificação do fim levanta `RuntimeError` quando um grupo fica sem uma das permissões (remover a permissão do grupo antes da etapa de conferência, por monkeypatch da função de criação) e que o reverso não apaga grupos

### Implementação

- [X] T016 [US4] Ajustar `contas/migrations/0004_papeis.py` para separar as etapas em funções de módulo (`criar_permissoes`, `criar_grupos`, `dar_papeis`, `conferir`) chamadas por uma função `aplicar(apps, schema_editor)`, o que os testes T014 e T015 usam; rodar `uv run python manage.py migrate contas` no banco de desenvolvimento e conferir no admin

**Checkpoint**: migração verificada; `quickstart.md`, passo 2.

---

## Phase 4: User Story 1 - Só o chefe opera as automações (Priority: P1)

**Goal**: Automações inteira só para `contas.operar_automacoes`, na rota, no menu, no painel e no disparo do lançamento (FR-006, FR-007, FR-012, FR-013)

**Independent Test**: com um usuário só de Atendimento, abrir cada rota de Automações em GET e POST e ver a recusa sem processo iniciado; com Gestão, tudo como antes

### Testes

- [X] T017 [P] [US1] Em `tests/test_papeis_acesso.py`: para cada uma das 7 rotas `automacoes:*` (de `tests/rotas.py`), um usuário só com `Atendimento` recebe 403 em GET e POST com o template `interface/acesso_negado.html` e o motivo "Esta página é de quem opera as automações."; nenhuma `ExecucaoRobo` é criada e o `subprocess.Popen` (monkeypatch) nunca é chamado; com `Gestão` o middleware não recusa
- [X] T018 [P] [US1] Em `tests/test_lancar_saidas.py`: `iniciar_lancamento` com um usuário sem `contas.operar_automacoes` levanta `PermissionDenied` sem criar `ExecucaoRobo`, nos modos simular e lançar; com a permissão, o comportamento atual não muda
- [X] T019 [P] [US1] Em `tests/test_papeis_acesso.py`: o painel de um usuário só com `Atendimento` não tem o cartão do lançamento (`automacoes:lancar` ausente do HTML), nem "Ver automações", nem o link "para conferir"; os avisos de saúde aparecem sem link para Automações; o detalhe de um pedido com lote travado não tem "Resolver em Automações"; com `Gestão`, tudo aparece

### Implementação

- [X] T020 [US1] Em `scpi/disparo.py`, `iniciar_lancamento` começa conferindo `usuario.has_perm("contas.operar_automacoes")`; sem ela (não há `request` ali, então não usa `registrar_recusa`), registra pelo logger `contas.acesso` a linha `Acesso recusado: matricula=<username> rota=scpi.disparo.iniciar_lancamento metodo=- falta=contas.operar_automacoes` e levanta `PermissionDenied("Lançar no SCPI é de quem opera as automações.")` antes de qualquer consulta ou gravação
- [X] T021 [US1] Em `pedidos/views/almoxarifado.py` (`painel`), calcular `lancamento_pendentes`, `lancamento_travados`, `lancamento_em_andamento` e `lancamento_real` só se `request.user.has_perm("contas.operar_automacoes")`
- [X] T022 [US1] Em `pedidos/templates/pedidos/painel.html`, envolver em `{% if perms.contas.operar_automacoes %}` o cartão do lançamento (o link "para conferir" e o formulário de `automacoes:lancar`) e o "Ver automações"; nos avisos de saúde, o link para Automações só com a permissão (o aviso continua)
- [X] T023 [US1] Em `pedidos/templates/pedidos/detalhe.html`, envolver o "Resolver em Automações" em `{% if perms.contas.operar_automacoes %}`

**Checkpoint**: `quickstart.md`, passo 3 (itens 2 e 4).

---

## Phase 5: User Story 2 - Funcionário que atende só vê o que precisa (Priority: P1)

**Goal**: Atendimento abre painel, pedido, recibos, atendimento, edição e saída avulsa; Curva ABC e Formulários ficam com Gestão (FR-001, FR-002, FR-010, FR-012)

**Independent Test**: com um usuário só de Atendimento, atender, imprimir, editar e registrar saída avulsa sem recusa; Curva ABC e Formulários recusados

### Testes

- [X] T024 [P] [US2] Em `tests/test_papeis_acesso.py`, a matriz completa da tabela (contrato, garantias 1 a 4): toda rota de `tests/rotas.py` está numa categoria de `REGRAS_POR_ROTA`; para cada rota com `Regra`, usuário sem a regra recebe 403 em GET e POST e usuário com a regra não recebe 403 do middleware; uma rota de teste fora da tabela (`urlpatterns` de teste com `@override_settings(ROOT_URLCONF=...)`) é negada a quem tem os dois papéis e aberta ao superusuário
- [X] T025 [P] [US2] Em `tests/test_papeis_acesso.py`, o fluxo do Atendimento pelos serviços reais e pelas rotas: registrar um pedido, `pedidos:atender`, `pedidos:marcar_impressos`, `pedidos:editar` (GET e POST) e `pedidos:avulsa` (POST que registra) com um usuário só de `Atendimento`, todos sem 403 e com o resultado de hoje; `catalogo:curva`, `catalogo:formularios` e `catalogo:formularios_material` recusados com "Esta página é da gestão do almoxarifado."
- [X] T026 [P] [US2] Em `tests/test_papeis_acesso.py`, o menu: só `Atendimento` vê "Painel" e "Saída avulsa"; `Atendimento` e `Gestão` veem também "Automações", "Curva ABC" e "Formulários"; "Cadastros" segue o `is_staff`; o menu da Segurança do Trabalho não muda
- [X] T027 [P] [US2] Em `tests/test_config_permissoes.py` (o arquivo de permissões da spec 009), as gravações da página Formulários continuam exigindo `is_staff` mais a permissão do cadastro e agora também `contas.ver_formularios`; as expectativas antigas de recusa continuam

### Implementação

- [X] T028 [US2] Em `interface/navegacao.py`, tirar o `so_equipe` de `ItemMenu` e mostrar o item quando `pode_abrir(usuario, item.rota)` (para `admin:index`, `ADMIN` passa a ser `usuario.is_staff`, como o `so_equipe` de hoje); manter a separação da Segurança do Trabalho (`para`) e o `menu_inicio`
- [X] T029 [US2] Conferir em `catalogo/urls.py` e `catalogo/views_formularios.py` que nomes e métodos batem com a tabela (`formularios_lote`: GET de prévia pela tabela, POST pelo `exige(pode_alterar_materiais)` do corpo) e corrigir `REGRAS_POR_ROTA` em `contas/acesso.py` e `contracts/tabela-de-rotas.md` se algo divergir

**Checkpoint**: `quickstart.md`, passo 3 (itens 1, 3 e 4).

---

## Phase 6: User Story 3 - O chefe dá e tira papéis sem programar (Priority: P2)

**Goal**: papéis pelo admin, valendo na próxima requisição; usuário sem papel vê a página que explica; superusuário passa (FR-003, FR-004, FR-008, FR-009)

**Independent Test**: criar um usuário sem grupo e ver a página "sem acesso"; dar e tirar Atendimento e ver o efeito na próxima requisição

### Testes

- [X] T030 [P] [US3] Em `tests/test_papeis_acesso.py`: usuário sem grupo, ao entrar (`login` com `LOGIN_REDIRECT_URL`), cai no painel e recebe 403 com "Seu usuário ainda não tem acesso", só com o formulário de Sair e sem nenhum pedido no HTML; dar `Atendimento` (sem novo login) e o painel abre; tirar e a próxima ação (POST em `pedidos:atender`) é recusada
- [X] T031 [P] [US3] Em `tests/test_papeis_acesso.py`: superusuário sem grupo abre todas as rotas com `Regra`; superusuário não decide autorização de EPI (a expectativa de `tests/test_epis_acesso.py` e dos testes da spec 008 continua)
- [X] T032 [P] [US3] Em `tests/test_papeis_acesso.py`: requisição do HTMX (`HTTP_HX_REQUEST="true"`) recusada devolve 403 com `Cache-Control` sem cache; a recusa nunca mostra número de pedido nem nome de solicitante

### Implementação

- [X] T033 [US3] Garantir no `ExigirPermissao` (`contas/middleware.py`) e em `interface/templates/interface/acesso_negado.html` o caso `sem_papel` antes do motivo da regra, e no `403.html` o "Voltar ao painel" condicionado a `pode_abrir`; conferir no admin (`contas/admin.py` usa o `UserAdmin`) que os grupos aparecem no formulário do usuário, sem mudança de código se já aparecem

**Checkpoint**: `quickstart.md`, passo 4.

---

## Phase 7: User Story 5 - Saber quem tentou o que não podia (Priority: P3)

**Goal**: toda recusa de acesso vira uma linha no log, nas quatro origens (FR-017, FR-018)

**Independent Test**: provocar uma recusa de cada origem e ver a linha com os campos combinados

### Testes

- [X] T034 [P] [US5] Em `tests/test_papeis_log.py` (com `caplog` no logger `contas.acesso`): uma linha por recusa do `ExigirPermissao` (POST em `automacoes:lancar` sem `Gestão`), do `RestringirSegurancaTrabalho` (POST do grupo numa rota fora da lista; o GET que redireciona não registra), do `exige` da spec 009 (POST em `catalogo:formularios_centros` sem `is_staff`), das views de autorização (usuário fora do grupo em `pedidos:autorizacoes`) e do disparo; cada linha tem `matricula=`, `rota=`, `metodo=` e `falta=` e nunca o número do pedido, o corpo nem nomes; 405 do `require_POST` e 403 de CSRF não registram

### Implementação

- [X] T035 [US5] Chamar `registrar_recusa(request, "grupo:Segurança do Trabalho")` no ramo 403 de `RestringirSegurancaTrabalho.process_view` em `contas/middleware.py` (só nos métodos que não são GET/HEAD)
- [X] T036 [P] [US5] Chamar `registrar_recusa` no `exige` de `catalogo/acesso.py` antes do `PermissionDenied`, com a permissão do cadastro e `is_staff` na `falta`
- [X] T037 [P] [US5] Chamar `registrar_recusa(request, "grupo:Segurança do Trabalho")` antes de cada `PermissionDenied` de `pedidos/views/autorizacao.py`

**Checkpoint**: `quickstart.md`, passo 3, item 5.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T038 [P] Atualizar o `CLAUDE.md` no mesmo PR: em Arquitetura, a nova regra de acesso (permissões `contas.*`, papéis Atendimento e Gestão, `REGRAS_POR_ROTA` com nega por padrão, `ExigirPermissao` depois do da Segurança do Trabalho, `registrar_recusa` e o logger `contas.acesso`, migrations `contas/0003` e `0004`, a fixture `usuario_logado` e `tests/papeis.py`); trocar a frase de `contas/acesso.py` "O sistema não tem papéis" e o docstring de `contas/middleware.py` ("o único lugar que separa")
- [X] T039 [P] Conferir que nenhum template da área interna tem link para rota que o usuário não abre: `grep` por `automacoes:`, `catalogo:curva` e `catalogo:formularios` em `pedidos/templates`, `interface/templates` e `catalogo/templates` fora das páginas já restritas, e condicionar o que sobrar
- [X] T040 Portões: `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run` e `DEBUG=0 uv run python manage.py check --deploy --fail-level WARNING` (com o `.env` de desenvolvimento ajustado só na linha de comando)
- [X] T041 Rodar `specs/012-papeis-de-acesso/quickstart.md` (passos 2 a 4) no servidor de desenvolvimento da porta 8000 (conferir antes se já está no ar e de qual branch), com screenshot do menu e da página de recusa para o PR

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias. T003 depende de T002; T004 a T008 em sequência (mesmos arquivos ou dependentes); T009 e T010 em paralelo depois de T003; T011 depende de T010; T012 depende de T008 e T011; T013 depende de T004
- **US4 (Phase 3)**: depende do Foundational; vem primeiro por ser a garantia do deploy
- **US1, US2 (Phases 4 e 5)**: dependem do Foundational; independentes entre si (arquivos de implementação diferentes; os testes vão no mesmo `tests/test_papeis_acesso.py`, então escreva um de cada vez ou em funções separadas)
- **US3 (Phase 6)**: depende do Foundational; T033 toca `contas/middleware.py` (feito no T007)
- **US5 (Phase 7)**: depende do Foundational e do T020 (disparo)
- **Polish (Phase 8)**: depende de todas

### Within Each User Story

- Testes primeiro, falhando; depois a implementação; checkpoint do quickstart no fim

### Parallel Opportunities

- Foundational: T009 e T010; depois T013 junto do T011
- US1: T017, T018 e T019 (arquivos e funções diferentes); depois T021, T022 e T023 em sequência (o template depende do contexto da view)
- US2: T024 a T027 em paralelo
- US5: T036 e T037 em paralelo depois do T035
- Polish: T038 e T039

## Parallel Example: User Story 1

```text
T017 [US1] matriz das rotas de Automações em tests/test_papeis_acesso.py
T018 [US1] disparo sem permissão em tests/test_lancar_saidas.py
T019 [US1] painel e detalhe sem os atalhos em tests/test_papeis_acesso.py (função separada)
```

## Implementation Strategy

### MVP

1. Setup e Foundational (suíte verde com papéis).
2. US4 (a migração que não tira acesso de ninguém).
3. US1 e US2 (Automações restringível; Atendimento intacto).
4. Validar com o quickstart, passos 2 e 3.

### Entrega completa

5. US3 (página de usuário sem papel; superusuário).
6. US5 (log das quatro origens).
7. Polish e PR para `develop`. A implantação em produção e o ajuste dos papéis no admin são ações separadas, só a pedido do usuário.
