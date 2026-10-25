# Pesquisa: Configuração das opções por formulário

Evidências primárias: `catalogo/catalogos.py`, `catalogo/models.py`, `pedidos/fluxos.py`,
`pedidos/servicos.py`, `pedidos/regras.py`, `pedidos/views/`, `contas/`, `interface/navegacao.py`, as
migrations e as specs 005 a 008. Números do banco local de desenvolvimento (podem diferir da produção):
11.597 materiais (7.322 visíveis), 244 linhas de centro (149 com placa, 2 de equipe de manutenção);
catálogos de 38 (limpeza), 377 (AB), 382 (viaturas), 122 (oficina), 83 (EPIs); o AB calcula em 0,06 s.

## R1. Chave do formulário

**Decisão**: o formulário é identificado pelo valor de `Pedido.Origem` (`LIMPEZA`, `AB`, `VIATURAS`,
`OFICINA`, `EPIS`), o mesmo que `Fluxo.origem`. Um `TextChoices` `Formulario` em `catalogo/models.py` lista
os cinco (sem `AVULSA`), com os valores vindos de `pedidos.regras` (o `catalogo` já importa `regras`).

**Justificativa**: já é o identificador estável gravado nos pedidos e usado por `fluxo_da_origem`; não cria
uma tabela de formulários (não há construtor de formulários, FR-001).

**Alternativas**: tabela `Formulario` (rejeitada: formulário é código, não dado); `Fluxo.nome` (rejeitada:
é o trecho da URL, mais fácil de mudar).

## R2. Modelo da disponibilidade de materiais: exceções

**Decisão** (do usuário, 2026-10-23): uma tabela `ExcecaoMaterial` (material, formulário, `habilitado`
verdadeiro = acrescenta, falso = retira), única por (material, formulário). **Sem linha, vale a regra de
origem de hoje.** A disponibilidade efetiva é calculada, nunca guardada:

```
efetiva = (regra_de_origem − retirados) ∪ acrescentados      (sempre sem os ocultos do cadastro)
```

**Justificativa**: preserva o AB dinâmico, não exige migrar disponibilidade e guarda só o que o
administrador mudou. O custo na leitura é uma consulta pequena por formulário (as exceções são poucas).

**Alternativas**: lista explícita por formulário (rejeitada pelo usuário: congela o AB e exige decidir item
a item); uma tabela única de associação com `habilitado` nos dois sentidos para materiais e centros
(rejeitada: centros não têm regra de origem; é presença/ausência, e juntar os dois mistura semânticas).

## R3. Regra de origem

**Decisão**: a regra de origem de cada formulário continua nas funções de `catalogo/catalogos.py`
(`catalogo_limpeza`, `catalogo_ab`, `catalogo_viaturas` mais o AB, `catalogo_oficina`, `catalogo_epis`), com
uma mudança: `catalogo_oficina` e `catalogo_epis` passam a ser **só os grupos** (o ramo
`Q(material_oficina__isnull=False)` / `Q(material_epi__isnull=False)` sai); os avulsos viram exceções
`habilitado=True` (R6). `formulario_*` passa a ser `aplicar_excecoes(origem, base)`. Uma função
`regra_de_origem(origem)` (a mesma base, sem o corte "indisponível") serve à tela.

**Aplicação das exceções** (`aplicar_excecoes`):

1. Uma consulta lê as exceções do formulário (`{material_id: habilitado}`), outra os materiais acrescentados
   (visíveis, `oculto=False`).
2. Retirados saem da base (por `norm_u(código)`, como o resto do catálogo); acrescentados que a base já traz
   são ignorados (sem duplicar).
3. Ordem: os acrescentados vêm **ao fim, em ordem alfabética (nome, código)** (esclarecimento a2); em
   oficina e EPIs, cujo catálogo é alfabético por inteiro, a lista toda é reordenada por (nome, código)
   para manter a ordem de hoje.
4. `duplicado` continua aparecendo bloqueado; estoque, teto e regra de quantidade seguem em
   `carrinho.motivo_bloqueio` / `maximo_pedivel`, depois (FR-019). `oculto` nunca é oferecido (FR-018).

**Justificativa**: o `catalogo` do `Fluxo` continua sendo uma chamada sem argumento que devolve
`list[ItemCatalogo] | None`; busca, carrinho, `validar_pedido` e `registrar_pedido` já validam contra ele,
então **a validação no backend (FR-020) acontece sem tocar neles**.

**Ponto de atenção (AB)**: o AB lista códigos canônicos (de/para). Acrescentar a um formulário um código
**antigo** de um par faz o formulário oferecer esse código com o saldo dele; a tela marca o material como
"código antigo (use o canônico)" ao acrescentar. Não bloqueia.

## R4. Centros de custo: modelo e modos de apresentação

**Decisão**:

- `CentroCusto.ativo` (booleano, padrão verdadeiro): estado global (FR-008).
- `CentroFormulario(centro, formulario)`: a **presença** da linha diz que a linha do cadastro (centro mais
  placa) é destino naquele formulário; única por par; guarda quem e quando (FR-031).
- `catalogos.centros_do_formulario(origem)` lê as linhas ativas e habilitadas do formulário e as apresenta
  pelo **modo de destino** do formulário (propriedade do formulário, não configuração):

| Formulário | Modo | Resultado para as linhas habilitadas e ativas |
|---|---|---|
| limpeza, AB, EPIs | `padrao` | cada linha como `Centro(descrição, código, placa)`; `opcoes_destino` gera a descrição e, para linha com placa, "descrição — placa" (igual a hoje) |
| viaturas | `sem_placa` | uma por descrição (a primeira por código), sem placa (igual a hoje) |
| oficina | `oficina` | linha com placa vira `so_com_placa=True` ("descrição — placa" só); linha sem placa vira o centro simples (hoje só "OFICINA MECÂNICA") |

- `Fluxo.centros` continua sendo um `Callable[[], list[Centro]]`; as cinco entradas apontam para
  `partial(centros_do_formulario, ORIGEM)`. A avulsa segue com `None`.
- `servicos.centros()` (todas as linhas) segue como está, para atendimento, edição e robô (FR-012).
  Surge `servicos.centros_ativos()` para a saída avulsa **nova** (R5).

**Justificativa**: o código atual já separa "o que o formulário aceita" (`Fluxo.centros`) de "tudo"
(`centros()`); só muda a origem da lista. Os três modos transcrevem exatamente `centros_equipe_manutencao`,
`centros_oficina` e o padrão, sem generalizar.

**Alternativas**: associação por descrição em vez de por linha (rejeitada: a oficina precisa de cada placa
como destino, e a spec FR-007 fixa a linha); um campo de modo configurável (rejeitada: é característica
fixa do formulário, ver "Fora do escopo").

## R5. Centro inativo e a parte interna

**Decisão** (do usuário): inativo some dos formulários públicos (R4 filtra `ativo`) e da **saída avulsa
nova**; atendimento, edição (inclusive de saída avulsa já registrada) e robô resolvem qualquer linha.

Pontos de contato, todos em `pedidos`:

- `views/almoxarifado.opcoes_saida(*, so_ativos=False)`: a view `avulsa` (nova) passa `so_ativos=True`;
  atendimento e edição seguem com todos.
- `servicos._validar_saida_avulsa(..., centros_validos)`: `registrar_saida_avulsa` passa `centros_ativos()`;
  `editar_saida_avulsa` e o atendimento passam `centros()`.
- `scpi/requisicoes.py` e `regras.resolver_centro_custo` não mudam (já recebem a lista completa).

**Justificativa**: o robô resolve por nome entre `centros()`; filtrar por ativo ali faria o lote pendente de
um centro inativado virar `ERRO` (Princípio III e Princípio IV: nada que o robô lançaria pode se perder).

## R6. Migração inicial e verificação

**Decisão**: duas migrations aditivas, `catalogo/0006_configuracao_formularios` (o esquema) e
`catalogo/0007_transcrever_configuracao` (os dados), separadas porque o DDL do MySQL não é
transacional: se a transcrição falhar, o esquema já está concluído e a nova tentativa roda só a
transcrição, idempotente. Em duas partes:
esquema (`ativo`, `CentroFormulario`, `ExcecaoMaterial`) e dados (`transcrever`, uma função de módulo
chamável `(apps, schema_editor)`, como `carregar_unidades` da 0002, sem reversão destrutiva: desfazer a `0007` não apaga nada, porque as tabelas já guardam também as
escolhas do administrador; a carga é atômica e só roda com as tabelas vazias, para nunca recolocar o que o administrador tirou):

| Origem hoje | Vira |
|---|---|
| limpeza, AB, EPIs: todos os centros | `CentroFormulario` de **todas** as linhas, nos três |
| viaturas: linhas com `equipe_manutencao` | `CentroFormulario` dessas linhas, em viaturas |
| oficina: a linha sem placa de "OFICINA MECÂNICA" (a primeira por código) e toda linha com placa | `CentroFormulario` dessas linhas, em oficina |
| `MaterialOficina` | `ExcecaoMaterial(OFICINA, habilitado=True)` |
| `MaterialEpi` | `ExcecaoMaterial(EPIS, habilitado=True)` |

- A migration **não apaga nem altera** `MaterialOficina`, `MaterialEpi` nem `equipe_manutencao` (os dados
  ficam; saem só do admin e deixam de valer, esclarecimento a3).
- **Verificação (FR-037, FR-038)**: no fim de `transcrever`, a migration recalcula, para cada formulário, as
  descrições de destino pela regra antiga (embutida na própria migration, sem importar código do app) e
  compara com o que a tabela nova produz; se diferirem, levanta erro e a migration não conclui. Sem o centro
  da oficina cadastrado, a regra antiga já dava lista vazia e a transcrição também (equivalente; a saúde
  avisa).
- Materiais ocultos com `MaterialOficina` ou `MaterialEpi` viram exceção e continuam sem aparecer (oculto
  prevalece, FR-018).
- Os testes de regressão comparam o catálogo e os destinos de cada formulário antes e depois, contra uma
  cópia congelada da regra antiga (SC-001).

**Justificativa**: nada a decidir caso a caso; cada regra antiga é determinística e a verificação interna
garante equivalência no próprio banco de produção.

## R7. Esclarecimento a1: centro novo sem formulário

`CentroCusto` nasce com `ativo=True` e **nenhuma** linha em `CentroFormulario`. A saúde ganha o aviso
"centro ativo sem formulário". Na prática, o centro criado no admin aparece na aba Centros de custo como
"sem formulário", com o botão de habilitar. Os testes e `tests/cenario.py` ganham um auxiliar que cria
centros já habilitados nos cinco formulários, para os testes existentes não mudarem de comportamento.

## R8. Permissões

**Decisão**: ver a página é `@login_required` (a Segurança do Trabalho já é barrada pelo middleware de
lista fechada; a rota nova **não** entra em `ROTAS_SEGURANCA_TRABALHO`). Gravar exige `is_staff` mais a
permissão do Django do cadastro afetado:

| Ação | Exige |
|---|---|
| habilitar e desabilitar centros por formulário; ativar e inativar centro | `catalogo.change_centrocusto` |
| exceções de material, restaurar, lote | `catalogo.change_excecaomaterial` |

O superusuário passa em tudo; o staff comum precisa ter a permissão dada no admin (documentado no
quickstart). Resposta 403 sem a permissão, também com o formulário forjado. Nenhum papel novo (FR-032).

**Alternativas**: um único atributo (rejeitada: a spec diferencia quem gerencia centros de quem habilita
materiais); permissão personalizada (rejeitada: o Django já gera as `change_*` dos modelos novos).

## R9. A tela: simples, no servidor, sem JavaScript novo

- Rota `/painel/catalogo/formularios/` (`catalogo:formularios`), item "Formulários" na barra lateral.
- Seletor de formulário (links) e, dentro, as abas **Centros de custo** e **Materiais** (`abas.js`, `?aba=`).
- **Materiais**: busca (código e nome), filtro por grupo e subgrupo e por estado (disponível, indisponível,
  com exceção), em `form[data-filtros]` (`filtros.js`); lista **paginada em 50** no servidor; cada linha com
  o estado, a origem e um botão (Acrescentar, Retirar ou Restaurar regra) que é um `<form>` POST com CSRF.
- **Lote** em dois passos, também sem JavaScript: o botão do filtro abre uma tela de **prévia** (formulário,
  ação, número exato, amostra) com o botão de confirmar; o POST leva o número esperado e é recusado se o
  filtro mudou entre a prévia e a confirmação; sem filtro (catálogo inteiro), a confirmação exige marcar
  "Estou ciente".
- **Por material**: `/painel/catalogo/formularios/material/<código>/` mostra os cinco formulários com
  estado e origem (história 4).
- **Centros**: tabela agrupada por descrição, uma linha por placa, com a marca "neste formulário" e o
  estado global; nas **viaturas** (modo `sem_placa`) a marca é da descrição (todas as linhas juntas,
  FR-007a); criar e editar centro leva ao admin (já existente). Sem HTMX obrigatório: PRG (POST,
  mensagem, redirecionamento), como as ações de Automações.

**Justificativa**: o catálogo é grande; busca, filtro e paginação no servidor evitam carregar 7.322 itens;
PRG e formulários comuns seguem o padrão de `automacoes` e dispensam JavaScript novo (Constituição VI).

## R10. Lote: atômico e mínimo

`aplicar_em_lote(formulario, materiais, acao, usuario)` roda numa transação: para cada material do filtro
decide pelo estado efetivo (pura) e grava **a menor mudança**: acrescentar um material que a regra traz e
estava retirado apaga a exceção; acrescentar o que a regra não traz cria `habilitado=True`; retirar o que a
regra traz cria `habilitado=False`; retirar o acrescentado apaga a exceção. Devolve quantos mudaram e
quantos já estavam assim. Usa `bulk_create(update_conflicts=True)` e `delete` por IN, em lotes de 1.000.

## R11. Saúde, admin e documentação

- `saude._viaturas/_oficina/_epis/_demais` trocam `centros_equipe_manutencao` e `centros_oficina` por
  `centros_do_formulario`; avisos novos: formulário sem destino (os cinco), centro ativo sem formulário e
  exceção sem efeito (retirar o que a regra não traz, acrescentar o que ela já traz).
- Admin: `CentroCustoAdmin` mostra e edita `ativo`, deixa de mostrar `equipe_manutencao`; `MaterialOficinaAdmin`
  e `MaterialEpiAdmin` saem. `Opcao`, `ItemLimpeza` e `PecaViatura` ficam.
- `CLAUDE.md`, `docs/` e os contratos de `005`/`006`/`007`/`008` que falam em `Fluxo.centros` e nos avulsos
  ganham a nota da nova fonte (no mesmo PR, Constituição).

## R12. Concorrência e histórico

- Cada gravação é uma operação curta; a unicidade (material, formulário) e (centro, formulário) no banco
  impede duplicata em gravações simultâneas, e a última vence (spec, Edge Cases).
- Nenhum pedido, atendimento, linha, item ou recibo lê a configuração depois de gravado (FR-033, FR-034);
  `validar_pedido` só a lê no envio, pelo catálogo e pela lista de centros que já recebe.
- Reenvio igual: `registrar_pedido` confere o registro gravado **antes** de validar (já é a ordem de hoje),
  então confirma mesmo com a configuração mudada (FR-035).
