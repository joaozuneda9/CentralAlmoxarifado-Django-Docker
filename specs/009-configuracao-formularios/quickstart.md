# Quickstart: validar a configuração dos formulários

Guia de validação, sem código. Pré-requisitos como no `CLAUDE.md` (MySQL/MariaDB local, `.env`,
`uv sync`). **Nunca** rode contra a produção; nada aqui lança no SCPI.

## 1. Portões automáticos

```bash
uv run python manage.py makemigrations --check --dry-run
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

Esperado: sem migration pendente, ruff limpo e a suíte inteira verde (os testes dos formulários existentes
passam, os de viaturas, oficina e EPIs com a configuração nova no lugar das marcas antigas).

```bash
uv run pytest tests/test_config_*.py
```

Esperado: os testes novos (estado, catálogo, centros, tela, permissões, lote, migração, saúde) passam.

## 2. Preparar o ambiente de desenvolvimento

1. `uv run python manage.py migrate` (aplica `catalogo/0006`, o esquema, e `catalogo/0007`, que transcreve as
   regras antigas; a 0007 falha se a transcrição não reproduzir os destinos de hoje, e uma nova
   tentativa roda só ela).
2. Importar cadastro e estoque de teste (`importar_cadastro`, `importar_estoque` com `--arquivo` e os CSV de
   `tests/fixtures/scpi/`).
3. Criar quatro usuários: um superusuário; um do almoxarifado comum (sem `is_staff`); um **staff comum**
   (`is_staff` marcado, sem ser superusuário), a quem se dão no admin, conforme o passo do roteiro, as
   permissões `change_centrocusto` e `change_excecaomaterial` (o superusuário já as tem); e um do grupo
   Segurança do Trabalho.

## 3. Roteiro ponta a ponta (US1 a US6)

| Passo | Ação | Esperado |
|-------|------|----------|
| 1 | Antes de mexer em nada, abrir os cinco formulários públicos | Destinos e materiais **idênticos** aos de antes (o teste de equivalência cobre o mesmo) |
| 2 | Entrar como superusuário e abrir **Formulários** no menu | Seletor dos cinco formulários; abas Centros de custo e Materiais |
| 3 | Aba Centros de custo, formulário Limpeza: desabilitar um centro | O centro some do destino da Limpeza e continua nos outros formulários |
| 4 | Enviar o formulário da **Limpeza** direto com o destino desabilitado nela no passo 3 (cliente HTTP); para o AB, desabilitar antes o mesmo centro no AB e repetir | Recusado com "não está na lista de centros de custo"; nenhum pedido |
| 5 | Inativar o centro (global) | Some de todos os formulários; um pedido antigo com esse destino segue íntegro; o atendimento dele e a saída avulsa **editada** ainda o resolvem; a saída avulsa **nova** não o oferece |
| 6 | No admin, criar um centro novo | Aparece na aba como "sem formulário", e a saúde avisa; habilitar em um formulário o faz aparecer ali |
| 7 | Aba Materiais, formulário AB: buscar um material que o AB oferece e **Retirar** | Some da busca do AB; envio direto com ele é recusado ("não está mais no catálogo"); continua nas viaturas |
| 8 | **Restaurar** regra no mesmo material | Volta ao AB |
| 9 | Acrescentar à Oficina um material de outro grupo | Aparece na Oficina (ordem alfabética); sem estoque, aparece bloqueado |
| 10 | Filtrar um grupo e **Retirar todos** no AB | A prévia mostra o número exato; ao confirmar, só os materiais do filtro mudam, só no AB |
| 11 | Pedir o lote sem nenhum filtro | A prévia exige marcar "Estou ciente" |
| 12 | Abrir a consulta por material | Os cinco formulários com estado e origem (regra, acrescentado, retirado) |
| 12a | Entrar como o **staff comum** com `change_centrocusto` e `change_excecaomaterial` e alterar um centro (habilitar ou desabilitar) e uma exceção de material | As duas gravações valem; sem uma das permissões, só a gravação correspondente é recusada (403) |
| 13 | Entrar como usuário comum (sem `is_staff`) | Vê tudo, sem controles; um POST forjado dá 403 e nada muda |
| 14 | Entrar como Segurança do Trabalho e abrir a página | Redireciona à fila de autorização |
| 15 | Em Automações, aba Visão geral | A saúde mostra os avisos novos (formulário sem destino, centro sem formulário, exceção sem efeito) quando existirem |

## 4. Conferências de não regressão

- Limpeza, AB, viaturas, oficina e EPIs enviam, atendem e avisam como antes.
- Um pedido registrado antes de uma retirada continua com o retrato gravado; o atendimento, a troca e o
  acréscimo do almoxarifado não consultam a configuração.
- O reenvio igual de um pedido registrado confirma mesmo depois de a configuração mudar.
- O robô (`lancar_saidas --dry-run`, só se o usuário pedir) resolve lote de centro inativo.
- `uv run python manage.py check --deploy` sem avisos com `DEBUG=0`.
