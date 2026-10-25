# Research: Formulário da oficina mecânica

Decisões do planejamento, com base no código de `develop` em 2026-10-22 (merge do PR #20) e nos
dados do banco de desenvolvimento (cópia do cadastro do SCPI).

## R1 — Um `Fluxo` novo, sem campo novo no `Fluxo`

- **Decision**: o formulário é a entrada `FLUXOS["oficina"]` (origem `OFICINA`, URL
  `/pedido/oficina/`), com `catalogo=formulario_oficina` e `centros=centros_oficina`. Nenhum campo
  novo em `Fluxo`: `folha=None`, `pede_ocorrencia=False`, `regra_quantidade` padrão (por unidade).
- **Rationale**: é o caminho previsto pela spec 005 (US8) e já exercido pela 006. Busca, carrinho,
  envio, proteções, limites, painel, atendimento, edição, recibo, Telegram e robô vêm prontos
  (FR-001, FR-002, FR-004, FR-010, FR-011). Os esclarecimentos tiraram tudo o que pediria campo novo
  (sem número de OS, sem folha, sem regra de estoque própria).
- **Alternatives considered**: reaproveitar o `Fluxo` das viaturas com outros parâmetros (acoplaria
  as duas features, contra o pedido do usuário); um formulário próprio fora de `FLUXOS` (duplicaria o
  núcleo).

**Ajuste da implementação (2026-10-22):** a validação manual (quickstart §4) mostrou que o
`_formulario.html` escolhia o placeholder do destino por `fluxo.centros` ("Centro de custo da equipe"
sempre que o fluxo restringe os centros), um acoplamento escondido com o formulário das viaturas. A
oficina ganharia o texto das equipes. Solução: um campo de texto opcional em `Fluxo`,
`exemplo_destino` (padrão "Posto de trabalho, placa do veículo ou setor", o texto de hoje), como os
`exemplo_*` que já existem; viaturas passa "Centro de custo da equipe" e a oficina "Oficina mecânica
ou placa da viatura". Nenhum comportamento muda nos outros formulários.

## R2 — Grupos da oficina numa lista de `Opcao`

- **Decision**: os grupos ficam numa lista nova de `Opcao`, `GRUPO_OFICINA` ("Grupos (oficina)"),
  mantida em Cadastros › Opções, comparados pelo mesmo `_grupo` (sem acento, maiúsculas, sem espaços)
  que os grupos ocultos do AB. Lista vazia = nenhum grupo (sem padrão embutido).
- **Rationale**: é exatamente o mecanismo de `GRUPO_OCULTO_AB`: nomes de grupo do SCPI, texto livre,
  mantidos pelo almoxarifado no admin (FR-012). Não há tabela de grupos no sistema; o grupo é um
  texto do `Material`.
- **Alternatives considered**: tabela própria de grupos (sem ganho: não há entidade grupo a
  referenciar); padrão embutido `AUTO PECAS` (a spec deixa a escolha ao almoxarifado, e um padrão
  escondido confunde a saúde do catálogo).

## R3 — Materiais avulsos num modelo próprio (`MaterialOficina`)

- **Decision**: `catalogo.MaterialOficina`, uma linha por material (`OneToOneField(Material,
  PROTECT)`), sem nome exibido nem ordem, com admin de autocomplete como o de `PecaViatura`.
- **Rationale**: FR-012a pede material do cadastro, cada um no máximo uma vez: a chave estrangeira
  garante a existência e a unicidade, e `PROTECT` segue `ItemLimpeza`/`PecaViatura`. O motivo do
  campo são os ~330 óleos e filtros do grupo `GERAL`, que não pode entrar inteiro (5.000 materiais).
- **Alternatives considered**: códigos numa lista de `Opcao` (sem integridade nem autocomplete);
  reaproveitar `PecaViatura` (acoplaria a lista das equipes à oficina).

## R4 — Catálogo do formulário

- **Decision**: `catalogos.catalogo_oficina()` lê os materiais não ocultos cujo grupo normalizado
  está em `GRUPO_OFICINA` ou que têm `MaterialOficina`, uma vez cada, ordenados pelo nome, e os
  converte com o `_item` de sempre (unidade e fração do SCPI, `duplicado` bloqueado).
  `formulario_oficina()` devolve `None` sem saldo importado ou sem item (FR-005).
- **Rationale**: o filtro por grupo exige normalização igual à do AB; como o número de grupos é
  pequeno e o cadastro visível tem ~6.000 linhas, a comparação é feita em Python sobre os grupos
  distintos (uma consulta `values_list("grupo").distinct()`), e a consulta dos materiais filtra pelo
  `grupo__in` dos textos que casaram, mais os avulsos. A busca já põe os bloqueados no fim e corta
  em 50 (`fluxos.buscar`); a ordem pelo nome é só a de base (spec, Assumptions).
- **Alternatives considered**: ordenar pelo número de saídas, como o AB (a spec não pede, e a conta
  é pesada); tirar os sem estoque (a resposta do esclarecimento foi "bloqueado", FR-004).

## R5 — Destinos: OFICINA MECÂNICA ou "centro — placa"

- **Decision**: `catalogos.centros_oficina()` devolve o centro sem placa cuja descrição normalizada é
  `OFICINA MECÂNICA` (as linhas sem placa) e um `Centro` por linha com placa, marcado
  `so_com_placa=True`. `regras.Centro` ganha `so_com_placa: bool = False`, e `opcoes_destino` deixa
  de oferecer a descrição sozinha dos centros cujas linhas são todas `so_com_placa`; como
  `resolver_destino` parte de `opcoes_destino`, o envio passa a recusar a descrição sozinha de uma
  viatura e aceita "centro — placa" ou a placa digitada (FR-006). O nome `OFICINA MECÂNICA` vira a
  constante `regras.CENTRO_OFICINA`, usada também por `resolver_centro_custo`.
- **Rationale**: no cadastro, cada placa é um centro de custo próprio (149 centros com placa, um
  código cada). Sem a marca, `opcoes_destino` ofereceria cada viatura duas vezes (descrição e
  "descrição — placa"), ~300 opções, e a descrição sozinha não diria a placa ao atendimento. Com o
  padrão `False`, `servicos.centros()` e os outros formulários não mudam (FR-014). O atendimento já
  sugere centro e placa a partir de "centro — placa" (`views/almoxarifado._saida_do_destino`):
  FR-009 não pede código novo.
- **Alternatives considered**: campo `Fluxo.destino_so_com_placa` passado por `validar_pedido` (mexe
  na assinatura das regras e nos serviços); aceitar as duas formas (lista duplicada e viatura sem
  placa no pedido); um campo de viatura separado do destino (descartado pelo esclarecimento).

## R6 — Indisponibilidade e saúde

- **Decision**: sem destinos, o formulário já fica indisponível pelo `sem_destinos` da view; sem
  catálogo, pelo `indisponivel`. A saúde ganha `_oficina()`, no molde de `_viaturas()`: erro sem
  destino ou sem material, "ok" com a contagem, aviso com os grupos da lista sem material visível e
  os materiais avulsos ocultos; `Situacao` ganha `oficina` (a contagem do formulário na visão geral
  de Automações).
- **Rationale**: FR-005 e FR-013 com os mecanismos que os outros formulários já usam.

## R7 — Migrations

- **Decision**: `catalogo/0004_oficina` (modelo `MaterialOficina` e `choices` de `Opcao.lista`) e
  `pedidos/0004_oficina` (`choices` de `Pedido.origem`). Sem carga de dados: o almoxarifado
  configura grupos e avulsos depois da implantação.
- **Rationale**: produção com dados reais (migration nova, aditiva). A escolha inicial dos grupos é
  decisão do almoxarifado (spec, Assumptions).

## R8 — Textos

- **Decision**: título "Oficina mecânica" (nome interno da origem igual), exemplo de busca "Ex.:
  filtro de óleo, pneu", exemplo do início "Ex.: filtro, óleo, pneu, aditivo, lâmpada", ícone já
  existente em `_icone.html` (escolhido na implementação). Mensagens de erro, indisponível e destino
  inválido são as de hoje (contrato `mensagens.md`).
