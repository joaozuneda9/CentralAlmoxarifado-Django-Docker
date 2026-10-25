# Contrato: rotas, permissões e serviços da configuração

## Rotas novas (`catalogo`, montadas em `/painel/catalogo/`)

| Nome | URL | Métodos | Quem acessa | Resposta |
|------|-----|---------|-------------|----------|
| `catalogo:formularios` | `/painel/catalogo/formularios/` | GET | usuário logado do almoxarifado | a página: seletor de formulário e as abas Centros de custo e Materiais |
| `catalogo:formularios_material` | `/painel/catalogo/formularios/material/<codigo>/` | GET | idem | os cinco formulários com estado e origem do material (404 se o código não existe) |
| `catalogo:formularios_lote` | `/painel/catalogo/formularios/lote/` | GET, POST | GET: logado; POST: `change_excecaomaterial` | GET é a **prévia** do lote; POST aplica |
| `catalogo:formularios_excecao` | `/painel/catalogo/formularios/excecao/` | POST | `change_excecaomaterial` | grava, restaura e volta |
| `catalogo:formularios_centros` | `/painel/catalogo/formularios/centros/` | POST | `change_centrocusto` | habilita ou desabilita linhas de centro no formulário |
| `catalogo:formularios_ativo` | `/painel/catalogo/formularios/centros/ativo/` | POST | `change_centrocusto` | ativa ou inativa linhas de centro (global) |

Toda rota exige login (`@login_required`); a Segurança do Trabalho é negada pelo middleware (nenhuma das
rotas entra em `ROTAS_SEGURANCA_TRABALHO`). Toda POST leva CSRF, segue o padrão POST, mensagem e
redirecionamento (a volta preserva o formulário, a aba, o filtro e a página) e usa `require_POST`.

### `GET catalogo:formularios` — parâmetros

| Parâmetro | Regra |
|-----------|-------|
| `formulario` | um valor de `Formulario`; ausente ou inválido volta ao primeiro (limpeza), sem erro |
| `aba` | `centros` ou `materiais` (componente `abas.js`); padrão `materiais` |
| `q` | texto; casa com o código e com o nome (sem acento, todas as palavras) |
| `grupo`, `subgrupo` | valores do cadastro (listas montadas do catálogo visível) |
| `estado` | `todos` (padrão), `disponivel`, `indisponivel`, `excecao` |
| `pagina` | inteiro a partir de 1; 50 materiais por página; fora da faixa vai à última |

A lista mostra só materiais **visíveis**; os ocultos aparecem na consulta por material.

### `POST catalogo:formularios_excecao` — campos

| Campo | Regra |
|-------|-------|
| `formulario` | valor de `Formulario` |
| `codigo` | código de um material existente (404 se não existe) |
| `acao` | `acrescentar`, `retirar` ou `restaurar`; outro valor, 400 |

`acrescentar` e `retirar` gravam o **resultado efetivo pedido** com a menor mudança (a mesma conta do lote:
se a regra já dá esse resultado, apaga a exceção; se não, grava). `restaurar` apaga a exceção. Idempotente.

### `GET/POST catalogo:formularios_lote`

| Campo | GET (prévia) | POST (aplica) |
|-------|--------------|---------------|
| `formulario`, `acao` (`acrescentar` ou `retirar`), `q`, `grupo`, `subgrupo`, `estado` | o filtro e a ação | os mesmos, reenviados |
| `total` | n/a | o número que a prévia mostrou |
| `ciente` | n/a | obrigatório quando não há filtro algum (catálogo inteiro) |

- A prévia mostra formulário, ação, **número exato** e uma amostra (primeiros 10), e o botão de confirmar.
- O POST recusa (volta à prévia, nada muda) se `total` difere do número atual do filtro, ou se faltar
  `ciente` sem filtro. Aplicado, mostra "N mudaram, M já estavam assim" e nada mais muda (FR-026, FR-027).
- O lote vale para **todos** os materiais do filtro (não só a página), atômico.

### `POST catalogo:formularios_centros` — campos

| Campo | Regra |
|-------|-------|
| `formulario` | valor de `Formulario` |
| `centro` | um ou mais ids de linhas de `CentroCusto` (a tela envia todas as linhas de uma descrição ao marcar o grupo) |
| `habilitado` | `1` habilita (cria as associações que faltam), `0` desabilita (apaga as existentes) |

Idempotente; id inexistente é ignorado com aviso.

### `POST catalogo:formularios_ativo` — campos

| Campo | Regra |
|-------|-------|
| `centro` | um ou mais ids de linhas de `CentroCusto` |
| `ativo` | `1` ou `0` |

## Permissões

| Operação | Exige | Sem a permissão |
|----------|-------|-----------------|
| ver (todas as GET) | login | login: redireciona ao login; Segurança do Trabalho: negada pelo middleware |
| centros (habilitar, desabilitar, ativar, inativar) | `is_staff` e `catalogo.change_centrocusto` | 403, nada muda |
| materiais (exceção, restaurar, lote) | `is_staff` e `catalogo.change_excecaomaterial` | 403, nada muda |

A tela mostra os controles só a quem pode, mas a recusa é do servidor. Criar e editar centro de custo
continua no admin (`admin:catalogo_centrocusto_*`), com as permissões do admin.

## Serviços e funções (`catalogo/disponibilidade.py` e `catalogo/catalogos.py`)

| Função | Faz | Garantias |
|--------|-----|-----------|
| `estado(oculto, na_regra, excecao)` | resultado efetivo, origem e "sem efeito" (pura) | sem ORM; tabela do data-model |
| `regra_de_origem(origem)` | os itens que a regra de hoje traz (sem exceções) | os mesmos que `formulario_*` trazia antes |
| `aplicar_excecoes(origem, base)` | a base sem os retirados, mais os acrescentados | `oculto` nunca entra; sem duplicar; ordem do R3 |
| `centros_do_formulario(origem)` | as linhas ativas e habilitadas, pelo modo do formulário | `ativo` filtrado; modos do R4 |
| `definir_excecao(origem, material, acao, usuario)` | uma exceção | transação; menor mudança |
| `aplicar_em_lote(origem, materiais, acao, usuario)` | várias exceções | atômico; devolve `(mudaram, ja_estavam)` |
| `habilitar_centros(origem, centros, habilitado, usuario)` | associações | idempotente |
| `definir_ativo(centros, ativo)` | estado global | idempotente |

Nenhuma delas toca `pedidos`, estoque ou o cadastro de materiais.
