#Requires -Version 5.1
<#
Planeja por padrao. -Aplicar permite alteracoes apenas no projeto selecionado.
Nao faz pull/checkout do Git, down, prune, restart do daemon ou migracao entre bancos.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('desenvolvimento', 'producao')][string]$Ambiente,
    [string]$Versao,
    [string]$Imagem,
    [switch]$Aplicar,
    [switch]$AtivarOperacao,
    [switch]$ManutencaoConfirmada
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$raiz = Split-Path -Parent $PSScriptRoot

function Invoke-Git {
    $resultado = & git -C $raiz @args
    if ($LASTEXITCODE -ne 0) { throw "Git falhou; nenhuma atualizacao automatica sera feita: $args" }
    return $resultado
}

function Invoke-Compose {
    $resultado = & docker @script:compose @args
    if ($LASTEXITCODE -ne 0) { throw "Docker falhou: $args. Interrompido; nao ha rollback automatico." }
    return $resultado
}

function Get-Valor {
    param($Objeto, [string]$Nome)
    $propriedade = $Objeto.PSObject.Properties[$Nome]
    if ($null -eq $propriedade) { return '' }
    return [string]$propriedade.Value
}

$marcador = Join-Path $raiz '.deploy-ambiente'
if (-not (Test-Path -LiteralPath $marcador) -or
    (Get-Content -LiteralPath $marcador -Raw).Trim() -ne $Ambiente) {
    throw 'O marcador .deploy-ambiente nao corresponde ao ambiente solicitado.'
}
if ($AtivarOperacao -and $Ambiente -ne 'producao') {
    throw 'Desenvolvimento nao pode ativar operacao real.'
}
if (Invoke-Git rev-parse --show-prefix) {
    throw 'O script precisa estar na raiz do clone dedicado.'
}
if (Invoke-Git status --porcelain --untracked-files=normal) {
    throw 'Clone com alteracoes locais. Preserve e revise o trabalho; nao use reset --hard.'
}
$sha = (Invoke-Git rev-parse HEAD).Trim()
$branch = & git -C $raiz symbolic-ref --quiet --short HEAD
$branchStatus = $LASTEXITCODE
if ($Ambiente -eq 'producao') {
    if ($branchStatus -ne 1) { throw 'Producao exige checkout destacado (detached HEAD) de uma tag.' }
    if ($Versao -cnotmatch '^v[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Informe -Versao vMAJOR.MINOR.PATCH.' }
    if ($Imagem -cnotmatch '^ghcr\.io/joaozuneda9/centralalmoxarifado-django-docker@sha256:[a-f0-9]{64}$') {
        throw 'Producao exige -Imagem do GHCR deste projeto fixada por digest sha256.'
    }
    if ((Invoke-Git rev-parse "refs/tags/$Versao`^{commit}").Trim() -ne $sha) {
        throw 'A tag nao corresponde ao checkout.'
    }
    $referencias = @(Invoke-Git ls-remote origin "refs/tags/$Versao" "refs/tags/$Versao^{}" 'refs/heads/main')
    $tagRemota = @($referencias | Where-Object { $_ -match "refs/tags/$([regex]::Escape($Versao))(\^\{\})?$" })
    if (-not $tagRemota.Count -or ($tagRemota[-1] -split '\s+')[0] -ne $sha) {
        throw 'Tag ausente ou diferente no GitHub. Atualize as referencias e revise.'
    }
    $mainRemota = @($referencias | Where-Object { $_ -match 'refs/heads/main$' })
    if (-not $mainRemota.Count -or
        (Invoke-Git rev-parse refs/remotes/origin/main).Trim() -ne ($mainRemota[0] -split '\s+')[0]) {
        throw 'origin/main desatualizada. Execute fetch e revise antes de continuar.'
    }
    Invoke-Git merge-base --is-ancestor $sha refs/remotes/origin/main | Out-Null
    $projeto = 'almoxarifado-prod'
} else {
    if ($branchStatus -ne 0 -or $branch -ne 'develop') { throw 'Desenvolvimento exige a branch develop.' }
    $remota = @(Invoke-Git ls-remote origin refs/heads/develop)
    if (-not $remota.Count -or ($remota[0] -split '\s+')[0] -ne $sha) {
        throw 'develop local difere do GitHub. Publique o trabalho por PR e atualize o clone.'
    }
    $projeto = 'almoxarifado'
    $Imagem = "central-almoxarifado-dev:$sha"
}

# Compose da precedencia ao ambiente do terminal sobre .env. Recusar em vez de
# deixar senhas, portas ou projeto herdados selecionarem outro destino silenciosamente.
$nomes = @('COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'COMPOSE_PROFILES', 'DOCKER_HOST',
    'DOCKER_CONTEXT', 'PROJETO_COMPOSE', 'IMAGEM_APP', 'REVISAO_APP', 'AMBIENTE_DEPLOY', 'PORTA_WEB')
foreach ($arquivo in @('.env', '.env.banco')) {
    $caminho = Join-Path $raiz $arquivo
    if (-not (Test-Path -LiteralPath $caminho)) { throw "Falta $arquivo no clone dedicado." }
    foreach ($linha in Get-Content -LiteralPath $caminho) {
        if ($linha -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') { $nomes += $Matches[1] }
    }
}
foreach ($nome in ($nomes | Select-Object -Unique)) {
    if (Test-Path "Env:$nome") { throw "Variavel herdada do terminal: $nome. Use um terminal limpo." }
}
$env:PROJETO_COMPOSE = $projeto
$env:IMAGEM_APP = $Imagem
$env:REVISAO_APP = $sha
$env:AMBIENTE_DEPLOY = $Ambiente
try {
    $contexto = & docker context show
    if ($LASTEXITCODE -ne 0 -or ($contexto -join '').Trim() -ne 'desktop-linux') {
        throw 'Este roteiro exige o contexto desktop-linux do Docker Desktop local.'
    }
    $script:compose = @('compose', '--project-directory', $raiz, '--env-file', (Join-Path $raiz '.env'),
        '-p', $projeto, '-f', (Join-Path $raiz 'compose.ambientes.yaml'),
        '-f', (Join-Path $raiz "compose.$Ambiente.yaml"))
    # Nao imprimir config: inclui senhas. A saida e validada somente em memoria.
    $config = (Invoke-Compose --profile '*' config --format json) -join "`n" | ConvertFrom-Json
    if ($config.name -ne $projeto -or $config.services.web.image -ne $Imagem) {
        throw 'Projeto ou imagem resolvidos nao correspondem ao alvo.'
    }
    foreach ($servico in @('web', 'agendador')) {
        $vars = $config.services.$servico.environment
        $integracoes = @('SAEP_USER', 'SAEP_PASS', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID',
            'TELEGRAM_CHAT_ID_SEGURANCA')
        if (-not $AtivarOperacao) {
            if ((Get-Valor $vars 'LANCAMENTO_REAL') -ne '0' -or
                @($integracoes | Where-Object { (Get-Valor $vars $_) -ne '' }).Count) {
                throw 'Preparacao exige integracoes vazias e LANCAMENTO_REAL=0.'
            }
        }
        if ($Ambiente -eq 'producao' -and ((Get-Valor $vars 'DEBUG') -ne '0' -or
            (Get-Valor $vars 'USAR_HTTPS') -ne '1' -or (Get-Valor $vars 'PROXY_HTTPS') -ne '1')) {
            throw 'Producao exige DEBUG=0, USAR_HTTPS=1 e PROXY_HTTPS=1; configure HTTPS no proxy.'
        }
    }
    foreach ($porta in $config.services.web.ports) {
        if ($porta.host_ip -ne '127.0.0.1') { throw 'A porta precisa estar restrita a 127.0.0.1.' }
    }
    # Uma linha vazia do Compose nao representa um servico em execucao.
    $ativos = @(Invoke-Compose ps --status running --services |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($Aplicar -and $Ambiente -eq 'producao' -and $ativos.Count -and -not $ManutencaoConfirmada) {
        throw 'Producao existente exige janela de manutencao e -ManutencaoConfirmada.'
    }
    if ($ativos -contains 'agendador' -and ($Aplicar -or -not $AtivarOperacao)) {
        throw 'Agendador ativo: pause somente o agendador deste projeto na janela combinada antes de aplicar.'
    }
    Write-Output "Ambiente=$Ambiente Projeto=$projeto Commit=$sha Imagem=$Imagem"
    if (-not $Aplicar) {
        Write-Output 'Somente planejamento. Nenhum container ou arquivo foi alterado. Imagem ainda nao verificada.'
        return
    }
    if ($ativos -contains 'web') {
        Invoke-Compose exec -T web python manage.py robos_em_andamento | Out-Host
    }
    if ($Ambiente -eq 'producao') {
        Invoke-Compose pull web | Out-Host
    } else {
        Invoke-Compose build web | Out-Host
    }
    $labels = & docker image inspect $Imagem --format '{{json .Config.Labels}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker falhou ao conferir imagem.' }
    $labels = ($labels -join "`n") | ConvertFrom-Json
    if ((Get-Valor $labels 'org.opencontainers.image.revision') -ne $sha) {
        throw 'A revisao registrada na imagem difere do commit aprovado.'
    }
    # Atualizar um ambiente existente requer gravacoes e tarefas pausadas externamente.
    # Checar robos nao e uma trava global; o script nunca para usuarios automaticamente.
    Invoke-Compose pull banco | Out-Host
    Invoke-Compose up -d --wait --wait-timeout 120 --no-build --pull never banco | Out-Host
    # Container temporario: tambem protege banco existente quando web estiver parado.
    # Qualquer falha no backup interrompe antes de check/migrate.
    Invoke-Compose run --rm --no-deps web python manage.py backup_banco | Out-Host
    if ($Ambiente -eq 'producao') {
        Invoke-Compose run --rm --no-deps web python manage.py check --deploy --fail-level WARNING | Out-Host
    }
    Invoke-Compose run --rm --no-deps web python manage.py migrate --noinput | Out-Host
    Invoke-Compose up -d --no-build --pull never web | Out-Host
    if ($AtivarOperacao) {
        Invoke-Compose up -d --no-build --pull never agendador | Out-Host
    }
    Invoke-Compose ps | Out-Host
    Write-Output 'Comandos concluidos. Confira login, dados e logs; o script nao confirma a saude HTTP.'
} finally {
    foreach ($nome in @('PROJETO_COMPOSE', 'IMAGEM_APP', 'REVISAO_APP', 'AMBIENTE_DEPLOY')) {
        Remove-Item "Env:$nome" -ErrorAction SilentlyContinue
    }
}
