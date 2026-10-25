---

description: "Tarefas da funcionalidade 006: reposição de peças das viaturas das equipes de manutenção"
---

# Tasks: Reposição de peças das viaturas das equipes de manutenção

**Input**: documentos de design em `specs/006-reposicao-pecas-viaturas/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **incluídos**. A constituição (Princípio V) exige teste automatizado para toda mudança de comportamento. Os testes rodam contra MariaDB/MySQL, sem navegador; os de JavaScript só conferem o texto do arquivo, então o diálogo da folha é conferido à mão (T041).

**Organization**: tarefas agrupadas por história (US1 a US3), na ordem de prioridade da spec. Destinos (FR-007, FR-008, FR-008a) e número da ocorrência (FR-002a) fazem parte do envio do pedido e ficam na US1.

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec; Setup, Foundational e Polish não têm
- Comandos: `uv run pytest <arquivo>`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`. **Banco de desenvolvimento apenas; nada de lançamento no SCPI.**

## Regras gerais para todas as tarefas

- Nomes de código, textos e commits em pt-BR; textos ao usuário **exatamente** como em [contracts/mensagens.md](contracts/mensagens.md) e [contracts/folha.md](contracts/folha.md).
- `pedidos/servicos.py` continua o único lugar que grava pedidos; robô do SCPI, `LinhaSaida` e lançamento não mudam.
- Migrations **novas** e aditivas; nunca regenerar `0001`/`0002`.
- Nome interno `VIATURAS`/`viaturas`, nunca "reposição" (o catálogo já tem `ParametroReposicao`, research R1).
- Teste primeiro: escrever o teste da tarefa, vê-lo falhar, implementar.
- Código Python investigado e editado com o Serena (CLAUDE.md); UI com as skills `clean-design`, `ui-ux-pro-max` e `frontend-design` e o `docs/DESIGN.md`.

---

## Phase 1: Setup

**Purpose**: linha de base

- [X] T001 Confirmar que a branch `claude/reposicao-pecas-viaturas` só tem `specs/006-reposicao-pecas-viaturas/` além de `develop` e rodar `uv run pytest`; anotar o resultado (passaram/pulados) como linha de base em `specs/006-reposicao-pecas-viaturas/tasks.md` (seção Notas)
- [X] T002 [P] Rodar `uv run ruff check . && uv run ruff format --check .` e `uv run python manage.py makemigrations --check --dry-run`; ambos limpos antes de começar

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Purpose**: modelos, migrations, funções de catálogo e de centros e os campos opcionais do `Fluxo`.

**⚠️ CRÍTICO**: nenhuma história começa antes desta fase terminar.

### Modelos e migrations

- [X] T003 [P] Escrever `tests/test_viaturas_modelos.py`: `PecaViatura` recusa o mesmo material duas vezes (`IntegrityError`); apagar um `Material` com peça é barrado (`ProtectedError`); ordenação por `ordem` e depois `material__nome`; `__str__` é o nome exibido ou o material; `CentroCusto.equipe_manutencao` nasce `False`; `Pedido.Origem.VIATURAS` tem o rótulo "Reposição de peças das viaturas"; `Pedido.ocorrencia` nasce `""`
- [X] T004 Criar `PecaViatura` em `catalogo/models.py`, no molde de `ItemLimpeza`: `material = OneToOneField(Material, on_delete=models.PROTECT, related_name="peca_viatura")`, `nome_exibido = CharField(max_length=255, blank=True)`, `ordem = PositiveIntegerField(default=0)`, `Meta.ordering = ["ordem", "material__nome"]`, `verbose_name = "peça das viaturas"`, `verbose_name_plural = "peças das viaturas"`, `__str__` com `nome_exibido or str(material)`; e acrescentar a `CentroCusto` o campo `equipe_manutencao = BooleanField("equipe de manutenção", default=False)` (data-model.md)
- [X] T005 Gerar a migration **nova** `catalogo/migrations/0003_pecas_viaturas.py` (`makemigrations catalogo --name pecas_viaturas`) e conferir que só cria `PecaViatura` e acrescenta `equipe_manutencao`, sem carga de dados (depende de T004)
- [X] T006 [P] Em `pedidos/models.py`: acrescentar `VIATURAS = "VIATURAS", "Reposição de peças das viaturas"` a `Pedido.Origem` (definir a constante `VIATURAS = "VIATURAS"` em `pedidos/regras.py`, ao lado de `LIMPEZA` e `AB`, e usá-la no `choices`) e o campo `ocorrencia = CharField("nº da ocorrência", max_length=20, blank=True, default="")`; atualizar a docstring de `Pedido` com a origem nova
- [X] T007 Gerar a migration **nova** `pedidos/migrations/0003_viaturas.py` (`makemigrations pedidos --name viaturas`) e conferir que só altera `choices` de `origem` e acrescenta `ocorrencia` com `default=""` (depende de T006)

### Catálogo e centros do formulário

- [X] T008 [P] Escrever `tests/test_viaturas_catalogo.py` (com `tests/cenario.py` ou fixtures locais): `formulario_viaturas()` devolve `None` sem saldo importado e `None` sem peça na lista nem item no AB; com dados, devolve primeiro as peças da lista na ordem, com `nome` = nome exibido quando houver, sem as de material oculto, com a duplicada presente (bloqueada pelo carrinho), e depois os itens de `catalogo_ab()` sem repetir códigos da lista; peça da lista fora do AB (sem saída, da lista de limpeza ou de grupo oculto) aparece; `fracionavel` vem da unidade do SCPI; `folha_viaturas()` devolve os códigos visíveis na ordem; `centros_equipe_manutencao()` devolve só centros com alguma linha marcada, um `regras.Centro` por descrição, **sem placa**, e `[]` sem nenhum marcado
- [X] T009 Implementar em `catalogo/catalogos.py` `formulario_viaturas()`, `folha_viaturas()` e `centros_equipe_manutencao()` conforme research R3 e R6 (reusar `_item`, `unidades_fracionaveis`, `saldo_importado` e `catalogo_ab`; sem cache; a lista lida numa consulta com `select_related("material")`) (depende de T005, T008)
- [X] T010 Acrescentar a `Fluxo` em `pedidos/fluxos.py` os campos opcionais `folha: Callable[[], list[str]] | None = None`, `centros: Callable[[], list[Centro]] | None = None` e `pede_ocorrencia: bool = False`, com comentário curto de cada um (contracts/configuracao-fluxo.md); estender `tests/test_fluxo_configuravel.py` com um teste de que os padrões não mudam nada nos fluxos `limpeza`, `ab` e `avulsa`
- [X] T011 Criar `centros_do_fluxo(fluxo)` em `pedidos/servicos.py`: `fluxo.centros()` quando definido, senão `centros()` (depende de T010)

**Checkpoint**: `uv run pytest tests/test_viaturas_modelos.py tests/test_viaturas_catalogo.py tests/test_fluxo_configuravel.py` verde; migrations aplicam e revertem.

---

## Phase 3: User Story 1 - Pedir a reposição a partir da lista de peças comuns (Priority: P1) 🎯 MVP

**Goal**: o encarregado abre o formulário de viaturas, preenche a folha, escolhe o centro da equipe, informa (ou não) o número da ocorrência e envia; o almoxarifado vê e atende o pedido como os outros.

**Independent Test**: com a lista cadastrada, saldo importado e um centro marcado, abrir `/pedido/viaturas/`, preencher duas linhas da folha, informar nome e destino e enviar; o pedido aparece no painel como "Reposição de peças das viaturas" (quickstart §4 e §5).

### Testes da US1

- [X] T012 [P] [US1] Escrever `tests/test_viaturas_folha.py` para `carrinho.aplicar_folha` (pura): linha preenchida entra; substitui a quantidade de quem já está no pedido (não soma); vazio e "0" tiram do pedido; código fora da folha ou do catálogo é ignorado; "2,5" em `UN`, quantidade ilegível e acima do estoque geram erro na linha com os textos de `texto_erro_quantidade` e `texto_acima_do_estoque`; **tudo ou nada**: com um erro, nenhuma linha muda e `erros_folha` tem um texto por código; passar de `PEDIDOS_MAX_ITENS` (40) é recusado com "O pedido pode ter no máximo 40 materiais."; peça bloqueada (sem estoque, duplicada) não entra; os itens da busca que já estão no pedido ficam intactos
- [X] T013 [P] [US1] Escrever `tests/test_viaturas_ocorrencia.py` (regras puras e serviço): `MAX_OCORRENCIA == 20`; 20 caracteres aceitos, 21 recusados com "Nº da ocorrência: no máximo 20 caracteres." e `campo="ocorrencia"`; espaços nas pontas não contam; `cabecalho_enviado` de origem pública inclui a ocorrência; reenvio com a mesma ocorrência confirma (`reenvio=True`) e com outra é `divergente`; `registrar_pedido` grava a ocorrência em `VIATURAS` e grava `""` em `LIMPEZA` mesmo se o envio trouxer uma; pedidos antigos (ocorrência `""`) continuam conferindo no reenvio
- [X] T014 [P] [US1] Escrever `tests/test_viaturas_destinos.py`: a tela de `/pedido/viaturas/` oferece só as descrições dos centros marcados, sem "centro — placa"; enviar outro centro, uma placa ou "centro — placa" é recusado com o texto de destino inválido de hoje; sem centro marcado a tela mostra "Este formulário está indisponível no momento. Avise o almoxarifado." e `registrar_pedido` recusa; limpeza e AB continuam oferecendo todos os centros e "centro — placa"; o atendimento de um pedido de viaturas aceita qualquer centro de custo e sugere o do destino; um centro desmarcado entre abrir o formulário e enviar é recusado como destino inválido, com o carrinho mantido; desmarcar o centro depois do envio não muda o pedido gravado
- [X] T015 [P] [US1] Escrever `tests/test_viaturas_formulario.py` (cliente Django): a página inicial lista "Reposição de peças das viaturas"; o formulário mostra o campo "Nº da ocorrência (opcional)" e o botão "Preencher a lista de peças" (e limpeza/AB não mostram nenhum dos dois); `folha_abrir` devolve as linhas na ordem com nome exibido, "Estoque N · UN", campo preenchido com a quantidade do carrinho e o motivo no lugar do campo das bloqueadas; `folha` sem erro devolve o carrinho com o evento `folha-aplicada` e, com erro, a folha com os valores digitados, erro por linha e o resumo "Corrija N linhas para pôr no pedido."; o envio registra `origem="VIATURAS"`, número `P-` e a ocorrência; o painel mostra a origem e "Ocorrência", o filtro por origem e a busca pela ocorrência acham o pedido; detalhe e recibo mostram "Nº da ocorrência" só quando preenchida; o item gravado tem o nome exibido e o código; o aviso do Telegram (`texto_aviso`) traz "Reposição de peças das viaturas" e não traz a ocorrência; o limite diário por nome soma os pedidos de viaturas com os de limpeza e AB; com só as peças da lista sem estoque (e o AB com estoque) a folha as mostra bloqueadas e o aviso geral "Nenhum material deste formulário tem estoque agora." **não** aparece
- [X] T015a [P] [US1] Escrever `tests/test_viaturas_atendimento.py` (FR-010, SC-002): um pedido de origem `VIATURAS` é atendido por `confirmar_atendimento` com uma troca e um acréscimo, gera `LinhaSaida` `PENDENTE` com o centro de custo da equipe, entra na fila do robô (`consultas.fila_do_robo`), é editado por `editar_atendimento` (linhas recriadas) e o recibo mostra "Pedido pelo solicitante", "Adicionado pelo almoxarifado" e o nº da ocorrência — sem nenhum ramo próprio de viaturas em `servicos.py`
- [X] T016 [P] [US1] Acrescentar ao teste de texto do JavaScript que já existe (procurar `pedidos.js` em `tests/`) a conferência dos marcadores da folha em `pedidos/static/pedidos/js/pedidos.js`: `data-folha-abrir`, o evento `folha-aplicada`, `showModal`, o retorno do foco ao botão e o anúncio "Lista posta no pedido"

### Implementação da US1

- [X] T017 [US1] Implementar em `pedidos/carrinho.py` o campo `Carrinho.erros_folha: dict[str, str]` (padrão vazio) e `aplicar_folha(linhas, fluxo, catalogo, quantidades) -> Carrinho`, reusando `quantidade`, `acima_do_estoque`, `motivo_bloqueio`, `limite` e `fluxo.max_itens`, sem ORM (research R4, R5; contracts/folha.md) (depende de T012)
- [X] T018 [US1] Em `pedidos/regras.py`: `EnvioPedido.ocorrencia: str = ""`; `MAX_OCORRENCIA = 20`; em `validar_pedido`, o erro de tamanho da ocorrência com `campo="ocorrencia"` e o texto exato de contracts/mensagens.md; `cabecalho_enviado` das origens públicas devolve `(solicitante, destino, obs, ocorrencia)` (depende de T013)
- [X] T019 [US1] Em `pedidos/servicos.py`, `registrar_pedido`: ler os centros com `centros_do_fluxo(fluxo)` (antes da transação, como hoje); gravar `ocorrencia=texto(envio.ocorrencia)` só se `fluxo.pede_ocorrencia`, senão `""`; incluir `anterior.ocorrencia` no cabeçalho gravado da conferência de reenvio (depende de T011, T018)
- [X] T020 [US1] Acrescentar a entrada `"viaturas"` a `FLUXOS` em `pedidos/fluxos.py` com os valores de contracts/configuracao-fluxo.md (`origem=VIATURAS`, `catalogo=formulario_viaturas`, `folha=folha_viaturas`, `centros=centros_equipe_manutencao`, `pede_ocorrencia=True`, exemplos, ícone já existente em `interface/templates/interface/_icone.html`) (depende de T009, T010)
- [X] T021 [US1] Em `pedidos/views/publico.py`: `_contexto` usa `centros_do_fluxo(fluxo)` para `destinos`/`sem_destinos` e passa `fluxo.folha` à página (contagem de peças da folha para a dica do botão); `formulario` lê `ocorrencia` do POST só quando `fluxo.pede_ocorrencia`, a guarda em `campos` e a passa a `EnvioPedido`; `resolver_destino` com os centros do fluxo (depende de T019, T020)
- [X] T022 [US1] Em `pedidos/views/materiais.py`, `_carrinho`: ramo `folha_abrir` (desenha `_folha.html` com as quantidades do carrinho) e ramo `folha` (lê `folha-<código>`, chama `aplicar_folha`; sem erro devolve `_carrinho.html` com o cabeçalho `HX-Trigger: folha-aplicada`; com erro devolve `_folha.html` com os erros e os cabeçalhos `HX-Retarget: #folha-conteudo` e `HX-Reswap: innerHTML`, que o HTMX 4.0.0 vendorizado lê da resposta — conferido em `interface/static/interface/vendor/htmx/htmx-4.0.0.min.js`: `e.hx.retarget`, `e.hx.reswap`, `e.hx.trigger`); só em fluxos com `folha` (os outros respondem como hoje) (depende de T017, T020)
- [X] T023 [US1] Templates: em `pedidos/templates/pedidos/_formulario.html`, o campo "Nº da ocorrência (opcional)" com a dica e o erro por campo no passo "Seus dados" (só com `fluxo.pede_ocorrencia`, `maxlength="20"`), o botão "Preencher a lista de peças" com a dica "N peças, como na folha de papel" e o `<dialog id="folha">`, com um `div#folha-conteudo` dentro (alvo de `folha_abrir` e da resposta com erro), no passo dos materiais (só com `fluxo.folha`); criar `pedidos/templates/pedidos/_folha.html` conforme contracts/folha.md (rótulo por linha, `aria-describedby`/`aria-invalid` nos erros, resumo de erros, "Pôr no pedido", "Fechar") (depende de T021, T022)
- [X] T024 [US1] Em `pedidos/static/pedidos/js/pedidos.js` e `pedidos/static/pedidos/css/pedidos.css`: abrir o diálogo com `showModal` depois do `folha_abrir`, foco na primeira linha, Esc e "Fechar" sem mudar o pedido, foco de volta ao botão; no evento `folha-aplicada`, fechar e anunciar "Lista posta no pedido: N materiais." no `role="status"` do carrinho; na resposta com erro, foco no resumo; tela cheia em largura de celular e painel com rolagem no computador, com os tokens do design system Clean (`docs/DESIGN.md`) (depende de T016, T023)
- [X] T025 [P] [US1] Em `pedidos/telegram.py`: trocar o mapa fixo `FORMULARIOS` por `pedido.get_origem_display()` em `texto_aviso`, sem mudar os textos de limpeza e AB; a ocorrência não entra no aviso (depende de T006)
- [X] T026 [P] [US1] Em `pedidos/consultas.py`: a busca `q` de `pedidos_do_painel` também procura em `ocorrencia` (`icontains`), e o placeholder de `FiltrosPainel.q` vira "Nº, solicitante, recebedor ou ocorrência"; na lista do painel (`pedidos/templates/pedidos/_painel_lista.html`, na célula `col-destino`, abaixo do destino), mostrar "Ocorrência" e o valor quando preenchido (depende de T006)
- [X] T027 [P] [US1] Em `pedidos/templates/pedidos/detalhe.html` e `pedidos/templates/pedidos/_recibo.html`: "Nº da ocorrência" com o valor, só quando preenchido, perto do destino e da observação (depende de T006)
- [X] T028 [US1] Rodar `uv run pytest tests/test_viaturas_folha.py tests/test_viaturas_ocorrencia.py tests/test_viaturas_destinos.py tests/test_viaturas_formulario.py tests/test_viaturas_atendimento.py` e os testes existentes de formulários públicos, painel, atendimento, recibo e Telegram; todos verdes

**Checkpoint**: US1 entregue sozinha (MVP): formulário funcional com folha, destinos restritos e ocorrência.

---

## Phase 4: User Story 2 - Pedir uma peça que não está na lista (Priority: P2)

**Goal**: a busca do mesmo formulário acha os materiais do catálogo AB, sem repetir as peças da lista, e o pedido junta os dois.

**Independent Test**: buscar um material do AB fora da lista, adicioná-lo junto com uma peça posta pela folha e enviar; o pedido registra os dois (quickstart §4.6).

- [X] T029 [P] [US2] Acrescentar a `tests/test_viaturas_formulario.py` os testes da busca: material do AB fora da lista aparece e é adicionado com as regras de quantidade e estoque de sempre; a busca pelo nome exibido acha a peça da lista uma só vez (SC-004); material fora da lista e do AB não aparece; adicionar pela busca uma peça que já está no pedido soma, e a folha reaberta mostra a soma; um pedido com peças da folha e da busca é registrado com todos os itens, sem distinção de origem
- [X] T030 [US2] Rodar os testes de T029; se algum falhar, corrigir só em `catalogo/catalogos.py` (`formulario_viaturas`) ou em `pedidos/fluxos.py` (`exemplo_busca`), sem mudar `fluxos.buscar` nem o carrinho (depende de T029)

**Checkpoint**: US1 e US2 funcionam juntas e cada uma passa nos seus testes.

---

## Phase 5: User Story 3 - Manter a lista de peças comuns (Priority: P2)

**Goal**: o almoxarifado mantém a lista e a marca dos centros no admin, e a saúde do catálogo mostra o formulário.

**Independent Test**: incluir uma peça na lista e retirar outra no admin; no próximo acesso a folha mostra a incluída e não a retirada; a saúde mostra a contagem (quickstart §2 e §3).

- [X] T031 [P] [US3] Escrever `tests/test_viaturas_admin.py`: o admin de "Peças das viaturas" lista, inclui (autocomplete de material), edita a ordem na lista e recusa material repetido com mensagem; o admin de centros de custo mostra, filtra e edita na lista "Equipe de manutenção"; incluir, retirar e reordenar valem no próximo `folha_abrir` sem reiniciar nada (SC-003)
- [X] T032 [P] [US3] Acrescentar a `tests/test_saude.py`: linha ok "Formulário de reposição de peças das viaturas: N peças na lista e M materiais do AB."; erro sem centro marcado e erro sem nada a oferecer, com os textos de contracts/mensagens.md; aviso "Peças das viaturas ocultas no SCPI (não aparecem): …"; texto de "sem saldo" generalizado; `situacao_do_catalogo().viaturas` com o número de peças visíveis; atualizar o teste existente que conferia o texto antigo de "sem saldo"
- [X] T033 [US3] Em `catalogo/admin.py`: `PecaViaturaAdmin` no molde de `ItemLimpezaAdmin` (`autocomplete_fields = ["material"]`, `list_display = ["material", "nome_exibido", "ordem"]`, `list_editable = ["ordem"]`, `search_fields = ["material__codigo", "material__nome", "nome_exibido"]`); em `CentroCustoAdmin`, `equipe_manutencao` em `list_display`, `list_editable` e `list_filter` (depende de T031)
- [X] T034 [US3] Em `catalogo/saude.py`: bloco do formulário de viaturas em `_demais` (ok, erros de indisponibilidade com o motivo e aviso das peças ocultas, textos de contracts/mensagens.md); texto de "sem saldo" generalizado; `Situacao.viaturas: int` preenchido em `situacao_do_catalogo` (depende de T032)
- [X] T035 [US3] Mostrar o número de peças do formulário de viaturas na visão geral de Automações, ao lado de limpeza e AB, no parcial `catalogo/templates/catalogo/_situacao.html` (depende de T034)

**Checkpoint**: as três histórias funcionam e passam nos seus testes.

---

## Phase 6: Polish & Cross-Cutting

- [X] T036 Atualizar `CLAUDE.md`: o formulário "Reposição de peças das viaturas" (`FLUXOS["viaturas"]`, origem `VIATURAS`), `PecaViatura`, `CentroCusto.equipe_manutencao`, `Pedido.ocorrencia`, os campos opcionais `folha`/`centros`/`pede_ocorrencia` do `Fluxo`, a folha em diálogo (`_folha.html`, `aplicar_folha`, tudo ou nada) e o rótulo do Telegram pela origem
- [X] T037 [P] Acrescentar a `specs/005-consistencia-formularios-publicos/contracts/configuracao-fluxo.md` uma nota curta apontando para os campos opcionais novos em `specs/006-reposicao-pecas-viaturas/contracts/configuracao-fluxo.md`
- [X] T038 Rodar os portões: `uv run pytest` (comparar com a linha de base de T001), `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run` e `DEBUG=0 uv run python manage.py check --deploy --fail-level WARNING` (com as variáveis exigidas pelo `.env` de desenvolvimento)
- [X] T039 Conferir que `uv run python manage.py migrate catalogo 0002` e `migrate pedidos 0002` revertem as migrations novas sem erro no banco de desenvolvimento e reaplicá-las
- [X] T040 Revisar a interface da folha e do campo de ocorrência com as skills `clean-design` (e `docs/DESIGN.md`), `ui-ux-pro-max` e `frontend-design` (screenshot em 375 px e no computador), corrigindo só o que contrariar o design system
- [X] T041 Executar à mão o [quickstart.md](quickstart.md) §2 a §6 no navegador (375 px e computador, teclado incluído) e registrar o que foi conferido e o que não foi nas Notas deste arquivo

---

## Dependencies & Execution Order

- **Setup (T001–T002)** → **Foundational (T003–T011)** → histórias.
- **US1 (T012–T028)** depende só da Foundational. É o MVP.
- **US2 (T029–T030)** depende da Foundational; usa o envio da US1 para o teste do pedido misto (T029 depois de T021).
- **US3 (T031–T035)** depende da Foundational (modelos, `formulario_viaturas`); `folha_abrir` no teste de T031 depende de T022.
- **Polish (T036–T041)** depois das histórias.

Dentro da Foundational: T004 → T005 → T009; T006 → T007; T008 antes de T009; T010 → T011.
Dentro da US1: testes (T012–T016, com T015a) primeiro; T017 e T018 em paralelo; T019 → T021 → T023 → T024; T020 antes de T021/T022; T025, T026, T027 em paralelo depois de T006.

## Parallel Example: User Story 1

```text
# Testes, juntos (arquivos diferentes):
T012 tests/test_viaturas_folha.py
T013 tests/test_viaturas_ocorrencia.py
T014 tests/test_viaturas_destinos.py
T015 tests/test_viaturas_formulario.py
T015a tests/test_viaturas_atendimento.py
T016 teste de texto do pedidos.js

# Depois dos modelos, juntos:
T025 pedidos/telegram.py
T026 pedidos/consultas.py (+ template do painel)
T027 detalhe.html e _recibo.html
```

## Implementation Strategy

1. **MVP**: Setup + Foundational + US1. Para aqui, roda o quickstart §4 e §5 e decide.
2. **Incremento**: US2 (praticamente só testes, a busca já é a de sempre).
3. **Incremento**: US3 (admin e saúde); sem ela a lista só se mantém pelo shell, então ela entra antes da implantação.
4. Polish e PR para `develop`. A carga real da lista e a marca dos centros são feitas pelo almoxarifado depois da implantação.

## Notas

- Linha de base (T001): `uv run pytest` com 1410 passaram e 1 pulado; ruff e `makemigrations --check` limpos.
- Conferência manual (T041), 2026-10-22, banco local com dados reais e uma lista de 5 peças semeada
  (desfeita depois): em 375 px e no computador, a folha abre com o foco na primeira linha, recusa
  "1,5" em peça contada com o erro na linha e o resumo focado, mantém o que foi digitado (corrigido o
  "settle" do HTMX, ver contracts/folha.md), aplica com Enter, fecha, anuncia "Lista posta no pedido: 2
  materiais." e devolve o foco ao botão; o envio registrou o pedido com 2,5 M e 1 UN, destino só
  com o centro marcado, placeholder "Centro de custo da equipe" e o campo de ocorrência. **Não
  conferido no navegador**: painel, detalhe e recibo logados (cobertos pelos testes automatizados),
  leitor de tela e Esc com teclado físico. O `.env` local tem Telegram configurado: o envio tentou o
  aviso real, que falhou (o pedido ficou gravado, como previsto).
- T040 (2026-10-22): revisão com `clean-design` + `docs/DESIGN.md`, `ui-ux-pro-max` (busca "keyboard
  focus modal", "error summary validation", "numeric input keyboard mobile") e `frontend-design`, com
  screenshot em 375 px e no computador. Corrigido: vocabulário `folha-*` e ícones usados registrados
  no `DESIGN.md`; resumo de erros da folha com a classe `resumo-erros` e um link por linha; a rolagem
  da folha desconta a barra presa embaixo (o foco não fica escondido, WCAG 2.4.11); botões da barra
  sem quebra no celular; dica com plural; ocorrência em `.mono` na lista do painel; anúncio com a
  palavra do botão ("Lista posta no pedido: N materiais.").
