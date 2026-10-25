# Ambientes no Docker Desktop compartilhado

## Destinos e situação atual

| | Atual → desenvolvimento (somente após virada) | Nova produção |
|---|---|---|
| Pasta | `C:\Users\laboratorio\Desktop\CentralAlmoxarifado-Django-Docker` | `C:\docker\almoxarifado-prod` |
| Projeto | `almoxarifado` (preservado deliberadamente) | `almoxarifado-prod` |
| Git | `develop` | Tag aprovada de `main`, HEAD destacado |
| Imagem | `central-almoxarifado-dev:<SHA>` | GHCR com digest e label de revisão |
| Banco | `almoxarifado_banco-dados` | `almoxarifado-prod_banco-dados` |
| Perfil SCPI | `almoxarifado_perfil-navegador` | `almoxarifado-prod_perfil-navegador` |
| Porta | Loopback, por exemplo `127.0.0.1:8012` | Preparação em `127.0.0.1:8011` |

As portas propostas ainda precisam ser conferidas no Windows antes de usar.
Volumes são prefixados pelo projeto. Bind mounts `./dados` ficam em cada clone.
O perfil antigo não é compartilhado com produção; novo perfil exige novo login
no SCPI e conferência das automações. O journal em `dados/logs` precisa ser
preservado na migração, especialmente se houver lançamento a conferir.

O marcador local `.deploy-ambiente` é uma confirmação operacional. **Não criá-lo
na instalação atual enquanto ela for produção.** O script de desenvolvimento
reutiliza intencionalmente o nome e os volumes antigos; esse marcador só pode ser
criado após o encerramento da produção antiga. As proteções do script não
impedem um administrador de executar Docker diretamente com alvo incorreto.

## Arquivos e comandos

`compose.yaml` é legado e permanece intacto para não alterar o projeto em uso.
Os novos comandos combinam explicitamente `compose.ambientes.yaml` com um único
overlay (`compose.desenvolvimento.yaml` ou `compose.producao.yaml`). Não há
`compose.override.yaml` implícito. Sempre usar o script no clone de destino.

`deploy/atualizar.ps1` funciona em PowerShell 5.1 ou superior e **planeja por
padrão**. Valida checkout limpo, marcador, branch/tag remota, imagem/projeto,
contexto Docker `desktop-linux`, porta loopback e variáveis herdadas do terminal.
Não imprime a configuração resolvida, pois ela contém senhas. Não usar
`docker compose config` para enviar configuração completa ao chat.

Somente com `-Aplicar` executa pull/build, conferência da revisão da imagem,
banco com espera de saúde, backup por container temporário (mesmo com web parado), check de produção, migrations
e subida dos serviços selecionados. Para produção já existente, exige também
`-ManutencaoConfirmada`. Isso **não pausa as gravações**: a janela e o bloqueio
de acesso/tarefas são coordenados separadamente. Checar robôs não impede que
outro usuário comece um depois; nunca atualizar com operação em andamento.

Nenhum comando faz `down`, prune, remove volumes, reinicia daemon ou altera GIS.
Uma migration pode alterar o banco e recriar web interrompe suas requisições:
`-Aplicar` não é uma operação apenas de consulta.

## Preparar produção nova (após merge e release)

Não executar esta seção sobre a pasta antiga. Clonar o repositório para
`C:\docker\almoxarifado-prod`, preferencialmente com credencial somente leitura.
Conferir `git status`, fazer fetch de `main` e tags e checkout destacado da tag
escolhida. Exemplo, com versão já publicada:

```powershell
git -C C:\docker\almoxarifado-prod fetch origin --tags
git -C C:\docker\almoxarifado-prod switch --detach v1.0.0
```

Criar `.env` a partir de `.env.example`, `.env.banco` a partir de
`.env.banco.example` e restringir acesso às contas administradoras no Windows.
Criar o marcador **somente no clone novo** com conteúdo `producao`.
Usar chaves/senhas novas, sem copiar `.env` de produção para desenvolvimento.

| Variável no `.env` de produção | Preparação |
|---|---|
| `SECRET_KEY` | Chave forte exclusiva; manter estável após a virada |
| `DEBUG` | `0` |
| `ALLOWED_HOSTS` | Host real planejado e host usado na validação local, sem `*` |
| `CSRF_TRUSTED_ORIGINS` | Origem HTTPS real, com esquema |
| `USAR_HTTPS`, `PROXY_HTTPS` | `1`, `1` |
| `PREFIXO_URL` | Vazio se acesso na raiz; não copiar `/almoxarifado` sem decisão |
| `PORTA_WEB` | `8011` após conferir disponibilidade; somente o número, sem IP |
| `DB_NAME`, `DB_USER` | `almoxarifado`, `almox` (banco isolado pelo volume/rede) |
| `DB_PASSWORD` | Senha nova, diferente da instalação antiga |
| `LANCAMENTO_REAL` | `0` |
| `SAEP_USER`, `SAEP_PASS`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_CHAT_ID_SEGURANCA` | Vazios |

Em `.env.banco`, preencher apenas `MARIADB_ROOT_PASSWORD`, outra senha forte.
Senhas contendo `$` devem usar aspas simples nos arquivos dotenv. Mudar os
arquivos depois da criação do banco não altera automaticamente suas senhas.
Criar `dados/logs`, `dados/backups`, `dados/importacao`. O container usa UID 1000;
validar escrita pelos containers no Docker Desktop antes de considerar pronto.

`PORTA_PUBLICADA` pertence apenas ao Compose legado, que não foi alterado para
preservar a instalação atual. Nos novos ambientes, o Compose fixa `127.0.0.1`;
`PORTA_WEB` escolhe somente o número da porta (desenvolvimento: `8012`). Um valor
com IP é inválido, inclusive na execução direta do Compose.

No clone novo, usando o digest do resumo do workflow (substituir os placeholders):

```powershell
.\deploy\atualizar.ps1 -Ambiente producao -Versao v1.0.0 -Imagem 'ghcr.io/joaozuneda8/centralalmoxarifado-django-docker@sha256:<digest>'
```

Sem `-Aplicar`, não cria pasta, imagem ou container. A verificação da label da
imagem só ocorre durante aplicação, após pull. O planejamento faz consultas ao
GitHub e ao Docker, por isso precisa de acesso de leitura aos dois.

Aplicar sem `-AtivarOperacao` sobe somente banco/web e exige credenciais de
integração vazias. Agendador não sobe. Apenas `LANCAMENTO_REAL=0` não basta para
bloquear Telegram e importações, por isso há verificações adicionais.

O HTTPS ainda depende de decisão e configuração de domínio/certificado/proxy.
O script exige essas opções, mas não instala proxy nem confirma TLS. Para
validação local por HTTP do backend, é possível enviar `X-Forwarded-Proto: https`
com Host permitido, somente via loopback. Isso não é HTTPS para usuários.
Não publicar o backend diretamente na rede: o waitress confia nos headers do
proxy. O MikroTik deve encaminhar ao proxy HTTPS, não à porta loopback 8011.

## Copiar dados sem afetar a instalação atual

Esta seção é um roteiro; os comandos de restauração serão preparados para os
nomes e arquivos efetivos, revisados antes de executados no Windows.

1. Copiar um `.sql.gz` existente para a pasta de backups nova, preservando o original.
   Não copiar `/var/lib/mysql` de um banco em execução.
2. Na produção nova, parar **somente seus serviços web/agendador**, se já criados,
   e restaurar o dump no seu banco. Conferir o projeto/volume antes de qualquer
   operação destrutiva. Nunca apontar o cliente de restauração ao banco antigo.
3. Subir a versão nova com migrations aplicadas ao banco restaurado, operação
   real bloqueada. Conferir quantidades, últimos pedidos, atendimentos e saídas
   contra a origem; testar logins, painel, permissões e backup/restauração.
4. Copiar os arquivos necessários de `dados/logs` (incluindo journal), backups
   e importações úteis. Não reutilizar o volume de perfil SCPI nem credenciais.
5. Coordenar janela de virada: bloquear novas gravações/robôs e desativar o
   agendador **apenas do projeto antigo**, esperar tarefas concluírem, gerar
   dump final consistente e copiar os arquivos finais. Não reiniciar Docker.
6. Repetir restauração/conferência no destino. O dump inicial não contém pedidos
   feitos após sua geração e não serve como cópia final.
7. Configurar acesso HTTPS e, com André, trocar o encaminhamento externo. Manter
   a origem sem gravações; não deixar duas instalações atendendo usuários.
8. Preencher credenciais de operação apenas na nova produção; usar explicitamente
   `-Aplicar -AtivarOperacao -ManutencaoConfirmada` após conferir que o agendador e
   lançamentos da origem estão bloqueados. A ativação sobe o agendador com seus
   horários; só liberar `LANCAMENTO_REAL=1` depois da conferência do SCPI.
9. Testar primeiro lançamento controlado e backup. Guardar registro da versão,
   imagem/digest, horário do dump e do último pedido migrado.

## Converter a instalação antiga em desenvolvimento

Só depois da virada concluída. Preservar antes alterações locais e a referência
da versão anterior. Parar o agendador antigo em janela específica. Preparar o
clone na `develop` aprovada, trocar credenciais do banco de testes de maneira
coordenada (editar `.env` sozinho não troca a senha já persistida no MariaDB),
remover credenciais reais do SCPI/Telegram e manter `LANCAMENTO_REAL=0`.

O overlay de desenvolvimento força integrações vazias mesmo se o arquivo `.env`
contiver valores antigos. Não exportar segredos reais para essa pasta. Restringir
a porta a loopback e removê-la do encaminhamento externo. Manter dados de teste
controlados, reduzindo os dados pessoais copiados quando possível.

Criar então o marcador `desenvolvimento` na pasta antiga. O projeto continua
`almoxarifado` e preserva seus volumes, mas usa a imagem exclusiva de dev. O
script recusa aplicação se detectar agendador antigo ativo; não o para sozinho.
Planejar e, após revisar, aplicar:

```powershell
.\deploy\atualizar.ps1 -Ambiente desenvolvimento
# Em outra etapa, apos conferir o plano:
.\deploy\atualizar.ps1 -Ambiente desenvolvimento -Aplicar
```

Atualizar o clone para `develop` por fast-forward antes de cada validação; nada
é enviado a produção por esse comando. O agendador de desenvolvimento permanece
desligado. O perfil Compose não é uma barreira de permissão: iniciar explicitamente
esse serviço pelo Docker pode ativá-lo. Usar sempre o script e não ligar
agendamentos de testes que possam competir com produção.

## Atualizações de produção e recuperação

Preparar tag/digest aprovados em clone limpo, conferir backup e janela sem
usuários/tarefas, planejar e aplicar explicitamente com os switches necessários.
O script não bloqueia usuários, não acompanha a saúde HTTP e não muda o MikroTik.
Se falhar, para no comando; não continuar cegamente nem apagar dados/volumes.

Voltar a imagem anterior não desfaz migrations. Verificar compatibilidade e
preparar restauração específica antes de rollback do banco; restaurar um backup
antigo perde gravações posteriores. O ambiente antigo com novos dados de teste
não é uma origem segura para recuperação da produção nova.

Copiar backups para fora dessa máquina e testar restauração. Isolamento de projeto
não isola memória/CPU: build de desenvolvimento e Chromium continuam compartilhando
recursos com GIS. Não executar carga/robôs simultâneos durante operação crítica.
Recuperação após reinício continua pendente de validação, sem reiniciar a máquina.
