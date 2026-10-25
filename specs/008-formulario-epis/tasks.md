---

description: "Tarefas da funcionalidade 008: formulário de EPIs com autorização da Segurança do Trabalho"
---

# Tasks: Formulário de EPIs

**Input**: documentos de design em `specs/008-formulario-epis/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **incluídos**. A constituição (Princípio V) exige teste automatizado para toda mudança de comportamento. Os testes rodam contra MariaDB/MySQL, sem navegador, nunca abrem o SCPI nem o Telegram real (o envio é simulado).

**Organization**: tarefas agrupadas por história (US1 a US6), na ordem de prioridade da spec. O que todas as histórias usam (modelos, migrations, constantes, grupo, situação pura) fica no Foundational.

**Entrega**: a US2 (autorizar) e a US6 (acesso restrito) **não podem ir à produção separadas**: sem a US6, o usuário da Segurança do Trabalho enxergaria o painel inteiro. O corte mínimo publicável é US1 + US2 + US3 + US6.

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec; Setup, Foundational e Polish não têm
- Comandos: `uv run pytest <arquivo>`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`. **Banco de desenvolvimento apenas; nada de lançamento no SCPI; nada de `docker compose` na produção.**

## Regras gerais para todas as tarefas

- Nomes de código, textos e commits em pt-BR; textos ao usuário **exatamente** como em [contracts/mensagens.md](contracts/mensagens.md).
- `pedidos/servicos.py` continua o único lugar que grava pedidos; robô do SCPI, `LinhaSaida` e lançamento não mudam.
- Migrations **novas** e aditivas; nunca regenerar as existentes.
- Nenhuma condição por nome de fluxo no núcleo: a condição é `fluxo.exige_autorizacao` ([configuracao-fluxo.md](contracts/configuracao-fluxo.md), regra 1).
- Teste primeiro: escrever o teste da tarefa, vê-lo falhar, implementar.
- Código Python investigado e editado com o Serena (CLAUDE.md); templates, JS e settings com Read/Edit.
- Não alterar `catalogo_oficina` nem os formulários anteriores (FR-032); só acrescentar.

---

## Phase 1: Setup

**Purpose**: base de testes e confirmação do ponto de partida.

- [x] T001 Conferir o ponto de partida: na branch `claude/epis`, rodar `uv run pytest` e `uv run python manage.py makemigrations --check --dry-run` e registrar que a suíte inteira passa antes de qualquer mudança (linha de base de FR-032 e SC-008)
- [x] T002 [P] Criar `tests/epis_cenario.py` com os auxiliares dos testes de EPIs, no modelo de `tests/oficina_cenario.py`: materiais de EPI (grupo `MATERIAL DE SEGURANÇA E EPI` e um avulso de outro grupo, com saldo), `Opcao` `GRUPO_EPI`, o grupo `Segurança do Trabalho` e dois usuários (um do grupo, um do almoxarifado), e uma função que envia um pedido de EPI pelo `registrar_pedido`

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Purpose**: modelos, migrations, constantes, grupo e situação pura. Nada de tela.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

- [x] T003 [P] Escrever `tests/test_epis_modelos.py`: as três combinações válidas de `AutorizacaoPedido` e as inválidas recusadas pelo banco (CheckConstraint), `PROTECT` de `decidido_por` e de `MaterialEpi.material`, `OneToOne` do pedido e do material, `Pedido.Origem.EPIS`
- [x] T004 Em `pedidos/regras.py`, acrescentar as constantes `EPIS = "EPIS"`, `AUTORIZACAO_AGUARDANDO = "AGUARDANDO"`, `AUTORIZACAO_AUTORIZADA = "AUTORIZADO"` e `AUTORIZACAO_RECUSADA = "RECUSADO"`; **não** editar `origem_publica` nem `cabecalho_enviado` (já valem para toda origem que não é `AVULSA`: limite por nome e conferência de reenvio), e conferir isso com um teste novo em `tests/test_regras_pedidos.py`
- [x] T005 Em `pedidos/models.py`, acrescentar `Origem.EPIS = regras.EPIS, "Pedido de EPIs"` e o modelo `AutorizacaoPedido`: `pedido` `OneToOne(Pedido, CASCADE, related_name="autorizacao")`; `situacao` `CharField(max_length=12, choices)` com `AGUARDANDO`/`AUTORIZADO`/`RECUSADO`, padrão `AGUARDANDO`; `decidido_por` `FK(AUTH_USER_MODEL, PROTECT, null=True, blank=True, related_name="+")`; `decidido_em` `DateTimeField(null=True, blank=True)`; `motivo` `CharField(max_length=200, blank=True)`; `CheckConstraint`s: AGUARDANDO ⇒ `decidido_por` e `decidido_em` nulos e `motivo` vazio; AUTORIZADO ⇒ `decidido_por` e `decidido_em` preenchidos e `motivo` vazio; RECUSADO ⇒ `decidido_por` e `decidido_em` preenchidos e `motivo` não vazio. Acrescentar `Pedido.autorizacao_ou_none` (como `atendimento_ou_none`)
- [x] T006 Gerar `pedidos/migrations/0005_epis.py` com `uv run python manage.py makemigrations pedidos -n epis` (só `AlterField` de `choices` e `CreateModel`; conferir que não mexe em dados) e rodar `tests/test_epis_modelos.py`
- [x] T007 [P] Em `catalogo/models.py`, acrescentar `Opcao.Lista.GRUPO_EPI = "GRUPO_EPI", "Grupos (EPIs)"` e o modelo `MaterialEpi` com `material` `OneToOne(Material, PROTECT, related_name="material_epi")`, espelho de `MaterialOficina`; gerar `catalogo/migrations/0005_epis.py` com `makemigrations catalogo -n epis`
- [x] T008 [P] Criar `contas/acesso.py` com `GRUPO_SEGURANCA_TRABALHO = "Segurança do Trabalho"` e `da_seguranca_trabalho(usuario) -> bool` (autenticado e membro do grupo; nunca por `is_staff` nem por permissão), e `contas/migrations/0002_grupo_seguranca_trabalho.py` (migration de dados que cria o `Group` se não existir; reversa sem apagar)
- [x] T009 Em `pedidos/regras.py`, estender `situacao_pedido(origem, atendido, itens, autorizacao=None)`: `AGUARDANDO` devolve `Situacao("aguardando_autorizacao", "Aguardando autorização", ...)`, `RECUSADO` devolve `Situacao("recusado", "Recusado", ...)`, `AUTORIZADO` e `None` seguem a regra de hoje; em `Pedido.situacao` (`pedidos/models.py`) passar `self.autorizacao_ou_none.situacao` quando houver. Primeiro, testes novos em `tests/test_regras_saidas.py` (sem alterar os existentes)
- [x] T010 Em `pedidos/fluxos.py`, acrescentar ao dataclass `Fluxo` o campo `exige_autorizacao: bool = False` (comentado como os outros) e um teste em `tests/test_fluxo_configuravel.py` de que o padrão não muda os fluxos existentes
- [x] T011 Em `config/settings.py`, acrescentar `TELEGRAM_CHAT_ID_SEGURANCA = os.environ.get("TELEGRAM_CHAT_ID_SEGURANCA", "")` e `PEDIDOS_CONSULTA_LIMITE_IP_10_MIN = 20` junto das outras `PEDIDOS_*`

**Checkpoint**: modelos, migrations e situação pura prontos; `uv run pytest tests/test_epis_modelos.py tests/test_regras_saidas.py tests/test_fluxo_configuravel.py` e `makemigrations --check` passam.

---

## Phase 3: User Story 1 - Pedir um EPI (Priority: P1) 🎯 MVP

**Goal**: o servidor envia um pedido de EPI, que fica aguardando autorização; a Segurança do Trabalho é avisada.

**Independent Test**: com a escolha dos EPIs e o saldo, enviar um pedido; a tela de sucesso mostra o número e o aviso de aguardando; o pedido está no painel com a situação "Aguardando autorização" e só o chat da Segurança do Trabalho é avisado.

### Tests for User Story 1

- [x] T012 [P] [US1] Escrever `tests/test_epis_catalogo.py`: grupos (normalização como `_grupo`, vazio), avulsos de outro grupo, material avulso que também é de grupo escolhido aparece uma vez, ocultos fora, duplicado bloqueado, ordem pelo nome, `None` sem saldo importado e sem item visível (FR-004, FR-007)
- [x] T013 [P] [US1] Escrever `tests/test_epis_formulario.py`: o cartão na página inicial; o formulário abre; indisponível com a mensagem dos outros quando sem catálogo; o envio registra origem `EPIS` e cria `AutorizacaoPedido` `AGUARDANDO` na mesma transação; reenvio igual confirma sem duplicar a autorização; a tela de sucesso diz que aguarda a autorização e não sugere entrega; o limite por nome soma os formulários públicos; envio com mais de um destinatário não existe (um nome só) (FR-001 a FR-010)
- [x] T014 [P] [US1] Escrever `tests/test_epis_telegram.py` (lado do registro): ao registrar, só o chat da Segurança do Trabalho recebe e o do almoxarifado não; sem `TELEGRAM_CHAT_ID_SEGURANCA`, nada sai e o pedido segue gravado; falha do envio não desfaz o pedido; reenvio igual não reavisa (FR-026, FR-028)

### Implementation for User Story 1

- [x] T015 [US1] Em `catalogo/catalogos.py`, acrescentar `grupos_epis()`, `catalogo_epis()` (materiais visíveis dos grupos de `GRUPO_EPI` mais os de `MaterialEpi`, uma vez cada, ordem por nome e código) e `formulario_epis()` (`None` sem saldo importado ou sem item), reusando `_grupo`, `_item`, `unidades_fracionaveis` e `saldo_importado`, **sem alterar** as funções da oficina
- [x] T016 [US1] Em `pedidos/telegram.py`, extrair `_enviar(chat_id, texto, url, rotulo_botao)` de `notificar_pedido` (que continua com a assinatura e o resultado de hoje) e acrescentar `notificar_autorizacao_pendente(pedido, url_fila)` com o texto de [mensagens.md](contracts/mensagens.md) (número, nome, até 15 materiais, botão "Abrir fila") usando `settings.TELEGRAM_CHAT_ID_SEGURANCA`
- [x] T017 [US1] Em `pedidos/servicos.py`, em `registrar_pedido`: se `fluxo.exige_autorizacao`, criar `AutorizacaoPedido` (situação `AGUARDANDO`) logo depois do pedido e dos itens, e agendar no `on_commit` o aviso à Segurança do Trabalho **no lugar** do aviso ao almoxarifado; o caminho do reenvio igual (retorno antecipado) continua sem avisar; nenhum outro formulário muda. Em `pedidos/views/publico.py` (`formulario`), passar a `registrar_pedido` a URL absoluta da fila (`pedidos:autorizacoes`) como `url_painel` quando `fluxo.exige_autorizacao`, e a do painel nos demais (o botão do aviso à Segurança do Trabalho é "Abrir fila")
- [x] T018 [US1] Em `pedidos/fluxos.py`, acrescentar `FLUXOS["epis"]` conforme [configuracao-fluxo.md](contracts/configuracao-fluxo.md) (`origem=EPIS`, `catalogo=formulario_epis`, `exige_autorizacao=True`, `icone="escudo"`) e acrescentar o ícone `escudo` (Lucide `shield`, mesmo traço dos outros) em `interface/templates/interface/_icone.html`, porque nenhum ícone atual representa proteção
- [x] T019 [US1] Em `pedidos/templates/pedidos/_sucesso.html` (e no caminho sem HTMX de `pedidos/templates/pedidos/formulario.html`), mostrar para `fluxo.exige_autorizacao` o texto de aguardando autorização e o número em `.mono`; **sem** o link da consulta (a rota só existe na T043; o link entra na T044); os outros formulários não mudam
- [x] T020 [US1] Em `pedidos/templatetags/pedidos_extras.py`, acrescentar `aguardando_autorizacao` e `recusado` ao mapa de selos (`selo-info` e `selo-erro`) e os passos de `proximos_passos` para as duas chaves ("Aguardando a autorização da Segurança do Trabalho; ainda não pode ser atendido."); rodar `tests/test_epis_*.py` da fase

**Checkpoint**: o formulário de EPIs funciona de ponta a ponta até o aguardando; `uv run pytest tests/test_epis_catalogo.py tests/test_epis_formulario.py tests/test_epis_telegram.py` passa.

---

## Phase 4: User Story 2 - Autorizar ou recusar o pedido (Priority: P1)

**Goal**: o usuário da Segurança do Trabalho vê a fila e decide, uma vez, com motivo na recusa; autorizado, o almoxarifado é avisado.

**Independent Test**: com um pedido aguardando e um usuário do grupo, autorizar um pedido e recusar outro com motivo; ficam gravados quem e quando; só a autorização avisa o almoxarifado.

### Tests for User Story 2

- [x] T021 [P] [US2] Escrever `tests/test_epis_autorizacao.py`: autorizar grava `AUTORIZADO`, `decidido_por`, `decidido_em`; recusar com motivo; recusa sem motivo (ou só espaços) não grava; decisão repetida e decisão simultânea (a primeira vale, a segunda devolve `ja_decidida` com quem e quando, nada muda); usuário do almoxarifado e administrador **sem o grupo** negados; só pedido com autorização (outro número dá erro); a decisão não altera itens, destino nem observação; desativar o usuário depois de decidir não muda a decisão gravada nem o nome mostrado; nenhuma decisão é tomada por tempo decorrido (FR-011 a FR-016, FR-021)
- [x] T022 [P] [US2] Estender `tests/test_epis_telegram.py` (lado da decisão): ao autorizar, só o chat do almoxarifado recebe o aviso de pedido novo, uma vez; ao recusar, nenhum dos dois; chat vazio não envia e não desfaz a decisão (FR-027)
- [x] T023 [P] [US2] Escrever o início de `tests/test_epis_decisao_telas.py`: a fila lista só pedidos de EPI aguardando, do mais antigo para o mais novo, e os decididos em leitura; o detalhe de pedido que não é de EPI dá 404; o formulário de decisão avisa que o motivo será visto pelo servidor e pelo almoxarifado; usuário do grupo faz a decisão pela tela e volta ao detalhe com a mensagem (FR-011, FR-012)

### Implementation for User Story 2

- [x] T024 [US2] Em `pedidos/servicos.py`, acrescentar `decidir_autorizacao(numero, decisao, motivo, usuario, *, url_painel="")` (a URL absoluta do painel, que a view `decidir` passa, para o botão "Abrir painel" do aviso ao almoxarifado): transação; confere `da_seguranca_trabalho(usuario)`; trava a `AutorizacaoPedido` do pedido (`select_for_update`); só grava se `AGUARDANDO`; recusa exige `texto(motivo)` não vazio e `<= settings.PEDIDOS_MAX_TEXTO`; devolve `Resposta` com `ja_decidida` (quem e quando) sem alterar nada; ao autorizar, `transaction.on_commit` chama `telegram.notificar_pedido` (o aviso de hoje ao almoxarifado)
- [x] T025 [US2] Em `pedidos/consultas.py`, acrescentar `fila_de_autorizacao()` (aguardando por `criado_em` crescente) e `decididas_da_autorizacao()` (por `decidido_em` decrescente, paginável em 25), sempre só de pedidos com `AutorizacaoPedido`, com `select_related("pedido", "decidido_por")` e `prefetch_related("pedido__itens")` para não consultar por linha
- [x] T026 [US2] Criar `pedidos/views/autorizacao.py` com `autorizacoes` (fila), `autorizacao` (detalhe só de leitura, 404 se o pedido não tem `AutorizacaoPedido`) e `decidir` (POST; campos `decisao` e `motivo`), todas `@login_required` e negando com 403 quem não é `da_seguranca_trabalho` (defesa na própria view, além do middleware da US6)
- [x] T027 [US2] Em `pedidos/urls.py`, registrar `pedidos:autorizacoes` (`painel/autorizacoes/`), `pedidos:autorizacao` (`painel/autorizacoes/<str:numero>/`) e `pedidos:decidir` (`painel/autorizacoes/<str:numero>/decidir/`) conforme [rotas-e-acesso.md](contracts/rotas-e-acesso.md)
- [x] T028 [US2] Criar `pedidos/templates/pedidos/autorizacoes.html` (fila, `base_almoxarifado.html`, bloco `voltar` vazio) e `pedidos/templates/pedidos/autorizacao.html` (detalhe: cabeçalho, materiais e quantidades pedidas só de leitura, a decisão gravada quando houver, e o formulário com os botões Autorizar e Recusar, o campo do motivo e o aviso do FR-012; CSRF; estado nunca só por cor)

**Checkpoint**: a Segurança do Trabalho decide pela tela; `uv run pytest tests/test_epis_autorizacao.py tests/test_epis_decisao_telas.py tests/test_epis_telegram.py` passa.

---

## Phase 5: User Story 3 - Atender só o que foi autorizado (Priority: P1)

**Goal**: o almoxarifado vê todos os pedidos de EPI com a situação de autorização e só atende os autorizados.

**Independent Test**: tentar atender um pedido aguardando e um recusado (negado, por tela e por POST); autorizar e atender (permitido); o painel filtra por autorização.

### Tests for User Story 3

- [x] T029 [P] [US3] Escrever `tests/test_epis_atendimento.py`: `confirmar_atendimento` recusa pedido `AGUARDANDO` e `RECUSADO` sem criar `Atendimento` nem `LinhaSaida`, também com POST forjado na view `atender`; pedido `AUTORIZADO` atende como os outros (recibo, linhas de saída, edição do atendimento iguais); `atendimento_materiais` e `atendimento_adicionar` dão 404 para pedido não autorizado; o robô (`scpi/requisicoes.py`) não vê lote de pedido não autorizado (FR-023, FR-024, SC-002)
- [x] T030 [P] [US3] Escrever `tests/test_epis_painel.py`: a situação pura × a SQL com os estados de autorização; o filtro Situação `aguardando` exclui `AGUARDANDO` e `RECUSADO` de autorização e o atalho "Atender" do painel conta só o atendível; o filtro novo Autorização (aguardando, autorizado, recusado) e a combinação com os outros; a lista mostra "Aguardando autorização" e "Recusado"; sem linha de autorização, nada muda (FR-022, FR-025, FR-032)
- [x] T031 [P] [US3] Estender `tests/test_painel.py` apenas com os casos novos de autorização (os existentes ficam intactos) para a concordância entre `regras.situacao_pedido` e `consultas.filtrar_situacao`

### Implementation for User Story 3

- [x] T032 [US3] Em `pedidos/servicos.py`, em `confirmar_atendimento`: depois de travar o pedido e antes de qualquer gravação, devolver `Resposta(ok=False, mensagem=...)` se o pedido tem `AutorizacaoPedido` com situação diferente de `AUTORIZADO` (texto de [mensagens.md](contracts/mensagens.md)); o caminho do atendimento já gravado (reenvio e "já tem atendimento") não muda
- [x] T033 [US3] Em `pedidos/consultas.py`: `filtrar_situacao(..., "aguardando")` exclui os pedidos com autorização `AGUARDANDO` ou `RECUSADO`; acrescentar o campo `autorizacao` em `FiltrosPainel` (Todas, Aguardando autorização, Autorizado, Recusado) e o filtro em `pedidos_do_painel`; `parcial` e `atendido` não mudam; acrescentar `"autorizacao"` ao `select_related` de `pedidos_do_painel`, para a situação de cada linha não gerar consulta própria
- [x] T034 [US3] Em `pedidos/views/almoxarifado.py`: `_pedido` ganha `"autorizacao"` no `select_related`; `_contexto_detalhe` só marca `atendivel` com autorização `AUTORIZADO` ou sem autorização, e leva a autorização ao contexto; `_pedido_com_atendimento_aberto` levanta `Http404` para pedido com autorização diferente de `AUTORIZADO`
- [x] T035 [US3] Em `pedidos/templates/pedidos/detalhe.html` e `_recibo.html`, mostrar a autorização (situação, quem, quando, motivo) conforme [mensagens.md](contracts/mensagens.md) e, aguardando ou recusado, no lugar do formulário de atendimento a frase de bloqueio; o recibo impresso não muda
- [x] T036 [US3] Em `pedidos/templates/pedidos/painel.html` e `_painel_lista.html`, o campo Autorização nos filtros (e a contagem nos chips de `filtros.js`, que lê os campos do form) e o selo das duas situações novas; rodar `tests/test_epis_atendimento.py tests/test_epis_painel.py tests/test_painel.py`

**Checkpoint**: nenhum EPI sai antes da autorização; os testes de painel, atendimento e lançamento existentes passam sem alteração.

---

## Phase 6: User Story 4 - Definir os materiais de EPI (Priority: P2)

**Goal**: o almoxarifado mantém grupos e avulsos pelo admin, e a saúde do catálogo mostra o formulário.

**Independent Test**: incluir um grupo e um avulso e retirar outro grupo; no próximo acesso o formulário reflete a mudança e a saúde mostra a contagem.

### Tests for User Story 4

- [x] T037 [P] [US4] Escrever `tests/test_epis_admin.py`: a lista "Grupos (EPIs)" nas Opções e o admin de `MaterialEpi` (autocomplete, um por material); mudança de grupo vale no próximo acesso do formulário; o grupo `Segurança do Trabalho` existe depois do `migrate` e o formulário de usuário do admin (`/admin/contas/usuario/<id>/change/`) permite marcá-lo e salva a participação, o que dá o acesso sem nova versão (FR-019)
- [x] T038 [P] [US4] Escrever `tests/test_epis_saude.py`: contagem de materiais, indisponível (sem item visível), grupos escolhidos sem material visível, avulsos ocultos no SCPI, e a linha na visão geral de Automações (FR-030)

### Implementation for User Story 4

- [x] T039 [US4] Em `catalogo/admin.py`, registrar `MaterialEpiAdmin` (espelho de `MaterialOficinaAdmin`); a lista `GRUPO_EPI` já aparece em `OpcaoAdmin` pelas `choices`
- [x] T040 [US4] Em `catalogo/saude.py`, acrescentar `FORMULARIO_EPIS`, `_epis()` (quanto oferece, ou o motivo de estar indisponível; grupos sem material visível; avulsos ocultos) chamada onde `_oficina()` é chamada, e `Situacao.epis` (contagem de `catalogo_epis()`); em `catalogo/templates/catalogo/_situacao.html`, o cartão do formulário de EPIs ao lado do da oficina

**Checkpoint**: a escolha dos EPIs é mantida só pelo admin e aparece na saúde.

---

## Phase 7: User Story 5 - Consultar o resultado do pedido (Priority: P2)

**Goal**: o servidor, sem login, consulta pelo número a situação e o motivo da recusa.

**Independent Test**: consultar os números de um pedido aguardando, de um autorizado, de um recusado e um inexistente.

### Tests for User Story 5

- [x] T041 [P] [US5] Escrever `tests/test_epis_consulta.py`: as três situações e o motivo da recusa; a resposta não contém nome, destino, observação nem materiais; número inexistente e número de pedido de outro formulário dão a mesma resposta; o limite por origem (`PEDIDOS_CONSULTA_LIMITE_IP_10_MIN`) recusa a consulta seguinte com a mensagem própria da consulta ([mensagens.md](contracts/mensagens.md)) e limpa o cache entre testes; só POST consulta (GET só mostra o formulário); CSRF; cabeçalho `Cache-Control: no-store` (FR-031, FR-031a)

### Implementation for User Story 5

- [x] T042 [US5] Em `pedidos/regras.py`, acrescentar `texto_situacao_consulta(autorizacao, motivo)` (função pura, textos de [mensagens.md](contracts/mensagens.md)); testar em `tests/test_regras_pedidos.py` só com casos novos
- [x] T043 [US5] Em `pedidos/views/publico.py`, acrescentar `consulta_epi` (GET mostra o formulário do número; POST: conta a tentativa por `REMOTE_ADDR` no cache do Django com janela de 10 minutos, recusa acima do limite com a mensagem própria da consulta (não a `MENSAGEM_LIMITE_IP`, que fala de pedidos enviados), busca o pedido por número só se `origem` exige autorização, e responde igual em qualquer outro caso); em `pedidos/urls.py`, registrar `pedidos:consulta_epi` em `pedido/epis/consulta/` e criar `pedidos/templates/pedidos/consulta_epi.html` (`base_publico.html`)
- [x] T044 [US5] Em `pedidos/templates/pedidos/_sucesso.html`, ligar o link da consulta da T019 à rota; conferir que o texto de sucesso continua igual para os outros formulários (FR-031b)

**Checkpoint**: o servidor sabe o resultado sem login e a consulta não vaza dado pessoal.

---

## Phase 8: User Story 6 - Dar acesso à Segurança do Trabalho (Priority: P2)

**Goal**: o usuário do grupo só abre a fila, o detalhe de autorização, a decisão e as páginas públicas; o resto fica negado por padrão.

**Independent Test**: entrar com o usuário do grupo e tentar abrir cada rota do projeto; só as da lista passam.

### Tests for User Story 6

- [x] T045 [P] [US6] Escrever `tests/test_epis_acesso.py`: (a) teste puro de que `contas.acesso.ROTAS_SEGURANCA_TRABALHO` é exatamente a lista de [rotas-e-acesso.md](contracts/rotas-e-acesso.md); (b) enumerar os nomes de rota do projeto com `django.urls.get_resolver` (os `url_name` com namespace, incluindo os do admin), montar uma URL concreta de cada um com `reverse` e argumentos de teste e, com o usuário do grupo, em GET e POST, conferir que só os da lista passam (GET dos demais redireciona à fila, os outros métodos dão 403), e que um nome de rota não visto pelo teste falha o teste (a enumeração não pode ser silenciosamente incompleta); o administrador (`is_staff`) fora do grupo continua com tudo e é negado em decidir; o usuário comum e o anônimo não mudam; o login do usuário do grupo termina na fila; o menu do grupo só tem "Autorizações" e o dos demais não ganha o item (FR-017 a FR-020, SC-004)

### Implementation for User Story 6

- [x] T046 [US6] Em `contas/acesso.py`, acrescentar a constante pura `ROTAS_SEGURANCA_TRABALHO` (`frozenset` de nomes: `login`, `logout`, `pedidos:autorizacoes`, `pedidos:autorizacao`, `pedidos:decidir`, `pedidos:inicio`, `pedidos:formulario`, `pedidos:materiais`, `pedidos:carrinho`, `pedidos:consulta_epi`); criar `contas/middleware.py` com `RestringirSegurancaTrabalho`: para usuário autenticado e `da_seguranca_trabalho`, permite só os nomes dessa constante; GET e HEAD das demais redirecionam a `pedidos:autorizacoes`, os outros métodos dão 403; rota que não resolve segue ao 404; retorna cedo para quem não é do grupo. Registrar em `config/settings.py` `MIDDLEWARE` depois do `AuthenticationMiddleware`
- [x] T047 [US6] Em `interface/navegacao.py`, dar ao `ItemMenu` o perfil (`para`: almoxarifado por padrão) e acrescentar o item "Autorizações" (`pedidos:autorizacoes`) só para o grupo; o grupo vê só esse item e os demais mantêm o menu de hoje; nos templates do grupo, o bloco `voltar` não aponta ao painel (já vazio desde a T028)
- [x] T048 [US6] Rodar `tests/test_epis_acesso.py tests/test_acesso.py tests/test_rotas.py tests/test_prefixo.py` e conferir que as rotas e o prefixo seguem iguais (FR-018, FR-033)

**Checkpoint**: o acesso restrito está fechado por padrão; US1 + US2 + US3 + US6 formam o corte publicável.

---

## Phase 9: Polish & Cross-Cutting

**Purpose**: ambiente, documentação, portões e a conferência final.

- [x] T049 [P] Acrescentar `TELEGRAM_CHAT_ID_SEGURANCA=` (com comentário curto) e `PEDIDOS_CONSULTA_LIMITE_IP_10_MIN` se couber no padrão do arquivo, em `.env.example`; e `TELEGRAM_CHAT_ID_SEGURANCA: ""` em `compose.desenvolvimento.yaml`
- [x] T050 [P] Em `deploy/atualizar.ps1`, incluir `TELEGRAM_CHAT_ID_SEGURANCA` na lista `$integracoes` da preparação, atualizar `deploy/tests/atualizar.Tests.ps1` e `deploy/AMBIENTES.md` (a variável vazia nos ambientes novos); se o Pester não estiver disponível localmente, registrar na entrega que o teste não foi executado
- [x] T051 [P] Atualizar `CLAUDE.md` no mesmo PR: o formulário de EPIs e a autorização (`Fluxo.exige_autorizacao`, `AutorizacaoPedido`, portão do atendimento, middleware e grupo da Segurança do Trabalho, consulta pública, variáveis novas), a decisão de desenho "o número não vira página pública" e sua exceção, e as migrations novas; atualizar também `README.md` onde lista as variáveis do Telegram
- [x] T052 [P] Ajustar `tests/test_formularios_publicos.py` apenas para incluir o cartão de EPIs na página inicial (sem mudar o comportamento dos outros); confirmar `tests/test_config.py` com `check --deploy` sem avisos
- [x] T053 Rodar os portões: `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`, `DEBUG=0 uv run python manage.py check --deploy --fail-level WARNING`; corrigir o que aparecer (nada de `--no-verify`)
- [x] T054 Percorrer o roteiro de [quickstart.md](quickstart.md) no ambiente de desenvolvimento (formulário, fila, decisão, atendimento, recusa, consulta, acesso restrito) e anotar o resultado; telas conferidas à mão porque os testes não abrem navegador (Constituição V)
- [x] T055 Registrar em `specs/008-formulario-epis/checklists/operacao.md` (Notes) o que foi verificado e o que segue como pendência externa (NR-6 e política do SAEP), sem marcar itens como `[x]` (o revisor marca); rodar `/speckit-analyze` de novo se algum requisito mudou

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (1)**: sem dependências.
- **Foundational (2)**: depende da Setup; **bloqueia todas as histórias**.
- **US1 (3)**: depende da Foundational. É o MVP técnico.
- **US2 (4)**: depende da Foundational e da US1 (precisa de pedidos de EPI) e do T008 (`da_seguranca_trabalho`).
- **US3 (5)**: depende da Foundational e da US1 (pedido) e do T024 (para testar o fluxo completo autorizar → atender).
- **US4 (6)**: depende só da Foundational (T007) e da T015; pode andar em paralelo com a US2 e a US3.
- **US5 (7)**: depende da US1 (pedido) e do T024 (para ter autorizado e recusado).
- **US6 (8)**: depende da US2 (rotas da fila) e da US5 (rota pública da lista); só **depois** dela a US2 pode ir a produção.
- **Polish (9)**: depois das histórias desejadas.

### Within Each User Story

- Teste primeiro (e vê-lo falhar) → modelo/regra pura → serviço → rota/view → template.
- `pedidos/urls.py`, `pedidos/servicos.py`, `pedidos/consultas.py` e `pedidos/templates/pedidos/_sucesso.html` são tocados por mais de uma história: **sem [P] entre elas**; as histórias seguem a ordem.

### Parallel Opportunities

- Foundational: T003, T007, T008 em paralelo (arquivos diferentes); T004 → T005 → T006 em sequência.
- US1: os testes T012, T013, T014 em paralelo; depois T015 e T016 em paralelo.
- US2: T021, T022, T023 em paralelo.
- US3: T029, T030, T031 em paralelo.
- US4 inteira em paralelo com a US2/US3 (outro desenvolvedor) depois do Foundational.
- Polish: T049, T050, T051, T052 em paralelo.

### Parallel Example: User Story 1

```text
T012 tests/test_epis_catalogo.py
T013 tests/test_epis_formulario.py
T014 tests/test_epis_telegram.py (lado do registro)
→ depois T015 (catalogo/catalogos.py) e T016 (pedidos/telegram.py) em paralelo
```

---

## Implementation Strategy

### MVP First

1. Setup e Foundational.
2. US1: o formulário envia e fica aguardando (já testável, ainda sem decisão).
3. US2 + US3: decidir e só então atender.
4. US6: fechar o acesso. **Só aqui há algo publicável.**
5. US5 (consulta) e US4 (admin e saúde) em seguida, ou antes da publicação se o usuário preferir.

### Incremental Delivery

Cada fase termina com `uv run pytest` verde da fase e dos testes existentes. Um PR por entrega
publicável (`claude/epis` → `develop`); o merge e qualquer ação de produção são do usuário (CLAUDE.md).

### Parar e perguntar

Se, na implementação, aparecer decisão operacional não coberta (por exemplo, o texto de uma
mensagem, a carga inicial dos grupos de EPI, o endurecimento da consulta com o nome completo), **parar e
perguntar** ao usuário em vez de presumir.

---

## Cobertura dos requisitos

| Requisitos | Tarefas |
|------------|---------|
| FR-001, FR-002, FR-003, FR-006 | T013, T018, T019 |
| FR-004, FR-005, FR-007 | T012, T015 |
| FR-008, FR-009, FR-010 | T005, T009, T013, T017, T019, T020 |
| FR-011 a FR-016 | T021, T024, T025, T026, T027, T028 |
| FR-017 a FR-020 | T008, T045, T046, T047 |
| FR-021 | T021, T024, T026 |
| FR-022, FR-023, FR-024, FR-025 | T029, T030, T032, T033, T034, T035, T036 |
| FR-026, FR-027, FR-028 | T014, T016, T017, T022, T024 |
| FR-029, FR-030 | T012, T015, T037, T038, T039, T040 |
| FR-031, FR-031a, FR-031b | T041, T042, T043, T044 |
| FR-032, FR-033 | T001, T010, T030, T031, T048, T053 |
| SC-001 | T054 (medição no uso real depois da implantação) |
| SC-002 | T029 |
| SC-003 | T021, T024 |
| SC-004 | T045 |
| SC-005, SC-006 | T022, T028 (a fila independe do aviso) |
| SC-007 | T041 |
| SC-008 | T001, T053 |

## Phase 10: Convergence

**Purpose**: o que o `/speckit-converge` achou entre o código e a spec, o plano e as tarefas (2026-10-23). Nenhum requisito ficou sem implementação; o que resta é conferência.

- [ ] T056 Revisar as telas novas (`pedidos/templates/pedidos/autorizacoes.html`, `autorizacao.html`, `consulta_epi.html`, `_autorizacao.html` e o bloco de `_sucesso.html`) com as três skills de UI do projeto, `clean-design` com `docs/DESIGN.md`, `ui-ux-pro-max` e `frontend-design`, no celular **e** na largura de computador (só o celular foi visto), e corrigir o que divergir, per CLAUDE.md "Convenções" e Constitution VI (partial)
- [ ] T057 Rodar `deploy/tests/atualizar.Tests.ps1` com o Pester numa máquina com PowerShell 5.1+ (`pwsh` não existe nesta) e registrar o resultado, per T050 (partial)
- [ ] T058 Enviar um pedido de EPIs pelo navegador no celular e conferir os dois avisos do Telegram com token e chats de teste (ao registrar só o da Segurança do Trabalho; ao autorizar só o do almoxarifado), per quickstart §3 passo 1 e §4, FR-026 e FR-027 (partial)
