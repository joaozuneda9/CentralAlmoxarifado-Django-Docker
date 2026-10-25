# Research: Consistência dos formulários públicos de pedido

Cada item segue **Decisão / Justificativa / Alternativas**. Os fatos vêm da leitura do código em
2026-10-21; nada foi executado. Não há `NEEDS CLARIFICATION` aberto: o que ainda precisa da
confirmação do usuário está em *Itens a confirmar*, no fim.

## R1. Onde fica a lista de unidades fracionáveis

- **Decisão:** um novo valor em `Opcao.Lista` (`UNIDADE_FRACIONAVEL`), lido por
  `Opcao.valores(...)`, como já é feito com `GRUPO_OCULTO_AB`. A migration de dados cria as 10
  unidades (`M`, `MT`, `MTS`, `KM`, `KG`, `L`, `LT`, `M²`, `M³`, `T`).
- **Justificativa:** o mecanismo já existe, tem tela no admin (`OpcaoAdmin`) e o padrão de "lista
  vazia usa um padrão" já é conhecido (`catalogos.grupos_ocultos_ab`). Não cria modelo nem tela
  nova (FR-002).
- **Alternativas:** (a) um modelo `UnidadeFracionavel`: mais código e mais uma tela, sem ganho;
  (b) uma constante no código: exigiria publicar o sistema para ajustar a lista, o que a decisão
  D10 proibiu; (c) uma coluna "fracionável" em `Material`: o cadastro é sobrescrito pelos
  importadores e seriam milhares de materiais para marcar.
- **Atenção:** diferente de `GRUPO_OCULTO_AB`, **lista vazia significa "tudo inteiro"**, não "usar um
  padrão". Por isso a carga vai na própria migration (FR-043), e o teste da migração confere que as
  10 unidades existem depois dela.

## R2. Como o item do catálogo carrega a regra

- **Decisão:** `ItemCatalogo` ganha `fracionavel: bool = False`, calculado em `_item()` a partir de
  `Material.unidade` (a do SCPI), com a lista lida **uma vez por montagem de catálogo**. `unidade`
  continua sendo o texto exibido.
- **Justificativa:** na limpeza, `catalogo_limpeza` sobrescreve `unidade` por `unidade_exibida`
  (por exemplo "Pacote 500 g"); a regra não pode olhar esse campo (FR-004). No AB, `catalogo_ab`
  constrói o item a partir do `Material` do código **canônico**, então a unidade certa já é a dele.
  O padrão `False` protege os testes que montam `ItemCatalogo` direto e é o lado seguro (inteiro).
- **Alternativas:** guardar a unidade do SCPI num campo à parte (`unidade_scpi`) e decidir a
  fração a cada validação, com acesso à lista a cada chamada: espalha leitura da lista pelas
  funções puras, que deixariam de ser puras.

## R3. Comparação da unidade com a lista

- **Decisão:** normalizar os dois lados com `norm_u` (sem acento, maiúsculas, espaços colapsados).
- **Justificativa:** é a comparação que o projeto já usa para códigos (FR-003).
- **Consequência conhecida:** `norm_u` decompõe `²` e `³` (`NFKD`) em `2` e `3`, então `M²` e `M2`
  passam a ser a mesma unidade (e `M³`/`M3`). Na prática é o mesmo significado, e vale para os dois
  lados da comparação.

## R4. Truncagem e máximo pedível

- **Decisão:** duas funções puras em `regras.py`: `truncar_qtd(valor)`, que corta para 3 casas
  (`ROUND_DOWN`), e `maximo_pedivel(estoque, fracionavel)`, que devolve `truncar_qtd(estoque)` se a
  unidade é fracionável e `floor(estoque)` se é contável. A exibição continua usando `qtd_br`, que
  já remove zeros à direita.
- **Justificativa:** é a única conta que faz a lista, o teto e a mensagem usarem o mesmo número
  (FR-009, FR-010). Um saldo de 2,4996 vira 2,499; 0,0004 e 0,5 UN viram 0, e o material fica
  "Sem estoque" (FR-013).
- **Alternativas:** arredondar para cima ou para o mais próximo: aceitaria pedir mais que o saldo
  (rejeitado). Mostrar o saldo bruto de 4 casas e limitar a 3: reproduz o defeito atual.

## R5. Interpretação única da quantidade e tabela de textos

- **Decisão:** `interpretar_quantidade(texto, fracionavel)` devolve `(valor, causa)`, com causas
  nomeadas: `ilegivel`, `fracao_em_contavel`, `acima_do_maximo` e `zero`. Uma tabela única mapeia
  cada causa ao texto (ver [contracts/mensagens.md](contracts/mensagens.md)). O carrinho
  (adicionar e alterar) e a validação do envio usam as duas.
- **Justificativa:** resolve o defeito de dois textos para a mesma causa (FR-022) e o da mensagem
  enganosa acima de 999.999 (FR-007).
- **Refinamento da spec:** para material **contado**, uma quantidade ilegível diz "Informe um número
  inteiro maior que zero." (o texto atual do AB); sugerir vírgula para decimais seria enganoso. Para
  material fracionável vale "Informe uma quantidade maior que zero (use vírgula para decimais, ex.:
  1,5)." A FR-007 da spec foi ajustada para dizer isso.
- **Alternativas:** manter `parse_inteiro` e `parse_qtd_br` e escolher por `Fluxo.inteiro`: é a
  ramificação que a decisão D1 elimina.

## R6. A configuração de cada formulário (`Fluxo`)

- **Decisão:** `Fluxo` troca `inteiro`, `com_estoque` e `limita_estoque` por `regra_quantidade`
  (`"por_unidade"` para os públicos, `"livre"` para a equipe) e passa a carregar o que hoje está
  fixo nos templates ou espalhado: `catalogo` (função), `exemplo_busca`, textos de título, e os
  rótulos que já existem. Ver [contracts/configuracao-fluxo.md](contracts/configuracao-fluxo.md).
- **Justificativa:** é a decisão D19 (cada formulário é uma entrada de configuração sobre um núcleo
  único). Evita as ramificações por nome (`fluxo.nome == "limpeza"` em `_materiais.html:51` e
  `fluxo.nome == "ab"` em `_formulario.html:9`) e por origem.
- **Alternativas:** uma classe por formulário, com herança: descartada na decisão D19 porque o
  cabeçalho e o lançamento no SCPI são iguais e o núcleo é compartilhado com a saída avulsa e o
  atendimento.
- **Cuidado:** `fluxos.py` e `servicos.py` se importam de forma circular hoje (a importação de
  `carrinho` dentro das funções de `fluxos.py` evita isso). O `catalogo` do `Fluxo` aponta direto
  para as funções de `catalogo/catalogos.py`; `servicos.catalogo_de(origem)` apenas consulta o
  `Fluxo`.

## R7. Uma só validação de envio

- **Decisão:** `validar_pedido(envio, catalogo, centros)` substitui `validar_pedido_limpeza` e
  `validar_pedido_ab`, usando `interpretar_quantidade` e `maximo_pedivel` por item. As mensagens
  vêm da mesma tabela do carrinho.
- **Justificativa:** as duas funções diferem só na conversão da quantidade e no teto, que agora vêm
  do item (FR-038). O comportamento restante (nome, destino, itens vazios, duplicado, fora do
  catálogo, soma por código) é idêntico.
- **Cuidado:** `Validacao.estoque_atual` (usado para o aviso na tela) passa a ser o máximo pedível.

## R8. Regras da equipe

- **Decisão:** `regra_quantidade="livre"` para a saída avulsa e para o atendimento: `parse_qtd_br`,
  fração em qualquer unidade, teto igual a `truncar_qtd(estoque)`. Saem `regra_inteira` de
  `validar_saida`, as duas escolhas `parse_inteiro if pedido.origem == AB` de `servicos.py`
  (linhas 629 e 854), a escolha `FLUXOS["ab"] if pedido.origem == AB` de `atendimento_adicionar`
  e o `inputmode` por origem de `_adicionado.html` e `_recibo_item.html`.
- **Justificativa:** decisão D15. Isso corrige também a fração cortada no atendimento.
- **Efeito:** `_limites_de_estoque` e a mensagem "Saída de X maior que o estoque (…)" passam a usar o
  mesmo teto truncado.

## R9. Formatador único para quantidades

- **Decisão:** `qtd_br` (3 casas, vírgula, sem separador de milhar e sem zeros à direita) é o
  formato para campos, avisos e Telegram. `almoxarifado._formatar_qtd` e `telegram._quantidade`,
  que hoje fazem `int(q)` para o AB, passam a chamá-lo. O filtro de exibição `quantidade` (com
  separador de milhar) continua nas tabelas e não é tocado.
- **Justificativa:** corrige o corte silencioso (FR-032) sem criar um terceiro formatador.

## R10. Estados do catálogo e aviso de saúde

- **Decisão:**
  - `catalogo_de` devolve `None` (indisponível) quando o saldo nunca foi importado **ou** o
    catálogo não tem item algum, para os dois formulários (hoje o AB vazio devolve `[]`).
  - A tela ganha um aviso de "sem estoque agora" quando todos os itens têm máximo pedível 0.
  - `saude.py::_demais` passa a dizer "formulários" onde diz "formulário AB" e a emitir um item de
    saúde de erro quando um formulário tem zero itens; o de limpeza hoje é sempre "ok".
- **Justificativa:** FR-016 a FR-018. `saude_do_catalogo` já monta o `CatalogoAB`, então o aviso não
  custa uma consulta a mais.
- **Alternativa:** o aviso de saúde só para o AB: deixaria a limpeza vazia sem sinal.

## R11. Erros por item sem perder o pedido

- **Decisão:** `carrinho.ler(..., manter_ilegiveis=True)` mantém a linha cujo par código/quantidade
  não converte, guardando o texto digitado; `publico.formulario` usa esse modo ao devolver o
  formulário recusado. O `_carrinho` público também preserva essas linhas ao adicionar, alterar
  ou remover materiais, até a quantidade ser corrigida ou a linha ser removida explicitamente.
  Somar ao próprio material com quantidade inválida é recusado, mantendo o texto anterior.
- **Justificativa:** FR-020 e FR-021 também durante a recuperação do pedido. O envio marca os
  códigos recusados pela validação; as operações do carrinho mantêm "Corrigir" nas linhas cuja
  quantidade não converte. A saída avulsa continua descartando pares ilegíveis.
- **Fora do escopo:** botão de ajuste automático ao estoque (FR-023).

## R12. Mensagens de recusa de proteção

- **Decisão:** `protecao.recusar` passa a devolver o **motivo** (`isca`, `rapido` ou `None`);
  `MENSAGEM_EXPIRADO` vira `MENSAGEM_TOKEN_INVALIDO`; `MENSAGEM_RAPIDO` é nova; `MENSAGEM_RECUSA`
  (genérica) fica só para a isca (FR-024 a FR-027).
- **Justificativa:** a pessoa que reenvia logo após "ingresso inválido" cai no tempo mínimo, porque o
  ingresso novo nasce com `aberto_em` igual a agora; o texto "aguarde alguns segundos" resolve sem
  enfraquecer a proteção.
- **Alternativa rejeitada:** emitir o ingresso novo "já maduro" (com `aberto_em` no passado):
  permitiria burlar o tempo mínimo com um envio de ingresso falso.

## R13. JavaScript como requisito

- **Decisão:** um `<noscript>` com o aviso no `formulario.html`, mais uma regra de CSS para esconder o
  formulário quando `html` não tem a classe `js`. Comentários e texto que prometem funcionamento sem
  JavaScript são removidos ou corrigidos (levantamento: `_materiais.html:10,19`, `_carrinho.html:3,40`,
  `_resultados.html:18` e `pedidos.css:32,49`). As regras `.js ...` do CSS continuam: a classe `js`
  segue sendo colocada pelo `base.html`.
- **Justificativa:** FR-029 e FR-030, com o menor número de arquivos tocados. Refatorar todo o CSS
  `.js` seria mudança sem ganho para o usuário.
- **Não confundir:** os comentários "sem JavaScript" da área do almoxarifado (recibo, impressão,
  atendimento) tratam de telas que **funcionam** sem JavaScript e não fazem parte desta mudança.

## R14. Catálogo fora do bloqueio da numeração

- **Decisão:** em `registrar_pedido`, `catalogo_de(origem)` e `centros()` passam a ser carregados
  **antes** de `with transaction.atomic()`, dentro do qual ficam `travar_sequencia()`, o reenvio, os
  limites, a validação e a gravação. A ordem das respostas (reenvio, limite, indisponível, validação)
  não muda.
- **Justificativa:** o estoque é só um teto, nada é reservado, então uma diferença de milissegundos
  entre carregar e gravar não muda o resultado (FR-035). O custo é montar o catálogo também num
  reenvio, que é raro.
- **Teste:** conferir a ordem das chamadas (o catálogo é pedido antes de a sequência ser travada) e
  que `test_envio_duplo_simultaneo_grava_um_pedido` continua passando.
- **Medição (FR-036):** um trecho somente leitura em [quickstart.md](quickstart.md) mede
  `catalogo_ab()` e o número de consultas com dados reais. O resultado é registrado em *Medição*,
  abaixo, por quem tem acesso aos dados. Cache só entra com nova decisão.

## R15. Origens e formulários futuros

- **Decisão:** as ramificações `origem in (LIMPEZA, AB)` (`regras.py:850`, `servicos.py:199`) viram
  `origem_publica(origem)`, isto é, `origem != AVULSA`. Um formulário novo precisa de um valor novo em
  `Pedido.Origem` (migration só de choices, **não incluída aqui**) e de uma entrada em `FLUXOS`.
- **Justificativa:** FR-040 e FR-041. O limite por nome (`servicos._limite_atingido`) passa a valer
  também para os formulários novos, que é o desejável.
- **Fora do escopo:** criar a origem ou o formulário novo.

## R16. Documentação no mesmo PR

- **Decisão:** a spec principal (§4 catálogos e §5 fluxo 1), o `CLAUDE.md` (seções de quantidades,
  indisponível, equipe e JavaScript), o docstring de `fluxos.py` e os comentários dos templates são
  corrigidos no mesmo PR (FR-042 e a regra da constituição).

## R17. Verificação

- **Decisão:** testes automáticos em MariaDB para toda a lógica (matriz de SC-001, estados do
  catálogo, migração, formulário de teste de SC-007, equipe, Telegram); testes de JavaScript só de
  texto, dito como limite; conferência manual em tela de celular (375 px) com a lista do quickstart.
- **Justificativa:** constituição, Princípio V, e SC-010.

## Itens a confirmar (não bloqueiam o plano)

1. ~~Exibição do estoque na saída avulsa.~~ **Resolvido em 2026-10-21 pelo usuário:** a avulsa também
   mostra o saldo truncado a 3 casas, mantendo código, unidade e classe. A spec (FR-033 e US6) foi
   ajustada. `Resultado.estoque` da avulsa deixa de usar `qtd_estoque` (4 casas) e passa a usar
   `truncar_qtd` + `qtd_br`; os testes `test_carrinho.py:466-481` (que fixam "Estoque 0,0004" e
   "Estoque 2,4996") mudam de acordo.
2. ~~Unidade do código canônico no AB.~~ **Conferido em 2026-10-21** no banco de desenvolvimento:
   dos 397 pares de/para, 89 têm unidade diferente entre o código antigo e o novo (por exemplo
   `MTS` → `MT`, `UN` → `BR`, `PC` → `UN`), então a escolha importa; `catalogo_ab` constrói o item
   do `Material` do canônico, e `tests/test_catalogos.py` cobre o caso.
3. ~~Medição do catálogo do AB.~~ **Feita em 2026-10-21** (ver *Medição*): tempo da ordem de 40 ms, sem justificativa para cache.

## Medição

| Data | Ambiente | Tempo de `catalogo_ab()` | Nº de consultas | Observação |
|---|---|---|---|---|
| 2026-10-21 | Servidor em `http://45.172.240.231:8010`, medição indireta por HTTP (24 GETs, 8 rodadas, 1 s entre elas) | `/pedido/ab/materiais/?q=`: primeiro byte entre 0,14 e 0,19 s (média 0,17 s); `/pedido/limpeza/materiais/?q=`: mediana 0,13 s (um pico isolado de 0,86 s); página inicial, sem catálogo: mediana 0,12 s | Não medido (só pelo shell do projeto) | Sobra cerca de 40 a 50 ms para o AB sobre a linha de base, incluindo a montagem do catálogo, o filtro e a renderização de 50 linhas: a montagem sozinha fica abaixo disso. Não prova nada sobre concorrência, o envio (POST) nem o tamanho dos dados. Resposta do AB com 146 KB para 50 resultados (limpeza: 108 KB). Resta rodar o trecho do quickstart para o tempo exato e o número de consultas |
| 2026-10-21 | Banco de desenvolvimento local, com dados reais (11.597 materiais, 5.079 saídas), medição direta pelo shell do projeto, 5 execuções | `catalogo_ab()`: 35 a 57 ms (a primeira, mais lenta; as demais, 35 a 39 ms), 377 itens; `catalogo_avulsa()`: 23 a 26 ms, 1.382 itens; `catalogo_limpeza()`: 2 ms, 38 itens | 8 (AB), 2 (avulsa), 2 (limpeza) | Abaixo dos 100 ms da faixa em que só tirar a conta da fila única basta: **cache não se justifica** e fica fora desta funcionalidade. Confirma a estimativa indireta por HTTP. O que ainda não foi medido: concorrência real e o envio (POST) em produção |
