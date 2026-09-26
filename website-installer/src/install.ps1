# Installer fuer "Meine Website".
# Wird von Website-Installer.bat gestartet. Legt einen Ordner mit deiner
# Website an, richtet Verknuepfungen ein und startet alles.
#
# Zwei Modi:
#   lokal  - die Website laeuft nur auf diesem PC (zum Ausprobieren)
#   online - dieser PC ist der Server fuer deine eigene Domain. Ein
#            Cloudflare Tunnel verbindet die Domain mit dem PC (HTTPS inklusive,
#            keine Router-Einstellungen). Alles startet automatisch mit Windows,
#            die Bearbeiten-Seite ist mit einem Passwort geschuetzt.
param(
    [string]$Name,
    [ValidateSet('', 'lokal', 'online')][string]$Mode = '',
    [string]$BaseDir,
    [switch]$Elevated   # neu gestartet mit Administrator-Rechten
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Die Dateien werden beim Bauen (build.py) hier eingesetzt.
$Payload = @{
    'app\server.ps1'    = '__B64_server.ps1__'
    'app\host.ps1'      = '__B64_host.ps1__'
    'app\uninstall.ps1' = '__B64_uninstall.ps1__'
    'app\admin.html'    = '__B64_admin.html__'
    'app\login.html'    = '__B64_login.html__'
    'start.html'        = '__B64_start.html__'
}

function Get-PayloadBytes([string]$key) { return ,[Convert]::FromBase64String($Payload[$key]) }
function Get-PayloadText([string]$key) { return [Text.Encoding]::UTF8.GetString((Get-PayloadBytes $key)).TrimStart([char]0xFEFF) }
function Write-Utf8([string]$path, [string]$text, [bool]$bom = $false) {
    [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $bom))
}
function Step([string]$text) { Write-Host "  [ok] $text" -ForegroundColor Green }
function Warn([string]$text) { Write-Host "  [!] $text" -ForegroundColor Yellow }
function Finish([int]$code = 0) {
    # Im Admin-Fenster gibt es kein "pause" aus der .bat-Datei.
    if ($Elevated) { Write-Host ''; Read-Host '  Enter zum Schließen' | Out-Null }
    exit $code
}
trap {
    Write-Host ''
    Write-Host "  FEHLER: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '  Die Installation wurde abgebrochen. Du kannst den Installer einfach nochmal starten.'
    Finish 1
}
function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

try { $Host.UI.RawUI.WindowTitle = 'Website-Installer' } catch {}
Write-Host ''
Write-Host '  ==========================================' -ForegroundColor Cyan
Write-Host '     Website-Installer' -ForegroundColor Cyan
Write-Host '  ==========================================' -ForegroundColor Cyan
Write-Host ''
if (-not $Elevated) {
    Write-Host '  Richtet auf diesem PC eine eigene Website ein, in die du'
    Write-Host '  dein Design (z. B. aus Claude Design) hochladen und dann'
    Write-Host '  selbst bearbeiten kannst.'
    Write-Host ''
}

# ------------------------------------------------------------------- Name
if (-not $Name) {
    $Name = Read-Host '  Wie soll deine Website heißen? (Enter = "Meine Website")'
    $Name = "$Name".Trim()
    foreach ($c in [IO.Path]::GetInvalidFileNameChars()) { $Name = $Name.Replace([string]$c, '') }
    $Name = $Name.Trim(' ', '.')
    if ($Name -eq '') { $Name = 'Meine Website' }
}
if (-not $BaseDir) { $BaseDir = Join-Path $env:USERPROFILE $Name }
$AppDir    = Join-Path $BaseDir 'app'
$SiteDir   = Join-Path $BaseDir 'website'
$CfDir     = Join-Path $AppDir 'cloudflared'
$ServerPs1 = Join-Path $AppDir 'server.ps1'
$HostPs1   = Join-Path $AppDir 'host.ps1'
$PsExe     = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

$Old = $null
$oldConfigFile = Join-Path $AppDir 'config.json'
if (Test-Path $oldConfigFile) {
    try { $Old = Get-Content $oldConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
}

# -------------------------------------------------------------------- Modus
if (-not $Mode) {
    Write-Host ''
    Write-Host '  Wie soll deine Website laufen?'
    Write-Host ''
    Write-Host '    [1] Nur auf diesem PC        (zum Ausprobieren, sonst sieht sie niemand)'
    Write-Host '    [2] Im Internet unter deiner eigenen Domain'
    Write-Host '        (dieser PC ist der Server und sollte immer laufen)'
    Write-Host ''
    $default = '1'
    if ($Old -and $Old.domain) { $default = '2' }
    $answer = Read-Host "  Deine Wahl (Enter = $default)"
    if (-not "$answer".Trim()) { $answer = $default }
    if ("$answer".Trim() -eq '2') { $Mode = 'online' } else { $Mode = 'lokal' }
}
$Online = $Mode -eq 'online'

# Fuer den Online-Modus (und zum Abschalten eines frueheren Online-Modus)
# braucht es einmal Administrator-Rechte: Autostart-Aufgabe, Energiesparplan.
$needAdmin = $Online -or ($Old -and $Old.task)
if ($needAdmin -and -not (Test-Admin)) {
    Write-Host ''
    Write-Host '  Dafür braucht Windows einmal deine Erlaubnis (Administrator).'
    Write-Host '  Bitte im nächsten Fenster auf "Ja" klicken. Die Installation'
    Write-Host '  geht dann in einem neuen Fenster weiter.'
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                 '-Name', "`"$Name`"", '-Mode', $Mode, '-BaseDir', "`"$BaseDir`"", '-Elevated')
    try {
        Start-Process -FilePath $PsExe -Verb RunAs -ArgumentList $argList -Wait
    } catch {
        Warn 'Ohne Administrator-Rechte geht der Online-Modus leider nicht.'
        Write-Host '      Starte den Installer nochmal und klicke auf "Ja" - oder wähle [1].'
        exit 1
    }
    exit 0
}

Write-Host ''
if ($Old) {
    Write-Host "  Die Website gibt es schon in: $BaseDir"
    Write-Host '  Das Programm wird aktualisiert. Deine Website-Dateien bleiben unverändert.'
} else {
    Write-Host "  Deine Website kommt nach: $BaseDir"
}
Write-Host ''

# ------------------------------------------------ Laufende Version stoppen
if ($Old -and $Old.task) {
    try { Stop-ScheduledTask -TaskName $Old.task -ErrorAction SilentlyContinue } catch {}
}
try {
    Get-CimInstance Win32_Process |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains($AppDir) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}
Start-Sleep -Seconds 2   # bis die Dateien wieder freigegeben sind

# ------------------------------------------------------------------ Dateien
foreach ($d in @($BaseDir, $AppDir, $SiteDir, (Join-Path $BaseDir 'backups'))) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}
# PowerShell-Skripte mit BOM speichern, damit Umlaute unter Windows PowerShell stimmen.
foreach ($f in @('server.ps1', 'host.ps1', 'uninstall.ps1')) {
    Write-Utf8 (Join-Path $AppDir $f) (Get-PayloadText "app\$f") $true
}
foreach ($f in @('admin.html', 'login.html')) {
    [IO.File]::WriteAllBytes((Join-Path $AppDir $f), (Get-PayloadBytes "app\$f"))
}
Step 'Programmdateien'

if (@(Get-ChildItem -LiteralPath $SiteDir -Force).Count -eq 0) {
    $start = (Get-PayloadText 'start.html').Replace('__SITE_NAME__', [Net.WebUtility]::HtmlEncode($Name))
    Write-Utf8 (Join-Path $SiteDir 'index.html') $start
    Step 'Startseite (Platzhalter)'
}

$config = [ordered]@{ name = $Name; mode = $Mode; installed = (Get-Date -Format 's') }

# =================================================================== ONLINE
function Read-Password {
    while ($true) {
        $a = Read-Host '  Passwort (mind. 10 Zeichen)' -AsSecureString
        $b = Read-Host '  Passwort wiederholen       ' -AsSecureString
        $pa = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($a))
        $pb = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($b))
        if ($pa.Length -lt 10) { Warn 'Zu kurz - bitte mindestens 10 Zeichen.'; continue }
        if ($pa -cne $pb) { Warn 'Die beiden Eingaben sind nicht gleich.'; continue }
        return $pa
    }
}

function New-PasswordHash([string]$password) {
    $rounds = 150000
    $salt = New-Object byte[] 16
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($salt)
    $kdf = New-Object Security.Cryptography.Rfc2898DeriveBytes($password, $salt, $rounds, [Security.Cryptography.HashAlgorithmName]::SHA256)
    return 'pbkdf2-sha256$' + $rounds + '$' + [Convert]::ToBase64String($salt) + '$' + [Convert]::ToBase64String($kdf.GetBytes(32))
}

function Read-Domain {
    while ($true) {
        $d = "$(Read-Host '  Deine Domain (z. B. meine-seite.de)')".Trim().ToLowerInvariant()
        $d = ($d -replace '^[a-z]+://', '').Split('/')[0].TrimEnd('.')
        if ($d.StartsWith('www.')) { $d = $d.Substring(4) }
        try { $d = (New-Object Globalization.IdnMapping).GetAscii($d) } catch {}   # Umlaut-Domains
        if ($d -match '^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z0-9-]{2,}$') { return $d }
        Warn 'Das sieht nicht wie eine Domain aus. Beispiel: meine-seite.de'
    }
}

# Fuehrt cloudflared aus und sammelt die Ausgabe (cloudflared schreibt auf stderr).
function Invoke-Cf([string[]]$cfArgs) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $CfExe @cfArgs 2>&1 | ForEach-Object { "$_" }
        return @{ code = $LASTEXITCODE; out = ($out -join "`n") }
    } finally { $ErrorActionPreference = $prev }
}

function Get-FreePort([int]$from) {
    $used = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | ForEach-Object { $_.Port })
    $p = $from
    while ($used -contains $p) { $p++ }
    return $p
}

function New-UrlShortcut([string]$path, [string]$url, [string]$icon) {
    $text = "[InternetShortcut]`r`nURL=$url`r`nIconFile=$($icon.Split(',')[0])`r`nIconIndex=$($icon.Split(',')[1])`r`n"
    [IO.File]::WriteAllText($path, $text, [Text.Encoding]::ASCII)
}

if ($Online) {
    $CfExe   = Join-Path $CfDir 'cloudflared.exe'
    $CfCert  = Join-Path $CfDir 'cert.pem'
    $CfCred  = Join-Path $CfDir 'tunnel.json'
    $CfYml   = Join-Path $CfDir 'config.yml'
    if (-not (Test-Path $CfDir)) { New-Item -ItemType Directory -Path $CfDir | Out-Null }

    $keep = $false
    if ($Old -and $Old.domain -and $Old.tunnelId -and (Test-Path $CfCred) -and (Test-Path $CfExe)) {
        $a = Read-Host "  Bisherige Einstellungen für $($Old.domain) behalten? [J/n]"
        $keep = "$a".Trim().ToLowerInvariant() -ne 'n'
    }

    # ------------------------------------------------------------ Passwort
    Write-Host ''
    if ($keep -and $Old.password) {
        $a = Read-Host '  Neues Passwort für die Bearbeiten-Seite festlegen? [j/N]'
        if ("$a".Trim().ToLowerInvariant() -eq 'j') { $config.password = New-PasswordHash (Read-Password) }
        else { $config.password = $Old.password }
    } else {
        Write-Host '  Die Bearbeiten-Seite ist gleich im Internet erreichbar.'
        Write-Host '  Lege ein Passwort fest, damit nur du deine Website ändern kannst.'
        $config.password = New-PasswordHash (Read-Password)
    }
    Step 'Passwort gespeichert (nur als sicherer Hash)'

    if ($keep) {
        $Domain = $Old.domain
        $TunnelId = $Old.tunnelId
        $Port = [int]$Old.port
    } else {
        # -------------------------------------------------- Cloudflare-Check
        Write-Host ''
        Write-Host '  So kommt deine Domain zu diesem PC (einmalig, ca. 10 Minuten):' -ForegroundColor Cyan
        Write-Host ''
        Write-Host '   1. Kostenloses Konto anlegen: https://dash.cloudflare.com/sign-up'
        Write-Host '   2. Dort "Domain hinzufügen" -> deine Domain eingeben -> Tarif "Free".'
        Write-Host '   3. Cloudflare zeigt dir zwei Nameserver (z. B. anna.ns.cloudflare.com).'
        Write-Host '      Die trägst du bei dem Anbieter ein, bei dem du die Domain gekauft'
        Write-Host '      hast (IONOS, Strato, GoDaddy, ...) - meist unter "Nameserver" oder "DNS".'
        Write-Host '   4. Warten, bis Cloudflare meldet, dass die Domain aktiv ist'
        Write-Host '      (oft ein paar Minuten, manchmal bis zu 24 Stunden).'
        Write-Host ''
        while ($true) {
            $a = "$(Read-Host '  Ist deine Domain bei Cloudflare aktiv? [j = weiter / o = Cloudflare öffnen / n = später]')".Trim().ToLowerInvariant()
            if ($a -eq 'j') { break }
            if ($a -eq 'o') { Start-Process 'https://dash.cloudflare.com/'; continue }
            if ($a -eq 'n') {
                Write-Host ''
                Write-Host '  Kein Problem. Starte den Installer einfach nochmal, wenn die Domain aktiv ist.'
                Write-Host '  Deine bisherigen Dateien bleiben erhalten.'
                Finish 0
            }
        }
        Write-Host ''
        $Domain = Read-Domain
        $hostnames = @($Domain)
        if ($Domain.Split('.').Count -eq 2) { $hostnames += "www.$Domain" }

        # --------------------------------------------------- cloudflared laden
        Write-Host ''
        Write-Host '  Lade den Cloudflare-Tunnel herunter ...'
        $arch = 'amd64'
        if ($env:PROCESSOR_ARCHITECTURE -eq 'x86' -and -not $env:PROCESSOR_ARCHITEW6432) { $arch = '386' }
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $tmpExe = "$CfExe.download"
        Invoke-WebRequest -UseBasicParsing -OutFile $tmpExe `
            -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-$arch.exe"
        Move-Item -LiteralPath $tmpExe -Destination $CfExe -Force
        Step 'Cloudflare-Tunnel heruntergeladen'

        # ------------------------------------------------------- Anmeldung
        Write-Host ''
        Write-Host '  Gleich öffnet sich dein Browser mit Cloudflare.' -ForegroundColor Cyan
        Write-Host "  Melde dich an, klicke auf deine Domain ($Domain) und dann auf ""Authorize""."
        Write-Host '  Danach hierher zurückkommen.'
        Write-Host ''
        Read-Host '  Enter drücken, um fortzufahren' | Out-Null
        # cloudflared legt das Login-Zertifikat immer unter ~\.cloudflared ab.
        # Ein vorhandenes Zertifikat kurz beiseitelegen und danach zurueckholen.
        $userCfDir = Join-Path $env:USERPROFILE '.cloudflared'
        $userCert = Join-Path $userCfDir 'cert.pem'
        $parked = $null
        if (Test-Path $userCert) {
            $parked = "$userCert.vorher-" + (Get-Date -Format 'yyyyMMddHHmmss')
            Move-Item -LiteralPath $userCert -Destination $parked
        }
        try {
            $p = Start-Process -FilePath $CfExe -ArgumentList @('tunnel', 'login') -NoNewWindow -Wait -PassThru
            if ($p.ExitCode -ne 0 -or -not (Test-Path $userCert)) { throw 'Die Anmeldung bei Cloudflare hat nicht geklappt.' }
            Move-Item -LiteralPath $userCert -Destination $CfCert -Force
        } finally {
            if ($parked) { Move-Item -LiteralPath $parked -Destination $userCert -Force }
        }
        Step 'Bei Cloudflare angemeldet'
        $env:TUNNEL_ORIGIN_CERT = $CfCert

        # ------------------------------------------------------ Tunnel anlegen
        $tunnelName = 'website-' + $Domain.Replace('.', '-')
        if (Test-Path $CfCred) { Remove-Item -LiteralPath $CfCred -Force }
        $r = Invoke-Cf @('tunnel', 'create', '--credentials-file', $CfCred, $tunnelName)
        if ($r.code -ne 0 -and $r.out -match 'already exists') {
            # Tunnel von einer frueheren Installation - ersetzen.
            Invoke-Cf @('tunnel', 'cleanup', $tunnelName) | Out-Null
            $d = Invoke-Cf @('tunnel', 'delete', '-f', $tunnelName)
            if ($d.code -ne 0) { throw "Alter Tunnel '$tunnelName' ließ sich nicht löschen:`n$($d.out)" }
            $r = Invoke-Cf @('tunnel', 'create', '--credentials-file', $CfCred, $tunnelName)
        }
        if ($r.code -ne 0 -or -not (Test-Path $CfCred)) { throw "Tunnel konnte nicht angelegt werden:`n$($r.out)" }
        $TunnelId = (Get-Content $CfCred -Raw | ConvertFrom-Json).TunnelID
        Step "Tunnel angelegt ($tunnelName)"

        foreach ($h in $hostnames) {
            $r = Invoke-Cf @('tunnel', 'route', 'dns', '--overwrite-dns', $TunnelId, $h)
            if ($r.code -ne 0) { throw "DNS-Eintrag für $h konnte nicht gesetzt werden:`n$($r.out)" }
            Step "$h zeigt jetzt auf diesen PC"
        }
        $Port = Get-FreePort 8080
    }
    if (-not $Port) { $Port = Get-FreePort 8080 }

    # ------------------------------------------------------ Tunnel-Konfiguration
    $hostnames = @($Domain)
    if ($Domain.Split('.').Count -eq 2) { $hostnames += "www.$Domain" }
    $yml = "tunnel: $TunnelId`r`ncredentials-file: '" + $CfCred.Replace("'", "''") + "'`r`ningress:`r`n"
    foreach ($h in $hostnames) {
        $yml += "  - hostname: $h`r`n    service: http://localhost:$Port`r`n    originRequest:`r`n      httpHostHeader: localhost:$Port`r`n"
    }
    $yml += "  - service: http_status:404`r`n"
    Write-Utf8 $CfYml $yml

    $config.domain = $Domain
    $config.tunnelId = $TunnelId
    $config.port = $Port

    # ---------------------------------------------------- Nicht einschlafen
    # Ein Server muss wach bleiben: im Netzbetrieb kein Standby/Ruhezustand.
    & powercfg.exe /change standby-timeout-ac 0 | Out-Null
    & powercfg.exe /change hibernate-timeout-ac 0 | Out-Null
    Step 'Energiesparen: PC geht am Stromnetz nicht mehr in den Standby'

    # ------------------------------------------------------------ Autostart
    $taskName = "Website - $Name"
    $action = New-ScheduledTaskAction -Execute $PsExe -WorkingDirectory $BaseDir `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$HostPs1`""
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal `
        -Settings $settings -Description "Startet die Website $Domain beim Hochfahren." -Force | Out-Null
    $config.task = $taskName
    Step 'Startet automatisch mit Windows (auch ohne Anmeldung)'
} elseif ($Old -and $Old.task) {
    # Wechsel von online zu lokal: Autostart abschalten.
    try { Unregister-ScheduledTask -TaskName $Old.task -Confirm:$false } catch {}
    Step 'Online-Modus abgeschaltet (Autostart entfernt)'
    Write-Host '      Der Tunnel bei Cloudflare bleibt bestehen; installiere erneut mit [2], um ihn wieder zu nutzen.'
}

# ---------------------------------------------------- Starter im Ordner
$runServer = 'start "" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\server.ps1"'
foreach ($f in @('Website starten.bat', 'Website bearbeiten.bat')) {
    $p = Join-Path $BaseDir $f
    if (Test-Path $p) { Remove-Item -LiteralPath $p -Force }
}
if (-not $Online) {
    [IO.File]::WriteAllText((Join-Path $BaseDir 'Website starten.bat'), "@echo off`r`n$runServer`r`n", [Text.Encoding]::ASCII)
    [IO.File]::WriteAllText((Join-Path $BaseDir 'Website bearbeiten.bat'), "@echo off`r`n$runServer -Admin`r`n", [Text.Encoding]::ASCII)
}
[IO.File]::WriteAllText((Join-Path $BaseDir 'Deinstallieren.bat'),
    "@echo off`r`nset `"APP=%~dp0app`"`r`ncd /d `"%USERPROFILE%`"`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%APP%\uninstall.ps1`"`r`n", [Text.Encoding]::ASCII)

# ------------------------------------------------------------- Anleitung
$ordner = @"
Ordner:
  website\   Die Dateien deiner Website. Du kannst sie auch direkt mit
             jedem Editor (z. B. VS Code oder Notepad) bearbeiten.
  backups\   Automatische Sicherungen, bevor ein neues Design die alte
             Version ersetzt.
  app\       Das Programm selbst (nicht ändern).
"@
if ($Online) {
    $readme = @"
$Name
$('=' * $Name.Length)

Deine Website:        https://$Domain/
Bearbeiten (überall): https://$Domain/_admin/   (mit deinem Passwort)

Dieser PC ist der Server. Die Website startet automatisch, sobald Windows
hochfährt - niemand muss sich anmelden. Solange der PC läuft und Internet
hat, ist die Seite erreichbar. Bitte nicht herunterfahren und nicht in den
Standby schicken (am Stromnetz ist Standby jetzt abgeschaltet).

Passwort vergessen oder ändern? Installer nochmal starten, gleichen Namen
eingeben, [2] wählen und "Einstellungen behalten" mit J beantworten.

Wenn etwas nicht geht: im Ordner logs\ stehen Hinweise (tunnel.log, server.log).

$ordner
  logs\      Protokolle von Webserver und Tunnel.

Entfernen: "Deinstallieren.bat" doppelklicken.
"@
} else {
    $readme = @"
$Name
$('=' * $Name.Length)

So benutzt du deine Website:

  * "$Name" auf dem Desktop            -> Website ansehen
  * "$Name bearbeiten" auf dem Desktop -> Design hochladen und Dateien bearbeiten

Solange die Website läuft, siehst du unten in der Taskleiste ein
PowerShell-Fenster. Schließt du es, ist die Website aus. Ein Klick auf
eine der Verknüpfungen startet sie wieder.

$ordner

Entfernen: "Deinstallieren.bat" doppelklicken.
"@
}
Write-Utf8 (Join-Path $BaseDir 'LIESMICH.txt') $readme $true
Step 'Starter und Anleitung'

# --------------------------------------------------------- Verknuepfungen
if ($Old -and $Old.shortcuts) {
    foreach ($s in @($Old.shortcuts)) { if ($s -and (Test-Path -LiteralPath $s)) { Remove-Item -LiteralPath $s -Force } }
}
$shortcuts = @()
try {
    $shell = New-Object -ComObject WScript.Shell
    $globe = (Join-Path $env:SystemRoot 'System32\shell32.dll') + ',13'
    $pen   = (Join-Path $env:SystemRoot 'System32\notepad.exe') + ',0'
    $places = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
    foreach ($dir in $places) {
        if (-not $dir -or -not (Test-Path $dir)) { continue }
        if ($Online) {
            $a = Join-Path $dir "$Name.url"
            $b = Join-Path $dir "$Name bearbeiten.url"
            New-UrlShortcut $a "https://$Domain/" $globe
            New-UrlShortcut $b "https://$Domain/_admin/" $pen
            $shortcuts += $a, $b
            continue
        }
        foreach ($s in @(
            @{ file = "$Name.lnk";            args = '';        desc = "$Name ansehen";    icon = $globe },
            @{ file = "$Name bearbeiten.lnk"; args = ' -Admin'; desc = "$Name bearbeiten"; icon = $pen }
        )) {
            $path = Join-Path $dir $s.file
            $lnk = $shell.CreateShortcut($path)
            $lnk.TargetPath = $PsExe
            $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ServerPs1`"" + $s.args
            $lnk.WorkingDirectory = $BaseDir
            $lnk.WindowStyle = 7   # minimiert
            $lnk.IconLocation = $s.icon
            $lnk.Description = $s.desc
            $lnk.Save()
            $shortcuts += $path
        }
    }
    Step 'Verknüpfungen auf dem Desktop und im Startmenü'
} catch {
    Warn "Verknüpfungen konnten nicht angelegt werden: $($_.Exception.Message)"
}
$config.shortcuts = $shortcuts
Write-Utf8 (Join-Path $AppDir 'config.json') (ConvertTo-Json -InputObject $config -Depth 3)

# ------------------------------------------------------------------- Start
if ($Online) {
    Start-ScheduledTask -TaskName $config.task
    Write-Host ''
    Write-Host '  Starte die Website ...'
    $localOk = $false
    for ($i = 0; $i -lt 30 -and -not $localOk; $i++) {
        Start-Sleep -Seconds 1
        try { $localOk = "$((Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://localhost:$Port/_api/ping").Content)" -eq 'meine-website-server' } catch {}
    }
    if ($localOk) { Step 'Webserver läuft' } else { Warn "Webserver antwortet noch nicht - siehe $BaseDir\logs\" }

    Write-Host '  Prüfe, ob die Website im Internet erreichbar ist (bis zu 2 Minuten) ...'
    $publicOk = $false
    for ($i = 0; $i -lt 24 -and -not $publicOk; $i++) {
        Start-Sleep -Seconds 5
        try { $publicOk = "$((Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "https://$Domain/_api/ping").Content)" -eq 'meine-website-server' } catch {}
    }
    Write-Host ''
    if ($publicOk) {
        Write-Host "  Fertig! Deine Website ist online: https://$Domain/" -ForegroundColor Green
    } else {
        Write-Host '  Fast fertig!' -ForegroundColor Green
        Warn "https://$Domain/ antwortet noch nicht. Das kann nach dem Umstellen der"
        Write-Host '      Nameserver etwas dauern. Probier es in ein paar Minuten nochmal.'
        Write-Host "      Hinweise stehen in $BaseDir\logs\tunnel.log"
    }
    Write-Host ''
    Write-Host "  Bearbeiten - von jedem Gerät aus: https://$Domain/_admin/"
    Write-Host '  (mit deinem Passwort anmelden)'
    Write-Host ''
    Write-Host "  Deine Dateien liegen in: $SiteDir"
    Write-Host '  Wichtig: Dieser PC muss dafür eingeschaltet bleiben.' -ForegroundColor Yellow
    Write-Host ''
    Start-Process "https://$Domain/_admin/"
    Finish 0
}

Start-Process -FilePath $PsExe -WindowStyle Minimized `
    -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$ServerPs1`"", '-Admin')
Step 'Website gestartet'

Write-Host ''
Write-Host '  Fertig!' -ForegroundColor Green
Write-Host ''
Write-Host '  Gleich öffnet sich dein Browser mit der Bearbeiten-Seite.'
Write-Host '  Dort ziehst du einfach deinen Claude-Design-Export hinein.'
Write-Host ''
Write-Host "  Später: Auf dem Desktop '$Name' oder '$Name bearbeiten' doppelklicken."
Write-Host "  Deine Dateien liegen in: $SiteDir"
Write-Host ''
Finish 0
