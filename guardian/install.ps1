<#
  Guardian-Installer für Windows -- für den angemeldeten Benutzer, ohne
  Administratorrechte. Gestartet wird er über install.bat / uninstall.bat.

  Was er tut, und nur das:
    1. Rust suchen. Fehlt es, fragt er, ob er den offiziellen Rust-Installer
       (rustup-init.exe von static.rust-lang.org) laden und starten soll.
    2. Guardian bauen: cargo build --release --locked
    3. guardian.exe nach %LOCALAPPDATA%\Programs\Guardian kopieren und den
       Ordner in den PATH des Benutzers eintragen (dort findet Jarvis es).
    4. Die YARA-Regeln aus rules\ in den Regelordner kopieren, den Guardian
       selbst meldet, und eine config.toml anlegen, falls noch keine da ist
       (Scan-Ordner: Downloads). Eine vorhandene Konfiguration bleibt, wie
       sie ist.
    5. Prüfen: "guardian --json status" muss geladene Regeln melden, und ein
       Probescan einer harmlosen Datei (ohne Quarantäne) muss sauber sein.
       Fertig meldet der Installer nur mit diesem Beleg.

  -Uninstall entfernt Programm und PATH-Eintrag. Konfiguration, Protokoll
  und Quarantäne bleiben liegen -- in der Quarantäne liegen deine Dateien.
#>
param(
    [switch]$Uninstall,
    # Wohin guardian.exe kommt. Vorgabe: %LOCALAPPDATA%\Programs\Guardian
    [string]$InstallDir = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # sonst lädt PowerShell 5.1 quälend langsam

$aufWindows = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$exeName = if ($aufWindows) { 'guardian.exe' } else { 'guardian' }
if (-not $InstallDir) {
    if ($aufWindows) {
        $InstallDir = [IO.Path]::Combine($env:LOCALAPPDATA, 'Programs', 'Guardian')
    } else {
        $InstallDir = [IO.Path]::Combine($HOME, '.local', 'bin')
    }
}
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$installiert = [IO.Path]::Combine($InstallDir, $exeName)


# ─────────────────────────────────────────────────────────────── Ausgabe ──
function Titel([string]$text) {
    Write-Host ''
    Write-Host "  $text"
    Write-Host ('  ' + ('=' * $text.Length))
}
function Schritt([string]$nr, [string]$text) {
    Write-Host ''
    Write-Host "  [$nr] $text" -ForegroundColor Cyan
}
function Ok([string]$text) { Write-Host "  [ok] $text" -ForegroundColor Green }
function Warnung([string]$text) { Write-Host "  [!]  $text" -ForegroundColor Yellow }


# ─────────────────────────────────────────────────────── Programme starten ──
function Starte([string]$exe, [string[]]$argumente) {
    # Fortschritt auf stderr ist bei cargo normal und kein Fehler.
    $vorher = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $exe @argumente | Out-Host
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $vorher
    }
}

function Frage-Guardian([string]$exe, [string[]]$befehl, [int[]]$erlaubt = @(0)) {
    # Guardian mit --json: genau ein JSON-Dokument auf stdout, Warnungen auf
    # stderr. Kein Raten an Textausgaben.
    $vorher = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $ausgabe = (& $exe --json @befehl) | Out-String
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $vorher
    }
    $antwort = $null
    try { $antwort = $ausgabe | ConvertFrom-Json } catch { <# kein JSON: unten erklärt #> }
    if ($null -ne $antwort -and $antwort.error) { throw "Guardian meldet: $($antwort.error)" }
    if ($null -eq $antwort) { throw "Guardian hat keine lesbare Antwort gegeben (Exit-Code $code)." }
    if ($erlaubt -notcontains $code) { throw "Guardian endete mit Exit-Code $code." }
    $antwort | Add-Member -NotePropertyName exit_code -NotePropertyValue $code
    return $antwort
}


# ──────────────────────────────────────────────────────────────────── Rust ──
function Finde-Cargo {
    $befehl = Get-Command cargo -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($befehl) { return $befehl.Path }
    # Direkt nach der Rust-Installation steht cargo noch nicht im PATH
    # dieses Fensters -- rustup legt es immer hierhin.
    $cargoHome = if ($env:CARGO_HOME) { $env:CARGO_HOME } else { [IO.Path]::Combine($HOME, '.cargo') }
    $kandidat = [IO.Path]::Combine($cargoHome, 'bin', $(if ($aufWindows) { 'cargo.exe' } else { 'cargo' }))
    if (Test-Path -LiteralPath $kandidat) { return $kandidat }
    return $null
}

function Installiere-Rust {
    if (-not $aufWindows) { throw 'Rust (cargo) fehlt. Installieren: https://rustup.rs' }
    Warnung 'Rust ist nicht installiert. Guardian wird aus dem Quellcode gebaut und braucht es.'
    Write-Host '       Ich kann den offiziellen Rust-Installer (rustup-init.exe) laden und starten.'
    Write-Host '       Dort die Vorgabe (1) nehmen. Fragt er nach den Visual Studio Build Tools:'
    Write-Host '       zustimmen -- ohne sie kann Windows nichts bauen.'
    $antwort = Read-Host '       Rust jetzt installieren? [J/n]'
    if ($antwort -match '^[nN]') {
        throw 'Ohne Rust kein Build. Rust gibt es unter https://rustup.rs -- danach install.bat erneut starten.'
    }
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'aarch64' } else { 'x86_64' }
    $url = "https://static.rust-lang.org/rustup/dist/$arch-pc-windows-msvc/rustup-init.exe"
    $datei = [IO.Path]::Combine($env:TEMP, 'rustup-init.exe')
    # Windows PowerShell 5.1 spricht ohne das nicht immer TLS 1.2.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    try {
        Invoke-WebRequest -Uri $url -OutFile $datei -UseBasicParsing
    } catch {
        throw "Download von $url fehlgeschlagen: $($_.Exception.Message)"
    }
    # Eigener Prozess im selben Fenster: rustup-init fragt interaktiv nach.
    $prozess = Start-Process -FilePath $datei -Wait -NoNewWindow -PassThru
    Remove-Item -LiteralPath $datei -ErrorAction SilentlyContinue
    if ($prozess.ExitCode -ne 0) { throw "Der Rust-Installer endete mit Exit-Code $($prozess.ExitCode)." }
}

function Baue-Guardian([string]$cargo) {
    $zielOrdner = [IO.Path]::Combine($PSScriptRoot, 'target')
    $code = Starte $cargo @('build', '--release', '--locked',
        '--manifest-path', [IO.Path]::Combine($PSScriptRoot, 'Cargo.toml'),
        '--target-dir', $zielOrdner)
    if ($code -ne 0) {
        throw ("cargo build ist fehlgeschlagen (Exit-Code $code), Details stehen oben. " +
               "Steht dort 'link.exe not found', fehlen die Visual Studio Build Tools mit " +
               "'Desktopentwicklung mit C++': https://visualstudio.microsoft.com/de/visual-cpp-build-tools/")
    }
    $gebaut = [IO.Path]::Combine($zielOrdner, 'release', $exeName)
    if (-not (Test-Path -LiteralPath $gebaut)) { throw "cargo meldet Erfolg, aber $gebaut fehlt." }
    return $gebaut
}


# ───────────────────────────────────────────────────────── PATH (Windows) ──
function Lies-BenutzerPath {
    $schluessel = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
    try {
        # Roh lesen: Einträge wie %USERPROFILE%\... bleiben so erhalten.
        return [string]$schluessel.GetValue('Path', '',
            [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
    } finally { $schluessel.Close() }
}

function Schreibe-BenutzerPath([string]$wert) {
    $schluessel = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
    try {
        if ($wert) {
            $schluessel.SetValue('Path', $wert, [Microsoft.Win32.RegistryValueKind]::ExpandString)
        } else {
            $schluessel.DeleteValue('Path', $false)
        }
    } finally { $schluessel.Close() }
    Melde-Umgebungsaenderung
}

function Melde-Umgebungsaenderung {
    # Explorer (und damit jedes neu geöffnete Fenster) übernimmt den neuen
    # PATH erst nach dieser Nachricht -- sonst erst nach dem Neuanmelden.
    try {
        if (-not ('Guardian.Umgebung' -as [type])) {
            Add-Type -Namespace Guardian -Name Umgebung -MemberDefinition @'
[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam,
    string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
'@
        }
        $ergebnis = [UIntPtr]::Zero
        # HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG, 5 s
        [void][Guardian.Umgebung]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero,
            'Environment', 2, 5000, [ref]$ergebnis)
    } catch {
        Warnung 'Windows ließ sich nicht über den neuen PATH benachrichtigen -- einmal ab- und wieder anmelden.'
    }
}

function Gleicher-Ordner([string]$eintrag, [string]$ordner) {
    $eintrag = [Environment]::ExpandEnvironmentVariables($eintrag.Trim().Trim('"')).TrimEnd('\')
    return $eintrag -ieq $ordner.TrimEnd('\')
}

function Trage-InPathEin([string]$ordner) {
    $eintraege = @((Lies-BenutzerPath) -split ';' | Where-Object { $_ })
    if (@($eintraege | Where-Object { Gleicher-Ordner $_ $ordner }).Count -gt 0) { return $false }
    Schreibe-BenutzerPath ((@($eintraege) + $ordner) -join ';')
    return $true
}

function Entferne-AusPath([string]$ordner) {
    $eintraege = @((Lies-BenutzerPath) -split ';' | Where-Object { $_ })
    $rest = @($eintraege | Where-Object { -not (Gleicher-Ordner $_ $ordner) })
    if ($rest.Count -eq $eintraege.Count) { return $false }
    Schreibe-BenutzerPath ($rest -join ';')
    return $true
}


# ─────────────────────────────────────────────── Regeln und Konfiguration ──
function Kopiere-Regeln([string]$regelOrdner) {
    $quelle = [IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot, 'rules'))
    $ziel = [IO.Path]::GetFullPath($regelOrdner)
    if ($quelle.TrimEnd('\', '/') -ieq $ziel.TrimEnd('\', '/')) {
        Ok "Regeln: Guardian liest sie direkt aus $quelle"
        return
    }
    $anzahl = 0
    foreach ($datei in Get-ChildItem -LiteralPath $quelle -Recurse -File) {
        if (@('.yar', '.yara') -notcontains $datei.Extension.ToLowerInvariant()) { continue }
        $relativ = $datei.FullName.Substring($quelle.Length).TrimStart('\', '/')
        $dateiZiel = [IO.Path]::Combine($ziel, $relativ)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dateiZiel) | Out-Null
        Copy-Item -LiteralPath $datei.FullName -Destination $dateiZiel -Force
        $anzahl++
    }
    Ok "$anzahl Regeldatei(en) nach $ziel kopiert"
}

function Finde-Downloads {
    if ($aufWindows) {
        # Der echte Downloads-Ordner -- er kann verschoben sein (OneDrive, D:\ ...).
        try {
            $ordner = (Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders').'{374DE290-123F-4565-9164-39C4925E467B}'
            if ($ordner) {
                $ordner = [Environment]::ExpandEnvironmentVariables($ordner)
                if (Test-Path -LiteralPath $ordner -PathType Container) { return $ordner }
            }
        } catch { <# Eintrag fehlt: dann der übliche Ort #> }
    }
    $vermutet = [IO.Path]::Combine($HOME, 'Downloads')
    if (Test-Path -LiteralPath $vermutet -PathType Container) { return $vermutet }
    return $null
}

function Als-TomlText([string]$text) {
    return '"' + ($text -replace '\\', '\\' -replace '"', '\"') + '"'
}

function Lege-Konfiguration-an([string]$pfad) {
    $zeilen = @(
        '# Angelegt vom Guardian-Installer. Was hier fehlt, nimmt Guardian aus seinen',
        '# Vorgaben (Regeln, Quarantäne und Protokoll liegen neben dieser Datei).',
        '#',
        '# scan_roots: die Ordner, die "guardian scan --full" durchsucht -- in Jarvis',
        '# "prüf alle Guardian-Ordner". Weitere Ordner einfach ergänzen.'
    )
    $downloads = Finde-Downloads
    if ($downloads) {
        $zeilen += "scan_roots = [$(Als-TomlText $downloads)]"
    } else {
        $zeilen += 'scan_roots = []'
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pfad) | Out-Null
    # Ohne BOM: Guardian liest die Datei als reines UTF-8.
    [IO.File]::WriteAllText($pfad, (($zeilen -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding $false))
    Ok "Konfiguration angelegt: $pfad"
    if ($downloads) {
        Ok "Scan-Ordner: $downloads"
    } else {
        Warnung "Keinen Downloads-Ordner gefunden -- scan_roots in $pfad selbst eintragen."
    }
}


# ─────────────────────────────────────────────────────────── Installieren ──
function Installiere {
    Titel 'Guardian -- Installation'

    Schritt '1/5' 'Rust'
    $cargo = Finde-Cargo
    if (-not $cargo) {
        Installiere-Rust
        $cargo = Finde-Cargo
        if (-not $cargo) {
            throw 'Rust ist installiert, aber cargo ist nicht auffindbar -- ein neues Fenster öffnen und install.bat erneut starten.'
        }
    }
    Ok "cargo: $cargo"

    Schritt '2/5' 'Guardian bauen (beim ersten Mal dauert das einige Minuten)'
    $gebaut = Baue-Guardian $cargo
    Ok "gebaut: $gebaut"

    Schritt '3/5' 'Programm einrichten'
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    try {
        Copy-Item -LiteralPath $gebaut -Destination $installiert -Force
    } catch {
        throw "$installiert lässt sich nicht überschreiben -- läuft gerade ein Guardian-Scan (z. B. über Jarvis)? ($($_.Exception.Message))"
    }
    if ((Get-FileHash -LiteralPath $gebaut).Hash -ne (Get-FileHash -LiteralPath $installiert).Hash) {
        throw "Die Kopie in $installiert weicht vom Build ab."
    }
    Ok "installiert: $installiert"
    if ($aufWindows) {
        if (Trage-InPathEin $InstallDir) {
            Ok "$InstallDir in deinen PATH eingetragen (gilt für neu geöffnete Fenster)"
        } else {
            Ok "$InstallDir steht schon in deinem PATH"
        }
    } elseif (($env:PATH -split [IO.Path]::PathSeparator) -notcontains $InstallDir) {
        Warnung "$InstallDir steht nicht in deinem PATH -- eintragen, damit 'guardian' überall geht."
    }

    Schritt '4/5' 'Regeln und Konfiguration'
    # Guardian selbst sagt, wo seine Konfiguration und sein Regelordner sind --
    # der Installer rechnet das nicht nach.
    try {
        $status = Frage-Guardian $installiert @('status')
    } catch {
        throw "Guardian startet nicht: $($_.Exception.Message)"
    }
    Kopiere-Regeln $status.rules_dir
    if (Test-Path -LiteralPath $status.config) {
        Ok "Konfiguration vorhanden, bleibt wie sie ist: $($status.config)"
    } else {
        Lege-Konfiguration-an $status.config
    }

    Schritt '5/5' 'Prüfen'
    $status = Frage-Guardian $installiert @('status')
    foreach ($warnung in @($status.warnings)) { if ($warnung) { Warnung "Guardian: $warnung" } }
    if ([int]$status.rule_files -lt 1) {
        throw "Guardian startet, hat aber keine YARA-Regeln geladen (Regelordner: $($status.rules_dir))."
    }
    Ok ("Guardian läuft: $($status.rule_files) Regeldatei(en) geladen, " +
        "$($status.hash_db_entries) bekannte Hashes, $($status.quarantine_entries) Einträge in Quarantäne")
    $probe = Frage-Guardian $installiert @('scan', '--no-quarantine', $installiert) @(0, 1)
    if ($probe.exit_code -ne 0) {
        $befund = @($probe.results)[0]
        throw ("Der Probescan hält die eigene $exeName für eine Bedrohung (Score $($befund.score): " +
               "$(@($befund.reasons) -join '; ')). Das ist ein Fehlalarm der Regeln.")
    }
    if ([int]$probe.scanned -ne 1 -or @($probe.failed).Count -gt 0) {
        throw "Der Probescan hat $installiert nicht geprüft ($($probe.scanned) geprüft, $(@($probe.failed).Count) fehlgeschlagen)."
    }
    Ok 'Probescan einer harmlosen Datei: geprüft, nichts gefunden, nichts verschoben'

    Write-Host ''
    Write-Host '  Guardian ist installiert.' -ForegroundColor Green
    Write-Host "  - Konfiguration: $($status.config)"
    Write-Host '  - In einem NEUEN Fenster:  guardian status   /   guardian scan <Ordner>'
    Write-Host '  - Jarvis neu starten: dann stehen die guardian.*-Werkzeuge auf "bereit".'
    Write-Host '  - Guardian prüft nur, wenn du oder Jarvis es aufrufen -- kein Echtzeitschutz.'
    Write-Host '    Windows Defender also unbedingt anlassen.'
    Write-Host '  - Entfernen: uninstall.bat'
}


# ─────────────────────────────────────────────────────────── Deinstallieren ──
function Deinstalliere {
    Titel 'Guardian -- Deinstallation'

    $datenOrdner = $null
    $quarantaene = 0
    if (Test-Path -LiteralPath $installiert) {
        # Vorher fragen, was liegen bleibt -- danach gibt es kein guardian mehr.
        try {
            $status = Frage-Guardian $installiert @('status')
            $datenOrdner = Split-Path -Parent $status.config
            $quarantaene = [int]$status.quarantine_entries
        } catch { <# startet nicht (z. B. kaputte Konfiguration) -- entfernen geht trotzdem #> }
        try {
            Remove-Item -LiteralPath $installiert -Force
        } catch {
            throw "$installiert lässt sich nicht löschen -- läuft gerade ein Guardian-Scan? ($($_.Exception.Message))"
        }
        Ok "entfernt: $installiert"
        if ((Split-Path -Leaf $InstallDir) -eq 'Guardian' -and
            -not (Get-ChildItem -LiteralPath $InstallDir -Force)) {
            Remove-Item -LiteralPath $InstallDir
        }
    } else {
        Ok "war nicht installiert: $installiert"
    }
    if ($aufWindows) {
        if (Entferne-AusPath $InstallDir) {
            Ok "$InstallDir aus deinem PATH entfernt"
        }
    }

    if ($datenOrdner) {
        Write-Host ''
        Warnung "Absichtlich NICHT gelöscht: $datenOrdner (Konfiguration, Regeln, Protokoll, Quarantäne)."
        if ($quarantaene -gt 0) {
            Warnung "In der Quarantäne liegen $quarantaene Datei(en) -- das sind deine Dateien."
            Write-Host "       Zurückholen geht mit dem Build im Repo:  guardian\target\release\$exeName quarantine list"
        }
        Write-Host '       Wer auch das nicht mehr braucht, löscht den Ordner selbst.'
    }
    Write-Host ''
    Write-Host '  Guardian ist deinstalliert.' -ForegroundColor Green
}


try {
    if ($Uninstall) { Deinstalliere } else { Installiere }
} catch {
    Write-Host ''
    Write-Host "  [X]  $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ''
    Write-Host '  Abgebrochen. Den Punkt mit [X] beheben und das Skript erneut starten.' -ForegroundColor Red
    exit 1
}
exit 0
