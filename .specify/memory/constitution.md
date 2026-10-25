# Central Almoxarifado (Django) Constitution

## Core Principles

### I. Regras de negócio puras, com o próprio sistema como referência

- Regras de negócio ficam em funções puras, sem ORM (`pedidos/regras.py`, `scpi/leitura.py`,
  `scpi/requisicoes.py`), testáveis sem banco.
- O Central Almoxarifado é a referência das próprias regras: valem o código, os testes e as
  specs vigentes. O Apps Script e as planilhas de onde vieram são histórico, não requisito: não
  há compromisso de equivalência de resultados, textos ou estrutura com eles. Mudar uma regra
  que veio deles segue o fluxo de qualquer mudança (spec, plano e teste), justificada pela
  necessidade atual da operação.
- Quantidades são `Decimal`, no formato pt-BR estrito ("1.5" é recusado). Códigos (CADPRO,
  placa) são comparados por `norm_u`, como a collation `utf8mb4_unicode_ci` do banco.

Motivo: regra pura é a única que se testa por inteiro; e o sistema já substituiu o processo
antigo, então reproduzi-lo só limitaria a evolução.

### II. Uma porta de gravação, transacional e idempotente

- `pedidos/servicos.py` é o único lugar que grava pedidos; cada operação roda numa transação e
  serializa o que precisa (`select_for_update` na `Sequencia` e no pedido).
- Envio repetido NÃO PODE duplicar: o identificador do envio decide se é o mesmo pedido.
- Fora de `servicos.py`, só o robô de lançamento grava em `pedidos`, e só nos campos `status`,
  `requisicao_scpi`, `lancado_em` e `mensagem` das `LinhaSaida`.
- Efeito externo (como o aviso no Telegram) sai depois do commit e nunca desfaz a gravação.

Motivo: com uma porta só, as garantias de concorrência e de idempotência valem em todo lugar.

### III. Nunca lançar duas vezes no SCPI (INEGOCIÁVEL)

- O estado `EM_LANCAMENTO` DEVE estar confirmado no banco antes do clique em Salvar.
- Qualquer falha depois do clique vira `VERIFICAR`, nunca `PENDENTE`. Na dúvida, a linha fica
  travada.
- O número da requisição vai para o journal antes de ir para o banco; se o banco recusar, a
  execução para com o lote travado.
- Uma execução de cada robô por vez (`GET_LOCK`).
- O lançamento real só roda com `LANCAMENTO_REAL` ligado; o padrão é desligado.

Motivo: uma requisição duplicada no SCPI é um erro contábil que o sistema não consegue desfazer.

### IV. Dados importados nunca se perdem em silêncio

- Toda importação grava numa transação: se falhar, nada muda.
- Material que some do cadastro fica oculto, nunca é apagado.
- Importação que parece cortada aborta (cadastro completo que esconderia mais de 20% dos
  visíveis, estoque vazio), salvo pedido explícito.
- Problemas são juntados e mostrados de uma vez. Erro bloqueia a gravação; aviso não bloqueia.
  Perder algo que o robô lançaria é sempre erro.
- Cada execução fica registrada (`Importacao`, `ExecucaoRobo`) com situação, resumo e erro.

Motivo: os dados vêm de fontes externas (SCPI, planilhas) que falham de formas imprevisíveis, e
uma perda silenciosa só seria notada tarde demais.

### V. Testes contra o banco real, sem navegador

- Toda mudança de comportamento vem com teste automatizado.
- Os testes rodam contra MySQL ou MariaDB (`config.settings_test`), nunca SQLite: transações e
  `select_for_update` precisam se comportar como no servidor.
- Os testes nunca abrem o navegador, nunca falam com o SCPI real (usam o SCPI simulado), nunca
  rodam `mysqldump` de verdade e nunca gravam no `logs/` do repositório.
- A navegação do Playwright só é exercida pela simulação no SCPI real (`--dry-run`), feita à mão.

Motivo: os erros que importam aqui são de concorrência e de transação, e só aparecem no banco
de verdade.

### VI. Interface em pt-BR, acessível e sem dependências externas

- Nomes de código, textos de interface, mensagens e commits em português (pt-BR).
- A interface segue o design system Clean (`docs/DESIGN.md`). Estado nunca só por cor; códigos
  (CADPRO, matrícula, placa) em fonte mono.
- Nenhuma dependência do Google, de CDN ou de npm: fontes, ícones e HTMX ficam no repositório.
- Requisição que grava leva CSRF; logout só por POST.

Motivo: o público é o almoxarifado e os funcionários da operação, e o servidor é interno.

## Restrições técnicas

- Python `>=3.13,<3.14`, Django 6.x, MySQL 8 ou MariaDB; dependências pelo `uv`.
- Servidor Windows: waitress como serviço NSSM, atrás do Apache em `/almoxarifado`; robôs e
  importações em processo separado ou pelo Agendador de Tarefas.
- Configuração num único `config/settings.py` lido do `.env`; segredos só no `.env`, e cada
  variável nova documentada no `.env.example`.
- Com `DEBUG=0`, `check --deploy --fail-level WARNING` DEVE passar sem avisos.
- Migrations: o banco de produção tem dados reais; toda mudança de modelo ganha migration nova,
  nunca regenerada.

## Fluxo de desenvolvimento

- Toda funcionalidade nova parte de uma spec e de um plano escritos antes do código.
- Trabalho em branch própria, integrado ao `main` por pull request.
- Portões antes do merge: `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format --check .` e `uv run python manage.py makemigrations --check --dry-run`,
  todos limpos.
- O `CLAUDE.md` é o guia operacional (arquitetura, comandos, detalhes) e DEVE ser atualizado no
  mesmo pull request que muda o que ele descreve.

## Governance

- Esta constituição vale mais que qualquer outra prática do projeto. Se o `CLAUDE.md`, uma spec
  ou um plano a contrariar, a constituição vence e o documento é corrigido.
- Emendas são feitas por pull request que altera este arquivo, explica o motivo e ajusta, no
  mesmo pull request, os documentos e o código afetados.
- Versão semântica: MAJOR quando um princípio é removido ou redefinido de forma incompatível;
  MINOR quando um princípio ou seção é acrescentado ou ampliado; PATCH para redação e
  esclarecimentos.
- Todo plano tem uma verificação de conformidade com estes princípios. Exceção a um princípio
  só com justificativa escrita no plano; o Princípio III não admite exceção.

**Version**: 2.0.0 | **Ratified**: 2026-10-12 | **Last Amended**: 2026-10-22
