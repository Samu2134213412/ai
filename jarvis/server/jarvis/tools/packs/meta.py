"""Tool Pack: ``jarvis.tools.*`` -- Introspektion über den eigenen
Werkzeugkasten (Punkt 36): suchen, ansehen, Favoriten setzen, abschalten,
Verlauf und Kennzahlen.

Ein Sonderfall unter den Packs: jedes andere Pack kennt nur den
``ToolContext`` (config/store/workspace/home/services) und baut seine
Werkzeuge unabhängig von allem anderen -- insbesondere unabhängig von der
Registry, die es selbst gerade mit aufbaut. Diese Werkzeuge hier brauchen
dagegen zwangsläufig die FERTIGE Registry und den Suchindex
(``ToolDiscovery``): ein Werkzeug, das über "alle Werkzeuge" Auskunft gibt,
kann nicht vor ihnen existieren. Deshalb wird dieser Pack getrennt von den
übrigen aufgerufen, NACHDEM Registry und Discovery fertig sind (siehe
``tools/__init__.py::build_registry``), mit Registry/Discovery/History über
``ctx.services`` statt über die üblichen ``ToolContext``-Felder.

Bewusst KEIN zweites Sicherheitssystem für das Abschalten selbst: "abschalten"
ist eine Vorliebe des Nutzers, keine Berechtigungsstufe, und wird durchgesetzt
in ``Agent._run_tool``, nicht hier. Die BerechtigungsSTUFE jedes einzelnen
Werkzeugs hier folgt aber sehr wohl der normalen Einordnung (SAFE/READ/WRITE)
wie jeder andere Pack auch: reine Auskunft ist READ, ein Favorit setzen oder
ein Werkzeug abschalten verändert gespeicherten Zustand und ist WRITE --
SAFE wäre hier falsch (SAFE läuft ohne jede Bestätigung, an jeder
Autonomiestufe vorbei, siehe ``permissions.py``).
"""

from __future__ import annotations

import sys

from ...permissions import PermissionLevel as P
from .. import shell as shell_module
from ..base import Tool, ToolError, ToolResult
from ..catalog import PROBES, ToolContext, availability, dependency_report, probe, reset_probes, run_process
from ..shell import SUGGESTED_ALLOWLIST
from ._base import LIST, NO_PARAMS, flag, integer, ok, params, planned, table, text

#: Ausgabe von "pip install" kann bei einem gescheiterten Build (fehlende
#: Systembibliothek, Kompilierfehler) sehr lang werden -- gekürzt statt
#: ungebremst ins Modell/den Verlauf durchgereicht.
_MAX_INSTALL_OUTPUT = 8_000


def _clip(value: str) -> str:
    value = value or ""
    if len(value) <= _MAX_INSTALL_OUTPUT:
        return value
    return value[:_MAX_INSTALL_OUTPUT] + f"\n… gekürzt ({len(value) - _MAX_INSTALL_OUTPUT} weitere Zeichen)"


def build(ctx: ToolContext) -> list[Tool]:
    registry = ctx.services.get("registry")
    discovery = ctx.services.get("discovery")
    history = ctx.services.get("history")
    if registry is None or discovery is None or history is None:
        raise RuntimeError(
            "jarvis.tools.* braucht registry/discovery/history in ctx.services "
            "-- siehe build_registry().")

    def tools_search(query: str, limit: int = 10) -> ToolResult:
        treffer = discovery.search((query or "").strip(), limit=max(1, min(int(limit or 10), 30)))
        zeilen = []
        for hit in treffer:
            zustand, _ = availability(hit.tool)
            zeilen.append([hit.tool.name, f"{hit.score:.1f}", zustand.value,
                          hit.tool.description[:80]])
        return ok("jarvis.tools.search", f"{len(treffer)} Treffer für {query!r}",
                  payload=table(zeilen, headers=["Werkzeug", "Punkte", "Status", "Beschreibung"]),
                  anzahl=len(treffer))

    def tools_info(name: str) -> ToolResult:
        wert = (name or "").strip()
        if wert not in registry:
            raise ToolError(f"Unbekanntes Werkzeug: {name!r}")
        tool = registry.get(wert)
        zustand, grund = availability(tool)
        daten = tool.as_dict()
        daten["verfuegbarkeit"] = zustand.value
        daten["verfuegbarkeit_grund"] = grund
        daten["favorit"] = tool.name in history.favorites()
        daten["abgeschaltet"] = tool.name in history.disabled()
        return ok("jarvis.tools.info", f"{tool.name}: {tool.description}", payload=daten)

    def tools_list(category: str = "", tag: str = "") -> ToolResult:
        werkzeuge = registry.filter(category, tag)
        zeilen = [[t.name, t.category, t.level.label, t.description[:70]] for t in werkzeuge]
        return ok("jarvis.tools.list", f"{len(werkzeuge)} Werkzeug(e)",
                  payload=table(zeilen, headers=["Werkzeug", "Kategorie", "Stufe", "Beschreibung"]),
                  anzahl=len(werkzeuge))

    def tools_favorite(name: str) -> ToolResult:
        real = registry.resolve((name or "").strip())
        if real not in registry:
            raise ToolError(f"Unbekanntes Werkzeug: {name!r}")
        history.favorite(real)
        return ok("jarvis.tools.favorite", f"{real} als Favorit markiert", name=real)

    def tools_unfavorite(name: str) -> ToolResult:
        real = registry.resolve((name or "").strip())
        if not history.unfavorite(real):
            raise ToolError(f"{real} war kein Favorit.")
        return ok("jarvis.tools.unfavorite", f"{real} ist kein Favorit mehr", name=real)

    def tools_favorites() -> ToolResult:
        namen = history.favorites()
        return ok("jarvis.tools.favorites", f"{len(namen)} Favorit(en)",
                  payload=namen, anzahl=len(namen))

    def tools_disable(name: str, reason: str = "") -> ToolResult:
        real = registry.resolve((name or "").strip())
        if real not in registry:
            raise ToolError(f"Unbekanntes Werkzeug: {name!r}")
        try:
            history.disable(real, reason or "")
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return ok("jarvis.tools.disable", f"{real} abgeschaltet", name=real, grund=reason)

    def tools_enable(name: str) -> ToolResult:
        real = registry.resolve((name or "").strip())
        if not history.enable(real):
            raise ToolError(f"{real} war nicht abgeschaltet.")
        return ok("jarvis.tools.enable", f"{real} wieder angeschaltet", name=real)

    def tools_history(limit: int = 30, tool: str = "") -> ToolResult:
        eintraege = history.list(limit=limit, tool=(tool or None))
        zeilen = [[e.tool, "ok" if e.ok else "fehler", e.summary[:60], e.request[:40]]
                 for e in eintraege]
        return ok("jarvis.tools.history", f"{len(eintraege)} Eintrag/Einträge",
                  payload=table(zeilen, headers=["Werkzeug", "Erfolg", "Ergebnis", "Anfrage"]),
                  anzahl=len(eintraege))

    def tools_stats(limit: int = 30) -> ToolResult:
        reihen = history.stats(limit=limit)
        zeilen = [[r["werkzeug"], str(r["aufrufe"]), f"{r['erfolgsquote']:.0%}",
                  f"{r['dauer_ms']}ms"] for r in reihen]
        return ok("jarvis.tools.stats", f"{len(reihen)} Werkzeug(e) mit Verlauf",
                  payload=table(zeilen, headers=["Werkzeug", "Aufrufe", "Erfolgsquote", "Ø Dauer"]),
                  anzahl=len(reihen))

    # ══════════════════════════════════════════════ jarvis.shell.enable/disable
    # run_command (tools/shell.py) ist voll gebaut, steht aber per Voreinstellung
    # auf "aus" -- eine bewusste Sicherheitsentscheidung, kein fehlendes Stück
    # (siehe shell.py). Genau deshalb zeigt die Oberfläche es dauerhaft als
    # "fehlt" an, obwohl es das Werkzeug längst gibt. Diese beiden Werkzeuge
    # sind der echte, im Permission-System selbst geführte Weg, das umzuschalten
    # -- statt eines Bypasses läuft jeder Aufruf über dieselbe SYSTEM-Bestätigung
    # wie run_command selbst.
    def _bereinigte_allowlist(programme: list[str] | None) -> list[str]:
        werte = programme or []
        return sorted({p.strip().lower() for p in werte if isinstance(p, str) and p.strip()})

    def shell_enable(allowlist: list[str] | None = None, dry_run: bool = False) -> ToolResult:
        ziel = _bereinigte_allowlist(allowlist) if allowlist else sorted(set(SUGGESTED_ALLOWLIST))
        if not ziel:
            raise ToolError(
                "Die Allowlist wäre leer -- damit liefe kein einziges Programm. "
                f"Vorschlag: {', '.join(SUGGESTED_ALLOWLIST)}")
        policy = registry.shell_policy
        if policy.enabled and policy.allowlist == set(ziel):
            return ok("jarvis.shell.enable",
                      f"War schon an, erlaubt: {', '.join(ziel)}", erlaubt=ziel)
        if dry_run:
            return planned("jarvis.shell.enable",
                          f"Würde run_command aktivieren, erlaubt: {', '.join(ziel)}",
                          erlaubt=ziel)
        policy.enabled = True
        policy.allowlist = set(ziel)
        if "run_command" not in registry:
            for tool in shell_module.build(policy):
                registry.add(tool)
                discovery.index.add(tool)
        ctx.config.shell.enabled = True
        ctx.config.shell.allowlist = ziel
        ctx.config.save()
        return ok("jarvis.shell.enable", f"run_command ist jetzt an, erlaubt: {', '.join(ziel)}",
                  erlaubt=ziel)

    def shell_disable() -> ToolResult:
        policy = registry.shell_policy
        if not policy.enabled:
            raise ToolError("run_command ist schon aus.")
        policy.enabled = False
        ctx.config.shell.enabled = False
        ctx.config.save()
        return ok("jarvis.shell.disable",
                  "run_command ist jetzt aus -- jeder Aufruf wird ab sofort abgelehnt.")

    # ═════════════════════════ jarvis.tools.dependencies/install_dependency
    # Dasselbe Prinzip wie bei run_command: eine Abhängigkeit, die fehlt, ist
    # kein Rätsel (catalog.dependency_report() sagt seit Punkt 53/55 schon
    # lange, was fehlt und wie man es bekäme), aber "installiert wird hier
    # nichts" stand bisher als bewusste Grenze da. Für ein reines Python-Paket
    # ist das keine Grenze mehr nötig -- solange echt nachgeprüft wird, ob es
    # danach wirklich da ist, statt pip's Rückgabewert zu glauben.
    def tools_dependencies() -> ToolResult:
        berichte = dependency_report()
        zeilen = [[r["schluessel"], r["name"], "da" if r["vorhanden"] else "fehlt",
                  r["installation"]] for r in berichte]
        fehlend = sum(1 for r in berichte if not r["vorhanden"])
        zusammenfassung = (f"Alle {len(berichte)} Abhängigkeiten sind da" if not fehlend
                          else f"{fehlend} von {len(berichte)} Abhängigkeit(en) fehlen")
        return ok("jarvis.tools.dependencies", zusammenfassung,
                  payload=table(zeilen, headers=["Schlüssel", "Name", "Status", "Installation"]),
                  fehlend=fehlend, gesamt=len(berichte))

    def tools_install_dependency(key: str, dry_run: bool = False) -> ToolResult:
        spec = PROBES.get((key or "").strip())
        if spec is None:
            raise ToolError(f"Unbekannter Abhängigkeits-Schlüssel: {key!r} -- "
                            "jarvis.tools.dependencies zeigt die gültigen.")
        vorhanden, _ = probe(spec.key)
        if vorhanden:
            return ok("jarvis.tools.install_dependency",
                      f"{spec.label} ist schon vorhanden.", schluessel=spec.key)
        if spec.kind != "module":
            raise ToolError(
                f"{spec.label} ist ein externes Programm, kein Python-Paket -- das kann "
                f"Jarvis nicht automatisch installieren. Von Hand: {spec.install_hint}")
        befehl = [sys.executable, "-m", "pip", "install", spec.label]
        if dry_run:
            return planned("jarvis.tools.install_dependency",
                          f"Würde ausführen: {' '.join(befehl)}",
                          schluessel=spec.key, befehl=" ".join(befehl))
        ergebnis = run_process(befehl, timeout=300)
        ausgabe = ((ergebnis.stdout or "") + "\n" + (ergebnis.stderr or "")).strip()
        if ergebnis.returncode != 0:
            raise ToolError(_clip(ausgabe) or f"Installation von {spec.label} fehlgeschlagen")
        # Nachgeprüft statt pip's Exit-Code geglaubt -- derselbe Beleg-Zwang
        # wie überall sonst: ein Werkzeug, das seinen eigenen Erfolg nur
        # behauptet, ist genau das, was dieses Projekt verhindern soll.
        reset_probes()
        jetzt_da, _ = probe(spec.key)
        if not jetzt_da:
            raise ToolError(
                f"pip install lief durch, aber {spec.label} lässt sich immer noch "
                "nicht importieren -- vermutlich ein anderer Interpreter als Jarvis selbst.")
        rest = ""
        if "&&" in spec.install_hint:
            rest = f" Zusätzlich von Hand nötig: {spec.install_hint.split('&&', 1)[1].strip()}"
        return ok("jarvis.tools.install_dependency", f"{spec.label} installiert.{rest}",
                  payload=_clip(ausgabe), schluessel=spec.key)

    return [
        Tool("jarvis.tools.search", "Sucht im Werkzeugkasten nach passenden Werkzeugen "
             "(Name, Beschreibung, Tags, Beispielsätze). Nützlich, wenn kein passendes "
             "Werkzeug in der aktuellen Auswahl steht.",
             params("query", query=text("Suchbegriff, z. B. 'gpu temperatur'"),
                    limit=integer("Maximal so viele Treffer, Vorgabe 10")),
             tools_search, level=P.READ, tags=("jarvis", "werkzeuge"),
             phrases=("welche werkzeuge gibt es für", "suche ein werkzeug für")),
        Tool("jarvis.tools.info", "Zeigt alle Details zu einem Werkzeug: Parameter, "
             "Berechtigungsstufe, Verfügbarkeit, Beispiele.",
             params("name", name=text("Werkzeugname")), tools_info, level=P.READ,
             tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.list", "Listet Werkzeuge, optional nach Kategorie/Tag gefiltert.",
             params(category=text("Kategorie, optional"), tag=text("Tag, optional")),
             tools_list, level=P.READ, tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.favorite", "Markiert ein Werkzeug als Favorit -- taucht in der "
             "Suche danach bevorzugt auf.",
             params("name", name=text("Werkzeugname")), tools_favorite, level=P.WRITE,
             tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.unfavorite", "Entfernt die Favoriten-Markierung.",
             params("name", name=text("Werkzeugname")), tools_unfavorite, level=P.WRITE,
             tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.favorites", "Listet alle als Favorit markierten Werkzeuge.",
             NO_PARAMS, tools_favorites, level=P.READ, tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.disable", "Schaltet ein Werkzeug ab (Punkt 26) -- keine "
             "Sicherheitsfunktion, sondern eine Vorliebe: das Werkzeug läuft danach nicht "
             "mehr, egal was das Permission-System dazu sagen würde.",
             params("name", name=text("Werkzeugname"), reason=text("Grund, optional")),
             tools_disable, level=P.WRITE, tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.enable", "Schaltet ein zuvor abgeschaltetes Werkzeug wieder an.",
             params("name", name=text("Werkzeugname")), tools_enable, level=P.WRITE,
             tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.history", "Zeigt zuletzt aufgerufene Werkzeuge samt Ergebnis.",
             params(limit=integer("Maximal so viele Einträge, Vorgabe 30"),
                    tool=text("Nur dieses Werkzeug, optional")),
             tools_history, level=P.READ, tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.stats", "Kennzahlen je Werkzeug: Aufrufe, Erfolgsquote, "
             "mittlere Dauer.",
             params(limit=integer("Maximal so viele Werkzeuge, Vorgabe 30")),
             tools_stats, level=P.READ, tags=("jarvis", "werkzeuge")),
        Tool("jarvis.shell.enable", "Schaltet run_command an -- das Werkzeug existiert "
             "längst, ist aber per Voreinstellung aus (siehe tools/shell.py). Ohne "
             "eigene Angabe eine vorsichtige Vorgabe-Allowlist (git, python, npm, "
             "pytest, lesende Befehle wie ls/cat). Betrifft nur die Allowlist selbst, "
             "nicht das Permission-System: jeder einzelne run_command-Aufruf verlangt "
             "weiterhin dieselbe Bestätigung wie jedes andere SYSTEM-Werkzeug.",
             params(allowlist=LIST, dry_run=flag("Nur zeigen, was sich ändern würde")),
             shell_enable, level=P.SYSTEM, dry_run=True,
             tags=("jarvis", "shell", "konfiguration"),
             phrases=("aktiviere die shell", "schalte befehle ausführen an")),
        Tool("jarvis.shell.disable", "Schaltet run_command wieder ab.",
             NO_PARAMS, shell_disable, level=P.SYSTEM,
             tags=("jarvis", "shell", "konfiguration"),
             phrases=("deaktiviere die shell", "schalte befehle ausführen aus")),
        Tool("jarvis.tools.dependencies", "Zeigt, welche externen Abhängigkeiten "
             "(Python-Pakete, Programme) auf diesem Rechner da sind und welche fehlen, "
             "mit Installationshinweis -- die Grundlage für "
             "jarvis.tools.install_dependency.",
             NO_PARAMS, tools_dependencies, level=P.READ,
             tags=("jarvis", "werkzeuge", "abhängigkeiten"),
             phrases=("was fehlt noch", "welche abhängigkeiten fehlen")),
        Tool("jarvis.tools.install_dependency", "Installiert eine fehlende Python-"
             "Abhängigkeit mit pip, in Jarvis' eigener Laufzeitumgebung (Schlüssel aus "
             "jarvis.tools.dependencies, z. B. 'pyautogui' oder 'qrcode'). Prüft danach "
             "echt nach, ob sie jetzt importierbar ist, statt pip's Erfolg zu glauben. "
             "Externe Programme (ffmpeg, Tesseract, nginx, ...) kann das NICHT "
             "automatisch installieren -- die verlangen von Hand einen Installer oder "
             "den Paketmanager des Betriebssystems.",
             params("key", key=text("Schlüssel aus jarvis.tools.dependencies, z. B. 'pyautogui'"),
                    dry_run=flag("Nur zeigen, welcher Befehl liefe")),
             tools_install_dependency, level=P.SYSTEM, dry_run=True,
             tags=("jarvis", "werkzeuge", "abhängigkeiten"),
             phrases=("installiere die fehlende abhängigkeit", "installiere pyautogui")),
    ]
