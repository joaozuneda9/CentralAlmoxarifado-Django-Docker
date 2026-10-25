# Contrato: a entrada `oficina` de `FLUXOS`

> **Nota (spec 009, 2026-10-23):** `centros` agora é definido nas cinco entradas públicas, como
> `partial(catalogos.centros_do_formulario, ORIGEM)`, que lê a configuração da página Formulários (a
> marca `equipe_manutencao` e os avulsos do formulário foram transcritos e saíram do admin). Veja
> [009 / configuracao-fluxo.md](../../009-configuracao-formularios/contracts/configuracao-fluxo.md).

Usa o contrato da spec 005
([configuracao-fluxo.md](../../005-consistencia-formularios-publicos/contracts/configuracao-fluxo.md))
e os campos opcionais da spec 006
([configuracao-fluxo.md](../../006-reposicao-pecas-viaturas/contracts/configuracao-fluxo.md)), com um
campo de texto novo, `exemplo_destino` (o placeholder do campo de destino; padrão "Posto de trabalho,
placa do veículo ou setor"; viaturas: "Centro de custo da equipe"), research R1.

| Campo | Valor |
|---|---|
| `nome` | `oficina` (URL `/pedido/oficina/`) |
| `origem` | `OFICINA` |
| `titulo` | Oficina mecânica |
| `catalogo` | `catalogos.formulario_oficina` (research R4) |
| `exemplo_busca` | Ex.: filtro de óleo, pneu |
| `exemplo_inicio` | Ex.: filtro, óleo, pneu, aditivo, lâmpada |
| `icone` | `caixa-check` (já existente em `_icone.html`) |
| `exemplo_destino` | Oficina mecânica ou placa da viatura |
| `publico` | `True` |
| `regra_quantidade` | `por_unidade` (padrão) |
| `folha` | `None` (padrão) |
| `centros` | `catalogos.centros_oficina` (research R5) |
| `pede_ocorrencia` | `False` (padrão) |

## Regras

1. O núcleo não pergunta pelo nome nem pela origem do fluxo; nenhuma condição `oficina` fora de
   `FLUXOS`, `catalogos.py`, `saude.py` e as `choices`.
2. `centros` vale só para o formulário público (tela e `registrar_pedido`); atendimento, edição e
   saída avulsa usam todos os centros (`servicos.centros()`), como na 006.
3. `regras.Centro.so_com_placa` só é ligado por `centros_oficina`; nos outros fluxos, `False`, e
   `opcoes_destino` devolve o mesmo de hoje.

## Destinos

| Linha do cadastro de centros | Opção oferecida |
|---|---|
| `OFICINA MECÂNICA`, sem placa | `OFICINA MECÂNICA` |
| qualquer centro com placa `P` | `<descrição> — P` (só nesta forma; a placa digitada também é reconhecida) |
| qualquer outro centro | não é oferecido; enviado, é destino inválido |
