# Feature Specification: Contas de solicitante

**Feature Branch**: `claude/papeis-de-acesso` (provisória; ver Dependências)

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: um papel novo para os funcionários que pedem material pelos formulários
públicos: com uma conta, eles entram, pedem mais rápido e acompanham os próprios pedidos. Decisões do
usuário em 2026-11-08, numa conversa de design antes desta especificação: a conta serve para **não
precisar guardar números**, **privacidade** (só o dono vê o próprio pedido) e **pedir mais rápido**;
**não há cadastro aberto** (o almoxarifado cria as contas e entrega a senha inicial); a conta é
**opcional** (os formulários seguem abertos a quem não tem conta, e a consulta pública da spec 011
continua); "Meus pedidos" mostra **só os pedidos feitos com a conta**; o solicitante é um usuário comum
do sistema num papel próprio (abordagem A, escolhida entre usuário comum, cadastro separado e link
pessoal sem senha); o limite de tentativas de login usa o **django-axes**.

## Contexto

Fatos do código em 2026-11-08 (branch `develop`, `16f317c`):

| # | Fato | Onde |
|---|------|------|
| F1 | O pedido guarda o solicitante só como o nome digitado, sem matrícula nem ligação com usuário. O único vínculo com usuário é `registrado_por`, de quem registra uma saída avulsa (equipe). | `pedidos.models.Pedido` |
| F2 | O usuário entra pela matrícula; a recusa do login é genérica ("Matrícula ou senha incorretas."). O login não tem limite de tentativas. | `contas/models.py`, `contas/forms.py`, `contas/urls.py` |
| F3 | O sistema não envia e-mail (não há configuração de envio); o único canal de aviso é o Telegram, para a equipe. | `config/settings.py`, `pedidos/telegram.py` |
| F4 | A consulta pública (spec 011) abre qualquer pedido de formulário público com o número e o primeiro nome do solicitante, e mostra a situação, as datas, o motivo da recusa de EPI e os materiais pedidos. Quem acerta os dois vê o pedido de outra pessoa. | `pedidos.views.publico.consulta`, spec 011 |
| F5 | O `pedidos.js` guarda no aparelho (`localStorage`) o último nome digitado e o último destino, e preenche os campos vazios. Num computador dividido, o próximo herda o nome. | `pedidos/static/pedidos/js/pedidos.js` |
| F6 | Hoje todo usuário logado vê a área interna inteira. A spec 012 (papéis de acesso) põe a área interna em "nega por padrão", com uma tabela de rotas para permissões. | spec 012, F1 |
| F7 | A situação do pedido tem fonte única (`Pedido.situacao`), com os selos e as mensagens da spec 011. | `pedidos/regras.py` |
| F8 | O servidor de produção roda em Docker Desktop no Windows, em HTTP direto. Não foi conferido se o endereço de origem que chega à aplicação é o do aparelho ou um endereço interno comum a todos. | `deploy/AMBIENTES.md` |

## Dependências

- **A spec 012 precisa estar implantada antes.** Sem o "nega por padrão" da 012, uma conta de
  solicitante entraria na área interna inteira (F6). A implementação desta spec parte de `develop` com
  a 012 já integrada, numa branch própria; a branch acima é só onde a spec foi escrita.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Acompanhar os próprios pedidos sem guardar números (Priority: P1)

O funcionário com conta entra pela matrícula e cai em "Meus pedidos": a lista de tudo o que pediu com a
conta, do mais novo para o mais antigo, cada um com o número, o formulário, a data e a situação. Ao
abrir um, vê a situação explicada, o que pediu, quanto foi entregue e se algum material foi trocado.

**Why this priority**: é o motivo principal da conta; sem isso ela não vale nada para o solicitante.

**Independent Test**: com uma conta de solicitante, fazer dois pedidos logado, atender um com uma
quantidade menor e uma troca, e conferir a lista e as duas páginas de pedido.

**Acceptance Scenarios**:

1. **Given** um solicitante com dois pedidos feitos com a conta, **When** ele entra, **Then** cai em
   "Meus pedidos" e vê os dois, o mais novo primeiro, com o número, o formulário, a data e o selo da
   situação.
2. **Given** um desses pedidos atendido com um material entregue a menos e outro trocado, **When** ele
   o abre, **Then** vê o selo "Atendido parcialmente", a mensagem da spec 011, cada material pedido com
   a quantidade pedida e a entregue, e "trocado por <material>" no que foi trocado.
3. **Given** um pedido de EPI recusado, **When** ele o abre, **Then** vê o selo "Recusado" e o motivo.
4. **Given** qualquer pedido dele, **When** ele o abre, **Then** nunca vê quem atendeu ou decidiu, o
   recebedor, o centro de custo, a placa, o tipo de saída, a situação no SCPI, o número da requisição
   nem os materiais que o almoxarifado acrescentou por conta própria.
5. **Given** mais de 20 pedidos, **When** ele abre a lista, **Then** ela vem em páginas de 20.
6. **Given** um pedido que ele fez antes de ter conta (ou sem entrar), **When** ele abre a lista,
   **Then** esse pedido não aparece; continua só na consulta pública.

---

### User Story 2 - Só o dono vê o pedido (Priority: P1)

O pedido feito com conta é visto só pelo dono, em "Meus pedidos". Ninguém o abre trocando o número na
página, e a consulta pública deixa de abri-lo, mesmo com o número e o primeiro nome certos.

**Why this priority**: privacidade é um dos três objetivos do usuário, e a consulta pública hoje abre o
pedido de outra pessoa a quem acerta número e primeiro nome (F4).

**Independent Test**: com duas contas, fazer um pedido com a primeira e tentar abri-lo pela segunda e
pela consulta pública.

**Acceptance Scenarios**:

1. **Given** um pedido da conta A, **When** a conta B abre o endereço desse pedido em "Meus pedidos",
   **Then** recebe a mesma resposta de um número que não existe.
2. **Given** o mesmo pedido, **When** alguém o procura na consulta pública com o número e o primeiro
   nome certos, **Then** recebe "Não encontramos um pedido com este número e este nome.", a mesma
   resposta de um número inexistente.
3. **Given** um pedido anônimo, **When** uma conta tenta abri-lo em "Meus pedidos", **Then** recebe a
   resposta de número inexistente; na consulta pública ele continua abrindo como hoje.

---

### User Story 3 - Pedir mais rápido e em nome próprio (Priority: P2)

Logado, o solicitante abre um formulário e encontra o nome preenchido (o da conta, que não muda ali) e o
destino do último pedido que fez naquele formulário já sugerido. O pedido sai ligado à conta e, na tela
de sucesso, o caminho é "Ver em Meus pedidos".

**Why this priority**: é o terceiro objetivo do usuário e o que liga o pedido à conta; sem a ligação, as
histórias 1 e 2 não têm o que mostrar.

**Independent Test**: logado, fazer um pedido; depois abrir o mesmo formulário e conferir o nome e o
destino; tentar mudar o nome alterando o formulário no navegador e ver que o pedido grava o da conta.

**Acceptance Scenarios**:

1. **Given** um solicitante logado, **When** ele abre um formulário, **Then** o campo do nome mostra o
   nome da conta e não pode ser editado.
2. **Given** o mesmo solicitante, que já fez um pedido nesse formulário, **When** ele o abre de novo,
   **Then** o destino vem sugerido com o do último pedido; num formulário em que ainda não pediu, o
   destino vem vazio.
3. **Given** o formulário enviado com outro nome (alterado no navegador), **When** o pedido é registrado,
   **Then** ele grava o nome da conta e fica ligado a ela.
4. **Given** um solicitante logado, **When** o pedido é registrado, **Then** a tela de sucesso mostra o
   número e "Ver em Meus pedidos", sem o aviso para guardar o número nem o botão da consulta pública.
5. **Given** um solicitante logado, **When** ele usa o formulário, **Then** o nome não fica guardado no
   aparelho para o próximo que usar o mesmo navegador.
6. **Given** um membro da equipe (Atendimento, Gestão ou Segurança do Trabalho) logado, **When** ele faz
   um pedido por um formulário público, **Then** o pedido sai anônimo, como hoje.
7. **Given** alguém sem conta, **When** usa os formulários e a consulta pública, **Then** tudo funciona
   como hoje.

---

### User Story 4 - Sessão que termina no meio do pedido (Priority: P2)

O solicitante abre o formulário logado, demora, e a sessão termina (ou ele sai em outra aba) antes de
enviar. O envio não vira um pedido anônimo sem ele perceber: é recusado com a explicação, e os
materiais continuam no pedido para ele entrar de novo e enviar.

**Why this priority**: um pedido anônimo por engano sairia da lista dele e abriria na consulta pública,
o contrário da privacidade prometida.

**Independent Test**: abrir o formulário logado, encerrar a sessão, enviar e conferir a recusa, os
materiais mantidos e que nada foi gravado.

**Acceptance Scenarios**:

1. **Given** um formulário aberto com a conta A, **When** ele é enviado sem sessão, **Then** o envio é
   recusado com "Sua sessão terminou. Entre de novo para enviar; os materiais continuam aqui.", nada é
   gravado e o carrinho é mantido.
2. **Given** o mesmo formulário, **When** ele é enviado com a sessão de outra conta, **Then** é recusado
   do mesmo jeito.
3. **Given** um formulário aberto sem conta, **When** ele é enviado por alguém que entrou depois,
   **Then** o pedido sai anônimo (vale a situação de quando a página abriu) e a tela de sucesso diz isso.

---

### User Story 5 - O almoxarifado cria e mantém as contas (Priority: P1)

O chefe cria a conta no admin com matrícula, nome completo, senha inicial e o papel Solicitante, e
entrega a senha à pessoa. No primeiro acesso, o sistema exige trocar a senha. Quando a pessoa esquece a
senha, o chefe define outra no admin, e a troca volta a ser exigida.

**Why this priority**: sem cadastro aberto e sem e-mail (F3), é o único jeito de uma conta existir.

**Independent Test**: criar uma conta, entrar com a senha inicial, ser levado à troca, trocar e cair em
"Meus pedidos"; redefinir no admin e ver a troca exigida de novo.

**Acceptance Scenarios**:

1. **Given** uma conta nova de solicitante, **When** a pessoa entra com a senha inicial, **Then** é
   levada à troca de senha e, até trocar, só abre a troca e o Sair.
2. **Given** a senha trocada, **When** ela entra de novo, **Then** cai em "Meus pedidos".
3. **Given** o chefe define uma senha nova no admin, **When** a pessoa entra com ela, **Then** a troca é
   exigida de novo.
4. **Given** o chefe marca Solicitante junto com Atendimento, Gestão ou Segurança do Trabalho, **When**
   salva, **Then** o admin recusa com a explicação de que solicitante não pode ter papel interno.
5. **Given** um solicitante, **When** ele abre qualquer página da área interna, **Then** é recusado
   (spec 012).
6. **Given** as contas da equipe que já existem, **When** esta mudança é implantada, **Then** nenhuma é
   obrigada a trocar a senha.

---

### User Story 6 - Limite de tentativas no login (Priority: P2)

Quem erra a senha muitas vezes seguidas fica bloqueado por um tempo, na página de entrar e no login do
admin. O bloqueio é por matrícula e origem juntas, para um erro repetido num aparelho não travar o login
de todo mundo.

**Why this priority**: o login passa de 3 pessoas da equipe para muitos funcionários, cuja senha protege
os próprios pedidos, e hoje não tem limite nenhum (F2).

**Independent Test**: errar a senha de uma matrícula até o limite, ver a página de bloqueio, ver que
outra matrícula entra normalmente e que a primeira volta a entrar depois do tempo de espera.

**Acceptance Scenarios**:

1. **Given** uma matrícula com tentativas erradas até o limite, **When** ela tenta de novo, **Then** vê
   a página de bloqueio em português: "Muitas tentativas. Tente de novo em alguns minutos ou procure o
   almoxarifado."
2. **Given** essa matrícula bloqueada, **When** outra matrícula entra da mesma origem, **Then** entra
   normalmente.
3. **Given** o tempo de espera passou, **When** a matrícula tenta com a senha certa, **Then** entra, e
   as tentativas erradas são zeradas.
4. **Given** uma matrícula bloqueada, **When** o chefe a desbloqueia no admin, **Then** ela entra na hora.
5. **Given** o login do admin, **When** alguém erra a senha até o limite, **Then** o mesmo bloqueio vale.
6. **Given** qualquer recusa por senha errada antes do limite, **When** ela aparece, **Then** a mensagem
   continua "Matrícula ou senha incorretas.", sem dizer se a matrícula existe.

### Edge Cases

- **Conta desativada no admin**: não entra (recusa genérica); os pedidos ficam ligados a ela e
  continuam só para a equipe, no painel. Se for reativada, a lista volta.
- **Nome da conta alterado depois**: os pedidos antigos guardam o nome de quando foram feitos; a lista
  e os pedidos não mudam.
- **Solicitante com papel interno por engano** (antes da recusa do admin existir, ou por migração): a
  regra de "nega por padrão" da 012 continua valendo; a combinação é recusada no próximo salvamento.
- **Pedido de EPI com conta**: o fluxo da autorização (spec 008) não muda; a Segurança do Trabalho vê o
  nome gravado, como hoje, e o aviso no Telegram não muda.
- **Reenvio do mesmo pedido** (a tela não respondeu e a pessoa enviou de novo): continua não
  duplicando; a conta faz parte do que é conferido, então um reenvio com outra conta é "divergente".
- **Bloqueio por matrícula usado para atrapalhar alguém** (errar a senha de outra pessoa de propósito):
  o bloqueio é temporário e o chefe desbloqueia; como a origem entra junto, isso depende de onde vem o
  ataque (ver F8 e Assumptions).
- **Origem igual para todos** (se o servidor não enxergar o endereço do aparelho, F8): o bloqueio por
  matrícula e origem vira, na prática, bloqueio por matrícula; nunca um bloqueio de todo mundo.
- **Equipe abrindo "Meus pedidos"**: é levada ao seu ponto de partida (painel ou fila de autorizações).
- **Sem conta abrindo "Meus pedidos"**: vai à página de entrar e volta à lista depois.

## Requirements *(mandatory)*

### Functional Requirements

**Conta e acesso**

- **FR-001**: O sistema DEVE ter um papel **Solicitante**, criado na implantação, sem nenhuma permissão
  da área interna (spec 012).
- **FR-002**: O admin DEVE recusar, ao salvar, um usuário que tenha o papel Solicitante junto com
  Atendimento, Gestão ou Segurança do Trabalho, com uma mensagem que diga por quê.
- **FR-003**: Não DEVE haver cadastro aberto: contas de solicitante só são criadas no admin.
- **FR-004**: Depois de entrar, o solicitante DEVE ir para "Meus pedidos"; a equipe continua indo para o
  seu ponto de partida (spec 012 e spec 008).
- **FR-005**: O layout público DEVE oferecer "Entrar" a quem não está logado e "Meus pedidos" e "Sair" ao
  solicitante logado.
- **FR-006**: Uma conta de solicitante DEVE ser obrigada a trocar a senha no primeiro acesso e depois de
  cada senha definida pelo admin; enquanto não trocar, só abre a troca de senha e o Sair. A troca segue
  as regras de senha do sistema.
- **FR-007**: As contas que já existem na implantação NÃO DEVEM ser obrigadas a trocar a senha.

**Limite de tentativas**

- **FR-008**: As duas portas de login (a página de entrar e o login do admin) DEVEM bloquear
  temporariamente, depois de um número de tentativas erradas, a combinação de matrícula e origem; nunca
  só a origem.
- **FR-009**: O número de tentativas e o tempo de bloqueio DEVEM ser configuráveis no ambiente, com
  padrões documentados.
- **FR-010**: O bloqueio DEVE ser mostrado numa página em português, no layout público; antes do limite,
  a recusa continua genérica e igual à de hoje.
- **FR-011**: O login certo DEVE zerar as tentativas erradas da matrícula, e o administrador DEVE poder
  desbloquear uma matrícula no admin.

**Pedido com conta**

- **FR-012**: O pedido DEVE ficar ligado à conta quando é registrado por um solicitante logado, e só
  nesse caso; a equipe logada e quem não tem conta fazem pedido anônimo, como hoje.
- **FR-013**: Para o solicitante logado, o nome do pedido DEVE ser o da conta: o formulário o mostra sem
  edição e o servidor ignora o nome enviado.
- **FR-014**: Para o solicitante logado, o destino DEVE vir sugerido com o do último pedido da conta no
  mesmo formulário, e o nome NÃO DEVE ficar guardado no aparelho.
- **FR-015**: O formulário DEVE levar, de forma que não possa ser forjada, se foi aberto com uma conta e
  qual; o envio de um formulário aberto com uma conta, feito sem essa mesma conta logada, DEVE ser
  recusado sem gravar nada, com a mensagem da User Story 4, mantendo o carrinho.
- **FR-016**: A tela de sucesso do pedido com conta DEVE levar a "Meus pedidos" em vez de pedir para
  guardar o número e oferecer a consulta pública.
- **FR-017**: Todas as proteções atuais dos formulários públicos (campo isca, tempo mínimo, token,
  limites, reenvio sem duplicar, autorização de EPI, aviso no Telegram) DEVEM continuar valendo para o
  pedido com conta.

**Meus pedidos e privacidade**

- **FR-018**: "Meus pedidos" DEVE listar só os pedidos ligados à conta logada, do mais novo para o mais
  antigo, em páginas de 20, com o número, o formulário, a data e o selo da situação.
- **FR-019**: A página do pedido DEVE mostrar a situação com os selos e mensagens da spec 011, o destino,
  a observação e o nº da ocorrência informados, cada material pedido com a quantidade pedida e a
  entregue, a troca ("trocado por <material>") e o motivo da recusa de EPI.
- **FR-020**: A página do pedido NUNCA DEVE mostrar quem atendeu ou decidiu, o recebedor, o centro de
  custo, a placa, o tipo de saída, a situação no SCPI, o número da requisição nem os materiais
  acrescentados pelo almoxarifado.
- **FR-021**: Um pedido que não é da conta logada (de outra conta ou anônimo) DEVE ter a mesma resposta
  de um número inexistente em "Meus pedidos".
- **FR-022**: A consulta pública (spec 011) DEVE responder a um pedido ligado a uma conta exatamente
  como a um número inexistente.
- **FR-023**: As páginas de "Meus pedidos" NÃO DEVEM ser guardadas em cache.
- **FR-024**: As rotas de "Meus pedidos" DEVEM entrar na tabela de rotas da spec 012 como área do
  solicitante: só o papel Solicitante as abre; a equipe é levada ao seu ponto de partida; elas não
  entram na lista fechada da Segurança do Trabalho.

**Implantação**

- **FR-025**: A implantação NÃO DEVE mudar nada para quem não tem conta: formulários, consulta pública e
  pedidos antigos seguem iguais, e os pedidos antigos ficam anônimos.

### Key Entities

- **Conta de solicitante**: um usuário do sistema com o papel Solicitante; matrícula, nome completo,
  senha e a marca de troca obrigatória da senha.
- **Pedido** (existente): ganha a ligação opcional com a conta que o fez; o nome gravado continua sendo
  o texto que a equipe, o recibo e o Telegram já usam.
- **Tentativa de login**: o registro das tentativas por matrícula e origem, com o bloqueio temporário.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um solicitante encontra a situação de qualquer pedido feito com a conta em no máximo 2
  toques depois de entrar, sem digitar número.
- **SC-002**: 100% das tentativas de abrir um pedido de outra conta, pela página ou pela consulta
  pública, têm a mesma resposta de um número inexistente.
- **SC-003**: Logado, o solicitante não digita o nome em nenhum pedido e, a partir do segundo pedido num
  formulário, não digita o destino.
- **SC-004**: 0 pedido de uma conta é gravado como anônimo por sessão terminada no meio do envio.
- **SC-005**: Uma matrícula é bloqueada depois do limite de tentativas erradas, e um erro repetido numa
  matrícula nunca impede outra matrícula de entrar.
- **SC-006**: O chefe cria uma conta de solicitante e entrega a senha em menos de 2 minutos.
- **SC-007**: No dia da implantação, 0 mudança para quem pede sem conta e 0 conta da equipe obrigada a
  trocar a senha.

## Assumptions

- O solicitante tem matrícula e a usa para entrar, como a equipe.
- Sem envio de e-mail, a senha esquecida é redefinida pelo almoxarifado no admin.
- O solicitante usa o celular ou um computador do setor, às vezes dividido com outras pessoas.
- O servidor enxerga o endereço do aparelho, ou ao menos um endereço que não é o mesmo para todos; isso
  é conferido no servidor real antes da implementação (F8). Se não enxergar, o bloqueio vale na prática
  por matrícula, o que ainda atende ao SC-005.
- A mudança de senha pelo próprio solicitante, fora da troca obrigatória, usa a mesma página de troca.
- Os pedidos feitos com conta continuam aparecendo para a equipe no painel exatamente como hoje.

## Fora do escopo

- Cadastro aberto, confirmação por e-mail e "esqueci a senha" pelo próprio solicitante.
- Avisos ao solicitante (e-mail, Telegram, notificação) quando o pedido muda.
- Ligar à conta pedidos feitos antes, por nome ou à mão.
- Formulário que exige conta.
- Editar ou cancelar o pedido pelo solicitante.
- Login único, dois fatores ou diretório externo.
