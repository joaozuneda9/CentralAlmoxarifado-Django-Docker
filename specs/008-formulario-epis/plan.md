# Implementation Plan: Formulário de EPIs

**Branch**: `008-formulario-epis` (branch de trabalho: `claude/epis`) | **Date**: 2026-10-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-formulario-epis/spec.md`

## Summary

Um formulário público novo, "Equipamentos de proteção individual (EPIs)", cujo pedido **passa antes por
autorização da Segurança do Trabalho**. Ele é uma entrada de `FLUXOS` (PR #18) com **um campo novo**,
`exige_autorizacao`: busca, carrinho, envio, proteções, painel, atendimento, edição, recibo e lançamento
no SCPI vêm prontos. O que é próprio:

- **Autorização**: modelo `AutorizacaoPedido` (uma linha por pedido de EPI, definitiva, com quem, quando
  e motivo) e o serviço `decidir_autorizacao`; o atendimento só é aceito com `AUTORIZADO` (portão na
  `confirmar_atendimento`, espelhado na tela).
- **Acesso da Segurança do Trabalho**: grupo do Django e um middleware com lista fechada de rotas
  (nega por padrão); fila e detalhe de leitura em rotas novas.
- **Avisos**: um segundo chat do Telegram para a Segurança do Trabalho (ao registrar); o aviso ao
  almoxarifado passa a sair ao autorizar.
- **Consulta pública** do resultado pelo número, com resposta neutra e limite por origem.
- **Catálogo** pelos grupos `Opcao.GRUPO_EPI` mais os avulsos de `MaterialEpi`, como a oficina, sem
  tocar nela.

Decisões e alternativas em [research.md](research.md); modelo em [data-model.md](data-model.md).

## Technical Context

**Language/Version**: Python 3.13 (`>=3.13,<3.14`), Django 6.x

**Primary Dependencies**: Django, HTMX 4.0.0 (vendorizado), waitress; nenhuma dependência nova

**Storage**: MariaDB 11.4 / MySQL 8; três migrations aditivas (`pedidos/0005_epis`, `catalogo/0005_epis`,
`contas/0002_grupo_seguranca_trabalho`), sem carga de dados de catálogo

**Testing**: pytest contra MariaDB/MySQL (`config.settings_test`), sem navegador; Pester para o script
de atualização (`deploy/tests/`); JavaScript novo só se a tela de decisão pedir (nenhum previsto: a
decisão é um formulário comum)

**Target Platform**: servidor em Docker Compose (Windows 10 + Docker Desktop); celular e computador

**Project Type**: aplicação web Django com HTMX (monólito; apps `catalogo`, `pedidos`, `contas`,
`interface`)

**Performance Goals**: catálogo em duas consultas (como a oficina); fila e painel paginados em 25; a
autorização é uma linha por pedido de EPI (poucas por dia)

**Constraints**: produção com dados reais (migrations novas, nunca regeneradas); `servicos.py` único
lugar que grava pedidos; nenhum lançamento real no SCPI; formulários existentes inalterados (FR-032);
`check --deploy` sem avisos; variável de ambiente nova documentada no `.env.example`

**Scale/Scope**: 1 formulário, 2 modelos novos, 1 origem, 1 lista de opções, 1 grupo, 1 middleware, 4
rotas internas e 1 pública

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação | Observação |
|---|---|---|
| I. Regras puras, o próprio sistema como referência | **Passa** | A situação e os textos da consulta ficam em `regras.py` (funções puras, sem ORM); a SQL do painel repete a regra, como hoje, com teste de concordância |
| II. Uma porta de gravação, transacional e idempotente | **Passa** | `registrar_pedido` cria a autorização na mesma transação; `decidir_autorizacao` e `confirmar_atendimento` são serviços em `servicos.py`; a decisão trava a linha e é idempotente (R9); a consulta pública só lê |
| III. Nunca lançar duas vezes no SCPI | **Passa, sem toque** | Robô, `LinhaSaida` e travas intocados; o portão do atendimento garante que nenhum lote nasce antes da autorização, o que só **reduz** o que o robô vê |
| IV. Dados importados nunca se perdem em silêncio | **Passa** | Importadores intocados; `MaterialEpi` usa `PROTECT` |
| V. Testes contra o banco real, sem navegador | **Passa** | Cada FR ganha teste em MariaDB; o acesso é testado por todas as rotas do projeto |
| VI. Interface em pt-BR, acessível, sem dependências externas | **Passa** | Reusa os layouts e componentes; estado nunca só por cor (selos com texto); CSRF em todo POST |
| Restrições técnicas | **Passa** | Migrations novas e aditivas; variável nova no `.env.example`; `check --deploy` coberto |
| Fluxo de desenvolvimento | **Passa** | Spec e plano antes do código; `CLAUDE.md` atualizado no mesmo PR |

**Pontos de atenção (sem violação)**:
- `publico.formulario` registra que o sucesso "não tem URL própria, para o número não virar página
  pública". A consulta por número é uma exceção pedida pelo usuário e limitada a situação e motivo
  (R6); o endurecimento com o nome completo é proposto ao usuário.
- É o primeiro ponto do sistema com separação de acesso. O middleware de lista fechada (R4) a concentra
  num só lugar em vez de espalhar decoradores.

**Reavaliação depois do design (Fase 1)**: as mesmas conclusões. O ponto de maior risco é o middleware
(trava de usuário errado) e é coberto por um teste que percorre todas as rotas do projeto.

## Riscos de regressão

- `situacao_pedido` e `filtrar_situacao` servem a todos os pedidos: parâmetro opcional com padrão `None` e
  nenhuma linha de autorização nos pedidos antigos; o teste de concordância SQL × pura inclui os casos
  novos e os antigos sem alteração.
- `registrar_pedido` escolhe o aviso por `fluxo.exige_autorizacao`: os testes de Telegram e de registro
  dos outros formulários seguem sem alteração.
- `telegram._enviar` é extraído de `notificar_pedido`: o teste do aviso existente é a rede.
- O middleware roda em todo pedido: sem usuário no grupo, retorna cedo; teste de que usuário comum
  continua com tudo.
- `compose.desenvolvimento.yaml` e `atualizar.ps1`: a variável nova entra na lista de integrações vazias;
  o teste Pester cobre.

## Testes

- `tests/test_epis_catalogo.py`: grupos (normalização, vazio), avulsos (também de grupo fora da escolha,
  sem repetir), ocultos fora, duplicado bloqueado, ordem pelo nome, `None` sem saldo ou sem item.
- `tests/test_epis_modelos.py`: constraints de `AutorizacaoPedido` (os três estados válidos e os
  inválidos), `PROTECT` de `MaterialEpi` e de `decidido_por`, origem nova.
- `tests/test_epis_formulario.py`: cartão na página inicial; formulário abre; indisponível sem catálogo;
  envio registra origem `EPIS` e a autorização `AGUARDANDO`; reenvio igual confirma sem duplicar; tela de
  sucesso com os textos de aguardando e o link; limites por nome somam os formulários públicos.
- `tests/test_epis_autorizacao.py`: autorizar, recusar com motivo, recusa sem motivo, decisão repetida e
  simultânea (primeira vale), grupo errado negado (administrador sem grupo, usuário do almoxarifado), só
  pedido de EPI, gravação de quem e quando.
- `tests/test_epis_atendimento.py`: atendimento recusado para aguardando e para recusado, sem
  `Atendimento` nem `LinhaSaida`, por tela e por POST forjado; autorizado atende como os outros; edição,
  recibo e lote do robô iguais; busca e acréscimo de material em pedido não autorizado dão 404.
- `tests/test_epis_acesso.py`: o middleware com todas as rotas do projeto (as da lista passam, as demais
  não, para GET e POST); usuário comum e anônimo inalterados; login do usuário do grupo cai na fila;
  menu.
- `tests/test_epis_painel.py`: situação pura × SQL com autorização, filtro Autorização, atalho "Atender"
  sem os não autorizados.
- `tests/test_epis_consulta.py`: três situações, número inexistente e de outro formulário (mesma
  resposta), limite por origem, sem dados pessoais na resposta, `no-store`.
- `tests/test_epis_decisao_telas.py`: a fila (só EPI aguardando, mais antigo primeiro, decididos em
  leitura), o detalhe (404 fora de EPI), o aviso do motivo e a decisão pela tela.
- `tests/test_epis_telegram.py`: ao registrar, só o chat da Segurança do Trabalho; ao autorizar, só o do
  almoxarifado; ao recusar, nenhum; chat vazio não envia e não desfaz; reenvio não reavisa.
- `tests/test_epis_saude.py` e `tests/test_epis_admin.py`: textos de saúde, contagem em Automações,
  admin de `MaterialEpi` e da lista de grupos, grupo criado pela migration.
- `deploy/tests/atualizar.Tests.ps1`: variável nova vazia na preparação.
- Migrations: `makemigrations --check`; `test_fluxo_configuravel.py` continua verde.
- Risco aceito: a navegação e o visual das telas novas são conferidos à mão pelo quickstart; os testes
  não abrem navegador (Constituição V).

## Dependências e ordem

1. Modelos, constantes e migrations (bloqueiam o resto): `AutorizacaoPedido`, `MaterialEpi`, `GRUPO_EPI`,
   `Origem.EPIS`, grupo.
2. Regras puras (`situacao_pedido`, textos) e catálogo (`catalogo_epis`, `formulario_epis`), em paralelo.
3. Serviços: `registrar_pedido` com a autorização, `decidir_autorizacao`, o portão em
   `confirmar_atendimento`.
4. Entrada de `FLUXOS` com `exige_autorizacao` e a tela de sucesso (formulário público utilizável).
5. Acesso: grupo, `da_seguranca_trabalho`, middleware, menu.
6. Telas: fila, detalhe e decisão; detalhe e filtros do almoxarifado; consulta pública.
7. Avisos (Telegram e variável de ambiente, compose, script).
8. Saúde, admin e documentação (`CLAUDE.md`, `.env.example`, `deploy/AMBIENTES.md`).

## Project Structure

### Documentation (this feature)

```text
specs/008-formulario-epis/
├── plan.md
├── research.md          # R1–R10
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── configuracao-fluxo.md
│   ├── rotas-e-acesso.md
│   └── mensagens.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
catalogo/
├── models.py            # MaterialEpi; Opcao.Lista.GRUPO_EPI
├── admin.py             # MaterialEpiAdmin
├── catalogos.py         # grupos_epis, catalogo_epis, formulario_epis
├── saude.py             # _epis; Situacao.epis
├── templates/catalogo/_situacao.html   # contagem do formulário
└── migrations/0005_epis.py
contas/
├── acesso.py            # GRUPO_SEGURANCA_TRABALHO, da_seguranca_trabalho
├── middleware.py        # RestringirSegurancaTrabalho
└── migrations/0002_grupo_seguranca_trabalho.py
pedidos/
├── models.py            # Origem.EPIS; AutorizacaoPedido; Pedido.autorizacao_ou_none
├── regras.py            # EPIS; situação com autorização; texto da consulta
├── fluxos.py            # Fluxo.exige_autorizacao; FLUXOS["epis"]
├── servicos.py          # registrar_pedido (autorização e aviso); decidir_autorizacao; portão do atendimento
├── telegram.py          # _enviar; aviso à Segurança do Trabalho
├── consultas.py         # filtro Autorização; filtrar_situacao; fila de autorização
├── views/autorizacao.py # fila, detalhe, decisão
├── views/publico.py     # consulta_epi
├── views/almoxarifado.py# detalhe e endpoints com a autorização
├── urls.py
├── templates/pedidos/   # autorizacoes.html, autorizacao.html, consulta_epi.html, _sucesso.html, detalhe.html, _painel_lista.html
├── templatetags/pedidos_extras.py   # selos e passos das novas situações
└── migrations/0005_epis.py
interface/navegacao.py   # itens por perfil
interface/templates/interface/_icone.html   # ícone `escudo` (novo)
config/settings.py       # TELEGRAM_CHAT_ID_SEGURANCA; PEDIDOS_CONSULTA_LIMITE_IP_10_MIN; middleware
.env.example, compose.desenvolvimento.yaml, deploy/atualizar.ps1, deploy/AMBIENTES.md, CLAUDE.md
tests/ (test_epis_*.py, epis_cenario.py), deploy/tests/atualizar.Tests.ps1
```

**Structure Decision**: monólito Django existente; nenhum app novo. A escolha dos EPIs vive em
`catalogo`, como as outras listas; a autorização e as telas em `pedidos`; o acesso em `contas`.

## Complexity Tracking

| Desvio | Por que é necessário | Alternativa mais simples rejeitada |
|--------|----------------------|-------------------------------------|
| Middleware de rotas permitidas (primeiro controle de acesso por perfil) | "Só a fila" (FR-017) sem editar e testar cada view; nega por padrão | `@permission_required` em cada view: esquecer uma rota abre o sistema |
| Modelo `AutorizacaoPedido` separado de `Pedido` | O pedido antigo não pode mudar (FR-032) e "nulo" seria ambíguo | Colunas nulas em `Pedido` |
| Página pública de consulta pelo número | Pedido do usuário (FR-031); o servidor não tem login | Nenhuma: sem ela o servidor não sabe o resultado |
