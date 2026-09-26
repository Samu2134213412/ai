# Haelt die Website im Hintergrund am Laufen. Wird von der Windows-
# Aufgabenplanung beim Hochfahren gestartet (auch ohne Anmeldung) und
# startet alles neu, was abstuerzt:
#   Einfache Website: den kleinen PowerShell-Webserver
#   WordPress:        PHP (mehrere php-cgi-Prozesse) und den Webserver Caddy
#   Online-Modus:     zusaetzlich den Cloudflare Tunnel zu deiner Domain
$ErrorActionPreference = 'Continue'

$AppDir    = $PSScriptRoot
$BaseDir   = Split-Path $AppDir -Parent
$LogDir    = Join-Path $BaseDir 'logs'
$ServerPs1 = Join-Path $AppDir 'server.ps1'
$CfExe     = Join-Path $AppDir 'cloudflared\cloudflared.exe'
$CfConfig  = Join-Path $AppDir 'cloudflared\config.yml'
$PhpCgi    = Join-Path $AppDir 'php\php-cgi.exe'
$PhpIni    = Join-Path $AppDir 'php\php.ini'
$CaddyExe  = Join-Path $AppDir 'caddy\caddy.exe'
$Caddyfile = Join-Path $AppDir 'caddy\Caddyfile'
$PsExe     = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

$config = Get-Content (Join-Path $AppDir 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$IsWordPress = $config.type -eq 'wordpress'
$UseTunnel = [bool]$config.domain -and (Test-Path $CfConfig)

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-Log([string]$text) {
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $text
    Add-Content -LiteralPath (Join-Path $LogDir 'host.log') -Value $line -Encoding UTF8
}

# Reste eines frueheren Laufs beenden (z. B. nach einem Absturz).
Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains($AppDir) -and
    -not $_.CommandLine.Contains('host.ps1')
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# Die Logdateien klein halten.
Get-ChildItem -LiteralPath $LogDir -File | Where-Object { $_.Length -gt 5MB } | Remove-Item -Force -ErrorAction SilentlyContinue

# php-cgi beendet sich sonst nach 500 Anfragen.
$env:PHP_FCGI_MAX_REQUESTS = '0'

function Start-Logged([string]$what, [string]$file, [string[]]$argList, [string]$log) {
    Write-Log "Starte $what"
    Start-Process -FilePath $file -ArgumentList $argList -PassThru -WorkingDirectory $BaseDir `
        -RedirectStandardOutput (Join-Path $LogDir "$log-ausgabe.log") `
        -RedirectStandardError (Join-Path $LogDir "$log.log")
}

# Was laufen soll: Name -> Startbefehl
$services = [ordered]@{}
if ($IsWordPress) {
    $i = 0
    foreach ($p in @($config.phpPorts)) {
        $i++
        $services["PHP $i"] = @{ file = $PhpCgi; args = @('-b', "127.0.0.1:$p", '-c', "`"$PhpIni`""); log = "php-$i" }
    }
    $services['Webserver'] = @{ file = $CaddyExe; args = @('run', '--config', "`"$Caddyfile`"", '--adapter', 'caddyfile'); log = 'webserver' }
} else {
    $services['Webserver'] = @{ file = $PsExe; args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$ServerPs1`"", '-Service'); log = 'server' }
}
if ($UseTunnel) {
    $services['Cloudflare Tunnel'] = @{ file = $CfExe; args = @('tunnel', '--no-autoupdate', '--config', "`"$CfConfig`"", 'run'); log = 'tunnel' }
}

Write-Log 'Gestartet'
$running = @{}
while ($true) {
    foreach ($name in $services.Keys) {
        try {
            $proc = $running[$name]
            if (-not $proc -or $proc.HasExited) {
                if ($proc) { Write-Log "$name wurde beendet (Code $($proc.ExitCode))" }
                $s = $services[$name]
                $running[$name] = Start-Logged $name $s.file $s.args $s.log
            }
        } catch {
            Write-Log "Fehler bei ${name}: $($_.Exception.Message)"
        }
    }
    Start-Sleep -Seconds 10
}
