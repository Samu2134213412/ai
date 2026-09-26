"""Konfiguration. Eine JSON-Datei neben der Datenbank, keine Umgebungsvariablen-Jagd."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .autonomy import AutonomyLevel


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
class CodeConfig:
    """Der Code-Modus (siehe ``coder.py``).

    Früher lief er über CodePilot Remote: Jarvis -> HTTP -> CodePilot ->
    Claude Code -> Ollama. Das waren drei Dienste zwischen der Frage und dem
    Modell, von denen jeder einzeln laufen und eingerichtet sein musste --
    und wenn einer davon nicht lief, konnte Jarvis gar nichts. Jetzt spricht
    Jarvis das Code-Modell direkt über Ollama an, mit seinen eigenen
    Werkzeugen, seinem eigenen Permission-System und seiner eigenen
    Undo-Historie.
    """

    #: Das Modell für Code. Bewusst ein anderes als ``Config.model``: es darf
    #: größer und langsamer sein, weil es nur für Code-Aufträge geladen wird.
    #: Leer heißt: dasselbe Modell wie im Chat benutzen.
    model: str = "qwen3-coder:30b"
    #: Werkzeugrunden je Auftrag. Mehr als im Chat, weil ein Code-Auftrag
    #: typischerweise erst liest, dann schreibt, dann prüft.
    max_rounds: int = 14
    #: Niedriger als im Chat: bei Code ist Erfindungsreichtum keine Tugend.
    temperature: float = 0.1
    #: Code-Modelle sind groß und werden beim ersten Aufruf erst geladen.
    timeout: int = 600
    #: Nach Änderungen automatisch nachprüfen (Syntax der geänderten Dateien).
    #: Das ist die Verification-Engine-Idee aus Autonomy V1, angewendet auf
    #: Code: ein Modell, das "fertig" sagt, ist kein Beleg.
    auto_check: bool = True


@dataclass
class PermissionConfig:
    """Regeln des Permission-Systems (``permissions.py``) -- innerhalb der
    nicht verhandelbaren Grenzen: SAFE ist immer automatisch erlaubt,
    CRITICAL verlangt immer eine Bestätigung, und keines von beiden steht
    hier als Feld, damit es nicht wegkonfigurierbar ist."""

    confirm_read: bool = False
    confirm_write: bool = True
    confirm_system: bool = True
    confirmation_timeout: float = 300.0


@dataclass
class WhisperConfig:
    #: Leer heißt: Speech-to-Text ist aus. Jarvis bringt keinen eigenen
    #: Schlüssel mit -- der Nutzer trägt seinen eigenen ein (siehe /api/whisper/key).
    api_key: str = ""
    model: str = "whisper-1"
    timeout: int = 30


@dataclass
class SearchConfig:
    """Web-Suche (``search.web``) -- dasselbe Prinzip wie bei Whisper: Jarvis
    bringt keinen eigenen Schlüssel oder Dienst mit, leer heißt aus. Bevorzugt
    eine selbst gehostete SearXNG-Instanz (kein Schlüssel, keine dritte
    Partei, passt zum Rest des Projekts); ersatzweise die Brave Search API
    (Schlüssel nötig, aber ohne eigene Infrastruktur)."""
    searxng_url: str = ""
    brave_api_key: str = ""
    timeout: int = 15


@dataclass
class GuardianConfig:
    """Der Virenschutz Guardian (``../guardian``, eigenes Rust-Projekt) --
    Jarvis ruft sein Programm auf, statt einen zweiten Scanner nachzubauen
    (siehe ``tools/packs/guardian.py``)."""
    #: Pfad zur ``guardian``-Datei. Leer heißt: erst im PATH suchen, dann im
    #: gebauten Repo-Ordner (``guardian/target/release`` bzw. ``debug``).
    binary: str = ""
    #: Guardians eigene config.toml. Leer heißt: Guardians Vorgabe
    #: (``%PROGRAMDATA%\\Guardian\\config.toml`` bzw. ``~/.guardian``).
    config: str = ""
    #: Sekunden, die ein Scan höchstens dauern darf -- ein ganzer Ordner mit
    #: vielen Dateien braucht deutlich länger als die übrigen Befehle.
    scan_timeout: int = 900


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
    #: Ein zweites, kleineres Modell für einfache Fragen ohne Werkzeugbedarf
    #: (siehe ``complexity.py``). Leer heißt: aus -- jede Nachricht geht ans
    #: Hauptmodell, wie bisher. Absichtlich kein Standardwert: ein zweites
    #: Modell ist ein zusätzlicher Download, den niemand ungefragt bekommt
    #: (Punkt 55 der Aufgabenstellung).
    fast_model: str = ""
    context_length: int = 8192
    temperature: float = 0.3
    max_tool_rounds: int = 6
    request_timeout: int = 120

    # -- Arbeitsbereich -----------------------------------------------------
    roots: list[str] = field(default_factory=default_roots)
    shell: ShellConfig = field(default_factory=ShellConfig)
    code: CodeConfig = field(default_factory=CodeConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    guardian: GuardianConfig = field(default_factory=GuardianConfig)
    permissions: PermissionConfig = field(default_factory=PermissionConfig)
    #: Wie viel Eigeninitiative Jarvis nehmen darf (siehe autonomy.py).
    #: 2 ist "ein sinnvoller mittlerer Level", wie gefordert: normale
    #: Werkzeugregeln, aber noch keine eigenständige Zielverfolgung.
    autonomy_level: int = int(AutonomyLevel.LOCAL_ACTIONS)

    # -- Ablage -------------------------------------------------------------
    home: str = field(default_factory=lambda: str(default_home()))

    @property
    def db_path(self) -> Path:
        return Path(self.home) / "gedaechtnis.sqlite3"

    @property
    def audit_db_path(self) -> Path:
        return Path(self.home) / "protokoll.sqlite3"

    @property
    def undo_db_path(self) -> Path:
        return Path(self.home) / "undo.sqlite3"

    @property
    def task_db_path(self) -> Path:
        return Path(self.home) / "aufgaben.sqlite3"

    @property
    def goal_db_path(self) -> Path:
        return Path(self.home) / "ziele.sqlite3"

    @property
    def decision_db_path(self) -> Path:
        return Path(self.home) / "entscheidungen.sqlite3"

    @property
    def macro_db_path(self) -> Path:
        return Path(self.home) / "makros.sqlite3"

    @property
    def tool_history_db_path(self) -> Path:
        return Path(self.home) / "werkzeugverlauf.sqlite3"

    @property
    def config_path(self) -> Path:
        return Path(self.home) / "jarvis.json"

    @property
    def is_loopback(self) -> bool:
        return self.host in {"127.0.0.1", "localhost", "::1"}

    @property
    def autonomy(self) -> AutonomyLevel:
        """Ein ungültiger Wert wird zur sichersten Stufe, nicht zum Absturz --
        ``validate()`` macht den Nutzer trotzdem darauf aufmerksam."""
        try:
            return AutonomyLevel.from_value(self.autonomy_level)
        except ValueError:
            return AutonomyLevel.NONE

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
        if isinstance(data.get("code"), dict):
            data["code"] = CodeConfig(**{
                k: v for k, v in data["code"].items()
                if k in {f.name for f in fields(CodeConfig)}})
        if isinstance(data.get("whisper"), dict):
            data["whisper"] = WhisperConfig(**{
                k: v for k, v in data["whisper"].items()
                if k in {f.name for f in fields(WhisperConfig)}})
        if isinstance(data.get("search"), dict):
            data["search"] = SearchConfig(**{
                k: v for k, v in data["search"].items()
                if k in {f.name for f in fields(SearchConfig)}})
        if isinstance(data.get("guardian"), dict):
            data["guardian"] = GuardianConfig(**{
                k: v for k, v in data["guardian"].items()
                if k in {f.name for f in fields(GuardianConfig)}})
        if isinstance(data.get("permissions"), dict):
            data["permissions"] = PermissionConfig(**{
                k: v for k, v in data["permissions"].items()
                if k in {f.name for f in fields(PermissionConfig)}})
        return cls(**data)

    def save(self, path: str | Path | None = None) -> Path:
        """Schreibt die Konfiguration. Ohne Angabe nach ``config_path``.

        ``path`` ist für den Fall da, dass der Nutzer beim Start ausdrücklich
        ``--config <datei>`` angegeben hat: dann gehört die Datei dorthin und
        nicht ins Heimverzeichnis. Vorher landete sie in beiden Fällen in
        ``~/.jarvis`` -- die Angabe wurde beim Speichern stillschweigend
        ignoriert, und der Nutzer suchte anschließend eine Datei, die woanders
        lag.
        """
        target = Path(path) if path else self.config_path
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
        if self.code.max_rounds < 2:
            problems.append(
                f"code.max_rounds ist {self.code.max_rounds}. Unter 2 Runden kann "
                "der Code-Modus nicht einmal lesen und dann schreiben.")
        if not 0 <= self.autonomy_level <= 4:
            problems.append(
                f"autonomy_level ist {self.autonomy_level}, gültig ist 0-4 "
                "(siehe autonomy.py). Jarvis behandelt das wie Stufe 0.")
        return problems
