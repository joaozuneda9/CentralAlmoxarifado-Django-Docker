# Modelo de dados: Formulário de EPIs

Quatro mudanças aditivas, em três migrations novas (nunca regeneradas). Nenhum dado existente é
alterado.

## `pedidos.AutorizacaoPedido` (novo)

Uma linha por pedido de um formulário que exige autorização (hoje, só EPIs).

| Campo | Tipo | Observação |
|-------|------|-----------|
| `pedido` | `OneToOne(Pedido, CASCADE, related_name="autorizacao")` | apagar o pedido leva a autorização |
| `situacao` | `CharField(12, choices)` | `AGUARDANDO`, `AUTORIZADO`, `RECUSADO`; nasce `AGUARDANDO` |
| `decidido_por` | `FK(AUTH_USER_MODEL, PROTECT, null, related_name="+")` | quem decidiu |
| `decidido_em` | `DateTimeField(null)` | quando |
| `motivo` | `CharField(200, blank)` | só na recusa; mesmo limite de `PEDIDOS_MAX_TEXTO` |

**Constraints** (`CheckConstraint`, o banco é a última defesa):
- `AGUARDANDO` ⇒ `decidido_por` e `decidido_em` nulos e `motivo` vazio.
- `AUTORIZADO` ⇒ `decidido_por` e `decidido_em` preenchidos e `motivo` vazio.
- `RECUSADO` ⇒ `decidido_por` e `decidido_em` preenchidos e `motivo` não vazio.

**Transições** (definitivas, FR-010):

```text
(nasce) AGUARDANDO ──autorizar──▶ AUTORIZADO
            └────────recusar───▶ RECUSADO (com motivo)
```

Não há volta. `AUTORIZADO` é pré-requisito do atendimento. `PROTECT` em `decidido_por` impede apagar
quem decidiu (o usuário se desativa, não se apaga).

**Acesso por `Pedido`**: `Pedido.autorizacao_ou_none` (como `atendimento_ou_none`) e
`Pedido.situacao` passando `self.autorizacao.situacao` quando há.

## `pedidos.Pedido.Origem` — valor novo

`EPIS = regras.EPIS, "Pedido de EPIs"` (`choices`; migration de `AlterField`, sem SQL de dados). A
constante `EPIS = "EPIS"` entra em `regras.py` ao lado de `OFICINA` e conta como origem pública
(`origem_publica`, limite por nome e conferência de reenvio como as outras).

## `catalogo.MaterialEpi` (novo)

Material avulso do formulário de EPIs (além dos grupos da lista).

| Campo | Tipo |
|-------|------|
| `material` | `OneToOne(Material, PROTECT, related_name="material_epi")` |

Espelho de `MaterialOficina`: uma linha por material, de qualquer grupo; retirar a linha não tira o
material se o grupo dele for de EPI.

## `catalogo.Opcao.Lista` — valor novo

`GRUPO_EPI = "GRUPO_EPI", "Grupos (EPIs)"` (migration de `choices`). Os grupos de EPI ficam em `Opcao`
como os da oficina, comparados por `_grupo`. A carga inicial (quais grupos) é do almoxarifado, pelo
admin; as migrations não carregam dados de catálogo.

## `contas` — grupo novo (migration de dados)

`django.contrib.auth.models.Group` com o nome `Segurança do Trabalho` (constante
`contas.acesso.GRUPO_SEGURANCA_TRABALHO`). A migration o cria se não existir e não faz nada ao
reverter. Nenhuma permissão é atribuída ao grupo: o acesso é a participação, conferida por
`contas.acesso.da_seguranca_trabalho` (R4).

## Funções puras (sem ORM, `pedidos/regras.py`)

- `situacao_pedido(origem, atendido, itens, autorizacao=None)`: ver R2.
- `texto_situacao_consulta(autorizacao, motivo)`: o texto da consulta pública, só situação e motivo (R6).
- Constantes: `EPIS`, `AUTORIZACAO_AGUARDANDO`, `AUTORIZACAO_AUTORIZADA`, `AUTORIZACAO_RECUSADA`.

## Mapa spec → dados

| Spec | Onde fica |
|------|-----------|
| FR-008, FR-010 | `Pedido.origem = EPIS`, `AutorizacaoPedido.situacao` |
| FR-012, FR-013 | `AutorizacaoPedido.decidido_por/em/motivo` |
| FR-017, FR-019 | `Group` "Segurança do Trabalho" |
| FR-029 | `Opcao.GRUPO_EPI`, `MaterialEpi` |
| FR-031 | lê `AutorizacaoPedido` (nada novo guardado) |
| FR-006 | nenhum campo novo em `ItemPedido` nem em `Pedido` |
