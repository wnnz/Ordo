param([switch]$NoElevation)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($NoElevation) {
        throw "Administrator privileges are required to configure Windows Service."
    }
    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath), '-NoElevation')
    $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList $arguments
    exit $process.ExitCode
}

$sourceExe = Join-Path $PSScriptRoot 'bin\publish\OrdoWindowsAgent.exe'
if (-not (Test-Path -LiteralPath $sourceExe)) {
    throw "Published executable not found at: $sourceExe"
}

$installDir = Join-Path $env:ProgramData 'Ordo\WindowsAgent'
$targetExe = Join-Path $installDir 'OrdoWindowsAgent.exe'
$configPath = Join-Path $env:ProgramData 'Ordo\windows-agent.json'
$envPath = 'D:\Dev\Ordo\.env'

$token = $null
if (Test-Path -LiteralPath $envPath) {
    $match = Select-String -LiteralPath $envPath -Pattern '^(HOST_INFO_AGENT_TOKEN|SANDBOX_SHARED_SECRET)=(.+)$' | Select-Object -First 1
    if ($match -and $match.Matches[0].Groups[2].Value) {
        $token = $match.Matches[0].Groups[2].Value.Trim()
    }
}

$service = Get-Service -Name 'OrdoWindowsAgent' -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne 'Stopped') {
    Stop-Service -Name 'OrdoWindowsAgent' -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

if (Test-Path -LiteralPath $installDir) {
    & takeown.exe '/f' $installDir '/a' '/r' '/d' 'y' | Out-Null
    & icacls.exe $installDir '/reset' '/t' '/c' | Out-Null
}
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

Copy-Item -LiteralPath $sourceExe -Destination $targetExe -Force
foreach ($legacy in @('ordo_host_info_agent.py', 'pythonservice.exe', 'python312.dll', 'python3.dll', 'pywintypes312.dll', 'pythoncom312.dll')) {
    $p = Join-Path $installDir $legacy
    if (Test-Path -LiteralPath $p) {
        Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
    }
}

& icacls.exe $installDir '/grant:r' '*S-1-5-18:(OI)(CI)(F)' '*S-1-5-32-544:(OI)(CI)(F)' '*S-1-5-32-545:(OI)(CI)(RX)' '/t' '/c' | Out-Null

if ($token) {
    if (Test-Path -LiteralPath $configPath) {
        & takeown.exe '/f' $configPath '/a' | Out-Null
        & icacls.exe $configPath '/reset' '/c' | Out-Null
    }
    @{ host = '127.0.0.1'; port = 8765; token = $token } | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
    & icacls.exe $configPath '/grant:r' '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' '*S-1-5-32-545:(R)' | Out-Null
}

$regBase = 'HKLM:\SYSTEM\CurrentControlSet\Services\OrdoWindowsAgent'
if (Test-Path -LiteralPath $regBase) {
    foreach ($subKey in @('PythonClass', 'Parameters')) {
        $sub = Join-Path $regBase $subKey
        if (Test-Path -LiteralPath $sub) {
            Remove-Item -LiteralPath $sub -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

$binPathArg = '"{0}"' -f $targetExe
if ($service) {
    & sc.exe config OrdoWindowsAgent binPath= $binPathArg start= auto DisplayName= "Ordo Windows Agent" | Out-Null
} else {
    & sc.exe create OrdoWindowsAgent binPath= $binPathArg start= auto DisplayName= "Ordo Windows Agent" | Out-Null
}

& sc.exe failure OrdoWindowsAgent reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
& sc.exe description OrdoWindowsAgent "Provides token-protected Windows host operations to local Ordo workflows (C# Native)." | Out-Null

Start-Service -Name 'OrdoWindowsAgent'
Start-Sleep -Seconds 2

$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 5
$status = (Get-Service -Name 'OrdoWindowsAgent').Status

[PSCustomObject]@{
    Service = 'OrdoWindowsAgent'
    BinaryPath = $targetExe
    Status = $status
    Health = $health.status
}
