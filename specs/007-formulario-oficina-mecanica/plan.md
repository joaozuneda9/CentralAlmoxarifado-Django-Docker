# Implementation Plan: Formulário da oficina mecânica

**Branch**: `007-formulario-oficina-mecanica` (branch de trabalho: `claude/oficina-mecanica`) | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-formulario-oficina-mecanica/spec.md`

## Summary

Um formulário público novo, "Oficina mecânica", para quem trabalha na oficina pedir ao almoxarifado
autopeças e insumos. Ele é uma entrada de `FLUXOS` (PR #18), com um único campo de texto novo no
`Fluxo` (`exemplo_destino`, research R1, achado na validação manual): busca,
carrinho, envio, proteções, painel, atendimento, edição, recibo, Telegram e lançamento no SCPI vêm
prontos. O que é próprio do formulário:

- **Catálogo pela escolha da oficina**: os materiais visíveis dos grupos do SCPI listados em
  `Opcao` `GRUPO_OFICINA` mais os materiais avulsos de `catalogo.MaterialOficina` (para os óleos e
  filtros do grupo `GERAL`), ordenados pelo nome, com a regra de quantidade e de estoque dos
  formulários públicos.
- **Destinos**: o centro `OFICINA MECÂNICA` ou uma viatura, oferecida só como "centro — placa"
  (`regras.Centro.so_com_placa`). O atendimento já sugere centro e placa a partir desse destino.

Decisões e alternativas em [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.13 (`>=3.13,<3.14`), Django 6.x

**Primary Dependencies**: Django, HTMX 4.0.0 (vendorizado), waitress; nenhuma dependência nova

**Storage**: MariaDB 11.4 / MySQL 8; duas migrations aditivas (`catalogo/0004_oficina`, `pedidos/0004_oficina`), sem carga de dados

**Testing**: pytest contra MariaDB/MySQL (`config.settings_test`), sem navegador; nenhum JavaScript novo

**Target Platform**: servidor em Docker Compose (Windows 10 + Docker Desktop); clientes: navegador de celular e de computador, com JavaScript

**Project Type**: aplicação web Django com HTMX (monólito; apps `catalogo`, `pedidos`, `interface`)

**Performance Goals**: catálogo em duas consultas (grupos distintos do cadastro visível, depois os materiais), ~120 a ~500 itens; sem cache, como os outros

**Constraints**: produção com dados reais (migrations novas, nunca regeneradas); `servicos.py` continua o único lugar que grava pedidos; nenhum lançamento real no SCPI; os formulários existentes não mudam de comportamento (FR-014)

**Scale/Scope**: 1 formulário, 1 modelo novo, 1 lista de opções nova, 1 origem nova, 1 campo opcional numa estrutura pura

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação | Observação |
|---|---|---|
| I. Regras puras, o próprio sistema como referência | **Passa** | A regra dos destinos fica em `regras.opcoes_destino` (pura), com `Centro.so_com_placa`; o catálogo e os centros são leituras em `catalogos.py`, como os demais |
| II. Uma porta de gravação, transacional e idempotente | **Passa** | `registrar_pedido` continua a única porta, com a conferência de reenvio de sempre (o destino já faz parte dela) |
| III. Nunca lançar duas vezes no SCPI | **Não se aplica** | Robô, `LinhaSaida` e lançamento intocados |
| IV. Dados importados nunca se perdem em silêncio | **Passa** | Nenhum importador muda; `MaterialOficina` usa `PROTECT` |
| V. Testes contra o banco real, sem navegador | **Passa** | Cada FR ganha teste em MariaDB; não há JavaScript novo |
| VI. Interface em pt-BR, acessível, sem dependências externas | **Passa** | Reusa os templates dos formulários públicos; ícone já existente |
| Restrições técnicas | **Passa** | Migrations novas e aditivas; sem variável de ambiente nova |
| Fluxo de desenvolvimento | **Passa** | Spec e plano antes do código; branch `claude/*`; `CLAUDE.md` atualizado no mesmo PR |

Nenhuma violação; *Complexity Tracking* vazio.

**Reavaliação depois do design (Fase 1):** as mesmas conclusões. O único ponto no núcleo é
`Centro.so_com_placa`, com padrão neutro: `servicos.centros()` não o liga, e os testes de destino
existentes (`test_viaturas_destinos.py`, os do formulário público) cobrem que nada mudou.

## Riscos de regressão

- `opcoes_destino`/`resolver_destino` servem a todos os formulários públicos: o padrão `False` mantém
  o resultado; um teste novo confere a igualdade com a lista de antes para centros sem a marca.
- `resolver_centro_custo` passa a usar `CENTRO_OFICINA`: mesmo texto, testes existentes do
  atendimento cobrem.
- `Situacao` ganha `oficina`: o template da visão geral de Automações precisa do valor; teste da
  página.

## Testes

- `tests/test_oficina_catalogo.py`: grupos (normalização, vazio), avulsos (também de grupo oculto do
  AB, sem repetir com o grupo), ocultos fora, duplicado bloqueado, ordem pelo nome, `None` sem saldo
  ou sem item.
- `tests/test_oficina_destinos.py`: `opcoes_destino` com `so_com_placa` (pura) e sem (igual a hoje);
  `centros_oficina` (com e sem OFICINA MECÂNICA, viaturas); `resolver_destino` com placa digitada;
  envio recusado com outro centro e com a descrição sozinha da viatura.
- `tests/test_oficina_formulario.py`: página inicial lista o cartão; formulário abre; indisponível
  sem catálogo e sem destinos; envio registra origem `OFICINA`; reenvio igual confirma; atendimento
  sugere centro e placa; filtro do painel por origem.
- `tests/test_oficina_modelos.py`: unicidade e `PROTECT` de `MaterialOficina`; origem nova.
- `tests/test_oficina_admin.py`: admin dos materiais da oficina e a lista de grupos.
- `tests/test_oficina_saude.py`: textos de saúde e contagem na visão geral.
- Risco aceito: a edição do atendimento (FR-011) não ganha teste próprio; é o mesmo código dos
  outros formulários, coberto pelos testes deles.
- Migrations: `makemigrations --check`; `test_fluxo_configuravel.py` continua verde.

## Dependências e ordem

1. Modelos e migrations (bloqueiam o resto).
2. `regras` (`CENTRO_OFICINA`, `Centro.so_com_placa`) e funções de catálogo (testáveis em paralelo).
3. Entrada de `FLUXOS` e admin.
4. Saúde, documentação (`CLAUDE.md`).

## Project Structure

### Documentation (this feature)

```text
specs/007-formulario-oficina-mecanica/
├── plan.md
├── research.md          # R1–R8
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── configuracao-fluxo.md
│   └── mensagens.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
catalogo/
├── models.py            # MaterialOficina; Opcao.Lista.GRUPO_OFICINA
├── admin.py             # MaterialOficinaAdmin
├── catalogos.py         # grupos_oficina, catalogo_oficina, formulario_oficina, centros_oficina
├── saude.py             # _oficina; Situacao.oficina
├── templates/catalogo/_situacao.html   # contagem do formulário (se a visão geral listar por formulário)
└── migrations/0004_oficina.py
pedidos/
├── models.py            # Origem.OFICINA
├── regras.py            # OFICINA, CENTRO_OFICINA, Centro.so_com_placa, opcoes_destino
├── fluxos.py            # FLUXOS["oficina"]
└── migrations/0004_oficina.py
tests/
├── test_oficina_modelos.py
├── test_oficina_catalogo.py
├── test_oficina_destinos.py
├── test_oficina_formulario.py
├── test_oficina_admin.py
└── test_oficina_saude.py
```

**Structure Decision**: monólito Django existente; nenhum app novo. A escolha da oficina vive em
`catalogo`, como as outras listas, e o formulário em `pedidos`, como os outros.

## Complexity Tracking

Sem violações a justificar.
