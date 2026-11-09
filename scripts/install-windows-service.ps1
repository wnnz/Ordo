<#
.SYNOPSIS
    将 Ordo C# 后端安装为 Windows 服务（单体：API + Worker + 调度 + Web + 宿主机插件 + Docker 沙箱）。

.DESCRIPTION
    流程：发布 win-x64 自包含二进制 -> 复制到安装目录 -> 写入服务级环境变量 -> 注册/更新服务 -> 启动并健康检查。
    数据目录默认使用 C:\ProgramData\Ordo\data；数据库沿用 Docker 中的 shared-postgres（默认 127.0.0.1:55432）。

.PARAMETER ServiceName
    Windows 服务名，默认 OrdoBackend。

.PARAMETER InstallDir
    程序安装目录，默认 D:\Program Files\Ordo\backend。

.PARAMETER DataDir
    数据目录（文件上传与沙箱产物），默认 D:\Program Files\Ordo\data。

.PARAMETER DatabaseUrl
    SQLAlchemy 风格数据库地址。默认沿用 Docker shared-postgres 的宿主映射端口 127.0.0.1:55432。

.PARAMETER BindAddress
    监听地址，支持逗号分隔多个地址；默认读取 .env 的 ORDO_BIND_ADDRESS，否则 127.0.0.1。
    经 SG2 回源时需包含 cn1-sg2 隧道地址 10.66.70.2。

.PARAMETER LogFile
    可选的安装日志文件路径（Start-Transcript）。自提权时自动写入 %TEMP%\ordo-install-*.log。

.PARAMETER Port
    监听端口，默认读取 .env 的 ORDO_PORT，否则 8000。

.PARAMETER BuildFrontend
    发布前先执行 frontend npm run build。

.PARAMETER SkipSandboxImage
    跳过 ordo-sandbox 运行时镜像检查/构建。

.PARAMETER Uninstall
    停止并删除服务（不删除安装目录与数据）。

.EXAMPLE
    .\install-windows-service.ps1 -BuildFrontend
#>
param(
    [switch]$NoElevation,
    [string]$ServiceName = 'OrdoBackend',
    [string]$InstallDir = 'D:\Program Files\Ordo\backend',
    [string]$DataDir = 'D:\Program Files\Ordo\data',
    [string]$DatabaseUrl = '',
    [string]$BindAddress = '',
    [int]$Port = 0,
    [switch]$BuildFrontend,
    [switch]$SkipSandboxImage,
    [switch]$Uninstall,
    [string]$LogFile = ''
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($NoElevation) {
        throw "Administrator privileges are required to configure Windows Service."
    }
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath), '-NoElevation')
    foreach ($k in $PSBoundParameters.Keys) {
        if ($k -eq 'NoElevation') { continue }
        $v = $PSBoundParameters[$k]
        if ($v -is [switch]) { $argList += "-$k" } else { $argList += "-$k"; $argList += ('"{0}"' -f $v) }
    }
    if (-not $PSBoundParameters.ContainsKey('LogFile')) {
        $LogFile = Join-Path $env:TEMP ('ordo-install-{0:yyyyMMdd-HHmmss}.log' -f (Get-Date))
        $argList += '-LogFile'; $argList += ('"{0}"' -f $LogFile)
        Write-Output "Elevation required; install output will be logged to $LogFile"
    }
    $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList $argList
    exit $process.ExitCode
}

if ($LogFile) { Start-Transcript -Path $LogFile -Force | Out-Null }

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$envPath = Join-Path $repoRoot '.env'

# ---------- 卸载 ----------
if ($Uninstall) {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Output "Service $ServiceName not found."
        exit 0
    }
    if ($service.Status -ne 'Stopped') {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    & sc.exe delete $ServiceName | Out-Null
    Write-Output "Service $ServiceName removed (install dir and data kept at $InstallDir / $DataDir)."
    exit 0
}

# ---------- 读取 .env ----------
$envVars = @{}
if (Test-Path -LiteralPath $envPath) {
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $envVars[$Matches[1]] = $Matches[2].Trim()
        }
    }
}

if (-not $DatabaseUrl) {
    $DatabaseUrl = if ($envVars['DATABASE_URL']) {
        # 容器内地址转换为宿主机可达地址（shared-postgres 映射到 127.0.0.1:55432）
        $envVars['DATABASE_URL'] -replace '@(shared-postgres|postgres|db)(:\d+)?/', '@127.0.0.1:55432/'
    } else {
        'postgresql+asyncpg://ordo:ordo@127.0.0.1:55432/ordo'
    }
}
if (-not $BindAddress) { $BindAddress = if ($envVars['ORDO_BIND_ADDRESS']) { $envVars['ORDO_BIND_ADDRESS'] } else { '127.0.0.1' } }
if (-not $Port) { $Port = if ($envVars['ORDO_PORT']) { [int]$envVars['ORDO_PORT'] } else { 8000 } }

# ---------- 前端构建 ----------
if ($BuildFrontend) {
    Write-Output "Building frontend..."
    Push-Location (Join-Path $repoRoot 'frontend')
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    }
    finally { Pop-Location }
}

# ---------- 发布后端 ----------
Write-Output "Publishing backend (win-x64, self-contained)..."
$publishDir = Join-Path $repoRoot 'backend-csharp\bin\publish-win'
& dotnet publish (Join-Path $repoRoot 'backend-csharp\backend-csharp.csproj') `
    -c Release -r win-x64 --self-contained true -o $publishDir --nologo -v q
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }

$exePath = Join-Path $InstallDir 'Ordo.exe'
if (-not (Test-Path (Join-Path $publishDir 'Ordo.exe'))) {
    throw "Published executable not found in $publishDir"
}

# ---------- 沙箱运行时镜像 ----------
if (-not $SkipSandboxImage) {
    & docker image inspect ordo-sandbox 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Output "Building ordo-sandbox runtime image..."
        & docker build -t ordo-sandbox (Join-Path $repoRoot 'sandbox')
        if ($LASTEXITCODE -ne 0) { throw "docker build ordo-sandbox failed" }
    }
}

# ---------- 部署文件 ----------
$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne 'Stopped') {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataDir 'files') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataDir 'sandbox-artifacts') | Out-Null

Copy-Item -Path (Join-Path $publishDir '*') -Destination $InstallDir -Recurse -Force
# 清理旧版输出名（backend-csharp.* → Ordo.* 改名后残留）
Remove-Item -Path (Join-Path $InstallDir 'backend-csharp.*') -Force -ErrorAction SilentlyContinue

# ---------- 注册服务 ----------
$binPathArg = '"{0}"' -f $exePath
if ($service) {
    & sc.exe config $ServiceName binPath= $binPathArg start= auto DisplayName= "Ordo Backend" | Out-Null
}
else {
    & sc.exe create $ServiceName binPath= $binPathArg start= auto DisplayName= "Ordo Backend" | Out-Null
}

# 若存在 cn1-sg2 AWG 隧道，则让服务依赖它，保证 10.66.70.2 先于服务绑定
if (Get-Service -Name 'AmneziaWGTunnel$cn1-sg2' -ErrorAction SilentlyContinue) {
    & sc.exe config $ServiceName depend= 'AmneziaWGTunnel$cn1-sg2' | Out-Null
}

# ---------- 服务环境变量 ----------
$serviceEnv = @(
    "APP_ENV=production",
    "APP_SECRET_KEY=$($envVars['APP_SECRET_KEY'])",
    "CREDENTIAL_ENCRYPTION_KEY=$($envVars['CREDENTIAL_ENCRYPTION_KEY'])",
    "DATABASE_URL=$DatabaseUrl",
    "STORAGE_PATH=$(Join-Path $DataDir 'files')",
    "SANDBOX_ARTIFACT_PATH=$(Join-Path $DataDir 'sandbox-artifacts')",
    "CORS_ORIGINS=$($envVars['CORS_ORIGINS'])",
    "ORDO_BIND_ADDRESS=$BindAddress",
    "ORDO_PORT=$Port",
    "DOCKER_HOST=npipe://./pipe/docker_engine"
)
$regBase = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName"
Write-Output "Service env: DATABASE_URL length=$($DatabaseUrl.Length), BIND=$BindAddress, PORT=$Port"
Set-ItemProperty -Path $regBase -Name 'Environment' -Value $serviceEnv -Type MultiString

& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
& sc.exe description $ServiceName "Ordo AI workflow platform: API, worker, scheduler, web UI, host ops and Docker sandbox in one Windows service." | Out-Null

Start-Service -Name $ServiceName
Start-Sleep -Seconds 3

$health = $null
$addrList = @($BindAddress.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }) + '127.0.0.1'
foreach ($addr in ($addrList | Select-Object -Unique)) {
    try {
        $health = Invoke-RestMethod -Uri "http://$addr`:$Port/health" -TimeoutSec 10
        if ($health) { break }
    }
    catch { }
}
if (-not $health) { throw "Health check failed on all bind addresses: $($addrList -join ', ')" }

[PSCustomObject]@{
    Service    = $ServiceName
    BinaryPath = $exePath
    DataDir    = $DataDir
    Listen     = ($addrList | Select-Object -Unique | ForEach-Object { "http://$_`:$Port" }) -join ' '
    Status     = (Get-Service -Name $ServiceName).Status
    Health     = $health.status
}
