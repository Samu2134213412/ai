"""Tool Pack: Guardian -- der eigene Virenschutz (``../guardian``) aus Jarvis heraus.

Jarvis scannt hier nicht selbst. Guardian ist ein eigenes, getestetes
Rust-Programm (Hash-/YARA-Erkennung, Punktbewertung, umkehrbare Quarantäne);
ein zweiter Scanner in Python wäre doppelte Arbeit mit doppelten Fehlern
(Punkt 56). Dieses Pack ruft ``guardian --json …`` auf und wertet
ausschließlich dessen JSON-Antwort aus -- nie Fließtext, der sich beim
nächsten Update ändern könnte.

Einordnung ins Permission-System:

* Status, Quarantäne-Liste, Ereignisse, Regelprüfung: READ -- nur Auskunft.
* ``guardian.check``: WRITE -- ein Treffer verschiebt die Datei in die
  Quarantäne. ``dry_run`` ist ein echter Scan mit ``--no-quarantine``: jede
  Datei wird wirklich bewertet, aber nichts verschoben und nichts
  protokolliert.
* ``guardian.quarantine.restore``: CRITICAL -- die Datei, die Guardian als
  Bedrohung eingestuft hat, kommt zurück auf die Platte. Das ist die eine
  Aktion, bei der ein Fehlgriff des Modells den Rechner wieder infizieren
  kann; sie verlangt deshalb IMMER eine ausdrückliche Bestätigung, egal wie
  die Policy sonst eingestellt ist.

Wo die ``guardian``-Datei liegt, entscheidet ``_finde_guardian`` -- sie hängt
als eigene Suche an der Abhängigkeit "guardian" (``catalog.PROBES``), damit
die Werkzeugliste ehrlich ``nachrüsten`` zeigt, solange Guardian nicht
gebaut ist.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, probe, run_process, set_probe_finder
from ._base import DRY, NO_PARAMS, flag, integer, ok, params, planned, table, text

#: Das Repo, in dem jarvis/ und guardian/ nebeneinander liegen.
_REPO = Path(__file__).resolve().parents[5]
_EXE = "guardian.exe" if os.name == "nt" else "guardian"


def _finde_guardian(konfiguriert: str) -> str:
    """Wo liegt die ``guardian``-Datei? Reihenfolge: ausdrücklich
    konfiguriert → PATH → Release-Build im Repo → Debug-Build im Repo.

    Ein konfigurierter Pfad, der nicht existiert, gilt als "nicht gefunden"
    -- nicht als Anlass, stillschweigend eine andere Guardian-Datei zu
    nehmen als die, die der Nutzer gemeint hat."""
    if konfiguriert:
        pfad = Path(os.path.expandvars(os.path.expanduser(konfiguriert)))
        return str(pfad) if pfad.is_file() else ""
    im_path = shutil.which("guardian")
    if im_path:
        return im_path
    for build in ("release", "debug"):
        kandidat = _REPO / "guardian" / "target" / build / _EXE
        if kandidat.is_file():
            return str(kandidat)
    return ""


def _kurz(wert: str, grenze: int = 600) -> str:
    wert = (wert or "").strip()
    return wert if len(wert) <= grenze else wert[:grenze] + " …"


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace
    cfg = ctx.config.guardian
    set_probe_finder("guardian", lambda: _finde_guardian(cfg.binary))

    def lauf(befehl: list[str], timeout: float = 60.0,
             erlaubte_codes: tuple[int, ...] = (0,)) -> tuple[dict[str, Any], int]:
        """Ein Guardian-Aufruf mit ``--json``. Gibt (Antwort, Exit-Code) zurück
        oder scheitert mit Guardians eigener Fehlermeldung."""
        exe = probe("guardian")[1]
        if not exe:
            raise ToolError("Guardian ist nicht gebaut oder nicht gefunden -- im Ordner "
                            "guardian/: cargo build --release, oder guardian.binary in "
                            "der jarvis.json setzen.")
        args = [exe]
        if cfg.config:
            args += ["--config", os.path.expanduser(cfg.config)]
        args += ["--json", *befehl]
        try:
            res = run_process(args, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ToolError(f"Guardian hat nach {timeout:.0f} s nicht geantwortet.") from None
        except OSError as exc:
            raise ToolError(f"Guardian ließ sich nicht starten: {exc}") from exc
        fehlertext = _kurz(res.stderr or res.stdout)
        if "--json" in (res.stderr or "") and "unexpected argument" in (res.stderr or ""):
            raise ToolError("Diese Guardian-Version kennt --json noch nicht -- im Ordner "
                            "guardian/ neu bauen (cargo build --release).")
        try:
            daten = json.loads(res.stdout or "")
        except json.JSONDecodeError:
            raise ToolError(f"Guardian gab keine auswertbare Antwort "
                            f"(Exit {res.returncode}): {fehlertext}") from None
        if not isinstance(daten, dict):
            raise ToolError(f"Guardian gab unerwartete Daten zurück: {_kurz(res.stdout)}")
        if "error" in daten or res.returncode not in erlaubte_codes:
            raise ToolError(f"Guardian: {daten.get('error') or fehlertext}")
        return daten, res.returncode

    def warnungen(daten: dict[str, Any]) -> str:
        liste = daten.get("warnings") or []
        return ("\nWarnungen: " + "; ".join(liste)) if liste else ""

    # ══════════════════════════════════════════════════════════ Auskunft
    def guardian_status() -> ToolResult:
        daten, _ = lauf(["status"])
        return ok("guardian.status",
                  f"Guardian bereit: {daten.get('rule_files', 0)} Regeldatei(en), "
                  f"{daten.get('hash_db_entries', 0)} bekannte Hashes, "
                  f"{daten.get('quarantine_entries', 0)} in Quarantäne"
                  + warnungen(daten),
                  payload=json.dumps(daten, ensure_ascii=False, indent=2),
                  regeldateien=daten.get("rule_files"),
                  regelversion=daten.get("rules_version"),
                  hashes=daten.get("hash_db_entries"),
                  quarantaene=daten.get("quarantine_entries"),
                  konfiguration=daten.get("config"))

    def guardian_quarantine_list() -> ToolResult:
        daten, _ = lauf(["quarantine", "list"])
        eintraege = daten.get("entries") or []
        offen = [e for e in eintraege if not e.get("restored")]
        zeilen = [[e.get("id", ""), str(e.get("threat_score", "")),
                   e.get("original_filename", ""), e.get("detection_time", ""),
                   "ja" if e.get("restored") else "nein", _kurz(e.get("detection_reason", ""), 80)]
                  for e in eintraege]
        return ok("guardian.quarantine.list",
                  f"{len(offen)} Datei(en) in Quarantäne"
                  + (f", {len(eintraege) - len(offen)} bereits wiederhergestellt"
                     if len(eintraege) > len(offen) else ""),
                  payload=table(zeilen, headers=["ID", "Score", "Datei", "Erkannt",
                                                 "Zurück", "Grund"]) if zeilen else "(leer)",
                  anzahl=len(offen))

    def guardian_events(limit: int = 20) -> ToolResult:
        anzahl = max(1, min(int(limit or 20), 500))
        daten, _ = lauf(["events", "--limit", str(anzahl)])
        ereignisse = daten.get("events") or []
        zeilen = [[e.get("timestamp", ""), e.get("event", ""),
                   "-" if e.get("score") is None else str(e.get("score")),
                   e.get("action", ""), e.get("file") or ""] for e in ereignisse]
        return ok("guardian.events", f"{len(ereignisse)} Ereignis(se)",
                  payload=table(zeilen, headers=["Zeit", "Ereignis", "Score", "Aktion", "Datei"])
                  if zeilen else "(noch keine)",
                  anzahl=len(ereignisse))

    def guardian_rules_update() -> ToolResult:
        daten, _ = lauf(["rules", "update"])
        return ok("guardian.rules.update",
                  f"Regeln geprüft und neu geladen: {daten.get('rule_files', 0)} Datei(en), "
                  f"Version {daten.get('version', '?')}",
                  regeldateien=daten.get("rule_files"), version=daten.get("version"),
                  vorher=daten.get("previous"))

    # ══════════════════════════════════════════════════════════ Scan
    def guardian_check(path: str = "", full: bool = False, dry_run: bool = False) -> ToolResult:
        if full and (path or "").strip():
            raise ToolError("Entweder ein Pfad oder full=true, nicht beides.")
        if full:
            ziel = ["--full"]
            beschreibung = "Guardians eingetragene Scan-Ordner"
        else:
            if not (path or "").strip():
                raise ToolError("Gib einen Pfad an oder benutze full=true für Guardians "
                                "eingetragene Scan-Ordner.")
            # Dieselbe Pfadgrenze wie jedes Dateiwerkzeug: ein Treffer
            # verschiebt die Datei, also gilt hier dieselbe Freigabe (roots).
            pfad = ws.resolve(path)
            if not pfad.exists():
                raise ToolError(f"Existiert nicht: {pfad}")
            ziel = [str(pfad)]
            beschreibung = pfad.name or str(pfad)
        befehl = ["scan", *(["--no-quarantine"] if dry_run else []), *ziel]
        # Exit 1 heißt bei Guardian "Bedrohung gefunden" -- ein gelungener
        # Scan, kein Fehler.
        daten, _ = lauf(befehl, timeout=float(cfg.scan_timeout), erlaubte_codes=(0, 1))

        ergebnisse = daten.get("results") or []
        fehlgeschlagen = daten.get("failed") or []
        treffer = [r for r in ergebnisse if r.get("verdict") not in (None, "clean")]
        verschoben = [r for r in treffer if r.get("action") == "quarantined"]
        waere = [r for r in treffer if r.get("action") == "would_quarantine"]
        misslungen = [r for r in treffer if r.get("action") == "quarantine_failed"]

        # Nachgeprüft statt geglaubt: eine Datei, die laut Guardian in der
        # Quarantäne liegt, darf an ihrem alten Ort nicht mehr existieren.
        noch_da = [r["path"] for r in verschoben if Path(r["path"]).exists()]
        if noch_da:
            raise ToolError("Guardian meldet Quarantäne, aber die Datei liegt noch an ihrem "
                            f"Platz: {', '.join(noch_da)}")

        zeilen = [[Path(r.get("path", "")).name, str(r.get("score", "")),
                   r.get("verdict", ""), r.get("action", ""),
                   r.get("quarantine_id") or "", "; ".join(r.get("reasons") or [])[:120]]
                  for r in ergebnisse]
        payload = (table(zeilen, headers=["Datei", "Score", "Urteil", "Aktion", "Quarantäne-ID",
                                          "Gründe"]) if zeilen else daten.get("message", "(nichts)"))
        if fehlgeschlagen:
            payload += "\nNicht prüfbar: " + "; ".join(
                f"{f.get('path')}: {f.get('error')}" for f in fehlgeschlagen)
        payload += warnungen(daten)

        geprueft = daten.get("scanned", len(ergebnisse))
        if not ergebnisse and not fehlgeschlagen:
            satz = daten.get("message") or "Keine passenden Dateien gefunden."
        elif not treffer:
            satz = f"{geprueft} Datei(en) in {beschreibung} geprüft -- nichts gefunden"
        else:
            teile = [f"{len(treffer)} Bedrohung(en) in {beschreibung} "
                     f"(schlimmstes Urteil: {daten.get('worst')})"]
            if verschoben:
                teile.append(f"{len(verschoben)} in Quarantäne verschoben")
            if misslungen:
                teile.append(f"{len(misslungen)} ließ(en) sich NICHT verschieben")
            satz = f"{geprueft} Datei(en) geprüft: " + ", ".join(teile)
        if fehlgeschlagen:
            satz += f" · {len(fehlgeschlagen)} nicht prüfbar"

        belege = dict(geprueft=geprueft, bedrohungen=len(treffer),
                      schlimmstes=daten.get("worst"), in_quarantaene=len(verschoben),
                      nicht_pruefbar=len(fehlgeschlagen))
        if dry_run:
            if waere:
                satz += f" -- würde {len(waere)} Datei(en) in Quarantäne verschieben"
            return planned("guardian.check", satz, payload=payload,
                           wuerde_verschieben=len(waere), **belege)
        if misslungen:
            raise ToolError(satz + " -- " + "; ".join(
                f"{Path(r['path']).name}: {r.get('quarantine_error')}" for r in misslungen))
        return ok("guardian.check", satz, payload=payload, **belege)

    # ══════════════════════════════════════════════════════════ Wiederherstellen
    def guardian_quarantine_restore(id: str) -> ToolResult:  # noqa: A002 - Name im Schema
        kennung = (id or "").strip()
        if not kennung:
            raise ToolError("Welche Quarantäne-ID? guardian.quarantine.list zeigt sie.")
        daten, _ = lauf(["quarantine", "restore", kennung])
        ziel = daten.get("restored") or ""
        if not ziel or not Path(ziel).exists():
            raise ToolError(f"Guardian meldet die Wiederherstellung, aber unter {ziel!r} "
                            "liegt keine Datei.")
        return ok("guardian.quarantine.restore",
                  f"Aus der Quarantäne zurückgeholt: {Path(ziel).name}",
                  id=kennung, pfad=ziel)

    _tags = ("sicherheit", "virenschutz", "guardian")
    return [
        Tool("guardian.status", "Zustand des Virenschutzes Guardian: geladene Regeln, "
             "bekannte Schadsoftware-Hashes, Quarantäne, Protokollort.",
             NO_PARAMS, guardian_status, level=P.READ, requires=("guardian",), tags=_tags,
             phrases=("ist der virenschutz aktiv", "guardian status")),
        Tool("guardian.check", "Prüft eine Datei oder einen Ordner mit Guardian auf "
             "Schadsoftware (Hash- und YARA-Erkennung, Punktwert 0-100). Ab dem "
             "Quarantäne-Schwellwert wird die Datei in Guardians Quarantäne verschoben "
             "(umkehrbar). dry_run bewertet wirklich, verschiebt aber nichts.",
             params(path=text("Datei oder Ordner im Arbeitsbereich"),
                    full=flag("Guardians eingetragene Scan-Ordner statt eines Pfads"),
                    dry_run=DRY),
             guardian_check, level=P.WRITE, requires=("guardian",), dry_run=True,
             timeout=float(cfg.scan_timeout), tags=_tags,
             phrases=("prüf das auf viren", "scan meine downloads", "ist das ein virus")),
        Tool("guardian.quarantine.list", "Listet, was Guardian in Quarantäne genommen hat, "
             "mit ID, Punktwert und Grund.",
             NO_PARAMS, guardian_quarantine_list, level=P.READ, requires=("guardian",),
             tags=_tags, phrases=("was ist in quarantäne", "zeig die quarantäne")),
        Tool("guardian.quarantine.restore", "Holt eine Datei aus Guardians Quarantäne an "
             "ihren alten Platz zurück. CRITICAL: die Datei wurde als Bedrohung eingestuft -- "
             "verlangt immer eine ausdrückliche Bestätigung.",
             params("id", id=text("Quarantäne-ID aus guardian.quarantine.list")),
             guardian_quarantine_restore, level=P.CRITICAL, requires=("guardian",),
             tags=_tags),
        Tool("guardian.events", "Die letzten Ereignisse aus Guardians Protokoll "
             "(Scans, Funde, Quarantäne, Wiederherstellungen).",
             params(limit=integer("Maximal so viele, Vorgabe 20")),
             guardian_events, level=P.READ, requires=("guardian",), tags=_tags,
             phrases=("was hat der virenschutz gefunden",)),
        Tool("guardian.rules.update", "Prüft Guardians lokale YARA-Regeln und lädt sie neu; "
             "meldet die Regelversion. (Einen Online-Regeldienst gibt es noch nicht.)",
             NO_PARAMS, guardian_rules_update, level=P.READ, requires=("guardian",),
             tags=_tags),
    ]
