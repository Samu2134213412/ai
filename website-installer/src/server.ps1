# Lokaler Webserver fuer "Meine Website".
# Liefert den Ordner "website" aus und stellt unter /_admin/ eine
# Bearbeiten-Seite bereit (Design hochladen, Dateien bearbeiten).
# Laeuft nur auf diesem PC (http://localhost), braucht keine Admin-Rechte
# und nichts ausser dem PowerShell, das in Windows schon drin ist.
param(
    [switch]$Admin,      # nach dem Start die Bearbeiten-Seite oeffnen
    [switch]$NoBrowser   # keinen Browser oeffnen
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$AppDir    = $PSScriptRoot
$BaseDir   = Split-Path $AppDir -Parent
$SiteDir   = Join-Path $BaseDir 'website'
$BackupDir = Join-Path $BaseDir 'backups'
$AdminFile = Join-Path $AppDir 'admin.html'
$Marker    = 'meine-website-server'
$MaxBackups = 15

$SiteName = 'Meine Website'
$configFile = Join-Path $AppDir 'config.json'
if (Test-Path $configFile) {
    try { $SiteName = (Get-Content $configFile -Raw -Encoding UTF8 | ConvertFrom-Json).name } catch {}
}
foreach ($d in @($SiteDir, $BackupDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}

$MimeTypes = @{
    '.html' = 'text/html; charset=utf-8';  '.htm'  = 'text/html; charset=utf-8'
    '.css'  = 'text/css; charset=utf-8';   '.js'   = 'text/javascript; charset=utf-8'
    '.mjs'  = 'text/javascript; charset=utf-8'
    '.json' = 'application/json; charset=utf-8'; '.map' = 'application/json; charset=utf-8'
    '.txt'  = 'text/plain; charset=utf-8'; '.md'   = 'text/plain; charset=utf-8'
    '.xml'  = 'application/xml; charset=utf-8'
    '.svg'  = 'image/svg+xml'; '.png' = 'image/png'; '.jpg' = 'image/jpeg'; '.jpeg' = 'image/jpeg'
    '.gif'  = 'image/gif';     '.webp' = 'image/webp'; '.avif' = 'image/avif'; '.ico' = 'image/x-icon'
    '.bmp'  = 'image/bmp'
    '.woff' = 'font/woff'; '.woff2' = 'font/woff2'; '.ttf' = 'font/ttf'; '.otf' = 'font/otf'
    '.mp4'  = 'video/mp4'; '.webm' = 'video/webm'; '.mp3' = 'audio/mpeg'; '.wav' = 'audio/wav'
    '.ogg'  = 'audio/ogg'; '.pdf' = 'application/pdf'; '.zip' = 'application/zip'
    '.wasm' = 'application/wasm'; '.webmanifest' = 'application/manifest+json'
}

function Get-Mime([string]$path) {
    $ext = [IO.Path]::GetExtension($path).ToLowerInvariant()
    if ($MimeTypes.ContainsKey($ext)) { return $MimeTypes[$ext] }
    return 'application/octet-stream'
}

# ------------------------------------------------------------------ Antworten
function Send-Bytes($ctx, [int]$status, [string]$type, [byte[]]$bytes) {
    $res = $ctx.Response
    $res.StatusCode = $status
    $res.ContentType = $type
    $res.Headers['Cache-Control'] = 'no-store'
    $res.ContentLength64 = $bytes.Length
    if ($ctx.Request.HttpMethod -ne 'HEAD' -and $bytes.Length -gt 0) {
        $res.OutputStream.Write($bytes, 0, $bytes.Length)
    }
}
function Send-Text($ctx, [int]$status, [string]$text, [string]$type = 'text/plain; charset=utf-8') {
    Send-Bytes $ctx $status $type ([Text.Encoding]::UTF8.GetBytes($text))
}
function Send-Json($ctx, $obj, [int]$status = 200) {
    Send-Text $ctx $status (ConvertTo-Json -InputObject $obj -Depth 5 -Compress) 'application/json; charset=utf-8'
}
function Send-Error($ctx, [int]$status, [string]$message) {
    Send-Json $ctx @{ error = $message } $status
}
function Send-Redirect($ctx, [string]$location) {
    $ctx.Response.StatusCode = 302
    $ctx.Response.RedirectLocation = $location
}

function Read-Body($req) {
    $ms = New-Object IO.MemoryStream
    $req.InputStream.CopyTo($ms)
    return ,$ms.ToArray()
}

# ------------------------------------------------------------------- Pfade
$SiteRoot = [IO.Path]::GetFullPath($SiteDir).TrimEnd('\', '/')

# Wandelt einen relativen Pfad ("css/style.css") in einen absoluten Pfad im
# Website-Ordner um. Alles, was aus dem Ordner herausfuehren wuerde, wird
# abgelehnt.
function Resolve-SitePath([string]$rel, [switch]$AllowRoot) {
    if ($null -eq $rel) { $rel = '' }
    $rel = $rel.Replace('\', '/').Trim().Trim('/')
    if ($rel -eq '') {
        if ($AllowRoot) { return $SiteRoot }
        throw 'Kein Dateiname angegeben.'
    }
    foreach ($part in $rel.Split('/')) {
        if ($part -eq '' -or $part -eq '.' -or $part -eq '..' -or
            $part.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) {
            throw "Ungueltiger Dateiname: $rel"
        }
    }
    $full = [IO.Path]::GetFullPath([IO.Path]::Combine($SiteRoot, $rel.Replace('/', [IO.Path]::DirectorySeparatorChar)))
    $prefix = $SiteRoot + [IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Ungueltiger Pfad: $rel"
    }
    return $full
}

function Get-RelPath([string]$full) {
    return $full.Substring($SiteRoot.Length).TrimStart('\', '/').Replace('\', '/')
}

# ------------------------------------------------------------ Website-Pflege
function Backup-Site {
    $items = @(Get-ChildItem -LiteralPath $SiteDir -Force)
    if ($items.Count -eq 0) { return $null }
    $name = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
    $target = Join-Path $BackupDir $name
    New-Item -ItemType Directory -Path $target | Out-Null
    foreach ($i in $items) { Copy-Item -LiteralPath $i.FullName -Destination $target -Recurse -Force }
    # Nur die neuesten Sicherungen behalten.
    $all = @(Get-ChildItem -LiteralPath $BackupDir -Directory | Sort-Object Name -Descending)
    if ($all.Count -gt $MaxBackups) {
        $all | Select-Object -Skip $MaxBackups | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    }
    return $name
}

function Clear-Site {
    $backup = Backup-Site
    Get-ChildItem -LiteralPath $SiteDir -Force | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    return $backup
}

# Sorgt dafuer, dass es eine Startseite (index.html) gibt. Heisst die
# hochgeladene Seite anders (z. B. "Landingpage.html"), wird eine kleine
# index.html angelegt, die dorthin weiterleitet.
function Ensure-Index {
    if (Test-Path -LiteralPath (Join-Path $SiteDir 'index.html')) { return $null }
    $html = @(Get-ChildItem -LiteralPath $SiteDir -File | Where-Object { $_.Extension -match '^\.html?$' } | Sort-Object Name)
    if ($html.Count -eq 0) { return $null }
    $target = $html[0].Name
    $href = [Uri]::EscapeDataString($target)
    $page = "<!doctype html><meta charset=`"utf-8`"><meta http-equiv=`"refresh`" content=`"0; url=$href`"><title>Weiterleitung</title><a href=`"$href`">Weiter</a>"
    [IO.File]::WriteAllText((Join-Path $SiteDir 'index.html'), $page, (New-Object Text.UTF8Encoding $false))
    return $target
}

function Expand-Upload([byte[]]$zipBytes, [bool]$replace) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('meine-website-' + [Guid]::NewGuid().ToString('N'))
    $zipPath = "$tmp.zip"
    try {
        [IO.File]::WriteAllBytes($zipPath, $zipBytes)
        [IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $tmp)
        Get-ChildItem -LiteralPath $tmp -Force -Recurse -Directory -Filter '__MACOSX' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Get-ChildItem -LiteralPath $tmp -Force -Recurse -File | Where-Object { $_.Name -eq '.DS_Store' -or $_.Name -eq 'Thumbs.db' } | Remove-Item -Force -ErrorAction SilentlyContinue

        # Liegt alles in einem einzigen Unterordner, dessen Inhalt nehmen.
        $src = $tmp
        while ($true) {
            $entries = @(Get-ChildItem -LiteralPath $src -Force)
            if ($entries.Count -eq 1 -and $entries[0].PSIsContainer) { $src = $entries[0].FullName } else { break }
        }
        $backup = $null
        if ($replace) { $backup = Clear-Site }
        foreach ($i in Get-ChildItem -LiteralPath $src -Force) {
            $dest = Join-Path $SiteDir $i.Name
            if ($i.PSIsContainer -and (Test-Path -LiteralPath $dest)) {
                # Ordner zusammenfuehren statt verschachteln.
                foreach ($c in Get-ChildItem -LiteralPath $i.FullName -Force) {
                    Copy-Item -LiteralPath $c.FullName -Destination $dest -Recurse -Force
                }
            } else {
                Copy-Item -LiteralPath $i.FullName -Destination $SiteDir -Recurse -Force
            }
        }
        $count = @(Get-ChildItem -LiteralPath $src -Recurse -File -Force).Count
        return @{ files = $count; backup = $backup; redirect = (Ensure-Index) }
    } finally {
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------------------------- API
function Invoke-Api($ctx, [string]$action) {
    $req = $ctx.Request
    $method = $req.HttpMethod

    if ($action -eq 'ping') { Send-Text $ctx 200 $Marker; return }

    # Schutz: Nur die eigene Bearbeiten-Seite darf die API benutzen. Fremde
    # Webseiten im Browser koennen diesen Header nicht mitschicken.
    if ($req.Headers['X-Meine-Website'] -ne '1') { Send-Error $ctx 403 'Nicht erlaubt.'; return }

    switch ("$method $action") {
        'GET info' {
            Send-Json $ctx @{ name = $SiteName; folder = $BaseDir; site = $SiteDir; url = "http://localhost:$Port/" }
        }
        'GET files' {
            $list = @(Get-ChildItem -LiteralPath $SiteDir -Recurse -File -Force | Sort-Object FullName | ForEach-Object {
                @{ path = (Get-RelPath $_.FullName); size = $_.Length; modified = $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm') }
            })
            Send-Json $ctx $list
        }
        'GET file' {
            $full = Resolve-SitePath $req.QueryString['path']
            if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { Send-Error $ctx 404 'Datei nicht gefunden.'; return }
            Send-Bytes $ctx 200 (Get-Mime $full) ([IO.File]::ReadAllBytes($full))
        }
        'PUT file' {
            $full = Resolve-SitePath $req.QueryString['path']
            $dir = Split-Path $full -Parent
            if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
            [IO.File]::WriteAllBytes($full, (Read-Body $req))
            Send-Json $ctx @{ ok = $true; path = (Get-RelPath $full) }
        }
        'DELETE file' {
            $full = Resolve-SitePath $req.QueryString['path']
            if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
            # Leere Ordner aufraeumen.
            $dir = Split-Path $full -Parent
            while ($dir.Length -gt $SiteRoot.Length -and @(Get-ChildItem -LiteralPath $dir -Force).Count -eq 0) {
                Remove-Item -LiteralPath $dir -Force
                $dir = Split-Path $dir -Parent
            }
            Send-Json $ctx @{ ok = $true }
        }
        'POST upload-zip' {
            $result = Expand-Upload (Read-Body $req) ($req.QueryString['replace'] -eq '1')
            Send-Json $ctx $result
        }
        'POST clear' {
            Send-Json $ctx @{ backup = (Clear-Site) }
        }
        'POST backup' {
            Send-Json $ctx @{ backup = (Backup-Site) }
        }
        'POST fix-index' {
            Send-Json $ctx @{ redirect = (Ensure-Index) }
        }
        'POST open-folder' {
            $which = $req.QueryString['which']
            $target = $SiteDir
            if ($which -eq 'backups') { $target = $BackupDir }
            if ($which -eq 'base') { $target = $BaseDir }
            Start-Process explorer.exe -ArgumentList "`"$target`""
            Send-Json $ctx @{ ok = $true }
        }
        default { Send-Error $ctx 404 "Unbekannte Aktion: $method $action" }
    }
}

# --------------------------------------------------------------- Anfragen
function Invoke-Request($ctx) {
    $req = $ctx.Request
    $path = [Uri]::UnescapeDataString($req.Url.AbsolutePath)

    if ($path -eq '/_admin') { Send-Redirect $ctx '/_admin/'; return }
    if ($path -eq '/_admin/') {
        Send-Bytes $ctx 200 'text/html; charset=utf-8' ([IO.File]::ReadAllBytes($AdminFile))
        return
    }
    if ($path.StartsWith('/_api/')) {
        try { Invoke-Api $ctx $path.Substring(6) }
        catch { Send-Error $ctx 400 $_.Exception.Message }
        return
    }

    if ($req.HttpMethod -ne 'GET' -and $req.HttpMethod -ne 'HEAD') { Send-Text $ctx 405 'Nicht erlaubt.'; return }

    try { $full = Resolve-SitePath $path -AllowRoot } catch { $full = $null }
    if ($full -and (Test-Path -LiteralPath $full -PathType Container)) {
        if (-not $path.EndsWith('/')) { Send-Redirect $ctx ($req.Url.AbsolutePath + '/'); return }
        $full = Join-Path $full 'index.html'
    }
    if ($full -and (Test-Path -LiteralPath $full -PathType Leaf)) {
        Send-Bytes $ctx 200 (Get-Mime $full) ([IO.File]::ReadAllBytes($full))
        return
    }

    $safe = [Net.WebUtility]::HtmlEncode($path)
    $page = @"
<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nicht gefunden</title>
<body style="font-family:system-ui,sans-serif;max-width:560px;margin:15vh auto;padding:0 20px;color:#222">
<h1 style="font-size:28px">Seite nicht gefunden</h1>
<p>Die Datei <code>$safe</code> gibt es auf deiner Website (noch) nicht.</p>
<p><a href="/">Zur Startseite</a> &nbsp;&middot;&nbsp; <a href="/_admin/">Website bearbeiten</a></p>
</body></html>
"@
    Send-Text $ctx 404 $page 'text/html; charset=utf-8'
}

function Open-Browser([string]$url) {
    if ($NoBrowser) { return }
    try { Start-Process $url } catch { Write-Host "Bitte im Browser oeffnen: $url" }
}

# ------------------------------------------------------------------ Start
try { $Host.UI.RawUI.WindowTitle = "$SiteName - Webserver" } catch {}
$listener = $null
$Port = 0
foreach ($p in 8080..8099) {
    # Laeuft die Website schon? Dann nur den Browser oeffnen.
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri "http://localhost:$p/_api/ping"
        if ("$($r.Content)" -eq $Marker) {
            $u = "http://localhost:$p/"
            if ($Admin) { $u += '_admin/' }
            Open-Browser $u
            exit 0
        }
        continue   # Port gehoert einem anderen Programm
    } catch {}
    $l = New-Object Net.HttpListener
    $l.Prefixes.Add("http://localhost:$p/")
    try { $l.Start(); $listener = $l; $Port = $p; break } catch { $l.Close() }
}
if (-not $listener) {
    Write-Host 'Es wurde kein freier Port (8080-8099) gefunden. Bitte den PC neu starten und es erneut versuchen.' -ForegroundColor Red
    Read-Host 'Enter zum Schliessen'
    exit 1
}

$url = "http://localhost:$Port/"
Write-Host ''
Write-Host "  $SiteName laeuft!" -ForegroundColor Green
Write-Host ''
Write-Host "  Website ansehen:     $url"
Write-Host "  Website bearbeiten:  ${url}_admin/"
Write-Host "  Dateien liegen in:   $SiteDir"
Write-Host ''
Write-Host '  Dieses Fenster offen lassen (minimieren ist ok).' -ForegroundColor Yellow
Write-Host '  Fenster schliessen = Website ausschalten.' -ForegroundColor Yellow
Write-Host ''

if ($Admin) { Open-Browser "${url}_admin/" } else { Open-Browser $url }

try {
    while ($listener.IsListening) {
        $task = $listener.GetContextAsync()
        # In kleinen Schritten warten, damit Strg+C funktioniert.
        while (-not $task.AsyncWaitHandle.WaitOne(250)) {}
        $ctx = $task.GetAwaiter().GetResult()
        try {
            Invoke-Request $ctx
        } catch {
            Write-Host "Fehler bei $($ctx.Request.Url): $($_.Exception.Message)" -ForegroundColor Red
            try { Send-Text $ctx 500 "Fehler: $($_.Exception.Message)" } catch {}
        } finally {
            try { $ctx.Response.Close() } catch {}
        }
    }
} finally {
    $listener.Stop()
    $listener.Close()
}
