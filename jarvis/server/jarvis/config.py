"""Konfiguration. Eine JSON-Datei neben der Datenbank, keine Umgebungsvariablen-Jagd."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def default_home() -> Path:
    return Path(os.environ.get("JARVIS_HOME") or (Path.home() / ".jarvis"))


def default_roots() -> list[str]:
    """Was Jarvis anfassen darf, bevor der Nutzer etwas anderes sagt.

    Bewusst eng: der Desktop und ein eigener Arbeitsordner. Nicht das ganze
    Benutzerverzeichnis, und schon gar nicht das Laufwerk.
    """
    home = Path.home()
    picks = [home / "Desktop", home / "Schreibtisch", home / "Documents" / "Jarvis"]
    return [str(p) for p in picks if p.is_dir()] or [str(default_home() / "arbeitsbereich")]


@dataclass
class ShellConfig:
    enabled: bool = False
    allowlist: list[str] = field(default_factory=list)
    cwd: str = ""
    timeout: int = 60


@dataclass
class CodePilotConfig:
    url: str = "http://127.0.0.1:8765"
    token: str = ""
    project_id: str = ""
    timeout: int = 900
    #: Läuft CodePilot bei einer Codeaufgabe nicht, startet Jarvis es selbst.
    #: Bewusst erst dann und nicht beim Hochfahren: das Code-Modell belegt
    #: 18 GB VRAM, die sonst dem Chat-Modell fehlen.
    autostart: bool = True
    #: Leer heißt: CodePilot im Repo neben jarvis/ suchen.
    start_dir: str = ""
    start_timeout: int = 90


@dataclass
class Config:
    # -- Netz ---------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8770
    #: Leer lassen heißt: nur von diesem Rechner erreichbar und ohne Token.
    #: Sobald host nicht loopback ist, wird ein Token erzwungen.
    token: str = ""

    # -- Modell -------------------------------------------------------------
    ollama_url: str = "http://127.0.0.1:11434"
    #: Mittelweg auf 24 GB VRAM: bleibt nicht zwingend neben dem Coder geladen,
    #: aber deutlich verlässlicher bei Werkzeugaufrufen als ein 3B-Modell.
    #: Siehe jarvis/README.md für die Abwägung.
    model: str = "qwen3:14b"
    context_length: int = 8192
    temperature: float = 0.3
    max_tool_rounds: int = 6
    request_timeout: int = 120

    # -- Arbeitsbereich -----------------------------------------------------
    roots: list[str] = field(default_factory=default_roots)
    shell: ShellConfig = field(default_factory=ShellConfig)
    codepilot: CodePilotConfig = field(default_factory=CodePilotConfig)

    # -- Ablage -------------------------------------------------------------
    home: str = field(default_factory=lambda: str(default_home()))

    @property
    def db_path(self) -> Path:
        return Path(self.home) / "gedaechtnis.sqlite3"

    @property
    def config_path(self) -> Path:
        return Path(self.home) / "jarvis.json"

    @property
    def is_loopback(self) -> bool:
        return self.host in {"127.0.0.1", "localhost", "::1"}

    # -- laden / speichern --------------------------------------------------
    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        target = Path(path) if path else (default_home() / "jarvis.json")
        if not target.is_file():
            return cls()
        try:
            # utf-8-sig statt utf-8: Windows-PowerShell schreibt mit
            # "Set-Content -Encoding UTF8" eine BOM an den Dateianfang, und
            # der strenge utf-8-Decoder stolpert darüber. utf-8-sig liest
            # beide Varianten -- mit BOM und ohne.
            raw = json.loads(target.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Konfiguration nicht lesbar: {target}\n  {exc}") from exc
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "Config":
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in (raw or {}).items() if k in known}
        if isinstance(data.get("shell"), dict):
            data["shell"] = ShellConfig(**{
                k: v for k, v in data["shell"].items()
                if k in {f.name for f in fields(ShellConfig)}})
        if isinstance(data.get("codepilot"), dict):
            data["codepilot"] = CodePilotConfig(**{
                k: v for k, v in data["codepilot"].items()
                if k in {f.name for f in fields(CodePilotConfig)}})
        return cls(**data)

    def save(self) -> Path:
        target = self.config_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False),
                          encoding="utf-8")
        return target

    def validate(self) -> list[str]:
        """Probleme, die der Nutzer kennen muss. Keine stillen Annahmen."""
        problems: list[str] = []
        if not self.is_loopback and not self.token:
            problems.append(
                f"host ist '{self.host}', also aus dem Netz erreichbar, aber es "
                "ist kein token gesetzt. Setze ein Token oder binde auf 127.0.0.1.")
        if not self.roots:
            problems.append("roots ist leer — Jarvis darf dann keine Datei anfassen.")
        if self.shell.enabled and not self.shell.allowlist:
            problems.append(
                "shell.enabled ist an, aber die Allowlist ist leer. Es läuft "
                "dadurch kein Befehl; trage die erlaubten Programme ein.")
        return problems
