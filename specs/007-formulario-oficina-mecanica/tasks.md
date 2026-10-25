---

description: "Tarefas da funcionalidade 007: formulário da oficina mecânica"
---

# Tasks: Formulário da oficina mecânica

**Input**: documentos de design em `specs/007-formulario-oficina-mecanica/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **incluídos**. A constituição (Princípio V) exige teste automatizado para toda mudança de comportamento. Os testes rodam contra MariaDB/MySQL, sem navegador; não há JavaScript novo.

**Organization**: tarefas agrupadas por história (US1 a US3), na ordem de prioridade da spec. O catálogo pelos grupos e avulsos é a base da US1 e fica no Foundational; a configuração pelo admin e a saúde do catálogo são a US3.

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec; Setup, Foundational e Polish não têm
- Comandos: `uv run pytest <arquivo>`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`. **Banco de desenvolvimento apenas; nada de lançamento no SCPI.**

## Regras gerais para todas as tarefas

- Nomes de código, textos e commits em pt-BR; textos ao usuário **exatamente** como em [contracts/mensagens.md](contracts/mensagens.md).
- `pedidos/servicos.py` continua o único lugar que grava pedidos; robô do SCPI, `LinhaSaida` e lançamento não mudam.
- Migrations **novas** e aditivas; nunca regenerar as existentes.
- Nenhuma condição por nome de fluxo no núcleo (contrato [configuracao-fluxo.md](contracts/configuracao-fluxo.md), regra 1).
- Teste primeiro: escrever o teste da tarefa, vê-lo falhar, implementar.
- Código Python investigado e editado com o Serena (CLAUDE.md).

---

## Phase 1: Setup

- [X] T001 Conferir a base: branch `claude/oficina-mecanica` a partir de `develop` atualizada e `uv run pytest -q` verde antes de qualquer mudança (registrar o número de testes)

---

## Phase 2: Foundational (bloqueia todas as histórias)

- [X] T002 [P] Acrescentar `Opcao.Lista.GRUPO_OFICINA = "GRUPO_OFICINA", "Grupos (oficina)"` e o modelo `MaterialOficina` (`material = OneToOneField(Material, on_delete=PROTECT, related_name="material_oficina")`, `Meta.ordering = ["material__nome"]`, `verbose_name` "material da oficina", `verbose_name_plural` "materiais da oficina", `__str__` do material) em catalogo/models.py, e gerar catalogo/migrations/0004_oficina.py (data-model)
- [X] T003 [P] Acrescentar `OFICINA = "OFICINA"` e `CENTRO_OFICINA = "OFICINA MECÂNICA"` em pedidos/regras.py, usar `CENTRO_OFICINA` no lugar do texto em `resolver_centro_custo`, e `Origem.OFICINA = regras.OFICINA, "Oficina mecânica"` em pedidos/models.py, com pedidos/migrations/0004_oficina.py (só `choices`)
- [X] T004 Teste das migrations e do modelo em tests/test_oficina_modelos.py: `MaterialOficina` recusa o mesmo material duas vezes; `PROTECT` impede apagar o material; a origem `OFICINA` existe com o rótulo "Oficina mecânica"
- [X] T005 [P] Testes do catálogo em tests/test_oficina_catalogo.py: grupo comparado sem acento, maiúsculas e espaços; lista de grupos vazia e sem avulsos → `formulario_oficina()` é `None`; sem saldo importado → `None`; avulso de grupo oculto do AB (`GERAL`) aparece; avulso que também é de grupo da escolha aparece uma vez; oculto não aparece; `duplicado` aparece (bloqueado pela busca); ordem pelo nome; unidade e `fracionavel` do SCPI
- [X] T006 Implementar `grupos_oficina()`, `catalogo_oficina()` e `formulario_oficina()` em catalogo/catalogos.py (research R4: grupos distintos do cadastro visível casados por `_grupo`, depois `Material.objects.filter(oculto=False)` com `grupo__in` dos casados ou `material_oficina` não nulo, `order_by("nome", "codigo")`, convertidos por `_item`); atualizar a docstring do módulo
- [X] T007 [P] Testes puros em tests/test_oficina_destinos.py: `opcoes_destino` com `Centro(..., so_com_placa=True)` não oferece a descrição sozinha e oferece "descrição — placa"; com centros sem a marca, o resultado é igual ao de antes (lista fixa de exemplo); `resolver_destino` reconhece a placa sem hífen e em minúsculas e recusa a descrição sozinha de uma viatura marcada; `centros_oficina` com e sem OFICINA MECÂNICA no cadastro
- [X] T008 Acrescentar `so_com_placa: bool = False` em `regras.Centro` e ajustar `opcoes_destino` em pedidos/regras.py (descrições só dos centros com alguma entrada sem a marca; docstring atualizada); criar `centros_oficina()` em catalogo/catalogos.py (centro sem placa cuja `norm_u(descricao) == norm_u(CENTRO_OFICINA)`, uma vez, e um `Centro(descricao, codigo, placa, so_com_placa=True)` por linha com placa, ordenados pela descrição) (research R5)
- [X] T009 Acrescentar `FLUXOS["oficina"]` em pedidos/fluxos.py com os valores do contrato configuracao-fluxo.md (título "Oficina mecânica", `exemplo_busca` "Ex.: filtro de óleo, pneu", `exemplo_inicio` "Ex.: filtro, óleo, pneu, aditivo, lâmpada", ícone já existente em interface/templates/interface/_icone.html, `catalogo=formulario_oficina`, `centros=centros_oficina`), depois de `viaturas` e antes de `avulsa`

**Checkpoint**: `uv run pytest tests/test_oficina_modelos.py tests/test_oficina_catalogo.py tests/test_oficina_destinos.py tests/test_fluxo_configuravel.py` verde; `makemigrations --check` limpo.

---

## Phase 3: User Story 1 - Pedir materiais da oficina (Priority: P1) 🎯 MVP

**Goal**: o formulário público `/pedido/oficina/` registra pedidos com origem `OFICINA`, que seguem o caminho de sempre.

**Independent Test**: com grupos configurados e saldo importado, abrir o formulário, adicionar dois materiais, informar nome e destino OFICINA MECÂNICA e enviar; o pedido aparece no painel com a origem "Oficina mecânica".

- [X] T010 [US1] Testes em tests/test_oficina_formulario.py (FR-001 a FR-005, FR-010, FR-011): o cartão "Oficina mecânica" com o exemplo do contrato aparece na página inicial; o formulário abre com o exemplo de busca; a busca só devolve materiais da escolha, com os sem estoque bloqueados; indisponível sem catálogo; envio válido registra `Pedido` com origem `OFICINA`; reenvio igual confirma; material retirado da escolha antes do envio é recusado com "não está mais no catálogo"; fração recusada em unidade não fracionável e quantidade acima do estoque recusada, com os textos de hoje (FR-004); o painel filtra pela origem e mostra "Oficina mecânica"; o aviso do Telegram usa o rótulo "Oficina mecânica" (`get_origem_display`); o atendimento confirma e gera `LinhaSaida` como nos outros
- [X] T011 [US1] Rodar T010 e `tests/test_fluxo_configuravel.py` verdes sem nenhuma condição `oficina` fora de pedidos/fluxos.py, catalogo/catalogos.py, catalogo/saude.py e das `choices` (conferir com `grep -rn "oficina" pedidos catalogo --include=*.py`); o que falhar se corrige pelo `Fluxo`

**Checkpoint**: US1 testável de ponta a ponta com destino OFICINA MECÂNICA.

---

## Phase 4: User Story 2 - Indicar a viatura do pedido (Priority: P2)

**Goal**: o destino é OFICINA MECÂNICA ou "centro — placa"; o atendimento já vem com centro e placa.

**Independent Test**: enviar um pedido com destino numa viatura e outro na OFICINA MECÂNICA; o atendimento do primeiro sugere centro e placa, o do segundo só o centro.

- [X] T012 [US2] Testes de integração em tests/test_oficina_destinos.py (FR-006 a FR-009): o formulário lista só OFICINA MECÂNICA e "descrição — placa"; envio com outro centro e com a descrição sozinha da viatura é recusado com a mensagem de destino inválido de hoje, mantendo o pedido; envio com a placa digitada grava "descrição — placa"; formulário sem nenhum destino fica indisponível (`sem_destinos`); atendimento de pedido com viatura sugere `centro_custo` e `placa`, e com OFICINA MECÂNICA só o centro; detalhe e recibo mostram o destino; destinos do formulário AB e das viaturas iguais aos de antes (FR-014)

**Checkpoint**: US1 e US2 verdes.

---

## Phase 5: User Story 3 - Escolher os materiais da oficina (Priority: P2)

**Goal**: o almoxarifado mantém grupos e avulsos no admin, e a saúde do catálogo diz a situação.

**Independent Test**: incluir um grupo e um avulso, retirar outro; no próximo acesso o formulário reflete a mudança e a saúde mostra a contagem.

- [X] T013 [P] [US3] Testes em tests/test_oficina_admin.py (FR-012, FR-012a): `MaterialOficinaAdmin` registrado com autocomplete de material e busca por código e nome; a lista "Grupos (oficina)" é aceita pelo admin de opções; incluir e retirar grupo ou avulso muda o formulário no próximo acesso
- [X] T014 [US3] Registrar `MaterialOficinaAdmin` em catalogo/admin.py (no molde de `PecaViaturaAdmin`, sem `list_editable`), com docstring citando a spec 007
- [X] T015 [P] [US3] Testes da saúde em tests/test_oficina_saude.py (FR-013) com os textos exatos de contracts/mensagens.md: ok com a contagem; erro sem destino; erro sem material; aviso de grupo sem material visível; aviso de avulso oculto; aviso sem o centro OFICINA MECÂNICA com viaturas; nada disso sem saldo importado; `situacao_do_catalogo().oficina` com a contagem
- [X] T016 [US3] Implementar `FORMULARIO_OFICINA` e `_oficina()` em catalogo/saude.py (no molde de `_viaturas`, chamado no mesmo ponto, só com saldo importado) e `Situacao.oficina` preenchido em `situacao_do_catalogo`
- [X] T017 [US3] Mostrar a contagem do formulário da oficina na visão geral em catalogo/templates/catalogo/_situacao.html, ao lado da das viaturas ("1 material"/"N materiais"), coberta por teste da página de Automações em tests/test_oficina_saude.py

**Checkpoint**: todas as histórias verdes.

---

## Phase 6: Polish & Cross-Cutting

- [X] T018 Atualizar CLAUDE.md (formulário da oficina: `FLUXOS["oficina"]`, `GRUPO_OFICINA`, `MaterialOficina`, `Centro.so_com_placa`, `CENTRO_OFICINA`, saúde) e o contrato da interface pública da spec 005 se ele listar os formulários aceitos
- [X] T019 Portões: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`, todos limpos; comparar o número de testes com T001
- [ ] T020 Validação manual pelo quickstart.md §2 a §5 no servidor de desenvolvimento (formulário no celular e no computador, atendimento, simulação sem `LANCAMENTO_REAL`)

- [X] T021 Achado de T020: o placeholder do destino vinha de `fluxo.centros` (texto das equipes). Criar `Fluxo.exemplo_destino` em pedidos/fluxos.py (padrão o texto de hoje; viaturas "Centro de custo da equipe"; oficina "Oficina mecânica ou placa da viatura"), usá-lo em pedidos/templates/pedidos/_formulario.html e testá-lo em tests/test_oficina_formulario.py (research R1)

---

## Dependencies & Execution Order

- T001 → T002, T003 (paralelas) → T004 → T005/T007 (testes, paralelos) → T006, T008 → T009.
- US1 (T010–T011), US2 (T012) e US3 (T013–T017) dependem só do Foundational e podem seguir em
  qualquer ordem; a ordem de prioridade é US1 → US2 → US3.
- Polish depois de tudo.

### Parallel Opportunities

- T002 e T003 (apps diferentes); T005 e T007 (arquivos de teste diferentes); T013 e T015.

## Implementation Strategy

- MVP: Foundational + US1 (pedido com destino OFICINA MECÂNICA). A viatura (US2) já vem com
  `centros_oficina`; a US2 só a prova. Depois, configuração e saúde (US3).
- Commits pequenos por fase, na branch `claude/oficina-mecanica`.
