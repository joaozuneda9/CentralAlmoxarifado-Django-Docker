# Research: Reposição de peças das viaturas

Fase 0 do plano. Cada decisão vem da leitura do código atual (`develop` em `430fd13`, depois dos PRs
#18 e #19) e das respostas do usuário registradas na spec. Os caminhos citados são do repositório.

## R1. O formulário é uma entrada de `FLUXOS`, sem núcleo novo

**Decision**: um `Fluxo` novo, `nome="viaturas"`, `origem="VIATURAS"`, `titulo="Reposição de peças
das viaturas"`, `catalogo=formulario_viaturas`, `regra_quantidade` padrão (`por_unidade`),
`publico=True`. Rotas, página inicial, busca, carrinho, envio, proteções, painel, atendimento,
edição, recibo e lançamento ficam como estão.

**Rationale**: as rotas já são `/pedido/<fluxo>/…` (`pedidos/urls.py`); a página inicial lista
`fluxos_publicos()`; o filtro do painel lê `Pedido.Origem.choices` (`pedidos/consultas.py`); o núcleo
só distingue "avulsa ou não" (`regras.origem_publica`, `regras.situacao_pedido`), e `VIATURAS` cai no
lado público (numeração `P-`, limite por nome, conferência de reenvio). `tests/test_fluxo_configuravel.py`
já prova o caminho com um formulário de teste chamado justamente "Reposição de peças das viaturas".

**Alternatives considered**: reaproveitar o fluxo `ab` com um filtro (rejeitado: o pedido precisa de
origem própria no painel, FR-009, e de destinos próprios, FR-007).

**Nome interno**: `VIATURAS`/`viaturas`, e não "reposição": o catálogo já tem
`ParametroReposicao` e a aba "Reposição" da curva ABC, que tratam de outra coisa (repor o estoque do
almoxarifado). Evita a confusão no código e no admin.

## R2. Lista de peças: modelo novo `PecaViatura`, no molde de `ItemLimpeza`

**Decision**: `catalogo.PecaViatura` com `material` (`OneToOneField` para `Material`, `PROTECT`),
`nome_exibido` (opcional) e `ordem`. Admin com `autocomplete_fields=["material"]`, `list_editable =
["ordem"]` e busca por código, nome e nome exibido, como o de `ItemLimpeza`.

**Rationale**: é o mesmo problema que `ItemLimpeza` resolve (lista curada, nome familiar, ordem), e o
admin dele já é conhecido pelo almoxarifado. O `OneToOneField` garante FR-011a (um material uma vez só)
no banco. `PROTECT` segue `ItemLimpeza`: material nunca é apagado (Princípio IV), só ocultado.

**Alternatives considered**:
- `Opcao` com o código do material no `valor`: sem nome exibido nem chave estrangeira; rejeitado.
- Acrescentar um campo "lista" a `ItemLimpeza`: mistura dois formulários num modelo cujo `clean`
  exige categoria de limpeza, e o `OneToOne` impediria a mesma peça nas duas listas; rejeitado.
- Modelo genérico "item de formulário" (base do futuro painel de configuração): abstração prematura
  com um só uso; o painel futuro pode migrar `ItemLimpeza` e `PecaViatura` quando existir.

## R3. Catálogo do formulário = lista + catálogo AB, sem repetição

**Decision**: `catalogos.formulario_viaturas()` devolve `None` sem saldo importado; senão, as peças da
lista (material não oculto, com o nome exibido quando houver) na ordem da lista, seguidas dos itens de
`catalogo_ab()` cujo código não está na lista; `None` se o resultado for vazio (contrato do `Fluxo`).
`catalogos.folha_viaturas()` devolve os códigos da lista visíveis, na ordem: é o que a folha mostra.

**Rationale**: FR-005 (pesquisa no catálogo AB), FR-012 (peça da lista aparece mesmo fora do AB),
SC-004 (sem repetição) e FR-004 (indisponível só sem saldo ou sem nada). A busca de sempre
(`fluxos.buscar`) percorre o catálogo inteiro, então a peça da lista é achada pela pesquisa com o nome
exibido (FR-011b). O catálogo AB não muda (FR-014): a lista não tira nada dele.

**Custo**: `catalogo_ab()` mediu 35 a 57 ms com dados reais (PR #18); a lista soma uma consulta de
cerca de 40 linhas. Sem cache, como os outros.

## R4. A folha: diálogo com a lista inteira, aplicado de uma vez

**Decision**: no passo "Materiais", um botão em destaque "Preencher a lista de peças" abre um
`<dialog>` (tela cheia no celular) com as linhas da lista na ordem: nome, unidade, "Estoque N" e um campo
de quantidade; a linha bloqueada mostra o motivo no lugar do campo. Ao abrir, o diálogo vem do
servidor já preenchido com as quantidades que essas peças têm no pedido. "Pôr no pedido" manda todas as
quantidades de uma vez ao endpoint do carrinho (`folha=1`); o servidor aplica tudo ou nada:
- linha em branco ou zero: a peça sai do pedido (se estava);
- linha preenchida: a peça fica no pedido com essa quantidade (substitui, não soma);
- algum erro (quantidade ilegível, fração em unidade contada, acima do estoque, mais de
  `PEDIDOS_MAX_ITENS` materiais): nada muda, e o diálogo volta com o erro embaixo de cada linha, os
  valores digitados mantidos e o foco no primeiro erro.
Sem erro, o diálogo fecha e o carrinho (revisão) é atualizado; ele continua sendo o lugar de rever,
alterar e remover, inclusive o que veio da folha.

**Rationale**: é a experiência do papel que o usuário pediu ("quem sabe em um modal"): preencher a
folha inteira e entregá-la, sem um passo de confirmação por peça (FR-003). Tudo ou nada evita um pedido
meio aplicado. O carrinho continua sendo o único estado do pedido (campos escondidos `item_codigo`/
`item_qtd`), então o envio, a validação final, o reenvio e o atendimento não mudam. A busca de
materiais fora da lista continua no mesmo passo (FR-003a).

**Ajuste na spec**: o cenário 1 da US1 e o FR-003 diziam "ao abrir o formulário, vê a lista". Com o
diálogo, a lista abre com um toque no passo "Materiais". A spec foi ajustada (ver Clarifications) e a
escolha está aberta à revisão do usuário.

**Alternatives considered**:
- Folha embutida na página, sincronizada linha a linha com o carrinho: 40 linhas empurram a busca e o
  carrinho para baixo no celular, e manter dois lugares de edição sincronizados ao vivo exige muito
  mais JavaScript; rejeitada.
- Adicionar pela lista com o fluxo de sempre (tocar, quantidade, confirmar): é a "confirmação por
  peça" que FR-003 exclui.

## R5. Lógica da folha em `carrinho.py`, pura

**Decision**: `carrinho.aplicar_folha(linhas, fluxo, catalogo, quantidades) -> Carrinho` (sem ORM),
com `Carrinho` ganhando `erros_folha: dict[str, str]` (código → texto). Usa `quantidade`,
`acima_do_estoque`, `motivo_bloqueio` e o `max_itens` de sempre, com os mesmos textos. A view
`materiais._carrinho` ganha os ramos `folha` (aplicar) e `folha_abrir` (desenhar o diálogo preenchido).

**Rationale**: Princípio I; os textos de erro são os de `regras.texto_erro_quantidade` e
`texto_acima_do_estoque` (spec 005), sem texto novo para a mesma causa.

## R6. Destinos por formulário: `Fluxo.centros`

**Decision**: `Fluxo` ganha `centros: Callable[[], list[Centro]] | None = None` (None = todos, como
hoje). O fluxo `viaturas` usa `catalogos.centros_equipe_manutencao()`: os `CentroCusto` marcados,
convertidos em `regras.Centro` **sem placa** (uma opção por descrição). `_contexto` da view pública e
`registrar_pedido` pedem os centros ao fluxo (`servicos.centros_do_fluxo(fluxo)`); o atendimento, a
edição e a saída avulsa continuam com todos os centros (FR-010).

**Rationale**: `opcoes_destino` e `resolver_destino` (puras) já fazem o resto: sem placa nas linhas, a
opção "centro — placa" não aparece e uma placa digitada não resolve (FR-008); um centro fora da lista é
recusado com o texto de hoje (FR-007). Sem centro marcado, `sem_destinos` já mostra o aviso
"Este formulário está indisponível no momento" (`_formulario.html`) e `registrar_pedido` já recusa
(FR-008a). `fluxos.py` não importa `servicos` (que importa `fluxos`): as funções de centros ficam em
`catalogo/catalogos.py`, como as de catálogo.

**Marca do centro**: `CentroCusto.equipe_manutencao = BooleanField(default=False)`, editável na lista
do admin (`list_editable`, `list_filter`). Como um centro pode ter várias linhas (uma por placa), o
centro é de equipe se **alguma** linha dele estiver marcada.

**Alternatives considered**: lista em `Opcao` com a descrição do centro (quebra quando o centro é
renomeado); relação "formulários × destinos" (abstração do painel de configuração futuro, sem segundo
uso agora).

## R7. Número da ocorrência: coluna nova em `Pedido`, só no formulário que pede

**Decision**: `Pedido.ocorrencia = CharField("nº da ocorrência", max_length=20, blank=True,
default="")`; `EnvioPedido.ocorrencia: str = ""`; `Fluxo.pede_ocorrencia: bool = False` (True em
`viaturas`). A view só lê o campo quando o fluxo o pede; `registrar_pedido` grava `texto(ocorrencia)`
só se o fluxo o pede (os outros gravam ""). Validação pura em `regras`:
`MAX_OCORRENCIA = 20` e o erro `"Nº da ocorrência: no máximo 20 caracteres."` no campo `ocorrencia`.
A conferência de reenvio passa a comparar também a ocorrência (`cabecalho_enviado` e o cabeçalho
gravado em `registrar_pedido`). O detalhe e o recibo mostram "Nº da ocorrência" quando preenchido.

**Rationale**: FR-002a. Uma coluna com `default=""` não altera os pedidos existentes nem a conferência
de reenvio dos outros formulários ("" dos dois lados). Usar a observação perderia o campo próprio, a
validação de tamanho e a exibição separada.

**Alternatives considered**: JSON de "campos extras" por formulário (abstração sem segundo uso; o
painel de configuração futuro decide se vale); tabela à parte (uma linha por pedido, sem ganho).

## R8. Saúde do catálogo

**Decision**: `saude._demais` ganha o bloco do formulário de viaturas: "Formulário de reposição de
peças das viaturas: N peças na lista e M materiais do AB." (ok); erro quando indisponível (sem saldo,
nada a oferecer, ou nenhum centro de custo marcado como de equipe de manutenção); aviso com as peças da
lista ocultas no SCPI. O texto "Sem saldo importado: os formulários de limpeza e AB ficam
indisponíveis" passa a citar os formulários públicos em geral. `Situacao` ganha `viaturas` (o número
de peças da lista visíveis) para a visão geral de Automações, ao lado de limpeza e AB.

**Rationale**: FR-013 e FR-008a. A saúde hoje cita os formulários um a um, no código; um formulário
novo precisa da própria linha (lacuna conhecida do PR #18, que só generalizou o lado público).

## R9. Migrations

**Decision**: duas migrations novas, só aditivas:
- `catalogo/0003_pecas_viaturas`: cria `PecaViatura`; acrescenta `CentroCusto.equipe_manutencao`
  (default False).
- `pedidos/0003_viaturas`: acrescenta a escolha `VIATURAS` em `Pedido.origem` (só `choices`) e a
  coluna `Pedido.ocorrencia` (default "").
Nenhuma carga de dados: a lista e a marca dos centros são preenchidas pelo almoxarifado no admin.

**Rationale**: produção com dados reais (constituição, Restrições técnicas). As duas são reversíveis
sem perda dos dados que já existiam. O `deploy/atualizar.ps1` já faz o backup antes de migrar.

## R10. Limite de materiais por pedido

**Decision**: mantém `PEDIDOS_MAX_ITENS = 40` (FR-002: mesmos limites). A lista em papel tem 39 linhas,
e uma reposição raramente usa todas; aplicar a folha que passaria do limite é recusado com o texto de
sempre ("O pedido pode ter no máximo 40 materiais.").

## R11. Testes de JavaScript e conferência no celular

**Decision**: como no projeto todo, os testes não abrem o navegador (Princípio V): os testes de
`pedidos.js` conferem o texto do arquivo, e o diálogo é conferido à mão (quickstart), no celular
(375 px) e no computador, incluindo teclado (Tab, Esc fecha, foco volta ao botão).

## Itens a confirmar com o usuário

- A escolha do diálogo (R4) e o ajuste correspondente na US1 da spec.
- A carga inicial da lista: as 39 linhas do papel precisam ser associadas a códigos do SCPI (uma linha
  por material, as alternativas "ou" desdobradas). É trabalho do almoxarifado no admin, depois da
  implantação; não há importador.
