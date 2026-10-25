# Feature Specification: Consistência dos formulários públicos de pedido

**Feature Branch**: `005-consistencia-formularios-publicos`

**Created**: 2026-10-21

**Status**: Draft

**Input**: User description: tornar consistentes, nas regras e no comportamento percebido, os dois
formulários públicos de pedido ("Limpeza, copa e escritório" e "Ferramentas, peças e materiais"),
como base para novos formulários. Origem: o brainstorm de 2026-10-20/21 sobre o diagnóstico dos
formulários `/pedido/limpeza/` e `/pedido/ab/`; todas as decisões abaixo foram tomadas pelo usuário.

## Contexto

Os funcionários pedem materiais ao almoxarifado por dois formulários públicos, quase sempre no
celular. Eles foram feitos em momentos diferentes e, por isso, tratam do mesmo assunto de jeitos
diferentes. A leitura do código e o brainstorm acharam estes problemas:

- **Quantidade.** O formulário de limpeza aceita fração e o AB só aceita inteiro, embora os dois
  tenham materiais vendidos em metro, quilo e litro. A regra "AB só inteiro" veio do sistema
  anterior (Apps Script) sem justificativa registrada, e hoje impede pedir e entregar fração no AB.
- **Estoque.** O saldo tem 4 casas e a quantidade pedida tem 3: o limite usa uma precisão, a mensagem
  de erro outra. Com saldo 2,4996, pedir 2,5 é recusado com "estoque disponível: 2,5". O AB mostra
  "N UN disponíveis" e a limpeza mostra "Estoque N", duas redações para a mesma informação.
- **Catálogo vazio.** A limpeza fica "indisponível" quando não há itens; o AB abre vazio e o
  funcionário descobre depois de preencher nome e destino. Só o AB explica o motivo.
- **Erros.** Um item com quantidade ilegível some do pedido depois de uma recusa; a mesma causa tem
  dois textos conforme o momento (ao adicionar ou ao enviar); a mensagem para quantidade acima de
  999.999 engana.
- **Proteções.** A mensagem diz que o formulário "expirou", o que não existe; quem reenvia logo
  após o aviso esbarra no tempo mínimo e recebe "procure o almoxarifado".
- **Sem JavaScript.** O código e os comentários prometem que o formulário funciona sem JavaScript,
  mas não é possível buscar nem adicionar material sem ele.
- **Equipe.** No atendimento e no aviso do Telegram, a quantidade de um pedido do AB é cortada para
  inteiro em silêncio. Hoje é inofensivo; deixa de ser quando o AB aceitar fração.
- **Código.** A diferença entre os formulários está espalhada em mais de vinte pontos que perguntam
  "é limpeza ou AB?", o que torna caro e arriscado criar novos formulários. Já estão previstos pelo
  menos dois: reposição de peças de manutenção guardadas nas viaturas e autopeças da oficina
  mecânica.

Esta funcionalidade unifica a regra de quantidade e de estoque, define o que aparece quando não há
o que pedir, melhora a recuperação de erros e de recusas, declara o JavaScript como requisito e deixa
o código preparado para novos formulários. O cabeçalho do pedido (solicitante, destino, observação),
o lançamento no SCPI e os limites contra abuso continuam como estão.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pedir a quantidade certa para cada material (Priority: P1)

O funcionário pede, nos dois formulários, uma quantidade fracionada quando o material é medido em
metro, quilo, litro etc., e só inteira quando o material é contado (unidade, peça, caixa). O sistema
recusa na hora uma fração em material contado, com uma mensagem clara.

**Why this priority**: É a regra que mais afeta o resultado do pedido e a que o AB hoje não atende:
quem precisa de 2,5 m de mangueira não consegue pedir.

**Independent Test**: Pedir 2,5 de um material em metro e 2,5 de um material em unidade, nos dois
formulários; o primeiro entra no pedido, o segundo é recusado.

**Acceptance Scenarios**:

1. **Given** um material com unidade `M` e saldo suficiente, **When** o funcionário informa "2,5" em
   qualquer dos dois formulários, **Then** a quantidade é aceita e o pedido registra 2,5.
2. **Given** um material com unidade `UN`, **When** o funcionário informa "2,5" ao adicionar, ao
   alterar a quantidade ou ao enviar, **Then** a quantidade é recusada na hora com a mensagem
   "Este material só é pedido em quantidade inteira (unidade: UN)."
3. **Given** um material sem unidade cadastrada, **When** o funcionário informa "2,5", **Then** a
   quantidade é recusada como inteira, e a mensagem omite a unidade.
4. **Given** uma quantidade com mais de 3 casas, "1.5" com ponto, ou acima de 999.999, **When** o
   funcionário tenta adicionar, **Then** cada caso recebe a sua própria mensagem: em material
   fracionável, "Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5)." para
   os dois primeiros; em material contado, "Informe um número inteiro maior que zero."; e, nos dois,
   "A quantidade máxima é 999.999." para o terceiro.
5. **Given** a lista de unidades fracionáveis alterada por quem mantém o cadastro, **When** o
   funcionário faz o próximo pedido, **Then** a nova lista já vale, sem nenhuma nova publicação do
   sistema.
6. **Given** a quantidade "2,5" num campo de quantidade, **When** o funcionário toca em "+",
   **Then** o campo passa a "3,5" (anda de 1 em 1 e preserva a fração digitada).

---

### User Story 2 - Ver o estoque como o limite real do pedido (Priority: P1)

O funcionário vê, na lista de materiais, exatamente o máximo que consegue pedir. O número da lista,
o limite aceito e o texto do erro são sempre o mesmo, sem zeros desnecessários, e a linha de estoque
tem a mesma redação nos dois formulários.

**Why this priority**: Hoje o funcionário vê um número, é recusado por outro e lê um terceiro na
mensagem; isso gera pedidos recusados sem que ele entenda por quê.

**Independent Test**: Para um material de cada tipo (de medida e contado) e saldos como 2,4996, 2,5
e 0,0004, conferir a lista, a tentativa de adicionar o máximo e o máximo mais um, e a mensagem.

**Acceptance Scenarios**:

1. **Given** um material `M` com saldo 2,4996, **When** o funcionário vê a lista, **Then** ela mostra
   "Estoque 2,499 · M"; **And** 2,499 é aceito; **And** 2,5 é recusado com "Quantidade acima do
   estoque. Estoque disponível: 2,499 M."
2. **Given** um material `UN` com saldo 2,5, **When** o funcionário vê a lista, **Then** ela mostra
   "Estoque 2 · UN"; **And** 3 é recusado com "Quantidade acima do estoque. Estoque disponível: 2
   UN."
3. **Given** um material `UN` com saldo 0,5 ou um material `M` com saldo 0,0004, **When** o
   funcionário vê a lista, **Then** o material aparece bloqueado como "Sem estoque", porque o
   máximo que se consegue pedir é zero.
4. **Given** um material com saldo 10,000, **When** o funcionário vê a lista, **Then** o número é
   "10", nunca "10,000" ou "10,0".
5. **Given** os dois formulários, **When** o funcionário vê a lista, **Then** a linha de estoque tem
   a forma "Estoque N · UN" nos dois (ou "Estoque N" quando o material não tem unidade) e a frase "N
   UN disponíveis" deixa de existir.
6. **Given** um material no limite, **When** o funcionário adiciona, altera a quantidade e envia,
   **Then** a recusa tem o mesmo texto e o mesmo número nos três momentos.

---

### User Story 3 - Entender quando o formulário não pode ser usado (Priority: P2)

Quando não há nada para pedir, o funcionário não preenche um formulário que não pode ser enviado e
entende o motivo. O almoxarifado é avisado quando o problema é de cadastro.

**Why this priority**: Evita o pedido perdido depois de preencher nome e destino, e dá ao
almoxarifado um sinal quando o catálogo está vazio por configuração.

**Independent Test**: Esvaziar o catálogo, depois zerar o estoque de todos os itens, e abrir os dois
formulários em cada situação.

**Acceptance Scenarios**:

1. **Given** que o saldo de estoque nunca foi importado, **When** o funcionário abre qualquer dos
   dois formulários, **Then** a página mostra "Este formulário está indisponível no momento. Avise o
   almoxarifado." no lugar do formulário, com o mesmo texto nos dois.
2. **Given** um catálogo sem nenhum item (por exemplo, o AB sem saída na janela de consulta, ou a
   limpeza sem itens cadastrados), **When** o funcionário abre o formulário, **Then** vale o mesmo
   comportamento do cenário 1 **And** o painel do almoxarifado mostra um aviso de saúde do catálogo
   dizendo qual formulário está sem itens.
3. **Given** um catálogo com itens, todos sem estoque agora, **When** o funcionário abre o
   formulário, **Then** o formulário abre com um aviso no topo ("Nenhum material deste formulário
   tem estoque agora.") e a lista mostra os itens bloqueados como "Sem estoque".
4. **Given** um material com cadastro duplicado, **When** ele aparece na lista, **Then** continua
   bloqueado com o motivo "Cadastro duplicado — avise o almoxarifado".

---

### User Story 4 - Corrigir um item com problema sem perder o pedido (Priority: P2)

Quando o envio é recusado por causa de um item, o funcionário continua com tudo preenchido e vê
exatamente qual item corrigir e por quê.

**Why this priority**: Perder parte do pedido, ou ler um texto diferente do que viu ao adicionar,
obriga a refazer o trabalho e gera desconfiança.

**Independent Test**: Montar um pedido, reduzir o estoque de um item por baixo e enviar; depois
provocar uma quantidade ilegível no campo escondido do pedido e enviar.

**Acceptance Scenarios**:

1. **Given** que o estoque de um item baixou depois de adicionado, **When** o funcionário envia,
   **Then** o formulário volta com nome, destino, observação e todos os materiais, um resumo no topo
   e o item marcado "Corrigir" com a mensagem "Quantidade acima do estoque. Estoque disponível: N
   UN."
2. **Given** um item cuja quantidade chegou ilegível ao servidor, **When** o envio é recusado,
   **Then** a linha continua no pedido, com o texto digitado, marcada "Corrigir".
3. **Given** a mesma causa de erro, **When** ela ocorre ao adicionar e ao enviar, **Then** o texto é
   idêntico, nos dois formulários.
4. **Given** um item recusado, **When** o funcionário corrige a quantidade ou remove o item e envia
   de novo, **Then** o pedido é registrado normalmente.

---

### User Story 5 - Recuperar-se de uma recusa de proteção (Priority: P2)

Quando uma proteção contra envio automático recusa o pedido, o funcionário entende o que fazer e
consegue concluir sem procurar o almoxarifado.

**Why this priority**: As proteções existem para robôs; quem é pessoa não deve ficar sem saída.

**Independent Test**: Enviar com um ingresso adulterado, enviar em menos de 5 segundos e preencher o
campo escondido; conferir cada mensagem e a tentativa seguinte.

**Acceptance Scenarios**:

1. **Given** um ingresso inválido ou adulterado, **When** o funcionário envia, **Then** vê "Houve um
   problema ao confirmar o formulário. Seus dados foram mantidos: toque em Enviar de novo." com
   nome, destino e materiais preservados; **And** o envio seguinte, depois do tempo mínimo, é
   aceito.
2. **Given** um envio feito em menos de 5 segundos depois de abrir a página (ou depois do aviso do
   cenário 1), **When** ele é recusado, **Then** vê "Aguarde alguns segundos e toque em Enviar de
   novo." com os dados preservados.
3. **Given** o campo escondido preenchido, **When** o envio é recusado, **Then** vê a mensagem
   genérica "Não foi possível registrar o pedido. Procure o almoxarifado."
4. **Given** qualquer das recusas acima, **Then** nenhuma mensagem diz que o formulário "expirou".
5. **Given** um reenvio idêntico, **Then** o pedido já registrado é confirmado sem duplicar, e um
   reenvio diferente continua recebendo o aviso de divergência (comportamento atual, sem mudança).
6. **Given** os limites por IP, por nome, por itens e por tamanho de texto, **Then** continuam
   exatamente como estão.

---

### User Story 6 - A equipe atende e registra quantidades fracionadas sem perda (Priority: P3)

O almoxarifado vê, entrega e registra frações em qualquer material, e os avisos mostram a quantidade
exata que o funcionário pediu.

**Why this priority**: É o efeito colateral obrigatório de aceitar fração no AB: sem isto, um pedido
de 2,5 apareceria como "2" para quem atende.

**Independent Test**: Registrar um pedido do AB com fração, abrir o atendimento, o recibo e o aviso
do Telegram; entregar uma fração em material contado; registrar uma saída avulsa.

**Acceptance Scenarios**:

1. **Given** um pedido do AB de 2,5 M, **When** o aviso do Telegram é enviado e o almoxarifado abre o
   atendimento, **Then** o aviso, o detalhe, o campo de entrega e o recibo mostram "2,5".
2. **Given** um pedido de qualquer origem, **When** a equipe informa a quantidade entregue ou
   acrescenta um material, **Then** a fração é aceita em qualquer unidade (a regra por unidade vale
   só para o funcionário), com o teto no saldo exato truncado a 3 casas.
3. **Given** uma saída avulsa, **Then** a regra de quantidade e a forma da linha (código, estoque,
   unidade e classe) continuam como hoje, e o estoque mostrado é o saldo truncado a 3 casas (por
   exemplo, "Estoque 2,499" para o saldo 2,4996), igual ao teto aceito.
4. **Given** pedidos já gravados antes desta mudança, **Then** todos abrem com os mesmos números e
   textos de antes.

---

### User Story 7 - Aviso claro para quem está sem JavaScript (Priority: P3)

Quem abre o formulário sem JavaScript vê um aviso explicando que ele é necessário, em vez de um
formulário que parece utilizável e não funciona.

**Why this priority**: Declara o requisito real e remove um caminho que nunca funcionou.

**Independent Test**: Abrir os dois formulários com JavaScript desligado.

**Acceptance Scenarios**:

1. **Given** um navegador sem JavaScript, **When** o funcionário abre qualquer dos dois formulários,
   **Then** vê um aviso claro de que o formulário precisa de JavaScript e como proceder (usar outro
   navegador ou procurar o almoxarifado).
2. **Given** um navegador com JavaScript, **Then** o aviso não aparece e nada muda no uso.

---

### User Story 8 - Criar um formulário novo sem mexer no núcleo (Priority: P3)

Quem mantém o sistema cria um formulário novo (por exemplo, reposição de peças das viaturas ou
autopeças da oficina) descrevendo só o que muda: o catálogo, os textos, a origem e, se for preciso,
um limite próprio. Busca, carrinho, envio, proteções e recibo vêm prontos.

**Why this priority**: É o objetivo de fundo do trabalho: baixar o custo e o risco de cada formulário
novo. Não entrega valor direto ao funcionário nesta etapa, mas condiciona as próximas.

**Independent Test**: Com um formulário de teste (só catálogo e textos), buscar, adicionar, enviar e
ver o recibo e o painel, sem alterar o núcleo.

**Acceptance Scenarios**:

1. **Given** uma descrição de formulário com catálogo e textos próprios, **When** ela é registrada,
   **Then** o formulário aparece, busca, monta o pedido, valida, grava e mostra o recibo sem
   nenhuma alteração no núcleo.
2. **Given** os dois formulários atuais, **Then** a validação do envio é única para ambos e o
   comportamento visível é o descrito nas histórias 1 a 5.
3. **Given** uma origem nova, **Then** o pedido aparece no painel e no recibo com o nome certo.

---

### User Story 9 - Envios simultâneos não esperam a montagem do catálogo (Priority: P3)

Quando várias pessoas enviam pedidos ao mesmo tempo, nenhuma espera a montagem do catálogo do AB
enquanto outra tem o pedido gravado.

**Why this priority**: A montagem do catálogo é a parte mais pesada do envio e hoje acontece
enquanto os demais envios aguardam a vez.

**Independent Test**: Medir o tempo de montagem do catálogo do AB com dados reais, somente leitura, e
conferir que ele não acontece durante o bloqueio da numeração.

**Acceptance Scenarios**:

1. **Given** um envio do AB, **When** o pedido é gravado, **Then** o catálogo já foi montado antes do
   bloqueio da numeração e o bloqueio dura só o necessário para numerar e gravar.
2. **Given** a medição feita com dados reais, **Then** o resultado fica registrado e só ele decide se
   um cache será proposto (o cache não faz parte desta funcionalidade).

---

### Edge Cases

- Saldo 0,0004 em material de medida: o máximo é 0 e o material aparece "Sem estoque".
- Material sem unidade, ou com unidade fora da lista: só inteiro.
- Unidade escrita com outra caixa ou espaços (por exemplo `kg`, ` M² `): vale como `KG` e `M²`.
- No AB, código antigo consolidado em um novo: vale a unidade e o saldo do código novo, que é onde a
  saída é lançada.
- Na limpeza, o texto da unidade exibida ao funcionário (por exemplo "Pacote 500 g") não decide a
  regra: decide a unidade do cadastro do SCPI.
- A unidade ou o saldo mudam entre adicionar e enviar: o envio revalida e o item recusado fica no
  pedido marcado "Corrigir".
- O mesmo material em mais de uma linha: as quantidades somam contra o limite, como hoje.
- Pedido com mais de 40 materiais: continua recusado, como hoje.
- Reenvio durante uma recusa de proteção: não duplica; o reenvio idêntico confirma o pedido já
  gravado.
- Lista de unidades fracionáveis vazia: todos os materiais passam a aceitar só inteiro; por isso a
  lista nasce carregada (ver requisitos de implantação).
- Todos os itens do catálogo sem estoque, depois só um com estoque: o aviso do topo some, o
  formulário abre normalmente.
- Fração em pedido já gravado e depois editado no atendimento: continua aceita pela regra da equipe.

## Requirements *(mandatory)*

### Functional Requirements

**Quantidade**

- **FR-001**: Nos dois formulários públicos, o sistema MUST aceitar fração, com até 3 casas
  decimais, em materiais cuja unidade do cadastro do SCPI é uma das unidades fracionáveis, e MUST
  aceitar só inteiro em qualquer outro material, inclusive o que não tem unidade.
- **FR-002**: As unidades fracionáveis iniciais MUST ser `M`, `MT`, `MTS`, `KM`, `KG`, `L`, `LT`,
  `M²`, `M³` e `T`. A lista MUST ser mantida por quem administra o cadastro, sem nova publicação do
  sistema, e MUST nascer carregada com essas dez unidades.
- **FR-003**: A comparação da unidade com a lista MUST ignorar caixa alta ou baixa, acentos e
  espaços nas pontas.
- **FR-004**: A regra MUST usar a unidade do cadastro do SCPI; no AB, a do código canônico
  depois do de/para; na limpeza, nunca a unidade exibida ao funcionário.
- **FR-005**: Uma fração em material contado MUST ser recusada ao adicionar, ao alterar a
  quantidade e ao enviar, sempre com a mesma mensagem: "Este material só é pedido em quantidade
  inteira (unidade: UN)." (a mensagem omite a unidade quando o material não tem).
- **FR-006**: A menor quantidade MUST ser 0,001 para unidade fracionável e 1 para as demais; a maior
  continua 999.999.
- **FR-007**: Quantidades com mais de 3 casas, com ponto decimal, ilegíveis ou zero MUST ter, em
  material fracionável, a mensagem "Informe uma quantidade maior que zero (use vírgula para
  decimais, ex.: 1,5)."; em material contado, "Informe um número inteiro maior que zero."; acima de
  999.999, "A quantidade máxima é 999.999."
- **FR-008**: O botão "−"/"+" da quantidade MUST continuar andando de 1 em 1 e preservando a
  fração digitada.

**Estoque**

- **FR-009**: O número exibido como estoque MUST ser o máximo que o formulário aceita: para unidade
  fracionável, o saldo truncado a 3 casas; para unidade contável, a parte inteira.
- **FR-010**: O limite aceito, o texto "Estoque disponível" das mensagens e o número da lista MUST
  ser sempre o mesmo valor.
- **FR-011**: Nenhum número de quantidade ou de estoque MUST mostrar zeros à direita ("2,5", nunca
  "2,500"; "10", nunca "10,000").
- **FR-012**: A linha de estoque MUST ser "Estoque N · UN" nos dois formulários (sem a unidade
  quando o material não tem); a frase "N UN disponíveis" MUST deixar de ser usada.
- **FR-013**: Um material cujo máximo pedível é zero MUST aparecer bloqueado como "Sem estoque", na
  lista, ao adicionar e ao enviar.
- **FR-014**: Quando o pedido já tem uma quantidade do material, o limite MUST considerar o que já
  está no pedido, com os mesmos textos de hoje ("Já há N no pedido; é possível acrescentar no
  máximo M." e "…que é todo o estoque disponível.").

**Catálogo e disponibilidade**

- **FR-015**: O catálogo do AB MUST continuar vindo do histórico de saídas consolidado pelo de/para,
  e o da limpeza MUST continuar sendo o cadastro curado.
- **FR-016**: Os dois formulários MUST ficar indisponíveis, mostrando "Este formulário está
  indisponível no momento. Avise o almoxarifado." no lugar do formulário, quando o saldo de estoque
  nunca foi importado ou quando o catálogo não tem nenhum item.
- **FR-017**: Um catálogo sem nenhum item MUST aparecer como aviso de saúde do catálogo no painel do
  almoxarifado, identificando o formulário.
- **FR-018**: Quando há itens e todos estão sem estoque, o formulário MUST abrir com o aviso "Nenhum
  material deste formulário tem estoque agora." no topo e a lista de itens bloqueados.
- **FR-019**: A busca, o filtro por grupo e subgrupo, o bloqueio por cadastro duplicado e a ordem
  (pedíveis antes dos bloqueados, corte em 50 resultados) MUST ser iguais nos dois formulários.

**Erros no envio**

- **FR-020**: Quando o envio é recusado por causa de itens, o formulário MUST voltar com todos os
  campos e todos os materiais preservados, um resumo no topo e cada item com problema marcado
  "Corrigir".
- **FR-021**: Um item cuja quantidade chegou ilegível MUST permanecer no pedido com o texto
  digitado, marcado "Corrigir", e MUST NOT desaparecer da tela.
- **FR-022**: Cada causa de erro de quantidade MUST ter um texto só, igual ao adicionar, ao alterar
  e ao enviar, e igual nos dois formulários.
- **FR-023**: O sistema MUST NOT ajustar quantidades automaticamente ao estoque.

**Proteções**

- **FR-024**: Ingresso inválido MUST mostrar "Houve um problema ao confirmar o formulário. Seus dados
  foram mantidos: toque em Enviar de novo.", com os dados preservados.
- **FR-025**: Envio rápido demais MUST mostrar "Aguarde alguns segundos e toque em Enviar de novo.",
  com os dados preservados.
- **FR-026**: O campo escondido preenchido MUST continuar recusado com a mensagem genérica "Não foi
  possível registrar o pedido. Procure o almoxarifado."
- **FR-027**: Nenhuma mensagem do formulário MUST afirmar que ele "expirou".
- **FR-028**: O tempo mínimo de 5 segundos, os limites por IP (3 em 10 minutos e 10 por dia), o
  limite por nome (5 por dia), o limite de 40 materiais, o limite de 200 caracteres e o tratamento
  de reenvio MUST permanecer como estão.

**JavaScript**

- **FR-029**: Os dois formulários MUST mostrar, para quem está sem JavaScript, um aviso claro de que
  ele é necessário e como proceder.
- **FR-030**: O código e os comentários do modo "sem JavaScript" que não funciona MUST ser removidos
  ou corrigidos.

**Equipe e efeitos em outros fluxos**

- **FR-031**: Atendimento, saída avulsa e material acrescentado pela equipe MUST aceitar fração em
  qualquer unidade, em pedidos de qualquer origem, com o teto no saldo exato truncado a 3 casas.
- **FR-032**: Toda tela e todo aviso que mostram a quantidade de um pedido (Telegram, detalhe,
  campo de entrega, recibo, painel) MUST mostrar a quantidade exata, sem cortar a fração, usando um
  só formato sem zeros à direita.
- **FR-033**: A saída avulsa MUST manter a regra de quantidade e a forma da linha de estoque atual
  (código, estoque, unidade e classe), mas o estoque exibido MUST ser o mesmo número do teto da
  equipe (saldo truncado a 3 casas, sem zeros à direita), para o que se vê ser o que se aceita.
- **FR-034**: Pedidos, itens, recibos e atendimentos já gravados MUST permanecer idênticos e MUST
  NOT ser convertidos.

**Desempenho**

- **FR-035**: A montagem do catálogo do AB MUST acontecer fora do bloqueio da numeração dos pedidos.
- **FR-036**: A funcionalidade MUST incluir uma medição somente leitura do tempo de montagem do
  catálogo do AB com dados reais, cujo resultado fica registrado; nenhum cache MUST ser introduzido
  nesta funcionalidade.

**Organização e documentação**

- **FR-037**: Cada formulário MUST ser descrito por uma configuração própria (catálogo, textos,
  origem e, se necessário, limite) sobre um núcleo único de busca, carrinho, envio, proteções e
  recibo.
- **FR-038**: Os dois formulários públicos MUST usar uma só validação de envio.
- **FR-039**: Os textos hoje fixos nos modelos de página (exemplo da busca, mensagem de
  indisponível, rótulos de envio) MUST passar para a configuração do formulário.
- **FR-040**: O sistema MUST deixar de ramificar por nome ou por origem do formulário nos pontos
  em que a regra por unidade os torna desnecessários (quantidade inteira ou decimal, estoque
  exibido, formatação de quantidade).
- **FR-041**: Um formulário novo, com catálogo e textos próprios, MUST funcionar sem alteração no
  núcleo; o cabeçalho (solicitante, destino, observação) e o lançamento no SCPI MUST permanecer
  iguais.
- **FR-042**: A documentação MUST ser corrigida onde diverge do comportamento: a especificação
  principal, a descrição do módulo de fluxos e os comentários dos modelos de página.

**Dados e implantação**

- **FR-043**: Qualquer mudança de modelo MUST vir como migration nova (nunca regenerada), e a carga
  das dez unidades fracionáveis MUST ir na própria migration, de modo que, logo após a implantação,
  os formulários já aceitem fração nas unidades de medida.
- **FR-044**: Nenhuma verificação ou implantação desta funcionalidade MUST lançar saídas no SCPI nem
  acionar integrações reais.

### Key Entities

- **Unidade fracionável**: uma sigla de unidade do cadastro do SCPI em que a quantidade pode ter
  fração; mantida numa lista editável por quem administra o cadastro.
- **Material**: item do cadastro com unidade do SCPI e saldo de estoque (até 4 casas); a regra de
  quantidade e o estoque exibido derivam dele.
- **Configuração do formulário**: descrição de um formulário (catálogo, textos, origem, limite
  próprio opcional); os formulários atuais e os futuros são entradas dela.
- **Pedido e itens do pedido**: continuam como estão (cabeçalho: solicitante, destino, observação).
- **Aviso de saúde do catálogo**: sinal no painel de que um formulário está sem itens.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Em uma matriz de casos (material de medida e contado × saldos 0,0004, 0,5, 2,4996,
  2,5 e 10 × quantidade igual ao máximo e máximo mais um), 100% dos casos mostram o mesmo número na
  lista, no limite aceito e na mensagem de erro, nos dois formulários.
- **SC-002**: Um pedido com fração em material de medida, feito em cada formulário, aparece com a
  quantidade exata no aviso do Telegram, no atendimento, no recibo e no painel: zero ocorrências de
  fração cortada.
- **SC-003**: Em 100% dos casos de formulário sem o que pedir (sem saldo importado, catálogo vazio,
  tudo sem estoque), o funcionário vê o aviso correspondente antes de preencher qualquer campo, e a
  redação é a mesma nos dois formulários.
- **SC-004**: Em 100% das recusas por item, o pedido volta com todos os materiais que o funcionário
  tinha.
- **SC-005**: Depois de qualquer recusa de proteção que não seja a isca, o funcionário conclui o
  pedido na tentativa seguinte, no máximo 10 segundos depois, sem procurar o almoxarifado.
- **SC-006**: Durante um envio do AB, o tempo em que a numeração fica bloqueada não inclui a
  montagem do catálogo; a medição com dados reais fica registrada.
- **SC-007**: Um formulário de teste, com só catálogo e textos, funciona de ponta a ponta sem
  nenhuma alteração no núcleo de busca, carrinho, envio, proteções e recibo.
- **SC-008**: Uma amostra de pedidos gravados antes da mudança abre com os mesmos números e textos
  depois dela (zero diferenças).
- **SC-009**: Nenhum texto de interface nem documento menciona o formulário funcionando sem
  JavaScript, e os três documentos citados em FR-042 refletem o comportamento novo.
- **SC-010**: A conferência manual em tela de celular (375 px) dos dois formulários, cobrindo busca,
  adicionar, alterar, erro por item, indisponível e envio, é feita e registrada, porque os testes
  automáticos de JavaScript só conferem texto do arquivo e não comprovam o comportamento no
  navegador.

## Assumptions

- Os dois formulários e a saída avulsa continuam compartilhando busca e carrinho; mudanças nesses
  componentes são conferidas também na saída avulsa e no atendimento.
- O SCPI aceita quantidade fracionada mesmo em unidade contável (confirmado pelo usuário); por isso a
  recusa da fração em material contado é uma proteção contra erro de digitação, não uma exigência do
  SCPI, e a lista de unidades fracionáveis pode ser ajustada sem risco para o lançamento.
- O catálogo do AB continua dependendo do histórico de saídas porque o cadastro do SCPI está
  contaminado com muitos materiais desatualizados; como um material novo entra no AB é uma questão
  futura.
- Os formulários estão abertos à internet; os limites contra abuso ficam como estão e a calibragem
  dos limites por IP é adiada até haver volume de pedidos para medir.
- O JavaScript é requisito: o público usa celular e computador de trabalho com navegador comum, e o
  aviso cobre o caso raro.
- Na equipe, a fração em material contado é aceita porque o saldo do SCPI já tem frações de
  unidades contáveis (meia barra, caixa partida) e a equipe conhece o material.
- Os formulários futuros previstos (reposição de peças guardadas nas viaturas e autopeças da oficina)
  mantêm o cabeçalho do pedido, em que o destino é um centro de custo cadastrado, e o mesmo tipo de
  saída no SCPI; o destino aceito e um possível limite próprio de cada um serão tratados na
  especificação de cada formulário.
- Esta funcionalidade altera, onde conflitar, o que a especificação 002 definiu para as mensagens e
  a linha de estoque.
- Divergências deliberadas em relação ao sistema anterior (Apps Script), registradas conforme o
  Princípio I da constituição do projeto:
  - o AB passa a aceitar fração (a origem só aceitava inteiro), porque o AB também tem materiais
    medidos em metro, quilo e litro;
  - a limpeza e a saída avulsa passam a limitar a quantidade ao saldo (a origem não limitava), o
    que já foi implantado antes e agora fica uniforme;
  - os textos de erro de quantidade foram unificados e diferem dos da origem, para haver um só texto
    por causa;
  - o estoque exibido deixa de ser "N UN disponíveis" no AB e passa a ser o máximo pedível, em
    todos os formulários.

### Fora do escopo

- Criar os formulários novos (reposição de peças das viaturas e autopeças da oficina).
- Calibrar ou alterar os limites por IP.
- Definir como um material novo passa a aparecer no AB.
- Introduzir cache do catálogo do AB (só depois da medição e com nova decisão).
- Alterar o robô do SCPI, o cabeçalho do pedido ou o tipo de saída lançado.
