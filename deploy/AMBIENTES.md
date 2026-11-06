# Ambientes no Docker Desktop compartilhado

## Situação atual

Conferida no servidor em 06/11/2026, com `docker ps`, os rótulos do Compose e os
arquivos de cada pasta.

| | Produção | Desenvolvimento |
|---|---|---|
| Pasta | `C:\docker\producao` | `C:\Users\laboratorio\Desktop\CentralAlmoxarifado-Django-Docker` |
| Projeto Compose | `almoxarifado_prod` | `almoxarifado` |
| Arquivos Compose | `compose.ambientes.yaml` + `compose.producao.yaml` (veja "Passagem única") | `compose.ambientes.yaml` + `compose.desenvolvimento.yaml` |
| Git | Tag de `main`, HEAD destacado | `develop` |
| Imagem | GHCR por digest, com label de revisão | `central-almoxarifado-dev:<SHA>` (build local) |
| Containers | `almoxarifado_prod` (web), `almoxarifado_prod-agendador-1`, `almoxarifado_prod-banco-1` | `almoxarifado-web-1`, `-agendador-1`, `-banco-1` (parados) |
| Banco | Volume `almoxarifado_prod_banco-dados` | Volume `almoxarifado_banco-dados` |
| Perfil SCPI | Volume `almoxarifado_prod_perfil-navegador` | Volume `almoxarifado_perfil-navegador` |
| Porta | `0.0.0.0:8012`, HTTP direto na rede (`PORTA_WEB`, padrão 8012) | `127.0.0.1:8011` (`PORTA_WEB`, padrão 8011) |
| Marcador `.deploy-ambiente` | `producao` | `desenvolvimento` |
| Operação real | `LANCAMENTO_REAL=1`, SCPI e Telegram preenchidos, agendador ligado | Integrações forçadas vazias pelo overlay, agendador nunca sobe |

Volumes são prefixados pelo projeto, por isso o nome do projeto é o que escolhe
o banco: o mesmo projeto rodado de outra pasta usaria o mesmo banco com outro
`.env` e outra `dados/`. O `atualizar.ps1` recusa quando os containers do
projeto foram criados noutra pasta (rótulo `com.docker.compose.project.working_dir`).
Bind mounts `./dados` ficam em cada pasta: logs (com o journal do lançamento),
backups e `.xlsx` de carga.

### Topologia de acesso: HTTP direto, sem proxy

Não há Apache, proxy nem HTTPS. O waitress publica na porta 8012 de todas as
interfaces do Windows (`192.168.0.241`), e o acesso externo chega por
encaminhamento do MikroTik (a regra exata é conferida com o André). Por isso:

- o waitress **não** usa `--trusted-proxy` (`compose.producao.yaml` substitui o
  comando da base): com a porta aberta na rede, qualquer cliente forjaria
  `x-forwarded-for` (que divide o limite por IP dos formulários) e
  `x-forwarded-proto`;
- o `.env` de produção tem `USAR_HTTPS=0` e `PROXY_HTTPS=0`. Com `USAR_HTTPS=0`,
  o `settings.py` silencia só os quatro avisos do `check --deploy` que são a
  consequência dessa decisão (W004, W008, W012, W016); os demais continuam
  barrando a atualização;
- o `atualizar.ps1` recusa produção com `USAR_HTTPS` ou `PROXY_HTTPS` diferentes
  de `0` e porta aberta na rede com `--trusted-proxy`. Desenvolvimento continua
  só em loopback.

Quando houver proxy HTTPS, o caminho de volta é: porta em `127.0.0.1`, o
comando da base (com `--trusted-proxy`), `USAR_HTTPS=1` e `PROXY_HTTPS=1` no
`.env`, e as verificações do script invertidas no mesmo PR.

### Pastas que não são ambiente

- `C:\docker\almoxarifado-prod`: clone da preparação de outubro (tag `v1.0.1`,
  marcador `producao`, volumes `almoxarifado-prod_*` de 20/10/2026). **Não é a
  produção** e nunca entrou em operação. Não rode o `atualizar.ps1` nele: o
  projeto de produção (`almoxarifado_prod`) foi criado em `C:\docker\producao`, e
  o script recusa. Retire o marcador `.deploy-ambiente` dessa pasta; apagar a
  pasta e os volumes `almoxarifado-prod_*` é decisão à parte, depois de conferir
  que nada dali é necessário.
- `C:\docker\resguardo-producao-20261023-163939`: o que foi guardado na virada de
  23/10/2026 (dump do banco antes da troca, o `.env` anterior, o `compose.yaml` e
  o script de importação). Contém segredos: não versionar nem enviar ao chat.

## Arquivos e comandos

`compose.yaml` é legado e não se altera; nenhum ambiente o usa depois da
passagem única. Os comandos combinam explicitamente `compose.ambientes.yaml` com
um único overlay (`compose.desenvolvimento.yaml` ou `compose.producao.yaml`).
Não há `compose.override.yaml` implícito. Sempre usar o script na pasta do
ambiente.

`deploy/atualizar.ps1` funciona em PowerShell 5.1 ou superior e **planeja por
padrão**. Valida checkout limpo, marcador, branch/tag remota, imagem/projeto,
pasta de origem do projeto, contexto Docker `desktop-linux`, porta e topologia
de acesso e variáveis herdadas do terminal. Não imprime a configuração
resolvida, pois ela contém senhas. Não usar `docker compose config` para enviar
configuração completa ao chat.

Somente com `-Aplicar` executa pull/build, conferência da revisão da imagem,
banco com espera de saúde, backup por container temporário (mesmo com web
parado), check de produção, migrations e subida dos serviços selecionados. Para
produção já existente, exige também `-ManutencaoConfirmada`. Isso **não pausa as
gravações**: a janela e o bloqueio de acesso/tarefas são coordenados
separadamente. Checar robôs não impede que outro usuário comece um depois; nunca
atualizar com operação em andamento.

Nenhum comando faz `down`, prune, remove volumes, reinicia daemon ou altera GIS.
Uma migration pode alterar o banco e recriar web interrompe suas requisições
(e mata os robôs, filhos do waitress): `-Aplicar` não é uma operação apenas de
consulta.

## Atualizar a produção

Pré-requisitos: tag `vX.Y.Z` em `main` e a imagem aprovada do workflow **Imagem
de release** (`ghcr.io/joaozuneda9/centralalmoxarifado-django-docker@sha256:...`),
conforme [FLUXO_GIT.md](FLUXO_GIT.md). Num terminal PowerShell limpo, em
`C:\docker\producao`:

```powershell
git fetch origin --tags
git switch --detach vX.Y.Z
git status   # precisa estar limpo
$imagem = 'ghcr.io/joaozuneda9/centralalmoxarifado-django-docker@sha256:<digest>'
.\deploy\atualizar.ps1 -Ambiente producao -Versao vX.Y.Z -Imagem $imagem
```

Revisar o plano. Na janela combinada (sem usuários gravando nem robôs
rodando), parar **só o agendador deste projeto** e aplicar. A produção tem
integrações preenchidas, então toda aplicação usa `-AtivarOperacao`, que também
religa o agendador no fim:

```powershell
docker compose -p almoxarifado_prod stop agendador
.\deploy\atualizar.ps1 -Ambiente producao -Versao vX.Y.Z -Imagem $imagem `
    -Aplicar -AtivarOperacao -ManutencaoConfirmada
```

Depois: abrir o painel, conferir login, a página Automações e
`dados/logs`. O script não acompanha a saúde HTTP. Se falhar, ele para no
comando que falhou: não continuar cegamente nem apagar dados/volumes; religar o
agendador (`docker compose -p almoxarifado_prod start agendador`) só com a versão
anterior ou a nova inteira no ar.

## Passagem única: do `compose.yaml` editado ao script

Até a `v1.3.0`, a produção rodou do `compose.yaml` legado **editado à mão no
servidor** (projeto `almoxarifado_prod`, imagem por digest, `container_name`,
porta `0.0.0.0:8012`, sem `--trusted-proxy`), com o checkout sujo e sem
marcador; o `atualizar.ps1` recusava essa pasta. O `compose.producao.yaml`
passou a descrever exatamente essa instalação, com o mesmo projeto e os mesmos
volumes. A passagem é feita uma vez, na primeira versão que traz esta mudança,
dentro de uma janela de manutenção:

1. Guardar uma cópia do `compose.yaml` editado (por exemplo em
   `C:\docker\resguardo-producao-<data>\compose.yaml`) e conferir que o `.env`
   tem `USAR_HTTPS=0` e `PROXY_HTTPS=0`. `PORTA_PUBLICADA` deixa de ser lida;
   `PORTA_WEB` só precisa existir se a porta mudar de 8012.
2. Desfazer a edição local (`git restore compose.yaml`), trocar para a tag nova
   (`git switch --detach vX.Y.Z`) e conferir `git status` limpo.
3. Criar o marcador: `Set-Content .deploy-ambiente producao` (ignorado pelo Git).
4. Planejar e aplicar como em "Atualizar a produção". Os containers são
   recriados a partir dos arquivos novos, com os mesmos nomes e volumes; o
   banco pode ser recriado (o volume fica). O Compose pode avisar que o projeto
   foi criado com outros arquivos: é esperado nesta passagem.
5. Conferir que `docker compose ls` mostra `almoxarifado_prod` com
   `compose.ambientes.yaml,compose.producao.yaml` e que o volume em uso é
   `almoxarifado_prod_banco-dados` (os dados de antes continuam lá).

Rollback da passagem: o `compose.yaml` guardado no passo 1 e `docker compose -f
compose.yaml up -d` na pasta, como antes. Voltar a imagem não desfaz migrations.

## Desenvolvimento

O projeto continua `almoxarifado` e preserva seus volumes, mas usa a imagem
exclusiva de dev. O overlay força integrações vazias mesmo se o `.env` contiver
valores antigos; não exportar segredos reais para essa pasta. O script recusa
aplicação se detectar agendador ativo; não o para sozinho. Planejar e, após
revisar, aplicar:

```powershell
.\deploy\atualizar.ps1 -Ambiente desenvolvimento
# Em outra etapa, apos conferir o plano:
.\deploy\atualizar.ps1 -Ambiente desenvolvimento -Aplicar
```

Atualizar o clone para `develop` por fast-forward antes de cada validação; nada
é enviado a produção por esse comando. O agendador de desenvolvimento permanece
desligado. O perfil Compose não é uma barreira de permissão: iniciar
explicitamente esse serviço pelo Docker pode ativá-lo. Usar sempre o script e
não ligar agendamentos de testes que possam competir com produção.

## Recuperação

Voltar a imagem anterior não desfaz migrations. Verificar compatibilidade e
preparar restauração específica antes de rollback do banco; restaurar um backup
antigo perde gravações posteriores. O banco de desenvolvimento não é uma origem
segura para recuperação da produção.

Copiar backups para fora dessa máquina e testar restauração. Isolamento de
projeto não isola memória/CPU: build de desenvolvimento e Chromium continuam
compartilhando recursos com GIS. Não executar carga/robôs simultâneos durante
operação crítica. Recuperação após reinício continua pendente de validação, sem
reiniciar a máquina.

## Histórico

- Out/2026: preparada uma produção nova em `C:\docker\almoxarifado-prod`
  (projeto `almoxarifado-prod`, loopback 8011 atrás de um proxy HTTPS que nunca
  foi instalado). Não entrou em operação.
- 23/10/2026: virada para `C:\docker\producao`, projeto `almoxarifado_prod`,
  com o `compose.yaml` legado editado no servidor e HTTP direto na 8012. A
  instalação do Desktop virou o desenvolvimento. Resguardo em
  `C:\docker\resguardo-producao-20261023-163939`.
- 11/2026: `compose.producao.yaml` e `atualizar.ps1` passaram a descrever essa
  produção; a edição local acaba na passagem única.
