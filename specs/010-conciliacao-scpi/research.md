# Pesquisa: conciliação dos lançamentos do robô com o SCPI

Decisões técnicas do [plano](plan.md). As decisões de produto estão nos esclarecimentos da
[spec](spec.md); aqui ficam só as escolhas de como fazer. Cada item traz a decisão, o motivo e as
alternativas descartadas.

## R1. Onde ficam os modelos novos

**Decisão**: num app novo, `conciliacao`, com modelos, regras puras (`conciliacao/regras.py`),
serviços (`conciliacao/servicos.py`), consultas da tela (`conciliacao/consultas.py`) e o comando
`conciliar_lancamentos`. Cada extração também ganha uma `Importacao` do tipo novo `REQUISICOES`
("Requisições do SCPI"), ligada por `OneToOne` à `ExtracaoOficial`.

**Motivo**:
- O Princípio II diz que, fora de `servicos.py`, só o robô grava em `pedidos`, e só em quatro campos
  da `LinhaSaida`. Pôr as tentativas e as conferências em `pedidos` abriria uma terceira porta de
  gravação.
- Um app próprio deixa claro que a conciliação só lê `pedidos`, com uma exceção: a correção do número
  (R16), que passa por `pedidos/servicos.py`.
- Reaproveitar a `Importacao` traz quatro coisas prontas: a trava por tipo (`trava_importacao`), o
  "em andamento" e o "interrompida", o histórico de Automações e o registro de falha
  (`scpi.execucao.executar`).

**Alternativas**:
- Pôr tudo em `scpi`, que hoje não tem modelos: misturaria navegação com estado.
- Pôr tudo em `catalogo`, junto da `SaidaSCPI`: o catálogo é cadastro, e a `SaidaSCPI` não pode mudar
  de comportamento (FR-006).

## R2. Onde fica o arquivo bruto

**Decisão**: no banco, comprimido com gzip num `BinaryField` da `ExtracaoOficial` (`arquivo`), com o
SHA-256 dos bytes recebidos (`impressao`). Se a impressão for igual à da extração anterior do mesmo
período, o campo fica vazio e `mesmo_arquivo_que` aponta para a extração que guarda o arquivo
(FR-003). A limpeza de 60 dias esvazia o campo e marca `arquivo_apagado_em` (FR-004), mas só
quando a extração e todas as que apontam para ela passaram dos 60 dias. Assim, uma extração repetida
recente nunca fica sem o bruto. A deduplicação só aponta para uma extração que ainda guarda os bytes;
se o bruto com a mesma impressão já foi apagado, a nova extração guarda o seu.

**Motivo**:
- Cerca de 20 KB por extração e 4 a 5 extrações por dia dão uns 6 MB em 60 dias.
- Guardando no banco, não é preciso pasta nem volume novo no Compose (que hoje força `/dados/logs`,
  `/dados/backups` e `/dados/perfil`), e o arquivo entra no backup diário.

**Alternativa**: guardar em `dados/conciliacao/` com o nome igual à impressão. Exigiria uma variável
nova, uma pasta nova nos três `compose*.yaml` e um cuidado à parte com o backup.

## R3. Como baixar o relatório sem filtro

**Decisão**:
- `scpi.relatorios.baixar_requisicoes(de, ate)` repete a navegação de `baixar_saidas` (Relatórios ›
  Requisições › Relação de Requisições, rádio "Requisições de Saída", datas De/Até) sem escolher o
  tipo no combo.
- `baixar_saidas` não muda.
- Dentro do `atualizar_catalogo`, as duas usam a mesma sessão compartilhada (`sessao_compartilhada`).

**Motivo**: o CSV real que o usuário extraiu (23/10 a 04/11) sai assim e traz `TPREQUI` "BALCÃO",
"OUTRA" e vazio.

**Alternativa descartada por ora**: derivar as saídas BALCÃO do relatório sem filtro, trocando dois
downloads por um. Seria mais barato, mas FR-006 pede que as saídas da curva não mudem. Fica como
melhoria futura, com teste de equivalência.

**Verificação manual**: o comando `extrair_requisicoes` (contrato em [contracts/comandos.md](contracts/comandos.md))
roda essa navegação no SCPI real. É só leitura, mas é feito pelo usuário (CLAUDE.md, importadores do
SCPI).

## R4. Leitura do CSV

**Decisão**: `scpi.leitura.ler_requisicoes(conteudo) -> Leitura` é pura e usa o mesmo caminho de
`ler_saidas`:
- recola os registros quebrados (`normalizadores.py`) e acha as colunas pelo nome (`_campos`);
- aceita o CSV salvo por planilha;
- tem colunas obrigatórias, conforme [contracts/relatorio-requisicoes.md](contracts/relatorio-requisicoes.md);
- agrupa por `REQUI` e recusa uma requisição cujo cabeçalho varie entre as linhas (no CSV real, nunca
  varia);
- lê quantidades com `decimal_br` e datas com `data_br`.

Um CSV vazio, ou sem uma coluna obrigatória, é `ErroImportacao`. Isso vira extração com falha (FR-005,
Princípio IV).

**Motivo**: os dois relatórios têm o mesmo formato (BOM, `;`, CRLF misturado com LF, registros
quebrados), e o leitor existente já foi testado contra eles.

## R5. Lote nas observações

**Decisão**: o robô escreve `Central Almoxarifado <lote>` no campo Observações, logo depois do
Recebimento (`lancador.preencher_cabecalho`). A leitura usa
`re.search(r"central\s+almoxarifado\s+((?:P|AV)-\d{6})", obs, re.I)` sobre o `OBS_CABECALHO` e
guarda o lote achado em `RequisicaoOficial.lote_observado`.

**Motivo**:
- O texto é fixo, curto e fácil de achar sem ambiguidade.
- Os ajustes de inventário têm observações longas que nunca casam com esse padrão.

**Verificação**: o `--dry-run` preenche as Observações e descarta. A navegação até o campo, portanto,
se confere sem salvar.

## R6. Ordem e intervalo dos números

**Decisão**: `regras.chave("003588/26") -> (2026, 3588)` (o ano vem do sufixo). Todo intervalo e todo
"maior número" é comparado por essa chave. O piso de uma execução é a maior chave da extração de antes.

**Motivo**: o número traz o ano. Na virada, `000001/27` vem depois de `004512/26`, e a comparação
precisa respeitar isso (spec, casos de borda).

## R7. Tentativas da extração de antes

**Decisão**: 3 tentativas com 30 s entre elas (`TENTATIVAS_EXTRACAO`, `PAUSA_EXTRACAO_S`; os testes
injetam a pausa). Se as três falharem, a execução termina `FALHA` com a frase "não foi possível
extrair as requisições do SCPI antes de lançar", antes de abrir o navegador do lançamento e sem tocar
em nenhum lote (FR-009).

**Motivo**: as falhas medidas dentro da janela das 7h às 17h vêm em surtos de minutos (27/10 e
28/10). Três tentativas cobrem o soluço sem segurar o lançamento por muito tempo.

## R8. Navegadores da extração e do lançamento

**Decisão**: as sessões são sequenciais, nunca simultâneas:
1. extração de antes (sessão de relatórios, aberta e fechada);
2. `lancar` (navegador do lançamento, perfil `lancamento`);
3. extração de depois (outra sessão de relatórios).

`executar_lancamento` recebe um `extrair: Callable[[date, date], bytes]` ao lado do `abrir_scpi`. Em
produção ele é `relatorios.baixar_requisicoes`; nos testes, o `SCPISimulado.relatorio`.

**Motivo**:
- Não se sabe se o SCPI aceita duas sessões do mesmo usuário ao mesmo tempo; em sequência, a dúvida
  não importa.
- A extração continua em "outra tela e outra sessão" (spec, Contexto).

## R9. Período de cada extração

**Decisão**: `regras.periodo(datas, hoje) = (min(datas) − 1 dia, hoje + 1 dia)`.
- Na execução, `datas` são as datas dos lotes escolhidos mais as dos lotes em verificar abertos.
- Na extração diária e na conferência pedida pela tela, são hoje − 9 dias mais as datas dos lotes em
  verificar abertos.

O relatório filtra por `DTPAG`, que nas requisições do robô é a data digitada (Assumptions da spec).
Então o período cobre tudo o que o robô pode ter salvo.

## R10. O que se compara e como

**Decisão**: a entrega esperada vem da **foto da tentativa** (R11), com uma exceção: o lote lançado
antes desta funcionalidade, cuja foto é recalculada das `LinhaSaida` com `requisicoes.validar` e
`servicos.centros()`.

Campos comparados (FR-016, FR-019, FR-019a e FR-019b):

| Campo | Entrega | Oficial | Regra |
|---|---|---|---|
| tipo | `tipo_saida` | `TPREQUI` | texto normalizado |
| data | `data` | `DTLAN` | igual |
| centro | `cod_ccusto` | `CODCCUSTO` | código, sem zeros à esquerda; o nome diferente vira nota |
| recebedor | `recebedor` | `RECEBE` | texto normalizado |
| placa | placa do item ou do centro | `PLACA` | `norm_placa`; se o lote não tem placa, vale a do centro |
| itens | lista de código e quantidade | lista de `CADPRO` e `QUAN2` | mesmo número de linhas, código por `norm_u` (Princípio I; o mesmo material para o banco), sem de/para, quantidade `Decimal` exata |

"Texto normalizado" é NFC, `casefold` e sem espaços nas pontas.

Cada diferença vira `{"campo", "esperado", "oficial"}`, e cada nota, `{"campo", "texto"}`. O de/para
aparece só como explicação de uma diferença de código (FR-020), nunca para aceitá-la.

## R11. Foto da tentativa

**Decisão**: a `TentativaLancamento` guarda em JSON o cabeçalho e os itens que o robô vai digitar
(`Requisicao.data`, `tipo_saida`, `cod_ccusto`, `recebedor` e cada `Item(cadpro, qtd, placa)`), mais a
placa do centro. A foto é gravada antes do Salvar, na mesma transação que confirma o `EM_LANCAMENTO`.

**Motivo**:
- É a "entrega confirmada como o robô as leu" (spec).
- Não depende do cadastro de centros mudar depois (o AV-000129 mostra um centro renomeado no SCPI).
- Guarda o código que o robô digitou de fato.

## R12. Vínculo e veredito

**Decisão**: `regras.veredito(foto, numero, requisicoes, maior_chave, cobre_data)` é pura. A ordem é:
1. Junta as requisições com o lote nas observações e a requisição com o número gravado.
2. Duas ou mais com o lote nas observações, ou o mesmo número gravado em dois lotes, dão **Duplicado**.
   O segundo caso vem de uma consulta no banco e entra como parâmetro.
3. Observações e número apontando para requisições diferentes dão **Vínculo em conflito**.
4. Sem nenhuma das duas: **Não encontrado** se `maior_chave > chave(numero)` e a extração cobre a data;
   senão, **Aguardando**.
5. Com uma requisição: **Comprovado** se não há diferença, ou **Divergente** com as diferenças.

A origem do vínculo fica gravada: `observacoes`, `numero` ou `ambos`.

## R13. Revisão nas extrações seguintes

**Decisão**:
- Enquanto o lote não tem conferência conclusiva, cada extração bem-sucedida grava uma de
  `tipo=LANCAMENTO`; as `AGUARDANDO` são provisórias. A primeira `LANCAMENTO` conclusiva é a do
  veredito do lançamento.
- Cada extração seguinte a ela que cobre a data grava uma de `tipo=REVISAO`. Se a requisição ligada diferir
  da conferida no lançamento, a revisão marca `alterado_depois` e lista as diferenças entre as duas
  fotos oficiais.
- O veredito do lançamento não muda (FR-017), com uma exceção: o Divergente que uma revisão mostra
  igual à entrega passa a Comprovado (FR-018), guardando a conferência anterior.

O "veredito atual" de um lote é o da última conferência que não está aguardando. A consulta da tela
lê só esse.

## R14. Intervalo de candidatas de um lote em verificar

**Decisão**: `regras.intervalo(tentativas, piso, indice)`.
- **Limite inferior**: a maior chave entre o piso da execução e os números obtidos pelas tentativas
  anteriores da mesma execução.
- **Limite superior**: o primeiro número obtido por uma tentativa posterior da mesma execução. Sem
  nenhuma, fica aberto, e vale tudo acima do limite inferior que a extração de depois traz.

Candidata é toda `RequisicaoOficial` da extração com a chave **estritamente entre** os dois limites
(o FR-022: acima do inferior e abaixo do superior), seja qual for o tipo, com uma exclusão: a que tem outro lote nas
observações não conta. A que tem este lote nas observações vem marcada "é esta". As demais vêm
ordenadas pela semelhança da foto: itens iguais, depois tipo, depois centro (FR-023).

O limite superior fica de fora de propósito: é o número que o lote seguinte obteve, e não pode ser do
lote em verificar. Se entrasse, sempre haveria uma candidata (a requisição do lote seguinte, quando
as observações dela se perdessem), e nenhum lote em verificar seria liberado.

**Execuções 8 e 28 (SC-003)**: os limites ficam entre 003495 e 003496 e entre 003532 e 003533, sem
nenhum número no meio. O intervalo sai vazio.

## R15. Lote em verificar de antes da funcionalidade

**Decisão**: o comando de uma vez `importar_tentativas --journal <arquivo>` lê o
`lancar_saidas_journal.jsonl` e cria as `TentativaLancamento` históricas. Ele é idempotente, pela
execução e pelo lote.
- Eventos `em_lancamento` dão a ordem.
- `lancada` dá o número; `incerto` dá verificar.
- O piso dessas execuções é o maior número de lote lançado antes do início da execução.
- Essas tentativas históricas não têm foto (a conferência recalcula, R10).

Um lote em verificar sem tentativa registrada (o journal se perdeu) não pode ser liberado: a recusa
manda informar o número ou marcar "não lançar" (lado seguro, FR-024).

**Motivo**: o journal é o único registro da ordem das tentativas antigas. Ler o journal numa migration
dependeria de um arquivo fora do banco.

## R16. Correção de um lote lançado (FR-026)

**Decisão**: `pedidos.servicos.corrigir_requisicao(lote, requisicao, *, usuario, agora)` vale para
linhas `LANCADA` cujo veredito atual é Não encontrado ou Vínculo em conflito. Ela:
- trava as linhas (`select_for_update`) sob a `TRAVA_LANCAMENTO`, como `resolver_lote`;
- recusa o número fora do formato, o número já gravado em outro lote e o pedido feito com lançamento em
  andamento;
- troca o `requisicao_scpi`, acrescenta o histórico na `mensagem` e mantém o status e o `lancado_em`;
- grava uma `CorrecaoVinculo` (anterior, novo, quem, quando, veredito de origem), cuja gravação fica em
  `conciliacao.servicos` e é chamada por `pedidos/servicos.py` na mesma transação.

O lote volta a Aguardando até a próxima extração.

**Motivo**: o Princípio II manda gravar pedidos só em `servicos.py`. A correção é uma ação de pessoa,
não do robô.

## R17. Liberação de um lote em verificar (FR-024)

**Decisão**: em `pedidos.servicos._resolver_com_a_trava`, a ação `liberar` com alguma linha
`VERIFICAR` ou `EM_LANCAMENTO` consulta `conciliacao.consultas.liberacao(lote, agora)`, que exige duas
condições:
1. existe ao menos uma conferência do lote feita por uma extração **bem-sucedida, iniciada depois da
   tentativa e cobrindo a data do lote**;
2. **nenhuma** dessas conferências teve candidata (FR-024: "ao menos uma candidata").

Uma candidata vista uma vez continua bloqueando, mesmo que uma extração mais nova não a traga: a
requisição pode ter sumido do relatório por falha dele, e liberar nesse caso arriscaria lançar duas
vezes (Princípio III). Se a pessoa confirmou no SCPI que a candidata não é deste lote (por exemplo,
porque foi excluída), o lote se resolve marcando "não lançar" e lançando à mão, ou informando o número.

A caixa "Conferi no SCPI" continua obrigatória. Confirmar a candidata "é esta" usa a ação `lancada` de
sempre, com o número dela (FR-025).

## R18. Trava da conferência pedida pela tela (FR-029)

**Decisão**: a conferência fora da execução roda em processo separado (`scpi.disparo.iniciar_conciliacao`,
log `conciliar_lancamentos.log`), sob a trava de importação do tipo `REQUISICOES`. Ela é recusada com
lançamento em andamento (`ExecucaoRobo.em_andamento`) ou com qualquer importação em andamento.

Dentro do lançamento, a extração pega a mesma trava. Se uma extração diária estiver rodando, a de antes
tenta de novo (R7).

## R19. Extração diária e horário

**Decisão**:
- O `atualizar_catalogo` ganha um quarto passo, "Requisições", depois das Saídas, na mesma sessão. Ele
  extrai o período de R9, concilia e roda a limpeza de 60 dias.
- O horário no `deploy/crontab` passa de 06:30 para 07:15.
- Uma falha nesse passo não desfaz os três primeiros: cada um já é uma `Importacao`.

**Motivo**: o SCPI só é estável das 7h às 17h. As três falhas medidas das saídas foram todas às 6h30.

## R20. Testes e fixtures

**Decisão**:
- O `SCPISimulado` guarda o que cada `salvar` registrou: número, cabeçalho, itens, observações e tipo.
- `SCPISimulado.relatorio(de, ate)` gera o CSV no formato real, com BOM, `;`, CRLF, as 65 colunas do
  cabeçalho real e um registro quebrado em duas linhas.
- O simulado ganha falhas novas:
  - `salvar` que registra e depois levanta (`ResultadoIncerto`);
  - `salvar` que levanta sem registrar;
  - tipo ou observações perdidos;
  - requisição editada ou excluída entre extrações;
  - requisição feita "à mão" no meio da execução;
  - relatório que falha N vezes.
- Os casos do SC-002a são reproduzidos com dados **sintéticos**, sem os nomes reais do CSV do usuário:
  - centro renomeado;
  - acentos decompostos;
  - placa vinda do centro;
  - itens trocados;
  - data diferente.
- O CSV real nunca entra no repositório. Ele tem nomes de pessoas e serve só para a validação manual
  do [quickstart](quickstart.md).

## R21. Saúde e tela

**Decisão**:
- `catalogo.saude` (ou um `conciliacao.saude` chamado de lá) ganha os avisos do FR-028.
- A aba Lançamento no SCPI ganha:
  - por lote lançado, o selo do veredito em texto e a requisição ligada, em mono;
  - no lote em verificar, as candidatas dentro do painel de resolução que já existe;
  - na correção (FR-026), um formulário no mesmo `<details>` dos lotes travados;
  - o botão "Conferir agora".
- A interface segue o `docs/DESIGN.md` e as três skills de UI do CLAUDE.md. O estado nunca é mostrado
  só por cor (FR-031).

## R22. Pendências que não bloqueiam o plano

Três pontos seguem em aberto nas Assumptions da spec. Nenhum muda uma regra:
- **Os números que faltam no relatório**: são provavelmente entradas. O robô só cria saídas, que sempre
  aparecem.
- **As canceladas**: até o formato ser conhecido, uma requisição que some de uma extração para a outra
  vira "alterado no SCPI depois do lançamento" (excluída).
- **A latência**: a regra do "Não encontrado" só vale com número maior já no relatório (SC-008).
