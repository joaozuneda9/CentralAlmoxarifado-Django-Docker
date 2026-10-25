# Feature Specification: Formulário de EPIs

**Feature Branch**: `claude/epis`

**Created**: 2026-10-23

**Status**: Draft

**Input**: User description: novo formulário do Central Almoxarifado para o pedido de Equipamentos de
Proteção Individual (EPIs), integrado aos formulários públicos existentes (especificações 005, 006 e
007). Respostas do usuário em 2026-10-23, antes desta especificação: o pedido é **público, sem login**,
como os outros, mas **passa primeiro por autorização da Segurança do Trabalho**, dentro do sistema e com
acesso próprio; cada pedido é de **um servidor**, identificado pelo "Nome completo"; o recebimento é
comprovado pelo **recibo impresso e assinado em papel**; **nenhum dado extra de EPI** entra no pedido
nesta entrega.

## Contexto

Hoje não há formulário de EPIs. Quem precisa de um EPI pede pelo formulário "Ferramentas, peças e
materiais" (catálogo AB) ou direto no balcão, como saída avulsa, e nenhum desses caminhos passa pela
Segurança do Trabalho: o almoxarifado entrega o que lhe é pedido. O cadastro do SCPI tem materiais de
segurança e EPI em grupo próprio (no cadastro de teste, "MATERIAL DE SEGURANÇA E EPI"); o cadastro real
da produção não foi consultado.

Os formulários públicos já compartilham busca, pedido, envio, proteções contra abuso, painel,
atendimento, edição, recibo, aviso no Telegram e lançamento no SCPI (especificação 005). Esta
funcionalidade acrescenta um formulário com o seu próprio conjunto de materiais e **uma etapa nova antes
do atendimento: a autorização da Segurança do Trabalho**. O restante do caminho do pedido é o mesmo.

**Solicitar não é fornecer.** O sistema nunca baixa estoque por conta própria: o saldo só é substituído
pela importação do SCPI, e o pedido não reserva nada (o estoque é só um teto na hora do envio). Para um
EPI, cada etapa é uma coisa diferente e nenhuma se confunde com o envio do formulário:

1. **Solicitação**: o servidor envia o pedido (comprova só que ele pediu).
2. **Autorização**: a Segurança do Trabalho decide se o pedido segue (etapa nova desta funcionalidade).
3. **Entrega**: o almoxarifado atende o pedido autorizado, registrando as quantidades entregues, o
   recebedor, a data efetiva e quem atendeu (atendimento de hoje).
4. **Recebimento**: o servidor assina o recibo impresso, em papel, fora do sistema (como hoje).
5. **Movimentação do estoque**: a requisição lançada no SCPI pelo robô a partir do atendimento (como
   hoje, sem mudança).

**Termos.** "Segurança do Trabalho" é o setor do SAEP que autoriza os pedidos de EPI; "usuário da
Segurança do Trabalho" é quem dele tem acesso próprio ao sistema (por matrícula); "autorização" é a
decisão de autorizar ou recusar um pedido de EPI; "pedido de EPI" é o pedido feito por este formulário;
"escolha dos EPIs" é o conjunto de materiais do cadastro do SCPI que o formulário oferece.

## Clarifications

### Session 2026-10-23

Respostas do usuário, anteriores à escrita desta especificação:

- Q: Qual processo o formulário de EPIs atende? → A: o mesmo pedido público dos outros formulários
  (sem login, quem pede preenche), mas o pedido passa primeiro por autorização da Segurança do
  Trabalho, e só depois segue ao atendimento do almoxarifado.
- Q: Quem recebe o EPI e como o destinatário é identificado? → A: um servidor por pedido,
  identificado pelo "Nome completo" já existente nos formulários públicos (texto livre). Sem matrícula,
  sem cadastro de servidores e sem pedido para equipe. O recebedor é registrado no atendimento, como
  hoje.
- Q: Como o recebimento é comprovado? → A: pelo recibo impresso que o sistema já emite no atendimento,
  assinado em papel fora do sistema. Sem assinatura eletrônica nem biometria.
- Q: Que dados extras de EPI entram no pedido? → A: nenhum por enquanto. Valem só material,
  quantidade, destinatário e observação livre. Tamanho, CA e motivo (primeira entrega ou reposição)
  ficam fora desta entrega.
- Q: Como a Segurança do Trabalho autoriza? → A: dentro do sistema, com acesso próprio: quem é da
  Segurança do Trabalho tem usuário (matrícula) e vê só a fila de pedidos de EPI para autorizar; fica
  gravado quem autorizou e quando. O sistema hoje não tem papéis (todo usuário logado vê o painel
  inteiro): a separação do que esse usuário enxerga é requisito desta funcionalidade.
- Q: O que quem autoriza pode fazer? → A: autorizar ou recusar, com motivo. Não altera materiais nem
  quantidades. Autorizado, o pedido segue ao atendimento; recusado, fica encerrado com o motivo.
- Q: O que o almoxarifado vê e recebe antes da autorização? → A: vê o pedido no painel como
  "Aguardando autorização", bloqueado para atendimento; o aviso do Telegram ao almoxarifado só sai
  depois de autorizado.
- Q: Quem é avisado de que há pedido esperando autorização? → A: a Segurança do Trabalho, por um
  aviso novo do Telegram, para um segundo chat próprio dela.
- Q: Quais materiais do SCPI o formulário oferece e como o almoxarifado mantém a escolha? → A: grupos
  inteiros do SCPI mais materiais avulsos de outros grupos, mantidos pelo admin, como na oficina.
- Q: Como o servidor, sem login, fica sabendo se o pedido foi autorizado ou recusado? → A: por uma
  página pública de consulta pelo número do pedido, que mostra só a situação e o motivo da recusa, sem
  nome nem materiais.
- Q: Além dos usuários da Segurança do Trabalho, alguém mais pode autorizar ou recusar? → A: só a
  Segurança do Trabalho.
- Q: A Segurança do Trabalho precisa extrair um relatório dos EPIs fornecidos (NR-6, 6.5.1.1)? → A: não
  nesta entrega; fica como pendência de validação normativa. O painel já lista e filtra os pedidos.
- Q: Depois de autorizado ou recusado, a decisão pode ser desfeita? → A: não, é definitiva. Se foi um
  engano, o servidor faz um pedido novo.
- Decisão de escopo do usuário: a autorização da Segurança do Trabalho, com o acesso próprio e o
  aviso acima, é a **única etapa nova** desta funcionalidade. Não é um sistema de gestão de Segurança
  do Trabalho nem um fluxo de aprovação genérico.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pedir um EPI (Priority: P1)

O servidor que precisa de um EPI abre o formulário de EPIs, procura o material pelo nome, escolhe as
quantidades, informa o próprio nome completo e envia. O pedido fica aguardando a autorização da
Segurança do Trabalho.

**Why this priority**: É a entrada do processo: sem o pedido identificado e com materiais de EPI, não há
o que autorizar nem entregar.

**Independent Test**: Com a escolha dos EPIs definida e o saldo importado, abrir o formulário, buscar e
adicionar dois materiais, informar o nome e enviar; a tela de sucesso mostra o número e o pedido aparece
no painel como "Aguardando autorização".

**Acceptance Scenarios**:

1. **Given** materiais visíveis com saldo na escolha dos EPIs, **When** o servidor digita parte do nome
   de um deles, **Then** o material aparece nos resultados com nome, unidade e estoque disponível, como
   nos outros formulários públicos.
2. **Given** um material fora da escolha dos EPIs, **When** o servidor o procura, **Then** ele não
   aparece.
3. **Given** um pedido com materiais e nome válidos, **When** o servidor envia, **Then** o pedido é
   registrado com número próprio da sequência dos pedidos públicos, a tela de sucesso mostra o número e
   diz que o pedido **aguarda a autorização da Segurança do Trabalho**, sem sugerir que o EPI já será
   entregue.
4. **Given** um pedido de EPI recém-registrado, **When** o almoxarifado consulta o painel, **Then** o
   pedido aparece identificado como de EPIs, na situação "Aguardando autorização", e o aviso do Telegram
   ao almoxarifado **não** sai.
5. **Given** um pedido de EPI recém-registrado, **When** o aviso para a Segurança do Trabalho é
   configurado, **Then** a Segurança do Trabalho é avisada de que há pedido esperando autorização; sem a
   configuração, o pedido segue registrado sem aviso, e uma falha do aviso nunca desfaz o pedido.

---

### User Story 2 - Autorizar ou recusar o pedido (Priority: P1)

Quem é da Segurança do Trabalho entra com a sua matrícula, vê a fila dos pedidos de EPI que aguardam
decisão, abre um pedido e o autoriza ou o recusa, informando o motivo da recusa.

**Why this priority**: É a razão de ser da etapa nova: sem a decisão gravada, o pedido não chega ao
atendimento.

**Independent Test**: Com um pedido aguardando e um usuário da Segurança do Trabalho, autorizar um pedido
e recusar outro (com motivo); o primeiro passa a poder ser atendido e o segundo fica encerrado, ambos com
quem decidiu e quando.

**Acceptance Scenarios**:

1. **Given** pedidos de EPI aguardando, **When** um usuário da Segurança do Trabalho abre a fila,
   **Then** vê esses pedidos (número, quem pediu, quando, materiais e quantidades) e nenhum outro tipo de
   pedido.
2. **Given** um pedido aguardando, **When** o usuário o autoriza, **Then** o pedido passa a
   "Autorizado", ficam gravados quem autorizou e quando, e o pedido segue para o atendimento do
   almoxarifado, que é avisado pelo Telegram como nos outros formulários.
3. **Given** um pedido aguardando, **When** o usuário o recusa informando o motivo, **Then** o pedido
   passa a "Recusado", ficam gravados quem recusou, quando e o motivo, e o pedido fica encerrado: não
   pode ser atendido e o almoxarifado **não** recebe o aviso de pedido novo.
4. **Given** um pedido aguardando, **When** o usuário tenta recusar sem informar o motivo, **Then** a
   recusa é negada com a mensagem pedindo o motivo e o pedido continua aguardando.
5. **Given** o pedido aberto para decisão, **When** o usuário o examina, **Then** os materiais e as
   quantidades são só de leitura: ele não pode alterá-los, trocá-los nem acrescentar material.
6. **Given** dois usuários da Segurança do Trabalho com o mesmo pedido aberto, **When** um deles decide
   e o outro tenta decidir depois, **Then** a segunda decisão é recusada com a informação da decisão já
   gravada, e o pedido não muda.

---

### User Story 3 - Atender só o que foi autorizado (Priority: P1)

O almoxarifado vê todos os pedidos de EPI no painel, mas só atende os autorizados. O atendimento, a
edição, o recibo e o lançamento no SCPI funcionam como nos outros formulários.

**Why this priority**: É a garantia da etapa nova: nenhum EPI sai antes da autorização.

**Independent Test**: Abrir um pedido de EPI aguardando e tentar atendê-lo (bloqueado); autorizá-lo e
atendê-lo (permitido), imprimir o recibo e conferir as linhas de saída para o robô.

**Acceptance Scenarios**:

1. **Given** um pedido de EPI aguardando autorização, **When** o almoxarifado abre o detalhe, **Then**
   vê o pedido e a situação "Aguardando autorização" e **não** consegue confirmar o atendimento nem por
   um envio forjado.
2. **Given** um pedido de EPI recusado, **When** o almoxarifado abre o detalhe, **Then** vê a situação
   "Recusado", o motivo e quem recusou, e não consegue atendê-lo.
3. **Given** um pedido de EPI autorizado, **When** o almoxarifado o atende, **Then** o atendimento (com
   trocas, acréscimos, recebedor e data efetiva), o recibo e as linhas de saída para o robô do SCPI são
   os de hoje, sem regra própria.
4. **Given** um pedido de EPI autorizado e já atendido, **When** o almoxarifado edita o atendimento,
   **Then** vale a edição de hoje (até o robô lançar o lote), sem nova autorização.
5. **Given** o painel, **When** o almoxarifado filtra por situação ou por formulário, **Then** os
   pedidos de EPI aparecem identificados e podem ser achados por "Aguardando autorização", "Autorizado" e
   "Recusado".

---

### User Story 4 - Definir os materiais de EPI (Priority: P2)

Quem mantém os cadastros no almoxarifado escolhe quais grupos do cadastro do SCPI e quais materiais
avulsos o formulário de EPIs oferece, sem depender de nova versão do sistema. A situação do formulário aparece na saúde do catálogo
como a dos outros formulários.

**Why this priority**: O cadastro do SCPI muda com o tempo. Mas uma configuração inicial basta para as
histórias anteriores.

**Independent Test**: Incluir um grupo e um material avulso na escolha dos EPIs e retirar outro grupo; no
próximo acesso, os incluídos aparecem no formulário e os do grupo retirado não.

**Acceptance Scenarios**:

1. **Given** quem mantém os cadastros, **When** inclui um grupo do SCPI entre os EPIs, **Then** os
   materiais visíveis dele passam a aparecer no próximo acesso; **When** o retira, **Then** deixam de
   aparecer (salvo os incluídos como avulsos), e nenhum outro formulário muda.
2. **Given** um material de um grupo que não é de EPI, **When** quem mantém os cadastros o inclui como
   avulso, **Then** só ele, e não o grupo, passa a aparecer; se o grupo dele também for de EPI, ele
   aparece uma só vez.
3. **Given** a saúde do catálogo, **When** o almoxarifado a consulta, **Then** ela mostra quantos
   materiais o formulário de EPIs oferece, ou que ele está indisponível e por quê.

---

### User Story 5 - Consultar o resultado do pedido (Priority: P2)

O servidor que pediu o EPI, sem login, abre a página de consulta, digita o número do pedido e vê se ele
está aguardando, foi autorizado ou foi recusado (e o motivo).

**Why this priority**: Sem isso o servidor não sabe o que aconteceu com o pedido. Mas o processo
autorizado funciona sem a consulta (o almoxarifado avisa por fora).

**Independent Test**: Consultar o número de um pedido aguardando, de um autorizado e de um recusado, e
um número que não existe.

**Acceptance Scenarios**:

1. **Given** um pedido de EPI aguardando, autorizado ou recusado, **When** o servidor digita o número,
   **Then** vê a situação correspondente e, no recusado, o motivo.
2. **Given** a página de consulta, **When** ela mostra um pedido, **Then** não mostra nome, destino,
   observação nem materiais.
3. **Given** um número que não existe ou que é de pedido de outro formulário, **When** o servidor o
   consulta, **Then** vê a mesma mensagem neutra nos dois casos.
4. **Given** muitas consultas em sequência da mesma origem, **When** o limite é atingido, **Then** a
   consulta é recusada com uma mensagem própria da consulta, que manda procurar o almoxarifado.

---

### User Story 6 - Dar acesso à Segurança do Trabalho (Priority: P2)

Quem administra o sistema cria o usuário de alguém da Segurança do Trabalho e lhe dá o acesso próprio
(só a fila e a decisão dos pedidos de EPI).

**Why this priority**: Sem o usuário, não há quem autorize. O acesso a mais do que a fila seria um risco:
hoje todo usuário logado vê o painel inteiro.

**Independent Test**: Entrar com um usuário da Segurança do Trabalho e tentar abrir cada área do sistema;
só a fila de autorização funciona, e as demais são negadas.

**Acceptance Scenarios**:

1. **Given** um usuário com o acesso da Segurança do Trabalho, **When** ele entra, **Then** chega
   direto à fila de autorização, sem o menu das outras áreas.
2. **Given** esse usuário, **When** ele tenta abrir o painel de pedidos, a saída avulsa, as automações, a
   curva ABC, os cadastros ou o detalhe de um pedido que não é de EPI (por endereço digitado),
   **Then** o acesso é negado.
3. **Given** um usuário do almoxarifado sem o acesso da Segurança do Trabalho, **When** ele tenta
   autorizar ou recusar um pedido por um envio forjado, **Then** é negado, e o mesmo vale para o
   administrador sem o acesso da Segurança do Trabalho (FR-021).

---

### Edge Cases

- **Escolha dos EPIs vazia, sem material visível ou saldo nunca importado.** O formulário fica
  indisponível, com a mesma mensagem dos outros formulários públicos, e a saúde do catálogo diz o motivo.
- **Todos os materiais sem estoque.** Abre com o aviso "Nenhum material deste formulário tem estoque
  agora.", como os outros; os materiais aparecem bloqueados ("Sem estoque").
- **Reenvio igual, envio rápido demais, campo isca, limites por IP e por nome.** Iguais aos dos outros
  formulários públicos, inclusive o limite por nome, que conta os pedidos de todos os formulários
  públicos juntos. O reenvio igual confirma o mesmo pedido: não cria outro nem repete o aviso à
  Segurança do Trabalho.
- **Estoque que muda entre o envio e a decisão, ou entre a decisão e o atendimento.** A autorização não
  reserva estoque nem o confere de novo: o atendimento vale o saldo do momento, como nos outros
  formulários.
- **Material que sai da escolha dos EPIs depois do envio.** O pedido já registrado não muda; a decisão e o
  atendimento seguem com os itens gravados.
- **Aviso à Segurança do Trabalho não configurado ou com falha.** O pedido fica registrado e aparece na
  fila; nada é desfeito.
- **Pedido aguardando há muito tempo.** O sistema não o autoriza nem o recusa sozinho (prazo: a
  esclarecer, Assumptions).
- **Usuário da Segurança do Trabalho desativado depois de decidir.** A decisão gravada não muda e
  continua mostrando quem decidiu.
- **EPI entregue pela saída avulsa.** A saída avulsa continua sem autorização: ela é o registro do
  balcão pelo próprio almoxarifado e não é objeto desta funcionalidade (Fora do escopo).
- **Decisão de dois usuários ao mesmo tempo.** Vale a primeira; a segunda é recusada (US2-6).
- **Usuário da Segurança do Trabalho pede EPI para si mesmo.** Ele pode usar o formulário público como
  qualquer pessoa, e o sistema não impede que decida o próprio pedido, porque o nome do pedido é texto
  livre e não se liga a uma conta. Evitar a autoautorização é procedimento do SAEP, não regra do sistema
  (pendência (j) em "A esclarecer"); a decisão fica gravada com o usuário, o que permite a conferência
  depois.
- **Recebedor diferente do solicitante.** Hoje o atendimento aceita qualquer nome como recebedor (há
  só um atalho para repetir o solicitante). O sistema não impõe que o recebedor do EPI seja o servidor
  do pedido (pendência (i) em "A esclarecer"); o recibo assinado em papel é o que identifica quem
  recebeu.
- **Motivo da recusa com dado sensível.** O motivo é texto livre e aparece na consulta pública; o aviso
  da tela de decisão (FR-012) é a única proteção do sistema.

## Requirements *(mandatory)*

### Functional Requirements

**Formulário**

- **FR-001**: O sistema DEVE oferecer um formulário público, sem login, de pedido de EPIs, listado na
  página inicial dos formulários junto com os existentes, com título, exemplo de busca e ícone próprios.
- **FR-002**: O formulário DEVE ter o cabeçalho comum dos formulários públicos (nome completo, destino e
  observação), as mesmas proteções contra abuso, os mesmos limites e o mesmo requisito de JavaScript. O
  "Nome completo" identifica o servidor que vai receber o EPI; não há matrícula nem lista de servidores.
- **FR-003**: Um pedido DEVE ter um único destinatário, o servidor do "Nome completo". O sistema NÃO DEVE
  oferecer pedido para equipe nem mais de um destinatário por pedido.
- **FR-004**: O formulário DEVE oferecer, pela busca por nome, só os materiais visíveis da escolha dos
  EPIs, cada um uma só vez, com o estoque disponível e o mesmo texto da busca dos outros formulários
  públicos; os bloqueados ("Sem estoque", código repetido) aparecem no fim dos resultados, como hoje.
- **FR-005**: Os materiais DEVEM seguir a mesma regra de quantidade dos formulários públicos: fração só em
  unidade fracionável e teto no estoque disponível exibido, sem limite próprio.
- **FR-006**: O pedido NÃO DEVE ter campos de EPI além dos do cabeçalho comum e dos materiais com a
  quantidade: nada de tamanho, número do CA ou motivo (primeira entrega ou reposição). A observação livre
  é o único lugar para o servidor escrever mais.
- **FR-007**: O formulário DEVE ficar indisponível, com a mesma mensagem dos outros formulários públicos,
  quando o saldo de estoque nunca foi importado ou quando a escolha dos EPIs não tem nenhum material
  visível.

**Pedido e situação**

- **FR-008**: O pedido de EPI DEVE ser registrado como os dos outros formulários públicos, com uma origem
  própria que o identifique na lista e no filtro por origem do painel, e DEVE nascer na situação
  **"Aguardando autorização"**.
- **FR-009**: A tela de sucesso do envio DEVE dizer que o pedido aguarda a autorização da Segurança do
  Trabalho e que a entrega só acontece depois dela, no atendimento do almoxarifado; NÃO DEVE dizer nem
  sugerir que o EPI já será entregue. As mensagens ao servidor e ao almoxarifado DEVEM distinguir
  solicitação, autorização, entrega e recebimento (Contexto).
- **FR-010**: Um pedido de EPI DEVE ter exatamente uma destas situações de autorização: aguardando,
  autorizado ou recusado. Autorizado e recusado são definitivos: a decisão não é desfeita nem refeita, e
  um pedido recusado por engano é substituído por um pedido novo do servidor.

**Autorização**

- **FR-011**: O sistema DEVE oferecer uma fila dos pedidos de EPI aguardando decisão, ordenada do mais
  antigo para o mais novo, e o detalhe de cada pedido com cabeçalho, materiais e quantidades pedidas.
- **FR-012**: Quem autoriza DEVE poder **autorizar** ou **recusar** o pedido. A recusa DEVE exigir um
  motivo em texto, de tamanho limitado como as outras observações; a autorização não pede motivo. A tela
  da recusa DEVE avisar quem decide que o motivo será visto pelo servidor na consulta (FR-031) e pelo
  almoxarifado, para não escrever ali dado sensível.
- **FR-013**: A decisão DEVE gravar quem decidiu (o usuário), quando e, na recusa, o motivo, e esses
  dados DEVEM aparecer no detalhe do pedido para o almoxarifado e para a Segurança do Trabalho.
- **FR-014**: Quem autoriza NÃO DEVE poder alterar materiais, quantidades, destinatário, destino nem
  observação do pedido.
- **FR-015**: A decisão DEVE ser atômica e valer uma só vez: com duas decisões simultâneas, a primeira
  vale e a segunda é recusada com a informação da decisão já gravada. A decisão só vale para pedido de
  EPI na situação "Aguardando autorização".
- **FR-016**: O sistema NÃO DEVE autorizar nem recusar um pedido sozinho, nem por tempo decorrido.

**Acesso**

- **FR-017**: O sistema DEVE ter um acesso próprio para a Segurança do Trabalho, concedido a usuários
  identificados por matrícula, que dá acesso **só** à fila de autorização, ao detalhe dos pedidos de EPI
  e à decisão. Esse usuário NÃO DEVE conseguir abrir nenhuma outra área da parte interna (painel de
  pedidos, atendimento, saída avulsa, recibos, automações, curva ABC, cadastros), nem o detalhe de pedido
  que não seja de EPI, nem por endereço digitado nem por envio forjado.
- **FR-018**: Os usuários do almoxarifado que já existem DEVEM continuar com o acesso de hoje a tudo o que
  veem hoje, sem mudança; a separação nova DEVE valer só para o acesso da Segurança do Trabalho.
- **FR-019**: A concessão do acesso da Segurança do Trabalho DEVE poder ser feita por quem administra os
  usuários, sem nova versão do sistema.
- **FR-020**: O usuário da Segurança do Trabalho, ao entrar, DEVE chegar à fila de autorização.
- **FR-021**: Só os usuários da Segurança do Trabalho DEVEM poder autorizar ou recusar pedidos de EPI.
  Nenhum usuário do almoxarifado, nem administrador, decide por eles, e a tentativa por envio forjado é
  negada. O pedido sem decisão espera: o sistema não tem substituto.

**Almoxarifado**

- **FR-022**: O almoxarifado DEVE ver todos os pedidos de EPI no painel e no detalhe, identificados com a
  situação de autorização (e o motivo, se recusado), e poder filtrá-los por essa situação.
- **FR-023**: O sistema NÃO DEVE permitir o atendimento de pedido de EPI aguardando ou recusado, pela
  tela e por qualquer envio, e NÃO DEVE gerar linha de saída para o robô do SCPI desses pedidos.
- **FR-024**: Autorizado o pedido, atendimento, trocas e acréscimos pelo almoxarifado, edição do
  atendimento, recibo e lançamento no SCPI DEVEM funcionar como nos outros formulários públicos, sem
  regra própria e sem nova autorização. A troca ou o acréscimo de material pelo almoxarifado no
  atendimento não passa por nova autorização (se a Segurança do Trabalho quer vê-los: a esclarecer,
  item (g)).
- **FR-025**: O pedido de EPI recusado DEVE ficar encerrado, sem atendimento, e continuar consultável
  no painel.

**Avisos**

- **FR-026**: Na gravação do pedido de EPI, o sistema DEVE avisar a Segurança do Trabalho pelo Telegram,
  em chat próprio dela, que há pedido aguardando, com o número, o nome de quem pediu e os materiais; sem
  a configuração do chat, o aviso não sai e o pedido segue gravado. O aviso sai depois da gravação e
  nunca a desfaz.
- **FR-027**: O aviso do Telegram ao almoxarifado, o dos outros formulários, DEVE sair para o pedido de
  EPI **só depois de autorizado**, uma vez, e NÃO DEVE sair para pedido aguardando nem recusado.
- **FR-028**: O reenvio igual do mesmo pedido NÃO DEVE repetir nenhum dos dois avisos.

**Escolha dos EPIs**

- **FR-029**: Quem mantém os cadastros DEVE poder incluir e retirar, entre os EPIs do formulário,
  **grupos inteiros** do cadastro do SCPI e **materiais avulsos** de qualquer grupo (cada material uma
  só vez, mesmo que o grupo dele também esteja escolhido), e a mudança DEVE valer no próximo acesso ao
  formulário. Quais grupos e materiais compõem a carga inicial é decisão do almoxarifado, feita no
  cadastro; esta especificação não os define.
- **FR-030**: A saúde do catálogo DEVE mostrar quantos materiais o formulário de EPIs oferece, avisar
  quando ele estiver indisponível, com o motivo, e listar o que da escolha não aparece por estar oculto
  no SCPI.

**Resultado para o servidor**

- **FR-031**: O sistema DEVE oferecer uma página pública, sem login, de consulta do pedido de EPI pelo
  número, que mostra **só** a situação (aguardando autorização, autorizado ou recusado) e, na recusa, o
  motivo. Ela NÃO DEVE mostrar nome, destino, observação nem materiais, e NÃO DEVE responder sobre
  pedidos de outros formulários.
- **FR-031a**: A consulta DEVE responder da mesma forma para um número inexistente e para um número que
  não é de pedido de EPI (a resposta não distingue os dois casos), e DEVE ter limite por origem contra
  tentativas em sequência, como as proteções dos formulários públicos.
- **FR-031b**: A tela de sucesso do pedido de EPI DEVE dizer ao servidor que ele pode consultar o
  resultado nessa página com o número do pedido, e o número DEVE ser mostrado de forma que ele possa
  anotá-lo.

**Não regressão**

- **FR-032**: Os formulários existentes (limpeza, "Ferramentas, peças e materiais", reposição de peças das
  viaturas, oficina mecânica) e a saída avulsa DEVEM continuar com o mesmo conteúdo e comportamento, e
  os pedidos já registrados NÃO DEVEM mudar de situação nem passar a exigir autorização.
- **FR-033**: Os usuários e as telas do almoxarifado DEVEM continuar sem a etapa de autorização para
  qualquer pedido que não seja de EPI.

### Key Entities

- **Pedido de EPI**: pedido público como os demais, com origem própria; o solicitante é o servidor que
  vai receber o EPI; os itens são materiais da escolha dos EPIs; carrega a situação de autorização.
- **Autorização**: a decisão da Segurança do Trabalho sobre um pedido (aguardando, autorizado ou
  recusado), com quem decidiu, quando e o motivo da recusa. Uma por pedido.
- **Usuário da Segurança do Trabalho**: usuário do sistema (matrícula) com o acesso próprio, restrito à
  fila e à decisão dos pedidos de EPI; não é um cadastro de servidores.
- **Escolha dos EPIs**: os grupos do cadastro do SCPI escolhidos pelo almoxarifado e os materiais avulsos
  escolhidos um a um; juntos definem os materiais do formulário. Uma só escolha para todo o formulário.
- **Consulta do pedido**: a página pública que, pelo número, mostra a situação da autorização e o motivo
  da recusa; não guarda nada novo, só lê o pedido.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O servidor consegue pedir 3 EPIs em até 2 minutos no celular, contados de abrir o
  formulário até a tela com o número do pedido (medido no uso real, depois da implantação).
- **SC-002**: Em 100% dos pedidos de EPI, nenhum atendimento nem linha de saída para o SCPI existe antes
  da autorização, e nenhum existe nunca para pedido recusado.
- **SC-003**: Em 100% das decisões ficam gravados quem decidiu e quando, e, nas recusas, o motivo.
- **SC-004**: Em 100% das tentativas, o usuário da Segurança do Trabalho é impedido de abrir qualquer área
  da parte interna que não seja a fila de autorização e o detalhe de pedido de EPI.
- **SC-005**: O almoxarifado não recebe aviso de pedido novo de EPI antes da autorização em nenhum dos
  casos, e o recebe em até 1 minuto depois dela, com o canal configurado.
- **SC-006**: A Segurança do Trabalho identifica, pela fila, todos os pedidos de EPI aguardando decisão
  sem depender do aviso (o aviso só antecipa o conhecimento).
- **SC-007**: Em 100% dos casos, a página de consulta pelo número mostra a situação correta e nenhum dado
  pessoal nem material do pedido, e responde igual a um número inexistente e a um número de outro
  formulário.
- **SC-008**: Os formulários existentes e a saída avulsa não mudam: seus testes automatizados continuam
  passando sem alteração de comportamento.

## Assumptions

- O público do formulário é o servidor, no celular ou no computador, sem login; os limites por IP e por
  nome e as demais proteções dos formulários públicos bastam.
- O cabeçalho comum (destino e observação) não muda: o destino é escolhido entre os centros de custo
  cadastrados como nos outros formulários públicos. O destino do EPI é o setor do servidor.
- A regra de quantidade é a dos formulários públicos (a unidade do material decide se aceita fração).
- A ordem dos resultados da busca segue a regra comum dos formulários públicos; não há ordenação própria.
- O almoxarifado que atende e o usuário da Segurança do Trabalho que autoriza são pessoas e acessos
  diferentes; o atendimento continua sendo feito por quem tem hoje o acesso do almoxarifado.
- O robô do SCPI, o tipo de saída lançado e as regras de estoque não mudam. O estoque não é reservado nem
  conferido na autorização.
- O acesso da Segurança do Trabalho é concedido por quem administra os usuários, como os outros acessos.
- O usuário da Segurança do Trabalho, estando ou não logado, continua podendo abrir as páginas públicas
  (formulários e consulta) como qualquer pessoa; a restrição vale para a parte interna.
- Dados pessoais tratados: o nome do servidor (que o pedido já guarda hoje), a decisão e o motivo. A
  consulta pública não os expõe além da situação e do motivo; o prazo de guarda é pendência de
  validação externa (item 5 da seção normativa).
- O atendimento, a edição e o recibo continuam como hoje, inclusive o recebedor em texto livre.

### A esclarecer (não resolvido por suposição)

Perguntas abertas que a rodada de esclarecimento deve levar ao usuário; nenhuma delas tem padrão
adotado além do que está dito acima. Já respondidas na sessão de 2026-10-23 (ver Clarifications): quais
materiais são EPI, como o servidor sabe o resultado, quem pode autorizar, o relatório da NR-6 e a
reversão da decisão. Ficaram fora da cota de 5 perguntas, para o plano ou uma nova rodada:

- (f) Se a autorização tem prazo de validade (um pedido autorizado e não atendido a tempo). Sem prazo
  por enquanto: o pedido autorizado continua atendível.
- (g) Se a autorização (quem e quando) deve aparecer no recibo impresso, e se a Segurança do Trabalho
  quer ver a troca ou o acréscimo de material feito pelo almoxarifado no atendimento. Sem mudança no
  recibo por enquanto.
- (h) Se a Segurança do Trabalho vê, na fila, também os pedidos já decididos (histórico), ou só os
  aguardando. Por enquanto, os aguardando em destaque e os já decididos consultáveis, de leitura.
- (i) Se o recebedor do EPI deve ser sempre o servidor do pedido, ou se outra pessoa pode retirar por
  ele (hoje: texto livre, sem regra).
- (j) Se o SAEP quer que o sistema impeça o usuário da Segurança do Trabalho de decidir um pedido feito
  em seu próprio nome (hoje: impossível de detectar de forma confiável, porque o nome é texto livre).

## Referências normativas e pendências de validação externa

Fonte primária: NR-6 vigente, texto do Ministério do Trabalho e Emprego (PDF oficial atualizado até a
Portaria MTE nº 57/2025; o próprio texto informa que não substitui o publicado no DOU).

**Esta especificação não declara conformidade com a NR-6.** Os campos e as etapas abaixo são decisões
do SAEP e do usuário, e a adequação deve ser validada pelo setor competente (Segurança do
Trabalho/SESMT/jurídico).

| Origem | Item | Tratamento nesta funcionalidade |
|--------|------|---------------------------------|
| Exigência normativa | 6.5.1 d: registrar o fornecimento do EPI ao empregado (livro, ficha ou sistema eletrônico) | O pedido, o atendimento (recebedor, data efetiva, quem atendeu, quantidades entregues) e o recibo assinado em papel ficam gravados; se isso basta como registro de fornecimento é pendência de validação |
| Exigência normativa | 6.5.1.1: o sistema eletrônico deve permitir extrair relatórios | Não prevista nesta entrega, por decisão do usuário; o painel lista e filtra os pedidos de EPI, mas não há exportação. Se a validação normativa exigir a extração, é uma entrega futura |
| Exigência normativa | 6.5.1 g: substituir imediatamente o EPI danificado ou extraviado | Sem tratamento próprio: a reposição é um pedido como outro, sem o motivo (decisão 4); o prazo "imediato" vale para o procedimento da Segurança do Trabalho, não para o sistema |
| Exigência normativa, quando houver | 6.5.2.2: a seleção do EPI é feita com participação do SESMT, quando houver | A autorização da Segurança do Trabalho é uma decisão do SAEP, não o cumprimento dessa regra; a conformidade é pendência de validação |
| Exigência normativa, parcial | 6.5.1.2: descartável e creme de proteção, quando o registro for inviável, podem ser só disponibilizados em quantidade suficiente | Todos os materiais da escolha passam pelo mesmo fluxo; o tratamento dos descartáveis é pendência de validação |
| Boa prática, não exigida | 6.9.3: o CA é marcado no EPI pelo fabricante; a norma não lista campos obrigatórios do registro | Nome, CA e data são escolha do SAEP; CA, tamanho e motivo ficam fora desta entrega (decisão 4) |
| Procedimento interno do SAEP | A autorização da Segurança do Trabalho antes do atendimento; o recibo assinado em papel | Decididos pelo usuário (Clarifications) |
| Fora desta feature | 6.7.2 e 6.7.2.1: informações de uso e treinamento no fornecimento | Treinamento e informação ao servidor não fazem parte do sistema |

Pendências de validação externa, a confirmar com o setor competente antes de tratar o sistema como
registro de fornecimento:

1. Se a NR-6 se aplica ao regime jurídico dos servidores do SAEP.
2. Se o registro do pedido, do atendimento e do recibo assinado basta como registro de fornecimento
   (6.5.1 d).
3. Se é necessária a extração de relatório (6.5.1.1) e em que formato.
4. O tratamento dos EPIs descartáveis e do creme de proteção (6.5.1.2).
5. Por quanto tempo os registros devem ser guardados (a norma citada não fixa prazo).

## Fora do escopo

- Sistema de gestão de Segurança do Trabalho, controle de treinamentos e certificações, laudos e
  programas de riscos (PGR) ou qualquer integração com eles.
- Assinatura eletrônica, biometria e qualquer comprovação de recebimento dentro do sistema: o recibo
  impresso e assinado em papel continua sendo o comprovante.
- Tamanho ou numeração, número do CA, lote, validade, motivo da reposição e histórico de fornecimentos
  por servidor (decisão 4; podem ser reavaliados depois da validação normativa).
- Relatório ou exportação dos EPIs fornecidos (NR-6, 6.5.1.1): decidido não fazer nesta entrega e
  mantido como pendência de validação normativa.
- Aviso ao servidor pelo sistema (e-mail, SMS, Telegram): ele só consulta a página pelo número.
- Cadastro de servidores, matrícula no pedido e pedido para equipe ou para mais de um destinatário.
- Outras etapas de aprovação além da autorização da Segurança do Trabalho, aprovação em duas etapas,
  delegação e substituição de autorizador.
- Reverter ou refazer uma decisão: a decisão é definitiva.
- Reserva ou baixa de estoque na solicitação ou na autorização: a baixa continua sendo a requisição
  lançada no SCPI.
- Autorização na saída avulsa: ela é o registro do balcão pelo almoxarifado e não muda.
- Mudanças no catálogo AB, na lista de limpeza, nos formulários de viaturas e da oficina, no robô do SCPI
  ou no cabeçalho dos outros formulários.
- Papéis ou permissões novos além do acesso da Segurança do Trabalho; painel de configuração dos
  formulários pela interface.
