"""Programme starten — das Werkzeug mit dem größten Schadenspotenzial.

Ein Assistent, der beliebige Befehle auf dem eigenen Rechner ausführt, ist genau
das, was hier gewollt ist. Trotzdem ist der Standard **aus**, und zwar aus einem
konkreten Grund: ein Modell, das unzuverlässig Werkzeuge aufruft, ruft sie auch
unzuverlässig *richtig* auf. Bis das Chat-Modell steht, soll ein Fehlgriff keine
Festplatte kosten.

Drei Absicherungen:

* **Aus per Voreinstellung.** ``shell.enabled`` muss bewusst gesetzt werden.
* **Keine Shell.** ``shell=True`` gibt es hier nicht, also auch keine Ketten mit
  ``&&``, ``|``, ``;`` oder ``$()``. Der Befehl wird mit ``shlex`` zerlegt und
  das Programm direkt gestartet.
* **Allowlist.** Nur ausdrücklich eingetragene Programme laufen. Leere Liste
  heißt: keines.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from .base import Tool, ToolError, ToolResult

DEFAULT_TIMEOUT = 60
MAX_OUTPUT = 20_000

#: Ein vernünftiger Startpunkt: lesende Werkzeuge und Testläufe.
SUGGESTED_ALLOWLIST = [
    "python", "python3", "py", "pip", "pytest",
    "git", "node", "npm", "ollama",
    "echo", "where", "which", "dir", "ls", "cat", "type",
]


class ShellPolicy:
    """Was ausgeführt werden darf und was nicht."""

    def __init__(self, enabled: bool = False, allowlist: list[str] | None = None,
                 cwd: str | Path | None = None, timeout: int = DEFAULT_TIMEOUT):
        self.enabled = bool(enabled)
        self.allowlist = {a.strip().lower() for a in (allowlist or []) if a.strip()}
        self.cwd = Path(cwd).expanduser().resolve() if cwd else None
        self.timeout = max(1, min(int(timeout or DEFAULT_TIMEOUT), 600))

    def check(self, argv: list[str]) -> str:
        if not self.enabled:
            raise ToolError(
                "Befehle auszuführen ist abgeschaltet. Einschalten in der "
                "Konfiguration unter shell.enabled, zusammen mit einer "
                "Allowlist der erlaubten Programme.")
        if not argv:
            raise ToolError("Es wurde kein Befehl angegeben.")
        # Beide Trenner, unabhängig von der Plattform: ein Windows-Pfad muss
        # auch dann korrekt zerlegt werden, wenn der Server auf Linux läuft.
        program = re.split(r"[\\/]", argv[0])[-1].lower()
        program = program[:-4] if program.endswith(".exe") else program
        if not self.allowlist:
            raise ToolError(
                "Die Allowlist ist leer, also ist kein Programm freigegeben. "
                f"Vorschlag für den Anfang: {', '.join(SUGGESTED_ALLOWLIST)}")
        if program not in self.allowlist:
            raise ToolError(
                f"'{program}' steht nicht auf der Allowlist. Erlaubt sind: "
                f"{', '.join(sorted(self.allowlist))}")
        return program


def build(policy: ShellPolicy) -> list[Tool]:

    def run_command(command: str, cwd: str = "", timeout: int = 0) -> ToolResult:
        try:
            # posix=False auf Windows, damit Backslashes in Pfaden erhalten bleiben.
            argv = shlex.split(command or "", posix=os.name != "nt")
        except ValueError as exc:
            raise ToolError(f"Befehl nicht zerlegbar: {exc}") from exc
        argv = [a.strip('"') for a in argv]
        program = policy.check(argv)

        workdir = Path(cwd).expanduser() if cwd else policy.cwd
        if workdir and not workdir.is_dir():
            raise ToolError(f"Arbeitsverzeichnis existiert nicht: {workdir}")
        limit = max(1, min(int(timeout or policy.timeout), 600))

        try:
            proc = subprocess.run(  # noqa: S603 - Allowlist geprüft, keine Shell
                argv, capture_output=True, text=True, timeout=limit,
                cwd=str(workdir) if workdir else None, shell=False,
                encoding="utf-8", errors="replace")
        except FileNotFoundError:
            raise ToolError(f"Programm nicht gefunden: {argv[0]}") from None
        except subprocess.TimeoutExpired:
            raise ToolError(f"Abgebrochen: '{program}' lief länger als {limit} s.") from None
        except OSError as exc:
            raise ToolError(f"Start fehlgeschlagen: {exc}") from exc

        out = (proc.stdout or "")[:MAX_OUTPUT]
        err = (proc.stderr or "")[:MAX_OUTPUT]
        ok = proc.returncode == 0
        evidence = {"befehl": " ".join(argv), "exit_code": proc.returncode,
                    "arbeitsverzeichnis": str(workdir) if workdir else "(Standard)"}
        body = out if not err else (f"{out}\n--- stderr ---\n{err}" if out else err)
        return ToolResult(
            tool="run_command", ok=ok,
            summary=(f"'{program}' beendet mit Exit-Code {proc.returncode}"
                     if ok else
                     f"'{program}' ist mit Exit-Code {proc.returncode} fehlgeschlagen"),
            evidence=evidence, payload=body.strip() or "(keine Ausgabe)")

    return [
        Tool("run_command",
             "Führt ein Programm aus der Allowlist aus und gibt Exit-Code und "
             "Ausgabe zurück. Keine Shell: Verkettungen mit && oder | gehen nicht.",
             {"type": "object",
              "properties": {
                  "command": {"type": "string", "description": "Programm mit Argumenten"},
                  "cwd": {"type": "string", "description": "Arbeitsverzeichnis"},
                  "timeout": {"type": "integer", "description": "Sekunden"}},
              "required": ["command"]},
             run_command, mutating=True),
    ]
