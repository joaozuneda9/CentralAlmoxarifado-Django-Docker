# Feature Specification: Conciliação dos lançamentos do robô com o SCPI

**Feature Branch**: `claude/conciliacao-scpi`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: comprovar, com evidência independente do robô, que cada requisição que
o robô de lançamento diz ter lançado existe no SCPI com o conteúdo entregue, e impedir que um lote em
"Verificar no SCPI" seja relançado quando o SCPI pode já tê-lo salvo. A conversa de desenho, de
2026-11-03 a 2026-11-04, partiu da hipótese do usuário (disparo manual do lançamento real →
atualização do estoque → atualização das saídas oficiais → conciliação) e terminou com a sequência
**extrair as saídas antes → lançar → extrair as saídas depois → conciliar**, sem o estoque.

## Contexto

Hoje a única prova de que um lote foi lançado é a afirmação do próprio robô: ele lê o número da
requisição na tela do formulário depois do Salvar e o grava na linha de saída. As conferências que
ele faz antes do Salvar também leem só a tela, e já falharam duas vezes de formas diferentes: a
quantidade que voltava a 1 depois do "Novo Item" (já tratada) e o **Tipo Saída que a tela mostrava
como BALCÃO e o SCPI gravou vazio**.

Os fatos abaixo vêm do banco de produção de 2026-11-03 e de consultas do usuário no SCPI:

- **Quatro camadas, quatro papéis.** O pedido do funcionário não entra na conferência (a diferença
  entre pedido e entrega é decisão do atendimento). A **entrega confirmada** (as linhas de saída como
  o robô as leu) é o que deveria estar no SCPI. A **tentativa** (registro da execução, journal, número
  gravado) é só a afirmação do robô. O **registro oficial** é a requisição no SCPI, vista pelo
  relatório "Relação de Requisições" de saída, extraído por outra tela e outra sessão do navegador.
- **O vínculo se perde hoje.** O robô grava o número visível da requisição (formato `003588/26`). O
  importador de saídas guarda só o identificador interno (`ID_REQUI`), o código, a data, a quantidade
  e o valor, e descarta o número visível (`REQUI`), o centro de custo (`CODCCUSTO`) e as observações
  (`OBS_CABECALHO`). No CSV real sem filtro (23/10 a 04/11, 84 requisições) o identificador interno
  foi sempre o número visível mais 100; as diferenças de 99 e 101 da primeira medição vinham de
  casamentos só pelo conteúdo. O vínculo não depende disso: usa o número visível, que o relatório traz.
- **Casar só pelo conteúdo não basta.** Dos 137 lotes lançados conferíveis, 115 casam com uma única
  saída oficial por data, código e quantidade; 7 são ambíguos (AV-000040, 041 e 042 são três
  requisições idênticas no mesmo dia); 15 não casam.
- **Sete requisições ficaram com o Tipo Saída vazio** no SCPI, confirmado pelo usuário: as dos lotes
  AV-000014, 036, 059, 067, 071, 072 e 073. Em todas, o robô registrou "Tipo Saída = BALCÃO" na sua
  conferência. Como o relatório é extraído com o filtro BALCÃO, elas **sumiram** dele: o erro apareceu
  como ausência, não como divergência, e ninguém percebeu por duas semanas. Os casos com registro
  vieram logo depois de um lote que falhou nos itens, com o formulário reaproveitado.
- **Código diferente no registro oficial.** Nos lotes AV-000083 e 084 o robô digitou 024.006.011 e a
  grade confirmou esse código antes do Salvar; o relatório de 27/10 já mostrava 006.011.020 (ID 3688 e
  3689), um código antigo do mesmo desengripante. A causa (recodificação no SCPI, edição da requisição
  ou outro produto gravado) ainda não foi apurada.
- **Nenhuma resposta perdida até agora.** Todos os "Verificar no SCPI" reais foram mensagens do SCPI
  depois do clique (placa obrigatória, saldo negativo, data em outro mês). O P-000018 ficou em
  verificar duas vezes, foi relançado e tem uma única requisição oficial (003534/26).
- **Numeração sequencial.** Nos 105 pares de lançamentos seguidos dentro de uma mesma execução, o
  número seguinte foi sempre o anterior mais 1; e as tentativas recusadas não consumiram número
  (execução 8: 003495 às 9h59, falha às 10h03, 003496 às 10h06; execução 28: 003532, falha, 003533).
- **O SCPI só é estável das 7h às 17h.** As três falhas de extração de saídas do último mês foram às
  6h30, horário da atualização diária; dentro da janela, todas deram certo.
- **O relatório de saídas não é um espelho.** A gravação só acrescenta: edição ou exclusão feita
  depois no SCPI nunca chega ao sistema.

## Clarifications

### Session 2026-11-04

Decisões do usuário, uma a uma, na conversa de desenho:

- Q: O que é preciso para liberar um lote "Verificar no SCPI" para relançar? → A: uma extração do
  registro oficial feita depois da tentativa e **nenhuma requisição candidata**; havendo candidata, o
  lote só se resolve informando o número ou marcando "não lançar". A recusa é no servidor.
- Q: O que é uma requisição candidata? → A: **qualquer** requisição oficial cujo número caia entre o
  último número conhecido antes da tentativa e o primeiro depois, seja qual for o conteúdo ou o tipo;
  o conteúdo só ordena as candidatas na tela. Uma requisição manual criada no meio da execução bloqueia
  (lado seguro).
- Q: De onde vem o registro oficial? → A: da "Relação de Requisições" de saída **sem o filtro de
  tipo**, guardando o arquivo bruto de cada extração.
- Q: Quanto tempo se guarda o arquivo bruto? → A: **60 dias**, como os backups; o veredito, as linhas
  das requisições ligadas a lotes e a impressão digital do arquivo ficam para sempre.
- Q: Qual período cada extração cobre? → A: do **dia anterior** à data mais antiga envolvida até o
  **dia seguinte** a hoje (o SCPI aceita fim no futuro).
- Q: Onde fica o resultado? → A: num **registro próprio**, por lote e por extração, sem mudar o status
  das linhas de saída nem o que o robô grava.
- Q: Como gravar a identidade do lote no registro oficial? → A: o robô escreve
  "Central Almoxarifado <lote>" na primeira linha do campo **Observações** da requisição, que numa
  requisição nova vem sempre vazio; no relatório é a coluna `OBS_CABECALHO`. O lote nas observações
  **prova presença**; a falta dele **não prova nada**.
- Q: E se a extração antes do lançamento falhar? → A: depois de algumas tentativas, a execução
  **termina sem lançar** e sem tocar em nenhum lote.
- Q: O estoque entra? → A: **não**. A importação de estoque segue de meia em meia hora; a defasagem
  entre entrega e lançamento (mediana de 5,1 horas) fica como limite conhecido.
- Q: Um lote é conferido de novo depois? → A: **sim**, em toda extração que cobrir a sua data (a
  diária volta 9 dias); uma diferença em relação à primeira conferência vira o resultado secundário
  "alterado no SCPI depois do lançamento", sem mudar o veredito do lançamento.
- Q: Como se corrige um lote lançado "Não encontrado" ou com "Vínculo em conflito"? → A: só
  **informando o número certo**. No "Não encontrado", a pessoa lança à mão no SCPI, se preciso, e
  informa o número; no "Vínculo em conflito", escolhe qual das duas requisições vale. O robô nunca
  relança um lote lançado, e a conciliação seguinte confere o número informado.

### Session 2026-11-05

- Q: O campo Observações leva só o lote? → A: não. A observação da saída registrada no Central vai
  junto, num parágrafo novo depois da marca do lote (decisão do usuário, depois do `--dry-run` do
  AV-000165 que confirmou o campo no SCPI real).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Saber se cada lote lançado está no SCPI como foi entregue (Priority: P1)

Depois de cada execução real do robô, quem cuida dos lançamentos vê, para cada lote lançado, se a
requisição oficial existe e confere com a entrega, ou o que está diferente, sem abrir o SCPI.

**Why this priority**: é o erro que já aconteceu sete vezes sem ninguém notar (Tipo Saída vazio). Um
lançamento errado no SCPI afeta a contabilidade do estoque oficial e só o almoxarifado pode corrigi-lo.

**Independent Test**: com um SCPI simulado que grava uma requisição com o tipo vazio e outra certa, uma
execução real seguida da conciliação mostra um lote "Comprovado" e o outro "Divergente: tipo".

**Acceptance Scenarios**:

1. **Given** um lote lançado cuja requisição oficial tem o mesmo tipo, data, centro de custo e a mesma
   lista de código e quantidade, **When** a extração depois do lançamento é conciliada, **Then** o
   lote aparece como "Comprovado".
2. **Given** o lote AV-000036, cuja requisição 003531/26 ficou com o Tipo Saída vazio, **When** a
   extração é conciliada, **Then** o lote aparece como "Divergente", com o campo tipo nomeado e os dois
   valores (entregue BALCÃO, no SCPI vazio).
3. **Given** os lotes AV-000083 e 084 (lançado 024.006.011, no SCPI 006.011.020), **When** conciliados,
   **Then** aparecem como "Divergente" no código, com os dois códigos crus, sem que o de/para seja usado
   para aceitar a diferença.
4. **Given** os lotes AV-000040, 041 e 042, com o mesmo conteúdo no mesmo dia, **When** conciliados,
   **Then** cada um fica ligado à sua própria requisição, pelo número e pelo lote nas observações.
5. **Given** um lote cuja requisição oficial tem um código a mais, um a menos, uma quantidade diferente
   ou o mesmo código em duas linhas, **When** conciliado, **Then** aparece como "Divergente", com cada
   diferença listada.
6. **Given** um lote lançado e nenhuma extração feita depois do lançamento, **When** a pessoa abre a
   aba, **Then** o lote aparece como "Aguardando conferência", nunca como comprovado nem como ausente.

---

### User Story 2 - Resolver um "Verificar no SCPI" sem risco de duplicar (Priority: P1)

Quando o robô não tem certeza se o SCPI salvou, a pessoa vê se há alguma requisição que pode ser a
daquela tentativa e só consegue liberar o lote para relançar quando não há nenhuma.

**Why this priority**: uma requisição duplicada é o único erro que o sistema não pode desfazer
(constituição, Princípio III). Hoje a única barreira é a caixa "Conferi no SCPI", marcada à mão.

**Independent Test**: com o SCPI simulado, um Salvar que grava a requisição e depois falha deixa o
lote em verificar; a liberação é recusada porque a extração seguinte mostra uma candidata. Um Salvar que
falha antes de gravar deixa o intervalo vazio, e a liberação passa.

**Acceptance Scenarios**:

1. **Given** a tentativa do P-000018 na execução 8, entre os lançamentos 003495 e 003496, **When** a
   extração depois da tentativa é conciliada, **Then** não há candidata e a liberação para relançar é
   permitida.
2. **Given** um lote em verificar com uma requisição oficial no intervalo de números da tentativa,
   **When** a pessoa tenta liberar para relançar, **Then** o servidor recusa e mostra as candidatas, com
   número, data, tipo, centro de custo e itens, ordenadas pela semelhança com a entrega.
3. **Given** uma candidata com o lote nas observações, **When** a pessoa abre o lote, **Then** essa
   candidata vem marcada como "é esta", e confirmá-la grava esse número no lote.
4. **Given** uma requisição do intervalo com o lote de **outro** lote nas observações, **When** as
   candidatas são calculadas, **Then** ela não aparece como candidata deste lote.
5. **Given** um lote em verificar sem nenhuma extração bem-sucedida posterior à tentativa (como a
   liberação de 03/11 às 15h26, depois de uma tentativa às 12h24 e da última extração às 6h30),
   **When** a pessoa tenta liberar, **Then** o servidor recusa e diz que falta a conferência no SCPI.
6. **Given** uma candidata qualquer, **When** a pessoa marca "não lançar" ou informa o número, **Then**
   o lote se resolve como hoje, com o registro de quem fez.

---

### User Story 3 - Lançar só com a base de comparação garantida (Priority: P1)

Uma execução real só lança se conseguir, antes, extrair o registro oficial do período; e extrai de
novo logo depois de lançar.

**Why this priority**: sem a extração de antes, uma falha no primeiro lote da execução fica sem limite
inferior (o caso da execução 49: 19 requisições entre 003692 e 003712) e o lote só se resolve à mão.

**Independent Test**: com a extração simulada falhando, uma execução real termina sem tocar em nenhum
lote; com ela funcionando, a execução registra o maior número existente antes de lançar.

**Acceptance Scenarios**:

1. **Given** lotes escolhidos para lançar, **When** a execução real começa, **Then** ela extrai o
   registro oficial do período (do dia anterior à data mais antiga entre os lotes escolhidos e os lotes
   em verificar ainda abertos até o dia seguinte a hoje) e registra o maior número de requisição
   existente.
2. **Given** a extração antes falhando em todas as tentativas, **When** a execução real começa,
   **Then** ela termina com a falha explicada ("SCPI instável, tente de novo") e nenhum lote muda.
3. **Given** uma execução real que lançou lotes, **When** o último lote termina, **Then** a execução
   extrai o mesmo período de novo e concilia os lotes daquela execução.
4. **Given** a extração depois falhando, **When** a execução termina, **Then** os lotes ficam
   "Aguardando conferência" e a pessoa pode pedir a conferência de novo pela aba.
5. **Given** uma simulação (sem lançamento real), **When** ela roda, **Then** nenhuma extração nem
   conciliação acontece.

---

### User Story 4 - Gravar a identidade do lote dentro do registro oficial (Priority: P2)

O robô escreve o lote nas observações da requisição, e a conciliação usa isso para ligar a requisição
ao lote, achar duplicações e pegar um número lido errado.

**Why this priority**: torna o vínculo independente do número que o robô lê na tela. Não é P1 porque a
ausência das observações não prova nada: a regra da sequência continua sendo a prova de que nada foi
salvo.

**Independent Test**: com o SCPI simulado guardando as observações, duas requisições com o mesmo lote
nas observações levam o lote a "Duplicado"; observações e número apontando para requisições diferentes
levam a "Vínculo em conflito".

**Acceptance Scenarios**:

1. **Given** um lote a lançar, **When** o robô preenche a requisição, **Then** o campo Observações
   recebe "Central Almoxarifado <lote>" na primeira linha e, se a saída tem observação no Central,
   "Obs.: <observação>" num parágrafo novo.
2. **Given** duas requisições oficiais com o mesmo lote nas observações, ou o mesmo número gravado em
   dois lotes, **When** conciliadas, **Then** o lote aparece como "Duplicado", com as duas requisições.
3. **Given** observações que apontam para uma requisição e um número gravado que aponta para outra,
   **When** conciliados, **Then** o lote aparece como "Vínculo em conflito", com as duas.
4. **Given** uma requisição do lote sem o texto nas observações (o campo pode se perder como o tipo),
   **When** conciliada, **Then** o vínculo vem só pelo número e isso fica indicado, sem marcar o lote
   como divergente por esse motivo.
5. **Given** um lote lançado com "Vínculo em conflito" ou "Não encontrado", **When** a pessoa informa o
   número da requisição certa, **Then** o lote passa a apontar para ela, volta a "Aguardando" até a
   próxima conferência, guarda o número anterior e quem corrigiu, e nunca volta à fila do robô; um
   número já gravado em outro lote é recusado.

---

### User Story 5 - Perceber mudanças feitas no SCPI depois do lançamento (Priority: P2)

Uma requisição já conferida que é alterada ou excluída depois no SCPI aparece como "alterado no SCPI
depois do lançamento".

**Why this priority**: uma exclusão posterior significa material entregue sem baixa no SCPI. É menos
urgente que o erro do próprio lançamento.

**Independent Test**: com o SCPI simulado, uma requisição comprovada que é excluída antes da extração
do dia seguinte gera o resultado secundário, com o veredito do lançamento intacto.

**Acceptance Scenarios**:

1. **Given** um lote comprovado, **When** uma extração posterior que cobre a sua data mostra outro
   código, outra quantidade, outro tipo ou a requisição ausente, **Then** o lote ganha o resultado
   "alterado no SCPI depois do lançamento", com o campo e a data da extração, e o veredito do
   lançamento continua o mesmo.
2. **Given** um lote divergente corrigido à mão no SCPI, **When** a extração seguinte o mostra igual à
   entrega, **Then** o lote passa a "Comprovado", com o histórico da divergência mantido.
3. **Given** um lote cuja data já não é coberta por nenhuma extração nova, **When** as extrações
   seguem, **Then** ele não é mais revisto.

---

### User Story 6 - Guardar a evidência por tempo limitado (Priority: P3)

Cada extração guarda o arquivo exatamente como veio do SCPI, por 60 dias, para provar o que o SCPI
mostrou caso a leitura tenha descartado algo.

**Why this priority**: a evidência só é consultada quando há dúvida sobre um veredito; o veredito e as
linhas ligadas a lotes ficam para sempre de qualquer forma.

**Independent Test**: uma extração gera o arquivo bruto comprimido e a sua impressão digital; o
arquivo com mais de 60 dias é apagado e o veredito continua consultável.

**Acceptance Scenarios**:

1. **Given** uma extração, **When** ela termina, **Then** o arquivo bruto fica guardado comprimido, com
   a impressão digital do conteúdo registrada.
2. **Given** uma extração igual à anterior (mesma impressão digital), cujo bruto ainda está guardado,
   **When** ela termina, **Then** não se guarda um arquivo novo; se o bruto da anterior já foi apagado,
   a nova guarda o seu.
3. **Given** um arquivo bruto com mais de 60 dias, **When** a limpeza roda, **Then** ele é apagado e o
   veredito, as linhas ligadas a lotes e a impressão digital continuam no banco.

### Edge Cases

- **Relatório ainda sem a requisição recém-salva**: um lote só vira "Não encontrado" quando a extração
  já traz alguma requisição com número maior que o do lote; antes disso, continua "Aguardando
  conferência".
- **Extração vazia ou cortada**: uma extração sem nenhuma linha num período em que há lotes lançados
  conta como falha, nunca como "todos os lotes ausentes" (constituição, Princípio IV).
- **Falha no último lote da execução**: sem lançamento seguinte na execução, o limite superior do
  intervalo é a extração depois; uma requisição manual feita entre o fim da execução e essa extração
  vira candidata (lado seguro).
- **Lote em verificar de antes desta funcionalidade** (sem o maior número registrado no início da
  execução): o limite inferior é o maior número conhecido antes da tentativa, por qualquer extração ou
  lançamento; o intervalo pode ficar largo e bloquear.
- **Data da saída no passado**: os lotes de 03/11 com data de 29/10 exigem que o período comece em
  28/10; o período cobre sempre a data mais antiga envolvida.
- **Virada do ano**: o número da requisição traz o ano (`/26`, `/27`); a comparação de intervalo
  respeita o ano.
- **Requisição cancelada no SCPI**: se o relatório marcar requisições canceladas, uma requisição
  cancelada ligada a um lote conta como "Não encontrado"; o formato depende do CSV real.
- **Recebedor e placa**: o relatório traz os dois (`RECEBE`, `PLACA`). O SCPI preenche a placa a
  partir do centro de custo de uma viatura: o AV-000106 foi lançado sem placa no centro
  "UNO MILLE SMART, CYU4099" e o relatório mostra `CYU4A99`, a placa desse centro no cadastro.
- **Centro de custo renomeado no SCPI**: o AV-000129 foi lançado no centro 251, "Equipe de Manutenção
  #168", e o relatório mostra o mesmo código 251 com o nome "Viatura de Manutenção #68". O código
  decide; o nome diferente é só uma nota.
- **Mesmo texto, formas Unicode diferentes**: o nome do centro gravado no lote AV-000101 está com os
  acentos decompostos e o do relatório, compostos; uma comparação de texto cru os daria como
  diferentes.
- **Requisições que não são do robô**: o relatório traz também ajustes de inventário e transferências
  (entrada e saída na mesma requisição, sem tipo e sem responsável, observações longas), requisições
  "OUTRA" e saídas à mão de outras pessoas, algumas com data anterior ao dia em que foram feitas (a
  003728/26, com data de 20/10, foi registrada em 04/11). Nenhuma é conferida; todas podem ser
  candidatas.
- **Lote resolvido à mão** (número informado por uma pessoa): é conciliado como qualquer outro, e a
  origem do número (robô ou pessoa) fica visível.
- **Requisição à mão fora do período**: uma requisição feita à mão com `DTPAG` fora do período da
  extração não aparece e não vira candidata. Isso não afrouxa a proteção contra duplicar, porque a
  requisição que o robô pode ter salvo tem sempre a data do lote, que o período cobre; só se perde o
  bloqueio a mais, que era lado seguro.
- **Movimentos manuais no SCPI**: requisições sem lote nas observações e sem número ligado a um lote
  não são conferidas; só entram como candidatas de um lote em verificar.
- **Extração fora da janela das 7h às 17h**: a extração diária roda depois das 7h; uma execução real
  disparada fora da janela pode falhar já na extração de antes e então não lança.

## Requirements *(mandatory)*

### Functional Requirements

**Extração do registro oficial**

- **FR-001**: O sistema DEVE extrair do SCPI a "Relação de Requisições" de saída **de todos os
  tipos**, guardando de cada linha o número da requisição, o identificador interno, a data, o tipo, o
  centro de custo, as observações, o código, a quantidade e as demais colunas que o relatório trouxer.
- **FR-002**: O período de cada extração DEVE ir do dia anterior à data mais antiga envolvida até o dia
  seguinte a hoje; "envolvida" são as datas dos lotes da execução e dos lotes em verificar ainda
  abertos (ou, na extração diária, o período automático de hoje). O relatório filtra por `DTPAG`, que
  nas requisições do robô é a data digitada: o período sempre cobre as requisições que o robô pode ter
  salvo.
- **FR-003**: Cada extração DEVE guardar o arquivo bruto comprimido e a impressão digital do seu
  conteúdo; uma extração com a mesma impressão digital de outra cujo bruto ainda está guardado NÃO
  PODE gerar arquivo novo e aponta para ela. Se o bruto daquela já foi apagado, a extração nova guarda
  o seu.
- **FR-004**: O arquivo bruto DEVE ser apagado depois de 60 dias; as linhas das requisições ligadas a
  lotes, os vereditos e a impressão digital DEVEM ficar para sempre.
- **FR-005**: Uma extração vazia num período com lotes lançados, ou que não puder ser lida por inteiro,
  DEVE contar como falha e NÃO PODE produzir vereditos.
- **FR-006**: O comportamento das saídas usadas na curva ABC e no ranking do formulário AB NÃO PODE
  mudar: continuam só as saídas BALCÃO, com as mesmas regras de hoje.
- **FR-007**: A extração diária DEVE rodar depois das 7h e também conciliar os lotes cobertos pelo seu
  período.

**Execução real do robô**

- **FR-008**: Antes de lançar, uma execução real DEVE extrair o registro oficial (FR-002) e registrar o
  maior número de requisição existente naquele momento (o "piso").
- **FR-009**: Se a extração antes falhar depois de algumas tentativas, a execução DEVE terminar com a
  falha explicada e NÃO PODE mudar nenhum lote.
- **FR-010**: A execução DEVE registrar, em ordem, cada tentativa de lançamento: o lote, o momento, o
  resultado e o número obtido, quando houver.
- **FR-011**: O robô DEVE escrever "Central Almoxarifado <lote>" na primeira linha do campo
  Observações de cada requisição que preencher. Se a saída tem observação no Central (a do
  atendimento ou da saída avulsa, a mesma em todas as linhas do lote), ela vai num parágrafo novo,
  como "Obs.: <observação>", com as quebras de linha dela trocadas por espaço. O "Obs.: " impede que
  uma observação começada por uma data parta o registro na leitura do relatório, e o ";" vira
  "," porque é o separador de campos do CSV, que não usa aspas.
- **FR-012**: Depois do último lote, a execução DEVE extrair de novo o mesmo período e conciliar os
  lotes dela; se essa extração falhar, os lotes ficam "Aguardando conferência".
- **FR-013**: A simulação (sem lançamento real) NÃO PODE extrair nem conciliar.
- **FR-014**: Nenhuma etapa nova pode afrouxar as garantias de nunca lançar duas vezes: o lote continua
  em lançamento confirmado no banco antes do Salvar, e falha depois do clique continua em verificar.

**Vínculo e veredito de um lote lançado**

- **FR-015**: Uma requisição oficial DEVE ser ligada a um lote pelo lote nas observações e pelo número
  gravado no lote; quando os dois existem, DEVEM apontar para a mesma requisição.
- **FR-016**: Cada lote lançado DEVE receber, por extração que cobre a sua data, um destes vereditos:
  - **Aguardando conferência**: ainda não há conferência conclusiva depois do lançamento: nenhuma
    extração bem-sucedida, ou só as que ainda não trazem a requisição nem um número maior;
  - **Comprovado**: requisição ligada, com o mesmo tipo, a mesma data, o mesmo centro de custo, o
    mesmo recebedor, a placa esperada e a mesma lista de código e quantidade (mesmo número de linhas,
    quantidades exatas, códigos sem de/para);
  - **Divergente**: requisição ligada com alguma diferença, cada uma nomeada com os dois valores;
  - **Não encontrado**: nem o número gravado nem o lote nas observações aparecem, e a extração já traz
    requisição com número maior que o do lote;
  - **Duplicado**: duas requisições com o lote nas observações, ou o mesmo número gravado em dois lotes;
  - **Vínculo em conflito**: observações e número apontam para requisições diferentes.
- **FR-017**: O veredito do lançamento DEVE vir da primeira extração bem-sucedida feita depois do
  lançamento que dê um veredito conclusivo (diferente de "Aguardando conferência"); as extrações
  seguintes que cobrirem a data do lote DEVEM conferi-lo de novo e registrar
  qualquer diferença como "alterado no SCPI depois do lançamento", com o campo e a extração, sem mudar o
  veredito do lançamento.
- **FR-018**: Um lote divergente que uma extração posterior mostrar igual à entrega DEVE passar a
  "Comprovado", mantendo o histórico.
- **FR-019**: Recebedor e placa DEVEM ser conferidos pelas colunas do relatório (`RECEBE`, `PLACA`).
  A placa esperada é a do lote ou, se o lote não tiver placa, a do centro de custo no cadastro; uma
  placa que o SCPI preencheu a partir do centro NÃO PODE contar como divergência.
- **FR-019a**: O centro de custo DEVE ser comparado pelo código (`CODCCUSTO` contra o código do centro
  do lote no cadastro); um nome diferente com o mesmo código DEVE aparecer como nota, sem tornar o lote
  divergente.
- **FR-019b**: Toda comparação de texto (tipo, nome do centro, recebedor) DEVE ignorar a forma Unicode
  dos acentos, as maiúsculas e os espaços nas pontas. Códigos são comparados por `norm_u`, como em todo
  o sistema (constituição, Princípio I, igual à collation do banco), e nunca pelo de/para; quantidades
  são comparadas exatas.
- **FR-020**: O de/para NUNCA pode aceitar sozinho uma diferença de código; pode só ser mostrado como
  explicação, quando houver par.
- **FR-021**: A conciliação NÃO PODE mudar o status, o número, a data de lançamento nem a mensagem das
  linhas de saída; o resultado fica num registro próprio.

**Lote em verificar**

- **FR-022**: Para um lote em verificar, o sistema DEVE calcular as candidatas: toda requisição oficial
  com número acima do último número conhecido antes da tentativa (o maior entre o piso da execução e
  os lançamentos anteriores da mesma execução) e abaixo do primeiro número obtido depois da tentativa
  na mesma execução; sem lançamento posterior na execução, todas as acima do limite inferior presentes
  na extração depois.
- **FR-023**: Uma candidata com o lote nas observações DEVE vir marcada como "é esta"; uma requisição
  com outro lote nas observações NÃO PODE ser candidata deste lote. As candidatas DEVEM vir ordenadas
  pela semelhança com a entrega.
- **FR-024**: Liberar um lote em verificar para relançar DEVE ser recusado no servidor quando não houver
  extração bem-sucedida posterior à tentativa e cobrindo a data do lote, ou quando houver ao menos uma
  candidata.
- **FR-025**: Confirmar a candidata "é esta" DEVE gravar o número dela no lote pelo caminho de
  resolução que já existe (informar a requisição), com o registro de quem fez.
- **FR-026**: Um lote **lançado** que fique "Não encontrado" ou com "Vínculo em conflito" DEVE ser
  corrigido só **informando o número da requisição certa**: no "Não encontrado", o número que a pessoa
  achou no SCPI ou o da requisição que ela mesma lançou à mão; no "Vínculo em conflito", uma das duas
  requisições apontadas (a das observações ou a do número gravado). O robô NUNCA relança um lote
  lançado, e o status das linhas continua lançado. A correção DEVE guardar quem fez, quando, o número
  anterior e o novo; DEVE ser recusada no servidor com lançamento em andamento ou quando o número já
  estiver gravado em outro lote; e o número informado é conferido pela conciliação seguinte como
  qualquer outro (até lá, o lote fica "Aguardando").

**Apresentação e acesso**

- **FR-027**: A aba Lançamento no SCPI de Automações DEVE mostrar, por lote lançado, o veredito, o
  resultado secundário quando houver, a requisição ligada e a origem do vínculo (observações, número ou
  os dois); e, por lote em verificar, as candidatas.
- **FR-028**: Os avisos de saúde do painel DEVEM contar os lotes divergentes, não encontrados,
  duplicados e com vínculo em conflito, e os que estão aguardando conferência há mais de um dia útil.
- **FR-029**: A pessoa DEVE poder pedir uma nova conferência pela aba (uma extração e conciliação fora
  da execução), recusada enquanto houver lançamento ou importação em andamento.
- **FR-030**: Ver os vereditos e pedir a conferência DEVEM ter o mesmo acesso de hoje à aba Lançamento
  no SCPI; a Segurança do Trabalho continua negada.
- **FR-031**: Estado nunca só por cor; números de requisição, códigos e lotes em fonte mono.

### Key Entities

- **Extração do registro oficial**: uma leitura da "Relação de Requisições" de saída num período, com
  quando foi feita, se deu certo, o maior número de requisição encontrado, a impressão digital do
  arquivo e o arquivo bruto (por 60 dias). Pode ser a de antes ou a de depois de uma execução, a diária
  ou uma pedida à mão.
- **Requisição oficial**: uma requisição de saída como a extração a mostrou: número, identificador
  interno, data, tipo, centro de custo, observações e os seus itens (código e quantidade, na ordem do
  relatório). Pertence a uma extração.
- **Tentativa de lançamento**: um lote numa execução real, na ordem em que foi tentado, com o momento,
  o resultado e o número obtido. Liga a execução ao piso e permite calcular o intervalo de uma falha.
- **Conferência de lote**: o resultado de um lote numa extração: o veredito, as diferenças nomeadas, a
  requisição ligada e a origem do vínculo; e, para um lote em verificar, as candidatas. A primeira
  conferência depois do lançamento é a do veredito do lançamento; as seguintes, as de revisão.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Todo lote lançado entre 7h e 17h tem, no mesmo dia, um veredito diferente de
  "Aguardando conferência" quando a extração posterior foi bem-sucedida e o relatório já traz a
  requisição ou um número maior que o do lote. Se a extração falhou (FR-012) ou o relatório ainda não
  traz nenhum dos dois (SC-008), o lote continua "Aguardando conferência", e o aviso de saúde do FR-028
  aponta o que passar de um dia útil.
- **SC-002**: Repassando os dados de 09/10 a 03/11/2026, as sete requisições com Tipo Saída vazio
  (lotes AV-000014, 036, 059, 067, 071, 072 e 073) aparecem como "Divergente: tipo" e as dos lotes
  AV-000083 e 084 como "Divergente: código"; nenhuma delas aparece como comprovada.
- **SC-003**: Nenhum lote em verificar é liberado para relançar sem uma extração posterior à tentativa
  e sem o intervalo de candidatas vazio; nas tentativas reais do P-000018 (execuções 8 e 28) o intervalo
  sai vazio.
- **SC-004**: Nenhuma execução real lança sem a extração de antes bem-sucedida.
- **SC-002a**: Repassando o CSV real de 23/10 a 04/11/2026 (que filtra por `DTPAG`), dos 75 lotes
  lançados com data no período, 72 saem "Comprovado", inclusive o AV-000129 (centro renomeado, com a
  nota), os AV-000101, 130 e 131 (acentos em outra forma) e o AV-000106 (placa vinda do centro); os
  AV-000083 e 084 saem "Divergente: código" e o AV-000081 "Divergente: itens". O AV-000058 (data
  21/10) e os lotes com data de 21 e 22/10 ficam fora do período e não são conferidos por este CSV.
  Conferido no repasse local de 05/11/2026.
- **SC-005**: Os três lotes de conteúdo idêntico (AV-000040, 041 e 042) ficam cada um ligado a uma
  requisição diferente, sem ambiguidade.
- **SC-006**: Para resolver um lote em verificar, a pessoa vê numa tela só se há candidatas e quais,
  sem precisar abrir o SCPI, quando o intervalo está vazio ou a candidata tem o lote nas observações.
- **SC-007**: Nenhum arquivo bruto passa de 60 dias guardado, e todo veredito continua consultável
  depois que o seu arquivo é apagado.
- **SC-008**: Uma requisição recém-salva que o relatório ainda não traz nunca aparece como "Não
  encontrado".

## Assumptions

- Confirmado pelo CSV real sem filtro (23/10 a 04/11/2026, 240 linhas, 84 requisições, 65 colunas,
  UTF-8 com BOM, registros quebrados em várias linhas como no CSV filtrado):
  - o tipo vem na coluna `TPREQUI` ("BALCÃO", "OUTRA" ou vazio);
  - o número visível (`REQUI`) vem no formato do formulário (`003588/26`);
  - o centro de custo vem em código (`CODCCUSTO`, sem zeros à esquerda, o mesmo `codigo` do cadastro)
    e em nome (`CCUSTO`, o nome atual do SCPI);
  - recebedor (`RECEBE`) e placa (`PLACA`, com o `MODELO`) vêm preenchidos;
  - cada requisição tem um cabeçalho só (nenhum campo de cabeçalho varia entre as suas linhas) e
    nenhum código se repete dentro dela;
  - as quantidades vêm inteiras na amostra; quantidade 0 só aparece nos ajustes de inventário;
  - não há hora do registro (`HORAE` vazia, `HORAS` quase sempre vazia), e o responsável
    (`RESPONSA`) é o usuário que o robô usa, o mesmo de lançamentos à mão: não prova autoria;
  - o relatório só traz requisições com saída: 59 números da faixa (de 003599 a 003638 e de 003693 a
    003711) não aparecem e não são de nenhum lote.
- O período do relatório filtra pela coluna `DTPAG`, não pela data da requisição (`DTLAN`): o CSV foi
  extraído de 23/10 a 04/11 (informado pelo usuário), os lotes AV-000064, 066, 070, 072 e 074, com data
  de 21 e 22/10 e lançados em 23/10, ficaram de fora, e a 003728/26, com data de 20/10 e `DTPAG` de
  04/11, entrou. Nas requisições do robô a `DTPAG` é a data digitada (igual à `DTLAN` nos 76 lotes do
  CSV, e é por isso que os cinco lotes ficaram de fora); nas feitas à mão por outras pessoas ela pode
  ser outra (003727/26 e 003728/26).
- Ainda não confirmado pelo CSV: o que são os números que faltam (entradas, provavelmente); como
  aparece uma requisição cancelada; e a latência entre o Salvar e o relatório.
- A coluna `OBS_CABECALHO` é o campo Observações da tela (confirmado pelo usuário); ele é grande o
  bastante para o texto e vem vazio numa requisição nova.
- O SCPI numera as requisições em sequência por ano e uma recusa não consome número (105 pares e 2
  falhas observados); se algum dia não for assim, a regra continua errando para o lado seguro, porque
  um número a mais no intervalo só bloqueia.
- Uma requisição salva aparece no relatório logo depois; a latência real não foi medida.
- A extração roda no mesmo SCPI e sessão separada do navegador, dentro da janela das 7h às 17h.
- O registro da execução já guarda, em ordem, os lançamentos e as falhas; a tentativa de lançamento
  passa a ficar também no banco, não só no journal em arquivo.
- O acesso segue o da aba Lançamento no SCPI de hoje.

## Fora do escopo

- Corrigir a causa do Tipo Saída vazio no robô (tratada numa sessão separada, com a hipótese do
  formulário reaproveitado depois de uma falha nos itens).
- Descontar do saldo exibido as entregas ainda não lançadas.
- Conferir movimentos feitos à mão no SCPI que não pertencem a nenhum lote.
- Corrigir qualquer coisa no SCPI: o sistema só mostra; a correção é à mão.
- Mudar a curva ABC ou o ranking do formulário AB para incluir saídas de outros tipos.
