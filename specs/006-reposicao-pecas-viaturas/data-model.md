# Data Model: Reposição de peças das viaturas

Só mudanças aditivas (research R9). Modelos e campos que não aparecem aqui não mudam.

## `catalogo.PecaViatura` (novo)

A lista de peças comuns das equipes de manutenção: o quadro "Materiais" da folha em papel.

| Campo | Tipo | Regras |
|---|---|---|
| `material` | `OneToOneField(Material, on_delete=PROTECT, related_name="peca_viatura")` | Obrigatório. Uma linha, um material (FR-011a): o banco recusa o mesmo material duas vezes |
| `nome_exibido` | `CharField(max_length=255, blank=True)` | Opcional (FR-011b). Vazio: vale `Material.nome` |
| `ordem` | `PositiveIntegerField(default=0)` | Ordem da folha (FR-011). Empate: pelo nome do material |

- `Meta.ordering = ["ordem", "material__nome"]`; `verbose_name = "peça das viaturas"`,
  `verbose_name_plural = "peças das viaturas"`.
- `__str__`: o nome exibido, ou o material.
- Aparece no formulário enquanto `material.oculto` é falso (FR-012), esteja ou não no catálogo AB.
  Material duplicado aparece bloqueado (mesma regra dos outros formulários).
- Independente de `ItemLimpeza` e do catálogo AB: estar na lista não tira o material de lugar nenhum
  (FR-014).

## `catalogo.CentroCusto` (campo novo)

| Campo | Tipo | Regras |
|---|---|---|
| `equipe_manutencao` | `BooleanField("equipe de manutenção", default=False)` | Marcado pelo almoxarifado no admin (FR-007) |

- Um centro (descrição) é destino do formulário de viaturas se **alguma** das suas linhas (uma por
  placa) estiver marcada. O destino oferecido é só a descrição, sem placa (FR-008).
- Só restringe os destinos do formulário de viaturas; atendimento, edição, saída avulsa e os outros
  formulários continuam aceitando todos os centros.

## `pedidos.Pedido` (escolha e campo novos)

| Mudança | Detalhe |
|---|---|
| `Origem.VIATURAS` | `"VIATURAS"`, rótulo `"Reposição de peças das viaturas"` (só `choices`; a coluna já tem `max_length=20`) |
| `ocorrencia` | `CharField("nº da ocorrência", max_length=20, blank=True, default="")` (FR-002a) |

- `ocorrencia` só é preenchida em pedidos de origem `VIATURAS`; nas demais, sempre "".
- Pedidos existentes não são convertidos (ficam com "").
- Numeração `P-`, situação, atendimento, linhas de saída e lançamento: os de qualquer pedido público.

## Estruturas puras (sem banco)

| Onde | Mudança |
|---|---|
| `pedidos.regras.EnvioPedido` | `ocorrencia: str = ""` |
| `pedidos.regras` | `MAX_OCORRENCIA = 20`; o erro de tamanho entra na validação com `campo="ocorrencia"` |
| `pedidos.regras.cabecalho_enviado` | nas origens públicas, `(solicitante, destino, obs, ocorrencia)` |
| `pedidos.fluxos.Fluxo` | `folha: Callable[[], list[str]] \| None = None`; `centros: Callable[[], list[Centro]] \| None = None`; `pede_ocorrencia: bool = False` (contrato em [contracts/configuracao-fluxo.md](contracts/configuracao-fluxo.md)) |
| `pedidos.carrinho.Carrinho` | `erros_folha: dict[str, str]` (código → texto do erro da linha da folha) |

## Validação (resumo)

| Regra | Onde | Requisito |
|---|---|---|
| Quantidade por unidade e teto no estoque exibido | `regras.validar_pedido` e `carrinho` (sem mudança) | FR-006 |
| Destino entre os centros do fluxo | `regras._erro_destino` com os centros de `Fluxo.centros` | FR-007, FR-008 |
| Ocorrência até 20 caracteres, opcional | `regras` (novo) | FR-002a |
| Material uma vez só na lista | banco (`OneToOneField`) | FR-011a |
| Reenvio idêntico (inclui ocorrência) | `regras.registro_confere` | FR-002a |
| Folha: tudo ou nada, até `PEDIDOS_MAX_ITENS` | `carrinho.aplicar_folha` | FR-003, R4, R10 |

## Estados

Sem estados novos. O pedido de viaturas segue os de qualquer pedido público: aguardando atendimento →
atendido (ou parcial) → linhas de saída `PENDENTE` → lançamento pelo robô.
