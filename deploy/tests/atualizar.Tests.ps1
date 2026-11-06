# Testes de contrato: Git real temporario e Docker substituido, nunca acessa o daemon.
$ErrorActionPreference = 'Stop'
$global:AlmoxTesteOrigem = Split-Path -Parent $PSScriptRoot
$global:AlmoxTesteDestino = Join-Path ([IO.Path]::GetTempPath()) ('almox deploy ' + [guid]::NewGuid())
$global:AlmoxTesteRemoto = $global:AlmoxTesteDestino + '-remoto.git'
$global:AlmoxTesteChamadas = [Collections.Generic.List[string]]::new()
$global:AlmoxTesteRevision = ''
$global:AlmoxTesteServicos = @()
$global:AlmoxTesteFalhar = ''
$global:AlmoxTesteToken = ''
$global:AlmoxTesteChatSeguranca = ''
$global:AlmoxTesteHttps = '0'
$global:AlmoxTesteProxy = '--listen=0.0.0.0:8010'
$global:AlmoxTestePortaDev = '127.0.0.1'
$global:AlmoxTestePastaProjeto = @()
$global:AlmoxTesteVolumes = @()
$global:AlmoxTesteVolumesExistentes = @()
$global:AlmoxTesteOrigemVolume = @()
$global:AlmoxTesteDigest = 'ghcr.io/joaozuneda9/centralalmoxarifado-django-docker@sha256:' + ('a' * 64)

function docker {
    $linha = $args -join ' '
    $global:AlmoxTesteChamadas.Add($linha)
    $global:LASTEXITCODE = 0
    if ($global:AlmoxTesteFalhar -and $linha.Contains($global:AlmoxTesteFalhar)) {
        $global:LASTEXITCODE = 1
        return
    }
    if ($linha.Contains('ps --status running --services')) { return $global:AlmoxTesteServicos }
    if ($linha -eq 'context show') { return 'desktop-linux' }
    # Containers: o ps devolve IDs ("projeto<i>" ou "volume<i>", um por pasta nao vazia; a pasta
    # vazia simula container sem o rotulo working_dir) e o inspect devolve os rotulos como mapa
    # JSON, um por linha, sem aspas internas no formato (o PowerShell 5.1 as tiraria).
    $ids = {
        param([string]$Prefixo, $Pastas)
        $i = 0
        foreach ($pasta in @($Pastas)) { "$Prefixo$i"; $i++ }
    }
    if ($linha.StartsWith('ps -a -q --filter label=com.docker.compose.project=')) {
        return (& $ids 'projeto' $global:AlmoxTestePastaProjeto)
    }
    if ($linha.StartsWith('ps -a -q --filter volume=')) {
        return (& $ids 'volume' $global:AlmoxTesteOrigemVolume)
    }
    if ($linha.StartsWith('volume ls --quiet --filter label=com.docker.compose.project=')) {
        return $global:AlmoxTesteVolumes
    }
    # Todos os volumes do Docker, com ou sem rotulo do Compose.
    if ($linha -eq 'volume ls --quiet') { return $global:AlmoxTesteVolumesExistentes }
    if ($linha.StartsWith('inspect --format {{json .Config.Labels}} ')) {
        foreach ($id in $args[3..($args.Count - 1)]) {
            if ($id -match '^projeto(\d+)$') { $pasta = @($global:AlmoxTestePastaProjeto)[[int]$Matches[1]] }
            elseif ($id -match '^volume(\d+)$') { $pasta = @($global:AlmoxTesteOrigemVolume)[[int]$Matches[1]] }
            else { throw "ID inesperado: $id" }
            # '' = container com rotulos, mas sem working_dir; 'SEM-ROTULOS' = nenhum rotulo (null).
            if ($pasta -eq 'SEM-ROTULOS') { 'null'; continue }
            $mapa = @{ 'com.docker.compose.project' = 'x' }
            if (-not [string]::IsNullOrWhiteSpace($pasta)) { $mapa['com.docker.compose.project.working_dir'] = $pasta }
            $mapa | ConvertTo-Json -Compress
        }
        return
    }
    if ($linha.Contains('config --format json')) {
        $vars = @{ LANCAMENTO_REAL = '0'; DEBUG = '0'
            USAR_HTTPS = $global:AlmoxTesteHttps; PROXY_HTTPS = $global:AlmoxTesteHttps
            TELEGRAM_TOKEN = $global:AlmoxTesteToken
            TELEGRAM_CHAT_ID_SEGURANCA = $global:AlmoxTesteChatSeguranca }
        # Producao: HTTP direto na rede (compose.producao.yaml); desenvolvimento: loopback.
        if ($env:AMBIENTE_DEPLOY -eq 'producao') {
            $porta = @{host_ip = '0.0.0.0'; published = '8012'; target = 8010}
            $comando = @('python', '-m', 'waitress', $global:AlmoxTesteProxy, 'config.wsgi:application')
        } else {
            $porta = @{host_ip = $global:AlmoxTestePortaDev; published = '8012'; target = 8010}
            $comando = @('python', '-m', 'waitress', '--trusted-proxy=*', 'config.wsgi:application')
        }
        return (@{
            name = $env:PROJETO_COMPOSE
            services = @{
                web = @{ image = $env:IMAGEM_APP; environment = $vars; command = $comando
                    ports = @($porta) }
                agendador = @{ environment = $vars }
            }
            volumes = @{
                'banco-dados' = @{ name = "$($env:PROJETO_COMPOSE)_banco-dados" }
                'perfil-navegador' = @{ name = "$($env:PROJETO_COMPOSE)_perfil-navegador" }
            }
        } | ConvertTo-Json -Depth 8 -Compress)
    }
    if ($linha.StartsWith('image inspect')) {
        return (@{ 'org.opencontainers.image.revision' = $global:AlmoxTesteRevision } | ConvertTo-Json -Compress)
    }
}

function Git-Teste {
    & git -C $global:AlmoxTesteDestino @args
    if ($LASTEXITCODE -ne 0) { throw "Git do teste falhou: $args" }
}

function Executar {
    param([string]$Ambiente = 'producao', [string]$Versao = 'v1.0.0', [switch]$Aplicar, [switch]$AtivarOperacao,
        [switch]$ManutencaoConfirmada)
    $global:AlmoxTesteChamadas.Clear()
    $parametros = @{ Ambiente = $Ambiente }
    if ($Ambiente -eq 'producao') {
        $parametros.Versao = $Versao
        $parametros.Imagem = $global:AlmoxTesteDigest
    }
    if ($Aplicar) { $parametros.Aplicar = $true }
    if ($AtivarOperacao) { $parametros.AtivarOperacao = $true }
    if ($ManutencaoConfirmada) { $parametros.ManutencaoConfirmada = $true }
    & (Join-Path $global:AlmoxTesteDestino 'deploy/atualizar.ps1') @parametros | Out-Null
}

# Lista de permissoes, nao de proibicoes: so estas consultas podem acontecer antes de -Aplicar.
# Qualquer outra chamada (inclusive "volume prune --force" ou "volume rm") reprova o teste.
$global:AlmoxTesteConsultas = @(
    '^context show$'
    ' config --format json$'
    ' ps --status running --services$'
    '^ps -a -q --filter label=com\.docker\.compose\.project=almoxarifado(_prod)?$'
    '^ps -a -q --filter volume=[A-Za-z0-9_.-]+$'
    '^volume ls --quiet( --filter label=com\.docker\.compose\.project=almoxarifado(_prod)?)?$'
    '^inspect --format \{\{json \.Config\.Labels\}\}( (projeto|volume)[0-9]+)+$'
) -join '|'

function Somente-Consultas {
    param([string]$Motivo)
    $fora = @($global:AlmoxTesteChamadas | Where-Object { $_ -cnotmatch $global:AlmoxTesteConsultas })
    if ($fora.Count) { throw "$Motivo Chamada fora da lista: $($fora[0])" }
}

function Recusa {
    param([scriptblock]$Acao, [string]$Motivo)
    $erro = $null
    try { & $Acao } catch { $erro = $_.Exception.Message }
    if (-not $erro -or $erro -notlike "*$Motivo*") { throw "Esperava recusa '$Motivo'; recebeu '$erro'" }
    Somente-Consultas 'Uma recusa de preflight alterou o Docker.'
}

try {
    New-Item -ItemType Directory -Path (Join-Path $global:AlmoxTesteDestino 'deploy') -Force | Out-Null
    Copy-Item (Join-Path $global:AlmoxTesteOrigem 'atualizar.ps1') (Join-Path $global:AlmoxTesteDestino 'deploy')
    $raiz = Split-Path -Parent $global:AlmoxTesteOrigem
    foreach ($arquivo in @('compose.ambientes.yaml', 'compose.desenvolvimento.yaml', 'compose.producao.yaml')) {
        Copy-Item (Join-Path $raiz $arquivo) $global:AlmoxTesteDestino
    }
    '.env', '.env.banco', '.deploy-ambiente', 'dados/' | Set-Content (Join-Path $global:AlmoxTesteDestino '.gitignore')
    'DB_USER=almox', 'DB_PASSWORD=teste', 'SECRET_KEY=teste', 'LANCAMENTO_REAL=0' |
        Set-Content (Join-Path $global:AlmoxTesteDestino '.env')
    'MARIADB_ROOT_PASSWORD=teste' | Set-Content (Join-Path $global:AlmoxTesteDestino '.env.banco')
    'producao' | Set-Content (Join-Path $global:AlmoxTesteDestino '.deploy-ambiente')
    Git-Teste init -b main | Out-Null
    Git-Teste config user.name Teste
    Git-Teste config user.email teste@example.invalid
    Git-Teste add .
    Git-Teste commit -m inicial | Out-Null
    $global:AlmoxTesteRevision = (Git-Teste rev-parse HEAD).Trim()
    Git-Teste tag v1.0.0
    Git-Teste tag -a v1.0.1 -m release
    Git-Teste update-ref refs/remotes/origin/main $global:AlmoxTesteRevision
    Git-Teste branch develop
    Git-Teste update-ref refs/remotes/origin/develop $global:AlmoxTesteRevision
    # Remoto independente, local e descartavel: nao conecta ao GitHub.
    & git clone --bare --quiet $global:AlmoxTesteDestino $global:AlmoxTesteRemoto
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel criar remoto local de teste.' }
    Git-Teste remote add origin $global:AlmoxTesteRemoto

    Recusa { Executar } 'destacado'
    Git-Teste checkout -q --detach v1.0.0
    Executar
    Somente-Consultas 'Planejamento deve apenas consultar o Docker.'
    # A propria lista recusa o que nao e consulta.
    $global:AlmoxTesteChamadas.Add('volume prune --force')
    $vazou = $false
    try { Somente-Consultas 'x' } catch { $vazou = $true }
    if (-not $vazou) { throw 'A lista de consultas aceitou volume prune.' }
    # -notmatch ignora maiusculas: digest e versao precisam da comparacao exata.
    $digestValido = $global:AlmoxTesteDigest
    $global:AlmoxTesteDigest = $digestValido.Substring(0, $digestValido.Length - 64) + ('A' * 64)
    Recusa { Executar } 'GHCR'
    $global:AlmoxTesteDigest = $digestValido
    Recusa { Executar -Versao V1.0.0 } 'vMAJOR'
    # Producao e HTTP direto: HTTPS ou proxy ligados quebrariam o acesso ou abririam forja.
    $global:AlmoxTesteHttps = '1'
    Recusa { Executar } 'HTTP direto'
    $global:AlmoxTesteHttps = '0'
    $global:AlmoxTesteProxy = '--trusted-proxy=*'
    Recusa { Executar } 'trusted-proxy'
    $global:AlmoxTesteProxy = '--listen=0.0.0.0:8010'
    # O mesmo projeto (e banco) a partir de outro clone, como o abandonado almoxarifado-prod.
    $global:AlmoxTestePastaProjeto = @('C:\docker\almoxarifado-prod')
    Recusa { Executar } 'noutra pasta'
    # A mesma pasta, com barras e maiusculas diferentes: aceita.
    $mesmaPasta = $global:AlmoxTesteDestino.Replace('\', '/').ToUpperInvariant() + '/'
    $global:AlmoxTestePastaProjeto = @($mesmaPasta)
    Executar
    # Um container do projeto sem rotulo de origem, ao lado de um desta pasta: recusa.
    $global:AlmoxTestePastaProjeto = @($mesmaPasta, '')
    Recusa { Executar } 'sem rotulo de origem'
    $global:AlmoxTestePastaProjeto = @()
    # Containers removidos, volumes do projeto ainda la: a origem precisa ser comprovada.
    $global:AlmoxTesteVolumes = @('almoxarifado_prod_banco-dados', '')
    $global:AlmoxTesteOrigemVolume = @()
    Recusa { Executar } 'comprove a origem'
    $global:AlmoxTesteOrigemVolume = @('C:\docker\almoxarifado-prod')
    Recusa { Executar } 'outra pasta'
    # Cenario misto: um consumidor desta pasta e outro sem origem (sem working_dir, ou sem
    # rotulo algum). O desta pasta nao basta: o outro tambem precisa ser comprovado.
    foreach ($desconhecido in @('', 'SEM-ROTULOS')) {
        $global:AlmoxTesteOrigemVolume = @(($global:AlmoxTesteDestino + '\'), $desconhecido)
        Recusa { Executar } 'sem rotulo de origem'
    }
    # Montado por container desta pasta (parado ou nao): aceita, sem alterar nada.
    $global:AlmoxTesteOrigemVolume = @(($global:AlmoxTesteDestino.Replace('\', '/') + '/'))
    Executar
    Somente-Consultas 'Conferir a origem dos volumes nao pode alterar o Docker.'
    if (-not ($global:AlmoxTesteChamadas | Where-Object { $_ -ceq 'ps -a -q --filter volume=almoxarifado_prod_banco-dados' })) {
        throw 'A origem do volume nao foi conferida.'
    }
    $global:AlmoxTesteVolumes = @()
    $global:AlmoxTesteOrigemVolume = @()
    # Volume criado fora do Compose (sem rotulo) com o nome que a configuracao usa: o Compose o
    # reutilizaria, entao tambem precisa de origem comprovada. Volume de outro nome nao conta.
    $global:AlmoxTesteVolumesExistentes = @('gis-stack_dados', 'almoxarifado_prod_banco-dados')
    Recusa { Executar } 'comprove a origem'
    $global:AlmoxTesteOrigemVolume = @(($global:AlmoxTesteDestino + '\'))
    Executar
    Somente-Consultas 'Conferir volume sem rotulo nao pode alterar o Docker.'
    $global:AlmoxTesteVolumesExistentes = @('gis-stack_dados', 'almoxarifado-prod_banco-dados')
    $global:AlmoxTesteOrigemVolume = @()
    Executar
    $global:AlmoxTesteVolumesExistentes = @()
    # Compose no Windows pode emitir uma linha vazia quando nao ha servicos.
    foreach ($saidaVazia in @('', " `t")) {
        $global:AlmoxTesteServicos = @($saidaVazia)
        Executar -Aplicar
        if (-not ($global:AlmoxTesteChamadas | Where-Object { $_ -match 'up -d --no-build --pull never web$' })) {
            throw 'Primeira instalacao com saida vazia deve subir o web sem exigir manutencao.'
        }
        if ($global:AlmoxTesteChamadas | Where-Object { $_ -match 'up .*agendador' }) {
            throw 'Primeira instalacao nao pode ativar agendador.'
        }
    }
    $global:AlmoxTesteServicos = @('', 'banco', '')
    Recusa { Executar -Aplicar } 'manutencao'
    $global:AlmoxTesteServicos = @('', 'agendador', '')
    Recusa { Executar -Aplicar -ManutencaoConfirmada } 'Agendador ativo'
    $global:AlmoxTesteServicos = @()
    Git-Teste checkout -q --detach v1.0.1
    Executar -Versao v1.0.1
    Git-Teste commit --allow-empty -m divergencia | Out-Null
    Git-Teste tag v9.0.0
    Git-Teste push --quiet origin ($global:AlmoxTesteRevision + ':refs/tags/v9.0.0')
    Recusa { Executar -Versao v9.0.0 -Aplicar } 'Tag ausente'
    Git-Teste checkout -q --detach v1.0.0
    'desenvolvimento' | Set-Content (Join-Path $global:AlmoxTesteDestino '.deploy-ambiente')
    Recusa { Executar -Aplicar } 'marcador'
    'producao' | Set-Content (Join-Path $global:AlmoxTesteDestino '.deploy-ambiente')
    Add-Content (Join-Path $global:AlmoxTesteDestino '.gitignore') '# alteracao local'
    Recusa { Executar -Aplicar } 'alteracoes locais'
    Git-Teste restore .gitignore
    $global:AlmoxTesteServicos = @('web', 'banco', 'agendador')
    Recusa { Executar -Aplicar } 'manutencao'
    Recusa { Executar -Aplicar -AtivarOperacao -ManutencaoConfirmada } 'Agendador ativo'
    $global:AlmoxTesteServicos = @()
    $global:AlmoxTesteToken = 'token-que-nao-pode-enviar'
    Recusa { Executar -Aplicar } 'integracoes vazias'
    # Producao em operacao (deploy/AMBIENTES.md): o planejamento tambem leva -AtivarOperacao e
    # aceita o agendador rodando; sem a opcao, recusa pelas integracoes preenchidas.
    $global:AlmoxTesteServicos = @('web', 'banco', 'agendador')
    Recusa { Executar } 'integracoes vazias'
    Executar -AtivarOperacao
    Somente-Consultas 'Planejamento com -AtivarOperacao nao pode alterar o Docker.'
    $global:AlmoxTesteServicos = @()
    $global:AlmoxTesteToken = ''
    # O chat da Seguranca do Trabalho (spec 008) tambem conta como integracao.
    $global:AlmoxTesteChatSeguranca = '-100123'
    Recusa { Executar -Aplicar } 'integracoes vazias'
    $global:AlmoxTesteChatSeguranca = ''
    $global:AlmoxTesteRevision = 'b' * 40
    $falhou = $false
    try { Executar -Aplicar } catch { $falhou = $_.Exception.Message -like '*revisao*' }
    if (-not $falhou) { throw 'Imagem divergente deve ser recusada.' }
    if ($global:AlmoxTesteChamadas | Where-Object { $_ -match ' (run|up) ' }) {
        throw 'Imagem divergente chegou a executar a aplicacao.'
    }
    $global:AlmoxTesteRevision = (Git-Teste rev-parse HEAD).Trim()
    # Banco em uso, mas web parado para manutencao: ainda precisa de backup.
    $global:AlmoxTesteServicos = @('banco')
    Executar -Aplicar -ManutencaoConfirmada
    $backup = @($global:AlmoxTesteChamadas | Where-Object { $_ -match 'run --rm --no-deps web python manage.py backup_banco$' })
    $migrate = @($global:AlmoxTesteChamadas | Where-Object { $_ -match 'migrate --noinput$' })
    if ($backup.Count -ne 1 -or $migrate.Count -ne 1 -or
        $global:AlmoxTesteChamadas.IndexOf($backup[0]) -ge $global:AlmoxTesteChamadas.IndexOf($migrate[0])) {
        throw 'Backup com web parado deve acontecer antes de migrate.'
    }
    if (-not ($global:AlmoxTesteChamadas | Where-Object { $_ -match 'up -d --no-build --pull never web$' })) {
        throw 'Aplicacao nao subiu o web explicitamente.'
    }
    if ($global:AlmoxTesteChamadas | Where-Object { $_ -match 'up .*agendador' }) {
        throw 'Preparacao ativou agendador.'
    }
    $global:AlmoxTesteFalhar = 'manage.py backup_banco'
    try { Executar -Aplicar -ManutencaoConfirmada; throw 'Backup deveria falhar' } catch {
        if ($_.Exception.Message -notlike '*Docker falhou*') { throw }
    }
    if ($global:AlmoxTesteChamadas | Where-Object { $_ -match 'check --deploy|migrate|up -d .*web' }) {
        throw 'Falha no backup deveria impedir verificacoes, migrations e web.'
    }
    $global:AlmoxTesteServicos = @()
    $global:AlmoxTesteFalhar = 'check --deploy'
    try { Executar -Aplicar; throw 'Check deveria falhar' } catch {
        if ($_.Exception.Message -notlike '*Docker falhou*') { throw }
    }
    if ($global:AlmoxTesteChamadas | Where-Object { $_ -match 'migrate|up -d .*web' }) {
        throw 'Falha no check deveria impedir migrations e web.'
    }
    $global:AlmoxTesteFalhar = ''
    Git-Teste checkout -q develop
    'desenvolvimento' | Set-Content (Join-Path $global:AlmoxTesteDestino '.deploy-ambiente')
    Executar -Ambiente desenvolvimento
    $global:AlmoxTestePortaDev = '0.0.0.0'
    Recusa { Executar -Ambiente desenvolvimento } '127.0.0.1'
    $global:AlmoxTestePortaDev = '127.0.0.1'
    Recusa { Executar -Ambiente desenvolvimento -AtivarOperacao } 'operacao real'
    $env:COMPOSE_PROJECT_NAME = 'gis-stack'
    Recusa { Executar -Ambiente desenvolvimento } 'herdada'
    Remove-Item Env:COMPOSE_PROJECT_NAME
    Write-Output 'PASS: recusas, planejamento, imagem, isolamento e falha de comando.'
} finally {
    Remove-Item Env:COMPOSE_PROJECT_NAME -ErrorAction SilentlyContinue
    if (Test-Path $global:AlmoxTesteDestino) { Remove-Item $global:AlmoxTesteDestino -Recurse -Force }
    if (Test-Path $global:AlmoxTesteRemoto) { Remove-Item $global:AlmoxTesteRemoto -Recurse -Force }
}
