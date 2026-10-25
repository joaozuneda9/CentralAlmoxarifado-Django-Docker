# Feature Specification: Configuração das opções por formulário

**Feature Branch**: `claude/configuracao-formularios`

**Created**: 2026-10-23

**Status**: Draft

**Input**: User description: tela administrativa do Central Almoxarifado para definir, formulário a
formulário, **quais centros de custo aparecem no campo Destino** e **quais materiais o formulário
oferece**, sem editar o código-fonte. Duas responsabilidades distintas na mesma experiência. O
catálogo de materiais do SCPI continua sendo o único cadastro: a funcionalidade só administra a
**associação** entre material (ou centro) e formulário. Decisões do usuário em 2026-10-23, antes desta
especificação: a disponibilidade dos materiais é **uma camada de exceções sobre as regras atuais** (a
regra de hoje continua valendo onde ninguém mexeu); ver a configuração é aberto a todo usuário do
almoxarifado e **alterá-la** é de quem hoje altera cadastros no admin; um centro de custo inativo some
dos formulários novos, mas **atendimento, edição e robô continuam resolvendo** qualquer centro.

## Contexto

Hoje o que cada formulário oferece está **escrito no código**, em regras diferentes por formulário
(entradas de `FLUXOS` e funções de catálogo), e só se muda com ajuda de quem programa, ou, nos casos
abaixo, por cadastros espalhados do admin:

| Formulário | Materiais oferecidos hoje | Destinos oferecidos hoje |
|---|---|---|
| Limpeza, copa e escritório | a lista de itens de limpeza (categoria, nome e unidade exibidos, ordem) | todos os centros de custo |
| Ferramentas, peças e materiais (AB) | calculado: o que teve saída no período da curva ABC, menos grupos ocultos e menos os itens da limpeza | todos |
| Reposição de peças das viaturas | a lista de peças (ordem e folha) mais o catálogo AB | só os centros marcados como "equipe de manutenção", um por descrição, sem placa |
| Oficina mecânica | os grupos escolhidos do SCPI mais materiais avulsos | o centro "OFICINA MECÂNICA" e cada viatura (centro com placa), esta só como "centro — placa" |
| EPIs | os grupos escolhidos do SCPI mais materiais avulsos | todos |

A **saída avulsa** é o registro do balcão pelo almoxarifado e o **atendimento** de um pedido é feito
pela equipe: os dois usam o catálogo interno completo e todos os centros, e **não fazem parte** desta
funcionalidade. O robô do SCPI resolve o centro de custo de cada lote pelo nome, entre todos os cadastrados.

O histórico já é protegido por construção: o destino e o centro de custo ficam gravados como **texto** no
pedido, no atendimento e na linha de saída, e cada item guarda um **retrato** do material (código, nome,
grupo, estoque). Nada disso depende de o centro ou o material continuar disponível num formulário.

**Termos.** "Formulário" é um dos cinco formulários públicos acima. "Disponível no formulário" é o que o
formulário **oferece** e **aceita** em pedidos novos; é diferente de "disponível em estoque" (o saldo do
SCPI) e de "ativo" (global, do centro de custo). "Regra de origem" é como o formulário já decide hoje
quais materiais oferece (a lista, os grupos, o cálculo do AB). "Exceção" é uma decisão do administrador,
por material e por formulário, que **acrescenta** um material à regra de origem ou o **retira** dela.
"Disponibilidade efetiva" é o resultado: regra de origem mais exceções.

## Clarifications

### Session 2026-10-23

Respostas do usuário, anteriores à escrita desta especificação:

- Q: A disponibilidade dos materiais é uma lista explícita por formulário (congelando o catálogo atual) ou
  uma camada de exceções sobre as regras atuais? → A: **exceções sobre as regras atuais**. Sem exceção,
  vale exatamente o que vale hoje (o AB continua calculado; os grupos e as listas continuam valendo). O
  administrador só acrescenta ou retira o que quiser.
- Q: Quem vê e quem altera a configuração? → A: qualquer usuário do almoxarifado (os usuários de sempre
  da parte interna) **vê**; **altera** quem hoje altera cadastros no admin (a mesma regra do menu
  "Cadastros"). Nenhum papel novo. A Segurança do Trabalho continua fora da parte interna, como na
  especificação 008.
- Q: O que muda quando um centro de custo é inativado? → A: ele deixa de ser oferecido e aceito nos
  **formulários públicos** e na **saída avulsa nova**. O atendimento, a
  edição de atendimento e o robô do SCPI **continuam resolvendo qualquer centro**, ativo ou não, para o
  pedido já registrado e o lote pendente não travarem.

Rodada de esclarecimento (`/speckit-clarify`), também em 2026-10-23:

- Q: Em quais formulários um centro de custo recém-criado já nasce disponível? → A: **em nenhum**: o
  administrador escolhe onde ele vale, e a saúde do cadastro avisa "centro sem formulário" até lá.
- Q: Como acrescentar a limpeza ou às viaturas um material que a lista de origem não traz? → A: **por
  exceção**, e o material acrescentado aparece **depois da lista, em ordem alfabética**, sem categoria na
  limpeza e fora da folha nas viaturas. Categoria, ordem e folha continuam sendo da lista de origem.
- Q: O que acontece com os cadastros antigos (marca de equipe de manutenção, materiais avulsos da oficina
  e dos EPIs) depois de transcritos? → A: **saem do admin**. Os dados ficam no banco (nada é apagado, o que
  permite voltar atrás), mas deixam de ser editáveis e de valer; só a configuração decide.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Escolher os destinos de cada formulário (Priority: P1)

O administrador abre a configuração, escolhe um formulário e vê a lista dos centros de custo com a
marca de quais são destino naquele formulário. Marca e desmarca; o formulário público passa a oferecer só
os marcados, e só aceita os marcados em pedidos novos.

**Why this priority**: É a parte de menor risco e de uso mais imediato (um setor novo, uma viatura nova,
um centro que deixou de existir), e hoje exige ajuda de quem programa ou uma marca isolada no admin que só
vale para as viaturas.

**Independent Test**: Com os cinco formulários migrados, habilitar o centro "ETA I" só na limpeza: ele
aparece como destino na limpeza e não nos outros quatro; enviar um pedido do AB com o destino "ETA I" (por
um envio direto, sem a tela) é recusado; o da limpeza é aceito.

**Acceptance Scenarios**:

1. **Given** um centro habilitado na limpeza e não habilitado na oficina, **When** o funcionário abre os
   dois formulários, **Then** o centro aparece como destino só na limpeza.
2. **Given** um centro não habilitado num formulário, **When** chega um envio direto desse formulário com
   esse destino, **Then** o servidor recusa com o erro de destino que já existe ("não está na lista de
   centros de custo"), sem registrar pedido.
3. **Given** um centro habilitado em dois formulários, **When** o administrador o desabilita num deles,
   **Then** o outro continua oferecendo-o.
4. **Given** um formulário que fica sem nenhum destino habilitado, **When** o funcionário o abre, **Then**
   ele aparece indisponível com a mensagem dos destinos ausentes que já existe, e a saúde do cadastro
   avisa o almoxarifado.
5. **Given** a primeira vez depois da implantação, **When** o funcionário abre qualquer um dos cinco
   formulários, **Then** os destinos oferecidos são **exatamente** os de antes (a regra de cada formulário
   foi transcrita para a configuração).

---

### User Story 2 - Escolher os materiais de cada formulário (Priority: P1)

O administrador escolhe um formulário e pesquisa materiais do catálogo. Para cada um vê se está
disponível naquele formulário e **por quê** (regra de origem, exceção para acrescentar, exceção para
retirar). Acrescenta um material que a regra não traz, ou retira um que ela traz, e a mudança vale no
formulário na hora. Pode também voltar um material à regra de origem, apagando a exceção.

**Why this priority**: É o objetivo central: hoje acrescentar ou retirar um material de um formulário
exige editar grupos, listas ou a lista avulsa de cada formulário, cada um num lugar.

**Independent Test**: Com o AB calculando 377 itens, retirar um deles do AB: ele some da busca do AB e um
envio direto com ele é recusado; continua no formulário de viaturas, que o oferecia por conta própria.
Acrescentar ao AB um material sem saída no período: ele aparece. Restaurar a regra nos dois: tudo volta
ao que era.

**Acceptance Scenarios**:

1. **Given** um material oferecido por um formulário pela regra de origem, **When** o administrador o
   retira dele, **Then** ele deixa de aparecer na busca e de ser aceito em pedidos novos **desse**
   formulário, e continua nos demais.
2. **Given** um material que a regra de origem não traz, **When** o administrador o acrescenta,
   **Then** ele aparece na busca desse formulário, com a regra de quantidade e de estoque dos formulários
   públicos.
3. **Given** uma exceção, **When** o administrador a restaura, **Then** o material volta ao que a regra de
   origem diz e a exceção deixa de existir.
4. **Given** um material acrescentado a um formulário e **sem estoque**, **When** o funcionário o procura,
   **Then** ele aparece bloqueado ("Sem estoque"), como qualquer material sem estoque: a disponibilidade no
   formulário não torna o material disponível em estoque.
5. **Given** um material oculto no cadastro (some do SCPI), **When** o administrador tenta acrescentá-lo,
   **Then** a configuração o mostra como oculto e o formulário continua não o oferecendo: a exceção não
   contraria o cadastro.
6. **Given** a primeira vez depois da implantação, **When** o funcionário abre qualquer formulário,
   **Then** os materiais oferecidos são **exatamente** os de antes, inclusive os avulsos da oficina e dos
   EPIs.

---

### User Story 3 - Alterar vários materiais de uma vez (Priority: P2)

Para um grupo inteiro (dezenas de materiais), o administrador filtra o catálogo (por grupo, subgrupo ou
texto), vê quantos materiais o filtro alcança e escolhe "acrescentar todos" ou "retirar todos" nesse
formulário. A tela mostra o número exato antes de confirmar e o resultado depois.

**Why this priority**: O catálogo tem mais de 7.000 materiais visíveis; um a um seria inviável para um
grupo, mas o caso mais comum (poucos materiais) já é atendido pela história 2.

**Independent Test**: Filtrar um grupo de 20 materiais, "retirar todos" do AB: a tela mostra "20
materiais" antes de confirmar, e depois "20 retirados"; só esses 20 mudam, só no AB.

**Acceptance Scenarios**:

1. **Given** um filtro que alcança N materiais, **When** o administrador pede a operação em lote,
   **Then** a tela mostra N, o formulário e a ação, e só aplica depois de uma confirmação explícita.
2. **Given** um filtro com várias páginas de resultado, **When** a operação é confirmada, **Then** ela vale
   para **todos** os N materiais do filtro, não só os da página visível.
3. **Given** um lote concluído, **When** o administrador consulta, **Then** vê o resultado (quantos
   mudaram, quantos já estavam assim) e nenhum material fora do filtro mudou.
4. **Given** um filtro vazio (o catálogo inteiro), **When** o administrador pede a operação em lote,
   **Then** a tela exige uma confirmação reforçada, com o número total.

---

### User Story 4 - Saber onde um material aparece (Priority: P2)

O administrador procura um material e vê, de uma vez, em quais dos cinco formulários ele está disponível e
por quê, sem abrir um formulário de cada vez.

**Why this priority**: Responde "por que não achei X no formulário Y?" e "onde esse material está sendo
oferecido?", as perguntas mais comuns do almoxarifado.

**Independent Test**: Procurar um material oferecido por regra no AB, acrescentado à oficina e retirado
dos EPIs: a tela mostra os três estados e a origem de cada um.

**Acceptance Scenarios**:

1. **Given** um material, **When** o administrador o consulta, **Then** vê os cinco formulários com
   "disponível" ou "não disponível" e a origem (regra, exceção que acrescenta, exceção que retira).
2. **Given** um material oculto ou duplicado no cadastro, **When** o administrador o consulta, **Then** a
   tela o marca assim, porque isso vale em todos os formulários.

---

### User Story 5 - Manter os centros de custo (Priority: P2)

O administrador cria um centro de custo novo, edita um existente ou o **inativa** (globalmente). O centro
inativo some de todos os formulários públicos, mas as escolhas por formulário ficam guardadas: se for
reativado, volta onde estava.

**Why this priority**: Fecha o ciclo de vida do centro (nasce, muda, deixa de existir) sem apagar
histórico; o cadastro de centros já existe no admin e só ganha a inativação e a associação.

**Independent Test**: Inativar um centro habilitado em três formulários: some dos três; um pedido antigo
com esse destino continua exibindo o destino; o atendimento desse pedido e o lote pendente dele
continuam resolvendo o centro; reativar devolve as três associações.

**Acceptance Scenarios**:

1. **Given** um centro habilitado em formulários, **When** o administrador o inativa, **Then** nenhum
   formulário público o oferece nem o aceita em pedidos novos.
2. **Given** um pedido já registrado com o destino de um centro inativado, **When** o almoxarifado abre o
   detalhe, atende ou edita, **Then** o destino continua visível e o centro continua sendo resolvido.
3. **Given** um lote pendente de um centro inativado, **When** o robô lança, **Then** o centro é resolvido
   como antes, sem o lote virar erro.
4. **Given** um centro inativado e reativado, **When** o administrador consulta, **Then** as associações
   por formulário são as de antes da inativação.
5. **Given** um centro novo criado pelo administrador, **When** ele é salvo, **Then** a tela de
   configuração o mostra sem formulário habilitado até o administrador escolher onde ele vale, e a saúde
   do cadastro avisa que há centro sem formulário.
6. **Given** um centro inativo que está habilitado em formulários, **When** o almoxarifado abre a saída
   avulsa **nova**, **Then** o centro não é oferecido nem aceito; e **When** abre a **edição** de uma saída
   avulsa já registrada com esse centro, **Then** ela o mantém e salva normalmente.

---

### User Story 6 - Quem pode ver e quem pode alterar (Priority: P2)

Qualquer usuário do almoxarifado abre a configuração e vê o estado atual. Só quem altera cadastros no
admin consegue gravar uma mudança; o servidor recusa a gravação de quem não pode, mesmo que o botão
apareça ou o pedido seja forjado.

**Why this priority**: A configuração muda o que os funcionários conseguem pedir; a permissão tem de valer
no servidor, não só na tela.

**Independent Test**: Com um usuário do almoxarifado sem permissão de alteração, enviar direto a gravação de
uma exceção e a de um centro: ambas recusadas e nada muda; com o administrador, aceitas. Com o usuário da
Segurança do Trabalho, a rota nem abre.

**Acceptance Scenarios**:

1. **Given** um usuário do almoxarifado sem permissão de alteração, **When** ele abre a configuração,
   **Then** vê tudo, sem os controles de alteração.
2. **Given** o mesmo usuário, **When** ele envia direto uma gravação, **Then** o servidor a recusa (403) e
   nada muda.
3. **Given** um usuário da Segurança do Trabalho, **When** ele tenta abrir a configuração, **Then** é
   negado como qualquer rota interna fora da lista dele.
4. **Given** uma pessoa sem login, **When** tenta abrir a configuração, **Then** vai ao login.

---

### Edge Cases

- **Formulário que fica sem material nenhum** depois de exceções: abre indisponível, com a mensagem de
  catálogo indisponível que já existe, e a saúde avisa.
- **Funcionário com o formulário aberto** quando o administrador retira um material ou um destino: o
  envio recusa com a mensagem que já existe ("não está mais no catálogo" / destino fora da lista), com
  os dados mantidos para corrigir; nada é registrado com a opção retirada.
- **Pedido já registrado** com material retirado depois: continua íntegro, com o retrato gravado; o
  atendimento, a troca e o acréscimo do almoxarifado não consultam a configuração.
- **Pedido de EPI aguardando autorização** com material retirado depois: continua autorizável e atendível
  com o que foi gravado; a retirada vale só para pedidos novos.
- **Reenvio igual** de um pedido já registrado (mesmo identificador): continua confirmando sem duplicar,
  mesmo que a configuração tenha mudado entre os envios.
- **Material que a regra de origem traz e uma exceção retira, e depois sai da regra** (grupo tirado da
  lista, por exemplo): a exceção que retira fica sem efeito visível; a tela a mostra como "sem efeito" e
  permite limpá-la, sem erro.
- **Material acrescentado e depois oculto pelo importador**: deixa de ser oferecido (o cadastro vale), a
  exceção continua guardada e a tela a mostra como "oculto no cadastro".
- **Material duplicado**: continua aparecendo bloqueado onde estiver disponível, como hoje.
- **Centro de custo com várias linhas** (uma por placa): a tela agrupa por descrição, e cada linha com
  placa pode ser habilitada separadamente; o modo de apresentação do destino de cada formulário (só a
  descrição, ou "centro — placa") não muda.
- **Placa em duas linhas** continua impossível (a regra do cadastro de centros não muda).
- **Dois administradores alterando ao mesmo tempo**: cada gravação vale por completo; a última prevalece
  sobre o mesmo item, e a tela mostra, ao recarregar, o estado gravado.
- **Operação em lote interrompida**: nada fica pela metade; ou as mudanças do lote valem todas, ou
  nenhuma.
- **Saldo de estoque nunca importado**: os formulários que dependem do saldo continuam indisponíveis, como
  hoje, qualquer que seja a configuração.
- **Origem sem formulário** (pedido antigo cuja origem não existe mais): não aparece na configuração e não
  é afetada.
- **Código antigo de um par de/para** acrescentado a um formulário: o formulário passa a oferecer esse
  código com o saldo dele (o AB oferece o canônico); a tela avisa que é um código antigo e sugere o
  canônico, sem impedir.
- **Habilitar um centro de formulário que só usa a descrição** (viaturas): ver FR-007a; habilitar a
  descrição vale para todas as suas linhas.

## Requirements *(mandatory)*

### Functional Requirements

**Configuração por formulário**

- **FR-001**: O sistema DEVE oferecer uma página interna de configuração dos formulários, na qual o
  usuário escolhe um dos cinco formulários públicos (limpeza, AB, viaturas, oficina, EPIs) e acessa duas
  áreas, **Centros de custo** e **Materiais**, ligadas ao formulário escolhido.
- **FR-002**: A saída avulsa e o atendimento NÃO DEVEM aparecer na configuração nem ser afetados pelas
  associações por formulário (centros e materiais). O único efeito sobre eles é o do estado **inativo** de
  um centro (FR-008 e FR-012): a saída avulsa **nova** não oferece centro inativo.
- **FR-003**: Qualquer mudança DEVE valer nos formulários **sem reiniciar** o sistema e sem editar código.
- **FR-004**: Configurar um formulário NÃO DEVE alterar a disponibilidade em nenhum outro formulário.

**Centros de custo**

- **FR-005**: O sistema DEVE permitir consultar os centros de custo existentes, com o estado (ativo ou
  inativo) e os formulários em que cada um é destino.
- **FR-006**: O sistema DEVE permitir habilitar e desabilitar cada centro de custo, **formulário a
  formulário**, e um mesmo centro DEVE poder estar em vários formulários.
- **FR-007**: A disponibilidade DEVE ser por **linha do cadastro de centros** (um centro com várias
  placas tem uma linha por placa); a tela DEVE agrupar as linhas pela descrição.
- **FR-007a**: O **modo de apresentação do destino** é característica de cada formulário e não é
  configurável: limpeza, AB e EPIs oferecem a descrição e, para a linha com placa, "descrição — placa";
  viaturas oferecem só a descrição, uma por centro; a oficina oferece a linha com placa só como "descrição
  — placa" e a linha sem placa como a descrição. Nas viaturas, como a placa não importa, a tela DEVE
  habilitar e desabilitar **pela descrição** (todas as linhas juntas) e mostrar como habilitada a descrição
  com alguma linha habilitada.
- **FR-008**: Cada centro de custo DEVE ter um estado **ativo/inativo global**. O centro inativo NÃO DEVE
  ser oferecido nem aceito em pedido novo de nenhum formulário público, nem oferecido numa saída avulsa
  nova, qualquer que seja a configuração por formulário, e as associações por formulário DEVEM ser
  preservadas.
- **FR-009**: O sistema DEVE permitir criar e editar centros de custo (descrição, código e placa), com as
  regras do cadastro de hoje (placa única e normalizada). O código é o do SCPI, já existente.
- **FR-010**: O centro de custo NÃO DEVE ser apagado por esta funcionalidade; inativar é o caminho para
  deixá-lo de fora.
- **FR-010a**: Um centro de custo recém-criado DEVE nascer **ativo e sem nenhum formulário habilitado**;
  a saúde do cadastro DEVE avisar enquanto houver centro ativo sem formulário.
- **FR-011**: O servidor DEVE recusar, em pedido novo, um destino que não seja de um centro **ativo e
  habilitado naquele formulário**, com o erro de destino que já existe; esconder a opção na tela não basta.
- **FR-012**: O atendimento, a edição do atendimento (inclusive a de uma saída avulsa já registrada) e o
  robô do SCPI DEVEM continuar resolvendo **todo** centro cadastrado, ativo ou inativo, habilitado ou não
  em algum formulário.
- **FR-013**: O formulário sem nenhum destino habilitado DEVE ficar indisponível com a mensagem dos
  destinos ausentes que já existe.

**Materiais**

- **FR-014**: O sistema DEVE permitir consultar os materiais do catálogo existente, com **busca** (código e
  nome) e **filtro** (grupo e subgrupo), paginados, sem carregar o catálogo inteiro de uma vez.
- **FR-015**: Para cada material e formulário, o sistema DEVE mostrar a **disponibilidade efetiva** e a
  **origem**: regra de origem, exceção que acrescenta ou exceção que retira.
- **FR-016**: O administrador DEVE poder **acrescentar** um material que a regra de origem não traz e
  **retirar** um que ela traz, por formulário, e **restaurar** a regra apagando a exceção.
- **FR-017**: Sem exceção, o formulário DEVE oferecer exatamente o que a regra de origem de hoje oferece
  (a lista, os grupos, o cálculo do AB). Material novo que a regra passar a trazer (nova importação, nova
  saída no período) DEVE continuar entrando sem ação do administrador.
- **FR-018**: A exceção que **retira** DEVE prevalecer sobre a regra de origem; a que **acrescenta** DEVE
  prevalecer sobre a ausência da regra. A exceção NÃO DEVE contrariar o cadastro: material **oculto** no
  cadastro não é oferecido em nenhum formulário, e o **duplicado** continua bloqueado onde for oferecido.
- **FR-019**: A disponibilidade no formulário NÃO DEVE alterar nenhuma regra de estoque: o saldo, o teto de
  quantidade, o bloqueio "sem estoque", a regra de quantidade por unidade e o bloqueio de duplicado valem
  como hoje, depois de o material ser considerado disponível no formulário.
- **FR-020**: O servidor DEVE recusar, em pedido novo, um material que não esteja disponível naquele
  formulário, com o erro de catálogo que já existe ("não está mais no catálogo"); esconder o material na
  busca não basta.
- **FR-021**: O sistema DEVE permitir consultar, por material, em quais dos cinco formulários ele está
  disponível e por quê (história 4).
- **FR-022**: A configuração NÃO DEVE criar, editar nem apagar material do catálogo e NÃO DEVE alterar
  estoque nem movimentação.
- **FR-023**: Os avulsos que hoje existem na oficina e nos EPIs DEVEM ser tratados pelo mesmo mecanismo de
  exceção (um só lugar para acrescentar material avulso a um formulário). Os cadastros antigos desses
  avulsos e a marca de equipe de manutenção dos centros, depois de transcritos, DEVEM sair do admin e
  deixar de valer, sem apagar dado.
- **FR-023a**: Nos formulários cuja regra de origem é uma lista (limpeza e viaturas), o material
  acrescentado por exceção DEVE aparecer **depois da lista, em ordem alfabética**, sem categoria na
  limpeza e fora da folha nas viaturas; a retirada por exceção DEVE tirar o item da lista e da folha.

**Operações em lote**

- **FR-024**: O sistema DEVE permitir **acrescentar** ou **retirar** de um formulário **todos os materiais
  que um filtro alcança**, em uma só operação.
- **FR-025**: A operação em lote DEVE mostrar, antes de aplicar, o formulário, a ação e o **número exato**
  de materiais alcançados, e DEVE exigir confirmação explícita; com o catálogo inteiro (sem filtro), a
  confirmação DEVE ser reforçada.
- **FR-026**: A operação em lote DEVE valer para **todos** os materiais do filtro (não só os da página
  visível), nenhum fora dele, e DEVE ser **atômica** (vale inteira ou não vale). Se o número de
  materiais do filtro mudou entre a prévia e a confirmação, a operação DEVE ser recusada, sem mudar
  nada, e a tela DEVE voltar à prévia com o número atual.
- **FR-027**: Concluída a operação, o sistema DEVE mostrar o resultado (quantos mudaram e quantos já
  estavam no estado pedido).

**Permissões e rastro**

- **FR-028**: Todo usuário do almoxarifado (a parte interna de hoje) DEVE poder **ver** a configuração.
- **FR-029**: **Alterar** (exceções, associações de centros, ativar/inativar, operações em lote) DEVE ser
  restrito a quem hoje altera cadastros no admin (a regra do menu "Cadastros"), e o servidor DEVE recusar a
  gravação de quem não tem essa permissão, independentemente da tela.
- **FR-030**: A Segurança do Trabalho NÃO DEVE abrir a configuração (a regra de negar por padrão da 008
  continua valendo para a rota nova).
- **FR-031**: Cada exceção e cada associação DEVE guardar **quem** alterou e **quando** pela última vez.
- **FR-032**: Nenhum papel ou permissão novos DEVEM ser criados.

**Integridade e histórico**

- **FR-033**: Inativar um centro, retirá-lo de um formulário ou retirar um material de um formulário NÃO
  DEVE alterar nenhum pedido, atendimento, linha de saída, item ou movimentação já registrados.
- **FR-034**: O atendimento, a troca e o acréscimo de material pelo almoxarifado, a edição do atendimento,
  o recibo e o lançamento no SCPI NÃO DEVEM consultar a configuração por formulário.
- **FR-035**: O reenvio igual de um pedido já registrado DEVE continuar confirmando, e o divergente DEVE
  continuar sendo recusado, como hoje, independentemente de a configuração ter mudado.

**Configuração inicial e migração**

- **FR-036**: Na implantação, a configuração DEVE ser preenchida a partir do que hoje vale, **sem alterar o
  que nenhum formulário oferece**: os destinos de cada formulário (todos, as marcas de equipe de
  manutenção, o centro da oficina e as viaturas) e os avulsos da oficina e dos EPIs.
- **FR-037**: A migração NÃO DEVE ser destrutiva: nada é apagado nem alterado no cadastro de materiais, nos
  pedidos nem nos cadastros de origem; DEVE ser **reversível** (desfazer a carga não apaga nada, porque depois da implantação as tabelas guardam também as escolhas do administrador; as tabelas somem ao desfazer o esquema); a
  transcrição DEVE ser verificável (os formulários oferecem o mesmo conjunto antes e depois).
- **FR-038**: Quando a transcrição não reproduzir com segurança o que um formulário oferece hoje, a
  migração DEVE parar e registrar a necessidade de decisão, em vez de adivinhar. Uma regra antiga que já
  resulta em lista vazia (a oficina sem o centro "OFICINA MECÂNICA", EPIs sem grupos) é transcrita como
  vazia, e a saúde do cadastro avisa.
- **FR-039**: A saúde do cadastro DEVE avisar: formulário sem destino, formulário sem material,
  centro ativo sem formulário, e exceção sem efeito.

**Compatibilidade**

- **FR-040**: Os cinco formulários, a saída avulsa, o atendimento, o painel, o recibo, o robô e as
  especificações 005 a 008 NÃO DEVEM mudar de comportamento além do que esta especificação define.

**Uso da tela**

- **FR-041**: A tela DEVE mostrar todo estado (disponível, retirado, acrescentado, inativo, sem efeito)
  **com texto**, nunca só por cor; DEVE funcionar sem JavaScript (formulários comuns, confirmação do lote
  em duas telas) e no tablet; e os códigos (CADPRO, placa) DEVEM aparecer em fonte mono, como no resto do
  sistema.

### Key Entities

- **Formulário**: um dos cinco formulários públicos. Já existe como entrada fixa do sistema; não é
  cadastrável (não há construtor de formulários).
- **Centro de custo (linha do cadastro)**: descrição, código do SCPI e placa opcional, agora com o estado
  ativo ou inativo. É o que o formulário oferece como destino.
- **Disponibilidade do centro no formulário**: a associação "esta linha de centro é destino neste
  formulário", com quem alterou e quando.
- **Exceção de material**: a decisão "acrescentar" ou "retirar" um material, para um formulário, sobre a
  regra de origem, com quem alterou e quando. Sem exceção, vale a regra.
- **Regra de origem**: o que cada formulário já decide hoje (lista de limpeza, lista de viaturas, grupos da
  oficina e dos EPIs, cálculo do AB). Continua existindo e continua sendo mantida onde é hoje.
- **Disponibilidade efetiva**: resultado calculado (regra de origem mais exceções, respeitando o cadastro);
  não é guardado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Depois da implantação, em 100% dos cinco formulários, o conjunto de destinos e o de
  materiais oferecidos é **idêntico** ao de antes (comparado por teste automatizado, formulário a
  formulário).
- **SC-002**: O administrador acrescenta ou retira **um material** de um formulário em até 30 segundos,
  contados de abrir a configuração, e a mudança aparece no formulário na próxima abertura, sem reiniciar.
- **SC-003**: O administrador retira um grupo de 50 materiais de um formulário em até 2 minutos pela
  operação em lote, vendo o número exato antes de confirmar.
- **SC-004**: Em 100% das tentativas, um envio direto com destino ou material não habilitado no
  formulário, ou com centro inativo, é recusado pelo servidor e nada é registrado.
- **SC-005**: Em 100% das alterações, os outros formulários não mudam (a mesma tentativa de envio direto
  neles dá o mesmo resultado de antes).
- **SC-006**: Depois de inativar centros e retirar materiais, 100% dos pedidos, atendimentos, recibos e
  linhas de saída anteriores continuam idênticos, e o robô lança os lotes pendentes dos centros inativos.
- **SC-007**: Em 100% das tentativas de quem não tem permissão de alteração, a gravação é recusada e nada
  muda; a Segurança do Trabalho é negada na rota.
- **SC-008**: O almoxarifado responde "em quais formulários este material aparece e por quê" em até 15
  segundos, pela consulta por material.
- **SC-009**: Os testes automatizados dos cinco formulários, da saída avulsa e do atendimento continuam
  passando sem alteração de comportamento.
- **SC-010**: A lista de materiais da configuração (catálogo de mais de 7.000 materiais visíveis) abre,
  filtra e pagina em até 2 segundos, e a abertura de qualquer formulário público não fica mais de 20%
  mais lenta que antes da configuração.

## Assumptions

- Os cinco formulários são fixos; não se cria nem apaga formulário pela tela.
- A regra de origem continua mantida onde é hoje (itens de limpeza, peças das viaturas, grupos da oficina
  e dos EPIs, grupos ocultos do AB, curva ABC); a configuração a **complementa** e mostra a origem, não a
  substitui. Os metadados por item (categoria, ordem, nome exibido, folha) ficam nas listas de origem.
- O código do centro de custo é o do SCPI, já existente; o cadastro de centros não ganha código novo.
- A tela mostra apenas materiais **visíveis** do catálogo para acrescentar; os ocultos aparecem só na
  consulta por material.
- A marca "equipe de manutenção" e os cadastros avulsos da oficina e dos EPIs são **transcritos** para a
  configuração, saem do admin e deixam de valer; os dados antigos ficam no banco, sem apagar nada.
- O modo de apresentação do destino de cada formulário (as viaturas só com a descrição, a oficina com
  "centro — placa") é característica do formulário e não muda.
- A permissão de alterar é a do admin de hoje (`is_staff` com as permissões do cadastro correspondente);
  quem vê é todo usuário interno que não seja da Segurança do Trabalho.
- O catálogo é grande (milhares de materiais): busca, filtro e paginação no servidor.
- Estoque, bloqueios e regra de quantidade já existentes não mudam; o estoque continua só um teto na
  hora do envio.

### Resolvido na rodada de esclarecimento

Os quatro pontos que estavam abertos (padrão do centro novo, acréscimo à limpeza e às viaturas, destino
dos cadastros antigos e ordem dos acrescentados) foram decididos; ver **Clarifications**. Nada permanece
em aberto que bloqueie o plano.

## Fora do escopo

- Construtor genérico de formulários ou de campos; criar, renomear ou apagar formulários.
- Novo cadastro de materiais, edição de nome, unidade, grupo ou estoque; reestruturação do catálogo.
- Mudanças no cálculo do AB, na curva ABC, no importador, no de/para ou no robô do SCPI.
- Novo mecanismo de estoque, reserva de saldo ou mudança nas regras de bloqueio e de quantidade.
- Configurar a saída avulsa, o atendimento, a troca ou o acréscimo de material do almoxarifado.
- Apagar centros de custo ou materiais; histórico de alterações além de "quem e quando" da última
  mudança; desfazer em lote.
- Papéis ou permissões novos; módulo genérico de parametrizações; integração externa.
- Dependência do Google Apps Script, de CDN ou de npm.
