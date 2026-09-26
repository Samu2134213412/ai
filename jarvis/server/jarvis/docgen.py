"""Werkzeugreferenz aus der Registry erzeugen (Punkt 49).

Bewusst kein von Hand gepflegtes Dokument: bei mehreren hundert Werkzeugen
läuft eine handgeschriebene Liste garantiert auseinander. Diese Datei liest
stattdessen die echte, laufende Registry und schreibt genau das auf, was
dort tatsächlich registriert ist -- Name, Beschreibung, Berechtigungsstufe,
Parameter, Abhängigkeiten. Aufgerufen über ``python -m jarvis --generate-docs``.
"""

from __future__ import annotations

import json

from .tools.base import Registry, Tool
from .tools.catalog import availability


def _parameter_table(parameter_schema: dict) -> list[str]:
    required = set(parameter_schema.get("required") or [])
    properties: dict = parameter_schema.get("properties") or {}
    if not properties:
        return []
    zeilen = ["", "| Parameter | Pflicht | Beschreibung |", "|---|---|---|"]
    for name, schema in properties.items():
        pflicht = "ja" if name in required else "nein"
        beschreibung = (schema or {}).get("description", "").replace("\n", " ")
        zeilen.append(f"| `{name}` | {pflicht} | {beschreibung} |")
    return zeilen


def _tool_section(tool: Tool) -> str:
    # Aus tool.as_dict() statt jedes Feld hier einzeln erneut abzuschreiben --
    # ein Feld, das dort dazukommt, taucht sonst nie in der Referenz auf,
    # ohne dass jemand daran denkt, diese Datei mit zu pflegen.
    daten = tool.as_dict()
    zustand, grund = availability(tool)
    zeilen = [f"### `{daten['id']}`", "", daten["beschreibung"], "",
             f"- **Stufe:** {daten['stufe']} ({daten['risiko']})"]
    if daten["aliase"]:
        zeilen.append(f"- **Aliase:** {', '.join(f'`{a}`' for a in daten['aliase'])}")
    if daten["tags"]:
        zeilen.append(f"- **Tags:** {', '.join(daten['tags'])}")
    if daten["benoetigt"]:
        zeilen.append(f"- **Benötigt:** {', '.join(daten['benoetigt'])}")
    if daten["plattformen"]:
        zeilen.append(f"- **Plattformen:** {', '.join(daten['plattformen'])}")
    if daten["rueckgaengig"]:
        zeilen.append("- **Rückgängig machbar:** ja (`undo_last_action`)")
    if daten["probelauf"]:
        zeilen.append("- **Probelauf:** unterstützt (`dry_run: true`)")
    zeilen.append(f"- **Verfügbarkeit hier, jetzt geprüft:** {zustand.value}"
                  + (f" -- {grund}" if grund else ""))
    zeilen.extend(_parameter_table(daten["parameter"]))
    if daten["beispiele"]:
        zeilen.append("")
        zeilen.append("Beispiel:")
        zeilen.append("```json")
        zeilen.append(json.dumps(daten["beispiele"][0], ensure_ascii=False, indent=2))
        zeilen.append("```")
    zeilen.append("")
    return "\n".join(zeilen)


def generate(registry: Registry) -> str:
    """Die vollständige Referenz als ein Markdown-Dokument."""
    kategorien: dict[str, list[Tool]] = {}
    for tool in registry:
        kategorien.setdefault(tool.category, []).append(tool)

    kopf = [
        "# Werkzeugreferenz",
        "",
        f"Automatisch erzeugt aus der Registry -- **{len(registry)} Werkzeuge** in "
        f"**{len(kategorien)} Kategorien**. Nicht von Hand pflegen: "
        "`python -m jarvis --generate-docs` schreibt diese Datei neu, "
        "aus dem, was tatsächlich registriert ist.",
        "",
        "## Kategorien",
        "",
    ]
    for kategorie in sorted(kategorien):
        anzahl = len(kategorien[kategorie])
        kopf.append(f"- [{kategorie}](#{kategorie}) ({anzahl})")
    kopf.append("")

    teile = ["\n".join(kopf)]
    for kategorie in sorted(kategorien):
        teile.append(f"## {kategorie}\n")
        for tool in sorted(kategorien[kategorie], key=lambda t: t.name):
            teile.append(_tool_section(tool))
    return "\n".join(teile)
