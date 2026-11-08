# Feature Specification: Papéis de acesso na área interna

**Feature Branch**: `claude/papeis-de-acesso`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: papéis de acesso (RBAC) na área interna do Central Almoxarifado. Hoje
todo usuário logado faz tudo na área interna, exceto a Segurança do Trabalho (lista fechada de
rotas, spec 008) e as gravações da página Formulários (spec 009). A equipe real é o **chefe do
almoxarifado** (dono do sistema) e **2 funcionários que atendem pedidos**. Decisões do usuário em
2026-11-08, antes desta especificação: (1) a página **Automações inteira** (ver, simular, lançar no
SCPI, resolver travas, corrigir requisição, conferir, atualizar catálogo, importar) fica **só para o
chefe**; (2) as gravações da página Formulários continuam exigindo o critério da spec 009 (acesso ao
admin mais a permissão do cadastro); (3) **toda recusa de acesso é registrada no log**, com usuário,
rota e método; (4) a Segurança do Trabalho continua como está. Desenho combinado: o sistema pergunta
por **permissões** e os **papéis** são pacotes de permissões montados pelo administrador; uma tabela
diz qual permissão cada rota interna exige, e um teste falha quando aparece rota interna fora dela;
no dia da implantação **ninguém perde acesso**, e o chefe restringe depois.

## Contexto

Fatos do código em 2026-11-08 (branch `develop`, `16f317c`):

| # | Fato | Onde |
|---|------|------|
| F1 | As views da área interna só exigem login: painel, detalhe, atendimento, edição, saída avulsa, recibos e **todas** as ações de Automações, inclusive o lançamento real no SCPI, a liberação de lote em verificar e a correção do número da requisição. | `pedidos/views/almoxarifado.py`, `automacoes/views.py` |
| F2 | A única barreira do lançamento real é `LANCAMENTO_REAL` no `.env`: vale para o ambiente, não para a pessoa. | `config/settings.py`, `automacoes.views.lancar` |
| F3 | A Segurança do Trabalho é o único papel: participação no grupo `Segurança do Trabalho`, com um middleware que nega por padrão tudo fora de `ROTAS_SEGURANCA_TRABALHO`, e um teste que percorre todas as rotas nomeadas. É verificada pelo grupo, nunca por permissão, porque o superusuário passa em qualquer permissão e a decisão de um EPI precisa ser da Segurança do Trabalho. | `contas/acesso.py`, `contas/middleware.py`, `tests/test_epis_acesso.py` |
| F4 | As gravações da página Formulários exigem acesso ao admin mais `catalogo.change_centrocusto` ou `catalogo.change_excecaomaterial`; ver é de todo usuário logado. | `catalogo/acesso.py` |
| F5 | No menu, só "Cadastros" (o admin) depende do usuário (acesso ao admin); o resto aparece para todos. | `interface/navegacao.py` |
| F6 | O painel tem o cartão do lançamento (requisições pendentes e travadas, com o botão que manda ao lançamento) e os avisos de saúde do catálogo, que levam a Automações. | `pedidos/templates/pedidos/painel.html` |
| F7 | Os robôs agendados (`deploy/crontab`) e os comandos do terminal rodam sem usuário. | `deploy/tarefa.sh`, `management/commands` |
| F8 | O sistema já registra quem fez cada ação (quem iniciou a execução, quem acrescentou o material, o histórico de alterações do atendimento): há registro, falta autorização. | `ExecucaoRobo.iniciada_por`, `ItemPedido.adicionado_por`, `AlteracaoPedido` |
| F9 | Recusa de acesso hoje não deixa rastro no log. | — |

Rotas internas que esta spec classifica (as públicas e as da Segurança do Trabalho não mudam):

| Área | Rotas |
|---|---|
| Painel e pedidos | `pedidos:painel`, `pedidos:detalhe`, `pedidos:marcar_impressos` |
| Atendimento | `pedidos:atender`, `pedidos:atendimento_materiais`, `pedidos:atendimento_adicionar` |
| Edição do atendimento | `pedidos:editar` |
| Saída avulsa | `pedidos:avulsa`, `pedidos:avulsa_materiais`, `pedidos:avulsa_carrinho` |
| Automações | `automacoes:pagina`, `atualizar`, `importar`, `lancar`, `resolver`, `conferir`, `corrigir` |
| Curva ABC | `catalogo:curva` |
| Formulários (leitura) | `catalogo:formularios`, `catalogo:formularios_material` |
| Formulários (gravação, spec 009) | `catalogo:formularios_centros`, `formularios_ativo`, `formularios_excecao`, `formularios_lote`, `formularios_regra` |

## Clarifications

### Session 2026-11-08

- Q: Os funcionários que atendem também registram saída avulsa? → A: Sim, saída avulsa faz parte do
  papel Atendimento.
- Q: Depois de confirmado (e antes de o robô lançar), quem edita o atendimento? → A: Os funcionários
  também: a edição faz parte do papel Atendimento, para qualquer atendimento ainda não lançado.
- Q: Os funcionários veem a Curva ABC e a página Formulários, só para leitura? → A: Não. As duas ficam
  só com o chefe, como Automações.

Com isso, os papéis ficam:

| Papel | Quem | O que abre |
|---|---|---|
| **Atendimento** | os 2 funcionários e o chefe | painel, detalhe do pedido, recibos, atendimento, edição do atendimento, saída avulsa |
| **Gestão** | só o chefe | Automações inteira, Curva ABC e página Formulários (leitura; a gravação segue a spec 009) |
| Segurança do Trabalho | sem mudança | a fila de autorização de EPIs (spec 008) |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Só o chefe opera as automações (Priority: P1)

O chefe do almoxarifado é o único que abre a página Automações e faz qualquer coisa nela: simular e
lançar no SCPI, resolver travas, corrigir o número de uma requisição, conferir com o SCPI, atualizar
o catálogo e importar. Os funcionários que atendem não veem o item no menu, não veem no painel os
atalhos que levam ao lançamento e, se tentarem abrir a página ou mandar uma ação por outro caminho
(link salvo, URL digitada, formulário antigo aberto), recebem a recusa.

**Why this priority**: o lançamento real no SCPI é irreversível (Princípio III), e liberar um lote em
verificar ou corrigir um número pode levar a uma requisição em dobro. Hoje qualquer usuário logado
faz isso (F1, F2).

**Independent Test**: com um usuário só de atendimento, abrir cada rota de Automações (GET e POST) e
ver a recusa; com o chefe, ver tudo funcionar como hoje.

**Acceptance Scenarios**:

1. **Given** um funcionário que só atende, **When** ele abre o painel, **Then** o menu não tem
   "Automações", e o painel não mostra o cartão do lançamento nem os links dos avisos de saúde para
   Automações.
2. **Given** o mesmo funcionário, **When** ele abre o endereço da página Automações, **Then** recebe a
   página de acesso negado, em português, dizendo que a página é do responsável pelas automações e
   com o caminho de volta ao painel.
3. **Given** o mesmo funcionário com uma página antiga ainda aberta, **When** ele manda "Lançar no
   SCPI", "Simular", "Liberar", "É esta", "Corrigir", "Conferir agora", "Atualizar agora" ou uma
   importação, **Then** o servidor recusa sem iniciar processo, sem mudar nenhuma linha e sem ocupar a
   trava do robô.
4. **Given** o chefe, **When** ele usa a página Automações, **Then** tudo funciona exatamente como
   antes desta spec.
5. **Given** um caminho que não passa pela página (uma tela futura, outro botão) e chega ao início do
   lançamento real com um usuário sem a permissão de automações, **When** o lançamento seria
   iniciado, **Then** ele é recusado ali também, antes de qualquer execução ser criada.

---

### User Story 2 - Funcionário que atende só vê o que precisa (Priority: P1)

O funcionário entra, cai no painel, abre o pedido, confirma o atendimento, imprime o recibo, corrige
um atendimento ainda não lançado e registra saída avulsa, como hoje. A Curva ABC e a página
Formulários, como Automações, ficam só com o chefe.

**Why this priority**: é o uso diário de 2 das 3 pessoas da equipe; a restrição não pode atrapalhar o
atendimento.

**Independent Test**: com um usuário só de atendimento, atender um pedido do começo ao fim e imprimir
o recibo, sem nenhuma recusa.

**Acceptance Scenarios**:

1. **Given** um funcionário com o papel Atendimento, **When** ele atende um pedido e imprime o
   recibo, **Then** tudo funciona como hoje.
2. **Given** o mesmo funcionário, **When** ele registra uma saída avulsa, **Then** tudo funciona como
   hoje.
3. **Given** um pedido atendido (por ele ou por outra pessoa) cujo lote ainda não foi lançado,
   **When** o funcionário edita o atendimento, **Then** a edição funciona como hoje, com as mesmas
   travas do robô e o mesmo histórico de alterações.
4. **Given** o mesmo funcionário, **When** ele abre o painel, **Then** o menu mostra só "Painel" e
   "Saída avulsa".
5. **Given** o mesmo funcionário, **When** ele abre o endereço da Curva ABC ou da página Formulários,
   **Then** recebe a página de acesso negado, como em Automações.

---

### User Story 3 - O chefe dá e tira papéis sem programar (Priority: P2)

O chefe (como administrador) diz no admin, marcando papéis no formulário do usuário, o que cada
pessoa pode fazer. Um funcionário novo nasce sem papel nenhum e, até receber um, vê só uma página que
explica que o usuário ainda não tem acesso e a quem pedir. No caso de hoje, o chefe tira o papel Gestão dos 2
funcionários e os deixa só com Atendimento.

**Why this priority**: sem isso a restrição dependeria de mudar código a cada pessoa que entra ou
sai.

**Independent Test**: criar um usuário, entrar com ele e ver a página "sem acesso"; marcar o papel de
atendimento e ver o painel; desmarcar e ver a recusa de novo, sem reiniciar nada.

**Acceptance Scenarios**:

1. **Given** um usuário recém-criado sem papel, **When** ele entra, **Then** vê a página de acesso
   negado com a explicação e o botão Sair, e não vê nenhum pedido.
2. **Given** o administrador marca o papel Atendimento nesse usuário, **When** o usuário recarrega a
   página, **Then** cai no painel.
3. **Given** o administrador tira o papel, **When** o usuário faz a próxima ação, **Then** ela é
   recusada, mesmo com a página já aberta.
4. **Given** o superusuário, **When** ele usa qualquer página interna, **Then** passa, exceto a decisão
   das autorizações de EPI, que continua só da Segurança do Trabalho.

---

### User Story 4 - Nada muda para ninguém no dia da implantação (Priority: P1)

A produção tem usuários reais. No dia em que esta mudança entra, todos os usuários ativos que não são
da Segurança do Trabalho continuam fazendo exatamente o que faziam. O chefe restringe depois, pelo
admin, tirando o papel Gestão dos 2 funcionários.

**Why this priority**: uma implantação que tira acesso de quem atende para o almoxarifado no meio do
expediente.

**Independent Test**: num banco com usuários de antes da mudança, aplicar a migração e conferir que
cada usuário ativo fora da Segurança do Trabalho tem todos os papéis novos, e que a migração para com
erro se algum ficar sem.

**Acceptance Scenarios**:

1. **Given** o banco antes da mudança, **When** a migração roda, **Then** cada usuário ativo que não é
   da Segurança do Trabalho fica com todos os papéis novos, e a migração confere isso e para com erro
   se não bater.
2. **Given** um usuário da Segurança do Trabalho ou um usuário inativo (como o `planilha` da migração
   do Apps Script), **When** a migração roda, **Then** ele não ganha papel nenhum.
3. **Given** a migração já aplicada, **When** ela é desfeita, **Then** os papéis ficam (podem já ter sido
   ajustados à mão), como a migração do grupo da Segurança do Trabalho.

---

### User Story 5 - Saber quem tentou o que não podia (Priority: P3)

Toda recusa de acesso deixa uma linha no log do sistema com quem tentou, o que tentou e quando, para
o chefe saber se alguém está esbarrando numa restrição (por erro de configuração ou não).

**Why this priority**: o sistema já registra quem fez cada ação (F8); faltam as tentativas recusadas.

**Independent Test**: com um usuário sem permissão, provocar uma recusa e ver a linha no log com os
campos combinados.

**Acceptance Scenarios**:

1. **Given** um funcionário sem o papel Gestão, **When** ele manda um POST para lançar, **Then**
   o log ganha uma linha com a matrícula, a rota, o método, a permissão que faltou e o momento.
2. **Given** o mesmo usuário, **When** a recusa vem do filtro da Segurança do Trabalho ou do critério da
   página Formulários, **Then** a linha também é escrita, no mesmo formato.
3. **Given** qualquer recusa, **When** a linha é escrita, **Then** ela nunca traz o corpo do formulário,
   senhas, tokens nem dados do pedido.

---

### Edge Cases

- **Página aberta que se recarrega sozinha** (a situação e o lançamento de Automações, a faixa da
  edição): se o papel for tirado com a página aberta, a recarga recebe a recusa e a página não é
  apagada (o comportamento atual do HTMX para respostas 4xx); a próxima navegação mostra a página de
  acesso negado.
- **Execução em andamento** quando o papel é tirado: o robô em execução termina normalmente (ele roda
  em processo próprio, sem usuário); só as novas ações são recusadas.
- **Robôs agendados e comandos do terminal** (F7): não têm usuário e não mudam.
- **Aviso no Telegram** com botão que abre o painel ou a fila: o link continua o mesmo; quem o abre
  passa pela verificação de sempre.
- **Superusuário** sem nenhum papel: passa em tudo (permissões), menos na decisão de EPI.
- **Usuário da Segurança do Trabalho que também recebe um papel do almoxarifado**: continua preso à
  lista fechada da spec 008 (o filtro dela vem antes), então o papel não tem efeito; misturar os dois
  não é suportado.
- **Usuário inativo**: não entra, como hoje.
- **Rota interna nova** criada no futuro sem entrada na tabela de permissões: o teste falha; em
  execução, a rota fora da tabela é negada a quem não é superusuário (nega por padrão).
- **Painel sem permissão de automações**: o cartão do lançamento some inteiro (não fica um cartão
  vazio), e os avisos de saúde do catálogo aparecem sem o link para Automações.
- **Recusa de método** (GET num endereço que só aceita POST) e **CSRF**: para quem tem a permissão da
  rota, continuam com as respostas de hoje (405 e 403 do CSRF) e não contam como recusa de acesso no
  log. Para quem não tem, a recusa de acesso vem antes do método: 403 e a linha no log, sem revelar
  quais métodos a rota aceita.

## Requirements *(mandatory)*

### Functional Requirements

**Permissões e papéis**

- **FR-001**: O sistema DEVE definir permissões próprias para as áreas da tabela de rotas do Contexto:
  **atendimento** (painel, detalhe, recibos, atendimento, edição do atendimento e saída avulsa),
  **automações** (a página e todas as suas ações), **Curva ABC** e **leitura da página Formulários**.
  As gravações da página Formulários continuam com o critério da spec 009 (FR-010) e exigem também a
  leitura da página.
- **FR-002**: O sistema DEVE oferecer dois papéis prontos: **Atendimento** (a permissão de
  atendimento) e **Gestão** (automações, Curva ABC e leitura da página Formulários). Os papéis são
  editáveis no admin; o sistema só pergunta pelas permissões, nunca pelo nome do papel.
- **FR-003**: O administrador DEVE poder dar e tirar papéis no formulário do usuário do admin, e a
  mudança DEVE valer na próxima requisição do usuário, sem reiniciar nada.
- **FR-004**: O superusuário DEVE passar em todas as permissões desta spec. A decisão das autorizações
  de EPI continua exigindo a participação no grupo da Segurança do Trabalho (spec 008), não muda.

**Verificação**

- **FR-005**: Cada rota interna DEVE estar declarada numa única tabela de rota para permissão. Rota da
  área interna fora da tabela DEVE ser negada a quem não é superusuário, e um teste automatizado DEVE
  percorrer todas as rotas nomeadas do projeto e falhar quando uma rota interna não está na tabela ou
  quando um usuário sem a permissão consegue abri-la.
- **FR-006**: A verificação DEVE acontecer no servidor, a cada requisição (GET e POST, inclusive as
  requisições do HTMX), antes de qualquer leitura de pedido ou gravação.
- **FR-007**: O início do lançamento real no SCPI DEVE conferir a permissão de automações também no
  ponto em que o processo do robô é iniciado, além da rota; sem ela, nada é criado (nem execução, nem
  trava, nem mudança de linha).
- **FR-008**: A recusa DEVE ser uma página em português, no layout do almoxarifado, que diz o que faltou
  em termos do papel ("Esta página é de quem opera as automações") e oferece o caminho de volta ao
  painel (quando o usuário pode abri-lo) e o Sair. Requisição do HTMX recebe a recusa sem apagar a
  página.
- **FR-009**: O usuário sem nenhum papel DEVE ver, ao entrar, a página de acesso negado com a
  explicação de que o usuário ainda não tem acesso e de que o papel é dado pelo administrador, em vez
  do painel.
- **FR-010**: As gravações da página Formulários DEVEM continuar exigindo acesso ao admin mais a
  permissão do cadastro afetado (spec 009, decisão do usuário em 2026-11-08), e passam a constar da
  mesma tabela de rotas.
- **FR-011**: O filtro da Segurança do Trabalho (spec 008) DEVE continuar valendo como está e antes das
  verificações desta spec.

**Interface**

- **FR-012**: O menu DEVE mostrar só os destinos que o usuário pode abrir.
- **FR-013**: O painel DEVE esconder o cartão do lançamento e os links para Automações, para a Curva
  ABC e para a página Formulários de quem não tem a permissão correspondente; os avisos de saúde
  continuam visíveis, sem o link.
- **FR-014**: Botões de ações que o usuário não pode fazer, numa página que ele pode ver, DEVEM aparecer
  desabilitados com o motivo (o mesmo padrão do lançamento real bloqueado), nunca só escondidos sem
  explicação.

**Implantação**

- **FR-015**: A migração DEVE criar os papéis e dar todos eles a cada usuário ativo que não é da
  Segurança do Trabalho, verificar isso ao fim e parar com erro se algum usuário não ficar com todos;
  desfeita, não apaga papéis.
- **FR-016**: A migração NÃO DEVE dar papel a usuário inativo nem a usuário da Segurança do Trabalho.

**Registro**

- **FR-017**: Toda recusa de acesso (desta spec, do filtro da Segurança do Trabalho e do critério da
  página Formulários) DEVE escrever uma linha no log do sistema com a matrícula do usuário, a rota
  nomeada, o método, a permissão ou regra que faltou e o momento.
- **FR-018**: A linha de recusa NUNCA DEVE trazer o corpo da requisição, senhas, tokens, nomes de
  solicitantes nem dados do pedido.

### Key Entities

- **Permissão**: uma capacidade nomeada (atender, editar atendimento, registrar saída avulsa, operar
  automações, ver a Curva ABC, ver a configuração dos formulários). É o que o sistema pergunta.
- **Papel**: um pacote de permissões com nome (Atendimento, Automações), dado a usuários pelo
  administrador. O sistema nunca pergunta pelo nome.
- **Tabela de rotas**: para cada rota interna, a permissão (ou a regra da spec 009) que ela exige. É a
  fonte única da verificação, do menu e do teste.
- **Recusa registrada**: uma linha do log com usuário, rota, método, o que faltou e o momento.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das rotas internas estão na tabela de permissões, conferido pelo teste a cada
  execução da suíte.
- **SC-002**: Um usuário só com o papel Atendimento recebe recusa em 100% das rotas de Automações (7),
  da Curva ABC (1) e da página Formulários (7), em GET e POST, e nenhuma delas inicia processo, ocupa
  trava ou muda linha.
- **SC-003**: No dia da implantação, 0 usuário ativo do almoxarifado perde acesso a algo que tinha.
- **SC-004**: O chefe tira o papel Gestão dos 2 funcionários pelo admin em menos de 2 minutos, sem
  ajuda de quem programa.
- **SC-005**: Um funcionário com o papel Atendimento atende um pedido do começo ao fim, imprime o
  recibo, edita o atendimento e registra uma saída avulsa sem nenhuma recusa.
- **SC-006**: 100% das recusas de acesso deixam uma linha no log com os 5 campos combinados, e nenhuma
  linha traz dado de pedido ou credencial.

## Assumptions

- O chefe do almoxarifado é superusuário e tem acesso ao admin; é ele quem dá os papéis.
- Os 2 funcionários têm usuários próprios e ativos (não dividem um login).
- As permissões vivem no próprio sistema (sem diretório externo, sem login único).
- Os papéis valem para a área interna; os formulários públicos e a consulta pública não mudam.
- A restrição é por área, não por registro: quem pode atender atende qualquer pedido (não há "só os
  meus pedidos").
- O registro da recusa vai para o log de sempre do sistema, com a retenção que ele já tem; não há tela
  para consultá-lo nesta spec.

## Fora do escopo

- Restrição por registro (pedido de um setor, de uma pessoa).
- Papéis no admin além das permissões nativas que ele já tem.
- Tela de auditoria das recusas.
- Mudanças na Segurança do Trabalho, nos formulários públicos e nos comandos do terminal.
- Autenticação (senha, login único, dois fatores).
