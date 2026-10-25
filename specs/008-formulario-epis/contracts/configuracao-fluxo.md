# Contrato: a entrada `epis` de `FLUXOS`

> **Nota (spec 009, 2026-10-23):** `centros` agora é definido nas cinco entradas públicas, como
> `partial(catalogos.centros_do_formulario, ORIGEM)`, que lê a configuração da página Formulários (a
> marca `equipe_manutencao` e os avulsos do formulário foram transcritos e saíram do admin). Veja
> [009 / configuracao-fluxo.md](../../009-configuracao-formularios/contracts/configuracao-fluxo.md).

Usa o contrato da spec 005
([configuracao-fluxo.md](../../005-consistencia-formularios-publicos/contracts/configuracao-fluxo.md)),
os campos opcionais da 006 e o `exemplo_destino` da 007, com **um campo novo**, `exige_autorizacao`.

| Campo | Valor |
|---|---|
| `nome` | `epis` (URL `/pedido/epis/`) |
| `origem` | `EPIS` |
| `titulo` | Equipamentos de proteção individual (EPIs) |
| `catalogo` | `catalogos.formulario_epis` (research R7) |
| `exemplo_busca` | Ex.: luva, capacete, óculos (ajustável ao cadastro real) |
| `exemplo_inicio` | Ex.: luva, botina, capacete, protetor auricular |
| `icone` | `escudo` (novo em `_icone.html`, Lucide `shield`; nenhum ícone atual representa proteção) |
| `exemplo_destino` | o padrão |
| `publico` | `True` |
| `regra_quantidade` | `por_unidade` (padrão) |
| `folha` | `None` |
| `centros` | `None` (todos os centros cadastrados) |
| `pede_ocorrencia` | `False` |
| **`exige_autorizacao`** | **`True`** (novo; padrão `False` nos demais) |

## Campo novo: `exige_autorizacao: bool = False`

Quando `True`:

1. `registrar_pedido` cria a `AutorizacaoPedido` (`AGUARDANDO`) na mesma transação do pedido e agenda,
   no `on_commit`, o aviso à Segurança do Trabalho em vez do aviso ao almoxarifado.
2. A tela de sucesso mostra o texto de "aguardando autorização" e o link da consulta (mensagens.md).
3. O painel, o detalhe e o atendimento tratam a autorização conforme rotas-e-acesso.md.

Quando `False` (limpeza, AB, viaturas, oficina, avulsa): nada muda.

## Regras

1. O núcleo não pergunta pelo nome nem pela origem do fluxo: nenhuma condição `epis` fora de `FLUXOS`,
   `catalogos.py`, `saude.py` e das `choices`; a condição do núcleo é `fluxo.exige_autorizacao`.
2. `fluxo_da_origem(pedido.origem).exige_autorizacao` é como o serviço e as views sabem que o pedido
   tem autorização; a presença da linha de `AutorizacaoPedido` é a fonte de verdade da situação.
3. O formulário de EPIs herda a busca pública (sem código nem grupo), o carrinho e as proteções sem
   alteração.
