# Implementation Plan: Consistência dos formulários públicos de pedido

**Branch**: `005-consistencia-formularios-publicos` (branch de trabalho: `claude/consistencia-formularios-publicos`) | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-consistencia-formularios-publicos/spec.md`

## Summary

Unificar a regra de quantidade e de estoque dos dois formulários públicos (limpeza e AB), de modo
que ela dependa da **unidade do material** (e da tela: público ou equipe), não do nome do
formulário. Em volta disso: estados vazios do catálogo iguais nos dois, erros por item sem perda do
pedido, mensagens de recusa humanas, JavaScript declarado como requisito, a montagem do catálogo do
AB fora do bloqueio da numeração e a configuração de cada formulário concentrada em `Fluxo`, para
que os próximos formulários sejam só catálogo e textos.

Abordagem técnica (detalhada em [research.md](research.md)):

- A lista de unidades fracionáveis vive em `Opcao` (mecanismo que já existe e já tem tela no admin),
  carregada com as 10 unidades por uma migration de dados. `ItemCatalogo` ganha `fracionavel`,
  calculado a partir da unidade do **cadastro do SCPI** (a do código canônico no AB).
- Funções puras novas em `pedidos/regras.py` (`truncar_qtd`, `maximo_pedivel`,
  `interpretar_quantidade`, tabela única de textos de erro) substituem as ramificações
  `inteiro`/`com_estoque`/`parse_inteiro if AB`. Uma só `validar_pedido` atende os dois formulários.
- `Fluxo` troca `inteiro`/`com_estoque`/`limita_estoque` por uma regra de quantidade
  (`por_unidade` para o público, `livre` para a equipe) e passa a carregar o catálogo e os textos.
- `registrar_pedido` carrega catálogo e centros **antes** de abrir a transação que trava a
  `Sequencia`.
- Nenhum cache, nenhuma coluna nova em `Pedido`, nenhuma mudança no robô do SCPI.

## Technical Context

**Language/Version**: Python 3.13 (`>=3.13,<3.14`), Django 6.x

**Primary Dependencies**: Django, HTMX 4.0.0 (vendorizado), waitress; Playwright só no robô do SCPI (não tocado)

**Storage**: MariaDB 11.4 / MySQL 8; uma migration de dados nova em `catalogo` (lista de unidades), sem mudar `pedidos`

**Testing**: pytest contra MariaDB/MySQL (`config.settings_test`), sem navegador; testes de JavaScript só conferem o texto do arquivo, então há conferência manual em celular (SC-010)

**Target Platform**: servidor em Docker Compose (Windows 10 + Docker Desktop); clientes: navegador de celular e de computador, com JavaScript

**Project Type**: aplicação web Django com HTMX (monólito, apps `catalogo`, `pedidos`, `interface`)

**Performance Goals**: a montagem do catálogo do AB não acontece enquanto a numeração está bloqueada; a medição do tempo dela com dados reais é entregue (cache fora do escopo)

**Constraints**: produção com dados reais (migration nova, nunca regenerada); nenhum lançamento real no SCPI; `servicos.py` continua o único lugar que grava pedidos; quantidades em `Decimal` com 3 casas; saldo com 4 casas

**Scale/Scope**: ~7.200 materiais no cadastro, ~38 itens na limpeza, centenas no AB; poucos pedidos por dia; 2 formulários públicos hoje, pelo menos 2 previstos

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação | Observação |
|---|---|---|
| I. Regras puras e fiéis à origem | **Passa**, com divergências deliberadas já registradas na spec (Assumptions) | As funções novas ficam em `pedidos/regras.py`, sem ORM. Os textos de erro de quantidade passam a ser únicos e diferem do Apps Script de propósito (FR-022); o AB aceita fração (FR-001) |
| II. Uma porta de gravação, transacional e idempotente | **Passa** | `registrar_pedido` continua a única porta; só a leitura do catálogo sai de dentro da transação. Reenvio, divergência e Telegram em `on_commit` ficam iguais |
| III. Nunca lançar duas vezes no SCPI | **Não se aplica** | Nenhum código do robô, das linhas de saída ou do lançamento é alterado; as verificações não lançam nada (FR-044) |
| IV. Dados importados nunca se perdem em silêncio | **Passa** | Nenhum importador muda. A lista de unidades é cadastro manual, não importação |
| V. Testes contra o banco real, sem navegador | **Passa** | Todo comportamento novo vem com teste em MariaDB; JavaScript só tem teste de texto, e isso é dito no plano; a conferência no navegador é manual e fica no quickstart |
| VI. Interface em pt-BR, acessível e sem dependências externas | **Passa** | O aviso de JavaScript usa as classes `aviso` do design system Clean; nenhuma fonte, CDN ou pacote novo; estado nunca só por cor ("Corrigir" e "Sem estoque" são texto) |
| Restrições técnicas | **Passa** | Migration nova com carga de dados (a regra de "regenerar" valia só até a importação das planilhas, já feita); sem variável de ambiente nova; `check --deploy` não é afetado |
| Fluxo de desenvolvimento | **Passa** | Spec e plano antes do código; branch própria; o `CLAUDE.md` e a spec principal são atualizados no mesmo PR (FR-042) |

Nenhuma violação; a tabela *Complexity Tracking* fica vazia.

**Reavaliação depois do design (Fase 1):** as mesmas conclusões. O desenho não acrescenta
dependência, tabela de gravação nem exceção a princípio.

## Project Structure

### Documentation (this feature)

```text
specs/005-consistencia-formularios-publicos/
├── plan.md              # Este arquivo
├── research.md          # Fase 0: decisões, alternativas e itens a confirmar
├── data-model.md        # Fase 1: entidades, regras de validação e estados
├── quickstart.md        # Fase 1: como validar de ponta a ponta, inclusive a medição e a conferência no celular
├── contracts/
│   ├── mensagens.md             # Catálogo único de textos (causa, texto, onde aparece)
│   ├── configuracao-fluxo.md    # O que um formulário (atual ou novo) informa
│   └── interface-publica.md     # Rotas, campos e contexto dos trechos (o que muda e o que não muda)
├── checklists/
│   └── requirements.md  # Qualidade da especificação
└── tasks.md             # Fase 2 (/speckit-tasks, ainda não criado)
```

### Source Code (repository root)

```text
catalogo/
├── models.py              # Opcao.Lista ganha UNIDADE_FRACIONAVEL (só choices)
├── migrations/
│   └── 0002_unidades_fracionaveis.py   # novo: choices + carga das 10 unidades (RunPython idempotente)
├── catalogos.py           # ItemCatalogo.fracionavel; _item/_catalogo_*; unidades_fracionaveis()
├── saude.py               # formulário sem itens vira aviso; texto "formulários" no lugar de "formulário AB"
└── admin.py               # sem mudança esperada (Opcao já é editável)

pedidos/
├── regras.py              # truncar_qtd, maximo_pedivel, interpretar_quantidade, textos; validar_pedido único;
│                          # remove validar_pedido_limpeza/ab e regra_inteira; origem_publica
├── carrinho.py            # usa interpretar_quantidade e maximo_pedivel; ler() pode manter linhas ilegíveis
├── fluxos.py              # Fluxo: regra de quantidade, catálogo, textos; resultados() com a linha única
├── servicos.py            # catalogo_de por Fluxo; registrar_pedido carrega o catálogo antes do lock;
│                          # conv e regra_inteira por origem saem; teto da equipe truncado a 3 casas
├── protecao.py            # motivo da recusa (isca | rapido); textos novos; sem "expirou"
├── telegram.py            # _quantidade usa o formatador único
├── views/
│   ├── publico.py         # indisponível único; aviso de "sem estoque agora"; linhas ilegíveis preservadas
│   └── almoxarifado.py    # _formatar_qtd; regra do atendimento_adicionar (equipe)
├── templates/pedidos/     # formulario.html, _formulario.html, _materiais.html, _carrinho.html,
│                          # _adicionado.html, _recibo_item.html (textos do Fluxo, inputmode, aviso, comentários)
└── static/pedidos/        # pedidos.css (aviso sem JS), pedidos.js (só comentários e o que depender do modo sem JS)

interface/templates/interface/base_publico.html   # <noscript> (ou no formulario.html)

docs/superpowers/specs/2026-10-10-central-almoxarifado-django-design.md   # §4 e §5 corrigidos
CLAUDE.md                                                                  # seções de quantidades, indisponível, JS, equipe

tests/
├── test_regras_pedidos.py, test_carrinho.py, test_limpeza_estoque.py, test_avulsa_estoque.py,
│   test_formularios_publicos.py, test_registrar_pedido.py, test_protecao_pedidos.py,
│   test_catalogos.py, test_saude.py, test_atendimento*.py, test_recibos.py   # ajustados
├── test_quantidade_por_unidade.py   # novo: matriz unidade × saldo × quantidade (SC-001)
├── test_estados_do_catalogo.py      # novo: indisponível, sem estoque agora, aviso de saúde
├── test_fluxo_configuravel.py       # novo: formulário de teste só com catálogo e textos (SC-007)
└── test_migracao_unidades.py        # novo: a carga das 10 unidades e a idempotência
```

**Structure Decision**: aplicação Django existente, sem diretório novo. O trabalho fica nos apps
`catalogo` (dados e catálogo), `pedidos` (regras, carrinho, fluxos, serviços, telas) e na camada
`interface` só para o aviso de JavaScript. Os arquivos de teste novos seguem o padrão `tests/test_*.py`
do projeto.

## Phases

- **Fase 0 (research.md):** decisões R1 a R17, com alternativas descartadas e os pontos que precisam de
  confirmação do usuário.
- **Fase 1 (design):** `data-model.md`, `contracts/` e `quickstart.md`.
- **Fase 2 (tarefas):** `/speckit-tasks`. A ordem sugerida, por dependência: (1) regras puras e testes
  da matriz; (2) lista de unidades e `ItemCatalogo.fracionavel`; (3) `Fluxo`, carrinho e validação
  única; (4) estados do catálogo e saúde; (5) erros, proteções e mensagens; (6) equipe, Telegram e
  formatador; (7) aviso de JavaScript; (8) catálogo fora do bloqueio e medição; (9) documentação e
  conferência manual.

## Complexity Tracking

Nenhuma violação da constituição a justificar.
