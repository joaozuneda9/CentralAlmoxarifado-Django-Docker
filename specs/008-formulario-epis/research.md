# Research: Formulário de EPIs

Decisões do plano, com o que existe hoje no repositório como evidência. Cada uma diz o que foi
escolhido, por quê e o que foi descartado. Nenhuma contradiz a spec; as que dependem do usuário estão
marcadas **(a confirmar)** e voltam no relatório final.

## R1 — A autorização é um modelo próprio, uma linha por pedido de EPI

**Decisão**: modelo novo `AutorizacaoPedido` (`OneToOne` com `Pedido`, `related_name="autorizacao"`),
criado na mesma transação do `registrar_pedido`, só para os formulários com `Fluxo.exige_autorizacao`.
Campos: `situacao` (`AGUARDANDO`, `AUTORIZADO`, `RECUSADO`), `decidido_por`, `decidido_em`, `motivo`.
`CheckConstraint`s fazem o banco recusar estado incoerente (R2 do data-model).

**Por quê**:
- FR-032: os pedidos antigos e os outros formulários não podem mudar. Com linha própria, "não exige
  autorização" é simplesmente "não tem linha": nenhum pedido existente é tocado e não há migração de
  dados.
- Campos nulos em todo `Pedido` (a tabela mais usada) deixariam o significado de "nulo" ambíguo (não
  exige ou ainda não decidiu).
- A spec chama a autorização de entidade (Key Entities), com quem, quando e motivo.

**Descartado**: quatro colunas em `Pedido` (mais simples, mas `NULL` ambíguo e `Pedido` já carrega
`ocorrencia` só de um formulário); tabela de eventos com várias decisões por pedido (a decisão é
definitiva, uma linha basta).

## R2 — A situação do pedido ganha dois valores e o filtro "aguardando" muda de sentido só para EPI

**Evidência**: `regras.situacao_pedido(origem, atendido, itens)` devolve `aguardando` (= "Aguardando
atendimento"), `parcial` ou `atendido`; `consultas.filtrar_situacao` repete a regra em SQL com `Exists`
e `tests/test_painel.py` confere que os dois concordam; o atalho "Atender" do painel conta
`filtrar_situacao(..., "aguardando")`.

**Decisão**:
- `situacao_pedido` ganha o parâmetro opcional `autorizacao: str | None = None` (padrão `None` = o
  formulário não exige, comportamento de hoje). `AGUARDANDO` devolve a chave `aguardando_autorizacao`
  ("Aguardando autorização"), `RECUSADO` devolve `recusado` ("Recusado"); `AUTORIZADO` segue a regra de
  hoje (aguardando atendimento, parcial, atendido). `Pedido.situacao` lê a autorização como já lê o
  atendimento (`autorizacao_ou_none`).
- `filtrar_situacao(..., "aguardando")` passa a excluir os pedidos com autorização aguardando ou
  recusada: senão o atalho "Atender" do painel contaria o que não pode ser atendido. Sem linha de
  autorização, o resultado é o de hoje.
- Filtro novo e independente no painel, **Autorização** (Todas, Aguardando autorização, Autorizado,
  Recusado), em SQL sobre `AutorizacaoPedido`. Atende FR-022 sem misturar dois vocabulários no filtro
  "Situação" (um pedido autorizado e já atendido tem situação "Atendido" e autorização "Autorizado").
- `tests/test_painel.py` ganha as combinações com autorização; é o teste que protege a concordância.

**Descartado**: "Autorizado" como valor do filtro Situação (sobrepõe "Atendido" e quebra a concordância
um-para-um com a função pura); trocar a chave `aguardando` (a chave é usada em templates, testes e no
atalho).

## R3 — O portão do atendimento fica no serviço, e a tela só o espelha

**Evidência**: `servicos.confirmar_atendimento` trava o pedido (`select_for_update`) e é a única porta
de gravação do atendimento (Constituição II). Todas as views do painel só têm `@login_required`.

**Decisão**: `confirmar_atendimento` devolve `Resposta(ok=False, mensagem=...)` quando o pedido tem
autorização diferente de `AUTORIZADO`, depois de travar o pedido e antes de qualquer gravação; assim não
nasce `Atendimento` nem `LinhaSaida` e o robô nunca vê o lote (SC-002). A tela espelha: `_contexto_detalhe`
só marca `atendivel` com autorização `AUTORIZADO` (ou sem exigência), o detalhe mostra o motivo da
recusa e quem decidiu, e `_pedido_com_atendimento_aberto` (busca e acréscimo de material no
atendimento) responde 404 para pedido não autorizado.

**Por quê**: a tela sozinha não bloqueia um POST forjado (US3-1); o serviço trava na única porta de
gravação, na mesma transação.

**Descartado**: bloquear só na view (contornável por POST); checar no robô (o lote já existiria).

## R4 — Acesso da Segurança do Trabalho: grupo do Django + um filtro de rotas permitidas

**Evidência**: não há papéis. `login_required` em cada view do painel, de Automações e da Curva ABC;
o admin exige `is_staff`; o menu só distingue `so_equipe`.

**Decisão**:
- O acesso é a **participação no grupo** `Segurança do Trabalho` (criado por migration de dados em
  `contas`, para que o administrador só marque o grupo na tela do usuário no admin). Um helper
  `contas.acesso.da_seguranca_trabalho(usuario)` é a única definição.
- Um **middleware** (`contas.middleware.RestringirSegurancaTrabalho`, depois do
  `AuthenticationMiddleware`) deixa o usuário do grupo abrir só as rotas de uma lista fechada: login,
  logout, a fila, o detalhe de autorização, a decisão e as rotas públicas. Qualquer outra rota resolvida
  recebe redirecionamento à fila (GET e HEAD) ou 403 (demais métodos). **Nega por padrão**: rota nova
  que alguém crie amanhã já nasce fechada para ele. As views existentes não mudam (FR-018).
- Quem decide é checado de novo na própria view e no serviço (`da_seguranca_trabalho`), não só no
  middleware: o administrador sem o grupo é negado (FR-021).
- O menu (`interface.navegacao`) mostra ao usuário do grupo só o item "Autorizações" e aos demais
  continua mostrando o que mostra hoje; o bloco `voltar` do layout deixa de apontar ao painel para ele.
- `is_staff` não dá nem tira o acesso: quem está no grupo é restringido mesmo sendo staff. O guia de
  administração diz para não pôr o grupo em contas de administrador.

**Por quê**: um filtro central com lista fechada é o único jeito de cumprir "só a fila" (FR-017, SC-004)
sem editar e testar cada view; o teste enumera todas as rotas do projeto e confere que só as da lista
passam.

**Descartado**: decorador `@permission_required` em cada view existente (esquecer uma rota abre o
sistema; muda todas as views); permissão do Django em vez de grupo (o superusuário passaria em qualquer
`has_perm`, contrariando FR-021); modelo de papéis próprio (excede o escopo).

## R5 — Os dois avisos do Telegram usam o mesmo envio, com chats diferentes

**Evidência**: `telegram.notificar_pedido` lê `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`, nunca lança, e
`registrar_pedido` o chama em `transaction.on_commit`. `compose.desenvolvimento.yaml` força as variáveis
do Telegram vazias nos ambientes de desenvolvimento, e `deploy/atualizar.ps1` confere que estão vazias
na preparação.

**Decisão**:
- `TELEGRAM_CHAT_ID_SEGURANCA` (variável nova, vazia por padrão, em `.env.example`, `settings`,
  `compose.desenvolvimento.yaml` e na lista de integrações do `atualizar.ps1`, com o teste Pester e
  `deploy/AMBIENTES.md`). Sem ela, o aviso à Segurança do Trabalho não sai e o pedido segue gravado.
- O envio é extraído para uma função interna `_enviar(chat_id, texto, url, rotulo_botao)`; o
  `notificar_pedido` de hoje vira uma chamada dela, sem mudar o que faz.
- Pedido de EPI: ao registrar, o `on_commit` avisa **só** a Segurança do Trabalho (botão "Abrir fila");
  o aviso ao almoxarifado sai do serviço de autorização, no `on_commit` da decisão `AUTORIZADO`. Recusa
  e pedido aguardando não avisam o almoxarifado (FR-027). O reenvio igual sai antes da gravação e não
  avisa (FR-028).

**Descartado**: reaproveitar o `TELEGRAM_CHAT_ID` (misturaria os dois públicos); fila de avisos no banco
(excesso: o aviso é "melhor esforço" e a fila é a fonte da verdade, SC-006).

## R6 — A consulta pública pelo número: POST, resposta neutra e limite por origem

**Evidência**: `publico.formulario` comenta que o sucesso "não tem URL própria, para o número não virar
página pública". O número é sequencial (`P-0001`), então uma consulta aberta é um risco de varredura.

**Decisão**: a consulta é uma página nova, `pedidos:consulta_epi` (`/pedido/epis/consulta/`), que aceita
**POST** (com CSRF) com o número, para o número não ficar na URL nem no histórico. Ela mostra só a
situação (aguardando autorização, autorizado, recusado) e, na recusa, o motivo (FR-031); a resposta é a
mesma para número inexistente e para número de outro formulário (FR-031a); e há limite de consultas por
origem (`PEDIDOS_CONSULTA_LIMITE_IP_10_MIN`, 20 por padrão) contado no cache do Django (`LocMemCache`,
um processo): um modelo e uma migration a mais não se justificam para um limite que pode zerar numa
reinicialização.

**(a confirmar)** Endurecimento proposto, **não adotado** por contrariar a resposta do usuário
("consulta pelo número"): exigir também o nome completo do servidor, comparado como o banco compara
(`norm_u`). Sem o nome, quem adivinhar um número vê a situação e o motivo de uma recusa de outra pessoa
(limitado pelo limite por origem). O custo do endurecimento é uma digitação a mais para o servidor; o
ganho é fechar a varredura. Fica como decisão do usuário no relatório.

**Descartado**: exibir o resultado na tela de sucesso (o pedido ainda está aguardando); consulta por GET
com o número na URL.

## R7 — O catálogo dos EPIs segue o desenho da oficina, sem tocar nela

**Evidência**: `catalogos.catalogo_oficina` junta os materiais visíveis dos grupos de `Opcao`
`GRUPO_OFICINA` e os avulsos de `MaterialOficina` (`OneToOne`, `PROTECT`); a saúde e a visão geral de
Automações têm uma linha cada (spec 007).

**Decisão**: `Opcao.Lista.GRUPO_EPI` ("Grupos (EPIs)") e o modelo `MaterialEpi` (`OneToOne` com
`Material`, `PROTECT`, `related_name="material_epi"`), `catalogos.catalogo_epis` / `formulario_epis`
(`None` sem saldo importado ou sem item), `saude._epis` e `Situacao.epis`. O código novo reusa `_grupo`,
`_item`, `unidades_fracionaveis` e `saldo_importado`; as funções da oficina **não** são alteradas
(FR-032): a duplicação é de poucas linhas e é o preço de não mexer em formulário em produção.

**Por quê**: a spec pede grupos inteiros mais avulsos mantidos no admin (resposta do usuário), igual à
oficina. Um modelo genérico "material de formulário" exigiria migrar a oficina.

**Descartado**: reusar `MaterialOficina` com um campo `formulario` (muda tabela e dados da oficina);
generalizar `catalogo_oficina` (altera código que está em produção sem necessidade).

## R8 — O que não muda e o que o formulário herda

- **Destino**: sem `Fluxo.centros`, vale o padrão (todos os centros cadastrados), como limpeza e AB.
- **Quantidade**: regra `por_unidade` padrão dos formulários públicos.
- **Recibo, atendimento, edição e lançamento no SCPI**: nenhuma mudança. O recibo não mostra a
  autorização (item (g) da spec, padrão adotado).
- **Tela de sucesso**: `_sucesso.html` ganha um bloco guiado por `fluxo.exige_autorizacao` (texto do
  aguardando e link da consulta); os outros formulários não mudam.
- **Telegram ao almoxarifado**: o texto atual é reaproveitado; o aviso à Segurança do Trabalho tem
  cabeçalho próprio.
- **Estoque**: nenhuma reserva nem conferência na autorização (FR do Contexto); a conferência de estoque
  continua sendo a do envio e a do atendimento.

## R9 — Concorrência e idempotência da decisão

**Decisão**: o serviço `decidir_autorizacao` abre transação, trava a `AutorizacaoPedido` do pedido
(`select_for_update`) e só grava se a situação ainda é `AGUARDANDO`; caso contrário devolve a decisão já
gravada (quem e quando) sem alterar nada (FR-015, US2-6). Um segundo envio idêntico (duplo clique) cai no
mesmo caminho e mostra a decisão gravada. A recusa sem motivo é recusada antes de gravar. A constraint do
banco é a última linha de defesa.

## R10 — Pontos do repositório afetados e riscos de regressão

| Ponto | Mudança | Risco | Cobertura |
|-------|---------|-------|-----------|
| `regras.situacao_pedido` | parâmetro opcional | pedidos sem autorização mudariam | testes de situação existentes, sem alteração |
| `consultas.filtrar_situacao("aguardando")` | exclui aguardando/recusado de autorização | atalho "Atender" contar errado | `test_painel.py` + caso novo |
| `servicos.registrar_pedido` | cria a autorização e escolhe qual aviso sai | outros formulários avisarem diferente | testes de registro e de Telegram existentes |
| `servicos.confirmar_atendimento` | recusa pedido não autorizado | pedido sem autorização ser recusado | testes de atendimento existentes |
| `telegram` | extrai `_enviar` | aviso atual mudar | `test_telegram` existente |
| middleware novo | restringe o grupo | travar usuário errado | teste das rotas × usuário |
| `compose.desenvolvimento.yaml`, `atualizar.ps1` | variável nova | teste Pester | `deploy/tests/` |
