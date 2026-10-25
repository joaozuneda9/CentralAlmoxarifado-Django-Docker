# Design do Central Almoxarifado — Clean

A interface segue o design system **Clean**: editorial, com espaço em branco de sobra,
tipografia precisa e nada de enfeite. A autoridade visual é a skill
`.claude/skills/clean-design/`; onde ela e o projeto divergem, valem as decisões da spec
`docs/superpowers/specs/2026-10-10-interface-clean-design.md` (só tema claro, dois ritmos,
nada de seções de landing page nem *scroll reveal*).

## Arquivos

| Arquivo | O que tem |
|---|---|
| `interface/static/interface/css/clean.css` | `@font-face`, tokens (`:root`), reset, tipografia, foco, utilitários e ritmos |
| `interface/static/interface/css/componentes.css` | botões, campos, cartões, selos, avisos, tabela, paginação, filtros, passos, materiais, carrinho, vazio, dados, ações |
| `interface/static/interface/css/layouts.css` | layout público, casca do almoxarifado, menu móvel e impressão |
| `interface/templates/interface/_icone.html` | ícones SVG inline (Lucide) |
| `interface/static/interface/fonts/` | Geist, DM Sans e Geist Mono em `.woff2`, com as licenças OFL |
| `pedidos/…/pedidos.css`, `catalogo/…/catalogo.css`, `contas/…/entrar.css` | só o que é próprio de cada app |

Nenhum CSS de app redefine componente comum: se faltar algo, ele entra em `componentes.css`.

## Tokens

- **Neutros:** fundo `#FFFFFF` (`--fundo`), superfície `#F7F6F2` (`--superficie`), texto
  `#0F0E0C`, texto secundário `#6B6760`, texto suave `#A8A49F`, borda `#E8E6E1`.
- **Destaque:** `#2563EB` (`--destaque`), hover `#1D4ED8`, texto sobre o destaque `#FFFFFF`,
  superfície `#EFF4FF`. Só em botões primários, links, foco e no item atual do menu.
- **Status** (superfície / texto, sempre com palavra, nunca só cor):
  ok `#ECF7EE`/`#1E6B34`; aviso `#FDF4E3`/`#8A5A00`; erro `#FCEDEC`/`#A3261D`;
  informação `#EFF4FF`/`#1D4ED8`; neutro `#F7F6F2`/`#6B6760`.
- Nenhuma outra cor e nenhum gradiente. A impressão é a exceção: texto preto e bordas cinza.
- **Espaço:** múltiplos de 8 (`--esp-1` = 8px até `--esp-16` = 128px); `--esp-meio` = 4px
  para ajuste fino.
- **Raios:** cartões 12px, botões e campos 8px, selos 100px.
- **Sombras:** cartão `0 1px 3px rgba(0,0,0,.05), 0 1px 2px rgba(0,0,0,.04)`; hover
  `0 6px 20px rgba(0,0,0,.08)`; painel elevado `0 8px 30px rgba(0,0,0,.09)`.

## Tipografia

- **Geist** 600/700 nos títulos, tracking -0.02em.
- **DM Sans** 400/500/600 no texto, entrelinha 1.6.
- **Geist Mono** 400/500 em CADPRO, Nº, placa, matrícula e requisição (classe `.mono`).
- Rótulo de seção (`.rotulo-secao`): DM Sans 500, 12px, maiúsculas, tracking 0.08em, cor suave.
- As fontes são servidas do próprio sistema, com `font-display: swap`: se o arquivo faltar ou
  demorar, o texto aparece na fonte reserva na hora. Nada de Google Fonts ou CDN. Nunca
  Inter, Roboto, Arial ou system-ui.

## Ritmos

Os mesmos tokens em duas densidades, escolhidas pela classe do `<body>`:

| | `.ritmo-publico` | `.ritmo-almox` |
|---|---|---|
| Corpo | 17px | 15px |
| H1 | `clamp(32px, 5vw, 48px)` | 24px |
| Recheio do cartão | 32px | 24px |
| Entre blocos | 48px | 24px |
| Célula de tabela | 12px/16px | 10px/12px |

## Vocabulário de classes

Use estes nomes, e nenhum outro para essas funções.

| Função | Classes |
|---|---|
| Ritmo (no `<body>`) | `ritmo-publico`, `ritmo-almox` |
| Texto | `rotulo-secao`, `texto-secundario`, `texto-suave`, `texto-pequeno`, `mono`, `visually-hidden` |
| Pilhas e grades | `pilha`, `pilha-larga`, `grade-2`, `grade-saida` (+ `grade-saida-largo`, duas colunas nas quatro; `grade-saida-linha`, linha toda nas duas; `grade-saida-cheio`, linha toda nas quatro; dentro de `saida-campos`: colunas pela largura do bloco), `linha` |
| Botões | `botao` + `botao-primario`, `botao-secundario` (com as cores `botao-destaque` azul, `botao-perigo` vermelho e `botao-ok` verde), `botao-texto`, `botao-icone`, `botao-bloco` |
| Campos | `campo`, `campo-rotulo`, `campo-entrada`, `campo-dica`, `campo-erro`, `campo-com-erro`, `campo-check`, `campo-check-caixa`, `campo-rotulo-linha`, `campo-nota`, `campo-linha`, `campo-busca` |
| Diálogo de confirmação | `dialogo-confirmacao` (`<dialog>` modal, com `open` no HTML: sem JavaScript fica à vista como aviso), `dialogo-confirmacao-corpo`, `-texto`, `-titulo`, `-acoes`; `data-abrir-dialogo="id"` no botão que o abre (vem `hidden`), `data-fechar-dialogo` no que fecha (`interface/js/dialogo.js`; o fundo e o Esc também fecham). Foco inicial em `autofocus`: no botão seguro (Cancelar) quando a ação é destrutiva. Usos: "O recibo saiu na impressora?" (`data-apos-imprimir`, aberto pelo `pedidos.js` depois de imprimir) e "Restaurar a regra padrão?" |
| Botão suave | `botao-suave` (azul sutil, com ícone; ação secundária) e, dentro de um campo, `com-acao` em volta dele + `acao-campo` (à esquerda da seta do dropdown) |
| Cartões | `cartao`, `cartao-titulo`, `cartao-sutil`, `cartao-opcao` |
| Abas | `abas` (`[data-abas]`, com `data-url`), `abas-lista` (`role="tablist"`), `aba` + `aba-ativa` (`role="tab"`, `data-aba`), `aba-painel` + `aba-painel-ativo` (`role="tabpanel"`, `id="painel-<chave>"`); `interface/js/abas.js`, na base. Pasta: a aba ativa é branca e se funde ao primeiro `cartao` do painel (filho direto, ou primeiro filho do primeiro filho); os demais cartões ficam soltos embaixo. Estado de cada aba em `selo aba-selo` dentro dela, com o ícone (`alerta`, ou `atualizar` em andamento) e o texto em `aba-selo-texto`: na tela larga aparece o texto; abaixo de 1024px, só o ícone, e o texto fica para o leitor de tela. Abas que não cabem rolam de lado com encaixe no começo de cada aba, e a borda do lado em que a lista continua esmaece (`data-mais-inicio`/`data-mais-fim`, marcados pelo `abas.js`). Link para outra aba da página: `data-abrir-aba="<chave>"` com `href="?aba=<chave>"`. Sem JavaScript, os painéis ficam empilhados |
| Selos | `selo` + `selo-ok`, `selo-aviso`, `selo-erro`, `selo-info`, `selo-neutro` |
| Avisos | `aviso` + `aviso-ok`, `aviso-atencao`, `aviso-erro`, `aviso-info` |
| Tabela | `tabela-rolagem` (sempre em volta da `tabela`), `tabela`, `tabela-data`, `tabela-vazia` |
| Paginação | `paginacao`, `paginacao-resumo`, `paginacao-lista`, `paginacao-link`, `paginacao-atual`, `paginacao-desativado`, `paginacao-reticencia`, `paginacao-larga`, `paginacao-compacta` |
| Dica flutuante | `dica-flutuante` (contêiner do controle) + `dica-flutuante-texto` (`role="tooltip"`, ligado ao controle por `aria-describedby`; aparece com o cursor, o toque ou o foco, também em botão desabilitado); `dica-flutuante-fim` no contêiner alinha a dica ao fim (borda direita) do controle, para controle encostado na borda direita |
| Filtros | `filtros`, `filtros-campo`, `filtros-acoes`; recolhíveis (`filtros.js`, `form[data-filtros]`): `filtros-recolhiveis`, `filtros-barra`, `filtros-busca`, `filtros-alternar` (+ `filtros-contagem`, `filtros-seta`), `filtros-limpar`, `filtros-chips`, `filtros-chip`, `filtros-painel`, `filtros-grade`, `filtros-periodo` |
| Passos | `passo`, `passo-numero`, `passo-cabecalho`, `passo-corpo` (no tablet da área interna, o número fica ao lado do título e o corpo usa a largura toda) |
| Materiais | `lista-materiais`, `material`, `material-bloqueado`, `material-dados`, `material-acao`, `quantidade`, `quantidade-campo`, `botao-adicionado` ("Adicionado" por 2 s); adicionar em dois passos (formulários públicos e saída avulsa; o painel do atendimento adiciona direto): `material-abrir` (botão transparente sobre a linha), `material-mais` ("+"), `material-no-pedido` (selo `selo selo-info`, com `selo-pulso` por 2 s ao confirmar), `material-qtd`, `material-cancelar`, estado `aberto` no `[data-adicionar]`; com um aberto, as outras linhas recuam |
| Pedido (formulários de carrinho) | `pedido-layout` (container query), `pedido-grade` (passos + coluna do pedido lado a lado a partir de 960px de largura), `pedido-passos`, `pedido-lado`, `pedido-resumo` (cartão fixo ao rolar, com o botão de envio em `pedido-enviar`), `acoes-final` (o envio do fim do formulário, só quando o pedido está na gaveta); `pagina-larga` no `<body>` alarga o formulário público para 1080px a partir de 1024px |
| Busca de materiais | `busca-area`, `busca-principal` (campo em destaque: 56px, borda azul de 2px), `busca-painel` (`#resultados`, painel no fluxo da página, logo abaixo da busca, em qualquer tela: o cartão do passo cresce com ele, a página rola para a busca subir e a altura é a do cabeçalho e de 5 linhas) |
| Painel flutuante (base) | `painel-flutuante` (casca; estados `aberto` e `fechando`) |
| Dropdown | `dropdown` (envolve o campo), `dropdown-gatilho`, `dropdown-valor`, `dropdown-seta`, `dropdown-combo`, `dropdown-painel`, `dropdown-lista`, `dropdown-grupo`, `dropdown-opcao`, `dropdown-texto`, `dropdown-check`, `dropdown-sem-opcoes`; montados pelo `dropdown.js` |
| Resultados | `resultados-vazio` ("Nenhum material encontrado."; o painel não tem legenda); `material-info` (linha de baixo do material); com o material no pedido, o botão diz "Alterar (N)" (`pedidos.js`) |
| Carrinho | `carrinho`, `carrinho-barra` (fixa), `carrinho-gaveta` (`<dialog>` sempre que o pedido cairia embaixo da busca, isto é, passo com menos de 760px: `data-gaveta` no `<html>`; bloco azul ao lado da busca nos demais casos), `carrinho-lista`, `carrinho-linha`, `carrinho-linha-erro`; nos formulários públicos e na saída avulsa (com os textos da saída), `carrinho-barra-contagem`, `carrinho-barra-vazia`, `carrinho-acoes-gaveta` (enviar e adicionar mais) e a quantidade em dois passos (`carrinho-qtd-texto`, `carrinho-qtd-area`, `carrinho-confirmar`, `carrinho-cancelar`, `carrinho-remover`; a linha toda é o `material-abrir`, com o lápis `material-mais`, como no resultado da busca; estado `aberto` no `[data-alterar]`) |
| Folha (formulário com lista fixa, spec 006) | `folha-chamada` (botão "Preencher a lista de peças" e a dica), `folha` (`<dialog>`: tela cheia abaixo de 640px, painel centrado com rolagem acima), `folha-corpo`, `folha-cabecalho`, `folha-titulo`, `folha-lista` (`<ol>`), `folha-linha` (+ `folha-linha-bloqueada`, `folha-linha-erro`), `folha-material` (o `<label>` do campo), `folha-qtd`, `folha-motivo` (selo no lugar do campo), `folha-erro`, `folha-acoes` (barra presa embaixo; a rolagem desconta a altura dela); o resumo de erros é o `resumo-erros` |
| Envio recusado (formulário público) | `resumo-erros` (+ `resumo-erros-titulo`, focável, com link para o campo), `campo-com-erro` + `campo-erro` com ícone embaixo do campo; `botao-esquecer` ("Não é você? Limpar"); `sucesso-itens` (lista da tela de sucesso) |
| Recibo e atendimento | `recibo-grupo` (linha de grupo da tabela de materiais: "Pedido pelo solicitante" e o selo `selo-info` "Adicionado pelo almoxarifado", só com material acrescentado; no atendimento, a dos acrescentados some enquanto o grupo está vazio), `recibo-nota` (nota pequena embaixo do nome: "Trocado por …", "No lugar de …"), `atendimento-painel` (+ `atendimento-painel-titulo`; painel de busca da troca e do acréscimo, um `<form>` com os resultados de sempre; na troca, o `pedidos.js` o põe numa `atendimento-painel-linha` logo abaixo do material, preso à esquerda da rolagem) |
| Vazio | `vazio`, `vazio-titulo` |
| Dados | `dados` (`<dl>` em grade de rótulo e valor) |
| Ações | `acoes` |
| Layout público | `publico-topo`, `publico-topo-interno`, `publico-conteudo`, `publico-cabecalho`, `publico-sub`, `publico-rodape`, `marca`, `link-discreto` |
| Casca do almoxarifado | `app`, `app-lateral`, `app-lateral-topo`, `app-lateral-painel`, `app-menu`, `app-menu-item`, `app-menu-botao`, `app-conta`, `app-principal`, `pagina-cabecalho`, `pagina-sub`, `pagina-acoes`, `link-voltar` (bloco `voltar` dos dois layouts, acima do rótulo: no almoxarifado, "Voltar ao painel" em toda página menos o painel; à direita do cabeçalho, só ações) |
| Impressão | `nao-imprimir`, `so-tela`, `folha-recibo` |

## Dropdowns

Todo `select.campo-entrada` e todo `input.campo-entrada[list]` ganha, pelo `interface/js/dropdown.js`,
um painel no mesmo estilo do painel de resultados da busca de materiais: cartão com borda e sombra,
sem legenda (nem rótulo nem contagem: o rótulo do campo vai no `aria-label` da lista), linhas de 14px
com divisória, opção marcada em azul
com o ícone `check` (nunca só a cor). O painel nunca tem caixa de busca: no `select`, digitar pula
para a opção que começa com o que se digitou (as letras se acumulam por 0,8 s).

A base é uma só: `.painel-flutuante` (casca, entrada e saída
animadas, em `componentes.css`) e o `dropdown.js` (abrir e fechar, teclado, ARIA, posição, fechar por
fora). Os tipos só montam o controle: seleção simples (`select`), campo com lista (`input[list]`, texto
livre), select digitável (`select[data-dropdown-digitavel]`: campo de texto que filtra a lista, mas só vale uma
opção dela; placa e centro de custo) e árvore (`select[data-dropdown-arvore]`). A busca de materiais (`#resultados`, `.busca-painel`)
usa a mesma casca e o mesmo abrir e fechar por `window.Dropdown.abrirPainel` e `fecharPainel`: painel
novo é `.painel-flutuante` + o que for só dele. O elemento original continua na página, escondido, e guarda o valor e dispara `change`: HTMX,
formulários e testes não mudam, e sem JavaScript valem os controles nativos. Quem troca o valor de
um `select` por script precisa disparar `change` (o dropdown redesenha ao ouvi-lo). Fora do escopo:
o Django admin e `<input type="date">`.

## Ícones

`{% include "interface/_icone.html" with nome="busca" %}` desenha um SVG inline no estilo
Lucide (traço 1.5, `currentColor`, `aria-hidden`). O conjunto é fechado: `caixa`, `busca`,
`mais`, `menos`, `lixeira`, `impressora`, `sair`, `seta-direita`, `seta-esquerda`, `alerta`,
`check`, `menu`, `fechar`, `painel`, `recibo`, `catalogo`, `cadastros`, `saida`, `enviar`,
`olho`, `robo`, `grafico`, `trocar`, `atualizar`, `caixa-check`, `filtro`, `seta-baixo`, `lapis`,
`usuario`, `cadeado`, `info`, `check-duplo`. Nome
desconhecido não desenha nada. Ícone novo entra no `_icone.html`, com os traços do Lucide.
Nunca emoji na interface.

## Movimento

- Transições de 0.18s em hover e foco; `scale(.98)` no clique dos botões.
- O cartão de opção sobe 2px no hover e a seta anda 4px.
- O cartão de sucesso do pedido entra com 0.4s (`subir`).
- `prefers-reduced-motion: reduce` zera transições e animações.
- Sem *scroll reveal* nem animação de entrada em listas.

## Regras que continuam

- Estado nunca só por cor: todo selo e aviso tem texto.
- Códigos em `.mono`.
- Foco visível: anel de 2px no destaque, afastado 2px (`:focus-visible`).
- Alvos de toque com no mínimo 44px no celular.
- Tabelas sempre dentro de `.tabela-rolagem`: no celular a página não rola de lado.
- Scripts no `<head>` com `defer`; logout por POST num formulário único; o `htmx-config`
  com `noSwap` fica no `base.html`.
- Bloco de cabeçalho vazio (`rotulo`, `sub`) não deixa buraco: o `<p>` do layout fica sem
  espaço dentro e some pelo `:empty`.
- Os resultados da busca de materiais abrem num painel preso ao campo (ao focar, digitar ou
  trocar o filtro) e fecham com Esc ou ao sair da área; sem JavaScript ficam na página. Os
  formulários públicos buscam só pelo nome; a saída avulsa também pelo código.
- Abaixo de 768px, "Seu pedido" vira uma barra fixa no rodapé que abre uma gaveta (`<dialog>`);
  sem JavaScript, ou no desktop, o pedido aparece na página. O material já escolhido ganha o selo
  "No pedido" nos resultados, para as duas listas não se confundirem.
- Até 1286px de largura a barra lateral vira cabeçalho com o botão `menu`/`fechar`
  (`aria-expanded`, Esc fecha). Sem JavaScript, a navegação fica aberta.

## Impressão

`@media print` em `layouts.css` esconde a casca (barra lateral, cabeçalho da página,
mensagens, topo e rodapé públicos), `.nao-imprimir` e `.so-tela`, e tira fundos e sombras.
Em `pedidos.css`, cada `.folha-recibo` sai numa folha, e os selos do recibo viram contorno
cinza com texto preto.

## Tela nova

1. Carregue a skill `clean-design` e leia este arquivo.
2. Estenda `interface/base_publico.html` (blocos `rotulo`, `heading`, `sub`, `page`,
   `rodape`) ou `interface/base_almoxarifado.html` (`rotulo`, `heading`, `sub`, `tools`,
   `page`).
3. Monte a página só com o vocabulário acima. CSS próprio da app fica no CSS da app, carregado
   pelo bloco `extra_css`.
4. Destino novo do menu entra em `ITENS_MENU` (`interface/navegacao.py`) com um ícone do
   conjunto.
5. Confira a 375px, 768px e 1280px.
