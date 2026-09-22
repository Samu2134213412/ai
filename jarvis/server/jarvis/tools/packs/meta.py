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

Bewusst KEIN zweites Sicherheitssystem: "abschalten" ist eine Vorliebe des
Nutzers, keine Berechtigungsstufe -- das Permission-System (``permissions.py``)
bleibt die einzige echte Schranke. Durchgesetzt wird das Abschalten in
``Agent._run_tool``, nicht hier.
"""

from __future__ import annotations

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, availability
from ._base import NO_PARAMS, integer, ok, params, table, text

#: Diese beiden dürfen sich nicht selbst abschalten -- sonst gäbe es über das
#: Modell keinen Weg mehr zurück (der Nutzer könnte es nur noch von außen,
#: über die Datenbank, reparieren).
_GESCHUETZT = {"jarvis.tools.enable", "jarvis.tools.disable"}


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
        werkzeuge = list(registry)
        if category:
            werkzeuge = [t for t in werkzeuge if t.category == category]
        if tag:
            werkzeuge = [t for t in werkzeuge if tag in t.tags]
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
        if real in _GESCHUETZT:
            raise ToolError(f"{real} lässt sich nicht abschalten -- sonst gäbe es keinen "
                            "Weg mehr, es über das Modell wieder anzuschalten.")
        history.disable(real, reason or "")
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

    return [
        Tool("jarvis.tools.search", "Sucht im Werkzeugkasten nach passenden Werkzeugen "
             "(Name, Beschreibung, Tags, Beispielsätze). Nützlich, wenn kein passendes "
             "Werkzeug in der aktuellen Auswahl steht.",
             params("query", query=text("Suchbegriff, z. B. 'gpu temperatur'"),
                    limit=integer("Maximal so viele Treffer, Vorgabe 10")),
             tools_search, level=P.SAFE, tags=("jarvis", "werkzeuge"),
             phrases=("welche werkzeuge gibt es für", "suche ein werkzeug für")),
        Tool("jarvis.tools.info", "Zeigt alle Details zu einem Werkzeug: Parameter, "
             "Berechtigungsstufe, Verfügbarkeit, Beispiele.",
             params("name", name=text("Werkzeugname")), tools_info, level=P.SAFE,
             tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.list", "Listet Werkzeuge, optional nach Kategorie/Tag gefiltert.",
             params(category=text("Kategorie, optional"), tag=text("Tag, optional")),
             tools_list, level=P.SAFE, tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.favorite", "Markiert ein Werkzeug als Favorit -- taucht in der "
             "Suche danach bevorzugt auf.",
             params("name", name=text("Werkzeugname")), tools_favorite, level=P.SAFE,
             tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.unfavorite", "Entfernt die Favoriten-Markierung.",
             params("name", name=text("Werkzeugname")), tools_unfavorite, level=P.SAFE,
             tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.favorites", "Listet alle als Favorit markierten Werkzeuge.",
             NO_PARAMS, tools_favorites, level=P.SAFE, tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.disable", "Schaltet ein Werkzeug ab (Punkt 26) -- keine "
             "Sicherheitsfunktion, sondern eine Vorliebe: das Werkzeug läuft danach nicht "
             "mehr, egal was das Permission-System dazu sagen würde.",
             params("name", name=text("Werkzeugname"), reason=text("Grund, optional")),
             tools_disable, level=P.SAFE, tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.enable", "Schaltet ein zuvor abgeschaltetes Werkzeug wieder an.",
             params("name", name=text("Werkzeugname")), tools_enable, level=P.SAFE,
             tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.history", "Zeigt zuletzt aufgerufene Werkzeuge samt Ergebnis.",
             params(limit=integer("Maximal so viele Einträge, Vorgabe 30"),
                    tool=text("Nur dieses Werkzeug, optional")),
             tools_history, level=P.SAFE, tags=("jarvis", "werkzeuge")),
        Tool("jarvis.tools.stats", "Kennzahlen je Werkzeug: Aufrufe, Erfolgsquote, "
             "mittlere Dauer.",
             params(limit=integer("Maximal so viele Werkzeuge, Vorgabe 30")),
             tools_stats, level=P.SAFE, tags=("jarvis", "werkzeuge")),
    ]
