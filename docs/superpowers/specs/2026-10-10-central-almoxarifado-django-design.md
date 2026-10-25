# Central Almoxarifado em Django — design

Data: 2026-10-10 · Situação: executada (registro histórico da reescrita)

> Esta spec descreve a migração do Apps Script. O que ela diz sobre manter os fluxos, as regras
> e os textos do sistema antigo valia para a migração, já concluída, e não é requisito atual:
> o comportamento vigente é o do código, dos testes e das specs posteriores (constituição,
> Princípio I).

## 1. Objetivo

Reescrever o Central Almoxarifado (hoje Google Apps Script + Google Sheets) como
um aplicativo Django com banco próprio, rodando no navegador, **sem nenhuma
dependência da plataforma Google**. Os fluxos e as regras de negócio continuam
os mesmos; mudam o armazenamento, a interface e a integração com o SCPI.

**Sucesso:** funcionários fazem pedidos, o almoxarifado atende, as saídas chegam
ao SCPI pelo robô e nenhuma etapa passa pelo Google.

### Decisões já tomadas

| Tema | Decisão |
|---|---|
| Hospedagem | Projeto Django **separado**, no mesmo servidor Windows do ProducaoLab (rede SAEP). Instalação e operação do servidor passam pelo André. |
| PWA | Não. Aplicativo web comum, no navegador. |
| Escopo funcional | O do Central Almoxarifado atual (pedido → atendimento → saída → SCPI). **Sem** o fluxo de autorização por chefe de setor do WMS-SAEP-v2. |
| Interface | Design system Clean (`.claude/skills/clean-design/`, spec `2026-10-10-interface-clean-design.md`): só tema claro, fontes locais, destaque azul `#2563EB`. |
| Robôs SCPI | Viram comandos `manage.py` do próprio projeto e rodam no servidor; o lançamento é disparado por botão no painel. |
| Curva ABC | Deixa de ser planilha: é o ranking de materiais por número de saídas do SCPI, calculado no banco e consolidado pelo de/para de códigos (antigo → canônico); a planilha MAPEAMENTO DE/PARA CONSOLIDADO também vira o cadastro de pares, as curvas por frequência e por valor e a reposição (`specs/001-depara-curva-abc`). |
| Login | Formulários dos funcionários **abertos, em qualquer rede**; área do almoxarifado com login do Django por matrícula. |

### Fora do escopo

- Os demais scripts do `extrair-relatorio` usados pelo setor de Compras
  (`exportar_entradas`, `exportar_pedidos`, `exportar_compras` e o envio de
  `exportar_saidas` para a planilha de relatórios) continuam no Google.
- Modo offline, aplicativo instalável, notificações push.
- Controle de estoque próprio (reserva, livro-razão): o saldo continua vindo do SCPI.

## 2. Arquitetura

### Stack

- Python 3.13, Django 6.x (mesma linha do WMS-Almoxarifado), `uv` para dependências.
- Banco: o servidor MySQL 8 / MariaDB já instalado no servidor do ProducaoLab,
  com **banco e usuário próprios** (`mysqlclient`).
- Interface: templates do Django, HTMX 4.0.0 vendorizado, CSS próprio com tokens,
  sem npm, bundler ou CDN.
- Playwright + Chromium para os robôs do SCPI.
- Servidor de aplicação: `waitress`, registrado como serviço do Windows (NSSM).
  Opcionalmente atrás do Apache do servidor em `/almoxarifado`.

### Repositório

O projeto Django fica num **repositório novo**, `CentralAlmoxarifado-Django`.
O repositório `CentralAlmoxarifado` (Apps Script) continua como está até a
virada e depois é arquivado (seção 8); dele vêm, como referência, `Regras.gs`,
os testes em Node e as telas atuais.

```
config/            settings (lidos do .env), urls, wsgi
interface/         tokens.css, base.css, components.css, shell.js, htmx,
                   parciais (_mensagens, _paginacao, _th_ordenavel) e os dois layouts
pedidos/           regras.py, models, views e templates: formulários, painel,
                   atendimento, saída avulsa, recibos, travas do SCPI
catalogo/          Material, ItemLimpeza, CentroCusto, Opcao, SaidaSCPI, Importacao;
                   montagem dos catálogos dos formulários e saúde do catálogo
scpi/              código vindo do extrair-relatorio: browser.py, normalizadores,
                   lançador (Playwright); management/commands:
                     importar_cadastro · importar_estoque · importar_saidas_scpi
                     lancar_saidas · importar_planilhas (migração única)
deploy/            INSTALACAO.md, .bat do agendador, atualizar.bat, backup
tests/             pytest + pytest-django
```

O código do SCPI é **copiado** do `extrair-relatorio` (não é dependência): a
versão do almoxarifado passa a gravar no banco, enquanto o `extrair-relatorio`
segue gravando no Google para o setor de Compras. A parte de Playwright
(login, navegação, interceptação do CSV, preenchimento do formulário de saída,
trava de arquivo e journal) vem praticamente sem mudança; só as funções que
liam ou gravavam planilhas são substituídas por acesso ao banco.

### Interface

Dois layouts sobre o design system Clean (`.claude/skills/clean-design/`, spec
`2026-10-10-interface-clean-design.md`), só com tema claro, fontes servidas localmente
(Geist, DM Sans e Geist Mono) e destaque azul `#2563EB`:

- **Almoxarifado** (login obrigatório): shell com barra lateral branca — Painel,
  Saída avulsa, Recibos, Catálogo, Lançamentos SCPI — em ritmo compacto.
- **Formulários públicos** (sem login): mesmo vocabulário, sem barra lateral, em ritmo
  arejado e priorizando o celular; busca de material e montagem do pedido com HTMX.

As telas atuais são **refeitas** nesse padrão, mantendo campos e fluxos. As regras do
`docs/DESIGN.md` valem: um destaque azul, estado nunca só por cor, códigos em fonte mono,
tabelas com rolagem lateral no celular. O `THIRD-PARTY-NOTICES.md` cita as fontes (OFL), os
ícones Lucide (ISC) e o que ainda é copiado do WMS-Almoxarifado.

## 3. Modelos de dados

### `catalogo`

| Modelo | Campos | Origem / substitui |
|---|---|---|
| `Material` | `codigo` (CADPRO, texto opaco, único), `nome`, `unidade`, `grupo`, `subgrupo`, `oculto` (NOCULTAR), `duplicado`, `estoque` (decimal), `estoque_em` | `importar_cadastro` + `importar_estoque`; substitui as planilhas de cadastro e "Banco Geral" |
| `ItemLimpeza` | `material` (FK), `categoria`, `nome_exibido`, `unidade_exibida`, `ordem` | admin; substitui `Lista_Limpeza` |
| `CentroCusto` | `descricao`, `codigo`, `placa` | admin; substitui `Centros de Custo` (o robô lê daqui) |
| `Opcao` | `lista` (TIPO_SAIDA, GRUPO_OCULTO_AB, CATEGORIA_LIMPEZA, FUNCIONARIO), `valor`, `ordem`, `ativo` | admin; substitui a aba `Listas` |
| `SaidaSCPI` | `id_requi`, `cadpro`, `item`, `data`, `qtd`, `valor`; único (`id_requi`, `cadpro`, `item`), com `item` a ordem da linha entre as do mesmo material na requisição | `importar_saidas_scpi`; equivale à aba `Saídas` da planilha de mapeamento (a `MOV_NORM` é a consolidação pelo de/para, calculada em `catalogo.consultas_curva`) |
| `Importacao` | `tipo`, `inicio`, `fim`, `situacao`, `linhas`, `avisos`, `erro` | registro de cada importação; alimenta a saúde do catálogo |

`duplicado` marca código que veio repetido no cadastro do SCPI; esses
materiais ficam bloqueados nos formulários, como hoje.

### `pedidos`

| Modelo | Campos | Substitui |
|---|---|---|
| `Pedido` | `id` (UUID do envio), `numero` (`P-000123` / `AV-000123`, único), `origem` (LIMPEZA, AB, AVULSA), `criado_em`, `solicitante`, `destino`, `obs`, `registrado_por` (FK usuário, só AVULSA) | aba `Pedidos` (cabeçalho) |
| `ItemPedido` | `pedido`, retrato do material no aceite (`codigo`, `material`, `unidade`, `categoria`, `grupo`, `subgrupo`, `estoque_no_pedido`), `qtd_pedida`, `qtd_entregue` | aba `Itens` |
| `Atendimento` | `pedido` (1:1), `id` (UUID), `data_efetiva`, `recebedor`, `centro_custo`, `tipo_saida`, `placa`, `obs`, `atendido_em`, `atendido_por`, `recibo_impresso_em` | colunas de atendimento de `Pedidos` |
| `LinhaSaida` | `atendimento`, `seq`, `data`, `qtd`, `codigo`, `descricao`, `recebedor`, `centro_custo`, `tipo_saida`, `placa`, `obs`, `lote` (= número do pedido), `status`, `requisicao_scpi`, `lancado_em`, `mensagem` | aba `Saídas` (contrato com o robô) |
| `ExecucaoRobo` | `tipo` (LANCAMENTO, IMPORTACAO), `iniciada_por`, `inicio`, `fim`, `situacao`, `resumo`, `log` | o terminal onde o robô roda hoje |
| `Sequencia` | `prefixo`, `ultimo` | numeração; travada com `select_for_update` |

`LinhaSaida.status`: `PENDENTE`, `EM_LANCAMENTO`, `LANCADA`, `ERRO`,
`VERIFICAR`, `NAO_LANCAR`. O "não lançar" deixa de ser texto na observação
("FORA DE ESTOQUE", "NÃO LANÇAR") e passa a ser status.

P- e AV- compartilham uma única sequência numérica, como hoje
(`proximoNumero_`): a `Sequencia` tem uma linha só, e o prefixo vem da origem.

## 4. Regras de negócio

`Regras.gs` vira `pedidos/regras.py`, com funções puras (sem ORM), traduzidas
uma a uma e com os mesmos textos de erro:

- `somar_por_codigo`, `resolver_destino`, `validar_pedido_limpeza`,
  `validar_pedido_ab`, `resolver_centro_custo`, `validar_saida`,
  `situacao_scpi`, `situacao_pedido`, conversões pt-BR (`parse_qtd_br`,
  `parse_inteiro`, `qtd_br`, `estoque_inteiro`, `norm_placa`, `norm_u`).
- Erros de validação continuam coletados em lista (`codigo`, `texto`) para o
  formulário mostrar tudo de uma vez.
- `registroConfere_` / `itensConferem_` continuam para decidir entre "reenvio
  igual" e "reenvio divergente".
- Deixam de existir: `montarLinhasSaida_` como formatação de planilha (vira
  criação de `LinhaSaida`), `concluirTransferencia`, `conferirAposFalha_`,
  cache do catálogo e lock global — todos existiam por causa de gravação
  parcial na planilha, impossível dentro de uma transação.

### Catálogos dos formulários (consulta ao banco, sem cache)

- **Limpeza:** `ItemLimpeza` cujo material existe e não está oculto; nome e
  unidade exibidos têm prioridade sobre o cadastro (a regra de quantidade, porém,
  olha a unidade do SCPI).
- **AB:** materiais de `SaidaSCPI` ordenados por número de ocorrências
  (desc.), excluindo os que estão em `ItemLimpeza`, os ocultos e os de grupo
  em `GRUPO_OCULTO_AB`; estoque disponível = o máximo pedível (ver abaixo); código
  ausente do estoque = 0. O catálogo do AB continua vindo do histórico de saídas
  porque o cadastro do SCPI tem muitos materiais desatualizados.
- **Saída avulsa:** todo material não oculto e com saldo positivo.
- Em todos, material `duplicado` aparece bloqueado.
- **Indisponível:** se o saldo nunca foi importado ou o catálogo não tem item algum, o
  formulário (limpeza ou AB) fica indisponível, com a mesma mensagem nos dois e um aviso de saúde
  no painel. Se há itens e todos estão sem estoque, o formulário abre com um aviso no topo.

### Quantidade e estoque (spec 005, substitui "AB só inteiros")

- A quantidade segue a **unidade do material** (a do cadastro do SCPI; no AB, a do código
  canônico), igual nos dois formulários públicos. Unidade fracionável (lista mantida no admin,
  inicialmente `M`, `MT`, `MTS`, `KM`, `KG`, `L`, `LT`, `M²`, `M³` e `T`) aceita até 3 casas
  decimais; qualquer outra, ou material sem unidade, só inteiro, e a fração é recusada na hora.
- O **máximo pedível** é o saldo truncado a 3 casas (para unidade contada, a parte inteira). É o
  mesmo número na lista ("Estoque N · UN"), no teto de adicionar e alterar, na validação do envio
  e no texto "Estoque disponível". Nenhum número mostra zeros à direita.
- A equipe (atendimento e saída avulsa) aceita fração em qualquer unidade, com o teto no saldo
  truncado a 3 casas.
- Divergências deliberadas do Apps Script: o AB passa a aceitar fração (a origem só aceitava
  inteiro, sem motivo registrado) e a limpeza passa a limitar pelo saldo (a origem não limitava).

## 5. Fluxos

1. **Pedido do funcionário (limpeza ou AB).** A página é aberta com um
   `envio_id` (UUID) em campo escondido. Busca de material via HTMX; o pedido
   é montado na página e enviado num POST único. `regras.py` valida; `Pedido`
   e `ItemPedido` são gravados numa transação. Reenvio com o mesmo `envio_id`:
   igual → confirma de novo; diferente → mensagem de divergência. Telegram via
   `transaction.on_commit`.
   Proteção contra abuso:
   - limite por IP: 3 pedidos a cada 10 minutos e 10 por dia; reenvio do
     mesmo `envio_id` não conta;
   - limite por solicitante: 5 pedidos por dia;
   - campo isca (honeypot) e tempo mínimo de preenchimento (envio menos de
     5 s após abrir a página é recusado);
   - tamanho máximo do pedido: 40 itens; textos livres limitados a 200 caracteres;
   - CSRF e toda validação no servidor;
   - token sem validade (o identificador é único e o reenvio igual só confirma); token
     inválido e envio rápido demais têm mensagem própria, com os dados mantidos, e só a isca
     recebe a mensagem genérica;
   - o JavaScript é requisito: sem ele, a página mostra só um aviso.
   Ao atingir um limite, a mensagem pede para procurar o almoxarifado. Os
   valores ficam no `settings` para ajuste. Atenção: aparelhos atrás do mesmo
   IP (rede de operadora ou NAT) dividem o limite por IP.
2. **Painel.** Lista de pedidos e saídas avulsas, mais recentes primeiro, com
   filtros (situação, situação SCPI, origem, período, busca) e paginação via
   HTMX. Situação do pedido e situação no SCPI calculadas por `regras.py` a
   partir de `Atendimento` e `LinhaSaida`. Inclui o quadro de saúde do catálogo.
3. **Confirmar atendimento.** `select_for_update` no pedido; numa transação:
   `Atendimento`, `qtd_entregue` de cada item e uma `LinhaSaida` por item com
   quantidade > 0. Pedido AB aceita só inteiros; centro de custo resolvido
   pela placa como hoje. Reenvio com o mesmo `atendimento_id` e mesmos dados
   confirma; outro atendimento para o mesmo pedido é recusado.
4. **Saída avulsa.** `Pedido` AVULSA, `Atendimento` e `LinhaSaida` numa
   transação; `registrado_por` = usuário logado. Após gravar, oferece o recibo.
5. **Recibos.** Página de impressão de um ou vários atendimentos (lote dos
   pendentes); `recibo_impresso_em` é gravado só na primeira impressão.
   O recibo impresso não mostra quem registrou.
6. **Lançar no SCPI.** Botão no painel cria `ExecucaoRobo` e inicia
   `manage.py lancar_saidas --execucao <id>` em processo separado. Botão
   bloqueado enquanto houver execução em andamento (verificado no banco, além
   da trava de arquivo do robô). O robô agrupa as linhas `PENDENTE` por
   `lote`; para cada grupo grava `EM_LANCAMENTO` e confirma a transação
   **antes** de abrir o formulário no SCPI; depois grava `LANCADA` +
   `requisicao_scpi` + `lancado_em`, ou `ERRO` + mensagem, ou `VERIFICAR`
   quando o resultado é incerto. O painel atualiza o andamento por HTMX a
   cada poucos segundos. Uma opção "simulação" executa com `--dry-run`.
7. **Resolver travas.** Para linha em `VERIFICAR` (ou `EM_LANCAMENTO` órfã):
   informar o nº da requisição (→ `LANCADA`), liberar para relançar
   (→ `PENDENTE`) ou marcar `NAO_LANCAR`. Linha em `ERRO` pode ser corrigida
   e liberada. O sistema nunca destrava sozinho. Casos raros: admin do Django.
8. **Importações.** Agendadas e também disparáveis por botão "Atualizar agora":
   - `importar_cadastro`: insere/atualiza `Material`, marca `oculto` e `duplicado`;
     material que some do cadastro é marcado oculto (não apagado, pois há
     histórico de pedidos).
   - `importar_estoque`: substitui todos os saldos; código ausente = 0.
     CSV vazio aborta sem alterar nada.
   - `importar_saidas_scpi`: busca apenas o intervalo novo (estado guardado
     em `Importacao`), sem duplicar (`id_requi`, `cadpro`).
   Cada execução grava `Importacao`.

## 6. Erros

- **Erro de negócio** não é exceção: o formulário volta com a lista do que
  corrigir e mantém o que foi preenchido.
- **Falha inesperada:** a transação desfaz tudo; a página pede nova tentativa,
  que reaproveita o mesmo identificador e não duplica.
- **Telegram fora do ar:** registra no log; o pedido segue aceito.
- **Importação com falha:** dados anteriores intactos; erro exibido na saúde
  do catálogo. Saldo com mais de 24 h sem atualização gera aviso.
- **Robô interrompido:** linhas `EM_LANCAMENTO` ficam travadas até conferência
  humana (fluxo 7); `ExecucaoRobo` sem fim há mais de 1 h aparece como
  "interrompida" e libera o botão.
- **Logs:** arquivo com rotação em `logs/` (fora do git).

## 7. Testes

pytest + pytest-django, banco MySQL/MariaDB local (Docker ou instalado), para
`select_for_update` e transações se comportarem como no servidor.

- `regras.py`: os casos de `tests/regras.test.cjs` e `tests/servicos.test.cjs`
  do repositório `CentralAlmoxarifado`, traduzidos.
- Fluxos com banco: pedido, reenvio igual, reenvio divergente, limites de abuso,
  atendimento (inclusive concorrente), avulsa, recibos, transições de status,
  catálogos e ranking AB.
- Importadores: CSVs de exemplo anonimizados em `tests/fixtures/`, sem Playwright.
- Robô: agrupamento por lote, seleção de pendentes e gravação de resultado
  (adaptação de `tests/lancar_saidas_lote_test.py` do `CentralAlmoxarifado`)
  com o SCPI simulado. O
  SCPI real só é tocado manualmente, com `--dry-run`.
- `check --deploy` sem avisos na configuração de produção.

## 8. Implantação, migração e virada

### Servidor (pasta `deploy/`)

Substituída pela implantação em Docker: `2026-10-15-docker-design.md`.

- `INSTALACAO.md` para o André: Python 3.13, `uv`, `playwright install
  chromium`; criar banco e usuário; preencher `.env`; `migrate`,
  `collectstatic`, `createsuperuser`; serviço `waitress` via NSSM; proxy
  opcional no Apache.
- `.bat` para o Agendador de Tarefas: estoque a cada 30 min em horário de
  expediente; cadastro e saídas SCPI uma vez por dia; backup diário
  (`mysqldump`, retenção de 60 dias, fora do repositório).
- `atualizar.bat`: `git pull`, `uv sync`, `migrate`, `collectstatic`,
  reinício do serviço.
- Segredos só no `.env` (fora do git), com `.env.example` versionado:
  `SECRET_KEY`, banco, `SAEP_USER`/`SAEP_PASS`, `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID`,
  `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`. `DEBUG` desligado em produção.

### Migração dos dados

1. `importar_planilhas` (uma vez): lê arquivos `.xlsx` exportados à mão da
   planilha atual — Pedidos, Itens, Saídas, Centros de Custo, Listas,
   Lista_Limpeza. Nenhuma credencial Google entra no projeto. Mantém os números
   P-/AV- (a `Sequencia` continua do maior), requisições e status das linhas
   (o texto "FORA DE ESTOQUE"/"NÃO LANÇAR" na observação vira `NAO_LANCAR`).
2. Carga inicial: `importar_cadastro`, `importar_estoque` e histórico completo
   de `importar_saidas_scpi`.

### Virada

1. Período em paralelo com o lançamento em `--dry-run`, conferindo pedidos,
   atendimentos e lotes contra o Apps Script.
2. Esvaziar as pendências do robô antigo.
3. Importação final das planilhas.
4. Desativar a implantação do Apps Script; a página antiga aponta para o
   endereço novo.
5. Liberar o lançamento real no Django.
6. Arquivar o repositório `CentralAlmoxarifado` (Apps Script).

## 9. Subprojetos e ordem de entrega

Cada um vira um plano de implementação próprio:

1. **Fundação:** projeto Django, settings/.env, MySQL, login por matrícula,
   interface base (layouts, tokens, HTMX), admin dos cadastros.
2. **Catálogo e importadores:** modelos do `catalogo`, código SCPI copiado,
   `importar_cadastro`, `importar_estoque`, `importar_saidas_scpi`, saúde do catálogo.
3. **Pedidos:** `regras.py` + testes, formulários públicos, painel, atendimento,
   saída avulsa, recibos, Telegram.
4. **Lançamento no SCPI:** `lancar_saidas` sobre o banco, botão, andamento,
   resolução de travas.
5. **Implantação e migração:** `deploy/`, `importar_planilhas`, período em
   paralelo e virada.
