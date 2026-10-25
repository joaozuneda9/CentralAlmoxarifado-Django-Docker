# Implementation Plan: Reposição de peças das viaturas das equipes de manutenção

**Branch**: `006-reposicao-pecas-viaturas` (branch de trabalho: `claude/reposicao-pecas-viaturas`) | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-reposicao-pecas-viaturas/spec.md`

## Summary

Um formulário público novo, "Reposição de peças das viaturas", para o encarregado da equipe de
manutenção pedir a reposição das peças que a viatura leva. Ele é uma entrada de `FLUXOS` (o mecanismo
do PR #18): busca, carrinho, envio, proteções, painel, atendimento, recibo e lançamento no SCPI vêm
prontos. O que é próprio do formulário:

- **Lista de peças comuns** (`catalogo.PecaViatura`, no molde de `ItemLimpeza`), mostrada numa
  **folha**: um diálogo com a lista inteira em que o encarregado preenche as quantidades como no papel
  e põe tudo no pedido de uma vez. O resto do catálogo AB continua na busca do mesmo passo.
- **Destinos**: só os centros de custo marcados como de equipe de manutenção, sem placa.
- **Nº da ocorrência**: campo opcional de até 20 caracteres, gravado no pedido.

Abordagem e alternativas em [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.13 (`>=3.13,<3.14`), Django 6.x

**Primary Dependencies**: Django, HTMX 4.0.0 (vendorizado), waitress; nenhuma dependência nova

**Storage**: MariaDB 11.4 / MySQL 8; duas migrations aditivas (`catalogo/0003`, `pedidos/0003`), sem carga de dados

**Testing**: pytest contra MariaDB/MySQL (`config.settings_test`), sem navegador; o diálogo da folha é conferido à mão (quickstart §4)

**Target Platform**: servidor em Docker Compose (Windows 10 + Docker Desktop); clientes: navegador de celular e de computador, com JavaScript

**Project Type**: aplicação web Django com HTMX (monólito; apps `catalogo`, `pedidos`, `interface`)

**Performance Goals**: o catálogo do formulário custa o do AB (35 a 57 ms medidos no PR #18) mais uma consulta de cerca de 40 linhas; sem cache

**Constraints**: produção com dados reais (migrations novas, nunca regeneradas); `servicos.py` continua o único lugar que grava pedidos; nenhum lançamento real no SCPI; os formulários existentes não mudam de comportamento

**Scale/Scope**: cerca de 40 peças na lista, alguns centros de equipe, poucos pedidos por dia; 1 formulário novo, 1 modelo novo, 2 campos novos

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação | Observação |
|---|---|---|
| I. Regras puras, o próprio sistema como referência | **Passa** | Ocorrência e cabeçalho em `pedidos/regras.py`; a folha em `pedidos/carrinho.py` (sem ORM), reaproveitando os textos de erro da spec 005. Nenhuma equivalência com o papel ou o Apps Script é perseguida além do que a spec pede |
| II. Uma porta de gravação, transacional e idempotente | **Passa** | `registrar_pedido` continua a única porta; a ocorrência entra na conferência de reenvio, então o reenvio igual confirma e o diferente é divergente, como antes. A folha não grava nada: só monta o carrinho da página |
| III. Nunca lançar duas vezes no SCPI | **Não se aplica** | Robô, `LinhaSaida` e lançamento intocados; o pedido de viaturas gera linhas pelo atendimento de sempre |
| IV. Dados importados nunca se perdem em silêncio | **Passa** | Nenhum importador muda; a lista é cadastro manual e usa `PROTECT`, como `ItemLimpeza` |
| V. Testes contra o banco real, sem navegador | **Passa** | Cada FR ganha teste em MariaDB; o JavaScript do diálogo tem teste de texto e conferência manual registrada |
| VI. Interface em pt-BR, acessível, sem dependências externas | **Passa** | `<dialog>` nativo com foco gerenciado, rótulos por linha, erros com `aria-describedby`; bloqueio em texto, não só cor; ícone já existente; design system Clean |
| Restrições técnicas | **Passa** | Migrations novas e aditivas; sem variável de ambiente nova; `check --deploy` não é afetado. (A seção ainda cita NSSM e Apache, que já não são a topologia; divergência documental conhecida, fora desta feature) |
| Fluxo de desenvolvimento | **Passa** | Spec e plano antes do código; branch `claude/*`; `CLAUDE.md` e o contrato da 005 atualizados no mesmo PR |

Nenhuma violação; *Complexity Tracking* vazio.

**Reavaliação depois do design (Fase 1):** as mesmas conclusões. Os três campos opcionais de `Fluxo`
(`folha`, `centros`, `pede_ocorrencia`) têm padrão neutro e uma justificativa por requisito (FR-003,
FR-007/008, FR-002a); nenhum cria abstração para usos que ainda não existem.

## O que reaproveita do PR #18 (sem mudar)

| Componente | Uso |
|---|---|
| `Fluxo`/`FLUXOS`, rotas `/pedido/<fluxo>/` | entrada `viaturas` |
| `fluxos.buscar`/`resultados`, `_resultados.html` | pesquisa no catálogo (lista + AB) |
| `carrinho` (`adicionar`, `alterar`, `remover`, `limite`, `motivo_bloqueio`) e `_carrinho.html` | revisão do pedido e base da folha |
| `regras.validar_pedido`, `interpretar_quantidade`, `maximo_pedivel`, textos de erro | validação do envio e da folha |
| `protecao` (token, isca, tempo mínimo), limites por IP e por nome | iguais |
| `opcoes_destino`/`resolver_destino`/`_erro_destino`, `sem_destinos` | destinos restritos e indisponibilidade sem centro |
| `registrar_pedido`, `Sequencia`, Telegram `on_commit` | gravação e aviso |
| Painel, filtro por origem, atendimento, edição, recibo, `LinhaSaida`, robô | sem regra própria (FR-010) |
| `catalogo_ab()` | a parte "AB" do catálogo do formulário |

## O que muda (mínimo)

| Área | Mudança | Requisitos |
|---|---|---|
| `catalogo/models.py` + `0003` | `PecaViatura`; `CentroCusto.equipe_manutencao` | FR-007, FR-011, FR-011a/b |
| `catalogo/admin.py` | admin de `PecaViatura` (como `ItemLimpeza`); coluna, filtro e edição da marca em `CentroCusto` | FR-007, FR-011 |
| `catalogo/catalogos.py` | `formulario_viaturas`, `folha_viaturas`, `centros_equipe_manutencao` | FR-003, FR-004, FR-005, FR-007/008, FR-012 |
| `catalogo/saude.py` | linhas do formulário de viaturas; `Situacao.viaturas`; texto de "sem saldo" generalizado | FR-008a, FR-013 |
| `pedidos/models.py` + `0003` | `Origem.VIATURAS`; `Pedido.ocorrencia` | FR-002a, FR-009 |
| `pedidos/regras.py` | `EnvioPedido.ocorrencia`, `MAX_OCORRENCIA`, erro de tamanho, `cabecalho_enviado` com a ocorrência | FR-002a |
| `pedidos/fluxos.py` | campos `folha`, `centros`, `pede_ocorrencia`; entrada `viaturas` | FR-001, FR-003, FR-007 |
| `pedidos/carrinho.py` | `aplicar_folha`, `Carrinho.erros_folha` | FR-003 |
| `pedidos/servicos.py` | `centros_do_fluxo`; `registrar_pedido` usa os centros do fluxo e grava/compara a ocorrência | FR-002a, FR-007, FR-008a |
| `pedidos/views/publico.py`, `views/materiais.py` | ler a ocorrência quando o fluxo pede; centros do fluxo; ramos `folha_abrir`/`folha` do carrinho | FR-002a, FR-003, FR-007 |
| `pedidos/telegram.py` | rótulo por `get_origem_display()` (a ocorrência não entra no aviso) | FR-009 |
| `pedidos/consultas.py` | a busca do painel (`q`) também procura em `Pedido.ocorrencia`; dica do campo "Nº, solicitante, recebedor ou ocorrência" | FR-002a |
| Templates | `_formulario.html` (campo de ocorrência, botão da folha), `_folha.html` (novo), `_painel_lista.html`, detalhe e `_recibo.html` (ocorrência) | FR-002a, FR-003 |
| `pedidos.js`/`pedidos.css` | abrir e fechar o diálogo, foco, evento `folha-aplicada`; estilo da folha no design Clean | FR-003 |
| Documentação | `CLAUDE.md`; nota no contrato da 005 apontando para os campos novos | Fluxo de desenvolvimento |

## Estratégia de testes

Testes novos em `tests/`, contra MariaDB, por história:

- **US1**: `test_viaturas_formulario.py` — o fluxo aparece na página inicial; folha abre com as peças
  na ordem, nome exibido, bloqueadas com motivo e quantidades do carrinho; `aplicar_folha` (pura):
  aplica, substitui, remove em branco/zero, tudo ou nada com erro por linha, limite de 40; envio
  registra `VIATURAS` com `P-`; painel filtra, mostra a ocorrência e a acha pela busca; Telegram com
  o rótulo e sem a ocorrência; ocorrência: opcional, 20 aceitos,
  21 recusados no campo, gravada, no detalhe e no recibo, ignorada em limpeza/AB, reenvio com
  ocorrência diferente é divergente.
- **Destinos (FR-007/008/008a)**: só centros marcados, sem placa; placa ou outro centro recusados;
  sem centro marcado = indisponível na tela e recusa no serviço; atendimento continua aceitando todos.
- **US2**: busca acha material do AB fora da lista e a peça da lista pelo nome exibido, uma vez só
  (SC-004); peça da lista fora do AB aparece; catálogo `None` sem saldo e sem nada.
- **US3**: admin de `PecaViatura` (inclusão, material repetido recusado, ordem); peça oculta some e vira
  aviso na saúde; contagem na saúde e na visão geral de Automações.
- **Não regressão**: a suíte existente passa sem mudança de comportamento (SC-005); limpeza e AB sem
  folha, sem ocorrência, com "centro — placa"; `test_fluxo_configuravel.py` continua verde.
- **Migrations**: `makemigrations --check`; teste de que pedidos antigos ficam com ocorrência "" e
  centros com a marca desligada.
- **JavaScript**: teste de texto do `pedidos.js` (atributos `data-folha-*`, evento `folha-aplicada`) e
  conferência manual do quickstart §4.

## Dependências e ordem

1. Modelos e migrations (bloqueiam o resto).
2. Funções de catálogo e centros; regras da ocorrência; `aplicar_folha` (puras, testáveis em paralelo).
3. `Fluxo` e serviços; views; templates e JavaScript.
4. Saúde, Telegram, documentação.

**Relação com a feature 007 (oficina)**: ela também acrescenta uma origem em `Pedido.Origem` e pode
usar `Fluxo.centros`. Por isso começa depois do merge desta (a migration `pedidos/0004` parte da
`0003`). Esta feature não antecipa nada da oficina.

## Project Structure

### Documentation (this feature)

```text
specs/006-reposicao-pecas-viaturas/
├── plan.md              # este arquivo
├── research.md          # Fase 0: decisões R1–R11
├── data-model.md        # Fase 1: PecaViatura, CentroCusto, Pedido e estruturas puras
├── quickstart.md        # Fase 1: validação de ponta a ponta
├── contracts/
│   ├── configuracao-fluxo.md   # campos novos do Fluxo e a entrada viaturas
│   ├── folha.md                # o diálogo da lista de peças
│   └── mensagens.md            # textos novos
├── checklists/requirements.md
└── tasks.md             # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
catalogo/
├── models.py            # PecaViatura; CentroCusto.equipe_manutencao
├── admin.py
├── catalogos.py         # formulario_viaturas, folha_viaturas, centros_equipe_manutencao
├── saude.py
└── migrations/0003_pecas_viaturas.py
pedidos/
├── models.py            # Origem.VIATURAS; Pedido.ocorrencia
├── regras.py            # ocorrência no envio e no reenvio
├── fluxos.py            # Fluxo.folha/centros/pede_ocorrencia; FLUXOS["viaturas"]
├── carrinho.py          # aplicar_folha
├── servicos.py          # centros_do_fluxo; registrar_pedido
├── telegram.py
├── views/publico.py
├── views/materiais.py
├── templates/pedidos/   # _formulario.html, _folha.html (novo), detalhe, _recibo.html
├── static/pedidos/js/pedidos.js
├── static/pedidos/css/pedidos.css
└── migrations/0003_viaturas.py
tests/
├── test_viaturas_modelos.py
├── test_viaturas_catalogo.py
├── test_viaturas_folha.py
├── test_viaturas_ocorrencia.py
├── test_viaturas_destinos.py
├── test_viaturas_formulario.py
├── test_viaturas_atendimento.py
└── test_viaturas_admin.py
```

**Structure Decision**: monólito Django existente; nenhum app novo. O formulário vive onde vivem os
outros (`pedidos`), e a lista onde vive a de limpeza (`catalogo`).

## Complexity Tracking

Sem violações a justificar.
