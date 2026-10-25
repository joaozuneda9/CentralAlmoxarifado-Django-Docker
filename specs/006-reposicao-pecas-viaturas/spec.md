# Feature Specification: Reposição de peças das viaturas das equipes de manutenção

**Feature Branch**: `claude/reposicao-pecas-viaturas`

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: formulário público de reposição de peças recorrentes das viaturas das
equipes de manutenção. Quem pede é o encarregado da equipe, sem login, como nos formulários públicos
atuais. Não há conjunto-padrão de peças por viatura ou por equipe; há uma lista de peças comumente
usadas pelas equipes, que o formulário mostra como lista fechada padrão, com a opção de também
pesquisar livremente os materiais do catálogo "Ferramentas, peças e materiais" (AB). A quantidade é
livre até o estoque disponível, por enquanto. O destino é o centro de custo da equipe, que o
almoxarifado cadastrará no SCPI e no sistema. O pedido segue o caminho dos formulários públicos:
atendimento pelo almoxarifado, recibo e lançamento no SCPI. Respostas do usuário em 2026-10-22, no
diagnóstico que antecedeu esta especificação.

## Contexto

As equipes de manutenção levam nas viaturas um estoque de peças que usam com frequência. Quando
essas peças acabam, o encarregado da equipe pede a reposição ao almoxarifado. Hoje ele usa o
formulário "Ferramentas, peças e materiais", que mostra todo o catálogo AB, ordenado pelo número de
saídas do almoxarifado inteiro: as peças das equipes ficam misturadas a ferramentas, EPIs e
materiais de obra, e o encarregado precisa procurar uma a uma.

Não existe um conjunto-padrão de peças por viatura nem por equipe, nem uma quantidade-alvo de
reposição. Existe, sim, uma lista das peças que as equipes costumam usar: o quadro "Materiais" da
folha de Ordem de Serviço em papel, com cerca de 40 conexões, tubos, registros e lacre, em que o
encarregado marcava as quantidades e escrevia à mão o que não estava impresso. Este formulário dá ao
encarregado essa lista pronta, preenchida como a folha, e mantém o acesso ao resto do catálogo AB
para o que fugir dela.

**Termos.** "Lista de peças comuns" é o conjunto curado de peças (no admin, "Peças das viaturas");
"folha" é a tela em que o encarregado a preenche, como o papel; "pesquisa" é a busca de materiais de
sempre, no catálogo AB.

Os formulários públicos já compartilham busca, pedido, envio, proteções contra abuso, atendimento,
recibo e lançamento no SCPI (especificação 005). Esta funcionalidade acrescenta um formulário com o
seu próprio conjunto de materiais e os seus destinos; o restante do caminho do pedido é o mesmo.

## Clarifications

### Session 2026-10-22

- Q: Quantas peças, aproximadamente, terá a lista de peças comuns? → A: cerca de 40. A referência é a
  lista em papel usada até hoje (quadro "Materiais" da Ordem de Serviço do SAEP, `Lista de materiais
  reposição .pdf`, fornecida pelo usuário): 39 linhas de conexões, tubos, registros e lacre, em duas
  colunas "QTDE | Materiais", com linhas em branco onde o encarregado escrevia à mão peças fora da
  lista. O formulário deve dar uma experiência parecida com o preenchimento desse papel: a lista
  inteira à vista, com a quantidade preenchida linha a linha, e os materiais fora dela acrescentados
  à parte, como as linhas em branco.
- Q: Cada linha da lista corresponde a um único material do cadastro do SCPI, ou uma linha pode
  valer por mais de um? → A: uma linha, um material. As alternativas do papel ("Cotovelo
  Galvanizado 3/4 ou Ferro") viram linhas separadas, cada uma com o seu código, unidade e estoque;
  na falta da peça, o almoxarifado a troca no atendimento, como já faz.
- Q: Na lista do formulário, cada peça aparece com o nome do cadastro do SCPI ou com um nome
  familiar, como o do papel? → A: nome exibido opcional por linha (o nome que a equipe conhece);
  sem ele, vale o nome do cadastro. Mesmo comportamento do nome exibido da lista de limpeza.
- Q: O pedido de reposição precisa trazer o número da ocorrência ou da Ordem de Serviço em que as
  peças foram usadas? → A: campo opcional com o número da ocorrência. É o primeiro campo de
  cabeçalho que existe só num formulário; os outros formulários não o têm.
- Q: Como é o número da ocorrência que o encarregado vai digitar? → A: texto curto livre, até 20
  caracteres.
- Q (checklist de operação, CHK027): a pesquisa cobre só o catálogo AB ou todo o cadastro visível?
  → A: só o catálogo AB, como pedido; o que faltar entra na lista pelo admin ou é acrescentado pelo
  almoxarifado no atendimento.
- Q (checklist de operação, CHK003): onde mais o número da ocorrência aparece? → A: na lista do
  painel e na busca do painel, além do detalhe e do recibo; não no Telegram.
- Ajuste da revisão do PR (2026-10-22, decidido pelo usuário): a tela de sucesso também mostra o
  número da ocorrência, quando preenchido, para o encarregado conferir o que enviou.
- Ajuste do planejamento (2026-10-22, aberto à revisão do usuário): a lista abre num diálogo, com um
  toque no passo dos materiais, como o usuário sugeriu ("quem sabe em um modal"), e é posta no pedido
  de uma vez, tudo ou nada (research R4). Cenário 1 da US1 e FR-003 ajustados.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pedir a reposição a partir da lista de peças comuns (Priority: P1)

O encarregado da equipe abre o formulário de reposição de peças das viaturas, vê a lista das peças
que as equipes costumam usar, escolhe as que precisa repor com as quantidades, informa o próprio
nome e o centro de custo da equipe e envia. O almoxarifado recebe o pedido como recebe os dos outros
formulários.

**Why this priority**: É o motivo do formulário: tirar o encarregado da busca no catálogo inteiro
para as peças que ele repõe sempre.

**Independent Test**: Com a lista de peças comuns cadastrada e saldo importado, abrir o formulário,
escolher duas peças da lista, informar nome e destino e enviar; o pedido aparece no painel do
almoxarifado identificado como reposição de peças das viaturas.

**Acceptance Scenarios**:

1. **Given** a lista de peças comuns com materiais com saldo, **When** o encarregado chega aos
   materiais e toca em "Preencher a lista de peças", **Then** vê a lista inteira de uma vez, como na
   folha de papel, cada linha com nome, unidade, estoque disponível e um campo de quantidade, sem
   precisar digitar uma busca.
2. **Given** a lista aberta, **When** o encarregado preenche a quantidade de várias linhas, uma após
   a outra, **Then** cada peça com quantidade entra no pedido, com a mesma regra de quantidade dos
   formulários públicos (fração só em unidade fracionável, até o estoque disponível), e as linhas
   deixadas em branco não entram.
3. **Given** um pedido com peças, nome e destino válidos, **When** o encarregado envia, **Then** o
   pedido é registrado com número próprio da sequência dos pedidos públicos, a tela de sucesso
   mostra o número, e o almoxarifado é avisado como nos outros formulários.
4. **Given** um pedido registrado por este formulário, **When** o almoxarifado consulta o painel,
   **Then** o pedido aparece com o nome deste formulário, pode ser filtrado por ele, e o atendimento,
   o recibo e o lançamento no SCPI seguem exatamente o caminho dos pedidos dos outros formulários.
5. **Given** uma peça da lista sem estoque, **When** o encarregado a vê, **Then** ela aparece
   bloqueada ("Sem estoque") no seu lugar na lista, sem campo de quantidade.

---

### User Story 2 - Pedir uma peça que não está na lista (Priority: P2)

Quando a equipe precisa de algo fora da lista de peças comuns, o encarregado pesquisa pelo nome no
catálogo "Ferramentas, peças e materiais" sem sair do formulário e acrescenta o material ao mesmo
pedido.

**Why this priority**: Sem isso, qualquer peça fora da lista obrigaria um segundo pedido em outro
formulário. Mas o formulário já entrega valor só com a lista (US1).

**Independent Test**: Pesquisar um material do catálogo AB que não está na lista de peças comuns,
adicioná-lo junto com uma peça da lista e enviar; o pedido registra os dois.

**Acceptance Scenarios**:

1. **Given** o formulário aberto, **When** o encarregado digita parte do nome de um material que
   está no catálogo AB mas não na lista, **Then** o material aparece nos resultados e pode ser
   adicionado com as mesmas regras de quantidade e estoque.
2. **Given** uma pesquisa cujo texto corresponde a uma peça da lista e a materiais do catálogo AB,
   **When** os resultados aparecem, **Then** cada material aparece uma só vez.
3. **Given** um material que não está na lista nem no catálogo AB, **When** o encarregado o
   pesquisa, **Then** ele não aparece, como nos outros formulários públicos.
4. **Given** um pedido com peças da lista e materiais pesquisados, **When** é enviado, **Then** o
   pedido único registra todos, e o almoxarifado não precisa distinguir de onde cada um veio para
   atendê-lo.

---

### User Story 3 - Manter a lista de peças comuns (Priority: P2)

Quem mantém os cadastros no almoxarifado inclui, retira e ordena as peças da lista de peças comuns,
sem depender de uma nova versão do sistema. A situação do formulário aparece na saúde do catálogo
como a dos outros formulários.

**Why this priority**: A lista é o conteúdo do formulário; sem manutenção ela envelhece. Mas a carga
inicial pode ser feita uma vez, e a US1 já funciona com ela.

**Independent Test**: Incluir um material na lista e retirar outro; no próximo acesso ao formulário,
o incluído aparece e o retirado não.

**Acceptance Scenarios**:

1. **Given** quem mantém os cadastros, **When** inclui um material do cadastro na lista, **Then** ele
   passa a aparecer no formulário no próximo acesso, sem nova publicação do sistema.
2. **Given** um material da lista, **When** é retirado dela, **Then** deixa de aparecer como peça
   comum; se estiver no catálogo AB, continua acessível pela pesquisa.
3. **Given** a lista, **When** quem mantém define a ordem, **Then** o formulário mostra as peças
   nessa ordem, as bloqueadas no próprio lugar, como numa folha impressa.
4. **Given** um material da lista que ficou oculto no SCPI, **When** o formulário
   é aberto, **Then** ele não aparece, e a saúde do catálogo avisa quais peças da lista estão nessa
   situação.
5. **Given** a saúde do catálogo, **When** o almoxarifado a consulta, **Then** ela mostra quantas
   peças o formulário de reposição oferece, ou que ele está indisponível e por quê.

---

### Edge Cases

- **Lista vazia.** Sem nenhuma peça comum disponível, o formulário abre só com a pesquisa no
  catálogo AB; se também não houver material no catálogo AB, fica indisponível (FR-004).
- **Saldo nunca importado.** O formulário fica indisponível, com a mesma mensagem dos outros
  formulários públicos e o mesmo aviso na saúde do catálogo.
- **Todas as peças da lista sem estoque.** Cada uma aparece bloqueada ("Sem estoque") na folha, e a
  pesquisa no catálogo AB continua disponível. O aviso geral "Nenhum material deste formulário tem
  estoque agora." só aparece quando nada do formulário (lista e catálogo AB) tem estoque, como nos
  outros formulários públicos.
- **Peça da lista que também é da lista de limpeza ou de um grupo oculto do AB.** A lista de peças
  comuns é curada à mão e prevalece: a peça aparece neste formulário, mesmo fora do catálogo AB.
- **Peça da lista sem saídas recentes.** Aparece normalmente: a lista não depende do histórico de
  saídas que ordena o catálogo AB.
- **Material com código repetido no cadastro.** Aparece bloqueado, como nos outros formulários.
- **Destino que não é centro de custo de equipe.** Não aparece entre as opções; digitado ou enviado
  mesmo assim, o envio é recusado com a mensagem de destino inválido de hoje (FR-007).
- **Centro de custo da equipe ainda não cadastrado ou não marcado.** O encarregado não o encontra
  entre os destinos e procura o almoxarifado. Sem nenhum centro marcado, o formulário fica
  indisponível (FR-008a).
- **Centro de custo de equipe com placas cadastradas.** O destino oferecido é só o centro, sem a
  placa (FR-008).
- **Centro desmarcado entre abrir o formulário e enviar.** O envio é recusado como destino inválido,
  e o pedido é mantido para o encarregado escolher outro destino.
- **Reenvio, envio rápido demais, campo isca, limites por IP e por nome.** Iguais aos dos outros
  formulários públicos, inclusive o limite por nome, que conta os pedidos de todos os formulários
  públicos juntos.
- **Folha que passaria do limite de materiais por pedido.** Nada é posto no pedido, e a folha mostra
  a recusa de sempre ("O pedido pode ter no máximo 40 materiais.").
- **Mesma peça pela folha e pela busca.** A folha mostra a quantidade que a peça já tem no pedido e,
  aplicada, a substitui; adicionar pela busca uma peça que já está no pedido soma, como hoje.
- **Falha de rede ou do servidor ao pôr a folha no pedido.** A folha continua aberta com o que foi
  digitado, o pedido não muda, e aparece o aviso de falha de envio que o formulário já tem.
- **Centro desmarcado ou peça retirada da lista depois do envio.** Pedidos já registrados não mudam:
  o destino e os itens são gravados como estavam no envio, e o atendimento aceita qualquer centro de
  custo, como nos outros formulários.
- **Estoque que muda entre abrir o formulário e enviar.** Como nos outros formulários: o envio é
  recusado com o estoque atual e o pedido é mantido para correção.

## Requirements *(mandatory)*

### Functional Requirements

**Formulário**

- **FR-001**: O sistema DEVE oferecer um formulário público, sem login, de reposição de peças das
  viaturas, listado na página inicial dos formulários junto com os existentes, com título, exemplo de
  busca e ícone próprios.
- **FR-002**: O formulário DEVE ter o mesmo cabeçalho dos outros formulários públicos (nome completo,
  destino e observação), as mesmas proteções contra abuso, os mesmos limites e o mesmo requisito de
  JavaScript.
- **FR-002a**: Além do cabeçalho comum, o formulário DEVE ter um campo opcional "Nº da ocorrência",
  o número da ocorrência da Ordem de Serviço em que as peças foram usadas: texto livre de até 20
  caracteres; acima disso, o envio é recusado com um erro no próprio campo, como os demais erros
  de tamanho do cabeçalho. O valor é o digitado sem os espaços nas pontas (os de dentro ficam): é
  ele que conta para o limite, que é gravado e que é comparado no reenvio, e a busca do painel
  também tira os espaços das pontas do que se procura. Preenchido, ele DEVE ser
  gravado com o pedido, mostrado ao encarregado na tela de sucesso e ao almoxarifado no detalhe
  do pedido, no recibo e na linha do pedido na lista do painel, e a busca do painel DEVE achar o pedido por ele (além de número,
  solicitante e recebedor); em branco, o pedido segue normalmente. O aviso no Telegram não o mostra. Um reenvio só é o mesmo pedido se o número também for o mesmo. Como o
  resto do que vem do encarregado, o número não muda depois do envio (a edição do atendimento não o
  altera). Os outros formulários não ganham esse campo.
- **FR-003**: Com um toque no passo dos materiais, o encarregado DEVE ver a lista de peças comuns
  inteira (da ordem de 40 linhas) sem digitar nada, na ordem definida pela lista, e preencher a
  quantidade direto em cada linha, como na folha de papel, sem um passo de busca ou de confirmação por
  peça, pondo todas no pedido de uma vez. As linhas sem quantidade não entram no pedido; as peças
  bloqueadas aparecem sem campo de quantidade, com o motivo. Se alguma linha tiver erro, nada é posto
  no pedido e cada erro aparece na própria linha. Cada linha mostra o nome, a unidade do cadastro do
  SCPI e o estoque disponível, com o mesmo texto da busca. Diferente da busca, que põe os bloqueados
  no fim, a folha mantém a ordem da lista, como o papel.
- **FR-003a**: Os materiais fora da lista DEVEM entrar pela pesquisa (FR-005), no papel das linhas em
  branco da folha, e somar-se às peças da lista num só pedido, que o encarregado revisa antes de
  enviar.
- **FR-003b**: A folha DEVE ser usável só com o teclado (o foco vai para a primeira linha ao abrir e
  volta ao botão ao fechar; Esc fecha sem mudar o pedido), cada campo DEVE ter o nome da peça como
  rótulo e cada erro DEVE ficar ligado ao seu campo. No celular ela ocupa a tela; no computador, um
  painel com rolagem.
- **FR-004**: O formulário DEVE ficar indisponível, com a mesma mensagem dos outros formulários
  públicos, quando o saldo de estoque nunca foi importado ou quando não há nenhum material a oferecer
  (nem peça da lista, nem material do catálogo AB).
- **FR-005**: O encarregado DEVE poder pesquisar pelo nome, no mesmo formulário, os materiais do
  catálogo "Ferramentas, peças e materiais", com o mesmo conjunto de materiais que esse formulário
  oferece no momento, e cada material DEVE aparecer uma só vez nos resultados.
- **FR-006**: Peças da lista e materiais pesquisados DEVEM seguir a mesma regra de quantidade dos
  formulários públicos: fração só em unidade fracionável, teto no estoque disponível exibido, sem
  limite de reposição próprio.

**Destino**

- **FR-007**: O destino DEVE ser um dos centros de custo marcados como de equipe de manutenção.
  Quem mantém os cadastros DEVE poder marcar e desmarcar um centro de custo como de equipe de
  manutenção, e a mudança DEVE valer no próximo acesso ao formulário. Um centro com várias linhas
  (uma por placa) é de equipe se alguma delas estiver marcada. O formulário DEVE oferecer só
  esses centros como destino e o envio DEVE recusar qualquer outro com a mensagem de destino
  inválido de hoje. Nos outros formulários, os destinos aceitos não mudam.
- **FR-008**: O pedido NÃO identifica a viatura: o destino é o centro de custo da equipe, sem placa,
  e as opções de destino deste formulário não incluem "centro — placa".
- **FR-008a**: Sem nenhum centro de custo marcado como de equipe de manutenção, o formulário DEVE
  ficar indisponível, com a mesma mensagem dos outros formulários indisponíveis, e a saúde do
  catálogo DEVE avisar o motivo.

**Pedido e atendimento**

- **FR-009**: O pedido DEVE ser registrado como os dos outros formulários públicos, com uma origem
  própria que o identifique no painel, no filtro por origem, no detalhe e no aviso ao almoxarifado.
- **FR-010**: Atendimento, trocas e acréscimos pelo almoxarifado, edição do atendimento, recibo e
  lançamento no SCPI DEVEM funcionar para estes pedidos exatamente como para os dos outros
  formulários públicos, sem regra própria.

**Lista de peças comuns**

- **FR-011**: Quem mantém os cadastros DEVE poder incluir, retirar e ordenar materiais do cadastro na
  lista de peças comuns, e a mudança DEVE valer no próximo acesso ao formulário.
- **FR-011a**: Cada linha da lista DEVE corresponder a exatamente um material do cadastro, e um
  material DEVE aparecer no máximo uma vez na lista.
- **FR-011b**: Quem mantém a lista DEVE poder dar a cada linha um nome exibido opcional (o nome que a
  equipe conhece, como o da folha de papel); sem ele, a linha mostra o nome do cadastro. Esse nome
  vale também quando a peça é achada pela pesquisa. O pedido grava o nome que o encarregado viu,
  junto com o código do material, e é esse nome, com o código, que o almoxarifado vê no painel, no
  atendimento e no recibo (como já acontece com o nome exibido da lista de limpeza).
- **FR-012**: Uma peça da lista DEVE aparecer no formulário enquanto o material estiver visível no
  cadastro, independentemente de estar no catálogo AB.
- **FR-013**: A saúde do catálogo DEVE mostrar quantas peças o formulário oferece, avisar quando ele
  estiver indisponível, com o motivo (sem saldo importado, nada a oferecer ou nenhum centro marcado),
  e listar as peças da lista que não aparecem por estarem ocultas no SCPI.

**Não regressão**

- **FR-014**: Os formulários existentes (limpeza, "Ferramentas, peças e materiais" e saída avulsa)
  DEVEM continuar com o mesmo conteúdo e comportamento; uma peça incluída na lista de peças comuns
  não sai do catálogo AB nem da lista de limpeza.

### Key Entities

- **Lista de peças comuns**: conjunto curado de materiais do cadastro que as equipes de manutenção
  costumam repor nas viaturas, com uma ordem de exibição. Cada linha é um material, sem repetição,
  com um nome exibido opcional. Uma só lista para todas as equipes. Não define quantidade-alvo.
- **Pedido de reposição**: pedido público como os demais, com origem própria e o número da
  ocorrência opcional; seus itens podem vir da lista ou da pesquisa no catálogo AB, sem distinção
  depois de registrados.
- **Centro de custo da equipe**: centro de custo cadastrado pelo almoxarifado no SCPI e no sistema
  para cada equipe de manutenção e marcado como de equipe de manutenção; é o destino do pedido. No
  atendimento, o destino sugere o centro de custo da saída no SCPI, que o almoxarifado pode trocar,
  como nos outros formulários. A marca só restringe os destinos deste formulário.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O encarregado consegue pedir a reposição de 5 peças da lista em até 2 minutos no
  celular, sem usar a pesquisa, contados de abrir o formulário até a tela com o número do pedido
  (medido no uso real, com um encarregado, depois da implantação).
- **SC-002**: 100% dos pedidos deste formulário passam pelo atendimento, recibo e lançamento no SCPI
  sem nenhum passo diferente dos pedidos dos outros formulários públicos.
- **SC-003**: Uma mudança na lista de peças comuns aparece no formulário no próximo acesso, sem nova
  publicação do sistema.
- **SC-004**: Nenhum material aparece duas vezes nos resultados do formulário.
- **SC-005**: Os formulários existentes não mudam: seus testes automatizados continuam passando sem
  alteração de comportamento.

## Assumptions

- O público é o encarregado da equipe de manutenção, no celular, sem login; os limites por IP e por
  nome e as demais proteções dos formulários públicos bastam.
- Há uma única lista de peças comuns para todas as equipes. Uma lista por equipe ou por viatura e uma
  quantidade-padrão de reposição ficam para quando existirem na operação.
- A quantidade é livre até o estoque disponível "por enquanto": um limite próprio de reposição pode
  vir numa especificação futura, quando houver o conjunto-padrão.
- A lista é mantida pelo almoxarifado, pela área administrativa, como as outras listas mantidas à mão.
  A carga inicial da lista é feita pelo almoxarifado a partir da relação de peças comuns que ele já
  tem; o conteúdo da lista não é definido por esta especificação.
- A pesquisa livre usa o catálogo AB como ele é hoje (materiais com saídas no período da curva ABC,
  sem os da lista de limpeza e sem os grupos ocultos), com o mesmo estoque exibido.
- Os centros de custo das equipes serão criados pelo almoxarifado no SCPI, cadastrados no sistema e
  marcados como de equipe de manutenção; até haver ao menos um marcado, o formulário fica
  indisponível (FR-008a).
- A marca de equipe de manutenção e a lista de peças comuns são mantidas pela área administrativa
  que já existe, pelos mesmos usuários que hoje mantêm a lista de limpeza e os centros de custo. Uma página própria de configuração dos formulários fica para depois (ver Fora do
  escopo).
- O tipo de saída lançado no SCPI e o robô de lançamento não mudam.
- Nome mostrado ao encarregado: "Reposição de peças das viaturas".

### Fora do escopo

- Conjunto-padrão de peças por viatura ou por equipe e limite de reposição até um padrão.
- Controle do estoque que está dentro de cada viatura e identificação da viatura no pedido.
- Painel de configuração dos formulários, em que o almoxarifado configuraria pela interface cada
  formulário e o seu conteúdo (lista de materiais, destinos aceitos, textos). Desejo registrado pelo
  usuário em 2026-10-22 para uma especificação futura; esta funcionalidade não deve impedi-lo, mas
  não o antecipa.
- Formulário da oficina mecânica (especificação própria, 007).
- Mudanças no catálogo AB, na lista de limpeza, no robô do SCPI ou no cabeçalho dos outros
  formulários.
