---

description: "Tarefas da funcionalidade 009: configuração das opções por formulário (centros de custo e materiais)"
---

# Tasks: Configuração das opções por formulário

**Input**: documentos de design em `specs/009-configuracao-formularios/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **incluídos**. A constituição (Princípio V) exige teste automatizado para toda mudança de comportamento. Os testes rodam contra MariaDB/MySQL, sem navegador, nunca abrem o SCPI.

**Organization**: tarefas agrupadas por história (US1 a US6), na ordem de prioridade da spec. O que todas usam (modelos, migration, regra pura, integração nos catálogos e nos destinos, adaptação dos testes antigos) fica no Foundational.

**Entrega**: o corte mínimo publicável é Foundational + US1 + US2 + US6 (a tela só deve ir a produção com a permissão de gravação funcionando). US3, US4 e US5 podem vir em seguida; a US5 é a que dá sentido ao estado inativo, então a **coluna `ativo` e o filtro de inativos** entram no Foundational e a tela de inativar na US5.

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec; Setup, Foundational e Polish não têm
- Comandos: `uv run pytest <arquivo>`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`. **Banco de desenvolvimento apenas; nada de lançamento no SCPI; nada de `docker compose` na produção; nenhum `migrate` no banco real.**

## Regras gerais para todas as tarefas

- Nomes de código, textos e commits em pt-BR; textos ao usuário em português correto, em linguagem do almoxarifado.
- `pedidos/servicos.py` continua o único lugar que grava pedidos; a configuração grava só em `catalogo`. Robô do SCPI, `LinhaSaida`, estoque e cadastro de materiais não mudam.
- Migration **nova** e aditiva (`catalogo/0006`, o esquema, e `0007`, os dados, separadas após a revisão: o DDL do MySQL não é transacional); nunca regenerar as existentes, nem `migrate catalogo zero`.
- Nenhuma condição por nome de formulário no núcleo (`carrinho.py`, `regras.py`, `views/materiais.py`, `views/publico.py`): a única tabela por origem é o modo de destino em `catalogo/catalogos.py` ([configuracao-fluxo.md](contracts/configuracao-fluxo.md)).
- Teste primeiro: escrever o teste da tarefa, vê-lo falhar, implementar.
- Código Python investigado e editado com o Serena (CLAUDE.md); templates, JS e CSS com Read/Edit.
- Os testes antigos adaptados **não podem ser enfraquecidos**: o que verificavam continua verificado, com a configuração nova no lugar das marcas antigas.
- Sem JavaScript novo, sem CDN, sem npm (Constituição VI).

---

## Phase 1: Setup

**Purpose**: linha de base e a cópia congelada da regra antiga, que só existe antes de a regra mudar.

- [x] T001 Conferir o ponto de partida: na branch `claude/configuracao-formularios`, rodar `uv run pytest` e `uv run python manage.py makemigrations --check --dry-run` e registrar que a suíte inteira passa antes de qualquer mudança (linha de base de FR-040 e SC-009) e **medir, no banco de desenvolvimento, o tempo de abertura de cada um dos cinco formulários públicos** (média de 10 aberturas por `Client`), gravando os números no `plan.md` (seção "Medições"): é a linha de base de SC-010
- [x] T002 [P] Criar `tests/regra_antiga.py`: cópia **congelada** das funções de hoje que a feature vai trocar, `centros_equipe_manutencao`, `centros_oficina`, o `centros()` de todas as linhas, `catalogo_oficina` e `catalogo_epis` com o ramo dos avulsos (`MaterialOficina`, `MaterialEpi`), copiadas de `catalogo/catalogos.py` e `pedidos/servicos.py` no commit atual; é a referência de SC-001 e da verificação da migração (T012). Comentário no topo: "não editar; é a regra antes da spec 009"
- [x] T003 [P] Criar `tests/config_cenario.py` com os auxiliares dos testes novos: `criar_centro(descricao, codigo, placa=None, *, formularios=(), ativo=True)` (cria a linha e as `CentroFormulario`), `habilitar(centros, *formularios)`, `material(codigo, nome, grupo="", estoque=10, oculto=False)`, `excecao(formulario, material, habilitado)`, os usuários (superusuário, staff com cada permissão, comum, Segurança do Trabalho) e `enviar_pedido(origem, ...)` pelo `registrar_pedido`, no modelo de `tests/epis_cenario.py`

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Purpose**: modelos, migration com a transcrição verificada, regra pura, os catálogos e os destinos lendo a configuração, e os testes antigos no lugar. Nenhuma tela.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

### Modelos e migration

- [x] T004 [P] Escrever `tests/test_config_modelos.py`: `Formulario` tem exatamente `LIMPEZA`, `AB`, `VIATURAS`, `OFICINA`, `EPIS` (sem `AVULSA`); `CentroCusto.ativo` nasce `True`; `CentroFormulario` única por (`centro`, `formulario`) (`centro_unico_no_formulario`) e some com o centro (`CASCADE`); `ExcecaoMaterial` única por (`material`, `formulario`) (`excecao_unica_no_material_e_formulario`) e `PROTECT` do material; `alterado_em` muda ao salvar; `alterado_por` vira nulo ao apagar o usuário (`SET_NULL`)
- [x] T005 Em `catalogo/models.py`, acrescentar (data-model.md, constraints verbatim): `class Formulario(models.TextChoices)` com `LIMPEZA = regras.LIMPEZA`, `AB = regras.AB`, `VIATURAS = regras.VIATURAS`, `OFICINA = regras.OFICINA`, `EPIS = regras.EPIS` (rótulos: "Limpeza, copa e escritório", "Ferramentas, peças e materiais", "Reposição de peças das viaturas", "Oficina mecânica", "Equipamentos de proteção individual (EPIs)"); `CentroCusto.ativo = BooleanField(default=True)`; modelo `CentroFormulario`: `centro` `FK(CentroCusto, CASCADE, related_name="formularios")`, `formulario` `CharField(choices=Formulario.choices)`, `alterado_por` `FK(AUTH_USER_MODEL, SET_NULL, null=True, blank=True, related_name="+")`, `alterado_em` `DateTimeField(auto_now=True)`, `UniqueConstraint(fields=["centro","formulario"], name="centro_unico_no_formulario")`, ordenação `["centro__descricao","centro__placa"]`; modelo `ExcecaoMaterial`: `material` `FK(Material, PROTECT, related_name="excecoes_formulario")`, `formulario` `CharField(choices=Formulario.choices)` com índice, `habilitado` `BooleanField()` (`True` acrescenta, `False` retira), `alterado_por` e `alterado_em` como acima, `UniqueConstraint(fields=["material","formulario"], name="excecao_unica_no_material_e_formulario")`, ordenação `["material__nome"]`; `CentroCusto.equipe_manutencao`: `help_text` dizendo que deixou de valer (spec 009)
- [x] T006 [P] Escrever `tests/test_config_migracao.py` no modelo de `tests/test_migracao_unidades.py` (função de módulo chamada com `apps`): cada regra antiga vira o conjunto certo (todos os centros em limpeza, AB e EPIs; só os de `equipe_manutencao` nas viaturas; na oficina a linha sem placa de "OFICINA MECÂNICA" (a primeira por código) mais toda linha com placa; `MaterialOficina` e `MaterialEpi` viram `ExcecaoMaterial` com `habilitado=True`); a oficina sem o centro e os EPIs sem avulsos viram vazio; repetir a carga não duplica; a **reversão** apaga só o criado e não toca `MaterialOficina`, `MaterialEpi` nem `equipe_manutencao`; a verificação interna **levanta erro** quando a transcrição não reproduz a regra antiga (simulada com uma regra deliberadamente trocada)
- [x] T007 Gerar `catalogo/migrations/0006_configuracao_formularios.py` com `uv run python manage.py makemigrations catalogo -n configuracao_formularios` (esquema aditivo: `ativo`, `CentroFormulario`, `ExcecaoMaterial`, `AlterField` do `help_text`) e acrescentar a operação `RunPython(transcrever, desfazer)` com `transcrever(apps, schema_editor)` como função de módulo e a comparação final, embutida na migration, entre o que a tabela nova produz e a regra antiga (sem importar código do app; `norm_u` escrito inline com `unicodedata`), conforme research.md R6; rodar `tests/test_config_migracao.py` e `tests/test_config_modelos.py`

### Regra pura e catálogos

- [x] T008 [P] Escrever `tests/test_config_estado.py`: a tabela inteira do data-model (as sete linhas de `oculto`, `na_regra`, `excecao`), `origem` e `sem_efeito` de cada uma, `oculto` sempre indisponível
- [x] T009 Criar `catalogo/disponibilidade.py` com a função pura `estado(oculto, na_regra, excecao) -> Estado` (`disponivel`, `origem` em `regra`/`acrescentado`/`retirado`/`fora`, `sem_efeito`) e a docstring com a tabela; sem ORM (Princípio I); rodar T008
- [x] T010 [P] Escrever `tests/test_config_catalogo.py`: `aplicar_excecoes` e os `formulario_*`: acrescentar (aparece, ao fim, em ordem alfabética por nome e código; em oficina e EPIs a lista toda é reordenada por nome e código), retirar (some da base e, nas viaturas, da lista **e** do AB), acrescentar o que a base já traz não duplica, `oculto` nunca é oferecido, `duplicado` aparece bloqueado, `None` quando as exceções esvaziam o formulário, `None` sem saldo importado, formulários independentes (a exceção de um não aparece em outro), o AB continua dinâmico (uma nova saída no período entra sozinha com exceções ao lado), `regra_de_origem` não aplica exceções; oficina e EPIs: a regra é **só os grupos** (o avulso entra só por exceção)
- [x] T011 Em `catalogo/catalogos.py`, implementar (research.md R3, contracts/configuracao-fluxo.md): `regra_de_origem(origem)`, `aplicar_excecoes(origem, base)` (uma consulta das exceções do formulário e uma dos materiais acrescentados visíveis; comparação por `norm_u(codigo)`), trocar os cinco `formulario_*` para `aplicar_excecoes(...) or None` mantendo a condição de `saldo_importado()`, e tirar de `catalogo_oficina` e de `catalogo_epis` o ramo `Q(material_oficina__isnull=False)` / `Q(material_epi__isnull=False)`; rodar T010 e a suíte de catálogos
- [x] T012 [P] Escrever `tests/test_config_centros.py` (parte de destinos): `centros_do_formulario` nos três modos (padrão: cada linha ativa e habilitada com a placa; `sem_placa`: uma por descrição, a primeira por código, sem placa; oficina: linha com placa `so_com_placa=True`, linha sem placa como o centro simples), centro **inativo** fora em todos os modos, habilitado em um formulário não aparece no outro, o resultado de `opcoes_destino` para cada modo, lista vazia quando nada está habilitado
- [x] T013 Em `catalogo/catalogos.py`, implementar `centros_do_formulario(origem)` e a tabela `MODO_DESTINO` (`LIMPEZA`, `AB`, `EPIS`: padrão; `VIATURAS`: sem placa; `OFICINA`: oficina) e remover `centros_equipe_manutencao` e `centros_oficina`; em `pedidos/fluxos.py`, apontar as cinco entradas de `FLUXOS` para `centros=partial(centros_do_formulario, <ORIGEM>)` e deixar a avulsa com `centros=None`; rodar T012

### Adaptação do que já existe

- [x] T014 Trocar em `catalogo/saude.py` os usos de `centros_equipe_manutencao` e `centros_oficina` por `centros_do_formulario(...)` e, nas contagens, o uso direto de `MaterialOficina` e `MaterialEpi` pelo que o catálogo oferece depois das exceções; **as mensagens existentes ficam iguais** (os avisos novos entram na Polish, T045)
- [x] T015 [P] Adaptar `tests/cenario.py`, `tests/viaturas_cenario.py`, `tests/oficina_cenario.py` e `tests/epis_cenario.py` para criar centros já habilitados nos formulários que o cenário usa (pelo auxiliar de T003), de modo que os testes de comportamento antigos não mudem
- [x] T016 [P] Adaptar os testes que usavam as marcas e os cadastros antigos, sem enfraquecê-los: `tests/test_viaturas_destinos.py`, `tests/test_viaturas_catalogo.py`, `tests/test_viaturas_modelos.py` (a marca `equipe_manutencao` passa a ser a habilitação em viaturas), `tests/test_oficina_catalogo.py`, `tests/test_oficina_destinos.py`, `tests/test_oficina_saude.py`, `tests/test_oficina_modelos.py`, `tests/test_epis_catalogo.py`, `tests/test_epis_saude.py` (avulso passa a ser exceção) e `tests/test_fluxo_configuravel.py` (`centros is None` só na avulsa); os de admin ficam para US2 e US5
- [x] T017 Escrever `tests/test_config_equivalencia.py` (SC-001): para cada um dos cinco formulários, o catálogo (códigos e ordem) e os destinos de `opcoes_destino(...)` com a configuração **transcrita pela migration** (usar `transcrever` sobre um cenário com centros de todos os tipos e avulsos) são idênticos aos da regra congelada de `tests/regra_antiga.py`; é a prova de que a integração não mudou o que os formulários oferecem
- [x] T018 Rodar `uv run pytest`, `ruff check`, `ruff format --check` e `makemigrations --check`: a suíte inteira verde (o que ainda não foi adaptado é só admin, US2 e US5) antes de qualquer tela

**Checkpoint**: os cinco formulários oferecem o mesmo que antes, agora lendo a configuração; nenhuma tela ainda.

---

## Phase 3: User Story 1 - Escolher os destinos de cada formulário (Priority: P1) 🎯 MVP

**Goal**: o administrador abre a página, escolhe um formulário e habilita ou desabilita centros; o formulário público muda e o servidor recusa o desabilitado.

**Independent Test**: habilitar "ETA I" só na limpeza: aparece na limpeza e não nos outros; envio direto do AB com esse destino é recusado e nada é gravado.

- [x] T019 [P] [US1] Escrever em `tests/test_config_centros.py` (parte de recusa no backend): `registrar_pedido` recusa, com "Destino ... não está na lista de centros de custo", destino de centro **não habilitado naquele formulário**, de centro **inativo** e de centro habilitado **só em outro** formulário, sem gravar `Pedido`; aceita o habilitado; formulário sem nenhum destino fica indisponível com a mensagem de hoje (`sem_destinos`); desabilitar num formulário não muda o outro; o formulário de viaturas habilitado pela descrição vale para todas as linhas dela
- [x] T020 [P] [US1] Escrever `tests/test_config_telas.py` (parte de centros): `GET /painel/catalogo/formularios/` abre com o primeiro formulário; `?formulario=` inválido volta ao primeiro; a aba Centros lista as linhas agrupadas por descrição, com a marca "neste formulário", o estado global e o texto "inativo"; nas viaturas a marca é da descrição; o `POST catalogo:formularios_centros` habilita e desabilita (idempotente), ignora id inexistente com aviso, volta preservando formulário e aba, e mostra a mensagem do que mudou
- [x] T021 [US1] Em `catalogo/disponibilidade.py`, implementar `habilitar_centros(origem, centros, habilitado, usuario)`: transação; `habilitado` cria só as associações que faltam (`alterado_por`, `alterado_em`), desabilitar apaga as existentes; idempotente; devolve quantas mudaram (contracts/rotas-e-permissoes.md)
- [x] T022 [US1] Em `catalogo/acesso.py` (novo), implementar `pode_alterar_centros(usuario)` (`is_staff` e `catalogo.change_centrocusto`), `pode_alterar_materiais(usuario)` (`is_staff` e `catalogo.change_excecaomaterial`) e o decorador `exige(pode)` que devolve 403 (`PermissionDenied`) a quem não pode, para as views de gravação usarem (FR-029); os testes de permissão completos ficam na US6
- [x] T023 [US1] Em `catalogo/forms.py`, acrescentar o formulário de escolha do formulário (`formulario`, `aba`) e, em `catalogo/views.py`, a view `formularios` (`@login_required`) e a `formularios_centros` (`@login_required`, `@require_POST`, `@exige(pode_alterar_centros)`, PRG com `messages`), com o contexto da aba Centros (linhas agrupadas por descrição, habilitadas por formulário, modo do formulário) e as rotas em `catalogo/urls.py` (`catalogo:formularios`, `catalogo:formularios_centros`)
- [x] T024 [US1] Criar `catalogo/templates/catalogo/formularios.html` (estende `interface/base_almoxarifado.html`; título, seletor de formulário como links, `[data-abas]` com `?aba=`) e `_formularios_centros.html` (tabela por descrição, uma linha por placa, formulário POST com CSRF por ação, selos com texto; controles só para quem `pode_alterar_centros`), reusando as classes de `docs/DESIGN.md`; acrescentar o item "Formulários" (ícone existente) a `ITENS_MENU` em `interface/navegacao.py` para o almoxarifado
- [x] T025 [US1] Rodar `tests/test_config_centros.py` e `tests/test_config_telas.py` e conferir a página no navegador do app (preview), nas larguras de celular, tablet e computador, com as três skills de UI do projeto (CLAUDE.md "Convenções") *(conferida no navegador do app, largura do painel; a revisão com as três skills, nas três larguras, fica na T051)*

**Checkpoint**: US1 funcional e testável sozinha.

---

## Phase 4: User Story 2 - Escolher os materiais de cada formulário (Priority: P1)

**Goal**: acrescentar e retirar um material de um formulário (e restaurar a regra), com o estado e a origem visíveis.

**Independent Test**: retirar um item do AB: some da busca e o envio direto é recusado, e continua nas viaturas; acrescentar um sem saída: aparece; restaurar os dois: volta ao que era.

- [x] T026 [P] [US2] Escrever em `tests/test_config_servicos.py` (parte de `definir_excecao`): `acrescentar` o que a regra não traz cria `habilitado=True`; `acrescentar` o que está retirado apaga a exceção (menor mudança); `retirar` o que a regra traz cria `habilitado=False`; `retirar` o acrescentado apaga; `restaurar` apaga; idempotente; grava `alterado_por` e `alterado_em`; cada formulário é independente; nada toca `Material`, estoque nem pedidos; **duas gravações simultâneas** do mesmo material e formulário (`em_paralelo` de `tests/cenario.py`) deixam **uma** linha e nenhum erro, e a última vence (spec, Edge Cases)
- [x] T027 [P] [US2] Escrever em `tests/test_config_catalogo.py` (parte de backend, FR-020) e `tests/test_config_historico.py`: `registrar_pedido` recusa, com "não está mais no catálogo", material retirado do formulário e aceita o acrescentado; pedido já registrado com material retirado depois continua íntegro (retrato do item), o atendimento, a troca e o acréscimo do almoxarifado não consultam a configuração, pedido de EPI aguardando autorização continua autorizável e atendível, reenvio igual confirma e divergente é recusado depois de a configuração mudar; sem estoque, o material acrescentado aparece bloqueado ("Sem estoque")
- [x] T028 [P] [US2] Escrever em `tests/test_config_telas.py` (parte de materiais): a aba Materiais lista só materiais **visíveis**, com busca por código e nome (sem acento, todas as palavras), filtros de grupo, subgrupo e estado, **50 por página** e página fora da faixa vai à última; cada linha mostra estado e origem com texto; `POST catalogo:formularios_excecao` (`acrescentar`, `retirar`, `restaurar`, `acao` inválida é 400, material inexistente é 404), volta preservando formulário, aba, filtro e página; aviso "código antigo (use o canônico)" ao acrescentar um código de par de/para; exceção "sem efeito" marcada; oculto aparece como oculto
- [x] T029 [US2] Em `catalogo/disponibilidade.py`, implementar `definir_excecao(origem, material, acao, usuario)` (transação, menor mudança pela regra de origem de `regra_de_origem`, idempotente) e a consulta da tela: `materiais_da_tela(origem, filtros)` que devolve o queryset de materiais visíveis filtrado por busca, grupo e subgrupo e, para `estado`, restringe por conjuntos de códigos (efetivos, exceções) calculados uma vez; sem carregar o catálogo todo (FR-014)
- [x] T030 [US2] Em `catalogo/forms.py`, acrescentar `FiltrosMateriais` (`q`, `grupo`, `subgrupo`, `estado`, `pagina`) e, em `catalogo/views.py`, a aba Materiais da view `formularios` (paginador de 50, estado por linha com `estado()` e o conjunto da regra calculado uma vez por requisição) e a view `formularios_excecao` (`@login_required`, `@require_POST`, `@exige(pode_alterar_materiais)`); rota `catalogo:formularios_excecao`
- [x] T031 [US2] Criar `catalogo/templates/catalogo/_formularios_materiais.html` (filtros no padrão de `filtros.js`, `form[data-filtros]`, lista com selos de estado e origem em texto, botão por linha como `<form>` POST com CSRF, paginação) e ligar à aba em `formularios.html`; códigos em `.mono`
- [x] T032 [US2] Tirar `MaterialOficinaAdmin` e `MaterialEpiAdmin` de `catalogo/admin.py` (os modelos e os dados ficam, saem do admin e deixam de valer: FR-023) e adaptar `tests/test_oficina_admin.py` e `tests/test_epis_admin.py`: o que verificavam sobre os avulsos passa a ser a exceção na configuração (`ExcecaoMaterial`), e a lista de grupos continua em `Opcao`
- [x] T033 [US2] Rodar `tests/test_config_servicos.py`, `tests/test_config_catalogo.py`, `tests/test_config_historico.py`, `tests/test_config_telas.py` e conferir a aba no navegador do app (preview) nas três larguras, com as três skills de UI

**Checkpoint**: US1 e US2 funcionam juntas; o corte mínimo (com US6) já é publicável.

---

## Phase 5: User Story 6 - Quem pode ver e quem pode alterar (Priority: P2)

**Goal**: a gravação é recusada no servidor a quem não pode, mesmo com a tela forjada; a Segurança do Trabalho não abre a página.

**Independent Test**: usuário comum e staff sem a permissão enviando direto cada POST de gravação: 403 e nada muda; superusuário passa; Segurança do Trabalho redirecionada.

- [x] T034 [P] [US6] Escrever `tests/test_config_permissoes.py`: anônimo vai ao login em todas as rotas; usuário do almoxarifado comum vê a página e a consulta por material, **sem os controles**, e recebe 403 em cada POST de gravação (`formularios_centros`, `formularios_ativo`, `formularios_excecao`, `formularios_lote`) sem nada mudar; staff **com** `change_centrocusto` só altera centros e com `change_excecaomaterial` só altera materiais (e o contrário dá 403); superusuário passa em todos; a Segurança do Trabalho recebe o redirecionamento do middleware na página e 403 nos POST
- [x] T035 [US6] Conferir que `tests/test_epis_acesso.py` (que percorre todas as rotas nomeadas) segue verde com as rotas novas **fora** de `ROTAS_SEGURANCA_TRABALHO` e, se ele fixar uma lista, acrescentar as rotas novas à lista de "negadas"; confirmar em `interface/navegacao.py` que o item "Formulários" não aparece para a Segurança do Trabalho (`para="almoxarifado"`) e testar em `tests/test_interface.py`
- [x] T036 [US6] Em `catalogo/views.py` e nos templates, garantir que os controles de alteração só aparecem a quem `pode_alterar_centros` / `pode_alterar_materiais` e que a página mostra, a quem só vê, o texto "Somente consulta" com a quem pedir a permissão; rodar `tests/test_config_permissoes.py`

**Checkpoint**: gravação protegida no servidor; **corte mínimo publicável fechado**.

---

## Phase 6: User Story 3 - Alterar vários materiais de uma vez (Priority: P2)

**Goal**: acrescentar ou retirar de um formulário todos os materiais que um filtro alcança, em duas telas, com número exato e confirmação.

**Independent Test**: filtrar um grupo de 20 materiais e "retirar todos" do AB: a prévia diz 20, o resultado diz 20, e só esses 20 mudam, só no AB.

- [x] T037 [P] [US3] Escrever em `tests/test_config_servicos.py` (parte de `aplicar_em_lote`): vale para **todos** os materiais do filtro (mais de uma página), nenhum fora do filtro muda, só no formulário pedido, menor mudança (apaga a exceção quando a regra já dá o resultado), devolve `(mudaram, ja_estavam)`, **atômico** (uma falha no meio, simulada, deixa tudo como estava), repetir o lote não muda mais nada
- [x] T038 [P] [US3] Escrever em `tests/test_config_telas.py` (parte do lote): `GET catalogo:formularios_lote` mostra formulário, ação, **número exato** e a amostra de 10; `POST` com `total` igual aplica e mostra "N mudaram, M já estavam assim"; `total` diferente do atual **recusa e volta à prévia** com o número atual, sem mudar nada; sem filtro algum exige `ciente`; sem `ciente` recusa; ação inválida é 400; `acao` de `retirar` e `acrescentar`; sem permissão, 403 (o GET da prévia é aberto a quem vê)
- [x] T039 [US3] Em `catalogo/disponibilidade.py`, implementar `aplicar_em_lote(origem, materiais, acao, usuario)` (research.md R10: transação, decisão por estado efetivo, `bulk_create(update_conflicts=True)` e `delete` em blocos de 1.000, devolve `(mudaram, ja_estavam)`); rodar T037
- [x] T040 [US3] Em `catalogo/forms.py` (`FormularioLote`: filtros, `acao`, `total`, `ciente`) e `catalogo/views.py` (`formularios_lote`, GET prévia aberta a quem vê, POST com `@exige(pode_alterar_materiais)`), rota `catalogo:formularios_lote`; criar `catalogo/templates/catalogo/_lote_previa.html` e o botão "Alterar todos os resultados" na aba Materiais (só a quem pode); rodar `tests/test_config_telas.py` e conferir no preview (largura de computador e tablet)

**Checkpoint**: US3 funcional sobre US2.

---

## Phase 7: User Story 4 - Saber onde um material aparece (Priority: P2)

**Goal**: pela busca, ver em quais dos cinco formulários o material está e por quê.

**Independent Test**: material por regra no AB, acrescentado à oficina e retirado dos EPIs: a tela mostra os três estados e as origens.

- [x] T041 [P] [US4] Escrever em `tests/test_config_telas.py` (parte da consulta): `GET catalogo:formularios_material` com código existente mostra os **cinco** formulários com "disponível"/"não disponível" e a origem (regra, acrescentado, retirado, fora do formulário); mostra "oculto" e "duplicado" do cadastro; código inexistente é 404; aberto a quem só vê; o link da lista de materiais leva a ela
- [x] T042 [US4] Em `catalogo/disponibilidade.py`, implementar `estados_do_material(material)` (os cinco `Estado`, com as regras de origem calculadas uma vez por requisição) e, em `catalogo/views.py`, a view `formularios_material` (`@login_required`), rota `catalogo:formularios_material`; criar `catalogo/templates/catalogo/formularios_material.html` e o link do código na lista; rodar T041

---

## Phase 8: User Story 5 - Manter os centros de custo (Priority: P2)

**Goal**: criar, editar e **inativar** centros; o inativo some dos formulários públicos e da saída avulsa nova, e atendimento, edição e robô seguem resolvendo.

**Independent Test**: inativar um centro habilitado em três formulários: some dos três; pedido antigo íntegro; atendimento e lote pendente o resolvem; reativar devolve as associações.

- [x] T043 [P] [US5] Escrever `tests/test_config_centro_inativo.py`: o atendimento (`confirmar_atendimento`), a edição do atendimento, a **edição de uma saída avulsa já registrada** e `scpi/requisicoes` (o robô, com lote pendente de centro inativo) resolvem o centro inativo; a saída avulsa **nova** (`registrar_saida_avulsa`) o recusa com "O centro de custo ... não está na lista" e a view `avulsa` não o oferece (`opcoes_saida(so_ativos=True)`), enquanto o atendimento e a edição seguem oferecendo todos; reativar devolve as associações; centro novo nasce ativo e **sem** formulário; pedido antigo com o destino inativado segue exibindo o destino
- [x] T044 [P] [US5] Escrever em `tests/test_config_telas.py` (parte de ativo) e `tests/test_config_admin.py`: `POST catalogo:formularios_ativo` ativa e inativa (idempotente, várias linhas, o texto "inativo" aparece na aba); `CentroCustoAdmin` mostra e edita `ativo`, filtra por `ativo` e **não** mostra mais `equipe_manutencao`; criar centro no admin o deixa sem formulário
- [x] T045 [US5] Em `pedidos/servicos.py`, acrescentar `centros_ativos()` (as linhas com `ativo=True`) e fazer `_validar_saida_avulsa` receber a lista de centros por parâmetro: `registrar_saida_avulsa` passa `centros_ativos()`; `editar_saida_avulsa` passa `centros()` (o atendimento já usa `centros()` em `_validar_atendimento` e não muda); em `pedidos/views/almoxarifado.py`, `opcoes_saida(*, so_ativos=False)` e a view `avulsa` (nova) chama com `so_ativos=True` (research.md R5); rodar T043
- [x] T046 [US5] Em `catalogo/disponibilidade.py`, implementar `definir_ativo(centros, ativo)` (idempotente) e, em `catalogo/views.py`, a view `formularios_ativo` (`@login_required`, `@require_POST`, `@exige(pode_alterar_centros)`), rota `catalogo:formularios_ativo`; na aba Centros, o botão Inativar/Ativar e o texto "inativo" em cada linha, e o atalho "Criar ou editar centro" para `admin:catalogo_centrocusto_add` / `_change` (só a quem o admin permite)
- [x] T047 [US5] Em `catalogo/admin.py`, `CentroCustoAdmin`: `list_display` com `ativo`, `list_editable` e `list_filter` sem `equipe_manutencao` e com `ativo`, `exclude = ["equipe_manutencao"]`, ajuda do campo `ativo`; rodar T044 e `tests/test_cadastros.py`

---

## Phase 9: Polish & Cross-Cutting Concerns

- [x] T048 [P] Saúde (`catalogo/saude.py`, `catalogo/templates/catalogo/_situacao.html`): avisos novos (formulário sem destino nos **cinco**, formulário **sem material** nos cinco depois das exceções, centro **ativo sem formulário**, exceção **sem efeito**; FR-039), cada um com o texto no padrão dos existentes e a contagem na visão geral de Automações; testes em `tests/test_config_saude.py` (e os existentes de saúde seguem verdes)
- [x] T049 [P] Atualizar `CLAUDE.md` (a nova fonte dos destinos e dos materiais, o que `ativo` faz e não faz, as permissões, `Fluxo.centros`, o fim das marcas antigas), as notas dos contratos de `specs/005-.../contracts/configuracao-fluxo.md`, `specs/006-...`, `specs/007-...` e `specs/008-...` (onde falam em `Fluxo.centros`, `equipe_manutencao` e os avulsos) e `.serena/memories/` se algo ali ficar desatualizado
- [x] T050 Rodar os portões: `uv run pytest` (suíte inteira), `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`, `DEBUG=0 uv run python manage.py check --deploy --fail-level WARNING` (com o ambiente de teste), e registrar o resultado
- [x] T051 Percorrer o [quickstart.md](quickstart.md) no ambiente de desenvolvimento (passos 1 a 15) com o navegador do app e as três skills de UI do projeto (`clean-design` com `docs/DESIGN.md`, `ui-ux-pro-max`, `frontend-design`), nas larguras de celular, tablet e computador, e anotar o que não for possível conferir *(feito no navegador do app em 375 px e em 1100 px, mais o painel de 800 px; a página empilha a tabela no celular. Passos de gravação e de permissão cobertos pelos testes automatizados; o passo 14, Segurança do Trabalho, e a medição com usuários reais ficam para o uso)*
- [x] T052 Medir SC-010 no banco de desenvolvimento (a lista de materiais da configuração e a abertura dos formulários públicos antes e depois) e registrar os números no `plan.md`

---

## Dependencies & Execution Order

- **Setup (T001 a T003)**: sem dependência; **T002 antes de qualquer mudança em `catalogos.py` e `servicos.py`** (é a cópia da regra antiga).
- **Foundational (T004 a T018)**: depende do Setup e **bloqueia** tudo. Dentro dele: T005 antes de T007; T006 antes de T007; T009 não bloqueia T011 (só T029, T039 e T042 consomem `estado`); T011 e T013 antes de T014 a T017; T018 fecha.
- **US1 (T019 a T025)**: depende do Foundational. **US2 (T026 a T033)**: depende do Foundational e usa a página de US1 (T023, T024): começa depois de T024.
- **US6 (T034 a T036)**: depende de T022 e T023; deve fechar **antes de publicar** qualquer gravação.
- **US3 (T037 a T040)**: depende de US2 (T029, T030). **US4 (T041, T042)**: depende de T029. **US5 (T043 a T047)**: depende do Foundational; T046 depende de T023/T024.
- **Polish (T048 a T052)**: depois das histórias desejadas.

### Parallel Opportunities

```text
Setup:        T002, T003
Foundational: T004, T006, T008, T010, T012  (testes, arquivos diferentes)
              depois T009 e T011 e T013 (arquivos diferentes), T014, T015, T016
US1:          T019, T020 em paralelo; T021, T022 em paralelo; depois T023, T024
US2:          T026, T027, T028 em paralelo
US3/US4/US5:  podem andar em paralelo entre si depois de US2 (arquivos diferentes: disponibilidade.py é
              compartilhado, então as funções entram em tarefas separadas e sequenciais)
Polish:       T048, T049
```

---

## Implementation Strategy

### MVP First

1. Setup e Foundational (T001 a T018): nada visível, mas os cinco formulários já leem a configuração com o mesmo resultado de antes (T017).
2. US1: o administrador escolhe os destinos (a parte de menor risco).
3. US2 + US6: os materiais e a permissão de gravação. **Só aqui há algo publicável.**
4. US5 (inativar), US3 (lote) e US4 (onde aparece) em seguida.
5. Polish.

### Incremental Delivery

Cada fase termina com `uv run pytest` verde da fase e dos testes existentes. Um PR por entrega publicável (`claude/configuracao-formularios` → `develop`); o merge e qualquer ação de produção são do usuário (CLAUDE.md).

### Parar e perguntar

Se, na implementação, aparecer decisão operacional não coberta (por exemplo, o texto de uma mensagem, o tamanho da amostra do lote, o que a tela mostra a quem não pode alterar, ou um dado de produção que a migração não consiga transcrever), **parar e perguntar** ao usuário em vez de presumir.

---

## Cobertura dos requisitos

| Requisitos | Tarefas |
|------------|---------|
| FR-001, FR-002, FR-003, FR-004 | T019, T020, T023, T024, T043 |
| FR-005, FR-006, FR-007, FR-007a | T005, T012, T013, T019, T020, T021, T024 |
| FR-008, FR-009, FR-010, FR-010a, FR-011 | T005, T012, T013, T019, T043, T044, T045, T046, T047 |
| FR-012, FR-013 | T019, T043, T045 |
| FR-014 a FR-018 | T008, T009, T010, T011, T028, T029, T030, T031 |
| FR-019, FR-020 | T010, T027 |
| FR-021, FR-022, FR-023, FR-023a | T010, T011, T032, T041, T042 |
| FR-024 a FR-027 | T037 a T040 |
| FR-028 a FR-032 | T022, T034, T035, T036, T005 (quem e quando) |
| FR-033 a FR-035 | T027, T043 |
| FR-036, FR-037, FR-038 | T006, T007, T017 |
| FR-039 | T048 |
| FR-040 | T001, T016, T018, T050 |
| FR-041 | T024, T031, T036, T051 |
| SC-001 | T017 |
| SC-002, SC-003 | T051 (medição manual) |
| SC-004, SC-005 | T019, T027 |
| SC-006 | T027, T043 |
| SC-007 | T034 |
| SC-008 | T041 |
| SC-009 | T001, T018, T050 |
| SC-010 | T052 |

## Phase 10: Convergence

**Purpose**: o que o `/speckit-converge` achou entre o código e a spec, o plano e as tarefas (2026-10-23). O que está construído e conferido por teste não aparece aqui; sobraram quatro lacunas parciais.

- [x] T053 Mostrar, na aba Centros de custo (`catalogo/templates/catalogo/_formularios_centros.html`, `catalogo/views_formularios.py`), em **quais outros formulários** cada linha de centro é destino (selos em texto, uma consulta só para a página: `CentroFormulario` das linhas listadas), com teste em `tests/test_config_telas.py`, per FR-005 e US1 (partial)
- [x] T054 Acrescentar à aba Centros de custo o atalho **"Criar centro" e "Editar" no admin** (`admin:catalogo_centrocusto_add` e `_change`), só a quem o admin permite (`has_perm`), com teste em `tests/test_config_telas.py`, per FR-009 e T046 (partial)
- [x] T055 Cobrir com teste (`tests/test_config_catalogo.py`) que **retirar uma peça das viaturas a tira da folha** (`carrinho.pecas_da_folha` sobre o catálogo com exceções) e que a peça **acrescentada** fica fora da folha e depois da lista, per FR-023a (partial)
- [x] T056 Fazer a saúde das viaturas (`catalogo/saude.py`, `_viaturas`) contar o catálogo **efetivo** (`catalogo_efetivo`) para dizer "formulário indisponível: nenhum material" quando as exceções esvaziam a lista e o AB, com teste em `tests/test_config_saude.py`, per FR-039 (partial)
