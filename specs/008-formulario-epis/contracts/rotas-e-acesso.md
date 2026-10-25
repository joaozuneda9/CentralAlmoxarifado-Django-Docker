# Contrato: rotas, acesso e serviços da autorização

## Rotas novas

| Nome | URL | Métodos | Quem acessa | Resposta |
|------|-----|---------|-------------|----------|
| `pedidos:formulario` (existente) | `/pedido/epis/` | GET, POST | público | formulário de EPIs (pelo `Fluxo`) |
| `pedidos:consulta_epi` | `/pedido/epis/consulta/` | GET, POST | público | formulário do número; POST mostra a situação |
| `pedidos:autorizacoes` | `/painel/autorizacoes/` | GET | grupo Segurança do Trabalho | fila: aguardando (mais antigo primeiro) e decididos (leitura, mais recente primeiro, 25 por página) |
| `pedidos:autorizacao` | `/painel/autorizacoes/<numero>/` | GET | grupo | detalhe só de leitura (cabeçalho, materiais, quantidades pedidas, decisão gravada) e o formulário de decisão; 404 para número que não é de EPI |
| `pedidos:decidir` | `/painel/autorizacoes/<numero>/decidir/` | POST | grupo | grava a decisão e volta ao detalhe |

Todas as POST levam CSRF. Nenhuma rota nova grava fora de `pedidos/servicos.py`.

### `pedidos:decidir` — campos

| Campo | Regra |
|-------|-------|
| `decisao` | `autorizar` ou `recusar`; outro valor é erro |
| `motivo` | obrigatório e não vazio (após `texto()`) na recusa; ignorado na autorização; até `PEDIDOS_MAX_TEXTO` |

Respostas: sucesso → redireciona ao detalhe com mensagem; recusa sem motivo → detalhe com o erro e o
pedido continua aguardando; decisão já gravada → detalhe com "Este pedido já foi autorizado/recusado por
<nome> em <data>" (nada muda); não é do grupo → 403.

### `pedidos:consulta_epi` — respostas

| Entrada | Resposta |
|---------|----------|
| número de pedido de EPI | situação (`Aguardando autorização`, `Autorizado`, `Recusado`) e, na recusa, o motivo; nada mais |
| número inexistente ou de outro formulário | a mesma mensagem neutra nos dois casos |
| limite de consultas da origem atingido | mensagem de limite; nada é consultado |

Não mostra nome, destino, observação nem materiais. Resposta com `Cache-Control: no-store`.

## Acesso (middleware `RestringirSegurancaTrabalho`)

Para o usuário autenticado e **no grupo** `Segurança do Trabalho`, só estas rotas passam:

`login`, `logout`, `pedidos:autorizacoes`, `pedidos:autorizacao`, `pedidos:decidir` e as públicas
`pedidos:inicio`, `pedidos:formulario`, `pedidos:materiais`, `pedidos:carrinho`, `pedidos:consulta_epi`.

Qualquer outra rota resolvida: GET/HEAD redireciona a `pedidos:autorizacoes`; os demais métodos devolvem
403. URL que não resolve segue para o 404 do Django. Usuários fora do grupo: o middleware não faz nada.

## Serviços (`pedidos/servicos.py`)

| Função | Faz | Garantias |
|--------|-----|-----------|
| `registrar_pedido` (existente) | se `fluxo.exige_autorizacao`, cria a `AutorizacaoPedido` `AGUARDANDO` e agenda o aviso à Segurança do Trabalho em vez do ao almoxarifado | mesma transação; reenvio igual não duplica nem reavisa |
| `decidir_autorizacao(numero, decisao, motivo, usuario)` (novo) | trava a autorização, confere o grupo e o estado, grava `decidido_*`/`motivo` e, ao autorizar, agenda o aviso ao almoxarifado | transação; primeira decisão vale; recusa sem motivo não grava |
| `confirmar_atendimento` (existente) | recusa pedido com autorização `AGUARDANDO` ou `RECUSADO` | antes de qualquer gravação; nenhuma `LinhaSaida` nasce |

`Resposta` de `decidir_autorizacao`: `ok`, `ja_decidida` (com quem e quando), `mensagem`.

## Painel do almoxarifado

- Filtro novo **Autorização** (`?autorizacao=aguardando|autorizado|recusado`) ao lado de Situação.
- Filtro Situação `aguardando` exclui pedidos com autorização aguardando ou recusada.
- O detalhe mostra a autorização (situação, quem, quando, motivo) e, aguardando ou recusado, não mostra
  o formulário de atendimento.
- Endpoints de busca e acréscimo do atendimento (`atendimento_materiais`, `atendimento_adicionar`)
  respondem 404 para pedido não autorizado.
