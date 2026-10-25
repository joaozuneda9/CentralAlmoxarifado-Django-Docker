# Git: desenvolvimento, versões e produção

Um repositório no GitHub, duas branches permanentes e clones independentes.
O Git versiona código e migrations; não transporta bancos, `.env`, perfis do
navegador, logs ou backups. Fazer push não altera nenhum container.

## Branches e permissões

| Referência | Função | Quem faz commit/push |
|---|---|---|
| `claude/<assunto>` ou `codex/<assunto>` | Uma alteração isolada, criada de `develop` (`claude/*` para agentes Claude Code, `codex/*` para Codex) | Desenvolvedor ou agente; push apenas dessa branch |
| `develop` | Integração e validação no desenvolvimento | Recebe PRs, sem commits diretos |
| `main` | Código aprovado para release | Recebe PR de `develop`, sem commits diretos |
| `claude/hotfix-<assunto>` ou `codex/hotfix-<assunto>` | Correção baseada na tag realmente implantada | Desenvolvedor; PR para `main`, depois sincronização com `develop` |
| `vMAJOR.MINOR.PATCH` | Versão de um commit aprovado de `main` | Responsável pela release; tag nunca movida/reutilizada |

As mudanças deste fluxo entram primeiro por PR em `develop`, depois por PR em
`main`. A primeira `develop` nasce da `main` existente. As proteções com checks
obrigatórios só devem exigir nomes de jobs que a CI realmente produz.

## Trabalho diário (na máquina de desenvolvimento)

Os comandos abaixo são exemplos para um clone de trabalho, não para a pasta que
atende usuários hoje. Antes de atualizar, `git status` precisa estar limpo;
alterações existentes são preservadas e publicadas em branch própria.

```powershell
git switch develop
git pull --ff-only origin develop
git switch -c claude/minha-alteracao
# editar, testar e revisar o diff
git add <arquivos-revisados>
git commit -m "Descrição da alteração"
git push -u origin claude/minha-alteracao
```

Abrir PR para `develop`. A CI usa banco MariaDB descartável e não recebe segredos
de produção. Após integrar, atualizar o clone dedicado ao ambiente de
desenvolvimento para `origin/develop`, planejar e aplicar com `atualizar.ps1`.
Nesse clone de validação, não desenvolver diretamente em `develop`: usar outro
clone/branch de trabalho. A branch pode mudar sem alterar containers já criados,
mas o próximo build passa a usar os arquivos da pasta.

Validar a versão integrada, anotar o commit e abrir PR `develop` → `main`.
Se houver funcionalidades incompletas em `develop`, não promover o conjunto:
preparar uma branch temporária de release a partir de `main` com as alterações
aprovadas e revisar por PR. Hotfixes partem da tag em produção e entram também
em `develop`. Não usar squash/rebase na promoção entre as branches permanentes:
preservar a ancestralidade com merge commit e sincronizar `main` → `develop`
após a promoção. Squash pode ser usado nos PRs das branches de trabalho.

Para sincronizar com os checks estritos, criar `codex/sync-<assunto>` ou
`claude/sync-<assunto>` a partir de `origin/develop`, fazer merge de `origin/main`
nessa branch e abrir PR dela para `develop`, com merge commit. Isso preserva a
ancestralidade e mantém a origem do PR atualizada com a base. Não usar um PR com
origem diretamente em `main` nem clicar em “Update branch” nesse caso: o botão
traria as alterações ainda em desenvolvimento para `main`. Não usar squash ou
rebase no PR de sincronização.

## Release e imagem

Após a CI passar em `main`, num clone de trabalho limpo e atualizado:

```powershell
git switch main
git pull --ff-only origin main
git tag -a v1.0.0 -m "Primeira release da nova implantação"
git push origin v1.0.0
```

Usar a próxima versão disponível, nunca sobrescrever uma tag. No GitHub, em
Actions, executar **Imagem de release**, selecionando a branch `main` e a tag.
O workflow exige que a tag corresponda ao HEAD usado de `main`, roda novamente
a CI e publica `linux/amd64` no GHCR. Se `main` avançar antes de iniciar, revisar
e emitir uma nova versão; não mover a tag antiga.

O resumo do workflow informa commit e referência completa `ghcr.io/...@sha256:...`.
Essa referência, não `latest` nem apenas a tag da imagem, entra no deploy manual.
O workflow não possui acesso ao computador do André nem faz publicação do site.
O build fica no GitHub, evitando carga de compilação no Docker compartilhado.

O pacote GHCR pode nascer privado mesmo com repositório público. Conferir sua
visibilidade. Se necessário, autenticar o pull no servidor com credencial somente
`read:packages` via `docker login --password-stdin`, sem colar token em comandos,
Git ou chat. A credencial de Git e a de registry são independentes.

## Clones e configuração local do Git

Produção usa clone exclusivo em `C:\docker\almoxarifado-prod`, com checkout
destacado na tag. Não editar código, fazer commit/push, trocar para `develop`
ou resolver conflitos nessa pasta. O script não executa `pull`, `fetch`, `checkout`
ou `reset`: preparar a versão é uma ação separada, visível e revisada.

Num clone de trabalho, configurar uma vez:

```powershell
git config --local push.default simple
git config --local pull.ff only
```

No clone de produção, usar `push.default nothing` e credencial somente leitura.
Uma deploy key sem permissão de escrita é adequada, mas é preciso garantir que
o clone realmente a utilize, em vez de uma credencial pessoal gravada no Windows.
`push.default nothing` bloqueia apenas push sem argumentos; não substitui a
permissão somente leitura. Usar `git status` antes de qualquer preparação.
Nunca usar `reset --hard`, `clean -fd`, force push ou troca de branch para apagar
uma divergência sem antes preservar e entender o trabalho.

`.env`, `.env.banco`, `.env.*`, `.deploy-ambiente`, `.deploy-*.json` e `dados/`
ficam fora do Git. Arquivos de exemplo não têm segredos. `.gitattributes` mantém
LF nos scripts e Compose. Migrations já aplicadas nunca são regeneradas/apagadas:
criar uma migration nova e publicar junto com o código correspondente.

## Proteções no GitHub

Proteger `main` e `develop`: exigir PR e checks `Aplicacao` e `Deploy Windows`,
bloquear force push e exclusão e aplicar as regras também aos administradores.
Habilitar revisão obrigatória se houver outro responsável disponível; não exigir
uma aprovação que o único mantenedor não pode dar ao próprio PR. Manter merge
commit habilitado para promoção entre branches permanentes.

Proteger também tags `v*` contra exclusão e atualização (ruleset), permitindo
criação pelo responsável. Não dar ao servidor de produção permissão de criar tags.
A CI deve rodar no GitHub, nunca num runner dentro da máquina de produção.
A configuração remota efetivamente aplicada deve ser conferida no PR; estes
arquivos por si só não configuram as regras do GitHub.

Referências: [branches protegidas](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches),
[deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys),
[GHCR](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
