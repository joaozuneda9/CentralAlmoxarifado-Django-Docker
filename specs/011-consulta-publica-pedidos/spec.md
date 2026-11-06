# Consulta pública da situação do pedido

**Branch**: `claude/consulta-publica-pedidos` · **Criada**: 2026-11-06 · **Situação**: implementada,
pendente de validação com solicitantes

**Pedido do usuário**: permitir que o solicitante, sem login, volte depois do envio e entenda a
situação atual do seu pedido, em qualquer um dos formulários públicos; escopo concentrado nessa
consulta.

## 1. Fatos comprovados (código e testes de 2026-11-06)

| # | Fato | Onde |
|---|------|------|
| F1 | Já existe uma consulta pública só para EPIs, `pedidos:consulta_epi` (`/pedido/epis/consulta/`): POST com CSRF, `never_cache`, só lê, limite por origem no cache do Django (`PEDIDOS_CONSULTA_LIMITE_IP_10_MIN` = 20 em 10 min). | `pedidos/views/publico.py` (`consulta_epi`, `_consultas_demais`) |
| F2 | Ela responde só sobre a **autorização** (`AutorizacaoPedido`), nunca sobre o atendimento: um EPI autorizado e já atendido continua "autorizado. O almoxarifado vai atendê-lo; procure o almoxarifado para retirar". | `regras.texto_situacao_consulta` |
| F3 | Essa frase promete atendimento e retirada que o sistema não registra (não há agendamento, aviso nem local de retirada no modelo). | `pedidos/models.py` (sem campo de retirada) |
| F4 | A situação do pedido tem uma fonte única: `regras.situacao_pedido(origem, atendido, itens, autorizacao)`, exposta em `Pedido.situacao`. Chaves: `aguardando_autorizacao`, `recusado`, `aguardando`, `parcial`, `atendido`. O painel, o detalhe e o filtro SQL (`consultas.filtrar_situacao`, conferido por teste) usam a mesma regra. | `pedidos/regras.py`, `pedidos/models.py` |
| F5 | "Atendido" é a confirmação do atendimento pelo almoxarifado: grava um `Atendimento` (data efetiva, recebedor, centro, tipo) e as `LinhaSaida`. O botão é "Confirmar e registrar saída"; exige ao menos um material com quantidade maior que zero. | `servicos.confirmar_atendimento`, `regras.validar_saida`, `detalhe.html` |
| F6 | "Parcial" é atendimento com algum material pedido entregue em quantidade menor que a pedida; o material trocado pelo almoxarifado por outro entregue não conta como faltante. Não existe segunda entrega: o pedido atendido não volta a "aguardando". | `regras.situacao_pedido` |
| F7 | Até o robô lançar o lote, o atendimento pode ser editado (`servicos.editar_atendimento`): quantidades e data efetiva mudam, o pedido continua atendido. Não há cancelamento nem exclusão de pedido pelos serviços. | `pedidos/servicos.py` |
| F8 | EPI: só a Segurança do Trabalho decide, uma vez e para sempre; `confirmar_atendimento` recusa o pedido não autorizado. Recusado nunca será atendido. | `servicos.decidir_autorizacao`, `confirmar_atendimento` |
| F9 | O número é sequencial e compartilhado: `P-000123` para os formulários públicos, `AV-000124` para a saída avulsa (interna). É fácil de adivinhar. | `servicos.proximo_numero`, `Sequencia` |
| F10 | A tela de sucesso não tem URL própria "para o número não virar página pública"; mostra o número em destaque e, nos EPIs, um link para a consulta. Nos demais formulários não há caminho para acompanhar o pedido. | `publico.formulario`, `_sucesso.html` |
| F11 | A página inicial não leva a nenhuma consulta. | `inicio.html` |
| F12 | Decisão anterior do usuário (spec 008, R6): consulta **pelo número**; exigir também o nome completo foi proposto e **não adotado**. | `specs/008-formulario-epis/research.md` |
| F13 | O usuário da Segurança do Trabalho só abre as rotas de `ROTAS_SEGURANCA_TRABALHO`; rota pública nova precisa entrar nela. | `contas/acesso.py`, `tests/test_epis_acesso.py` |

## 2. Hipóteses (não comprovadas pelo sistema)

- H1. O solicitante anota ou fotografa o número da tela de sucesso (o sistema não envia o número por
  nenhum canal).
- H2. "Registrou a saída" é entendido pelo solicitante como "o material saiu do almoxarifado para o
  recebedor". O sistema registra a saída e o recebedor, mas não comprova quem recebeu nem onde.
- H3. Os servidores de um mesmo prédio saem pela mesma rede: o limite de 20 consultas em 10 minutos é
  dividido entre eles.

## 3. Estados e mensagens

A situação vem de `Pedido.situacao` (F4); a consulta só a traduz para o solicitante
(`regras.texto_consulta_publica`). Autorização e atendimento ficam separados: a autorização só aparece
enquanto o atendimento não existe.

| Estado (chave) | Condição no banco | Selo | Mensagem |
|---|---|---|---|
| `aguardando_autorizacao` | EPI, `AutorizacaoPedido` `AGUARDANDO` | Aguardando autorização | A Segurança do Trabalho ainda não decidiu este pedido. O almoxarifado só pode atendê-lo depois da autorização. |
| `recusado` | EPI, `RECUSADO` | Recusado | A Segurança do Trabalho recusou este pedido. Ele está encerrado e não será atendido. + **Motivo:** texto |
| `aguardando` (autorizado) | EPI, `AUTORIZADO`, sem `Atendimento` | Autorizado | A Segurança do Trabalho autorizou este pedido em dd/mm/aaaa. O almoxarifado ainda não registrou o atendimento. |
| `aguardando` | sem autorização exigida, sem `Atendimento` | Aguardando atendimento | O almoxarifado ainda não registrou o atendimento deste pedido. |
| `atendido` | com `Atendimento`, nenhum material pedido abaixo do pedido (trocas contam como entregues) | Atendido | O almoxarifado registrou a saída dos materiais deste pedido em dd/mm/aaaa (data efetiva). |
| `parcial` | com `Atendimento`, algum material pedido entregue a menos | Atendido parcialmente | O almoxarifado registrou a saída dos materiais deste pedido em dd/mm/aaaa, com algum material em quantidade menor que a pedida. O que faltou não fica pendente neste pedido. |

Nenhuma mensagem promete retirada, entrega ou prazo (F3). "Atendido" de um EPI segue as linhas de
atendimento (a autorização já está implícita).

Respostas que não são de um pedido:

| Caso | Condição | Mensagem | HTTP |
|---|---|---|---|
| Em branco | só espaços | Informe o número do pedido. | 200 |
| Número inválido | não casa `P-?<1 a 9 dígitos>` depois de limpar espaços e maiúsculas (ex.: `AV-000002`, `003588/26`, ocorrência) | Este não é um número de pedido. O número começa com P, como P-000123, e aparece na tela de confirmação do envio. | 200 |
| Sem nome | número válido, nome só com espaços | Informe o seu primeiro nome, como foi escrito no pedido. | 200 |
| Não encontrado | número válido sem pedido de formulário público (inexistente ou de saída avulsa), **ou** primeiro nome que não confere | Não encontramos um pedido com este número e este nome. Confira os dois na tela de confirmação do envio. | 200 |
| Excesso de tentativas | mais de `PEDIDOS_CONSULTA_LIMITE_IP_10_MIN` consultas da mesma origem na janela de 10 min (toda consulta conta, inclusive a inválida) | Muitas consultas desta rede em pouco tempo. Tente de novo daqui a 10 minutos ou procure o almoxarifado. | 429 |

A validação do formato depende só do texto digitado, nunca do banco: não revela se um número existe.
Inexistente, saída avulsa e nome que não confere têm a mesma resposta: a tela nunca diz que o número
existe.

## 4. Contrato de acesso público

**Dados que o solicitante precisa** para entender a situação: a situação (tabela acima), a data que a
explica (decisão da autorização ou saída) e, na recusa, o motivo. Para conferir que digitou o número
certo (troca de identificadores): o número normalizado, o formulário e a data do envio.

**Com o número e o primeiro nome** (adotado, decisão do usuário em 2026-11-06, que substitui a F12):
número normalizado, título do formulário, data do envio (dia), selo, mensagem, data da decisão (EPI
autorizado) ou da saída (atendido), motivo da recusa (EPI) e, também a pedido do usuário em
2026-11-06, a **lista de materiais com as quantidades pedidas**: só os itens que o solicitante pediu
(`ItemPedido.Origem.PEDIDO`), com o nome, a quantidade pedida e a unidade gravados no pedido, como na
tela de sucesso. Nem o material acrescentado ou trocado pelo almoxarifado, nem a quantidade entregue.

**Regra do nome** (`regras.nome_confere`): a primeira palavra do que foi digitado é igual à primeira
palavra do `Pedido.solicitante`, sem diferença de acento, maiúsculas ou espaços (`norm_u`). "Marcos",
"márcos" e "Marcos Pereira" abrem o pedido de "Marcos Pereira"; "Pereira", "Marc" e "MarcosPereira"
não. Pedido sem nome nunca é consultado.

**Nunca na consulta pública**: nome do solicitante (o gravado; só o digitado volta no campo), destino,
observação, nº da ocorrência, códigos, quantidades entregues, materiais acrescentados pelo almoxarifado,
recebedor, quem atendeu ou decidiu, centro de custo, placa, situação no SCPI e número da requisição.

| Opção | Protege contra varredura | Custo para o solicitante | Custo no sistema |
|---|---|---|---|
| A. Só o número | Não; limita a 20 consultas/10 min por origem | Um dado, que ele já anota | Nenhum dado novo |
| A'. Número + primeiro nome (adotada) | Parcial: o número sozinho não abre nada, mas o primeiro nome é adivinhável (nomes comuns); somado ao limite por origem | O número e o próprio primeiro nome, que ele não precisa anotar | Comparação por `norm_u`, sem dado novo nem migration |
| B. Número + código de consulta (ex.: 6 caracteres derivados por HMAC do id do envio) | Sim | Dois dados para anotar; perder o código perde a consulta em outro aparelho | Troca da `SECRET_KEY` invalida os códigos, ou campo novo com migration |
| C. Número + nome completo | Um pouco mais que A' | Digitar o nome inteiro igual ao do envio (abreviações e sobrenomes esquecidos viram "não encontrado") | Comparação por `norm_u` |

**Recomendação inicial**: A, pela decisão anterior (F12). **Adotada**: A', a pedido do usuário. Quem
varre números precisa acertar também o primeiro nome de cada pedido, o que torna a varredura cega
inútil e protege sobretudo o motivo da recusa de EPI; um primeiro nome comum ("José", "Maria") ainda
pode acertar. Com a lista de materiais, quem acerta número e primeiro nome vê o que outra pessoa
pediu (no EPI, o equipamento e a quantidade); a opção B seria a proteção mais forte se isso pesar.

Proteções mantidas: POST com CSRF (número e nome não vão para a URL nem para o histórico),
`never_cache`, resposta idêntica para inexistente, avulsa e nome que não confere (o nome gravado nunca
volta na resposta; só o que foi digitado fica no campo), só leitura, toda tentativa conta no limite, limite por origem no cache do processo (zera
ao reiniciar, como na consulta de EPIs).

**Rotas**: `pedidos:consulta` (`/pedido/consulta/`) para todos os formulários públicos. A antiga
`pedidos:consulta_epi` (`/pedido/epis/consulta/`) continua servindo a mesma página (links e favoritos
já distribuídos, e formulário aberto antes da atualização). As duas estão em
`ROTAS_SEGURANCA_TRABALHO`. Isto substitui o FR-031 da spec 008 na parte "NÃO DEVE responder sobre
pedidos de outros formulários".

## 5. Jornada mínima

1. **Confirmação do envio** (`_sucesso.html`, todos os formulários): o número em destaque, a frase
   "Guarde o número. Para acompanhar o pedido, de qualquer aparelho, use Consultar pedido na página
   inicial com este número e o seu primeiro nome, como foi escrito no pedido." (o nome aparece na mesma
   tela: "N materiais registrados para <nome>") e o botão **Ver a situação agora** (formulário POST com
   o número e o nome escondidos: abre o resultado sem pôr nada na URL). No EPI a frase de aguardar a autorização continua.
2. **Depois, no mesmo ou em outro aparelho**: página inicial → **Consultar um pedido** (no topo, antes
   dos formulários, a pedido do usuário) →
   digita o número (aceita `p123`, `P-123`, espaços) e o primeiro nome (o navegador pode sugeri-lo,
   `autocomplete="given-name"`) → resultado.
3. **Erros**: em branco, inválido, sem nome, não encontrado e excesso de tentativas, cada um com a sua
   mensagem (seção 3); o número e o nome digitados ficam nos campos para corrigir.
4. **Rolagem**: o envio vai para `/pedido/consulta/#resultado`, também pelo botão da tela de sucesso, e o
   navegador rola sozinho, sem JavaScript, até o cartão do pedido; no erro, o alvo é o formulário, que
   cabe na tela com o aviso logo abaixo (com os dois campos, no celular o aviso ficava abaixo da dobra).

## 6. Verificação

- Matriz de resultados esperados (`tests/test_consulta_publica.py`): cada estado montado pelos serviços
  reais (registrar, decidir, atender, editar) com o selo e a mensagem escritos literalmente no teste.
- Acompanhamento: o mesmo pedido consultado antes e depois de atender e de editar o atendimento.
- Exposição: nenhum dado da lista "nunca" aparece na resposta, em nenhum estado.
- Erros, limite, CSRF, cache, métodos, rotas antigas e acesso da Segurança do Trabalho.
- Navegador (Playwright, fora da suíte): envio real → botão da tela de sucesso → consulta em outro
  contexto de navegador (outro aparelho) → atendimento → consulta de novo.

`tests/test_consulta_publica.py` substitui `tests/test_epis_consulta.py`: os casos dos EPIs seguem nele,
com as frases novas, e a regra antiga `texto_situacao_consulta` (com "procure o almoxarifado para
retirar") e `normalizar_numero_pedido` deram lugar a `texto_consulta_publica` e
`numero_de_pedido_publico`.

### Evidências executadas (2026-11-06)

Com o primeiro nome (segunda rodada, mesmo dia):

- `uv run pytest`: 2281 passaram, 1 pulado; `tests/test_consulta_publica.py` tem 103 casos, entre eles
  as variações do nome que conferem e as que não conferem (resposta idêntica à do número inexistente),
  o nome de outro pedido, o nome em branco, o nome errado contando no limite e a regra pura
  `nome_confere`. `ruff` e `manage.py check` sem problemas; nenhuma migration.
- Playwright: P-000169 enviado pela tela → "Ver a situação agora" (número e nome escondidos) → outro
  aparelho com `p169` e "Teste" → "Aguardando atendimento"; com "Playwright" (o sobrenome) → "não
  encontrado"; atendido pelo serviço → "Atendido"; inválido, não encontrado e 429 de novo.

Com a lista de materiais e a consulta no topo da página inicial (terceira rodada, mesmo dia): ver
o fim desta seção.

Primeira rodada (só com o número):

- `uv run pytest`: 2254 passaram, 1 pulado (o de flags do Windows); `tests/test_consulta_publica.py`
  tem 76 casos. `ruff check`, `ruff format --check`, `makemigrations --check` (nenhuma migration) e
  `manage.py check` sem problemas.
- Playwright contra o runserver local, com o banco local de teste: pedido de limpeza enviado pela tela
  (P-000168) → "Ver a situação agora" sem o número na URL → outro contexto de navegador em 375 px
  digitando `p168` → "Aguardando atendimento"; atendimento pelo `confirmar_atendimento` →
  "Atendido"; edição pelo `editar_atendimento` para 0,5 → "Atendido parcialmente"; `AV-000001` →
  inválido; `P-999999` → não encontrado; consultas repetidas → 429 com a mensagem do limite. A página
  inicial em 375 px não rola de lado.
- Os estados de EPI no navegador não foram exercitados (o banco local não tem pedido de EPI); estão
  cobertos pelo cliente de testes do Django.

Terceira rodada (lista de materiais e consulta no topo da página inicial):

- `uv run pytest`: 2291 passaram, 1 pulado. A lista é conferida em cada estado com os nomes, as
  quantidades pedidas e as unidades do cenário escritos no teste (a unidade da limpeza é a exibida ou,
  sem ela, a do cadastro, `catalogos.formulario_limpeza`): no parcial a quantidade continua a pedida,
  na troca o acrescentado não aparece, sem o nome certo a lista não aparece, e a consulta segue com no
  máximo 2 consultas ao banco.
- Playwright: P-000169 com "teste" no celular mostra "Materiais pedidos" (AÇÚCAR CRISTAL BRANCO,
  1 EMBALAGEM 5 Kg); a página inicial mostra
  "Já enviou um pedido? Consultar um pedido" acima dos formulários em 375 px e 1280 px, sem rolagem
  lateral.

- A lista é o mesmo parcial da tela de sucesso (`pedidos/_itens_pedidos.html`), a pedido do usuário:
  `test_a_lista_e_a_mesma_da_tela_de_sucesso` confere que o HTML das duas é igual; no celular, o
  P-000170 (4 materiais com unidades longas) sai como na confirmação, sem rolagem lateral.

- Rolagem (a pedido do usuário): no Playwright, em 375 px e 1280 px, a consulta com sucesso termina com o
  cartão do pedido no topo da tela (24 px no celular) e o botão da tela de sucesso também rola até
  ele; no erro, o formulário e o aviso ficam inteiros na tela. Um teste confere que há uma só âncora e
  em qual cartão, e outro que nenhum comentário de template vaza nas páginas da consulta.

## 7. Pendente de validação com solicitantes

- Se as frases de "Atendido" e "Atendido parcialmente" são entendidas como o almoxarifado espera (H2), e
  se "O que faltou não fica pendente neste pedido" deve sugerir um novo pedido ou procurar o almoxarifado.
- Se o número é de fato guardado (H1) ou se é preciso lembrá-lo no aparelho.
- Se o limite por rede atrapalha um prédio inteiro (H3).
- Se o formulário e a data do envio bastam para o solicitante perceber que digitou o número errado.
- Se o solicitante lembra do primeiro nome como o digitou (apelido, nome composto como "Ana Maria", que
  só compara "Ana"), e se o "não encontrado" com o nome errado é entendido.
