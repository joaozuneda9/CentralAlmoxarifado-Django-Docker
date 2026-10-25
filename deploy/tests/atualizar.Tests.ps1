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
    if ($linha.Contains('config --format json')) {
        $vars = @{ LANCAMENTO_REAL = '0'; DEBUG = '0'; USAR_HTTPS = '1'; PROXY_HTTPS = '1'
            TELEGRAM_TOKEN = $global:AlmoxTesteToken
            TELEGRAM_CHAT_ID_SEGURANCA = $global:AlmoxTesteChatSeguranca }
        return (@{
            name = $env:PROJETO_COMPOSE
            services = @{
                web = @{ image = $env:IMAGEM_APP; environment = $vars
                    ports = @(@{host_ip = '127.0.0.1'; published = '8011'; target = 8010}) }
                agendador = @{ environment = $vars }
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

function Recusa {
    param([scriptblock]$Acao, [string]$Motivo)
    $erro = $null
    try { & $Acao } catch { $erro = $_.Exception.Message }
    if (-not $erro -or $erro -notlike "*$Motivo*") { throw "Esperava recusa '$Motivo'; recebeu '$erro'" }
    if ($global:AlmoxTesteChamadas | Where-Object { $_ -match ' (pull|build|run|up|stop|down|restart) ' }) {
        throw 'Uma recusa de preflight alterou o Docker.'
    }
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
    if ($global:AlmoxTesteChamadas | Where-Object { $_ -notmatch ' ps --status running --services$|config --format json$|^context show$' }) {
        throw 'Planejamento deve apenas consultar os servicos do projeto.'
    }
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
