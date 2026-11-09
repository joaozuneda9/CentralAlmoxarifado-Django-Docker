# Pesquisa: Papéis de acesso na área interna

**Spec**: [spec.md](spec.md) · **Data**: 2026-11-08

Cada decisão segue o formato Decisão / Motivo / Alternativas. As referências de código são de
`develop` em `16f317c`.

## R1. Onde ficam as permissões

**Decisão**: quatro permissões próprias no `Meta.permissions` de `contas.Usuario`:

| Codinome | Rótulo |
|---|---|
| `contas.atender_pedidos` | Atender pedidos (painel, atendimento, edição e saída avulsa) |
| `contas.operar_automacoes` | Operar as automações (SCPI, importações e conferência) |
| `contas.ver_curva` | Ver a Curva ABC |
| `contas.ver_formularios` | Ver a configuração dos formulários |

**Motivo**: um lugar só; o app `automacoes` não tem modelos para declarar as suas, e espalhar
(`pedidos.Pedido`, `catalogo.Material`) misturaria "o que o usuário pode" com "o que o modelo é". As
permissões nativas do Django passam pelo `has_perm`, pelo `{{ perms }}` dos templates e pelo admin
sem código novo. A mudança no `Meta` é uma migration só de opções, sem DDL.

**Alternativas**: um modelo sem tabela (`managed=False`) só para as permissões (mais um conceito sem
ganho); campos booleanos no usuário (fora do admin de grupos, e cada papel novo vira migration);
permissão por grupo pelo nome (o código passaria a depender do nome do papel, o que a spec proíbe).

## R2. Onde a verificação acontece: um middleware com a tabela, não decoradores

**Decisão**: um middleware novo, `contas.middleware.ExigirPermissao`, logo depois do
`RestringirSegurancaTrabalho`, que em `process_view` lê `request.resolver_match.view_name` na tabela
`contas.acesso.REGRAS_POR_ROTA` (contrato em [contracts/tabela-de-rotas.md](contracts/tabela-de-rotas.md)):

- rota **pública** (formulários, consulta, login, logout): passa;
- rota do **admin** (namespace `admin`): passa; o admin decide pelo `is_staff` e pelas permissões
  nativas, como hoje;
- rota da **Segurança do Trabalho** (`pedidos:autorizacoes`, `autorizacao`, `decidir`): passa; as
  views já recusam quem não é do grupo (spec 008);
- rota **interna** com regra: anônimo segue para o `login_required` de sempre (redireciona ao login);
  logado sem a regra recebe a recusa;
- rota **fora da tabela**: negada a todos menos ao superusuário (anônimo vai ao login).

Os `@login_required` e o `exige(...)` da spec 009 ficam onde estão, como segunda camada.

**Motivo**: o "nega por padrão" só existe se a verificação não depender de alguém lembrar de pôr um
decorador. O projeto já usa esse desenho para a Segurança do Trabalho (`process_view` com a rota
resolvida), e a mesma tabela alimenta o menu e o teste. URL que não resolve nem chega ao
`process_view` (404 do Django).

**Alternativas**: decorador `exige_permissao` em cada view (esquecer um abre a rota; o teste pegaria,
mas a falha aparece só na suíte); `LoginRequiredMiddleware` do Django com `login_not_required` nas
públicas (resolve o login, não a permissão).

## R3. A regra de cada rota

**Decisão**: `Regra(permissoes: tuple[str, ...], exige_staff: bool = False, motivo: str)`, avaliada
por uma função pura `contas.acesso.pode(usuario, regra) -> bool`: autenticado, ativo, `is_staff` se
pedido e `has_perms(permissoes)`. As gravações da página Formulários usam
`Regra(("contas.ver_formularios", "catalogo.change_centrocusto"), exige_staff=True)` (e a de
exceções), o que repete na tabela o critério da spec 009 (FR-010) sem mudá-lo.

**Motivo**: um formato para todos os casos, com o texto da recusa junto da regra.

**Alternativas**: um texto de permissão por rota mais exceções em código (dois lugares para a mesma
decisão).

## R4. O lançamento real conferido também no disparo

**Decisão**: `scpi.disparo.iniciar_lancamento` confere `usuario.has_perm("contas.operar_automacoes")`
antes de qualquer gravação e levanta `PermissionDenied` (que o middleware não vê, mas o Django
transforma em 403). Vale para os dois modos: a spec exige no lançamento real (FR-007), e com
Automações inteira do chefe não há motivo para a simulação ser diferente. `iniciar_importacao`,
`iniciar_atualizacao` e `iniciar_conciliacao` ficam só com a rota: não lançam no SCPI.

**Motivo**: o lançamento é irreversível (Princípio III). A conferência no ponto de partida protege de
uma tela futura que chame o disparo sem passar pela rota.

**Alternativas**: conferir em `scpi.lancamento.lancar` (roda no processo do robô, sem usuário, e a
execução já teria sido criada).

## R5. As permissões numa migration de dados

**Decisão**: duas migrations novas em `contas`:

1. `0003_permissoes`: o `AlterModelOptions` gerado pelo `makemigrations`.
2. `0004_papeis`: `RunPython` que (a) cria as quatro permissões com `get_or_create` sobre o
   `ContentType` de `contas.usuario`, (b) cria os grupos **Atendimento** (`atender_pedidos`) e
   **Gestão** (`operar_automacoes`, `ver_curva`, `ver_formularios`), (c) põe nos dois todo usuário
   ativo que não é do grupo `Segurança do Trabalho` e (d) confere e levanta erro se algum desses
   usuários não tiver as quatro permissões pelos grupos. Reverter é `noop` (os grupos podem já ter
   sido ajustados). Nomes e codinomes são copiados na migration, como na `0002` (a migration não pode
   mudar se a constante mudar).

**Motivo**: o Django cria as permissões do `Meta` no sinal `post_migrate`, **depois** de todas as
migrations da execução; uma migration de dados que só as procurasse não as acharia num banco novo
(inclusive no banco de teste). O `get_or_create` funciona nos dois casos (banco novo e produção) e
o `post_migrate` depois não duplica. A conferência no fim segue o padrão da `catalogo/0007` (a
migration que se verifica).

**Alternativas**: chamar `create_permissions` dentro da migration (depende de API interna do
`django.contrib.auth.management`); criar os grupos à mão depois do deploy (a janela entre o deploy e
o ajuste deixaria todos sem acesso, o contrário do FR-015).

## R6. A recusa: uma página só, montada pelo middleware

**Decisão**: o middleware devolve a recusa com `TemplateResponse(..., "interface/acesso_negado.html",
status=403)` no layout do almoxarifado, com o motivo da regra; quem não tem permissão alguma vê o
texto de "usuário ainda sem acesso" (FR-009); o link "Voltar ao painel" só aparece se o usuário pode
abrir o painel. Para os 403 levantados fora do middleware (`PermissionDenied` das views da spec 008 e
do `exige` da spec 009, e o do disparo), um `templates/403.html` (em `interface/templates/`) com o
mesmo visual e a mensagem da exceção. Requisição do HTMX recebe o mesmo 403 sem corpo útil: o
`noSwap` de 4xx do `base.html` já impede que a página seja apagada.

**Motivo**: o 403 padrão do Django é uma página crua em inglês; a recusa precisa explicar o papel
que falta e oferecer o caminho de volta (FR-008).

**Alternativas**: redirecionar ao painel com mensagem (como o GET da Segurança do Trabalho): esconde a
recusa de quem não tem nem o painel, e o usuário sem papel entraria em laço.

## R7. O registro das recusas

**Decisão**: logger `contas.acesso`, nível `WARNING`, uma linha por recusa:
`Acesso recusado: matricula=<username> rota=<view_name> metodo=<GET|POST|...> falta=<permissões ou regra>`.
O momento vem do formato do log (`%(asctime)s`). Escrevem: o `ExigirPermissao`, o
`RestringirSegurancaTrabalho` (no 403 dos métodos que não são GET; o redirecionamento do GET é
navegação, não recusa) e uma função única `contas.acesso.registrar_recusa(request, falta)`, chamada
também pelo `exige` da spec 009, pelas views de autorização e pelo disparo. Nunca o corpo, os
parâmetros da URL, nomes de solicitantes nem dados do pedido (FR-018). O 405 do `require_POST` e o
403 do CSRF não passam por aí e continuam como estão.

**Motivo**: o handler do arquivo (`almoxarifado.log`, `ConcurrentRotatingFileHandler`) já existe e é
dividido por waitress e comandos; um logger com nome próprio permite filtrar as recusas.

**Alternativas**: o log `django.request` (já registra "Forbidden", mas sem usuário nem permissão);
uma tabela de auditoria (fora do escopo da spec).

## R8. Menu e botões pela mesma tabela

**Decisão**: `ItemMenu` perde o `so_equipe` e o menu mostra o item quando
`contas.acesso.pode_abrir(usuario, item.rota)` (a regra da tabela; para `admin:index`, `is_staff`,
o que repete o `so_equipe` de hoje). Nos templates, `{% if perms.contas.operar_automacoes %}` em volta
do cartão do lançamento e do "Ver automações" do painel (`painel.html`, linhas 43, 46 e 130) e do
"Resolver em Automações" do detalhe (`detalhe.html`, linha 58); a view do painel só calcula o que o
cartão usa (`lotes_pendentes`, `contar_lotes_travados`, `ExecucaoRobo.em_andamento`) para quem tem a
permissão. Os avisos de saúde continuam; o link de cada um para Automações só aparece com a
permissão.

**Motivo**: uma fonte só (FR-005); o menu nunca oferece o que a rota recusa.

**Alternativas**: um campo `permissao` em cada `ItemMenu` (duplica a tabela).

## R9. Os testes que já existem

**Decisão**: a fixture `usuario_logado` (`tests/conftest.py`) e os usuários do almoxarifado em
`tests/epis_cenario.py` passam a ganhar os dois papéis, como faz a migration; um helper
`tests/papeis.py::dar_papeis(usuario, *nomes)` serve aos testes que criam e logam usuários por conta
própria. Há 67 chamadas de `create_user`/`create_superuser` em 48 arquivos; só as que fazem
`force_login` numa rota interna mudam (as que passam o usuário a um serviço não). A suíte inteira
rodando depois da mudança aponta cada uma.

**Motivo**: o comportamento esperado de "um usuário do almoxarifado" é ter os papéis; sem isso toda a
suíte da área interna recebe 403.

**Alternativas**: um sinal no `settings_test` que dá os papéis a todo usuário criado (esconderia
exatamente o tipo de erro que o teste das rotas quer pegar).

## R10. Custo por requisição

**Decisão**: nenhuma otimização. O `ModelBackend` guarda as permissões do usuário no próprio objeto
(`_perm_cache`) depois da primeira consulta; por requisição, uma consulta a mais para quem está
logado. Com 3 usuários internos, irrelevante.
