# Tutor installieren (Windows): legt den Ordner "Tutor" und "Tutor.exe" auf den Desktop.
#
#   Einzeiler (PowerShell):
#   irm https://raw.githubusercontent.com/Samu2134213412/ai/ccr-b87b8acb-etedpt/tutor/install.ps1 | iex
#
# Ablauf: Quellcode laden -> Ordner auf den Desktop -> Tutor.exe aus dem GitHub-Release laden,
# falls es dort eine gibt, sonst selbst bauen (installiert bei Bedarf Node.js per winget).
# Optionale Umgebungsvariablen: TUTOR_REPO, TUTOR_BRANCH, TUTOR_PREBUILT (fertige .exe nutzen).

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$Repo   = if ($env:TUTOR_REPO)   { $env:TUTOR_REPO }   else { "Samu2134213412/ai" }
$Branch = if ($env:TUTOR_BRANCH) { $env:TUTOR_BRANCH } else { "ccr-b87b8acb-etedpt" }

function Say($text)  { Write-Host ">> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "FEHLER: $text" -ForegroundColor Red; throw $text }

$desktop = [Environment]::GetFolderPath("Desktop")      # findet auch einen OneDrive-Desktop
$target  = Join-Path $desktop "Tutor"
$work    = Join-Path $env:TEMP ("tutor-install-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $work | Out-Null

try {
    # 1. Quellcode: lokaler Ordner (wenn das Skript aus einem Tutor-Ordner startet) oder GitHub
    $src = $null
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "desktop\package.json"))) {
        $src = $PSScriptRoot
        Say "Nutze lokalen Ordner: $src"
    } else {
        Say "Lade Tutor von GitHub ($Repo, $Branch) ..."
        $zip = Join-Path $work "tutor.zip"
        Invoke-WebRequest -Uri "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $work -Force
        $root = Get-ChildItem -Path $work -Directory | Where-Object { Test-Path (Join-Path $_.FullName "tutor\desktop\package.json") } | Select-Object -First 1
        if (-not $root) { Fail "Im Download wurde kein Tutor-Ordner gefunden (Branch '$Branch' vorhanden?)." }
        $src = Join-Path $root.FullName "tutor"
    }

    # 2. Ordner auf den Desktop (vorhandene Daten bleiben, Build-Reste werden nicht kopiert)
    $same = (Test-Path $target) -and ((Resolve-Path $target).Path.TrimEnd('\') -eq (Resolve-Path $src).Path.TrimEnd('\'))
    if (-not $same) {
        Say "Kopiere nach $target ..."
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        & robocopy $src $target /E /XD node_modules dist www .git __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { Fail "Kopieren fehlgeschlagen (robocopy $LASTEXITCODE)." }
    }

    # 3. Tutor.exe besorgen
    $exe = $null
    if ($env:TUTOR_PREBUILT -and (Test-Path $env:TUTOR_PREBUILT)) {
        $exe = $env:TUTOR_PREBUILT
        Say "Nutze fertige Datei: $exe"
    }
    if (-not $exe) {
        try {
            Say "Suche fertige Tutor.exe im GitHub-Release ..."
            $releases = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases" -Headers @{ "User-Agent" = "tutor-installer" }
            $asset = $releases | Where-Object { $_.tag_name -like "tutor-desktop-v*" } |
                ForEach-Object { $_.assets } | Where-Object { $_.name -eq "Tutor.exe" } | Select-Object -First 1
            if ($asset) {
                $exe = Join-Path $work "Tutor.exe"
                Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $exe -UseBasicParsing
            }
        } catch { $exe = $null }
    }
    if (-not $exe) {
        Say "Keine fertige Datei gefunden - baue Tutor.exe selbst (dauert einige Minuten) ..."
        if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
            if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
                Fail "Node.js fehlt. Bitte von https://nodejs.org installieren und diesen Befehl erneut ausfuehren."
            }
            Say "Installiere Node.js ..."
            & winget install -e --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements | Out-Null
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
            if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
                Fail "Node.js wurde installiert, ist aber noch nicht im PATH. Bitte PowerShell neu oeffnen und den Befehl wiederholen."
            }
        }
        $env:CSC_IDENTITY_AUTO_DISCOVERY = "false"      # ohne Signierzertifikat bauen
        Push-Location (Join-Path $target "desktop")
        try {
            & npm install --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { Fail "npm install ist fehlgeschlagen." }
            & npm run dist:exe
            if ($LASTEXITCODE -ne 0) { Fail "Bauen ist fehlgeschlagen." }
        } finally { Pop-Location }
        $exe = Join-Path $target "desktop\dist\Tutor.exe"
        if (-not (Test-Path $exe)) { Fail "Tutor.exe wurde nicht erzeugt." }
    }

    # 4. Tutor.exe auf den Desktop und in den Ordner
    Copy-Item -Path $exe -Destination (Join-Path $desktop "Tutor.exe") -Force
    Copy-Item -Path $exe -Destination (Join-Path $target "Tutor.exe") -Force

    Write-Host ""
    Write-Host "Fertig! Auf dem Desktop liegen jetzt:" -ForegroundColor Green
    Write-Host "  - Tutor.exe   (Doppelklick zum Starten)"
    Write-Host "  - Tutor\      (Ordner mit allem Drumherum, Anleitung: Tutor\README.md)"
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "Noch noetig: Ollama (https://ollama.com/download), danach in der Eingabeaufforderung:" -ForegroundColor Yellow
        Write-Host "  ollama pull qwen2.5:32b      (kleiner PC: qwen2.5:7b)"
        Write-Host "  ollama pull qwen2.5vl:7b     (zum Lesen deiner Seiten)"
    }
} finally {
    Remove-Item -Path $work -Recurse -Force -ErrorAction SilentlyContinue
}
