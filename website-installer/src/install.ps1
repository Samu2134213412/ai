# Installer fuer "Meine Website".
# Wird von Website-Installer.bat gestartet. Legt einen Ordner mit deiner
# Website an, richtet Verknuepfungen ein und startet alles.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Die Dateien werden beim Bauen (build.py) hier eingesetzt.
$Payload = @{
    'app\server.ps1'    = '__B64_server.ps1__'
    'app\admin.html'    = '__B64_admin.html__'
    'app\uninstall.ps1' = '__B64_uninstall.ps1__'
    'start.html'        = '__B64_start.html__'
}

function Get-PayloadBytes([string]$key) { return ,[Convert]::FromBase64String($Payload[$key]) }
function Get-PayloadText([string]$key) { return [Text.Encoding]::UTF8.GetString((Get-PayloadBytes $key)).TrimStart([char]0xFEFF) }
function Write-Utf8([string]$path, [string]$text, [bool]$bom = $false) {
    [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $bom))
}
function Step([string]$text) { Write-Host "  [ok] $text" -ForegroundColor Green }

try { $Host.UI.RawUI.WindowTitle = 'Website-Installer' } catch {}
Write-Host ''
Write-Host '  ==========================================' -ForegroundColor Cyan
Write-Host '     Website-Installer' -ForegroundColor Cyan
Write-Host '  ==========================================' -ForegroundColor Cyan
Write-Host ''
Write-Host '  Richtet auf diesem PC eine eigene Website ein, in die du'
Write-Host '  dein Design (z. B. aus Claude Design) hochladen und dann'
Write-Host '  selbst bearbeiten kannst.'
Write-Host ''

# --------------------------------------------------------------- Name
$name = Read-Host '  Wie soll deine Website heissen? (Enter = "Meine Website")'
$name = "$name".Trim()
foreach ($c in [IO.Path]::GetInvalidFileNameChars()) { $name = $name.Replace([string]$c, '') }
$name = $name.Trim(' ', '.')
if ($name -eq '') { $name = 'Meine Website' }

$BaseDir   = Join-Path $env:USERPROFILE $name
$AppDir    = Join-Path $BaseDir 'app'
$SiteDir   = Join-Path $BaseDir 'website'
$ServerPs1 = Join-Path $AppDir 'server.ps1'
$isUpdate  = Test-Path (Join-Path $AppDir 'server.ps1')

Write-Host ''
if ($isUpdate) {
    Write-Host "  Die Website gibt es schon in: $BaseDir"
    Write-Host '  Das Programm wird aktualisiert. Deine Website-Dateien bleiben unveraendert.'
} else {
    Write-Host "  Deine Website kommt nach: $BaseDir"
}
Write-Host ''

# Laufenden Server dieser Website beenden (bei einer Aktualisierung).
try {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($ServerPs1) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}

# -------------------------------------------------------------- Dateien
foreach ($d in @($BaseDir, $AppDir, $SiteDir, (Join-Path $BaseDir 'backups'))) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}
# PowerShell-Skripte mit BOM speichern, damit Umlaute unter Windows PowerShell stimmen.
Write-Utf8 $ServerPs1 (Get-PayloadText 'app\server.ps1') $true
Write-Utf8 (Join-Path $AppDir 'uninstall.ps1') (Get-PayloadText 'app\uninstall.ps1') $true
[IO.File]::WriteAllBytes((Join-Path $AppDir 'admin.html'), (Get-PayloadBytes 'app\admin.html'))
Step 'Programmdateien'

if (@(Get-ChildItem -LiteralPath $SiteDir -Force).Count -eq 0) {
    $start = (Get-PayloadText 'start.html').Replace('__SITE_NAME__', [Net.WebUtility]::HtmlEncode($name))
    Write-Utf8 (Join-Path $SiteDir 'index.html') $start
    Step 'Startseite (Platzhalter)'
}

# Doppelklick-Starter im Ordner.
$runServer = 'start "" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\server.ps1"'
[IO.File]::WriteAllText((Join-Path $BaseDir 'Website starten.bat'), "@echo off`r`n$runServer`r`n", [Text.Encoding]::ASCII)
[IO.File]::WriteAllText((Join-Path $BaseDir 'Website bearbeiten.bat'), "@echo off`r`n$runServer -Admin`r`n", [Text.Encoding]::ASCII)
[IO.File]::WriteAllText((Join-Path $BaseDir 'Deinstallieren.bat'),
    "@echo off`r`nset `"APP=%~dp0app`"`r`ncd /d `"%USERPROFILE%`"`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%APP%\uninstall.ps1`"`r`n", [Text.Encoding]::ASCII)

$readme = @"
$name
$('=' * $name.Length)

So benutzt du deine Website:

  * "$name" auf dem Desktop            -> Website ansehen
  * "$name bearbeiten" auf dem Desktop -> Design hochladen und Dateien bearbeiten

Solange die Website laeuft, siehst du unten in der Taskleiste ein
PowerShell-Fenster. Schliesst du es, ist die Website aus. Ein Klick auf
eine der Verknuepfungen startet sie wieder.

Ordner:
  website\   Die Dateien deiner Website. Du kannst sie auch direkt mit
             jedem Editor (z. B. VS Code oder Notepad) bearbeiten.
  backups\   Automatische Sicherungen, bevor ein neues Design die alte
             Version ersetzt.
  app\       Das Programm selbst (nicht aendern).

Entfernen: "Deinstallieren.bat" doppelklicken.
"@
Write-Utf8 (Join-Path $BaseDir 'LIESMICH.txt') $readme $true
Step 'Starter und Anleitung'

# --------------------------------------------------------- Verknuepfungen
$shortcuts = @()
try {
    $shell = New-Object -ComObject WScript.Shell
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $icon  = Join-Path $env:SystemRoot 'System32\shell32.dll'
    $places = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
    foreach ($dir in $places) {
        if (-not $dir -or -not (Test-Path $dir)) { continue }
        foreach ($s in @(
            @{ file = "$name.lnk";            args = '';        desc = "$name ansehen";    icon = "$icon,13" },
            @{ file = "$name bearbeiten.lnk"; args = ' -Admin'; desc = "$name bearbeiten"; icon = (Join-Path $env:SystemRoot 'System32\notepad.exe') + ',0' }
        )) {
            $path = Join-Path $dir $s.file
            $lnk = $shell.CreateShortcut($path)
            $lnk.TargetPath = $psExe
            $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ServerPs1`"" + $s.args
            $lnk.WorkingDirectory = $BaseDir
            $lnk.WindowStyle = 7   # minimiert
            $lnk.IconLocation = $s.icon
            $lnk.Description = $s.desc
            $lnk.Save()
            $shortcuts += $path
        }
    }
    Step 'Verknuepfungen auf dem Desktop und im Startmenue'
} catch {
    Write-Host "  [!] Verknuepfungen konnten nicht angelegt werden: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "      Starte die Website einfach mit 'Website starten.bat' im Ordner."
}

$config = @{ name = $name; installed = (Get-Date -Format 's'); shortcuts = $shortcuts }
Write-Utf8 (Join-Path $AppDir 'config.json') (ConvertTo-Json -InputObject $config -Depth 3)

# ------------------------------------------------------------------ Start
Start-Process -FilePath 'powershell.exe' -WindowStyle Minimized `
    -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$ServerPs1`"", '-Admin')
Step 'Website gestartet'

Write-Host ''
Write-Host '  Fertig!' -ForegroundColor Green
Write-Host ''
Write-Host '  Gleich oeffnet sich dein Browser mit der Bearbeiten-Seite.'
Write-Host '  Dort ziehst du einfach deinen Claude-Design-Export hinein.'
Write-Host ''
Write-Host "  Spaeter: Auf dem Desktop '$name' oder '$name bearbeiten' doppelklicken."
Write-Host "  Deine Dateien liegen in: $SiteDir"
Write-Host ''
