# Haelt im Online-Modus alles am Laufen: den Webserver und den Cloudflare
# Tunnel, der deine Domain mit diesem PC verbindet. Wird von der Windows-
# Aufgabenplanung beim Hochfahren gestartet (auch ohne Anmeldung) und
# startet beide neu, falls einer abstuerzt.
$ErrorActionPreference = 'Continue'

$AppDir    = $PSScriptRoot
$BaseDir   = Split-Path $AppDir -Parent
$LogDir    = Join-Path $BaseDir 'logs'
$ServerPs1 = Join-Path $AppDir 'server.ps1'
$CfExe     = Join-Path $AppDir 'cloudflared\cloudflared.exe'
$CfConfig  = Join-Path $AppDir 'cloudflared\config.yml'
$PsExe     = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-Log([string]$text) {
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $text
    Add-Content -LiteralPath (Join-Path $LogDir 'host.log') -Value $line -Encoding UTF8
}

# Reste eines frueheren Laufs beenden (z. B. nach einem Absturz).
Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -and (
        ($_.Name -eq 'powershell.exe' -and $_.CommandLine.Contains($ServerPs1)) -or
        ($_.Name -eq 'cloudflared.exe' -and $_.CommandLine.Contains($CfConfig)))
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# Die Logdateien klein halten.
Get-ChildItem -LiteralPath $LogDir -File | Where-Object { $_.Length -gt 5MB } | Remove-Item -Force -ErrorAction SilentlyContinue

function Start-Server {
    Write-Log 'Starte Webserver'
    Start-Process -FilePath $PsExe -PassThru `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$ServerPs1`"", '-Service') `
        -RedirectStandardOutput (Join-Path $LogDir 'server.log') `
        -RedirectStandardError (Join-Path $LogDir 'server-fehler.log')
}

function Start-Tunnel {
    Write-Log 'Starte Cloudflare Tunnel'
    Start-Process -FilePath $CfExe -PassThru `
        -ArgumentList @('tunnel', '--no-autoupdate', '--config', "`"$CfConfig`"", 'run') `
        -RedirectStandardOutput (Join-Path $LogDir 'tunnel-ausgabe.log') `
        -RedirectStandardError (Join-Path $LogDir 'tunnel.log')
}

Write-Log 'Gestartet'
$server = $null
$tunnel = $null
while ($true) {
    try {
        if (-not $server -or $server.HasExited) { $server = Start-Server }
        if ((Test-Path $CfConfig) -and (-not $tunnel -or $tunnel.HasExited)) { $tunnel = Start-Tunnel }
    } catch {
        Write-Log "Fehler: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 10
}
