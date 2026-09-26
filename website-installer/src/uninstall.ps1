# Entfernt "Meine Website" wieder: Server und Tunnel stoppen, Autostart und
# Verknuepfungen loeschen und auf Wunsch den ganzen Ordner (inklusive
# Website-Dateien) entfernen.
param([switch]$Elevated)
$ErrorActionPreference = 'Stop'
$delete = $false
$AppDir  = $PSScriptRoot
$BaseDir = Split-Path $AppDir -Parent
$config  = Get-Content (Join-Path $AppDir 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json

# Online-Modus: Autostart-Aufgabe laeuft als SYSTEM, dafuer braucht es Admin-Rechte.
$isAdmin = (New-Object Security.Principal.WindowsPrincipal ([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if ($config.task -and -not $isAdmin) {
    Write-Host '  Zum Entfernen braucht Windows einmal deine Erlaubnis - bitte auf "Ja" klicken.'
    try {
        Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Elevated')
    } catch { Write-Host '  Abgebrochen.'; Read-Host '  Enter zum Schliessen' | Out-Null }
    exit
}

Write-Host ''
Write-Host "  $($config.name) deinstallieren" -ForegroundColor Cyan
Write-Host ''

if ($config.task) {
    try { Stop-ScheduledTask -TaskName $config.task -ErrorAction SilentlyContinue } catch {}
    try { Unregister-ScheduledTask -TaskName $config.task -Confirm:$false -ErrorAction SilentlyContinue } catch {}
    Write-Host '  [ok] Autostart entfernt' -ForegroundColor Green
}
try {
    Get-CimInstance Win32_Process |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains($AppDir) -and -not $_.CommandLine.Contains('uninstall.ps1') } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}
Write-Host '  [ok] Website gestoppt' -ForegroundColor Green

# Den Tunnel bei Cloudflare loeschen.
$cfExe  = Join-Path $AppDir 'cloudflared\cloudflared.exe'
$cfCert = Join-Path $AppDir 'cloudflared\cert.pem'
if ($config.tunnelId -and (Test-Path $cfExe) -and (Test-Path $cfCert)) {
    $env:TUNNEL_ORIGIN_CERT = $cfCert
    $ErrorActionPreference = 'Continue'
    & $cfExe tunnel cleanup $config.tunnelId 2>&1 | Out-Null
    & $cfExe tunnel delete -f $config.tunnelId 2>&1 | Out-Null
    $ok = $LASTEXITCODE -eq 0
    $ErrorActionPreference = 'Stop'
    if ($ok) {
        Write-Host '  [ok] Tunnel bei Cloudflare gelöscht' -ForegroundColor Green
        Write-Host "       (Die DNS-Einträge für $($config.domain) kannst du im Cloudflare-Dashboard entfernen.)"
    } else {
        Write-Host '  [!] Der Tunnel bei Cloudflare konnte nicht gelöscht werden - ggf. im Dashboard entfernen.' -ForegroundColor Yellow
    }
}

foreach ($s in @($config.shortcuts)) {
    if ($s -and (Test-Path -LiteralPath $s)) { Remove-Item -LiteralPath $s -Force }
}
Write-Host '  [ok] Verknüpfungen entfernt' -ForegroundColor Green

Write-Host ''
Write-Host "  Sollen auch ALLE Dateien gelöscht werden (deine Website, Sicherungen)?"
Write-Host "  Ordner: $BaseDir"
$answer = Read-Host '  Tippe JA zum Löschen, oder Enter um die Dateien zu behalten'
if ($answer -eq 'ja') {
    $delete = $true
    Write-Host '  [ok] Ordner wird gelöscht, sobald dieses Fenster zu ist' -ForegroundColor Green
} else {
    Write-Host "  Deine Dateien bleiben in: $BaseDir" -ForegroundColor Yellow
}
Write-Host ''
Write-Host '  Fertig.'
Read-Host '  Enter zum Schließen' | Out-Null
if ($delete) {
    # Die Deinstallieren.bat laeuft noch, deshalb erst kurz danach loeschen.
    Start-Process cmd.exe -WindowStyle Hidden -WorkingDirectory $env:USERPROFILE `
        -ArgumentList "/c ping -n 3 127.0.0.1 >nul & rmdir /s /q `"$BaseDir`""
}
