# Feature Specification: Formulário da oficina mecânica

**Feature Branch**: `claude/oficina-mecanica`

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: novo formulário do Central Almoxarifado para a oficina mecânica (previsto
na especificação 005 como "autopeças da oficina mecânica"), integrado aos formulários públicos
existentes e independente da especificação 006. Respostas do usuário em 2026-10-22, antes desta
especificação: o formulário é um **pedido de materiais** ao almoxarifado; quem pede preenche um
formulário **público, sem login**; o pedido pode **indicar a viatura ou o equipamento** (placa
opcional); os materiais oferecidos são os de **grupos do cadastro do SCPI** escolhidos pelo
almoxarifado.

## Contexto

A oficina mecânica mantém as viaturas e os equipamentos motorizados (caminhões, retroescavadeiras,
bombas, compactadores) e retira no almoxarifado as autopeças e os insumos do serviço: pneus,
filtros, óleos e fluidos, aditivos e afins. Hoje não há formulário próprio: o pedido vai pelo
formulário "Ferramentas, peças e materiais" (catálogo AB) ou direto no balcão, como saída avulsa.

O catálogo AB não serve à oficina. Ele é ordenado pelas saídas do almoxarifado inteiro e esconde
grupos inteiros do cadastro (entre eles o grupo `GERAL`, onde está boa parte dos óleos e filtros). O
cadastro do SCPI já separa as autopeças num grupo próprio (`AUTO PECAS`, cerca de 120 materiais
visíveis em 2026-10-22) e há outros grupos ligados à oficina (peças de bombas e motores, veículos e
equipamentos automotores).

As saídas da oficina já são atribuídas por viatura no SCPI: cada viatura ou equipamento tem o seu
centro de custo, identificado pela placa (cerca de 150 cadastrados), e a saída com placa sem centro
próprio vai para o centro `OFICINA MECÂNICA`. O almoxarifado faz essa atribuição no atendimento, que
já tem o campo placa.

Os formulários públicos já compartilham busca, pedido, envio, proteções contra abuso, atendimento,
recibo e lançamento no SCPI (especificação 005). Esta funcionalidade acrescenta um formulário com o
seu próprio conjunto de materiais e a indicação opcional da viatura; o restante do caminho do pedido
é o mesmo.

**Termos.** "Grupos da oficina" é o conjunto de grupos do cadastro do SCPI que o almoxarifado
escolhe para este formulário; "materiais avulsos da oficina" são materiais escolhidos um a um, de
qualquer grupo; os dois juntos são a "escolha da oficina"; "viatura" vale para viatura ou equipamento identificado por placa no
cadastro de centros de custo.

## Clarifications

### Session 2026-10-22

- Q: Qual processo da oficina mecânica o formulário atende? → A: pedido de materiais ao
  almoxarifado (autopeças, óleos, filtros, pneus etc.), que segue atendimento, recibo e lançamento no
  SCPI como os outros formulários. Não é registro de ordem de serviço nem de manutenção.
- Q: Quem preenche e com que acesso? → A: formulário público, sem login, como os atuais.
- Q: O pedido identifica a viatura ou o equipamento? → A: opcionalmente: às vezes o material é para
  uma viatura, às vezes para a própria oficina.
- Q: Quais materiais o formulário oferece? → A: os dos grupos do cadastro do SCPI ligados à oficina,
  escolhidos pelo almoxarifado.
- Q: Qual é o destino do pedido da oficina? → A: ou o centro de custo OFICINA MECÂNICA, ou um centro
  de custo com placa (a viatura ou o equipamento). Destino e viatura são o mesmo campo: escolher a
  OFICINA MECÂNICA é o pedido sem viatura.
- Q: Como a oficina chega aos óleos e filtros do grupo `GERAL` (~5.000 materiais de tudo)? → A: além
  dos grupos, o almoxarifado pode incluir materiais avulsos na escolha da oficina, sem trazer o grupo
  inteiro.
- Q: O pedido da oficina traz um número de referência do serviço (nº da ordem de serviço)? → A: não;
  só o cabeçalho comum, e a observação livre basta.
- Q: O que a oficina faz com material sem estoque (93 dos 121 materiais de `AUTO PECAS` com saldo
  zero em 2026-10-22)? → A: como nos outros formulários: aparece bloqueado ("Sem estoque") e não pode
  ser pedido; a quantidade vai até o estoque disponível (FR-004).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pedir materiais da oficina (Priority: P1)

Quem trabalha na oficina abre o formulário da oficina mecânica, procura os materiais pelo nome entre
os da escolha da oficina, escolhe as quantidades, informa o próprio nome e envia. O almoxarifado
recebe o pedido como recebe os dos outros formulários.

**Why this priority**: É o motivo do formulário: dar à oficina um catálogo com os seus materiais,
sem o ruído do catálogo AB e sem os materiais que ele esconde.

**Independent Test**: Com a escolha da oficina definida e saldo importado, abrir o formulário,
buscar e adicionar dois materiais desses grupos, informar o nome e enviar; o pedido aparece no
painel do almoxarifado identificado como da oficina mecânica.

**Acceptance Scenarios**:

1. **Given** materiais visíveis com saldo na escolha da oficina, **When** o funcionário digita parte
   do nome de um deles, **Then** o material aparece nos resultados com nome, unidade e estoque
   disponível, como nos outros formulários públicos.
2. **Given** um material de um grupo que não é da oficina, **When** o funcionário o procura,
   **Then** ele não aparece.
3. **Given** um material que o catálogo AB esconde (por exemplo, um óleo do grupo `GERAL`) incluído
   entre os materiais avulsos da oficina, **When** o funcionário o procura, **Then** ele aparece.
4. **Given** um pedido com materiais e nome válidos, **When** o funcionário envia, **Then** o pedido
   é registrado com número próprio da sequência dos pedidos públicos, a tela de sucesso mostra o
   número, e o almoxarifado é avisado como nos outros formulários.
5. **Given** um pedido registrado por este formulário, **When** o almoxarifado consulta o painel,
   **Then** o pedido aparece com o nome deste formulário, pode ser filtrado por ele, e o
   atendimento, o recibo e o lançamento no SCPI seguem o caminho dos pedidos dos outros
   formulários.

---

### User Story 2 - Indicar a viatura do pedido (Priority: P2)

Quando o material é para uma viatura ou um equipamento, o funcionário a escolhe como destino do
pedido, no lugar da oficina, e o almoxarifado já a vê ao atender, sem precisar perguntar.

**Why this priority**: A saída da oficina é atribuída por viatura no SCPI; sem a indicação, o
almoxarifado precisa descobri-la no balcão. Mas o pedido sem viatura já entrega valor (US1).

**Independent Test**: Enviar um pedido com destino numa viatura cadastrada e outro com destino na
OFICINA MECÂNICA; no detalhe e no atendimento, o primeiro mostra a viatura (centro e placa) e o
segundo, a oficina.

**Acceptance Scenarios**:

1. **Given** o formulário aberto, **When** o funcionário abre o destino, **Then** vê a OFICINA
   MECÂNICA e as viaturas cadastradas (centros de custo com placa), e nenhum outro centro.
2. **Given** o destino numa viatura, **When** o pedido é registrado, **Then** o almoxarifado vê o
   centro e a placa no detalhe, no atendimento e no recibo.
3. **Given** o destino na OFICINA MECÂNICA, **When** o pedido é registrado, **Then** ele segue
   normalmente, sem viatura.
4. **Given** um destino digitado ou enviado que não é a OFICINA MECÂNICA nem uma viatura cadastrada,
   **When** o funcionário envia, **Then** o envio é recusado com a mensagem de destino inválido de
   hoje e o pedido é mantido para correção.
5. **Given** um pedido com destino numa viatura, **When** o almoxarifado abre o atendimento,
   **Then** o centro de custo e a placa da saída já vêm sugeridos pelo destino, como nos outros
   formulários, e ele pode trocá-los.

---

### User Story 3 - Escolher os materiais da oficina (Priority: P2)

Quem mantém os cadastros no almoxarifado escolhe quais grupos do cadastro o formulário oferece e
acrescenta materiais avulsos de outros grupos (como os óleos e filtros do grupo `GERAL`), sem
depender de uma nova versão do sistema. A situação do formulário aparece na saúde do catálogo como
a dos outros formulários.

**Why this priority**: Os grupos do SCPI mudam com o tempo; sem a escolha pelo almoxarifado, o
formulário ficaria preso ao que existia na publicação. Mas uma configuração inicial basta para a US1.

**Independent Test**: Incluir um grupo na escolha e retirar outro; no próximo acesso, os materiais do
incluído aparecem e os do retirado não.

**Acceptance Scenarios**:

1. **Given** quem mantém os cadastros, **When** inclui um grupo do cadastro entre os da oficina,
   **Then** os materiais visíveis dele passam a aparecer no formulário no próximo acesso.
2. **Given** um grupo da oficina, **When** é retirado da escolha, **Then** os seus materiais deixam
   de aparecer neste formulário (salvo os incluídos como avulsos); nos outros formulários nada muda.
3. **Given** um material de um grupo que não é da oficina, **When** quem mantém os cadastros o inclui
   entre os materiais avulsos, **Then** só ele, e não o grupo inteiro, passa a aparecer no formulário
   no próximo acesso.
4. **Given** a saúde do catálogo, **When** o almoxarifado a consulta, **Then** ela mostra quantos
   materiais o formulário da oficina oferece, ou que ele está indisponível e por quê.

---

### Edge Cases

- **Escolha vazia, ou sem material visível.** O formulário fica indisponível, com a
  mesma mensagem dos outros formulários públicos, e a saúde do catálogo diz o motivo.
- **Saldo nunca importado.** O formulário fica indisponível, como os outros formulários públicos.
- **Todos os materiais sem estoque.** Abre com o aviso "Nenhum material deste formulário tem estoque
  agora.", como os outros formulários; os materiais aparecem bloqueados ("Sem estoque").
- **Grupo escolhido que some do cadastro.** Não oferece nada; a saúde do catálogo avisa o grupo da
  escolha que não tem nenhum material visível.
- **Material com código repetido no cadastro.** Aparece bloqueado, como nos outros formulários.
- **Material de um grupo da oficina que também está na lista de limpeza, no catálogo AB ou na lista
  das peças das viaturas.** Aparece neste formulário também; as escolhas de um formulário não tiram
  material dos outros.
- **Viatura digitada pela placa, com ou sem hífen, em minúsculas.** É reconhecida, como o destino
  "centro — placa" nos outros formulários.
- **Centro OFICINA MECÂNICA não cadastrado.** O formulário oferece só as viaturas; sem ele e sem
  nenhuma viatura, fica indisponível, e a saúde do catálogo diz o motivo.
- **Viatura descadastrada entre abrir o formulário e enviar.** O envio é recusado como destino
  inválido, e o pedido é mantido.
- **Material que sai da escolha da oficina (ou fica oculto) entre abrir o formulário e enviar.** O
  envio é recusado com a mensagem de hoje ("O material … não está mais no catálogo."), e o pedido é
  mantido para correção, como nos outros formulários. Pedidos já registrados não mudam.
- **Viatura descadastrada depois do envio.** O pedido registrado não muda; o atendimento aceita
  qualquer centro de custo, como nos outros formulários.
- **Reenvio, envio rápido demais, campo isca, limites por IP e por nome.** Iguais aos dos outros
  formulários públicos, inclusive o limite por nome, que conta os pedidos de todos os formulários
  públicos juntos.
- **Estoque que muda entre abrir o formulário e enviar.** Como nos outros formulários: o envio é
  recusado com o estoque atual e o pedido é mantido para correção.

## Requirements *(mandatory)*

### Functional Requirements

**Formulário**

- **FR-001**: O sistema DEVE oferecer um formulário público, sem login, de pedido de materiais da
  oficina mecânica, listado na página inicial dos formulários junto com os existentes, com título,
  exemplo de busca e ícone próprios.
- **FR-002**: O formulário DEVE ter o cabeçalho comum dos formulários públicos (nome completo,
  destino e observação), as mesmas proteções contra abuso, os mesmos limites e o mesmo requisito de
  JavaScript. Só o conjunto de destinos aceitos é próprio (FR-006).
- **FR-003**: O formulário DEVE oferecer, pela busca por nome, os materiais visíveis do cadastro
  cujo grupo está entre os grupos da oficina e os materiais avulsos da oficina, cada um uma só
  vez, com o estoque disponível e o mesmo texto da busca dos outros formulários públicos; os
  bloqueados ("Sem estoque", código repetido)
  aparecem no fim dos resultados, como hoje.
- **FR-004**: Os materiais DEVEM seguir a mesma regra de quantidade dos formulários públicos: fração
  só em unidade fracionável, teto no estoque disponível exibido, sem limite próprio.
- **FR-005**: O formulário DEVE ficar indisponível, com a mesma mensagem dos outros formulários
  públicos, quando o saldo de estoque nunca foi importado, quando a escolha da oficina não tem
  nenhum material visível ou quando não há destino a oferecer (nem o centro OFICINA MECÂNICA nem
  viatura cadastrada).

**Destino e viatura**

- **FR-006**: O destino DEVE ser o centro de custo OFICINA MECÂNICA ou uma viatura, isto é, um centro
  de custo com placa, oferecida como "centro — placa" e reconhecida também pela placa digitada (com
  ou sem hífen, sem diferença de maiúsculas), como os destinos com placa dos outros formulários. O
  formulário DEVE oferecer só esses destinos, e o envio DEVE recusar qualquer outro com a mensagem
  de destino inválido de hoje, mantendo o pedido. Nos outros formulários, os destinos aceitos não
  mudam.
- **FR-007**: Destino na OFICINA MECÂNICA é o pedido sem viatura; destino numa viatura identifica a
  viatura do pedido. Não há outro campo de viatura.
- **FR-008**: O destino DEVE ser gravado, mostrado e conferido no reenvio como nos outros
  formulários públicos (tela de sucesso, detalhe, recibo, lista do painel), e não muda depois do
  envio.
- **FR-009**: No atendimento, o centro de custo e a placa da saída DEVEM vir sugeridos pelo destino
  do pedido, como nos outros formulários, e o almoxarifado pode trocá-los; daí em diante valem as
  regras de centro de custo e placa do atendimento de hoje.

**Pedido e atendimento**

- **FR-010**: O pedido DEVE ser registrado como os dos outros formulários públicos, com uma origem
  própria que o identifique na lista e no filtro por origem do painel e no aviso ao almoxarifado,
  como as dos outros formulários.
- **FR-011**: Atendimento, trocas e acréscimos pelo almoxarifado, edição do atendimento, recibo e
  lançamento no SCPI DEVEM funcionar para estes pedidos como para os dos outros formulários
  públicos, sem regra própria.

**Grupos da oficina**

- **FR-012**: Quem mantém os cadastros DEVE poder incluir e retirar grupos do cadastro entre os
  grupos da oficina, e a mudança DEVE valer no próximo acesso ao formulário.
- **FR-012a**: Quem mantém os cadastros DEVE poder incluir e retirar materiais do cadastro, de
  qualquer grupo, entre os materiais avulsos da oficina, cada material no máximo uma vez, e a mudança
  DEVE valer no próximo acesso. Um material avulso que também é de um grupo da oficina aparece uma só
  vez. Retirar um material avulso não o tira do formulário se o seu grupo for da oficina.
- **FR-013**: A saúde do catálogo DEVE mostrar quantos materiais o formulário da oficina oferece,
  avisar quando ele estiver indisponível, com o motivo, e listar os grupos da escolha sem nenhum
  material visível e os materiais avulsos que não aparecem por estarem ocultos no SCPI. Sem o
  centro OFICINA MECÂNICA no cadastro, mas com viaturas, o formulário continua disponível e a
  saúde DEVE avisar que o destino da oficina não é oferecido.

**Não regressão**

- **FR-014**: Os formulários existentes (limpeza, "Ferramentas, peças e materiais", reposição de
  peças das viaturas e saída avulsa) DEVEM continuar com o mesmo conteúdo e comportamento.

### Key Entities

- **Escolha da oficina**: os grupos do cadastro do SCPI escolhidos pelo almoxarifado (pelo nome do
  grupo) e os materiais avulsos escolhidos um a um; juntos definem os materiais do formulário. Uma
  só escolha para toda a oficina.
- **Pedido da oficina**: pedido público como os demais, com origem própria; o destino é a OFICINA
  MECÂNICA ou uma viatura; seus itens são materiais da escolha da oficina.
- **Viatura**: veículo ou equipamento identificado pela placa no cadastro de centros de custo, que
  já existe (cada placa é um centro de custo próprio); o formulário só a referencia, não a cadastra.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O funcionário da oficina consegue pedir 3 materiais, com a viatura indicada, em até
  2 minutos no celular, contados de abrir o formulário até a tela com o número do pedido (medido no
  uso real, depois da implantação).
- **SC-002**: 100% dos materiais visíveis da escolha da oficina podem ser achados pela busca do
  formulário, e nenhum material fora dela aparece.
- **SC-003**: 100% dos pedidos com destino numa viatura chegam ao atendimento com o centro de custo
  e a placa já sugeridos.
- **SC-004**: Uma mudança na escolha da oficina aparece no formulário no próximo acesso, sem nova
  publicação do sistema.
- **SC-005**: Os formulários existentes não mudam: seus testes automatizados continuam passando sem
  alteração de comportamento.

## Assumptions

- O público é quem trabalha na oficina, no celular ou no computador da oficina, sem login; os limites
  por IP e por nome e as demais proteções dos formulários públicos bastam.
- A ordem dos resultados da busca segue a regra comum dos formulários públicos (os que podem ser
  pedidos primeiro, os bloqueados no fim, corte de 50); não há ordenação própria da oficina.
- A viatura é escolhida entre os centros de custo com placa já cadastrados pelo almoxarifado; o
  formulário não cria viatura nem centro de custo. O centro OFICINA MECÂNICA é o que tem essa
  descrição no cadastro (o mesmo nome que a regra de centro de custo do atendimento já usa).
- A escolha da oficina (grupos e materiais avulsos) é mantida pela área administrativa que já existe, pelos mesmos
  usuários que mantêm as outras listas. A carga inicial é feita pelo almoxarifado; esta
  especificação não define quais grupos são escolhidos.
- O tipo de saída lançado no SCPI e o robô de lançamento não mudam.
- Nome mostrado ao funcionário: "Oficina mecânica".

### Fora do escopo

- Ordem de serviço, registro da manutenção feita, mecânico responsável, quilometragem ou histórico
  de manutenção por viatura.
- Cadastro de viaturas fora do cadastro de centros de custo.
- Ordem e nome exibido próprios dos materiais, e preenchimento em folha (como na reposição de peças
  das viaturas).
- Número de ordem de serviço ou de ocorrência no pedido (diferente do formulário de reposição de
  peças das viaturas).
- Login, aprovação do pedido ou qualquer etapa nova antes do atendimento.
- Mudanças no catálogo AB, na lista de limpeza, no formulário de reposição de peças das viaturas, no
  robô do SCPI ou no cabeçalho dos outros formulários.
- Painel de configuração dos formulários pela interface (desejo registrado na especificação 006).
