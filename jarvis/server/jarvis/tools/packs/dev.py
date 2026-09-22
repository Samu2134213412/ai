"""Tool Pack: Entwicklung -- Python, Node.js und projektübergreifende Helfer.

Bewusst **keine** Universal-Ausführung ("python.run_anything"). Ein
allgemeiner Codeausführer existiert schon (``run_command`` in ``shell.py``,
mit eigener Allowlist und eigener Freigabe) -- ihn hier zu verdoppeln würde
nur einen zweiten Weg schaffen, dieselbe Absicherung zu umgehen (Punkt 31:
"JARVIS darf niemals das Permission-System umgehen"). Was hier steht, sind
stattdessen benannte, feste Abläufe: den Interpreter fragen, Pakete
verwalten, Tests laufen lassen, ein bekanntes npm-Skript starten. Jeder
Unterprozess bekommt eine feste Kommandozeile; nur die Werte (Paketname,
Projektpfad, ...) kommen vom Modell.

Ausführung von Projektcode (Tests, npm-Skripte, `pip install` mit seinen
Build-Hooks) steht auf SYSTEM -- dasselbe Risiko wie ``run_command``, nur
enger gefasst. Reine Analyse (Syntaxprüfung, Paketliste, Lint) bleibt SAFE/READ.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ... import coder
from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, run_process
from ._base import DRY, INT, NO_PARAMS, flag, integer, ok, planned, params, table, text

MAX_OUTPUT = 20_000
TEST_TIMEOUT = 300.0

#: Schlüsselwörter, deren Wert in dev.env.list geschwärzt wird (Punkt 51:
#: Geheimnisse nie im Klartext protokollieren oder anzeigen).
_SECRET_KEY = ("token", "secret", "key", "password", "passwort", "pass",
              "auth", "credential", "api_key", "apikey", "geheim")


def _clip(value: str) -> str:
    value = value or ""
    if len(value) <= MAX_OUTPUT:
        return value
    return value[:MAX_OUTPUT] + f"\n… gekürzt ({len(value) - MAX_OUTPUT} weitere Zeichen)"


def _looks_like_secret(key: str) -> bool:
    lower = key.lower()
    return any(marker in lower for marker in _SECRET_KEY)


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    def interpreter(python: str = "") -> str:
        """Ohne Angabe: Jarvis' eigener Interpreter -- für reine Analyse
        unbedenklich. Verändernde Werkzeuge (Pakete installieren, venv
        anlegen) verlangen unten eine ausdrückliche Angabe, damit sie nicht
        aus Versehen Jarvis' eigene Laufzeitumgebung verändern.

        Anders als ein Datei-Pfad wird ein Interpreter-Pfad **nicht** auf
        den Arbeitsbereich beschränkt: er benennt ein auszuführendes
        Programm, kein Ziel zum Lesen/Schreiben -- derselbe Unterschied wie
        bei einer Git-URL. Ein Systemweiter Interpreter (z. B. Jarvis'
        eigener, ``sys.executable``) liegt so gut wie nie im Arbeitsbereich.
        Ein relativer Pfad ('venv/bin/python') bleibt trotzdem bequem
        gegen den Arbeitsbereich auflösbar."""
        if not python or not python.strip():
            return sys.executable
        wert = python.strip()
        pfad = Path(wert)
        if not pfad.is_absolute():
            pfad = ws.resolve(wert)
        if not pfad.is_file():
            raise ToolError(f"Python-Interpreter nicht gefunden: {pfad}")
        return str(pfad)

    def interpreter_required(python: str, feld: str = "python") -> str:
        wert = (python or "").strip()
        if not wert:
            raise ToolError(
                f"{feld} fehlt. Damit dieses Werkzeug nicht versehentlich Jarvis' "
                "eigene Laufzeitumgebung verändert, muss der Ziel-Interpreter "
                "ausdrücklich angegeben werden (z. B. der einer virtuellen Umgebung).")
        return interpreter(wert)

    def module_missing(stderr: str, modul: str) -> bool:
        # "python -m modul" ohne Anführungszeichen ("No module named modul"),
        # ein import innerhalb von Code dagegen mit ("No module named 'modul'").
        # Beide Formen kommen tatsächlich vor, je nachdem, wo der Fehler auftritt.
        text = stderr or ""
        return (f"No module named {modul}" in text
                or f"No module named '{modul}'" in text)

    # ══════════════════════════════════════════════════════════ python.*
    def python_version(python: str = "") -> ToolResult:
        exe = interpreter(python)
        res = run_process([exe, "--version"], timeout=10)
        out = ((res.stdout or "") + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or "python --version fehlgeschlagen"))
        return ok("python.version", out, payload=out, interpreter=exe)

    def python_syntax_check(path: str) -> ToolResult:
        datei = ws.resolve(path)
        if not datei.is_file():
            raise ToolError(f"Datei existiert nicht: {datei}")
        inhalt = datei.read_text(encoding="utf-8", errors="replace")
        check = coder.check_syntax(str(datei), inhalt)
        if check is None:
            raise ToolError(f"Für {datei.suffix or '(ohne Endung)'} gibt es keine "
                            "Syntaxprüfung.")
        return ToolResult(tool="python.syntax_check", ok=check.ok, summary=check.detail,
                          evidence={"pfad": str(datei)})

    def python_packages_list(python: str = "") -> ToolResult:
        exe = interpreter(python)
        res = run_process([exe, "-m", "pip", "list", "--format=freeze"], timeout=30)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "pip list fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        return ok("python.packages.list", f"{len(zeilen)} installierte(s) Paket(e)",
                  payload="\n".join(zeilen), anzahl=len(zeilen), interpreter=exe)

    def python_package_install(package: str, python: str) -> ToolResult:
        exe = interpreter_required(python)
        pkg = (package or "").strip()
        if not pkg:
            raise ToolError("Es wurde kein Paket angegeben.")
        if pkg.startswith("-"):
            raise ToolError(f"Kein gültiger Paketname: {pkg!r}")
        res = run_process([exe, "-m", "pip", "install", pkg], timeout=300)
        out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or f"Installation von {pkg} fehlgeschlagen"))
        return ok("python.package.install", f"Installiert: {pkg}",
                  payload=_clip(out), paket=pkg, interpreter=exe)

    def python_package_uninstall(package: str, python: str) -> ToolResult:
        exe = interpreter_required(python)
        pkg = (package or "").strip()
        if not pkg or pkg.startswith("-"):
            raise ToolError(f"Kein gültiger Paketname: {pkg!r}")
        res = run_process([exe, "-m", "pip", "uninstall", "-y", pkg], timeout=60)
        out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or f"Deinstallation von {pkg} fehlgeschlagen"))
        return ok("python.package.uninstall", f"Deinstalliert: {pkg}",
                  payload=_clip(out), paket=pkg, interpreter=exe)

    def python_requirements_freeze(path: str, python: str) -> ToolResult:
        exe = interpreter_required(python)
        ziel = ws.resolve(path)
        res = run_process([exe, "-m", "pip", "freeze"], timeout=30)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "pip freeze fehlgeschlagen").strip()))
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text((res.stdout or "").strip() + "\n", encoding="utf-8")
        anzahl = len([z for z in (res.stdout or "").splitlines() if z.strip()])
        return ok("python.requirements.freeze", f"{anzahl} Paket(e) nach {ziel} geschrieben",
                  pfad=str(ziel), anzahl=anzahl, interpreter=exe)

    def python_venv_create(path: str, python: str = "") -> ToolResult:
        basis = interpreter(python)
        ziel = ws.resolve(path)
        if ziel.exists() and any(ziel.iterdir()):
            raise ToolError(f"Zielordner ist nicht leer: {ziel}")
        res = run_process([basis, "-m", "venv", str(ziel)], timeout=120)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "venv-Erstellung fehlgeschlagen").strip()))
        py_exe = ziel / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        return ok("python.venv.create", f"Virtuelle Umgebung angelegt: {ziel}",
                  pfad=str(ziel), interpreter=str(py_exe) if py_exe.exists() else "")

    def python_lint(path: str, python: str = "") -> ToolResult:
        exe = interpreter(python)
        ziel = ws.resolve(path)
        res = run_process([exe, "-m", "ruff", "check", str(ziel)], timeout=60)
        # Wichtig: 'ruff' fehlt beendet sich bei Python ebenfalls mit Exit-Code
        # 1 -- demselben Code, den ein echter Lint-Befund liefert. Ohne diese
        # Prüfung VOR der returncode-Auswertung würde "Modul fehlt" als
        # "0 Befunde" durchgehen, weil die eigentliche Fehlermeldung nur in
        # stderr steht und der Erfolgspfad nur stdout ansieht.
        if module_missing(res.stderr, "ruff"):
            raise ToolError(
                "Kein 'ruff' in diesem Interpreter installiert. Installieren mit "
                "python.package.install(package='ruff', python=<dieser Interpreter>).")
        if res.returncode not in (0, 1):
            raise ToolError(_clip((res.stderr or "ruff check fehlgeschlagen").strip()))
        out = (res.stdout or "").strip()
        anzahl = len(out.splitlines()) if out else 0
        return ok("python.lint", "Keine Befunde" if res.returncode == 0
                  else f"{anzahl} Befund(e)", payload=_clip(out) or "(keine)",
                  befunde=anzahl, interpreter=exe)

    def python_format(path: str, python: str = "", dry_run: bool = False) -> ToolResult:
        exe = interpreter(python)
        ziel = ws.resolve(path)
        args = [exe, "-m", "ruff", "format"] + (["--diff"] if dry_run else []) + [str(ziel)]
        res = run_process(args, timeout=60)
        if res.returncode != 0:
            if module_missing(res.stderr, "ruff"):
                raise ToolError(
                    "Kein 'ruff' in diesem Interpreter installiert. Installieren mit "
                    "python.package.install(package='ruff', python=<dieser Interpreter>).")
            raise ToolError(_clip((res.stderr or "ruff format fehlgeschlagen").strip()))
        out = ((res.stdout or "") + (res.stderr or "")).strip()
        if dry_run:
            return planned("python.format", f"Würde formatiert: {ziel}",
                           payload=_clip(out) or "(keine Änderungen)")
        return ok("python.format", f"Formatiert: {ziel}", payload=_clip(out) or None)

    def python_test(path: str = "", python: str = "", args: list[str] | None = None) -> ToolResult:
        exe = interpreter(python)
        ziel = [str(ws.resolve(path))] if path else []
        zusatz = [a for a in (args or []) if a and not a.startswith("-")]
        res = run_process([exe, "-m", "pytest", "-q", *ziel, *zusatz], timeout=TEST_TIMEOUT)
        if module_missing(res.stderr, "pytest"):
            raise ToolError(
                "Kein 'pytest' in diesem Interpreter installiert. Installieren mit "
                "python.package.install(package='pytest', python=<dieser Interpreter>).")
        out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        letzte = [z for z in out.splitlines() if z.strip()][-1:] or [""]
        return ToolResult(tool="python.test", ok=res.returncode == 0,
                          summary=letzte[0][:200], evidence={"exit_code": res.returncode,
                                                             "interpreter": exe},
                          payload=_clip(out))

    # ══════════════════════════════════════════════════════════ node.*/npm.*
    def node_version() -> ToolResult:
        res = run_process(["node", "--version"], timeout=10)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "node --version fehlgeschlagen").strip()))
        v = (res.stdout or "").strip()
        return ok("node.version", v, payload=v)

    def npm_version() -> ToolResult:
        res = run_process(["npm", "--version"], timeout=10)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "npm --version fehlgeschlagen").strip()))
        v = (res.stdout or "").strip()
        return ok("npm.version", v, payload=v)

    def node_package_list(path: str) -> ToolResult:
        projekt = ws.resolve(path)
        res = run_process(["npm", "list", "--depth=0"], timeout=30, cwd=str(projekt))
        out = (res.stdout or "").strip()
        # npm list gibt bei fehlenden Peer-Deps einen Exit-Code != 0 zurück,
        # obwohl die Liste selbst brauchbar ist -- deshalb hier keine
        # harte ToolError-Schwelle auf den Exit-Code allein.
        if not out and res.returncode != 0:
            raise ToolError(_clip((res.stderr or "npm list fehlgeschlagen").strip()))
        return ok("node.package.list", f"Pakete in {projekt.name}", payload=_clip(out))

    def node_install(path: str, timeout: int = 0) -> ToolResult:
        projekt = ws.resolve(path)
        t = max(30.0, min(float(timeout or 300), 900.0))
        res = run_process(["npm", "install"], timeout=t, cwd=str(projekt))
        out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or "npm install fehlgeschlagen"))
        return ok("node.install", f"Abhängigkeiten installiert in {projekt.name}",
                  payload=_clip(out))

    def node_package_add(path: str, package: str, dev: bool = False,
                         timeout: int = 0) -> ToolResult:
        projekt = ws.resolve(path)
        pkg = (package or "").strip()
        if not pkg or pkg.startswith("-"):
            raise ToolError(f"Kein gültiger Paketname: {pkg!r}")
        args = ["npm", "install", pkg] + (["--save-dev"] if dev else [])
        t = max(30.0, min(float(timeout or 300), 900.0))
        res = run_process(args, timeout=t, cwd=str(projekt))
        out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or f"Installation von {pkg} fehlgeschlagen"))
        return ok("node.package.add", f"Hinzugefügt: {pkg}"
                  f"{' (devDependency)' if dev else ''}", payload=_clip(out), paket=pkg)

    def node_package_remove(path: str, package: str) -> ToolResult:
        projekt = ws.resolve(path)
        pkg = (package or "").strip()
        if not pkg or pkg.startswith("-"):
            raise ToolError(f"Kein gültiger Paketname: {pkg!r}")
        res = run_process(["npm", "uninstall", pkg], timeout=120, cwd=str(projekt))
        out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(out or f"Entfernen von {pkg} fehlgeschlagen"))
        return ok("node.package.remove", f"Entfernt: {pkg}", payload=_clip(out), paket=pkg)

    def node_init(path: str) -> ToolResult:
        projekt = ws.resolve(path)
        projekt.mkdir(parents=True, exist_ok=True)
        if (projekt / "package.json").is_file():
            raise ToolError(f"package.json existiert bereits in {projekt}")
        res = run_process(["npm", "init", "-y"], timeout=30, cwd=str(projekt))
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "npm init fehlgeschlagen").strip()))
        return ok("node.init", f"package.json angelegt in {projekt}", pfad=str(projekt))

    def node_audit(path: str) -> ToolResult:
        projekt = ws.resolve(path)
        res = run_process(["npm", "audit"], timeout=60, cwd=str(projekt))
        out = (res.stdout or "").strip()
        return ok("node.audit", out.splitlines()[0] if out else "Keine Angaben",
                  payload=_clip(out) or "(keine Ausgabe)")

    def node_script_run(path: str, script: str, timeout: int = 0) -> ToolResult:
        projekt = ws.resolve(path)
        name = (script or "").strip()
        if not name:
            raise ToolError("Es wurde kein Skriptname angegeben.")
        manifest = projekt / "package.json"
        if not manifest.is_file():
            raise ToolError(f"Keine package.json in {projekt}")
        try:
            daten = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ToolError(f"package.json nicht lesbar: {exc}") from exc
        skripte = daten.get("scripts") or {}
        if name not in skripte:
            raise ToolError(f"'{name}' ist kein definiertes Skript. Vorhanden: "
                            f"{', '.join(sorted(skripte)) or '(keine)'}")
        t = max(10.0, min(float(timeout or 300), 900.0))
        res = run_process(["npm", "run", name], timeout=t, cwd=str(projekt))
        out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        return ToolResult(tool="node.script.run", ok=res.returncode == 0,
                          summary=f"'{name}' beendet mit Exit-Code {res.returncode}",
                          evidence={"exit_code": res.returncode, "skript": name},
                          payload=_clip(out))

    # ══════════════════════════════════════════════════════════ dev.*
    _MARKER = {
        "package.json": "Node.js", "requirements.txt": "Python (pip)",
        "pyproject.toml": "Python (pyproject)", "Pipfile": "Python (pipenv)",
        "Cargo.toml": "Rust", "go.mod": "Go", "Dockerfile": "Docker",
        "docker-compose.yml": "Docker Compose", ".git": "Git-Repository",
        "pom.xml": "Java (Maven)", "build.gradle": "Java/Kotlin (Gradle)",
    }

    def dev_project_detect(path: str) -> ToolResult:
        ordner = ws.resolve(path)
        if not ordner.is_dir():
            raise ToolError(f"Ordner existiert nicht: {ordner}")
        gefunden = [label for name, label in _MARKER.items() if (ordner / name).exists()]
        summary = (", ".join(gefunden) if gefunden else
                  "Kein bekannter Projekttyp erkannt")
        return ok("dev.project.detect", summary, payload=summary, projekttypen=gefunden)

    def dev_stats(path: str, max_files: int = 5000) -> ToolResult:
        ordner = ws.resolve(path)
        if not ordner.is_dir():
            raise ToolError(f"Ordner existiert nicht: {ordner}")
        ausgeschlossen = {".git", "node_modules", "__pycache__", ".venv", "venv",
                          "dist", "build", ".mypy_cache", ".pytest_cache"}
        je_endung: dict[str, list[int]] = {}
        anzahl = 0
        for wurzel, ordner_liste, dateien in os.walk(ordner):
            ordner_liste[:] = [o for o in ordner_liste if o not in ausgeschlossen]
            for name in dateien:
                anzahl += 1
                if anzahl > max_files:
                    break
                pfad = Path(wurzel) / name
                endung = pfad.suffix.lower() or "(ohne Endung)"
                try:
                    zeilen = sum(1 for _ in pfad.open("rb"))
                except OSError:
                    continue
                eintrag = je_endung.setdefault(endung, [0, 0])
                eintrag[0] += 1
                eintrag[1] += zeilen
            if anzahl > max_files:
                break
        rows = sorted(([e, d, z] for e, (d, z) in je_endung.items()),
                      key=lambda r: -r[2])[:40]
        return ok("dev.stats", f"{anzahl} Datei(en) in {ordner.name} untersucht",
                  payload=table(rows, headers=["Endung", "Dateien", "Zeilen"]),
                  dateien=anzahl, endungen=len(je_endung))

    def dev_env_list(filter: str = "") -> ToolResult:
        muster = (filter or "").strip().lower()
        zeilen = []
        for schluessel in sorted(os.environ):
            if muster and muster not in schluessel.lower():
                continue
            wert = os.environ[schluessel]
            if _looks_like_secret(schluessel):
                wert = "***"
            zeilen.append(f"{schluessel}={wert}")
        return ok("dev.env.list", f"{len(zeilen)} Umgebungsvariable(n)",
                  payload="\n".join(zeilen) or "(keine)", anzahl=len(zeilen))

    def dev_changelog_entry(path: str, entry: str, heading: str = "") -> ToolResult:
        datei = ws.resolve(path)
        text_neu = (entry or "").strip()
        if not text_neu:
            raise ToolError("Es wurde kein Eintrag angegeben.")
        import datetime
        titel = heading.strip() or datetime.date.today().isoformat()
        bestehend = datei.read_text(encoding="utf-8") if datei.is_file() else ""
        block = f"## {titel}\n\n- {text_neu}\n\n"
        datei.parent.mkdir(parents=True, exist_ok=True)
        if bestehend and f"## {titel}" in bestehend.splitlines():
            # Denselben Abschnitt weiterschreiben statt zu duplizieren.
            zeilen = bestehend.splitlines()
            index = zeilen.index(f"## {titel}")
            zeilen.insert(index + 2, f"- {text_neu}")
            datei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        else:
            datei.write_text(block + bestehend, encoding="utf-8")
        return ok("dev.changelog.entry", f"Eintrag ergänzt unter '{titel}'",
                  pfad=str(datei), abschnitt=titel)

    _pp = text("Projektordner (im Arbeitsbereich)")
    _py = text("Pfad zum Python-Interpreter, z. B. der venv. Leer = Jarvis' eigener")
    _py_req = text("Pfad zum Ziel-Interpreter (Pflicht, damit nicht aus Versehen "
                   "Jarvis' eigene Umgebung verändert wird)")

    return [
        # ── python.* -- Analyse (SAFE/READ) ──────────────────────────────
        Tool("python.version", "Version des Python-Interpreters.",
             params(python=_py), python_version, level=P.READ, tags=("python",)),
        Tool("python.syntax_check", "Prüft eine Datei auf Syntaxfehler, ohne sie "
             "auszuführen.",
             params("path", path=text("Pfad zur Datei")), python_syntax_check,
             level=P.SAFE, tags=("python", "syntax"),
             phrases=("ist die syntax okay", "python syntax prüfen")),
        Tool("python.packages.list", "Installierte Pakete eines Interpreters "
             "(wie pip freeze).",
             params(python=_py), python_packages_list, level=P.READ,
             tags=("python", "pakete")),
        Tool("python.lint", "Statische Codeprüfung mit ruff (falls installiert).",
             params("path", path=text("Datei oder Ordner"), python=_py),
             python_lint, level=P.READ, tags=("python", "lint", "qualitaet"),
             phrases=("prüf den code", "python linten")),

        # ── python.* -- verändernd ────────────────────────────────────────
        Tool("python.format", "Formatiert Code mit ruff. Unterstützt einen echten "
             "Probelauf (zeigt das Diff, ändert nichts).",
             params("path", path=text("Datei oder Ordner"), python=_py, dry_run=DRY),
             python_format, level=P.WRITE, tags=("python", "format"), dry_run=True),
        Tool("python.venv.create", "Legt eine virtuelle Umgebung an.",
             params("path", path=text("Zielordner im Arbeitsbereich"),
                    python=text("Basis-Interpreter, leer = Jarvis' eigener")),
             python_venv_create, level=P.WRITE, tags=("python", "venv"),
             phrases=("leg eine virtuelle umgebung an", "venv erstellen")),
        Tool("python.requirements.freeze", "Schreibt die installierten Pakete eines "
             "Interpreters in eine requirements-Datei.",
             params("path", "python", path=text("Zieldatei, z. B. requirements.txt"),
                    python=_py_req),
             python_requirements_freeze, level=P.WRITE, tags=("python", "pakete")),

        # ── python.* -- Codeausführung (SYSTEM) ───────────────────────────
        Tool("python.package.install", "Installiert ein Paket mit pip.",
             params("package", "python", package=text("Paketname, ggf. mit Version"),
                    python=_py_req),
             python_package_install, level=P.SYSTEM, tags=("python", "pakete"),
             timeout=300.0, phrases=("installier das python paket",)),
        Tool("python.package.uninstall", "Entfernt ein Paket mit pip.",
             params("package", "python", package=text("Paketname"), python=_py_req),
             python_package_uninstall, level=P.SYSTEM, tags=("python", "pakete")),
        Tool("python.test", "Führt pytest aus.",
             params(path=text("Datei/Ordner/Modul, leer = Vorgabe von pytest"),
                    python=_py, args={"type": "array", "items": {"type": "string"},
                                      "description": "Zusätzliche pytest-Argumente ohne führendes '-'"}),
             python_test, level=P.SYSTEM, tags=("python", "test"), timeout=TEST_TIMEOUT,
             phrases=("führ die tests aus", "pytest laufen lassen")),

        # ── node.*/npm.* ──────────────────────────────────────────────────
        Tool("node.version", "Installierte Node.js-Version.",
             NO_PARAMS, node_version, level=P.READ, requires=("node",), tags=("node",)),
        Tool("npm.version", "Installierte npm-Version.",
             NO_PARAMS, npm_version, level=P.READ, requires=("npm",), tags=("node",)),
        Tool("node.package.list", "Installierte npm-Pakete der obersten Ebene.",
             params("path", path=_pp), node_package_list, level=P.READ,
             requires=("npm",), tags=("node", "pakete")),
        Tool("node.audit", "Bekannte Sicherheitslücken in den npm-Abhängigkeiten.",
             params("path", path=_pp), node_audit, level=P.READ, requires=("npm",),
             tags=("node", "sicherheit")),
        Tool("node.install", "Installiert alle Abhängigkeiten aus package.json.",
             params("path", path=_pp, timeout=integer("Sekunden, Vorgabe 300")),
             node_install, level=P.SYSTEM, requires=("npm",), tags=("node", "pakete"),
             timeout=300.0, phrases=("npm install", "installier die abhängigkeiten")),
        Tool("node.package.add", "Fügt eine npm-Abhängigkeit hinzu.",
             params("path", "package", path=_pp, package=text("Paketname, ggf. mit Version"),
                    dev=flag("Als devDependency eintragen"),
                    timeout=integer("Sekunden, Vorgabe 300")),
             node_package_add, level=P.SYSTEM, requires=("npm",), tags=("node", "pakete"),
             timeout=300.0),
        Tool("node.package.remove", "Entfernt eine npm-Abhängigkeit.",
             params("path", "package", path=_pp, package=text("Paketname")),
             node_package_remove, level=P.SYSTEM, requires=("npm",), tags=("node", "pakete")),
        Tool("node.init", "Legt eine neue package.json an.",
             params("path", path=_pp), node_init, level=P.WRITE, requires=("npm",),
             tags=("node",)),
        Tool("node.script.run", "Führt ein in package.json definiertes npm-Skript aus.",
             params("path", "script", path=_pp, script=text("Skriptname aus package.json"),
                    timeout=integer("Sekunden, Vorgabe 300")),
             node_script_run, level=P.SYSTEM, requires=("npm",), tags=("node", "skript"),
             timeout=300.0, phrases=("führ den build aus", "npm run")),

        # ── dev.* ─────────────────────────────────────────────────────────
        Tool("dev.project.detect", "Erkennt anhand bekannter Dateien, was für ein "
             "Projekt in einem Ordner liegt.",
             params("path", path=_pp), dev_project_detect, level=P.SAFE,
             tags=("entwicklung", "projekt"),
             phrases=("was für ein projekt ist das",)),
        Tool("dev.stats", "Zählt Dateien und Zeilen je Dateityp in einem Ordner.",
             params("path", path=_pp, max_files=INT), dev_stats, level=P.READ,
             tags=("entwicklung", "statistik"),
             phrases=("wie groß ist das projekt", "zeilen zählen")),
        Tool("dev.env.list", "Umgebungsvariablen des Jarvis-Prozesses -- Geheimnisse "
             "(Token, Passwörter, Schlüssel) werden geschwärzt.",
             params(filter=text("Nur Namen, die diesen Text enthalten")),
             dev_env_list, level=P.READ, tags=("entwicklung", "umgebung"),
             phrases=("welche umgebungsvariablen gibt es",)),
        Tool("dev.changelog.entry", "Ergänzt einen Eintrag in einer CHANGELOG-Datei "
             "(legt sie bei Bedarf an).",
             params("path", "entry", path=text("Pfad zur CHANGELOG-Datei"),
                    entry=text("Der neue Eintrag"),
                    heading=text("Abschnittsüberschrift, Vorgabe: heutiges Datum")),
             dev_changelog_entry, level=P.WRITE, tags=("entwicklung", "dokumentation")),
    ]
