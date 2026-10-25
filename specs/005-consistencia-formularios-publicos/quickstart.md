# Quickstart: validar a consistência dos formulários públicos

Guia para provar, depois da implementação, que a funcionalidade funciona de ponta a ponta. Não
contém código da implementação. Contratos: [contracts/](contracts/); dados: [data-model.md](data-model.md).

## Pré-requisitos

- MariaDB ou MySQL local e `.env` copiado de `.env.example` (ver o `README.md`).
- Dependências: `uv sync`.
- **Banco de desenvolvimento apenas.** Nenhum destes passos deve ser feito no banco ou no Compose de
  produção por iniciativa própria (`deploy/AMBIENTES.md`). Nada aqui lança no SCPI.

## 1. Portões automáticos

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
uv run python manage.py makemigrations --check --dry-run
```

Esperado: tudo limpo. A migration `catalogo/0002_unidades_fracionaveis` já está no repositório, então
o `--check` não deve gerar nada novo.

Testes que provam o comportamento descrito (nomes de arquivo, não de função):

| Arquivo | Prova |
|---|---|
| `tests/test_quantidade_por_unidade.py` | SC-001: matriz unidade × saldo × quantidade, lista, teto e mensagem iguais |
| `tests/test_estados_do_catalogo.py` | SC-003: indisponível, sem estoque agora e aviso de saúde |
| `tests/test_fluxo_configuravel.py` | SC-007: formulário de teste só com catálogo e textos |
| `tests/test_migracao_unidades.py` | A carga das 10 unidades e a idempotência |
| `tests/test_registrar_pedido.py` | Reenvio, divergência, concorrência e ordem catálogo × bloqueio (SC-006) |
| `tests/test_protecao_pedidos.py`, `tests/test_formularios_publicos.py` | SC-004, SC-005 e as mensagens de proteção |
| `tests/test_atendimento*.py`, `tests/test_recibos.py` | SC-002 e SC-008 na área do almoxarifado |

## 2. Banco de desenvolvimento

```bash
uv run python manage.py migrate
```

```bash
uv run python manage.py shell -c "from tests.cenario import montar_cenario; montar_cenario()"
```

Conferir no admin (Opções → Unidades fracionáveis) que as 10 unidades estão ativas. Desativar `KG`
e voltar: o próximo pedido já obedece à lista, sem reiniciar (US1, cenário 5).

## 3. Cenários de ponta a ponta (servidor de desenvolvimento)

```bash
uv run python manage.py runserver
```

| # | Passo | Resultado esperado |
|---|---|---|
| 1 | Abrir `/pedido/ab/` e `/pedido/limpeza/` | Mesma linha "Estoque N · UN"; nenhum "N UN disponíveis" |
| 2 | Pedir 2,5 de um material `M` e de um `UN`, nos dois | O `M` entra; o `UN` é recusado com a mensagem única |
| 3 | Material `M` com saldo 2,4996 | Lista "Estoque 2,499"; 2,5 recusado com "Estoque disponível: 2,499 M." |
| 4 | Material `UN` com saldo 0,5 | Bloqueado como "Sem estoque" |
| 5 | Zerar o saldo de todos os itens de um formulário | Abre com o aviso "Nenhum material deste formulário tem estoque agora." |
| 6 | Apagar o catálogo de um formulário (cenário de teste) | Indisponível, mesma mensagem nos dois; aviso de erro no painel |
| 7 | Reduzir o estoque de um item depois de adicioná-lo e enviar | Pedido volta completo, item "Corrigir", texto igual ao de adicionar |
| 8 | Enviar com `token` adulterado, e em menos de 5 s | Mensagens humanas; dados mantidos; depois do prazo, o envio entra |
| 9 | Abrir com JavaScript desligado | Aviso de JavaScript; formulário escondido |
| 10 | Pedido AB de 2,5 M: atendimento, recibo e Telegram (envio simulado nos testes) | "2,5" em todos |
| 11 | Entregar 0,5 de um material `UN` no atendimento e numa saída avulsa | Aceito (regra da equipe) |
| 12 | Abrir pedidos gravados antes da mudança | Mesmos números e textos de antes |

## 4. Conferência manual em tela de celular (SC-010)

Porque os testes de JavaScript só conferem o texto do arquivo, não o comportamento no navegador.
Repetir nos **dois** formulários, em 375 px de largura (viewport de celular):

- [ ] Buscar, abrir a quantidade de um material e confirmar; o selo "N no pedido" aparece.
- [ ] Digitar fração em material de medida e em material contado; ver a mensagem.
- [ ] Alterar a quantidade de uma linha do pedido e confirmar; remover uma linha.
- [ ] Abrir a gaveta "Seu pedido" pela barra e enviar por ela.
- [ ] Provocar o erro por item (estoque reduzido) e ver a linha "Corrigir" e o resumo no topo.
- [ ] Ver o formulário indisponível e o de "sem estoque agora".
- [ ] Ver o aviso de JavaScript com o JavaScript desligado.
- [ ] Os botões − e + andam de 1 em 1 e preservam a fração digitada.

## 5. Medição do catálogo do AB (FR-036)

Somente leitura. Rodar num banco com dados reais (cópia ou ambiente de desenvolvimento com a carga);
em produção, só a pedido do usuário. Registrar o resultado na tabela *Medição* de
[research.md](research.md).

```bash
uv run python manage.py shell <<'EOF'
from time import perf_counter
from django.db import connection
from django.test.utils import CaptureQueriesContext
from catalogo.catalogos import catalogo_ab

with CaptureQueriesContext(connection) as consultas:
    inicio = perf_counter()
    ab = catalogo_ab()
    duracao = perf_counter() - inicio
print("itens:", len(ab.itens) if ab else None, "segundos:", round(duracao, 3), "consultas:", len(consultas))
EOF
```

Interpretação: se o tempo ficar em milissegundos, não há o que propor; se for da ordem de segundos, o
resultado é a base de uma nova decisão sobre cache (fora desta funcionalidade).

## 6. Critérios de conclusão

- Portões automáticos limpos (seção 1).
- Cenários 1 a 12 conferidos (seção 3).
- Conferência manual em celular feita e registrada (seção 4).
- Medição registrada (seção 5).
- `CLAUDE.md`, spec principal, docstring de `fluxos.py` e comentários dos modelos de página
  atualizados (FR-042).

## 7. Resultado da verificação (2026-10-21)

- **Portões automáticos:** `ruff check`, `ruff format --check`, `makemigrations --check`,
  `check --deploy` (com `DEBUG=0`) e a suíte inteira (1501 passaram, 1 pulado) limpos.
- **Banco de desenvolvimento:** migration `catalogo/0002` aplicada; as 10 unidades ficaram ativas.
- **Cenários 1 a 12:** a lógica de cada um é coberta por testes automáticos em MariaDB
  (`test_quantidade_por_unidade.py`, `test_estoque_exibido.py`, `test_estados_do_catalogo.py`,
  `test_formularios_publicos.py`, `test_quantidade_equipe.py`, `test_pedidos_antigos.py`,
  `test_fluxo_configuravel.py`, `test_registrar_pedido.py`). Os cenários que mudam saldo ou gravam
  pedido não foram repetidos no banco de desenvolvimento, que tem dados reais.
- **Conferência no navegador, em 375 px (só leitura, sem enviar pedido):** a página inicial lista os
  dois formulários; o AB e a limpeza mostram "Estoque N · UN" (a limpeza com a unidade exibida);
  adicionar 2,5 de um cabo em `M` entra no pedido ("2,5 M"); 1,5 de uma fita em `UN` é recusado com
  "Este material só é pedido em quantidade inteira (unidade: UN)." e a gaveta abre mostrando o erro;
  alterar o cabo para 301 mostra "Quantidade acima do estoque. Estoque disponível: 300 M." e a linha
  fica em 2,5; sem a classe `js` no `<html>` o formulário some e resta o `<noscript>`.
- **Não verificado:** o navegador com o JavaScript realmente desligado (simulei tirando a classe
  `js`), o envio do pedido pelo navegador e os formulários em tablet e desktop.
