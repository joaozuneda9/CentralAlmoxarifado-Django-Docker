# Contrato: tabela de rotas

`contas.acesso.REGRAS_POR_ROTA` é a fonte única de quem abre cada rota nomeada. O middleware
`ExigirPermissao`, o menu e o teste `tests/test_papeis_acesso.py` leem esta tabela. Rota nova da área
interna entra aqui no mesmo PR; fora dela, é negada a quem não é superusuário, e o teste falha.

## Categorias

| Categoria | Quem passa | Rotas |
|---|---|---|
| `PUBLICA` | qualquer um | `login`, `logout`, `pedidos:inicio`, `pedidos:formulario`, `pedidos:materiais`, `pedidos:carrinho`, `pedidos:consulta`, `pedidos:consulta_epi` |
| `ADMIN` | decide o admin (`is_staff` e permissões nativas) | todo o namespace `admin` |
| `SEGURANCA` | decidem as views (grupo da spec 008) | `pedidos:autorizacoes`, `pedidos:autorizacao`, `pedidos:decidir` |
| `Regra(...)` | autenticado, ativo e com a regra | as rotas abaixo |

## Rotas internas

| Rota | Permissões | `is_staff` | Motivo exibido na recusa |
|---|---|---|---|
| `pedidos:painel` | `contas.atender_pedidos` | — | Esta página é de quem atende os pedidos. |
| `pedidos:detalhe` | `contas.atender_pedidos` | — | idem |
| `pedidos:atender` | `contas.atender_pedidos` | — | idem |
| `pedidos:editar` | `contas.atender_pedidos` | — | idem |
| `pedidos:atendimento_materiais` | `contas.atender_pedidos` | — | idem |
| `pedidos:atendimento_adicionar` | `contas.atender_pedidos` | — | idem |
| `pedidos:avulsa` | `contas.atender_pedidos` | — | idem |
| `pedidos:avulsa_materiais` | `contas.atender_pedidos` | — | idem |
| `pedidos:avulsa_carrinho` | `contas.atender_pedidos` | — | idem |
| `pedidos:marcar_impressos` | `contas.atender_pedidos` | — | idem |
| `automacoes:pagina` | `contas.operar_automacoes` | — | Esta página é de quem opera as automações. |
| `automacoes:atualizar` | `contas.operar_automacoes` | — | idem |
| `automacoes:importar` | `contas.operar_automacoes` | — | idem |
| `automacoes:lancar` | `contas.operar_automacoes` | — | idem |
| `automacoes:resolver` | `contas.operar_automacoes` | — | idem |
| `automacoes:conferir` | `contas.operar_automacoes` | — | idem |
| `automacoes:corrigir` | `contas.operar_automacoes` | — | idem |
| `catalogo:curva` | `contas.ver_curva` | — | Esta página é da gestão do almoxarifado. |
| `catalogo:formularios` | `contas.ver_formularios` | — | idem |
| `catalogo:formularios_material` | `contas.ver_formularios` | — | idem |
| `catalogo:formularios_centros` | `contas.ver_formularios`, `catalogo.change_centrocusto` | sim | Alterar os formulários exige acesso aos cadastros e a permissão do cadastro. |
| `catalogo:formularios_ativo` | `contas.ver_formularios`, `catalogo.change_centrocusto` | sim | idem |
| `catalogo:formularios_excecao` | `contas.ver_formularios`, `catalogo.change_excecaomaterial` | sim | idem |
| `catalogo:formularios_lote` | `contas.ver_formularios` | — | Esta página é da gestão do almoxarifado. |
| `catalogo:formularios_regra` | `contas.ver_formularios`, `catalogo.change_excecaomaterial` | sim | Alterar os formulários exige acesso aos cadastros e a permissão do cadastro. |

`formularios_lote` tem a prévia em GET (leitura) e a aplicação em POST: a tabela exige a leitura, e o
`exige(pode_alterar_materiais)` que já está no POST continua decidindo a gravação. Os nomes exatos e
os métodos de cada rota de `catalogo` são conferidos contra `catalogo/urls.py` na implementação.

## Garantias do teste

1. Toda rota nomeada do projeto (o `rotas_nomeadas()` de `tests/test_epis_acesso.py`, movido para um
   helper comum) está numa categoria da tabela.
2. Para cada rota com `Regra`, um usuário sem a regra recebe 403 em GET e em POST, e a recusa vira uma
   linha do logger `contas.acesso`.
3. Para cada rota com `Regra`, um usuário com a regra não recebe 403 do middleware.
4. Uma rota de teste fora da tabela é negada ao usuário com todos os papéis e aberta ao superusuário.
5. O usuário da Segurança do Trabalho continua com o comportamento da spec 008 (o teste dela passa
   sem mudança de expectativa).
