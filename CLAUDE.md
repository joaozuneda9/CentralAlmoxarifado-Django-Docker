# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Regra prioritária: código Python com o Serena

- Para investigar ou alterar código Python, use primeiro a análise semântica do Serena, antes de
  uma sequência de buscas ou leituras de arquivos: `find_symbol` ou `get_symbols_overview` para
  localizar implementações, e `find_referencing_symbols` para ver quem depende de um símbolo e o
  impacto de uma mudança.
- Se as ferramentas `mcp__serena__*` não estiverem na lista, descubra-as com o `ToolSearch`
  (`select:mcp__serena__get_symbols_overview,mcp__serena__find_symbol,` e
  `mcp__serena__find_referencing_symbols`) antes de concluir que o Serena está indisponível.
- Read, Grep e Bash são o complemento: templates, `{% url %}`, referências dinâmicas, JS, CSS,
  configurações e o que o LSP não cobre. Tarefa sem código Python (documentação, template,
  estilo) não precisa do Serena.
- Com o Serena indisponível, use as ferramentas nativas e avise o usuário da limitação.
- Instalação, limites e hooks: seção "Serena" mais abaixo.

## Regra prioritária: Git e produção

Fonte completa: `deploy/FLUXO_GIT.md` (branches, tags, imagem) e `deploy/AMBIENTES.md` (ambientes
e `deploy/atualizar.ps1`). Resumo que vale para todo agente que trabalha aqui (Claude Code usa
`claude/*`; o Codex, `codex/*`; as demais regras são iguais):

- Trabalhe sempre numa branch com o prefixo do agente (`claude/<assunto>` ou `codex/<assunto>`),
  criada a partir de `develop` atualizada (`git switch develop && git pull --ff-only origin develop`,
  depois `git switch -c claude/<assunto>` ou `git switch -c codex/<assunto>`, conforme o agente),
  com `git status` limpo antes. Alterações já existentes na árvore são preservadas, nunca
  descartadas.
- Commits e pushes só na sua branch de trabalho (`claude/*` ou `codex/*`, conforme o agente).
  **Nunca** faça commit, push, merge
  local, rebase, force push, `reset --hard`, `clean -fd` nem troca de branch para apagar
  divergência em `main`, `develop` ou numa tag, nem na instalação de produção (clone em
  `C:\docker\almoxarifado-prod`, HEAD destacado numa tag, somente leitura). Essas branches só
  mudam pelo merge de um PR, e o merge é do usuário ou por ele autorizado; o agente não o faz por
  conta própria. Trazer `develop` para a sua branch (merge ou rebase dela) é permitido.
- Promoção só por PR. O fluxo normal é `claude/*` ou `codex/*` → `develop` → `main`. Squash é aceito
  nos PRs dessas branches de trabalho; entre `develop` e `main`, só merge commit. Hotfix é uma
  exceção ao fluxo normal: parte da tag implantada (`claude/hotfix-<assunto>` ou
  `codex/hotfix-<assunto>`, conforme o agente), entra em `main` por PR e depois é sincronizado
  por uma branch intermediária criada de `origin/develop`, que recebe merge de
  `origin/main` e abre PR para `develop`, com merge commit (sem squash/rebase).
  Não abrir PR com origem diretamente em `main` para essa sincronização nem usar
  “Update branch” nele: isso traria desenvolvimento para `main`. Não abra o PR de
  `develop` para `main` sem o pedido do usuário.
- Produção é por tag `vMAJOR.MINOR.PATCH` em `main` e imagem aprovada (workflow **Imagem de
  release**, referência `ghcr.io/...@sha256:...`), numa ação separada e explícita, nunca como efeito
  de um push. Não crie nem mova tag, não dispare o workflow de imagem e não rode
  `deploy/atualizar.ps1 -Aplicar` (nem `-AtivarOperacao`, `-ManutencaoConfirmada`) sem pedido
  expresso do usuário; sem `-Aplicar` o script só planeja. Nenhum `docker compose` sobre a pasta
  ou o projeto de produção por iniciativa própria.
- O Git não leva banco, `.env`, `.env.banco`, `.deploy-*`, `dados/`, perfis do navegador, logs nem
  backups. Nunca os versione (os arquivos de exemplo sem segredos, `.env.example` e
  `.env.banco.example`, são versionados e devem ser mantidos) nem imprima senhas (não envie `docker compose config` ao chat).

## O projeto

Central Almoxarifado em Django, sem nenhuma dependência do Google. Nasceu como reescrita do
sistema em Google Apps Script + Google Sheets, que já foi substituído: o Apps Script é histórico,
não referência nem requisito de compatibilidade (constituição, Princípio I). Fluxo: funcionários fazem pedidos em formulários públicos → o
almoxarifado atende → as saídas viram linhas que um robô (Playwright) lança no SCPI.

- Spec original da reescrita: `docs/superpowers/specs/2026-10-10-central-almoxarifado-django-design.md`.
  O comportamento vigente é o do código, dos testes e das specs posteriores (`specs/`,
  `docs/superpowers/specs/`); onde a spec original fala em manter o que o Apps Script fazia, é
  registro da migração. A seção 9 divide o trabalho em 5 subprojetos, cada um com plano próprio em
  `docs/superpowers/plans/`. Os subprojetos 1 (Fundação), 2 (Catálogo e importadores), 3
  (Pedidos) e 4 (Lançamento no SCPI) estão feitos; o 5 (implantação e migração) também: o
  código (app `implantacao`, `deploy/`, `LANCAMENTO_REAL`) e a instalação no servidor, que já
  roda em produção com dados reais (o roteiro foi `deploy/VIRADA.md`, migração histórica do
  Apps Script). A implantação é em Docker Compose
  (`docs/superpowers/specs/2026-10-15-docker-design.md`), no lugar do NSSM e do Agendador do
  Windows da spec principal; o ambiente confirmado é Windows 10 com Docker Desktop compartilhado
  (`deploy/INSTALACAO.md`, `deploy/AMBIENTES.md`). Do 4 ainda falta a
  simulação contra o SCPI real (João roda `lancar_saidas --dry-run --lote <número>`).
- Origens fora deste repositório, só para consulta histórica: o Apps Script
  (`../CentralAlmoxarifado`, com `Regras.gs`, `Catalogo.gs` e os testes em Node; nomes como
  `normU_` nas docstrings apontam para ele), o WMS-Almoxarifado
  (`joaorighetto/WMS-Almoxarifado`), de onde veio a fundação visual, e o extrair-relatorio
  (`joaorighetto/extrair-relatorio`, privado), de onde veio o código do SCPI.

## Comandos

Exigem um MySQL 8 ou MariaDB local (o SQL de criação do banco e do usuário está no README) e
um `.env` copiado de `.env.example`.

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
uv run pytest                                   # suíte inteira
uv run pytest tests/test_acesso.py::test_painel_exige_login   # um teste
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
uv run playwright install chromium              # uma vez, para os robôs do SCPI
uv run python manage.py importar_estoque --arquivo tests/fixtures/scpi/estoque.csv
```

`uv run python manage.py lancar_saidas --dry-run --lote P-0123` abre o SCPI, preenche essa
requisição pendente e a descarta sem salvar (`--lote` é obrigatório e se repete: o comando nunca
lança a fila inteira sem escolha); **sem `--dry-run` lança de verdade no SCPI**, e só
com `LANCAMENTO_REAL=1` no `.env` (sem ele, o comando recusa).

Comandos da implantação (app `implantacao`): `backup_banco` faz o dump
comprimido em `BACKUP_DIR` e apaga os de mais de 60 dias (a senha vai num arquivo de opções
temporário, `--defaults-extra-file`, nunca nos argumentos nem no ambiente); `robos_em_andamento` sai com erro se há
lançamento ou importação em andamento (o `deploy/atualizar.ps1` o usa);
`importar_depara --arquivo <xlsx> [--dry-run]` carrega os pares de/para da planilha MAPEAMENTO
DE/PARA CONSOLIDADO (carga única). No servidor os comandos rodam no container
(`docker compose ... exec web python manage.py ...`), não pelo `uv run`, sempre com o projeto e os
arquivos do ambiente explícitos (`deploy/AMBIENTES.md`). Em produção, só a pedido do usuário.

Os comandos `importar_cadastro`, `importar_estoque`, `importar_saidas_scpi` (`--desde`/`--ate`)
e `atualizar_catalogo` (os três em sequência, num navegador só; com `--carga-inicial`, o cadastro
inteiro e as saídas desde `curva.INICIO_DADOS_CONFIAVEIS`, também no botão "Carga inicial
completa" da página Automações) abrem o SCPI pelo Playwright; com `--arquivo`
leem um CSV já baixado. Os testes nunca abrem o navegador.

O pytest usa `config.settings_test` (definido no `pyproject.toml`) e cria o banco
`test_almoxarifado`. Testes rodam contra MySQL/MariaDB, nunca SQLite: `select_for_update` e
transações precisam se comportar como no servidor.

## Arquitetura

- `config/settings.py` é um módulo único para todos os ambientes, lido do `.env`
  (`python-dotenv`; variável já presente no ambiente vence) via `config/env.py`
  (`ler_bool`, `ler_lista`). Com `DEBUG=0` ligam as proteções de produção e
  `check --deploy` precisa passar sem avisos (há um teste para isso). `settings_test.py` só
  ajusta hasher, cookies seguros e storage de estáticos.
- A área interna (login, painel, automações, curva ABC e saída avulsa) fica em
  `/painel/`, e o admin em `/admin/`; os formulários públicos ficam na raiz. Os nomes das rotas
  não mudam (as páginas Catálogo e Lançamentos SCPI foram apagadas, com suas rotas, quando viraram
  Automações). O login é `/painel/entrar/`. O site pode sair sob um prefixo (`PREFIXO_URL` do
  `.env`, vazio na raiz; `/almoxarifado` era a proposta antiga com Apache, que não é a topologia
  verificada hoje: o acesso atual é HTTP direto e não há Apache nem HTTPS confirmados). O prefixo
  vem de duas pontas que precisam bater: o `--url-prefix=${PREFIXO_URL}` do waitress (que passa
  `SCRIPT_NAME` a cada pedido) e o `PREFIXO_URL` do `.env`, que vira `FORCE_SCRIPT_NAME` e o
  `STATIC_URL`. O `STATIC_URL` é lido na partida, antes de qualquer pedido: só com o
  `--url-prefix` os links dos estáticos sairiam sem o prefixo e quebrariam. Nenhum template tem
  caminho fixo (`tests/test_prefixo.py`). Guias: `deploy/INSTALACAO.md` e `deploy/AMBIENTES.md`.
- A variável que liga o HTTPS se chama `USAR_HTTPS`, nunca `HTTPS`: o wsgiref do `runserver`
  copia `os.environ` para a requisição, e `HTTPS=1` faria tudo parecer https e quebraria o
  CSRF. Atrás de um proxy HTTPS, o waitress precisa de
  `--trusted-proxy=<proxy> --trusted-proxy-headers="x-forwarded-proto x-forwarded-for"`
  (no compose, `<proxy>` é `*`: o proxy chega por um IP interno do Docker que muda, e isso só é
  seguro porque a porta publicada fica em loopback e só o proxy a alcança; nunca publique o
  backend direto na rede) junto com `PROXY_HTTPS=1`: sem o primeiro cabeçalho o redirecionamento
  para https entra em laço; sem o segundo, todo pedido parece vir do proxy e divide um único
  limite por IP.
- `contas.Usuario` é o `AUTH_USER_MODEL`: `AbstractUser` com o `username` rotulado
  "matrícula". O login (`/painel/entrar/`) e o login do admin usam formulários próprios
  (`contas/forms.py`) só para a recusa sair em português correto.
- `interface` é só apresentação (sem modelos nem regras), no design system Clean (skill
  `.claude/skills/clean-design/`; regras e vocabulário de classes em `docs/DESIGN.md`):
  `clean.css` (tokens, fontes, tipografia e os ritmos `ritmo-publico`/`ritmo-almox`),
  `componentes.css` e `layouts.css`, ícones Lucide em `_icone.html`, fontes `.woff2` locais
  (Geist, DM Sans, Geist Mono), HTMX 4.0.0 vendorizado, parciais e template tags. Só tema
  claro; o `shell.js` só cuida do menu móvel. O `dropdown.js` troca todo `select.campo-entrada` e
  `input.campo-entrada[list]` por um painel no estilo do de resultados da busca de materiais, sem
  caixa de busca (no `select`, digitar pula para a opção que começa com o texto); é a base de todo
  painel flutuante: a casca (`.painel-flutuante`, em `componentes.css`) e o abrir e fechar animados
  (`window.Dropdown.abrirPainel`/`fecharPainel`) também servem ao painel de resultados da busca de
  materiais (`pedidos.js`), e os tipos (select, campo com lista, select digitável, árvore) só montam o controle; o
  elemento original fica escondido e continua guardando o valor e disparando `change` (script
  que troca o valor de um `select` precisa disparar `change`). O `abas.js` (`[data-abas]`, `?aba=` na URL) dá as abas em pasta: a ativa se funde ao primeiro cartão
  do painel. O `filtros.js` recolhe o painel de
  um `form[data-filtros]` (filtros do painel de pedidos e do histórico de Automações): botão com a contagem, estado lembrado no
  `localStorage` e, fechado, um chip por filtro ativo; sem JavaScript o painel fica aberto. Dois layouts: `base_publico.html` (sem login,
  pensado para o celular) e `base_almoxarifado.html` (barra lateral), os dois com o bloco `voltar`
  (`link-voltar`, acima do rótulo; no almoxarifado, "Voltar ao painel" por padrão, vazio no painel). Cada subprojeto
  acrescenta seus destinos (com ícone) a `ITENS_MENU` em `interface/navegacao.py`. Scripts
  ficam no `<head>` com `defer`, nunca no `<body>` (o HTMX re-executa scripts do corpo ao
  restaurar o histórico).
- `pedidos/regras.py` guarda as regras de negócio: funções puras, sem ORM. Vieram de
  `Regras.gs`/`Util.gs`, mas o módulo e os seus testes são a referência e mudam como qualquer
  regra, sem compromisso de equivalência com o Apps Script. Quantidades são `Decimal` (pt-BR
  estrito, "1.5" é recusado).
- `pedidos/servicos.py` é o único lugar que grava pedidos: `registrar_pedido`,
  `confirmar_atendimento`, `registrar_saida_avulsa` e `marcar_recibos_impressos`, cada um numa
  transação. Todo registro trava a linha única da `Sequencia` (`select_for_update`), que numera
  P- e AV- juntos e serializa os envios; o atendimento trava o pedido. O `Pedido.id` é o
  identificador do envio, gerado quando a página abre: reenvio igual confirma, diferente é
  "divergente", e nada duplica. Erro de negócio volta numa `Resposta` com a lista de erros. O
  aviso no Telegram (`telegram.py`) sai por `transaction.on_commit` e nunca desfaz o pedido.
- Formulários públicos (`views/publico.py`): token assinado com o envio e o momento da
  abertura, campo isca e tempo mínimo (`protecao.py`: `recusar` devolve o motivo; token inválido e envio
  rápido demais ganham mensagem humana, com os dados mantidos, só a isca recebe a genérica, e o
  token não expira); limites por IP e por nome contados no banco (`settings.PEDIDOS_*`, o limite
  por nome vale para toda origem que não é a avulsa, `regras.origem_publica`). O JavaScript é
  requisito dos formulários públicos: sem ele, só o aviso do `<noscript>` aparece
  (`html:not(.js) .formulario-pedido` esconde o formulário). O envio vai pelo HTMX e a resposta substitui o formulário; o
  `htmx-config` do `base.html` impede que respostas 4xx/5xx apaguem a página. Busca de
  materiais e carrinho (`fluxos.py`, `carrinho.py`, `views/materiais.py`) são comuns a limpeza,
  AB e saída avulsa: o carrinho vive em campos escondidos e o servidor não guarda estado. A busca
  lista primeiro o que pode ser pedido e os bloqueados no fim, antes do corte de 50. A quantidade segue a **unidade do material**, igual nos dois
  formulários públicos (spec 005): a unidade fracionável (lista `Opcao.Lista.UNIDADE_FRACIONAVEL`,
  mantida no admin e carregada pela migration `catalogo/0002` com `M`, `MT`, `MTS`, `KM`, `KG`, `L`,
  `LT`, `M²`, `M³` e `T`; lista vazia = tudo inteiro) aceita até 3 casas; as demais, e o material
  sem unidade, só inteiro, e a fração é recusada na hora (`regras.interpretar_quantidade`, com um
  texto por causa em `texto_erro_quantidade`, o mesmo ao adicionar, alterar e enviar).
  `ItemCatalogo.fracionavel` vem da unidade do SCPI (a do código canônico no AB), nunca da unidade
  exibida da limpeza. O estoque exibido ("Estoque N · UN"), o teto de adicionar e alterar
  (`carrinho.limite`), a validação do envio (`regras.validar_pedido`, uma só para os dois) e o texto
  "Estoque disponível" são o mesmo número, `regras.maximo_pedivel`: o saldo truncado a 3 casas (para
  unidade contada, a parte inteira), sem zeros à direita (`regras.qtd_br`); material com máximo 0
  aparece bloqueado ("Sem estoque") e o envio o recusa. A equipe (atendimento e saída avulsa,
  `Fluxo.regra_quantidade == "livre"`) aceita fração em qualquer unidade, com o teto no saldo
  truncado a 3 casas, e o aviso do Telegram e o campo de entrega mostram a quantidade exata. Formulário
  com o saldo nunca importado (`catalogos.saldo_importado`) ou sem item algum fica indisponível, com
  a mesma mensagem nos dois, e vira aviso de saúde (`saude._demais`); com itens e todos sem estoque,
  abre com o aviso `sem_estoque_agora` no topo. Recusa por item devolve o pedido inteiro, com a linha
  ilegível mantida e marcada "Corrigir" (`carrinho.ler(manter_ilegiveis=True)`). Cada formulário é
  uma entrada de `FLUXOS` (`Fluxo`: `catalogo`, `exemplo_busca`, `exemplo_inicio`,
  `exemplo_destino`, `rotulo_destino` ("Número da viatura" nas viaturas), `icone`, `publico`,
  `regra_quantidade` e, opcionais, `folha`, `centros`,
  `pede_ocorrencia`, `geral` e `titulo_inicio`; o AB é o formulário `geral`, para o que não se
  encaixa nos outros: na página inicial vem à parte, depois da pergunta "Seu material não se
  encaixa…", com o `titulo_inicio` "Ferramentas, peças e outros materiais", que só vale ali; contratos em
  `specs/005-consistencia-formularios-publicos/contracts/configuracao-fluxo.md` e
  `specs/006-reposicao-pecas-viaturas/contracts/configuracao-fluxo.md`): um formulário novo é uma
  entrada, uma função `formulario_*` em `catalogos.py` e um valor em `Pedido.Origem` (migration de
  `choices`), sem mexer no núcleo. `registrar_pedido` lê o catálogo e os centros
  (`servicos.centros_do_fluxo`) antes de travar a `Sequencia`. Para o funcionário, os formulários
  se chamam "Limpeza, copa e escritório", "Ferramentas, peças e materiais", "Reposição de peças das
  viaturas" e "Oficina mecânica" (`Fluxo.titulo`); o nome interno (painel, Telegram, `Pedido.Origem`) do segundo continua
  "Materiais AB", e o rótulo do Telegram é o da origem (`get_origem_display`). `regras.Erro` tem
  `campo` (`solicitante`, `destino`, `obs`, `ocorrencia`) nos erros de um campo:
  a view monta `erros_por_campo`, e o formulário mostra o resumo no topo (focado pelo `pedidos.js`,
  com link para o campo) e o erro embaixo do próprio campo. No celular, a gaveta do pedido envia
  (`data-carrinho-enviar`, que aciona o botão do fim do formulário por `requestSubmit`; esse botão
  fica escondido com JavaScript), também na saída avulsa, com os textos da
  saída (`Fluxo.rotulo_carrinho` e afins: "Materiais da saída", "Revisar e registrar"). O "Nome completo" é texto livre, sem sugestões de nomes. O `pedidos.js`
  lembra no `localStorage` do aparelho (`almoxarifado.solicitante`) o último nome digitado (gravado
  ao digitar) e o destino do último pedido registrado (gravado pela tela de sucesso,
  `data-lembrar-*`), preenche só campos vazios e pede confirmação (`beforeunload`) para
  sair com material no pedido. Nos formulários públicos e na saída avulsa, adicionar tem dois passos
  (`[data-adicionar]` em `_resultados.html`): tocar na linha do material (o `material-abrir`, um botão
  transparente esticado sobre a linha; o "+" só indica que clica) abre a quantidade, que se confirma
  (o `hx-post` de sempre) ou, com o material já no pedido (selo azul claro "N no pedido" ao lado da
  informação, `data-selo-pedido`), "Atualizar" troca a linha do pedido; tocar de novo na linha aberta a
  fecha. Aberta, a linha mostra a quantidade à esquerda e o "Confirmar" no canto inferior direito, com o
  ✕ vermelho no superior direito; as outras linhas recuam (opacidade 0,6) mas seguem clicáveis. A
  informação do material quebra por dentro e o selo desce para a linha de baixo quando a unidade é
  longa (limpeza). O painel do atendimento (`um_passo`) adiciona ou troca direto, com botão. A coluna do `.passo-corpo` é `minmax(0, 1fr)`, para a busca não
  alargar com o conteúdo. O painel de resultados fica no fluxo da página, em qualquer tela (nunca
  absoluto: o cartão do passo cresce com ele, sem painel pendurado para fora); ao abrir, o pedidos.js
  rola o campo ao topo (`trazerAoTopo`, descontando a barra do topo no celular) e dá ao painel a altura
  do cabeçalho e de 5 linhas (`alturaDoPainel`, `LINHAS_VISIVEIS`, `--busca-limite`), a mesma no
  computador, no tablet e no celular, medida de novo quando os resultados ou a largura mudam; o resto
  rola dentro do painel. Há duas buscas de materiais: a pública (formulários) não mostra código nem
  grupo; a do almoxarifado (saída avulsa e atendimento) mostra. A linha do pedido
  (`_carrinho.html`) tem o mesmo desenho do resultado da busca, na coluna do desktop, no tablet e na
  gaveta do celular: a linha inteira abre a quantidade (`material-abrir`, `data-alterar-abrir`; o lápis
  só indica que clica), com a quantidade e o "Remover" embaixo; aberta, o − / + fica à esquerda, o
  "Confirmar" à direita (no lugar do "Remover") e o ✕ vermelho em cima, com a barra azul à esquerda e as
  outras linhas recuadas, mas clicáveis. O campo só manda o `alterar` no "Confirmar"
  (`hx-trigger="confirmar-quantidade"`), também na saída avulsa.
- Área do almoxarifado (`views/almoxarifado.py`): painel com filtros em SQL
  (`consultas.py`, que repete `regras.situacao_*` como `Exists`; um teste confere que
  concordam), detalhe com o atendimento, saída avulsa e recibos (`_recibo.html`, que nunca
  mostra quem registrou). Não há página de recibos: o "Imprimir recibo" do detalhe imprime a própria
  página (`data-imprimir`, escondido sem JavaScript) e, depois, mostra ali a confirmação de impresso
  (`marcar_impressos`); o atalho do painel filtra os não impressos (`?recibo=pendente`). Cada material entregue vira uma `LinhaSaida` (`PENDENTE`, ou
  `NAO_LANCAR` com a opção marcada): é o contrato com o robô do subprojeto 4. Na área interna a
  unidade é a do cadastro do SCPI (`consultas.unidades_scpi`), nunca a unidade exibida do
  formulário de limpeza (`ItemPedido.unidade`, que só vale para código fora do cadastro), e vai
  dentro do campo da quantidade entregue. Com JavaScript, cada quantidade entregue é confirmada
  ("Confirmar" ou Enter; o − e o + somem e a própria caixa, com um lápis, vira o "Alterar", com o lugar do "Confirmar" guardado; inválida não confirma, e acima do pedido confirma com o aviso âmbar da parcial, até o maior entre o pedido, o saldo e o que já está gravado (`servicos.tetos_de_entrega`, também no `data-maximo` do campo: acima dele, o estado "máximo" não confirma);
  "Entregar tudo" preenche e confirma) e o `pedidos.js` barra o envio com alguma pendente.
  No atendimento, o almoxarifado troca um material pedido por outro ou acrescenta um
  (`ItemPedido.origem` `PEDIDO` ou `ALMOXARIFADO`; o acrescentado tem `qtd_pedida` nula,
  `adicionado_por` e, na troca, `no_lugar_de`, e o trocado fica com 0 sem deixar o pedido parcial),
  do catálogo da saída avulsa (só material não oculto e com saldo > 0, `catalogos.materiais_avulsa`),
  com a quantidade limitada ao saldo do cadastro truncado a 3 casas, em qualquer unidade
  (`maximo_pedivel` com a regra `livre`; `ItemSaida.estoque` em `regras.validar_saida`, e
  `carrinho.limite` na
  resposta imediata do carrinho e do "Adicionar"). Na edição (`servicos._limites_de_estoque`) o teto
  de quem já está gravado é o maior entre o saldo e a quantidade gravada: o SCPI pode ter abatido o
  saldo, ou o material ter saído do catálogo, e a edição não o recusa, só não deixa subir. A busca (`atendimento_materiais`) e o
  "Adicionar" (`atendimento_adicionar`, que devolve a linha `_adicionado.html` ou a recusa para
  `#adicionar-erro`) não gravam nada: as linhas vivem em campos escondidos do formulário do
  atendimento (`adicionado`, `no-lugar-de-<codigo>`) e só o envio grava. O `pedidos.js` abre o
  painel de busca embaixo do material trocado, zera e confirma o trocado já ao abrir a troca (o "Cancelar troca" devolve a quantidade e a confirmação; a quantidade de antes
  fica em `data-qtd-antes`, para o "Desfazer troca"; até lá o trocado fica travado, sem o lápis,
  e "Entregar tudo" o pula; o servidor também recusa trocado com quantidade maior que 0),
  anuncia cada mudança no `role="status"` da
  tabela e reaplica tudo na página devolvida pela recusa. O recibo separa "Pedido pelo solicitante"
  de "Adicionado pelo almoxarifado" e nunca mostra quem acrescentou. Três travas contra linha de
  saída com quantidade ≤ 0: `servicos._gravar_linhas`, `scpi/requisicoes.py` (lote vira `ERRO`) e
  a `CheckConstraint` `qtd > 0` da `LinhaSaida`.
- Edição do atendimento (spec `2026-10-17-edicao-pedido-design.md`): até o robô lançar o lote, o
  "Editar atendimento" ("Editar saída" na avulsa) do detalhe abre `pedidos:editar`
  (`/painel/pedidos/<n>/editar/`), o formulário do atendimento (ou o da saída avulsa) preenchido
  com o que está gravado (`editando`). Edita só o que o atendimento grava (dados da saída,
  quantidades entregues, trocas e acréscimos); o que veio do funcionário (cabeçalho, materiais e
  quantidades pedidas) nunca muda. `regras.edicao_permitida` (puro) diz pelas linhas do lote se
  edita (`PENDENTE`, `NAO_LANCAR`, `ERRO` sem número), se está suspensa (`EM_LANCAMENTO`,
  `VERIFICAR`) ou bloqueada (lançada ou com número). `servicos.editar_atendimento` e
  `editar_saida_avulsa` travam o pedido e as linhas, conferem a `Pedido.versao` (concorrência
  otimista: outra pessoa salvou antes é recusa `versao`; o reenvio igual é sucesso), recusam o lote
  que entrou em lançamento (`lancamento`), validam como o atendimento, gravam a `AlteracaoPedido`
  (diferenças de `regras.diferencas_atendimento`, só na tela, nunca no recibo), devolvem o recibo a
  "não impresso" e **apagam e recriam as `LinhaSaida`**: com IDs novos, o robô que leu o lote antes
  da edição o pula no `_travar`; nunca atualize as linhas no lugar. `ERRO` volta a `PENDENTE`. O
  "Saiu na impressora" leva a versão (`versao-<atendimento>`) e não marca a versão nova. No modo de
  edição o `pedidos.js` abre as quantidades confirmadas, destaca o campo alterado, conta as
  alterações e pede confirmação para sair; com o robô rodando, a faixa (`_edicao_faixa.html`,
  `div#edicao-faixa` pelo `HX-Target`) se recarrega a cada 5 s e, se o lote travar, tira o
  "Salvar".
- Reposição de peças das viaturas (spec `specs/006-reposicao-pecas-viaturas/`): o formulário
  público `FLUXOS["viaturas"]` (origem `VIATURAS`, `/pedido/viaturas/`), para o encarregado da
  equipe de manutenção. O catálogo (`catalogos.formulario_viaturas`) é a lista `PecaViatura` (uma
  linha por material, `OneToOne` com `PROTECT`, nome exibido opcional e ordem; o quadro "Materiais"
  da folha em papel) seguida do catálogo AB sem repetir códigos; a peça da lista aparece mesmo fora
  do AB, e a unidade é sempre a do SCPI. A lista é preenchida numa **folha**: o botão "Preencher a
  lista de peças" pede ao endpoint do carrinho `folha_abrir` e abre o `<dialog id="folha">` (dentro
  do `<form>`) com `_folha.html`; "Pôr no pedido" manda `folha=1` e os `folha-<código>`, e
  `carrinho.aplicar_folha` (pura) aplica **tudo ou nada**: linha preenchida substitui a quantidade,
  vazia ou zero tira do pedido, o que veio da busca não muda; com erro, a resposta é a própria folha
  (`HX-Retarget: #folha-conteudo`) com o erro por linha, e sem erro é o carrinho com
  `HX-Trigger: folha-aplicada` (o `pedidos.js` fecha o diálogo e anuncia). Os destinos são só os
  centros habilitados nas viaturas na página Formulários, sem placa (modo `sem_placa` de
  `catalogos.centros_do_formulario`, pelo `Fluxo.centros`; antes era a marca `equipe_manutencao`,
  transcrita pela migration `catalogo/0007`, spec 009); sem nenhum habilitado, o formulário fica
  indisponível. `Pedido.ocorrencia`
  (até 20 caracteres, opcional, só onde `Fluxo.pede_ocorrencia`) entra na conferência de reenvio
  (`cabecalho_enviado` das origens públicas tem 4 campos), aparece na tela de sucesso, no detalhe, no
  recibo e na lista do painel e é achada pela busca do painel; não vai no Telegram nem muda na edição. A saúde do
  catálogo (`saude._viaturas`) diz quanto o formulário oferece ou por que está indisponível.
- Formulário da oficina mecânica (spec `specs/007-formulario-oficina-mecanica/`): o formulário
  público `FLUXOS["oficina"]` (origem `OFICINA`, `/pedido/oficina/`), pedido de autopeças e insumos
  da oficina, sem folha nem ocorrência; o único campo novo no `Fluxo` é `exemplo_destino`, o
  placeholder do destino (antes deduzido de `fluxo.centros`). O catálogo
  (`catalogos.formulario_oficina`) são os materiais visíveis dos grupos da lista `Opcao`
  `GRUPO_OFICINA` ("Grupos (oficina)", comparados por `_grupo`, como os ocultos do AB; lista vazia =
  nenhum grupo) mais os avulsos (exceções da configuração, spec 009: antes um cadastro
  `MaterialOficina`, que ficou no banco, sem valer; servem aos óleos e filtros do grupo `GERAL`, que
  não entra inteiro), uma vez cada, pelo nome, com a regra de quantidade e de estoque dos
  formulários públicos. Os destinos (modo `oficina` de `catalogos.centros_do_formulario`) são o centro
  `OFICINA MECÂNICA` (`regras.CENTRO_OFICINA`, o mesmo de `resolver_centro_custo`) e cada centro com
  placa, este só como "centro — placa": `regras.Centro.so_com_placa` tira a descrição sozinha de
  `opcoes_destino` (padrão `False`, os outros formulários não mudam). O atendimento já
  sugere centro e placa pelo destino (`_saida_do_destino`). A saúde (`saude._oficina`) diz quanto o
  formulário oferece, por que está indisponível, os grupos sem material visível, os avulsos ocultos
  e a falta do centro da oficina; a visão geral de Automações mostra a contagem
  (`Situacao.oficina`).
- Formulário de EPIs, com autorização da Segurança do Trabalho (spec `specs/008-formulario-epis/`):
  `FLUXOS["epis"]` (origem `EPIS`, `/pedido/epis/`, ícone `escudo`) é o primeiro com
  `Fluxo.exige_autorizacao`. O pedido nasce com uma `AutorizacaoPedido` (`AGUARDANDO`, na mesma
  transação; os outros formulários não têm a linha) e só quem é da Segurança do Trabalho a decide,
  uma vez e para sempre: `AUTORIZADO`, ou `RECUSADO` com motivo (`servicos.decidir_autorizacao`: trava
  o pedido, a primeira decisão vale, a segunda devolve quem decidiu e quando; `CheckConstraint` no
  banco). **Solicitar não é fornecer**: o sistema nunca baixa estoque, e `confirmar_atendimento`
  recusa o pedido não autorizado antes de gravar (nenhum `Atendimento` nem `LinhaSaida`, logo o robô
  nunca o vê); a tela do detalhe e os endpoints de busca e acréscimo do atendimento espelham. Nenhum
  dado extra de EPI (CA, tamanho, motivo) no pedido: está fora do escopo. `regras.situacao_pedido(...,
  autorizacao)` ganha `aguardando_autorizacao` e `recusado`; `filtrar_situacao("aguardando")` exclui
  os dois (o atalho "Atender" só conta o atendível) e o painel tem o filtro Autorização, à parte da
  situação; o recibo não muda. O catálogo é `Opcao.Lista.GRUPO_EPI` mais os avulsos, que desde a spec 009 são exceções da
  configuração (o cadastro `MaterialEpi` ficou no banco, sem valer), como o da oficina
  (`catalogos.catalogo_epis`, `saude._epis`, `Situacao.epis`).
  **Acesso**: o grupo `Segurança do Trabalho` (criado por migration de dados de `contas`; o acesso é
  participar do grupo, nunca `is_staff`, e o administrador o dá no formulário do usuário no admin) e o
  `contas.middleware.RestringirSegurancaTrabalho`, que em `process_view` **nega por padrão** tudo o
  que não está em `contas.acesso.ROTAS_SEGURANCA_TRABALHO` (GET redireciona à fila; os outros métodos
  dão 403); as views existentes não mudam, e `tests/test_epis_acesso.py` percorre todas as rotas
  nomeadas do projeto. Rota nova que o grupo deva abrir entra nessa constante. O menu (`ItemMenu.para`)
  e a marca mudam para ele. Telas em `views/autorizacao.py`: `/painel/autorizacoes/` (fila e já
  decididos), `<numero>/` (leitura e decisão) e `<numero>/decidir/`, com 403 para quem não é do grupo
  também sem o middleware. **Avisos**: ao registrar, só o chat `TELEGRAM_CHAT_ID_SEGURANCA` (botão
  "Abrir fila"; `telegram.notificar_autorizacao_pendente`); ao autorizar, o `TELEGRAM_CHAT_ID` de
  sempre; recusa e pedido aguardando não avisam o almoxarifado; falha nunca desfaz nada. **Consulta
  pública** `/pedido/epis/consulta/` (`publico.consulta_epi`, POST com CSRF, `never_cache`): mostra só a
  situação e o motivo da recusa, responde igual a número inexistente e a número de outro formulário e
  limita por origem no cache do Django (`PEDIDOS_CONSULTA_LIMITE_IP_10_MIN`, zera ao reiniciar). É a
  exceção ao desenho de o número do pedido não virar página pública; exigir também o nome completo
  foi proposto e **não adotado** (decisão do usuário). A spec lista as pendências de validação
  normativa (NR-6) que o sistema não resolve.
- Configuração das opções por formulário (spec `specs/009-configuracao-formularios/`): a página
  **Formulários** (`/painel/catalogo/formularios/`, `catalogo:formularios`, `views_formularios.py`,
  item do menu) diz, para cada um dos cinco formulários públicos (`catalogo.models.Formulario`, os
  valores de `Pedido.Origem`; a saída avulsa não entra), quais centros de custo são destino e quais
  materiais são oferecidos. **Centros**: `CentroCusto.ativo` (global) e `CentroFormulario` (a linha do
  cadastro, centro mais placa, é destino do formulário; a presença da linha basta). `Fluxo.centros` das
  cinco entradas públicas é `partial(catalogos.centros_do_formulario, ORIGEM)`, que lê as linhas ativas
  e habilitadas e as apresenta pelo **modo de destino** do formulário (`MODO_DESTINO`: `padrao` em
  limpeza, AB e EPIs; `sem_placa` nas viaturas; `oficina`), característica do formulário, não
  configurável. A saída avulsa segue com `centros=None`. **O inativo some só dos formulários públicos e
  da saída avulsa nova** (`servicos.centros_ativos`, `opcoes_saida(so_ativos=True)`,
  `_validar_saida_avulsa(so_ativos=True)`); `servicos.centros()` devolve todas as linhas e é o que o
  atendimento, a edição (também de saída avulsa já registrada) e o robô do SCPI usam, para pedido e lote
  pendente nunca travarem. Centro novo nasce ativo e **sem formulário** (a saúde avisa). **Materiais**:
  `ExcecaoMaterial` (material e formulário únicos; `habilitado` verdadeiro acrescenta, falso retira)
  é uma camada **sobre a regra de origem**, que continua nas funções de `catalogos.py` (lista de
  limpeza, curva ABC do AB, lista das viaturas mais o AB, grupos da oficina e dos EPIs: estes dois, só
  os grupos). Sem exceção, vale exatamente a regra de antes (o AB segue calculado); a disponibilidade
  efetiva, `(regra − retirados) ∪ acrescentados` sem os ocultos, é calculada (`aplicar_excecoes`,
  `catalogo_efetivo`; `disponibilidade.estado` é a regra pura), nunca guardada. `formulario_*` devolve a
  base com as exceções, então busca, carrinho e `validar_pedido` validam contra ela sem mudar. Os
  acrescentados vêm ao fim, em ordem alfabética (oficina e EPIs, na ordem do banco); `oculto` nunca
  entra e `duplicado` aparece bloqueado; estoque, teto e regra de quantidade seguem como eram.
  Serviços em `catalogo/disponibilidade.py` (`definir_excecao`, `aplicar_em_lote` atômico e em blocos,
  `habilitar_centros`, `definir_ativo`, `restaurar_regra`: restaura a regra padrão de um formulário, apagando todas as suas exceções de material, em dois passos na aba Materiais, `formularios_regra`); o `bulk_create(update_conflicts=True)` no MySQL/MariaDB não
  aceita `unique_fields`, e o `update_or_create` falha na corrida (duas gravações simultâneas deixam uma
  linha). A tela tem as abas Centros de custo e Materiais (busca, grupo, subgrupo e estado; 50 por
  página no servidor), o **lote em duas telas** (`formularios_lote`: prévia com número exato, POST com o
  `total` visto, recusa se o filtro mudou, "ciente" sem filtro), a consulta **por material**
  (`formularios_material`) e as gravações em POST, mensagem e redirecionamento. **Permissões**: ver é
  de todo usuário do almoxarifado; gravar exige `is_staff` mais `catalogo.change_centrocusto` (centros)
  ou `catalogo.change_excecaomaterial` (materiais), recusado com 403 no servidor
  (`catalogo/acesso.py`); a Segurança do Trabalho é negada pelo middleware (rotas fora da lista). A
  migration `catalogo/0007` (a 0006 é só o esquema, separada porque o DDL do MySQL não é transacional)
  transcreve as regras antigas (todos os centros em limpeza, AB e EPIs; as
  linhas de `equipe_manutencao` nas viaturas; a linha sem placa de OFICINA MECÂNICA e as com placa na
  oficina; `MaterialOficina` e `MaterialEpi` como exceções que acrescentam) e **se verifica**: levanta
  erro se um formulário não oferecer o mesmo; nada é apagado, e `equipe_manutencao`, `MaterialOficina`
  e `MaterialEpi` ficam no banco, sem valer. `tests/regra_antiga.py` é a cópia congelada da regra
  anterior (referência de `test_config_equivalencia.py`); nos testes, `tests/config_cenario.py`
  (`criar_centro`, `habilitar`, `excecao`) e `montar_cenario` habilitam os centros como as regras
  antigas ofereciam. A saúde avisa formulário sem destino, centro ativo sem formulário (por linha),
  exceção sem efeito e formulário esvaziado por exceções. A aba Centros mostra em quais outros
  formulários cada linha é destino e leva ao admin para criar e editar o centro.
- `catalogo` guarda os cadastros. `Material` e `SaidaSCPI` vêm do SCPI pelos importadores e
  são só leitura no admin, como o registro de cada execução (`Importacao`). `ItemLimpeza`,
  `PecaViatura`, `CentroCusto` (com o estado `ativo`) e `Opcao` são mantidos à mão no
  admin; os avulsos da oficina e dos EPIs e a marca de equipe de manutenção saíram do admin (spec 009).
  A placa do `CentroCusto` é normalizada
  (`norm_placa`), única no banco, e vazia vira NULL. `catalogos.py` monta os catálogos dos
  formulários (limpeza, AB pelo número de saídas consolidadas pelo de/para, avulsa) direto do
  banco, sem cache;
  `saude.py` diz o que está errado ou velho: `saude_do_catalogo` é a lista curta do painel e
  `situacao_do_catalogo` a mesma informação arrumada para a visão geral de Automações (uma linha
  por fonte de dados em colunas com cabeçalho: selo, fonte, o número em uso com o `complemento` mais
  apagado, "há quanto tempo" e uma ação, que leva aos avisos ou à aba do robô, "Tentar de novo" quando
  falhou; os avisos agrupados pelo começo do texto com
  `agrupar_avisos` e os números dos formulários; o erro inesperado do
  Playwright vira uma frase, `resumo_do_erro`, com o texto técnico recolhido). A visão geral tem o
  botão "Atualizar agora" (que inicia `atualizar_catalogo` em processo separado) e, recolhida, a
  carga inicial completa, que só inicia com a caixa "Estou ciente" marcada (`confirmar`). Cada robô
  de importação (Cadastro, Estoque, Saídas) tem sua aba em Automações, com um formulário de
  parâmetros (`catalogo/forms.py`: origem "baixar do SCPI" ou CSV enviado; no
  cadastro, o modo "só os novos" ou "recarga completa", com o "forçar" só se há material visível; no
  das saídas, o período). `automacoes.views.importar` valida e chama
  `scpi.disparo.iniciar_importacao`, que roda o comando do tipo em processo separado, com log próprio
  (`importar_<tipo>.log`) e uma importação por vez; o CSV enviado vai para `LOG_DIR/uploads` e o
  comando o apaga ao fim (`--apagar-arquivo`, mesmo se falhar). Os formulários ficam fora do trecho
  que o HTMX recarrega; o `importacoes.js` segue o `data-em-andamento` da situação para habilitar os botões.
- `automacoes` (sem modelos nem migrations) é a página Automações (`/painel/automacoes/`,
  `automacoes:pagina`), que junta o que eram as páginas Catálogo e Lançamentos SCPI: abas
  (`interface/js/abas.js`, `?aba=`) Visão geral, Lançamento no SCPI, Cadastro, Estoque e Saídas. A
  view só lê: `contexto_pagina` junta `contexto_catalogo`, `contexto_lancamento`, a linha do
  lançamento na visão geral (`visao_geral.linha_lancamento`, pura, ao lado das `saude.Fonte`) e o
  histórico; os parciais continuam em `catalogo/_situacao.html`, `catalogo/_robo.html` e
  `pedidos/_lancamentos.html`. As regiões que se recarregam sozinhas (situação a cada 5 s, também
  enquanto o lançamento roda; lançamento a cada 3 s; histórico a cada 5 s com a mesma query) pedem a
  própria página, e a view escolhe o trecho pelo cabeçalho `HX-Target` do HTMX 4 (`tag#id`,
  `REGIOES`). As ações (`atualizar`, `importar`, `lancar`, `resolver`) ficam aqui, com o mesmo corpo de
  quando eram das páginas antigas, e voltam para a aba de onde vieram. O histórico (`historico.py`)
  junta `Importacao` e `ExecucaoRobo`: filtros em SQL por modelo (`FiltrosHistorico`: busca no erro,
  nos avisos e no registro; robô; situação num vocabulário só, Concluída, Com avisos, Falhou,
  Interrompida e Em andamento, com "sem avisos" comparado como texto `"[]"`; período), e
  `SequenciaHistorico` intercala as duas por início e serve ao `Paginator` de 20; os filtros são
  os do painel (`filtros.js`) e cada aba tem "Ver histórico", que abre a lista filtrada pelo robô.
- `scpi` traz o código do extrair-relatorio. `browser.py` e `relatorios.py` (Playwright) vêm da
  navegação do original, com estas mudanças. As esperas pela geração do relatório são maiores
  (`ESPERA_GERACAO_*_MS`: o cadastro inteiro da primeira carga leva minutos). O `interceptar_csv`
  cancela o pedido do CSV (`route.abort`) depois de guardar os bytes: devolvido à página, ele virava
  um download que fechava o navegador. O `atualizar_catalogo` baixa os três relatórios num navegador
  só (`relatorios.sessao_compartilhada`, perfil `catalogo`, aberto só se algum relatório precisar;
  um relatório que falha descarta a sessão e o seguinte abre outra; enquanto ela existe, o
  `DJANGO_ALLOW_ASYNC_UNSAFE` fica ligado, porque a API síncrona do Playwright mantém um laço asyncio
  na thread e o Django recusaria as gravações); fora dele, cada comando abre e
  fecha o seu (perfil do tipo). O login (`abrir_sessao`) também acha os campos sem ID (o de senha, o último combo para o ano) e
  espera a tela parar de ser redesenhada: num perfil novo o SCPI a monta com outra numeração. Os
  campos do Relatório de Produtos são achados pelo que
  está na tela (legenda do quadro, rótulo acima do campo, `JS_CAMPO_ABAIXO_DO_ROTULO`), nunca pelo
  ID: o SCPI numera os IDs na ordem em que as telas são criadas na sessão, e a segunda abertura já
  tem outros; e cada relatório termina como começou ("Fechar relatório" e "Sair": reaberto, o
  formulário volta com os padrões). Sem nada no filtro o SCPI só avisa "Nada a exibir!!!"
  (`_gerar` clica OK): no cadastro o tipo é pulado, no estoque e nas saídas é erro. O cadastro pede
  um relatório por tipo de produto de `TIPOS_CADASTRO` (Produtos, Peças, Lubrificantes e Pneus, sem
  Serviços nem Combustíveis), trocando só o tipo no mesmo formulário; o `ler_cadastro` junta as
  linhas antes da gravação, inclusive no "só os novos", e descarta as dos `GRUPOS_DESCARTADOS` (o
  800, dos serviços, que o SCPI deixa sair nos tipos de produto; a coluna `GRUPO` é obrigatória),
  também no CSV enviado; o parcial sem nenhum material é sucesso com 0. `normalizadores.py` recola os registros quebrados
  em várias linhas; `leitura.py` (puro) vira bytes do CSV em linhas tipadas, achando as
  colunas pelo nome. Aceita o CSV do SCPI (`;`, campos sem aspas, recolado pelo
  `normalizadores.py`) e o mesmo relatório salvo por uma planilha (cabeçalho com `,`: lido pelo
  `csv` padrão, que trata aspas e quebras de linha dentro do campo, sem recolagem);
  `gravacao.py` grava; `execucao.py` registra cada execução em
  `Importacao`, com a gravação numa transação (falha não altera nada) e uma trava `GET_LOCK`
  por tipo (uma importação de cada tipo por vez, entre processos); "em andamento"
  (`Importacao.em_andamento`) vem dessa trava: sem sua trava ocupada, só a criada há menos de 60 s
  conta, e as demais (processo morto, janela fechada à força) aparecem como interrompidas e liberam
  os botões. Regras que valem:
  cadastro completo que deixaria de fora mais de 20% dos materiais visíveis aborta (salvo
  `--forcar`). O cadastro é carregado uma vez por inteiro (CSV enviado, sem datas) e depois o robô
  só traz os novos: sem datas e baixando do SCPI, o padrão é incremental (de 7 dias antes do corte
  da última carga bem-sucedida até hoje, `gravacao.periodo_cadastro_padrao`), que grava só o que o
  CSV traz e nunca oculta nem aborta (importação parcial, também com `--desde`/`--ate`). A recarga
  completa é explícita (`--completo`, ou `--forcar`; sem nenhuma carga anterior ou com `--arquivo`
  sem datas também é completa) e é a única que oculta o que sumiu. Período não combina com
  `--completo`/`--forcar`;
  material que some do cadastro fica oculto, nunca é apagado; estoque substitui todos os
  saldos (ausente = 0) e CSV vazio aborta; saídas voltam 7 dias antes do fim da última
  importação (o robô lança com a data efetiva) e não duplicam (`id_requi`, `cadpro`, `item`:
  o mesmo material repetido na requisição, com outra placa ou destino, é outra saída, numerada
  pela ordem no relatório; a requisição vem sempre inteira, então a numeração se repete).
  Códigos são comparados por `norm_u`, como a collation `utf8mb4_unicode_ci` do banco.
- Lançamento no SCPI (`lancar_saidas`, que abre o SCPI pelo Playwright): `scpi/requisicoes.py`
  (puro, sem ORM) agrupa as `LinhaSaida` `PENDENTE` por lote (um lote = uma requisição), valida
  cabeçalho e itens (centro de custo, tipo, CADPRO, quantidade no formato do SCPI) e deixa de
  fora o lote inteiro que tenha alguma linha `EM_LANCAMENTO`, `VERIFICAR` ou `ERRO` (as
  travas) ou `PENDENTE` já com número de requisição (já lançada); lote inválido vira `ERRO` sem abrir o navegador. `scpi/lancamento.py` fala com o SCPI
  pelo protocolo `SCPI` (o Playwright em produção, um simulado nos testes) e garante nunca
  lançar um lote duas vezes pela ordem das gravações: `EM_LANCAMENTO` é confirmado no banco
  (transação fechada, só se todas as linhas ainda estão `PENDENTE` e sem número de requisição)
  antes do clique em Salvar;
  qualquer falha depois do clique vira `VERIFICAR`, nunca `PENDENTE`; o número da requisição vai
  para o journal `logs/lancar_saidas_journal.jsonl` antes de ir para o banco, e se o banco
  recusar a gravação a execução para (`FalhaCritica`) com o lote travado. Uma trava `GET_LOCK`
  (`pedidos.models.TRAVA_LANCAMENTO`) permite uma execução por vez; a trava ignora o erro de
  banco (`django.db.Error`) ao ser liberada. `scpi/lancador.py` é a navegação copiada do
  extrair-relatorio (perfil do navegador em `SCPI_PERFIL_DIR/lancamento`; o `navegador()` liga o
  `DJANGO_ALLOW_ASYNC_UNSAFE` enquanto está aberto, `browser.orm_liberado`, como a sessão
  compartilhada do catálogo, porque o lançamento grava no banco com ele aberto); os testes só
  conferem a estrutura (implementa o protocolo, não importa o Playwright no topo), sem testes
  da navegação: só a simulação no SCPI real a exercita. `pedidos.ExecucaoRobo` registra cada execução (situação, resumo, log acumulado
  durante o laço, erro); o `--dry-run` preenche e descarta sem tocar em nenhuma linha. A aba
  Lançamento no SCPI de Automações (`pedidos/_lancamentos.html`) tem um formulário só, com a fila:
  cada requisição tem uma caixa de marcar (`name="lotes"`, "marcar todas" no cabeçalho, contagem
  no `aria-live` e botões desabilitados sem marcação, `pedidos/static/pedidos/js/fila-robo.js`) e
  os botões "Simular" e "Lançar no SCPI" mandam o modo (`name="modo"`); só as marcadas são
  processadas (`pedidos/forms.py` valida os `lotes` contra a fila de agora e recusa o que já saiu
  dela; `--lote` repetido no comando; `lancamento.lancar(lotes=...)`, que só valida e marca `ERRO`
  nos lotes escolhidos). Com o lançamento real liberado, o "Lançar no SCPI" abre antes a
  confirmação (`#dialogo-lancar`, fora do formulário, com `form="fila-form"`). A ação em
  destaque é a que dá para executar: com o lançamento real bloqueado, "Simular", e o "Lançar no
  SCPI" fica `aria-disabled` com cadeado e a dica do motivo, como no cartão do painel. O robô roda
  em processo separado (`scpi/disparo.py`, saída em `logs/lancar_saidas.log`). Logo abaixo dos
  botões fica a fila do robô (`consultas.fila_do_robo`: todas as requisições, sem corte, em SQL que
  repete `requisicoes.agrupar`, a regra única do que está na fila; `tests/test_consultas_fila.py`
  confere que concordam). A última execução vira uma frase, com quem iniciou, a duração e só os
  contadores diferentes de zero (`pedidos/andamento.py`, puro); a falha é explicada em português
  (`explicar_falha`: erro conhecido como vem, "Falha inesperada:" vira erro do sistema ou demora
  do SCPI, processo que não subiu vira "não chegou a iniciar"), com o texto técnico e o registro
  num "Detalhe técnico" recolhido, e, no lançamento real, o atalho para as travas (não há
  "Simular de novo": a nova simulação é escolhida na fila). As execuções anteriores ficam no histórico de Automações. A aba atualiza
  a cada 3 s só enquanto há execução em andamento e resolve os lotes travados com
  `servicos.resolver_lote` (informar a requisição, liberar para relançar, o que apaga o número
  e a data de lançamento, ou marcar para não lançar; liberar um lote
  `VERIFICAR`/`EM_LANCAMENTO` exige marcar "Conferi no SCPI"; recusada com execução em
  andamento). "Não lançar" vai em dois passos, também sem JavaScript: um `<details>` com um
  formulário próprio que manda `confirmado=1`, e a view recusa `nao_lancar` sem ele antes de
  chamar `resolver_lote` (o "Desistir" do `pedidos.js` fecha o painel). "Em andamento" (`ExecucaoRobo.em_andamento`) vem da trava: com ela ocupada
  (`IS_USED_LOCK`), toda execução sem fim; sem ela, só a criada há menos de 60 s (o processo
  ainda subindo). As demais sem fim aparecem como interrompidas e liberam o botão. Se o
  disparo não consegue iniciar o processo, a execução já nasce `FALHA`. `consultas.lotes_pendentes` (o total da fila, pela mesma regra) e `lotes_travados`
  alimentam o cartão do painel e a aba Lançamento no SCPI. O robô é o único lugar fora de `servicos.py` que grava em `pedidos`, e só
  mexe em `status`, `requisicao_scpi`, `lancado_em` e `mensagem` das `LinhaSaida` (o superusuário
  também edita esses quatro no admin).
  Na navegação (`scpi/lancador.py`): `pausar` espera `PAUSA_ENTRE_ACOES_MS` (100 ms) entre as
  ações do preenchimento dos itens; a QTD é digitada tecla a tecla (`preencher_celula(...,
  digitando=True)`); o "Novo Item" faz o SCPI recarregar a grade do servidor e, sem a pausa, o
  servidor às vezes devolvia a QTD de uma linha ao padrão (1), então antes de cada rodada da
  conferência final (`RODADAS_RECONCILIACAO`, 5) o robô pede essa recarga (`recarregar_grade`) e a
  tela passa a mostrar o que o servidor tem (se a recarga falha, a conferência final recusa o lote em vez de aceitar a tela); o log traz o diagnóstico (`registrar_regressoes`,
  `registrar_servidor`). `simular_repeticoes --lote <n> --vezes <k>` (só para testes do robô)
  simula a mesma requisição várias vezes numa sessão só do SCPI e resume os resets. A trava do
  lançamento é um `GET_LOCK` do servidor de banco: a suíte não roda junto de uma simulação real.
- `LANCAMENTO_REAL` (`.env`, padrão desligado) bloqueia o lançamento real no SCPI em todo
  ambiente que não é o que lança de verdade (a produção): uma cópia de desenvolvimento ou de
  teste com as mesmas saídas pendentes lançaria em dobro. Bloqueado, o comando
  `lancar_saidas` recusa sem `--dry-run`, a aba Lançamento no SCPI recusa o modo "Lançar" (só
  "Simular") e o painel avisa que está bloqueado. O `settings_test` o liga, porque os testes do
  robô lançam no SCPI simulado; os testes do bloqueio o desligam com o fixture `settings`.
- `implantacao` (sem modelos nem migrations) guarda o backup, o `robos_em_andamento` e a carga
  do de/para. A migração única das planilhas do Apps Script (`importar_planilhas`, com
  `conversao.py` e `migracao.py`) foi feita e removida; o código fica na tag `v1.0.1`. Do que ela
  deixou no banco: atendimentos e saídas avulsas importados apontam para o usuário inativo
  `planilha`, e o tipo de saída deles pode não ser BALCÃO. `planilha.py` (puro) lê o `.xlsx` com
  as colunas achadas pelo nome do cabeçalho. `backup.py` faz o dump (`MYSQLDUMP`, retenção de 60 dias pelo nome do arquivo, a
  limpeza só depois de um backup completo). `depara.py` (sem banco) lê os pares do `.xlsx` da
  planilha MAPEAMENTO DE/PARA CONSOLIDADO: a primeira aba cujo nome começa por "Planilha de
  mapeamento" (o `.xlsx` não aceita "/" no nome de aba) com as regras do `DEPARA_MAP` (formato
  000.000.000, antigo diferente do novo, primeira ocorrência), e a aba `DEPARA`, que vence e traz
  o fator; o `importar_depara` substitui todos os pares numa transação, registra uma
  `Importacao` `DEPARA` e recusa se há par de origem `SISTEMA` ou registro do admin (`LogEntry`)
  depois da última carga: depois dela, o sistema é a fonte dos pares.
- De/para e curva ABC (`specs/001-depara-curva-abc/`, feita pelo Spec Kit): `ParDePara` (código
  antigo único → novo, com fator de quantidade; validação, sem 1:N e sem ciclo no `clean`; o
  admin grava origem `SISTEMA`) e as funções puras de `catalogo/depara.py` (`validar_par`,
  `resolver_canonicos`, que segue a cadeia até o fim e multiplica os fatores, e `consolidar`).
  Toda contagem de saídas usa o canônico: `consultas_curva.py` agrega `SaidaSCPI` por código
  numa consulta e consolida em Python. O período é uma janela móvel (`ConfiguracaoCurva`, linha
  única via `atual()`: janela, prazo de entrega e cobertura alvo gerais) que nunca começa antes
  de 01/01/2026 (`curva.INICIO_DADOS_CONFIAVEIS`); o formulário AB usa a mesma janela e mostra o
  saldo do canônico. A página Painel › Curva ABC (`catalogo:curva`, `?aba=` e `?meses=`) mostra
  as curvas por frequência e por valor (`curva.curva`: A até 78% do acumulado, B até 95%), a
  reposição (`curva.reposicao`, fórmulas da planilha com o fator no consumo; o estoque soma o
  canônico e os antigos; `ParametroReposicao` substitui prazo e cobertura por material), os
  pendentes de mapeamento (código com saída, sem par, oculto ou fora do cadastro) e a
  reconciliação dos totais. As divergências deliberadas da planilha estão na spec.
- Implantação em Docker Compose (`Dockerfile`; spec `2026-10-15-docker-design.md`): uma imagem
  (Python 3.13, `.venv` do uv sem dev, Chromium do Playwright, `mariadb-client`, supercronic,
  estáticos coletados no build, usuário `almox` UID 1000 que só escreve em `/dados`) para os
  serviços `web` (waitress com `--url-prefix=${PREFIXO_URL}` e `--trusted-proxy=*`) e `agendador`
  (supercronic com `deploy/crontab`, que chama `deploy/tarefa.sh`, saída em
  `dados/logs/agendador.log`); o `banco` é o MariaDB 11.4, sem porta publicada. O `compose.yaml`
  é **legado** (instalação atual, publicado em `${PORTA_PUBLICADA}`) e não se altera. Os ambientes
  novos combinam `compose.ambientes.yaml` com um único overlay, `compose.desenvolvimento.yaml` ou
  `compose.producao.yaml`, sem `compose.override.yaml` implícito, em projetos e volumes separados
  (`almoxarifado` e `almoxarifado-prod`); a porta fica fixa em `127.0.0.1` e `PORTA_WEB` só
  escolhe o número. O Compose força `DB_HOST`, `SCPI_HEADLESS=1`, `MYSQLDUMP=mariadb-dump` e as
  pastas (`/dados/logs`, `/dados/backups`, `/dados/perfil`) por cima do `.env`; `dados/` do
  host guarda logs, backups e os `.xlsx` de carga (`dados/importacao`). Os robôs da página são filhos do waitress
  no container `web` (`disparo.py` abre sessão própria fora do Windows), então recriar o `web`
  os mata. Quem atualiza um ambiente é o `deploy/atualizar.ps1` (PowerShell 5.1+, com `-Ambiente`
  explícito): **planeja por padrão**, só altera com `-Aplicar`, não faz `pull`, `fetch`, `checkout`,
  `reset`, `down` nem `prune`, valida marcador `.deploy-ambiente`, checkout limpo, branch (dev) ou
  tag destacada com imagem por digest (produção), faz backup antes de migrar e confere os robôs;
  a produção existente ainda exige `-ManutencaoConfirmada`, e `-Aplicar` não pausa as gravações.
  O `deploy/atualizar.sh` antigo está bloqueado (sai com erro); não o restaure nem o contorne. Os
  testes do script estão em `deploy/tests/`. `deploy/*.sh`, `deploy/crontab`, `Dockerfile` e os
  `compose*.yaml` são LF (`.gitattributes`). Guias: `deploy/INSTALACAO.md`, `deploy/AMBIENTES.md`,
  `deploy/FLUXO_GIT.md` e `deploy/VIRADA.md` (migração histórica, já feita).
- O log usa `ConcurrentRotatingFileHandler` porque o waitress e os comandos gravam no mesmo
  arquivo (no container também: `web` e `agendador` dividem `dados/logs`); no Windows o
  `RotatingFileHandler` não consegue girar um arquivo aberto por outro processo.

## Serena (exploração semântica do código)

- Pré-requisitos, uma vez por máquina (o Serena roda no host, sem Docker): `uv tool install -p 3.13
  serena-agent`, `serena init` e `serena setup claude-code` (ou `claude mcp add --scope user serena --
  serena start-mcp-server --context claude-code --project-from-cwd`). O diretório dos executáveis do
  uv (`uv tool update-shell`) precisa estar no `PATH` de quem abre o Claude Code, porque os hooks
  chamam o `serena-hooks`. Confira com `claude mcp list` (o `serena` aparece conectado). Sem o
  executável, os hooks (que checam `command -v serena-hooks` antes de chamá-lo) saem calados, sem
  erro e sem decidir nada. Isso não instala o Serena nem disponibiliza o servidor MCP: na nuvem, o
  `.claude/setup-nuvem.sh` não os instala e a sessão segue só com as ferramentas nativas.
- O projeto usa a interface `tools` (`agent_interface: tools` em `.serena/project.yml`, versionado;
  o cache e o `project.local.yml` não): cada operação é uma ferramenta MCP, `mcp__serena__<nome>`. A
  preferência global do Serena continua REPL, e a do projeto a vence quando o projeto é ativado na
  partida do servidor, como faz o `--project-from-cwd`. A interface é escolhida nessa partida: depois
  de mudar o `project.yml`, reinicie o servidor (`/mcp`, reconectar) ou abra uma sessão nova. O
  projeto já nasce ativo, então o aviso do hook de início de sessão, que fala em `activate_project`,
  não se aplica; chame `initial_instructions` uma vez por sessão. As memórias
  (`.serena/memories/`) só apontam o essencial: este arquivo vence.
- Leitura: `get_symbols_overview`, `find_symbol` e `find_referencing_symbols` foram verificadas no
  modo Plan; `find_implementations`, `find_declaration` e `get_diagnostics_for_file` existem, mas
  não foram verificadas. As linhas do Serena começam em 0. O contexto `claude-code` não expõe busca
  por padrão, leitura de arquivo nem shell: para isso, Grep, Read e Bash.
- O LSP não enxerga `reverse`, `apps.get_model`, filtros do ORM escritos em texto (`status__in`,
  `atendimento__linhas`), campos dos formulários HTMX, templates, JS e CSS: depois de achar o
  símbolo, confira esses pontos com grep.
- Edição: a interface também expõe ferramentas de edição (`replace_symbol_body`,
  `insert_after_symbol`, `insert_before_symbol`, `replace_content`, `rename_symbol`,
  `safe_delete_symbol` e as de memória). Fora do modo Plan, renomeie com `rename_symbol` depois de
  ver as referências. O modo Plan é só para leitura e planejamento: nenhuma edição, do Serena ou
  nativa (o que o Plan faz com as ferramentas de edição do Serena não foi testado).
- O Serena não valida nada. A verdade sobre o código são `pytest`, `ruff`, `makemigrations --check`
  e as verificações do Django. O Pyright lê a `.venv` pelo `[tool.pyright]` do `pyproject.toml`, mas
  sem `django-stubs` aponta falsos erros em código Django correto (`objects` em modelos,
  `transaction.atomic` em `with`): não corrija o código por causa deles. Depois de mudar o
  `[tool.pyright]`, reinicie o servidor do Serena (`/mcp`, reconectar).
- As restrições de operações reais valem por qualquer caminho: `lancar_saidas` sem `--dry-run`,
  importadores do SCPI, `migrate` no banco real e `LANCAMENTO_REAL`; comando potencialmente
  destrutivo, só com autorização. Migrations, `servicos.py` como único lugar que grava pedidos e as
  travas do SCPI não mudam.
- Os hooks (`.claude/settings.json`: `serena-hooks` `activate`, `remind` e `cleanup`) são
  lembretes: o `remind` nega uma vez, a cada 2 minutos, uma sequência de 3 buscas, 3 leituras de
  código ou 4 das duas (inclusive `cat`, `sed` e `grep` pelo Bash), e a chamada seguinte passa;
  negar uma chamada não garante que o agente passe a usar o Serena. As ferramentas simbólicas do
  Serena zeram a contagem; `get_diagnostics_for_file`, `read_memory`, `write_memory` e `onboarding`
  não. O `auto-approve` fica de fora de propósito: ele aprovaria sozinho, no modo `auto`, as
  ferramentas de edição.

## Convenções

- Nomes de código, textos de interface, mensagens e commits em português (pt-BR).
- Logout só por POST com CSRF, num único formulário por página. Requisição HTMX que grava vai
  dentro de um `<form>` com `{% csrf_token %}`.
- Estado nunca só por cor; códigos (CADPRO, matrícula, placa) em fonte mono (`.mono`).
- Todo ajuste de UI/UX usa três skills juntas: `clean-design` (no repositório) com o
  `docs/DESIGN.md`, que são a referência fixa de estilo e vencem as outras duas;
  `ui-ux-pro-max` (plugin), para conferir usabilidade e acessibilidade pelo buscador; e
  `frontend-design` (plugin), para hierarquia, contenção, textos de interface e a conferência
  por screenshot. Onde discordarem, valem o DESIGN.md e o que já está no código. Não refazer o
  questionário inicial da `clean-design` (o projeto já o respondeu) nem gerar ou gravar um
  design system novo das skills sem pedido.
- O servidor está em produção com dados reais: mudança de modelo ganha **migration nova**,
  nunca regenerada (nem `migrate <app> zero`).
