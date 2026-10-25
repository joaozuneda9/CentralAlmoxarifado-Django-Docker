# Implementation Plan: Configuração das opções por formulário

**Branch**: `009-configuracao-formularios` (branch de trabalho: `claude/configuracao-formularios`) | **Date**: 2026-10-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-configuracao-formularios/spec.md`

## Summary

Uma página interna, **Formulários**, onde o almoxarifado escolhe, por formulário, **quais centros de custo
são destino** e **quais materiais são oferecidos**, sem editar código. Duas peças distintas, uma
experiência:

- **Centros de custo**: `CentroCusto.ativo` (global) e a associação `CentroFormulario` (linha do cadastro e
  formulário). `Fluxo.centros` das cinco entradas públicas passa a ler a associação, com o **modo de
  destino** que cada formulário já tinha (padrão, sem placa, oficina).
- **Materiais**: uma **camada de exceções** (`ExcecaoMaterial`) sobre a regra de origem de hoje. Sem
  exceção, vale o que valia; o AB continua calculado. A disponibilidade efetiva é calculada, nunca guardada.
- **Integração sem tocar o núcleo**: `formulario_*` devolve a base com as exceções aplicadas e
  `centros_do_formulario` devolve os destinos; busca, carrinho, `validar_pedido` e `registrar_pedido` já
  validam contra essas duas listas, então a validação no backend sai de graça.
- **Migração verificável**: uma migration aditiva transcreve as regras antigas (todos os centros, a marca
  de equipe, a oficina, os avulsos) e confere, no próprio banco, que cada formulário oferece o mesmo
  conjunto; os cadastros antigos ficam no banco e saem do admin.

Decisões e alternativas em [research.md](research.md); modelo em [data-model.md](data-model.md); rotas e
permissões em [contracts/](contracts/).

## Technical Context

**Language/Version**: Python 3.13 (`>=3.13,<3.14`), Django 6.x

**Primary Dependencies**: Django, HTMX 4.0.0 (vendorizado, só pelos componentes existentes), waitress;
nenhuma dependência nova

**Storage**: MariaDB 11.4 / MySQL 8; duas migrations (`catalogo/0006_configuracao_formularios`, o esquema, e `0007_transcrever_configuracao`, os dados): coluna
`ativo`, duas tabelas e a carga de dados; nada apagado

**Testing**: pytest contra MariaDB/MySQL (`config.settings_test`), sem navegador; a migration de dados
testada como `test_migracao_unidades.py` (função de módulo chamada com `apps`); equivalência contra uma
cópia congelada da regra antiga

**Target Platform**: servidor em Docker Compose (Windows 10 + Docker Desktop); a tela é do computador do
almoxarifado, mas deve funcionar no tablet

**Project Type**: aplicação web Django com HTMX (monólito; apps `catalogo`, `pedidos`, `contas`,
`interface`, `automacoes`)

**Performance Goals**: catálogo de formulário com **uma consulta a mais** (as exceções) mais uma pelos
acrescentados; destinos com uma consulta; a lista da tela paginada em 50, com o estado calculado só para a
página; o AB calcula em 0,06 s (7.322 materiais visíveis)

**Constraints**: produção com dados reais (migration nova, nunca regenerada, aditiva); `servicos.py` único
lugar que grava pedidos (a configuração grava só `catalogo`); nenhum lançamento real no SCPI; robô, estoque
e catálogo de materiais intocados; `check --deploy` sem avisos; sem CDN, sem npm, sem JavaScript novo

**Scale/Scope**: 5 formulários fixos, 2 modelos novos, 1 coluna, 1 página (mais 5 POST e 1 consulta), 1
migration, 1 módulo de regras e serviços, ~11 mil materiais no cadastro, 244 linhas de centro

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação | Observação |
|---|---|---|
| I. Regras puras, o próprio sistema como referência | **Passa** | `estado(oculto, na_regra, excecao)` é função pura, sem ORM, com a tabela do data-model como teste; o cálculo da regra continua nas funções de catálogo |
| II. Uma porta de gravação, transacional e idempotente | **Passa** | Nenhuma gravação em `pedidos` (só `servicos.py` muda a validação da saída avulsa); as gravações novas são curtas, transacionais, idempotentes e únicas por constraint; o reenvio de pedido segue conferindo o gravado antes de validar |
| III. Nunca lançar duas vezes no SCPI | **Passa, sem toque** | Robô, `LinhaSaida` e travas intocados; a decisão de **não** filtrar o robô por `ativo` (R5) existe justamente para um lote pendente não virar `ERRO` |
| IV. Dados importados nunca se perdem em silêncio | **Passa** | Importadores intocados; `ExcecaoMaterial` usa `PROTECT`; nada é apagado (nem os cadastros antigos); a migration verifica a equivalência e para se divergir |
| V. Testes contra o banco real, sem navegador | **Passa** | Cada FR ganha teste em MariaDB; permissões testadas por POST forjado; a navegação visual é conferida à mão pelo quickstart |
| VI. Interface em pt-BR, acessível, sem dependências externas | **Passa** | Reusa layouts, abas, filtros e selos; estado com texto (não só cor); CSRF em todo POST; sem JavaScript novo |
| Restrições técnicas | **Passa** | Migration nova e aditiva; sem variável de ambiente nova |
| Fluxo de desenvolvimento | **Passa** | Spec e plano antes do código; `CLAUDE.md` e os contratos antigos atualizados no mesmo PR |

**Pontos de atenção (sem violação)**:

- É a primeira tela interna cuja **gravação** exige `is_staff` mais permissão de modelo (o resto da parte
  interna não distingue). Segue o critério do menu "Cadastros" e do admin, sem papel novo (R8); a lista
  fechada da Segurança do Trabalho já nega a rota por padrão.
- A decisão "nada de filtrar atendimento, edição e robô por centro ativo" faz `ativo` ter dois alcances
  (R5). Está documentada nos contratos e coberta por teste de cada ponto.

**Reavaliação depois do design (Fase 1)**: as mesmas conclusões. O maior risco é a regressão de
equivalência na migração e nos testes antigos que montam centros e avulsos pelos cadastros velhos; é
coberto por teste de equivalência e pela adaptação planejada de `tests/cenario.py`.

## Riscos de regressão

- **Testes que criam centros sem associação**: com a decisão "centro novo sem formulário", todo teste que
  cria `CentroCusto` e abre um formulário público ficaria sem destino. Mitigação: `tests/cenario.py` e os
  cenários de viaturas, oficina e EPIs usam um auxiliar que cria centro e o habilita nos formulários
  desejados; os testes de comportamento antigo ficam como estão.
- **Testes que dependem dos cadastros antigos** (`equipe_manutencao`, `MaterialOficina`, `MaterialEpi`):
  `test_viaturas_destinos`, `test_viaturas_catalogo`, `test_viaturas_modelos`, `test_oficina_catalogo`,
  `test_oficina_destinos`, `test_oficina_admin`, `test_oficina_saude`, `test_epis_catalogo`,
  `test_epis_admin`, `test_epis_saude`, `test_fluxo_configuravel` (`centros is None`) são reescritos para a
  configuração nova, sem enfraquecer o que verificam.
- **`catalogo_oficina` e `catalogo_epis` passam a ser só os grupos**: o teste de equivalência junta o
  resultado da regra mais as exceções migradas e compara com o catálogo antigo.
- **`_validar_saida_avulsa`** serve à saída nova e à edição: ganha o parâmetro da lista de centros; os
  testes de edição e atendimento ficam como estão e ganham o caso do centro inativo.
- **`opcoes_saida()`** serve a atendimento, edição e avulsa: o padrão do parâmetro mantém o comportamento
  atual.
- **Saúde**: as mensagens existentes dos formulários seguem as mesmas; só a origem do dado muda.
- **Admin**: `CentroCustoAdmin` perde `equipe_manutencao`; `test_cadastros.py` é a rede.

## Medições

*(preenchidas por T001 e T052: tempo de abertura dos cinco formulários antes e depois, e da lista de
materiais da configuração; SC-010.)*

**Antes (T001, 2026-10-23, banco de desenvolvimento, `Client`, média de 10 aberturas):** limpeza 11 ms, AB
41 ms, viaturas 40 ms, oficina 36 ms, EPIs 36 ms. Suíte de base: 1.697 passam, 1 pulado (flags do Windows),
em 24 s.

**Depois (T052, 2026-10-23, mesmo banco e método):** limpeza 13 ms, AB 45 ms, viaturas 48 ms, oficina 40 ms,
EPIs 35 ms (no máximo +20%: o aumento é a consulta das exceções e dos destinos). A lista de materiais da
página Formulários (7.322 visíveis, 50 por página, no servidor): 80 a 101 ms; a aba de centros (244
linhas), 91 ms. Suíte: 1.895 passam, 1 pulado, em 35 s.

## Implantação

A migration roda no `deploy/atualizar.ps1`, que já faz o backup antes de migrar; nada de especial além de
conferir o quickstart (passo 1: os formulários oferecem o mesmo de antes). Em produção, só a pedido do
usuário (CLAUDE.md). A reversão do código é a volta à tag anterior com o banco restaurado do backup; as
tabelas novas são aditivas e inertes para o código antigo.

## Testes

- `tests/test_config_estado.py`: a tabela do data-model inteira (oculto, regra, exceção) e "sem efeito".
- `tests/test_config_catalogo.py`: exceção que acrescenta (aparece, ao fim, alfabética; oficina e EPIs
  reordenados), que retira (some da base e das viaturas, que juntam lista e AB), restaurar, duplicado
  bloqueado, oculto nunca oferecido, sem repetir, `None` quando esvazia, formulários independentes, AB
  continua dinâmico com uma exceção ao lado.
- `tests/test_config_centros.py`: os três modos de destino, inativo fora, habilitado e desabilitado por
  formulário, formulário sem destino indisponível, envio direto recusado (`registrar_pedido`) para centro
  desabilitado, inativo e de outro formulário, sem pedido gravado.
- `tests/test_config_centro_inativo.py`: atendimento, edição de atendimento, edição de saída avulsa e robô
  (`scpi/requisicoes`) resolvem centro inativo; a saída avulsa nova não oferece nem aceita.
- `tests/test_config_historico.py`: pedido antigo, retrato do item, atendimento em andamento, pedido de EPI
  aguardando autorização, reenvio igual e divergente depois de retirar material e inativar centro.
- `tests/test_config_servicos.py`: `definir_excecao` (menor mudança, idempotente), `aplicar_em_lote`
  (conjunto exato, fora do filtro intocado, atômico, mudaram e já estavam), `habilitar_centros`,
  `definir_ativo`, quem e quando.
- `tests/test_config_telas.py`: a página (formulário padrão, aba, busca, filtros, paginação em 50, só
  visíveis), a prévia e o POST do lote (número esperado, "ciente" sem filtro, recusa quando o filtro
  mudou), a consulta por material, mensagens, volta preservando o estado.
- `tests/test_config_permissoes.py`: usuário comum vê sem controles; POST forjado dá 403 em cada rota de
  gravação; staff sem a permissão específica; superusuário passa; anônimo vai ao login; Segurança do
  Trabalho negada (também pelo teste que percorre todas as rotas, `test_epis_acesso.py`).
- `tests/test_config_migracao.py`: `transcrever` com cada regra antiga (todos, equipe, oficina com e sem
  o centro, avulsos, ocultos), repetição sem duplicar, reversão, falha se divergir.
- `tests/test_config_equivalencia.py`: o catálogo e os destinos de cada formulário, antes e depois, contra
  uma cópia congelada da regra antiga (SC-001).
- `tests/test_config_saude.py` e `tests/test_config_admin.py`: avisos novos, `CentroCustoAdmin` com `ativo`
  e sem a marca antiga, admins de avulsos fora.
- Migrations: `makemigrations --check`; os testes de formulário, atendimento e robô seguem verdes.
- Risco aceito: o visual da tela é conferido à mão pelo quickstart (os testes não abrem navegador).

## Dependências e ordem

1. **Base** (bloqueia o resto): `Formulario`, `CentroCusto.ativo`, `CentroFormulario`, `ExcecaoMaterial`,
   a migration de esquema e a de dados com a verificação.
2. **Regras e serviços**: `catalogo/disponibilidade.py` (`estado` pura; `definir_excecao`,
   `aplicar_em_lote`, `habilitar_centros`, `definir_ativo`), em paralelo com `catalogos.py`
   (`regra_de_origem`, `aplicar_excecoes`, `centros_do_formulario`, catálogos só de grupos).
3. **Integração**: `FLUXOS` com `centros_do_formulario`; `servicos.centros_ativos` e o parâmetro da saída
   avulsa; `opcoes_saida(so_ativos)`.
4. **Equivalência**: adaptação dos cenários e dos testes antigos, e o teste de equivalência (prova de que a
   integração não mudou o que os formulários oferecem).
5. **Tela**: página, abas Centros e Materiais, prévia e lote, consulta por material, permissões e menu.
6. **Saúde, admin e documentação** (`CLAUDE.md`, contratos 005 a 008).

## Project Structure

### Documentation (this feature)

```text
specs/009-configuracao-formularios/
├── plan.md
├── research.md          # R1–R12
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── configuracao-fluxo.md
│   └── rotas-e-permissoes.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
catalogo/
├── models.py            # Formulario; CentroCusto.ativo; CentroFormulario; ExcecaoMaterial
├── disponibilidade.py   # NOVO: estado (pura), serviços de exceção, lote, centros e ativo
├── acesso.py            # NOVO: pode_alterar_centros, pode_alterar_materiais, decorador exige (403)
├── catalogos.py         # regra_de_origem, aplicar_excecoes, centros_do_formulario; formulario_*; só grupos
├── saude.py             # avisos novos; troca de centros_equipe_manutencao e centros_oficina
├── admin.py             # CentroCustoAdmin com ativo; fora MaterialOficinaAdmin e MaterialEpiAdmin
├── views_formularios.py # NOVO: formularios, formularios_material, lote, excecao, centros, ativo
├── urls.py              # as rotas novas
├── forms.py             # filtros da tela e do lote
├── templates/catalogo/  # formularios.html, _formularios_centros.html, _formularios_materiais.html, _lote_previa.html, formularios_material.html
├── static/catalogo/css/catalogo.css   # só o que a tela precisar (reuso primeiro)
└── migrations/0006_configuracao_formularios.py, 0007_transcrever_configuracao.py
pedidos/
├── fluxos.py            # as cinco entradas com centros=partial(centros_do_formulario, ...)
├── servicos.py          # centros_ativos; _validar_saida_avulsa recebe a lista de centros
└── views/almoxarifado.py# opcoes_saida(so_ativos); a avulsa nova passa so_ativos=True
interface/navegacao.py   # item "Formulários"
CLAUDE.md, specs/005..008 (notas dos contratos)
tests/ (test_config_*.py; cenario.py, viaturas_cenario.py, oficina_cenario.py, epis_cenario.py e os testes antigos adaptados)
```

**Structure Decision**: monólito Django existente; nenhum app novo. A configuração é do `catalogo` (que já
tem `CentroCusto`, os catálogos e a saúde) e a validação continua onde estava, em `pedidos`. A página fica
em `/painel/catalogo/formularios/`, ao lado da Curva ABC.

## Complexity Tracking

| Desvio | Por que é necessário | Alternativa mais simples rejeitada |
|--------|----------------------|-------------------------------------|
| Dois modelos de associação (`CentroFormulario`, `ExcecaoMaterial`) | Semânticas diferentes: centro é presença/ausência, material é exceção sobre uma regra calculada | Uma tabela única genérica: mistura "habilitado" com "exceção" e perderia o AB dinâmico |
| Modo de destino por formulário (3 valores) | Os formulários já se comportam assim (viaturas sem placa, oficina só placa); a configuração só escolhe as linhas | Configurar o modo na tela: viraria um construtor de formulários (fora do escopo) |
| Migration que se verifica | Produção com dados reais e a regra "não deixar formulário sem opções" | Migration sem conferência: um erro de transcrição só apareceria com o formulário vazio |
| Permissão por modelo (`change_*`) em vez de um papel | Reuso do admin; a spec proíbe papel novo | Um grupo novo: papel novo sem necessidade demonstrada |
