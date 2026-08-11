$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path $PSScriptRoot -Parent
$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($listener -and $listener.LocalAddress -eq '127.0.0.1') {
    exit 0
}

$secretMatch = Select-String -Path (Join-Path $repoRoot '.env') -Pattern '^SANDBOX_SHARED_SECRET=(.+)$'
if (-not $secretMatch) {
    throw 'SANDBOX_SHARED_SECRET is missing from .env'
}

$runtimePath = Join-Path $repoRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
$env:ORDO_HOST_INFO_TOKEN = $secretMatch.Matches[0].Groups[1].Value
$pythonPath = (Get-Command python).Source
$agentPath = Join-Path $PSScriptRoot 'ordo_host_info_agent.py'

Start-Process `
    -FilePath $pythonPath `
    -ArgumentList @($agentPath, '--host', '127.0.0.1', '--port', '8765') `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtimePath 'host-info-agent.out.log') `
    -RedirectStandardError (Join-Path $runtimePath 'host-info-agent.err.log')
