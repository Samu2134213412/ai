# Entfernt "Meine Website" wieder: Server stoppen, Verknuepfungen loeschen
# und auf Wunsch den ganzen Ordner (inklusive Website-Dateien) entfernen.
$ErrorActionPreference = 'Stop'
$delete = $false
$AppDir  = $PSScriptRoot
$BaseDir = Split-Path $AppDir -Parent
$config  = Get-Content (Join-Path $AppDir 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json

Write-Host ''
Write-Host "  $($config.name) deinstallieren" -ForegroundColor Cyan
Write-Host ''

$serverPs1 = Join-Path $AppDir 'server.ps1'
try {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($serverPs1) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}
Write-Host '  [ok] Website gestoppt' -ForegroundColor Green

foreach ($s in @($config.shortcuts)) {
    if ($s -and (Test-Path -LiteralPath $s)) { Remove-Item -LiteralPath $s -Force }
}
Write-Host '  [ok] Verknuepfungen entfernt' -ForegroundColor Green

Write-Host ''
Write-Host "  Sollen auch ALLE Dateien geloescht werden (deine Website, Sicherungen)?"
Write-Host "  Ordner: $BaseDir"
$answer = Read-Host '  Tippe JA zum Loeschen, oder Enter um die Dateien zu behalten'
if ($answer -eq 'ja') {
    $delete = $true
    Write-Host '  [ok] Ordner wird geloescht, sobald dieses Fenster zu ist' -ForegroundColor Green
} else {
    Write-Host "  Deine Dateien bleiben in: $BaseDir" -ForegroundColor Yellow
}
Write-Host ''
Write-Host '  Fertig.'
Read-Host '  Enter zum Schliessen' | Out-Null
if ($delete) {
    # Die Deinstallieren.bat laeuft noch, deshalb erst kurz danach loeschen.
    Start-Process cmd.exe -WindowStyle Hidden -WorkingDirectory $env:USERPROFILE `
        -ArgumentList "/c ping -n 3 127.0.0.1 >nul & rmdir /s /q `"$BaseDir`""
}
