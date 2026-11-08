# Contrato: recusa de acesso

## Página

`interface/acesso_negado.html`, no layout `base_almoxarifado.html`, status 403, `never_cache`.

| Situação | Título | Texto | Ações |
|---|---|---|---|
| Usuário sem nenhum papel | Seu usuário ainda não tem acesso | O administrador do almoxarifado precisa dar um papel ao seu usuário. Procure-o e entre de novo depois. | Sair |
| Falta a regra da rota | Sem acesso a esta página | o motivo da regra (ver [tabela-de-rotas.md](tabela-de-rotas.md)) | Voltar ao painel (só com `contas.atender_pedidos`), Sair |
| `PermissionDenied` de uma view ou do disparo (`templates/403.html`) | Sem acesso | a mensagem da exceção | Voltar ao painel (idem), Sair |

O Sair é o formulário POST com CSRF de sempre (um só por página). Nenhum dado do pedido, código ou
nome aparece na recusa.

Requisição do HTMX (`HX-Request`) recebe o mesmo status 403; a página aberta não é trocada (`noSwap`
de 4xx no `base.html`).

## Linha do log

Logger `contas.acesso`, nível `WARNING`, no arquivo `almoxarifado.log`:

```text
<asctime> WARNING contas.acesso: Acesso recusado: matricula=12345 rota=automacoes:lancar metodo=POST falta=contas.operar_automacoes
```

| Campo | Origem | Observação |
|---|---|---|
| `matricula` | `request.user.get_username()` | `anonimo` nunca aparece: anônimo vai ao login, não é recusado |
| `rota` | `request.resolver_match.view_name` | nunca o caminho com parâmetros (o número do pedido não vai ao log) |
| `metodo` | `request.method` | |
| `falta` | as permissões da regra, `is_staff`, `grupo:Segurança do Trabalho` ou `rota-fora-da-tabela` | |

Nunca: corpo da requisição, query string, cookies, cabeçalhos, nomes de solicitantes.
