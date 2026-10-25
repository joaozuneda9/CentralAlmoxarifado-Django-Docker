---

description: "Tarefas da funcionalidade 005: consistência dos formulários públicos de pedido"
---

# Tasks: Consistência dos formulários públicos de pedido

**Input**: documentos de design em `specs/005-consistencia-formularios-publicos/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **incluídos**. A constituição do projeto (Princípio V) exige teste automatizado para toda mudança de comportamento. Os testes rodam contra MariaDB/MySQL, sem navegador; os de JavaScript só conferem texto do arquivo, então a conferência no navegador é manual (T064).

**Organization**: tarefas agrupadas por história de usuário (US1 a US9), na ordem de prioridade da spec.

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec (US1 a US9); fases de Setup, Foundational e Polish não têm
- Comandos: `uv run pytest <arquivo>`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run`. **Banco de desenvolvimento apenas; nada de lançamento no SCPI.**

## Regras gerais para todas as tarefas

- Nomes de código, textos e commits em português (pt-BR); mensagens ao usuário **exatamente** como em [contracts/mensagens.md](contracts/mensagens.md).
- `pedidos/servicos.py` continua o único lugar que grava pedidos; nada do robô do SCPI muda.
- Quantidades em `Decimal`; quantidade com até 3 casas; saldo com até 4 casas; nenhum número exibido com zeros à direita.
- Teste primeiro: escrever o teste da tarefa, vê-lo falhar, implementar.

---

## Phase 1: Setup

**Purpose**: linha de base antes de mexer no código

- [X] T001 Confirmar que a branch `claude/consistencia-formularios-publicos` está limpa de código (só `specs/005-consistencia-formularios-publicos/` fora do Git) e rodar `uv run pytest`; anotar o resultado como linha de base
- [X] T002 [P] Rodar `uv run ruff check . && uv run ruff format --check .` e `uv run python manage.py makemigrations --check --dry-run`; ambos devem estar limpos antes de começar

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Purpose**: as regras puras, a lista de unidades e a garantia de que **nenhuma fração é cortada** na equipe e nos avisos. Sem a última parte, o AB não pode passar a aceitar fração (hoje o Telegram e o atendimento fazem `int()` nele).

**⚠️ CRÍTICO**: nenhuma história começa antes desta fase terminar.

### Regras puras

- [X] T003 [P] Escrever os testes das regras puras em `tests/test_quantidade_por_unidade.py`: `truncar_qtd` (2,4996 → 2,499; 0,0004 → 0; 10 → 10; corte para baixo em 3 casas), `maximo_pedivel` (regra `por_unidade` com unidade fracionável → saldo truncado a 3 casas; contável ou sem unidade → parte inteira; regra `livre` → truncado a 3 casas; saldos 0,0004, 0,5, 2,4996, 2,5 e 10) e `interpretar_quantidade` (causas `ilegivel`, `zero`, `fracao_em_contavel`, `acima_do_maximo`; "1.5" com ponto, 4 casas, vazio, negativo, 999.999 e 1.000.000)
- [X] T004 Implementar `truncar_qtd(valor)` (`ROUND_DOWN` a 3 casas) e `maximo_pedivel(estoque, fracionavel, regra)` como funções puras, sem ORM, em `pedidos/regras.py` (data-model.md, "Máximo pedível")
- [X] T005 Implementar `interpretar_quantidade(texto, fracionavel)` → `(valor, causa)` e a tabela única de textos por causa em `pedidos/regras.py`, com os textos exatos de `contracts/mensagens.md` (inclui "Este material só é pedido em quantidade inteira (unidade: UN).", que omite a unidade quando o material não tem, e "A quantidade máxima é 999.999."); manter `parse_qtd_br` e `parse_inteiro` (depende de T004)

### Lista de unidades fracionáveis (dados)

- [X] T006 [P] Acrescentar `UNIDADE_FRACIONAVEL = "UNIDADE_FRACIONAVEL", "Unidades fracionáveis"` a `Opcao.Lista` em `catalogo/models.py` (só `choices`; nenhum campo novo)
- [X] T007 [P] Escrever `tests/test_migracao_unidades.py`: depois de migrar, existem as 10 unidades `M`, `MT`, `MTS`, `KM`, `KG`, `L`, `LT`, `M²`, `M³` e `T`, todas `ativo=True`; rodar a função de carga duas vezes não duplica (restrição `opcao_unica_na_lista`); `Opcao.valores(Opcao.Lista.UNIDADE_FRACIONAVEL)` devolve as 10; desativar `KG` a tira do resultado
- [X] T008 Criar a migration **nova** `catalogo/migrations/0002_unidades_fracionaveis.py` (nunca regenerar a 0001): `AlterField` de `Opcao.lista` (novas `choices`) e `RunPython` idempotente com `get_or_create` por `lista` + `valor`, `ativo=True` e `ordem` em sequência para as 10 unidades; a reversão não apaga nada (depende de T006)
- [X] T009 [P] Escrever em `tests/test_catalogos.py` os testes de `fracionavel`: unidade `KG`, ` kg ` e `M²` (e `M2`) são fracionáveis; `UN`, `BR`, `MC`, `GL`, `ML` e unidade vazia, não; item da limpeza com `unidade_exibida` "Pacote 500 g" e unidade do SCPI `UN` é contável; no AB, código antigo consolidado usa a unidade do código **canônico**; lista de unidades vazia → nenhum fracionável
- [X] T010 Em `catalogo/catalogos.py`: criar `unidades_fracionaveis()` (lê `Opcao.valores(Opcao.Lista.UNIDADE_FRACIONAVEL)` e normaliza com `norm_u`), acrescentar `ItemCatalogo.fracionavel: bool = False` e calcular o campo em `_item(...)` a partir de `Material.unidade` (a do SCPI), inclusive em `catalogo_limpeza` (antes de sobrescrever `unidade` por `unidade_exibida`) e em `catalogo_ab` (Material do canônico); a lista é lida **uma vez por montagem de catálogo** (depende de T008)

### Equipe e formatadores: nenhuma fração cortada

- [X] T011 [P] Escrever `tests/test_quantidade_equipe.py` e ajustar os testes antigos: (a) o aviso do Telegram de um pedido AB de 2,5 mostra "2,5"; (b) o campo de entrega do atendimento (`_formatar_qtd`) mostra "2,5"; (c) confirmar atendimento de pedido AB com entregue "0,5" de material `UN` é aceito; (d) `validar_saida` aceita 1,5 sem `regra_inteira`; (e) `atendimento_adicionar` aceita fração em pedido AB; (f) `inputmode="decimal"` em `_recibo_item.html` e `_adicionado.html` para pedido AB; ajustar `tests/test_atendimento_adicionados.py:225` (o erro "Pedido AB: a quantidade de … deve ser inteira." deixa de existir) e `tests/test_regras_saidas.py:96-97`
- [X] T012 Em `pedidos/regras.py`: remover o parâmetro `regra_inteira` e o ramo "Pedido AB: a quantidade de … deve ser inteira." de `validar_saida`; em `itens_conferem` (≈linha 862) usar sempre `parse_qtd_br`
- [X] T013 Em `pedidos/servicos.py`: remover `regra_inteira=pedido.origem == AB` (≈linha 523) e as duas escolhas `conv = parse_inteiro if pedido.origem == AB else parse_qtd_br` (≈629 e ≈854), passando a `parse_qtd_br`; tirar o import `parse_inteiro` se ficar sem uso (depende de T012)
- [X] T014 [P] Em `pedidos/telegram.py`: `_quantidade` passa a devolver `qtd_br(qtd)` para todas as origens
- [X] T015 [P] Em `pedidos/views/almoxarifado.py`: `_formatar_qtd` devolve `qtd_br(q)`; em `atendimento_adicionar` (≈linha 589) a regra de quantidade é a da equipe (`FLUXOS["avulsa"]`), não `FLUXOS["ab"]` nem `FLUXOS["limpeza"]`
- [X] T016 [P] Em `pedidos/templates/pedidos/_adicionado.html` (linha 20) e `pedidos/templates/pedidos/_recibo_item.html` (linha 16): `inputmode="decimal"` sempre, sem testar `pedido.origem == 'AB'`

### Configuração do fluxo (aditiva)

- [X] T017 Em `pedidos/fluxos.py`: acrescentar `Fluxo.regra_quantidade` (`"por_unidade"` para `limpeza` e `ab`, `"livre"` para `avulsa`), **mantendo** `inteiro`, `com_estoque` e `limita_estoque` até as histórias trocarem o uso (a remoção é a T054)

**Checkpoint**: regras puras testadas, lista de unidades carregada, `ItemCatalogo.fracionavel` pronto, equipe e avisos sem corte de fração. As histórias podem começar.

---

## Phase 3: User Story 1 - Pedir a quantidade certa para cada material (Priority: P1) 🎯 MVP

**Goal**: fração só em unidade fracionável, nos dois formulários, recusada na hora no material contado, com uma mensagem única; uma só validação do envio.

**Independent Test**: pedir 2,5 de um material `M` e de um material `UN`, nos dois formulários; o primeiro entra no pedido, o segundo é recusado ao adicionar, ao alterar e ao enviar.

### Tests for User Story 1

- [X] T018 [P] [US1] Em `tests/test_quantidade_por_unidade.py`, escrever os cenários da US1 pelo carrinho (`adicionar`, `alterar`) e por `client.post` em `pedidos:carrinho` e `pedidos:formulario`, para `limpeza` e `ab`: `M` aceita 2,5; `UN` recusa com a mensagem única; material sem unidade omite a unidade; "1,2345", "1.5" e "1000000" recebem a mensagem de cada causa (fracionável: "Informe uma quantidade maior que zero (use vírgula para decimais, ex.: 1,5)."; contado: "Informe um número inteiro maior que zero."; "A quantidade máxima é 999.999."); desativar a unidade `KG` em `Opcao` faz o próximo pedido recusar fração em `KG` sem reiniciar
- [X] T019 [P] [US1] Em `tests/test_regras_pedidos.py`, trocar `validar_pedido_ab` e `validar_pedido_limpeza` por `validar_pedido`: manter os casos de nome, destino, duplicado, fora do catálogo, soma por código e repetição; acrescentar AB com fração em `M` (aceita) e em `UN` (recusa com o texto único); ajustar os textos de quantidade inválida
- [X] T020 [P] [US1] Em `tests/test_carrinho.py`, ajustar `test_quantidades_invalidas` e `test_ab_estoque_mensagens` aos textos de `contracts/mensagens.md` e ao fato de o AB aceitar fração em unidade de medida

### Implementation for User Story 1

- [X] T021 [US1] Em `pedidos/carrinho.py`: substituir `_converter` e `quantidade` por `interpretar_quantidade`; `LinhaCarrinho.quantidade` passa a ser sempre `Decimal` e `texto` sempre `qtd_br` (some o `isinstance(int)`); `ler()` busca o item antes de interpretar a quantidade; linha de item ausente do catálogo continua com `parse_qtd_br`
- [X] T022 [US1] Em `pedidos/carrinho.py`: `limite()` devolve `maximo_pedivel(item.estoque, item.fracionavel, fluxo.regra_quantidade)`; `acima_do_estoque` e `_fq` usam `qtd_br` do valor já truncado; `motivo_bloqueio` bloqueia com "Sem estoque" quando o limite é ≤ 0 (depende de T021, mesmo arquivo)
- [X] T023 [US1] Em `pedidos/regras.py`: criar `validar_pedido(envio, catalogo, centros)` única (nome e destino obrigatórios, ao menos um item, por código: ilegível, fora do catálogo, duplicado, sem estoque, acima do máximo, soma de linhas repetidas), usando `interpretar_quantidade` e `maximo_pedivel` por item e os textos únicos; `Validacao.estoque_atual` guarda o máximo pedível; remover `validar_pedido_limpeza` e `validar_pedido_ab` (depende de T005 e T010)
- [X] T024 [US1] Em `pedidos/servicos.py`: `registrar_pedido` chama `validar_pedido` para as duas origens, sem `if origem == AB` (depende de T023)
- [X] T025 [US1] Em `pedidos/templates/pedidos/_resultados.html` (campo de quantidade) e `pedidos/templates/pedidos/_carrinho.html` (campo `item_qtd`): `inputmode="decimal"` sempre e rótulo de acessibilidade sem "(inteira)" por `fluxo.inteiro`

**Checkpoint**: US1 funcional e testável sozinha; o AB aceita fração em unidade de medida.

---

## Phase 4: User Story 2 - Ver o estoque como o limite real do pedido (Priority: P1)

**Goal**: o número da lista, o teto aceito e o texto do erro são o mesmo valor; linha de estoque única "Estoque N · UN".

**Independent Test**: para `M` e `UN` com saldos 2,4996, 2,5, 0,5 e 10, conferir lista, máximo aceito, máximo mais um e mensagem.

### Tests for User Story 2

- [X] T026 [P] [US2] Escrever `tests/test_estoque_exibido.py` com a matriz SC-001 (unidade `M` e `UN` × saldos 0,0004, 0,5, 2,4996, 2,5 e 10 × quantidade igual ao máximo e máximo mais um), nos dois formulários: "Estoque 2,499 · M"; "Estoque 2 · UN"; "Sem estoque" para `UN` com 0,5 e `M` com 0,0004; "10" sem zeros; mensagem "Quantidade acima do estoque. Estoque disponível: N U." idêntica ao adicionar, ao alterar e ao enviar; linha sem unidade é "Estoque N"
- [X] T027 [US2] Em `tests/test_carrinho.py`, ajustar `test_texto_de_estoque_do_ab`, `test_estoque_na_linha_da_avulsa_e_da_limpeza` (a avulsa passa a mostrar o saldo truncado: "Estoque 2,499" e bloqueio para 0,0004; manter código, unidade e classe) e as asserções das linhas 170, 253 e 503 ("10 UN disponíveis" vira "Estoque 10 · UN")

### Implementation for User Story 2

- [X] T028 [US2] Em `pedidos/fluxos.py`: `resultados()` e `Resultado` montam a linha única "Estoque N · UN" (sem a unidade quando o material não tem) com N igual a `maximo_pedivel`; remover o ramo `com_estoque` e a frase "N UN disponíveis"; para a avulsa, `Resultado.estoque` usa `qtd_br(truncar_qtd(estoque))` (deixa de usar `qtd_estoque`) e mantém código, unidade e classe (depende de T022)

**Checkpoint**: US1 e US2 funcionam juntas; lista, limite e mensagem coincidem.

---

## Phase 5: User Story 3 - Entender quando o formulário não pode ser usado (Priority: P2)

**Goal**: indisponível (bloqueia, mesma mensagem, aviso de saúde) e sem estoque agora (abre com aviso) nos dois formulários.

**Independent Test**: esvaziar o catálogo e depois zerar o estoque de todos os itens, abrindo os dois formulários em cada situação.

### Tests for User Story 3

- [X] T029 [P] [US3] Escrever `tests/test_estados_do_catalogo.py`: saldo nunca importado → "Este formulário está indisponível no momento. Avise o almoxarifado." nos dois, sem `name="token"`; catálogo vazio (limpeza sem itens; AB sem saídas na janela) → mesma mensagem; todos sem estoque → formulário abre com "Nenhum material deste formulário tem estoque agora." e itens "Sem estoque"; um item com estoque faz o aviso sumir; cadastro duplicado continua "Cadastro duplicado — avise o almoxarifado"
- [X] T030 [P] [US3] Em `tests/test_saude.py`: formulário sem itens aparece como `erro` por formulário; textos "formulários de limpeza e AB" no lugar de "formulário AB"; o "ok" com a contagem de itens continua
- [X] T031 [P] [US3] Em `tests/test_formularios_publicos.py`: `test_ab_indisponivel_sem_saldo` (≈linhas 92-99) passa a esperar a mensagem única (sem "estoque ou catálogo não carregou") e `test_formulario_indisponivel_sem_centros_de_custo` (≈198-201) continua

### Implementation for User Story 3

- [X] T032 [US3] Em `pedidos/servicos.py`: `catalogo_de` devolve `None` também para o AB sem itens (`ab.itens or None`), igual à limpeza
- [X] T033 [US3] Em `pedidos/views/publico.py` (`_contexto`) criar `sem_estoque_agora` (há itens e todos têm `motivo_bloqueio` não vazio) e, em `pedidos/templates/pedidos/_formulario.html`, mostrar o aviso no topo e unificar a mensagem de indisponível, removendo o ramo `fluxo.nome == "ab"` (linha 9)
- [X] T034 [US3] Em `catalogo/saude.py` (`_demais`): "Sem saldo importado" cita os dois formulários; formulário sem itens vira `ItemSaude("erro", …)` com o texto de `contracts/mensagens.md` (a limpeza deixa de ser sempre "ok")

**Checkpoint**: estados vazios iguais nos dois formulários e visíveis no painel.

---

## Phase 6: User Story 4 - Corrigir um item com problema sem perder o pedido (Priority: P2)

**Goal**: recusa por item devolve tudo preenchido, a linha marcada "Corrigir", com o mesmo texto do adicionar.

**Independent Test**: reduzir o estoque de um item depois de adicioná-lo e enviar; depois enviar uma quantidade ilegível.

### Tests for User Story 4

- [X] T035 [P] [US4] Em `tests/test_formularios_publicos.py`: recusa por estoque devolve nome, destino, observação e todos os itens, resumo no topo e a linha "Corrigir" com o texto de adicionar; quantidade ilegível chegada ao servidor **mantém a linha** com o texto digitado, marcada "Corrigir"; corrigir e reenviar registra o pedido

### Implementation for User Story 4

- [X] T036 [US4] Em `pedidos/carrinho.py`: `ler(..., manter_ilegiveis=False)` mantém, quando verdadeiro, a linha cujo par código/quantidade não converte, guardando o texto digitado (campo novo em `LinhaCarrinho`); `texto` devolve esse texto bruto. O envio e as operações do carrinho público usam esse modo até a correção ou remoção explícita; a saída avulsa mantém o padrão de descartar ilegíveis.
- [X] T037 [US4] Em `pedidos/views/publico.py` (`de_volta`) chamar `ler(..., manter_ilegiveis=True)` e, em `pedidos/templates/pedidos/_carrinho.html`, exibir o texto digitado da linha ilegível com o selo "Corrigir" (depende de T036)

**Checkpoint**: nenhuma recusa faz um item desaparecer.

---

## Phase 7: User Story 5 - Recuperar-se de uma recusa de proteção (Priority: P2)

**Goal**: mensagens humanas para ingresso inválido e envio rápido; genérica só para a isca; nada de "expirou".

**Independent Test**: enviar com `token` adulterado, em menos de 5 s e com a isca preenchida; conferir cada mensagem e a tentativa seguinte.

### Tests for User Story 5

- [X] T038 [P] [US5] Em `tests/test_protecao_pedidos.py`: `recusar` passa a devolver o **motivo** (`"isca"`, `"rapido"` ou `None`); ajustar as asserções de `test_recusar_isca_e_envio_rapido` (≈linhas 99-103)
- [X] T039 [P] [US5] Em `tests/test_formularios_publicos.py`: ingresso inválido → "Houve um problema ao confirmar o formulário. Seus dados foram mantidos: toque em Enviar de novo." com dados preservados (ajustar ≈linhas 142 e 418, que citam `MENSAGEM_EXPIRADO`); envio rápido → "Aguarde alguns segundos e toque em Enviar de novo."; isca → "Não foi possível registrar o pedido. Procure o almoxarifado."; nenhum texto diz "expirou"; reenvio idêntico e divergente seguem como estão

### Implementation for User Story 5

- [X] T040 [US5] Em `pedidos/protecao.py`: `MENSAGEM_EXPIRADO` vira `MENSAGEM_TOKEN_INVALIDO` (texto novo), criar `MENSAGEM_RAPIDO`, manter `MENSAGEM_RECUSA` só para a isca; `recusar` devolve o motivo (tempo mínimo de 5 s e isca inalterados)
- [X] T041 [US5] Em `pedidos/views/publico.py`: usar o motivo de `recusar` para escolher a mensagem em `de_volta` (depende de T040)

**Checkpoint**: nenhuma recusa de proteção deixa pessoa sem saída.

---

## Phase 8: User Story 6 - A equipe atende e registra quantidades fracionadas sem perda (Priority: P3)

**Goal**: o teto da equipe é o saldo truncado a 3 casas; pedidos antigos abrem iguais; a avulsa mantém regra e forma.

**Independent Test**: registrar pedido AB com fração e conferir Telegram, atendimento e recibo; entregar fração em material contado; registrar saída avulsa.

### Tests for User Story 6

- [X] T042 [P] [US6] Em `tests/test_avulsa_estoque.py`: o teto da avulsa e do atendimento é o saldo truncado a 3 casas (saldo 2,4996 aceita 2,499 e recusa 2,5 com "Estoque disponível: 2,499"); a edição aceita o gravado maior que o saldo (comportamento atual preservado); fração aceita em qualquer unidade
- [X] T043 [P] [US6] Escrever `tests/test_pedidos_antigos.py` (SC-008): um pedido AB gravado com quantidades inteiras e um da limpeza com decimais continuam com o mesmo texto no recibo, no detalhe e no aviso do Telegram depois das mudanças

### Implementation for User Story 6

- [X] T044 [US6] Em `pedidos/servicos.py`: `_limites_de_estoque` e `item_catalogo_gravado` usam `truncar_qtd(estoque)`; o teto de quem já está gravado continua sendo o maior entre o saldo e a quantidade gravada
- [X] T045 [US6] Em `pedidos/regras.py` (`validar_saida`): a mensagem "Saída de {codigo} maior que o estoque ({N})." usa o teto truncado já passado em `ItemSaida.estoque`, formatado com `qtd_br`; conferir que as chamadas em `servicos.py` entregam o limite truncado (depende de T044)

**Checkpoint**: a equipe vê, entrega e registra frações sem perda.

---

## Phase 9: User Story 7 - Aviso claro para quem está sem JavaScript (Priority: P3)

**Goal**: aviso explicando que o JavaScript é necessário; fim do código e dos comentários do modo "sem JavaScript" que não funciona.

**Independent Test**: abrir os dois formulários com JavaScript desligado (manual, T064) e conferir o HTML/CSS por teste.

### Tests for User Story 7

- [X] T046 [P] [US7] Em `tests/test_formularios_publicos.py`: a página dos dois formulários traz `<noscript>` com o texto de `contracts/mensagens.md` ("Este formulário precisa de JavaScript para funcionar. …"); `pedidos.css` esconde o formulário quando o `<html>` não tem a classe `js`; os arquivos `_materiais.html`, `_carrinho.html` e `_resultados.html` não prometem funcionamento sem JavaScript (testes de texto: só provam o arquivo, não o navegador)

### Implementation for User Story 7

- [X] T047 [US7] Em `pedidos/templates/pedidos/formulario.html` colocar o `<noscript>` com o aviso (classes `aviso aviso-atencao`) e, em `pedidos/static/pedidos/css/pedidos.css`, a regra que esconde `#formulario` quando `html:not(.js)`
- [X] T048 [P] [US7] Remover ou corrigir os comentários que prometem o modo "sem JavaScript" dos formulários públicos: `pedidos/templates/pedidos/_materiais.html` (linhas 10 e 19), `_carrinho.html` (3 e 40), `_resultados.html` (18), `pedidos/static/pedidos/css/pedidos.css` (32, 49, 602) e `pedidos/static/pedidos/js/pedidos.js` (1024); **não** tocar nos comentários da área do almoxarifado (recibo, impressão, atendimento), que funcionam sem JavaScript

**Checkpoint**: o requisito de JavaScript está declarado e o código não mente sobre ele.

---

## Phase 10: User Story 8 - Criar um formulário novo sem mexer no núcleo (Priority: P3)

**Goal**: cada formulário é uma entrada de configuração; o núcleo não pergunta pelo nome nem pela origem.

**Independent Test**: com um formulário de teste (só catálogo e textos), buscar, adicionar, enviar e ver o recibo e o painel sem alterar o núcleo.

### Tests for User Story 8

- [X] T049 [P] [US8] Escrever `tests/test_fluxo_configuravel.py`: registrar (por `monkeypatch` em `FLUXOS`) um fluxo de teste com catálogo e textos próprios e uma origem de teste; ele abre, busca, valida, grava (prefixo `P-`), aparece no painel e no recibo, e o limite por nome o inclui; a página inicial lista os formulários públicos a partir de `FLUXOS`

### Implementation for User Story 8

- [X] T050 [US8] Em `pedidos/fluxos.py`: `Fluxo` ganha `catalogo` (função sem argumentos), `exemplo_busca`, `exemplo_inicio` e `icone`, conforme `contracts/configuracao-fluxo.md`; preencher as três entradas de `FLUXOS` com os textos que hoje estão fixos nos modelos ("Ex.: detergente, café", "Ex.: luva, fita veda rosca", "Ex.: luva, fita veda rosca, 016.005.010" e os exemplos de `inicio.html`)
- [X] T051 [US8] Em `pedidos/servicos.py` e `pedidos/regras.py`: `catalogo_de(origem)` consulta o `Fluxo` da origem (mantendo `None` para indisponível); `PREFIXOS` vira regra única (`AV-` para a avulsa, `P-` para as demais); criar `origem_publica(origem)` (`origem != AVULSA`) e usá-la em `regras.py` (≈linhas 850) e `servicos._limite_atingido` (≈linha 199, no lugar de `origem__in=[LIMPEZA, AB]`) (depende de T050)
- [X] T052 [US8] Em `pedidos/templates/pedidos/_materiais.html` (placeholder da busca), `pedidos/templates/pedidos/_formulario.html` (mensagens e rótulos de envio) e `pedidos/templates/pedidos/inicio.html` (cartões gerados dos fluxos públicos, com `fluxo.titulo`, `fluxo.exemplo_inicio` e `fluxo.icone`): ler tudo de `fluxo.*`, sem testar `fluxo.nome`; ajustar `tests/test_formularios_publicos.py` (`test_inicio_*`, `test_exemplo_da_busca_combina_com_o_formulario`) se o HTML mudar
- [X] T053 [P] [US8] Atualizar `specs/005-consistencia-formularios-publicos/contracts/configuracao-fluxo.md` com os campos `exemplo_inicio` e `icone`
- [X] T054 [US8] Em `pedidos/fluxos.py` e nos usos restantes (`grep` por `.inteiro`, `com_estoque`, `limita_estoque`): remover os campos antigos de `Fluxo` e qualquer uso que sobrar, com `uv run pytest` limpo (depende de T021 a T028 e T050)

**Checkpoint**: um formulário novo é uma entrada de configuração mais uma função de catálogo.

---

## Phase 11: User Story 9 - Envios simultâneos não esperam a montagem do catálogo (Priority: P3)

**Goal**: o catálogo do AB é montado antes do bloqueio da numeração; a medição fica registrada.

**Independent Test**: conferir que o catálogo é pedido antes de a sequência ser travada e que o envio duplo simultâneo continua gravando um pedido só.

### Tests for User Story 9

- [X] T055 [P] [US9] Em `tests/test_registrar_pedido.py`: a ordem das chamadas é `catalogo_de` e `centros` **antes** de `travar_sequencia`; `test_envio_duplo_simultaneo_grava_um_pedido`, `test_falha_inesperada_desfaz_tudo_e_a_retentativa_nao_duplica`, reenvio e divergência continuam passando; a ordem das respostas (reenvio, limite, indisponível, validação) não muda

### Implementation for User Story 9

- [X] T056 [US9] Em `pedidos/servicos.py` (`registrar_pedido`): carregar `catalogo_de(origem)` e `centros()` antes de `with transaction.atomic()`; manter dentro dele `travar_sequencia()`, reenvio, limites, validação e gravação (depende de T024 e T032)
- [X] T057 [US9] Rodar o trecho de `quickstart.md` (seção 5) com dados reais (cópia do banco ou ambiente com a carga; em produção só a pedido do usuário) e registrar tempo, número de consultas e tamanho dos dados na tabela *Medição* de `specs/005-consistencia-formularios-publicos/research.md`; não propor cache nesta funcionalidade (a medição indireta por HTTP já está registrada)

**Checkpoint**: a fila única de envios não carrega a montagem do catálogo.

---

## Phase 12: Polish & Cross-Cutting

**Purpose**: documentação, limpeza, portões e conferência final

- [X] T058 [P] Corrigir `docs/superpowers/specs/2026-10-10-central-almoxarifado-django-design.md` (§4 catálogos e §5 fluxo 1): regra por unidade, avulsa com saldo positivo, limite da limpeza, estados do catálogo, mensagens
- [X] T059 [P] Atualizar o `CLAUDE.md` no mesmo PR: seções de quantidades e estoque (regra por unidade e lista no admin), indisponível e sem estoque, equipe, JavaScript como requisito, `Fluxo` e como criar um formulário novo
- [X] T060 [P] Corrigir o docstring de `pedidos/fluxos.py` ("Cada fluxo diz de que catálogo lê…") e os docstrings de `pedidos/carrinho.py` e `pedidos/views/materiais.py` que citam "parte inteira do estoque no AB"
- [X] T061 Remover o que ficou sem uso (`grep` e Serena `find_referencing_symbols`): `qtd_estoque`, `parse_inteiro` e `estoque_inteiro` só se nada mais os referenciar; manter `ItemCatalogo.disponivel` se os testes ainda o usam, e anotar a decisão
- [X] T062 Rodar os portões: `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run python manage.py makemigrations --check --dry-run` e `uv run python manage.py check --deploy` com `DEBUG=0`; todos limpos
- [X] T063 Percorrer os cenários 1 a 12 de `quickstart.md` (seção 3) no servidor de desenvolvimento e anotar o resultado
- [X] T064 Conferência manual em tela de celular (375 px) dos dois formulários, com a lista da seção 4 do `quickstart.md`, e registrar o resultado (SC-010)
- [X] T065 Revisar `specs/005-consistencia-formularios-publicos/research.md` (itens a confirmar: unidade do código canônico no AB com um caso real de de/para; tabela *Medição*) e `checklists/requirements.md`
- [X] T066 Resumir as mudanças ao usuário; commit e PR para `develop` **só quando o usuário pedir** (regra Git do `CLAUDE.md`), PR com a lista de divergências deliberadas e sem lançar nada no SCPI

---

## Dependencies & Execution Order

### Dependências entre fases

- **Setup (Phase 1)**: sem dependências.
- **Foundational (Phase 2)**: depende do Setup e **bloqueia todas as histórias**. Dentro dela: T004 → T005; T006 → T008 → T010; T012 → T013; o resto em paralelo.
- **US1 (P1)** e **US2 (P1)**: dependem da Foundational. US2 depende de T022 (a regra de limite da US1). Compartilham `pedidos/carrinho.py`, `pedidos/fluxos.py` e `tests/test_carrinho.py`, então rodam em sequência.
- **US3** depende de US1 (usa `motivo_bloqueio` e `maximo_pedivel` em `carrinho.py`).
- **US4** depende de US1 (`ler()` e `LinhaCarrinho`).
- **US5** e **US7** são independentes (só da Foundational).
- **US6** depende da Foundational (T012 a T016) e dos helpers da US1 (`truncar_qtd` já vem da Foundational).
- **US8** depende de US1, US2 e US3 (os usos de `inteiro`, `com_estoque` e do catálogo precisam ter sido trocados antes de T054).
- **US9** depende de T024 (US1) e T032 (US3), pois mexe nas mesmas funções de `servicos.py`.
- **Polish** depende de todas as histórias escolhidas.

### Dependências dentro de cada história

Teste → regra pura → serviço → tela. Tarefas no mesmo arquivo não são paralelas.

### Oportunidades de paralelismo

- **Foundational:** T003, T006, T007, T009, T011, T014, T015, T016 em paralelo (arquivos diferentes).
- **US1:** T018, T019 e T020 em paralelo (testes em arquivos diferentes).
- **US3:** T029, T030 e T031 em paralelo.
- **US5 e US7** podem andar em paralelo com US3 e US4 (arquivos diferentes), com cuidado em `tests/test_formularios_publicos.py` e `publico.py`, que várias histórias tocam.

---

## Implementation Strategy

### MVP primeiro (US1 + US2)

1. Setup e Foundational (inclui a garantia de que a fração não é cortada).
2. US1 (quantidade por unidade) e US2 (estoque exibido = limite).
3. **Parar e validar**: matriz SC-001 e os cenários 1 a 4 do `quickstart.md`.
4. A US1 **não deve ir à produção sem a Foundational completa**: sem T011 a T016, o AB aceitaria fração e o Telegram e o atendimento mostrariam o número cortado.

### Entrega incremental

Depois do MVP, entregar nesta ordem: US3 (estados) → US4 (erros) → US5 (proteções) → US6 (equipe) → US7 (JavaScript) → US8 (formulário configurável) → US9 (concorrência) → Polish. Cada história deixa o sistema funcionando e os testes passando.

### Notas

- Uma migration nova (T008) e nenhuma coluna nova em `Pedido`: pedidos existentes não são convertidos.
- Não rodar `migrate`, `lancar_saidas` nem comandos que acionem o SCPI em produção por iniciativa própria.
- Commits só quando o usuário pedir, na branch `claude/consistencia-formularios-publicos`.
