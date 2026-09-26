# Installer fuer "Meine Website".
# Wird von Website-Installer.bat gestartet. Legt einen Ordner mit deiner
# Website an, richtet Verknuepfungen ein und startet alles.
#
# Zwei Arten von Website:
#   einfach   - HTML-Design (z. B. aus Claude Design) hochladen und im
#               eingebauten Editor bearbeiten
#   wordpress - WordPress, portabel im Ordner: PHP, der Webserver Caddy und
#               SQLite als Datenbank (kein MySQL, nichts wird ins System installiert)
#
# Zwei Modi:
#   lokal  - die Website laeuft nur auf diesem PC (zum Ausprobieren)
#   online - dieser PC ist der Server fuer deine eigene Domain. Ein
#            Cloudflare Tunnel verbindet die Domain mit dem PC (HTTPS inklusive,
#            keine Router-Einstellungen). Alles startet automatisch mit Windows,
#            die Bearbeiten-Seite ist mit einem Passwort geschuetzt.
param(
    [string]$Name,
    [ValidateSet('', 'einfach', 'wordpress')][string]$Type = '',
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
    'wp\wp-config.php'      = '__B64_wordpress/wp-config.php__'
    'wp\wp-setup.php'       = '__B64_wordpress/wp-setup.php__'
    'wp\website-schutz.php' = '__B64_wordpress/website-schutz.php__'
    'wp\Caddyfile'          = '__B64_wordpress/Caddyfile__'
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

# ---------------------------------------------------------------------- Art
if (-not $Type) {
    Write-Host ''
    Write-Host '  Was für eine Website möchtest du?'
    Write-Host ''
    Write-Host '    [1] Einfache Website   - Design (z. B. aus Claude Design) hochladen und'
    Write-Host '                             im eingebauten Editor bearbeiten'
    Write-Host '    [2] WordPress          - Seiten, Beiträge, Bilder, Menüs, Plugins und'
    Write-Host '                             Themes bequem im WordPress-Dashboard bearbeiten'
    Write-Host ''
    $default = '1'
    if ($Old -and $Old.type -eq 'wordpress') { $default = '2' }
    $answer = Read-Host "  Deine Wahl (Enter = $default)"
    if (-not "$answer".Trim()) { $answer = $default }
    if ("$answer".Trim() -eq '2') { $Type = 'wordpress' } else { $Type = 'einfach' }
}
$IsWordPress = $Type -eq 'wordpress'
if ($IsWordPress -and -not [Environment]::Is64BitOperatingSystem) {
    throw 'WordPress braucht ein 64-Bit-Windows.'
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

# Fuer den Online-Modus und WordPress (und zum Abschalten eines frueheren
# Hintergrunddienstes) braucht es einmal Administrator-Rechte: Autostart-
# Aufgabe, Energiesparplan, ggf. die Visual-C++-Laufzeit fuer PHP.
$needAdmin = $Online -or $IsWordPress -or ($Old -and $Old.task)
if ($needAdmin -and -not (Test-Admin)) {
    Write-Host ''
    Write-Host '  Dafür braucht Windows einmal deine Erlaubnis (Administrator).'
    Write-Host '  Bitte im nächsten Fenster auf "Ja" klicken. Die Installation'
    Write-Host '  geht dann in einem neuen Fenster weiter.'
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                 '-Name', "`"$Name`"", '-Type', $Type, '-Mode', $Mode, '-BaseDir', "`"$BaseDir`"", '-Elevated')
    try {
        Start-Process -FilePath $PsExe -Verb RunAs -ArgumentList $argList -Wait
    } catch {
        Warn 'Ohne Administrator-Rechte geht das leider nicht.'
        Write-Host '      Starte den Installer nochmal und klicke auf "Ja".'
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
# Wechsel zwischen einfacher Website und WordPress: die bisherige Website
# komplett in die Sicherungen verschieben und frisch anfangen.
$oldType = 'einfach'
if ($Old -and $Old.type) { $oldType = $Old.type }
if ($Old -and $oldType -ne $Type -and @(Get-ChildItem -LiteralPath $SiteDir -Force).Count -gt 0) {
    $saved = Join-Path $BaseDir ('backups' + $oldType + '-' + (Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'))
    Move-Item -LiteralPath $SiteDir -Destination $saved
    New-Item -ItemType Directory -Path $SiteDir | Out-Null
    Step "Bisherige Website gesichert in $saved"
}
# PowerShell-Skripte mit BOM speichern, damit Umlaute unter Windows PowerShell stimmen.
foreach ($f in @('server.ps1', 'host.ps1', 'uninstall.ps1')) {
    Write-Utf8 (Join-Path $AppDir $f) (Get-PayloadText "app\$f") $true
}
foreach ($f in @('admin.html', 'login.html')) {
    [IO.File]::WriteAllBytes((Join-Path $AppDir $f), (Get-PayloadBytes "app\$f"))
}
Step 'Programmdateien'

if (-not $IsWordPress -and @(Get-ChildItem -LiteralPath $SiteDir -Force).Count -eq 0) {
    $start = (Get-PayloadText 'start.html').Replace('__SITE_NAME__', [Net.WebUtility]::HtmlEncode($Name))
    Write-Utf8 (Join-Path $SiteDir 'index.html') $start
    Step 'Startseite (Platzhalter)'
}

$config = [ordered]@{ name = $Name; type = $Type; mode = $Mode; installed = (Get-Date -Format 's') }
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

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

# ------------------------------------------------ WordPress-Zugangsdaten
$PhpDir     = Join-Path $AppDir 'php'
$CaddyDir   = Join-Path $AppDir 'caddy'
$WpToolsDir = Join-Path $AppDir 'wordpress'
$WpConfig   = Join-Path $SiteDir 'wp-config.php'
$wpInstalled = $IsWordPress -and (Test-Path $WpConfig) -and (Test-Path (Join-Path $SiteDir 'wp-content\database\.ht.sqlite'))
if ($IsWordPress -and -not $wpInstalled) {
    Write-Host ''
    Write-Host '  Dein WordPress-Zugang (damit meldest du dich später zum Bearbeiten an):' -ForegroundColor Cyan
    $defUser = ("$env:USERNAME" -replace '[^A-Za-z0-9._-]', '').ToLowerInvariant()
    if ($defUser.Length -lt 3 -or $defUser -eq 'admin') { $defUser = 'redaktion' }
    while ($true) {
        $WpUser = "$(Read-Host "  Benutzername (Enter = $defUser)")".Trim()
        if (-not $WpUser) { $WpUser = $defUser }
        # "admin" ist der erste Name, den Angreifer ausprobieren.
        if ($WpUser -match '^[A-Za-z0-9._@-]{3,60}$' -and $WpUser -ne 'admin') { break }
        Warn 'Bitte 3-60 Zeichen (Buchstaben, Zahlen, . _ - @) und nicht "admin".'
    }
    while ($true) {
        $WpEmail = "$(Read-Host '  E-Mail-Adresse')".Trim()
        if ($WpEmail -match '^[^@\s]+@[^@\s]+\.[^@\s]+$') { break }
        Warn 'Bitte eine gültige E-Mail-Adresse eingeben.'
    }
    $WpPass = Read-Password
}

# =================================================================== ONLINE
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

    # ------------------------------------------ Passwort (einfache Website)
    # Bei WordPress schuetzt WordPress selbst die Anmeldung.
    if (-not $IsWordPress) {
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
    }

    if ($keep) {
        $Domain = $Old.domain
        $TunnelId = $Old.tunnelId
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
    }
    $config.domain = $Domain
    $config.tunnelId = $TunnelId
}

# --------------------------------------------------------------------- Port
# Online und WordPress laufen im Hintergrund auf einem festen Port.
$Port = 0
if ($Online -or $IsWordPress) {
    if ($Old -and $Old.port) { $Port = [int]$Old.port } else { $Port = Get-FreePort 8080 }
    $config.port = $Port
}
if ($Online) { $SiteUrl = "https://$Domain" } else { $SiteUrl = "http://localhost:$Port" }
if ($Online -or $IsWordPress) { $config.url = $SiteUrl }

if ($Online) {
    # -------------------------------------------------- Tunnel-Konfiguration
    $hostnames = @($Domain)
    if ($Domain.Split('.').Count -eq 2) { $hostnames += "www.$Domain" }
    $yml = "tunnel: $TunnelId`r`ncredentials-file: '" + $CfCred.Replace("'", "''") + "'`r`ningress:`r`n"
    foreach ($h in $hostnames) {
        $yml += "  - hostname: $h`r`n    service: http://127.0.0.1:$Port`r`n"
        # Der einfache Server nimmt nur "localhost" als Host an. WordPress dagegen
        # muss den echten Domainnamen sehen, sonst leitet es endlos auf die Domain um.
        if (-not $IsWordPress) { $yml += "    originRequest:`r`n      httpHostHeader: localhost:$Port`r`n" }
    }
    $yml += "  - service: http_status:404`r`n"
    Write-Utf8 $CfYml $yml

    # ---------------------------------------------------- Nicht einschlafen
    # Ein Server muss wach bleiben: im Netzbetrieb kein Standby/Ruhezustand.
    & powercfg.exe /change standby-timeout-ac 0 | Out-Null
    & powercfg.exe /change hibernate-timeout-ac 0 | Out-Null
    Step 'Energiesparen: PC geht am Stromnetz nicht mehr in den Standby'
}

# ================================================================ WORDPRESS
function Save-Download([string[]]$urls, [string]$target, [string]$what) {
    Write-Host "  Lade $what herunter ..."
    $last = $null
    foreach ($u in $urls) {
        try { Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $target; return } catch { $last = $_ }
    }
    throw "$what konnte nicht heruntergeladen werden: $($last.Exception.Message)"
}

function Expand-ZipTo([string]$zip, [string]$dest) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest | Out-Null }
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, $dest)
}

# Steckt alles in genau einem Unterordner, diesen zurueckgeben.
function Get-InnerFolder([string]$dir) {
    $e = @(Get-ChildItem -LiteralPath $dir -Force)
    if ($e.Count -eq 1 -and $e[0].PSIsContainer) { return $e[0].FullName }
    return $dir
}

# PHP fuer Windows braucht die Visual-C++-Laufzeit (2015-2022).
function Test-VcRuntime {
    foreach ($k in @('HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
                     'HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64')) {
        $v = Get-ItemProperty -Path $k -ErrorAction SilentlyContinue
        if ($v -and $v.Installed -eq 1 -and [int]$v.Minor -ge 30) { return $true }
    }
    return $false
}

function New-Secret {
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#%()*+,-.:;<=>?@[]^_{|}~'
    $bytes = New-Object byte[] 64
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

if ($IsWordPress) {
    Write-Host ''
    Write-Host '  WordPress wird eingerichtet ...' -ForegroundColor Cyan
    $LogDir = Join-Path $BaseDir 'logs'
    $PhpTmp = Join-Path $PhpDir 'tmp'
    $PhpIni = Join-Path $PhpDir 'php.ini'
    foreach ($d in @($PhpDir, $CaddyDir, $WpToolsDir, $LogDir)) {
        if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
    }
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('website-installer-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        # ------------------------------------------------ Visual C++ Laufzeit
        if (-not (Test-VcRuntime)) {
            $vc = Join-Path $tmp 'vc_redist.x64.exe'
            Save-Download @('https://aka.ms/vs/17/release/vc_redist.x64.exe') $vc 'die Visual-C++-Laufzeit (für PHP)'
            Start-Process -FilePath $vc -ArgumentList @('/install', '/quiet', '/norestart') -Wait | Out-Null
            if (-not (Test-VcRuntime)) { throw 'Die Visual-C++-Laufzeit ließ sich nicht installieren.' }
            Step 'Visual-C++-Laufzeit installiert'
        }

        # ---------------------------------------------------------------- PHP
        if (-not (Test-Path (Join-Path $PhpDir 'php-cgi.exe'))) {
            $releases = Invoke-RestMethod -UseBasicParsing -Uri 'https://windows.php.net/downloads/releases/releases.json'
            $branch = $releases.'8.3'
            if (-not $branch) {
                $newest = $releases.PSObject.Properties | Sort-Object { [version]$_.Name } | Select-Object -Last 1
                $branch = $newest.Value
            }
            $build = $branch.PSObject.Properties | Where-Object { $_.Name -match '^nts-vs\d+-x64$' } | Select-Object -First 1
            if (-not $build) { throw 'Keine passende PHP-Version gefunden.' }
            $phpZip = Join-Path $tmp 'php.zip'
            # Reste eines abgebrochenen Versuchs entfernen, sonst scheitert das Entpacken.
            if (Test-Path $PhpDir) { Remove-Item -LiteralPath $PhpDir -Recurse -Force }
            Save-Download @("https://windows.php.net/downloads/releases/$($build.Value.zip.path)",
                            "https://windows.php.net/downloads/releases/archives/$($build.Value.zip.path)") $phpZip "PHP $($branch.version)"
            Expand-ZipTo $phpZip $PhpDir
            Step "PHP $($branch.version)"
        }
        foreach ($d in @($PhpTmp, (Join-Path $PhpDir 'opcache'))) {
            if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
        }
        $fw = { param($p) $p.Replace('\', '/') }
        $caBundle = & $fw (Join-Path $SiteDir 'wp-includes\certificates\ca-bundle.crt')
        $ini = @"
; PHP-Einstellungen fuer WordPress (angelegt vom Website-Installer)
extension_dir = "$(& $fw (Join-Path $PhpDir 'ext'))"
extension=curl
extension=exif
extension=fileinfo
extension=gd
extension=intl
extension=mbstring
extension=openssl
extension=pdo_sqlite
extension=sqlite3
extension=zip
zend_extension=opcache
opcache.enable=1
opcache.memory_consumption=128
opcache.max_accelerated_files=20000
opcache.revalidate_freq=2
opcache.file_cache="$(& $fw (Join-Path $PhpDir 'opcache'))"
opcache.file_cache_fallback=1
memory_limit=256M
upload_max_filesize=100M
post_max_size=100M
max_execution_time=300
max_input_vars=5000
date.timezone=Europe/Berlin
expose_php=Off
display_errors=Off
log_errors=On
error_log="$(& $fw (Join-Path $LogDir 'php-fehler.log'))"
upload_tmp_dir="$(& $fw $PhpTmp)"
sys_temp_dir="$(& $fw $PhpTmp)"
session.save_path="$(& $fw $PhpTmp)"
curl.cainfo="$caBundle"
openssl.cafile="$caBundle"
cgi.fix_pathinfo=1
"@
        Write-Utf8 $PhpIni $ini

        # -------------------------------------------------------------- Caddy
        $caddyExe = Join-Path $CaddyDir 'caddy.exe'
        if (-not (Test-Path $caddyExe)) {
            try {
                Save-Download @('https://caddyserver.com/api/download?os=windows&arch=amd64') $caddyExe 'den Webserver Caddy'
            } catch {
                $rel = Invoke-RestMethod -UseBasicParsing -Uri 'https://api.github.com/repos/caddyserver/caddy/releases/latest'
                $asset = $rel.assets | Where-Object { $_.name -like '*_windows_amd64.zip' } | Select-Object -First 1
                $caddyZip = Join-Path $tmp 'caddy.zip'
                Save-Download @($asset.browser_download_url) $caddyZip 'den Webserver Caddy (GitHub)'
                Expand-ZipTo $caddyZip (Join-Path $tmp 'caddy')
                Copy-Item -LiteralPath (Join-Path $tmp 'caddy\caddy.exe') -Destination $caddyExe
            }
            Step 'Webserver Caddy'
        }
        # Mehrere PHP-Prozesse, damit mehrere Besucher gleichzeitig bedient werden.
        $phpPorts = @()
        $next = 9100
        for ($i = 0; $i -lt 4; $i++) { $next = Get-FreePort ($next + 1); $phpPorts += $next }
        $config.phpPorts = $phpPorts
        $upstreams = ($phpPorts | ForEach-Object { "127.0.0.1:$_" }) -join ' '
        $caddyfile = (Get-PayloadText 'wp\Caddyfile').Replace('__PORT__', "$Port")
        $caddyfile = $caddyfile.Replace('__ROOT__', (& $fw $SiteDir)).Replace('__PHP_UPSTREAMS__', $upstreams)
        Write-Utf8 (Join-Path $CaddyDir 'Caddyfile') $caddyfile

        # ---------------------------------------------------------- WordPress
        Write-Utf8 (Join-Path $WpToolsDir 'wp-setup.php') (Get-PayloadText 'wp\wp-setup.php')
        if (-not (Test-Path (Join-Path $SiteDir 'wp-load.php'))) {
            $wpZip = Join-Path $tmp 'wordpress.zip'
            Save-Download @('https://de.wordpress.org/latest-de_DE.zip', 'https://wordpress.org/latest.zip') $wpZip 'WordPress'
            Expand-ZipTo $wpZip (Join-Path $tmp 'wp')
            Copy-Item -Path (Join-Path (Get-InnerFolder (Join-Path $tmp 'wp')) '*') -Destination $SiteDir -Recurse -Force
            Step 'WordPress (deutsch)'
        }
        $pluginDir = Join-Path $SiteDir 'wp-content\plugins\sqlite-database-integration'
        if (-not (Test-Path (Join-Path $pluginDir 'load.php'))) {
            $sqZip = Join-Path $tmp 'sqlite.zip'
            Save-Download @('https://downloads.wordpress.org/plugin/sqlite-database-integration.latest-stable.zip',
                            'https://github.com/WordPress/sqlite-database-integration/releases/latest/download/plugin-sqlite-database-integration.zip') `
                $sqZip 'die SQLite-Datenbank für WordPress'
            Expand-ZipTo $sqZip (Join-Path $tmp 'sqlite')
            if (Test-Path $pluginDir) { Remove-Item -LiteralPath $pluginDir -Recurse -Force }
            Copy-Item -LiteralPath (Get-InnerFolder (Join-Path $tmp 'sqlite')) -Destination $pluginDir -Recurse
            Step 'SQLite-Datenbank (statt MySQL)'
        }
        $dbPhp = Join-Path $SiteDir 'wp-content\db.php'
        if (-not (Test-Path $dbPhp)) {
            $drop = [IO.File]::ReadAllText((Join-Path $pluginDir 'db.copy'))
            $drop = $drop.Replace("'{SQLITE_IMPLEMENTATION_FOLDER_PATH}'", "__DIR__ . '/plugins/sqlite-database-integration'")
            $drop = $drop.Replace('{SQLITE_PLUGIN}', 'sqlite-database-integration/load.php')
            Write-Utf8 $dbPhp $drop
        }
        $muDir = Join-Path $SiteDir 'wp-content\mu-plugins'
        if (-not (Test-Path $muDir)) { New-Item -ItemType Directory -Path $muDir | Out-Null }
        Write-Utf8 (Join-Path $muDir 'website-schutz.php') (Get-PayloadText 'wp\website-schutz.php')

        $oldUrl = ''
        if ($Old -and $Old.url) { $oldUrl = [string]$Old.url }
        if (-not (Test-Path $WpConfig)) {
            $salts = (@('AUTH_KEY', 'SECURE_AUTH_KEY', 'LOGGED_IN_KEY', 'NONCE_KEY',
                        'AUTH_SALT', 'SECURE_AUTH_SALT', 'LOGGED_IN_SALT', 'NONCE_SALT') |
                ForEach-Object { "define( '$_', '$(New-Secret)' );" }) -join "`n"
            $wpc = (Get-PayloadText 'wp\wp-config.php').Replace('__SALTS__', $salts).Replace('__URL__', $SiteUrl)
            Write-Utf8 $WpConfig $wpc
        } else {
            # Adresse aktualisieren (z. B. Wechsel von lokal auf die eigene Domain).
            $wpc = [IO.File]::ReadAllText($WpConfig)
            foreach ($c in @('WP_HOME', 'WP_SITEURL')) {
                $wpc = [regex]::Replace($wpc, "define\(\s*'$c',\s*'[^']*'\s*\);", "define( '$c', '$SiteUrl' );")
            }
            Write-Utf8 $WpConfig $wpc
        }

        # ------------------------------------------------- Einrichten (PHP-CLI)
        $env:MW_WP_DIR = $SiteDir
        $env:MW_URL = $SiteUrl
        $env:MW_OLD_URL = $oldUrl
        $env:MW_TITLE = $Name
        $env:MW_USER = $WpUser
        $env:MW_EMAIL = $WpEmail
        $env:MW_PASS = $WpPass
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $out = & (Join-Path $PhpDir 'php.exe') -c $PhpIni -d display_errors=stderr (Join-Path $WpToolsDir 'wp-setup.php') 2>&1 |
                ForEach-Object { "$_" }
            $code = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $prev
            foreach ($v in @('MW_WP_DIR', 'MW_URL', 'MW_OLD_URL', 'MW_TITLE', 'MW_USER', 'MW_EMAIL', 'MW_PASS')) {
                Remove-Item "Env:\$v" -ErrorAction SilentlyContinue
            }
        }
        if ($code -ne 0) { throw "WordPress-Einrichtung fehlgeschlagen:`n$($out -join "`n")" }
        if ($wpInstalled) { Step 'WordPress aktualisiert (Inhalte bleiben erhalten)' } else { Step "WordPress eingerichtet - Benutzer: $WpUser" }
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------- Autostart
if ($Online -or $IsWordPress) {
    $taskName = "Website - $Name"
    $action = New-ScheduledTaskAction -Execute $PsExe -WorkingDirectory $BaseDir `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$HostPs1`""
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal `
        -Settings $settings -Description "Startet die Website $SiteUrl beim Hochfahren." -Force | Out-Null
    $config.task = $taskName
    Step 'Startet automatisch mit Windows (auch ohne Anmeldung)'
} elseif ($Old -and $Old.task) {
    # Wechsel zur einfachen, lokalen Website: Hintergrunddienst abschalten.
    try { Unregister-ScheduledTask -TaskName $Old.task -Confirm:$false } catch {}
    Step 'Hintergrunddienst abgeschaltet (Autostart entfernt)'
    if ($Old.domain) {
        Write-Host '      Der Tunnel bei Cloudflare bleibt bestehen; installiere erneut mit [2], um ihn wieder zu nutzen.'
    }
}
$Background = $Online -or $IsWordPress

# ---------------------------------------------------- Starter im Ordner
$runServer = 'start "" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\server.ps1"'
foreach ($f in @('Website starten.bat', 'Website bearbeiten.bat')) {
    $p = Join-Path $BaseDir $f
    if (Test-Path $p) { Remove-Item -LiteralPath $p -Force }
}
if (-not $Background) {
    [IO.File]::WriteAllText((Join-Path $BaseDir 'Website starten.bat'), "@echo off`r`n$runServer`r`n", [Text.Encoding]::ASCII)
    [IO.File]::WriteAllText((Join-Path $BaseDir 'Website bearbeiten.bat'), "@echo off`r`n$runServer -Admin`r`n", [Text.Encoding]::ASCII)
}
[IO.File]::WriteAllText((Join-Path $BaseDir 'Deinstallieren.bat'),
    "@echo off`r`nset `"APP=%~dp0app`"`r`ncd /d `"%USERPROFILE%`"`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%APP%\uninstall.ps1`"`r`n", [Text.Encoding]::ASCII)

# ------------------------------------------------------------- Anleitung
if ($IsWordPress) { $EditUrl = "$SiteUrl/wp-admin/" } else { $EditUrl = "$SiteUrl/_admin/" }
$dienst = @"
Die Website läuft im Hintergrund und startet automatisch, sobald Windows
hochfährt - niemand muss sich anmelden.
"@
if ($Online) {
    $dienst += @"

Dieser PC ist der Server: Solange er läuft und Internet hat, ist die Seite
erreichbar. Bitte nicht herunterfahren und nicht in den Standby schicken
(am Stromnetz ist Standby jetzt abgeschaltet).
"@
}
if ($IsWordPress) {
    $readme = @"
$Name
$('=' * $Name.Length)

Deine Website:  $SiteUrl/
Bearbeiten:     $EditUrl   (mit deinem WordPress-Benutzer)

$dienst

Im WordPress-Dashboard bearbeitest du Seiten, Beiträge, Bilder und Menüs.
Unter "Design -> Themes -> Theme hochladen" kannst du ein eigenes Design
(Theme als ZIP) hochladen. Updates für WordPress, Plugins und Themes
installierst du ebenfalls im Dashboard.

Passwort vergessen? WordPress kann keine E-Mails verschicken. Frag Claude
nach einem Befehl zum Zurücksetzen, oder lege im Dashboard einen zweiten
Admin-Benutzer als Reserve an.

Ordner:
  website\   WordPress mit allen Inhalten. Die Datenbank liegt in
             website\wp-content\database\ (SQLite, kein MySQL nötig).
             Zum Sichern einfach den ganzen Ordner kopieren.
  app\       PHP, der Webserver Caddy und das Programm (nicht ändern).
  logs\      Protokolle - hier stehen Hinweise, wenn etwas nicht geht.

Entfernen: "Deinstallieren.bat" doppelklicken.
"@
} elseif ($Online) {
    $readme = @"
$Name
$('=' * $Name.Length)

Deine Website:        $SiteUrl/
Bearbeiten (überall): $EditUrl   (mit deinem Passwort)

$dienst

Passwort vergessen oder ändern? Installer nochmal starten, gleichen Namen
eingeben, [2] wählen und "Einstellungen behalten" mit J beantworten.

Ordner:
  website\   Die Dateien deiner Website.
  backups\   Automatische Sicherungen, bevor ein neues Design die alte
             Version ersetzt.
  app\       Das Programm selbst (nicht ändern).
  logs\      Protokolle - hier stehen Hinweise, wenn etwas nicht geht.

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

Ordner:
  website\   Die Dateien deiner Website. Du kannst sie auch direkt mit
             jedem Editor (z. B. VS Code oder Notepad) bearbeiten.
  backups\   Automatische Sicherungen, bevor ein neues Design die alte
             Version ersetzt.
  app\       Das Programm selbst (nicht ändern).

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
        if ($Background) {
            # Laeuft im Hintergrund: die Verknuepfungen oeffnen nur den Browser.
            $a = Join-Path $dir "$Name.url"
            $b = Join-Path $dir "$Name bearbeiten.url"
            New-UrlShortcut $a "$SiteUrl/" $globe
            New-UrlShortcut $b $EditUrl $pen
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
# Antwortet die Website? WordPress: Login-Seite, einfache Website: Ping.
function Test-Site([string]$base) {
    try {
        if ($IsWordPress) {
            return (Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "$base/wp-login.php").StatusCode -eq 200
        }
        return "$((Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "$base/_api/ping").Content)" -eq 'meine-website-server'
    } catch { return $false }
}

if ($Background) {
    Start-ScheduledTask -TaskName $config.task
    Write-Host ''
    Write-Host '  Starte die Website ...'
    $localOk = $false
    for ($i = 0; $i -lt 45 -and -not $localOk; $i++) {
        Start-Sleep -Seconds 2
        $localOk = Test-Site "http://127.0.0.1:$Port"
    }
    if ($localOk) { Step 'Webserver läuft' } else { Warn "Webserver antwortet noch nicht - siehe $BaseDir\logs\" }

    $publicOk = $true
    if ($Online) {
        Write-Host '  Prüfe, ob die Website im Internet erreichbar ist (bis zu 2 Minuten) ...'
        $publicOk = $false
        for ($i = 0; $i -lt 24 -and -not $publicOk; $i++) {
            Start-Sleep -Seconds 5
            $publicOk = Test-Site $SiteUrl
        }
    }
    Write-Host ''
    if ($publicOk -and $localOk) {
        Write-Host "  Fertig! Deine Website: $SiteUrl/" -ForegroundColor Green
    } else {
        Write-Host '  Fast fertig!' -ForegroundColor Green
        if (-not $publicOk) {
            Warn "$SiteUrl/ antwortet noch nicht. Das kann nach dem Umstellen der"
            Write-Host '      Nameserver etwas dauern. Probier es in ein paar Minuten nochmal.'
            Write-Host "      Hinweise stehen in $BaseDir\logs\tunnel.log"
        }
    }
    Write-Host ''
    if ($IsWordPress) {
        Write-Host "  Bearbeiten im WordPress-Dashboard: $EditUrl"
        if ($WpUser) { Write-Host "  (anmelden als: $WpUser)" }
    } else {
        Write-Host "  Bearbeiten - von jedem Gerät aus: $EditUrl"
        Write-Host '  (mit deinem Passwort anmelden)'
    }
    Write-Host ''
    Write-Host "  Deine Dateien liegen in: $SiteDir"
    if ($Online) { Write-Host '  Wichtig: Dieser PC muss dafür eingeschaltet bleiben.' -ForegroundColor Yellow }
    Write-Host ''
    Start-Process $EditUrl
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
