# Quickstart: validar a reposição de peças das viaturas

Roteiro de validação de ponta a ponta. Nenhum passo lança no SCPI nem roda importador contra o SCPI
real. Detalhes de dados e interface em [data-model.md](data-model.md) e [contracts/](contracts/).

## Pré-requisitos

- MariaDB/MySQL local e `.env` de desenvolvimento (README); `uv sync`.
- Branch `claude/reposicao-pecas-viaturas`.

```bash
uv run python manage.py migrate
uv run python manage.py importar_estoque --arquivo tests/fixtures/scpi/estoque.csv
uv run python manage.py runserver
```

## 1. Portões automáticos

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
```

Esperado: tudo limpo; as migrations `catalogo/0003_pecas_viaturas` e `pedidos/0003_viaturas`
aplicadas; a suíte inteira passa (os formulários existentes sem mudança de comportamento, SC-005).

## 2. Cadastro (admin, `/admin/`)

1. Cadastros › Peças das viaturas: incluir 3 materiais com saldo (um em `M`, um em `UN`, um sem
   estoque), com ordem e um nome exibido. Tentar incluir o mesmo material de novo: recusado.
2. Cadastros › Centros de custo: marcar "Equipe de manutenção" em um centro que tem placa.

## 3. Saúde do catálogo (`/painel/` e Automações › Visão geral)

- Antes do passo 2.2: erro "nenhum centro de custo marcado…"; o formulário em `/pedido/viaturas/`
  mostra "Este formulário está indisponível no momento. Avise o almoxarifado."
- Depois: "Formulário de reposição de peças das viaturas: 3 peças na lista e M materiais do AB."
- Ocultar no banco o material de uma peça: aviso com o código; a peça some da folha.

## 4. Formulário, no celular (375 px) e no computador

1. Página inicial: o cartão "Reposição de peças das viaturas" aparece com os outros.
2. Destinos: só o centro marcado, sem "centro — placa". Digitar uma placa ou outro centro e enviar:
   recusa de destino inválido.
3. "Preencher a lista de peças": a folha abre com as 3 linhas na ordem; a sem estoque mostra o motivo
   no lugar do campo; foco no primeiro campo; Esc fecha e devolve o foco.
4. Preencher "2,5" na peça em `UN` e "2,5" na peça em `M`, "Pôr no pedido": nada muda, a linha em `UN`
   mostra o erro de fração; corrigir para "2": o diálogo fecha e o carrinho mostra as duas.
5. Reabrir a folha: as duas vêm preenchidas. Apagar uma e aplicar: ela sai do carrinho.
6. Buscar um material do AB que não está na lista e adicioná-lo; buscar o nome exibido de uma peça da
   lista: ela aparece uma vez só.
7. "Nº da ocorrência" com 21 caracteres: erro no campo; com "1234/2026": enviado. Sucesso com o número
   `P-…`.
8. Reenviar o mesmo formulário (duplo toque): confirma o mesmo pedido, nada duplica.

## 5. Almoxarifado

1. Painel: o pedido aparece com "Reposição de peças das viaturas" e "Ocorrência 1234/2026"; o filtro
   por origem o encontra, e a busca por "1234/2026" também.
2. Detalhe e recibo: "Nº da ocorrência 1234/2026" visível; nome exibido conforme a regra da limpeza.
3. Atender (com uma troca), imprimir o recibo, ver as linhas de saída `PENDENTE` com o centro de custo
   da equipe. Simular o lançamento só com `--dry-run` em ambiente de desenvolvimento, se for o caso.
4. Telegram (se configurado): o aviso diz "Reposição de peças das viaturas".

## 6. Não regressão

Limpeza e "Ferramentas, peças e materiais": mesmos destinos (com "centro — placa"), sem campo de
ocorrência, sem botão de folha; uma peça da lista continua no AB.

## O que fica para validação operacional

- A carga real da lista (39 linhas do papel associadas a códigos do SCPI) e a marca dos centros das
  equipes, feitas pelo almoxarifado.
- O uso por um encarregado de verdade (SC-001: 5 peças em até 2 minutos no celular).
