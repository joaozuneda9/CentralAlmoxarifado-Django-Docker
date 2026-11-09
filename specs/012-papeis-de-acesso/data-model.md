# Modelo de dados: Papéis de acesso

**Spec**: [spec.md](spec.md) · **Pesquisa**: [research.md](research.md)

Nenhuma tabela nova. Muda o `Meta` de um modelo e entram dados em tabelas que o Django já tem.

## contas.Usuario (existente)

| Mudança | Detalhe |
|---|---|
| `Meta.permissions` | `atender_pedidos`, `operar_automacoes`, `ver_curva`, `ver_formularios` (rótulos em [research.md](research.md#r1-onde-ficam-as-permissões)) |
| Migration | `contas/0003_permissoes` (só opções, sem DDL) |

## auth.Permission (dados)

As quatro permissões acima, com o `ContentType` de `contas.usuario`. Criadas pela `contas/0004_papeis`
com `get_or_create` (o `post_migrate` depois não duplica).

## auth.Group (dados)

| Grupo | Permissões | Quem entra na implantação |
|---|---|---|
| Atendimento | `contas.atender_pedidos` | todo usuário ativo fora da Segurança do Trabalho |
| Gestão | `contas.operar_automacoes`, `contas.ver_curva`, `contas.ver_formularios` | idem |
| Segurança do Trabalho (existente, spec 008) | nenhuma | sem mudança |

As gravações da página Formulários continuam usando as permissões nativas de `catalogo`
(`change_centrocusto`, `add_centrocusto`, `change_excecaomaterial`), dadas ao usuário ou a um grupo
pelo admin, mais o `is_staff` (spec 009).

## Regras de validação da migração (`contas/0004_papeis`)

1. Todo usuário com `is_active=True` que não está no grupo `Segurança do Trabalho` fica nos dois
   grupos novos.
2. Ao fim, para cada um desses usuários, as quatro permissões vêm dos grupos; se faltar alguma, a
   migration levanta erro e a transação inteira é desfeita.
3. Usuário inativo e usuário da Segurança do Trabalho não ganham nada.
4. Reverter não apaga grupos nem permissões.

## Estado derivado (não guardado)

- **Pode abrir a rota**: `pode(usuario, REGRAS_POR_ROTA[rota])`, calculado a cada requisição.
- **Sem papel**: usuário autenticado sem nenhuma das quatro permissões e fora da Segurança do Trabalho;
  decide o texto da página de recusa.
