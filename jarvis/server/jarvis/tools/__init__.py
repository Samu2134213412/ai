"""Der Werkzeugkasten. Was hier nicht registriert ist, kann Jarvis nicht tun.

Genau das ist erwünscht: fehlt ein Werkzeug, sagt Jarvis „dafür habe ich kein
Tool" — statt sich etwas auszudenken.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..macros import MacroStore
from ..memory import MemoryStore
from ..undo import UndoContext, UndoStore
from . import files, knowledge, shell, system
from . import undo as undo_tool
from .base import Registry, Tool, ToolError, ToolMissing, ToolResult
from .catalog import Availability, ToolContext, availability, dependency_report, runnable
from .discovery import ToolDiscovery, ToolIndex
from .history import ToolHistory
from .packs import PACKS
from .packs import meta as meta_pack

#: Werkzeuge, die vorgesehen, aber noch nicht gebaut sind. Die Oberfläche zeigt
#: sie als „fehlt", damit klar ist, was Jarvis heute wirklich kann.
#: Die letzten vier (screen_capture, web_search, mouse_keyboard, open_program)
#: sind jetzt gebaut -- als desktop.screen.capture, search.web,
#: desktop.mouse.*/desktop.keyboard.* und search.apps.open (siehe
#: tools/packs/desktop.py und tools/packs/search.py).
PLANNED: list[str] = []

__all__ = ["Registry", "Tool", "ToolError", "ToolMissing", "ToolResult",
           "ToolContext", "ToolDiscovery", "ToolIndex", "ToolHistory",
           "Availability", "availability", "dependency_report",
           "build_registry", "tool_status", "PLANNED"]


def build_registry(config: Config, store: MemoryStore,
                   history: ToolHistory | None = None) -> Registry:
    registry = Registry()
    workspace = files.Workspace(config.roots)
    policy = shell.ShellPolicy(
        enabled=config.shell.enabled, allowlist=config.shell.allowlist,
        cwd=config.shell.cwd or (config.roots[0] if config.roots else None),
        timeout=config.shell.timeout)
    # Dieselbe Policy, die run_command (falls registriert) tatsächlich befragt --
    # so früh gesetzt, dass sie schon dasteht, wenn jarvis.shell.enable/disable
    # (meta.py) gebaut wird. Es schaltet sie zur Laufzeit um, statt einer
    # zweiten, unabhängigen Kopie der Einstellungen (Punkt 56).
    registry.shell_policy = policy
    undo_store = UndoStore(str(config.undo_db_path),
                          context=UndoContext(workspace=workspace, store=store))
    macro_store = MacroStore(str(config.macro_db_path))
    history = history or ToolHistory(str(config.tool_history_db_path))

    for tool in files.build(workspace):
        registry.add(tool)
    for tool in system.build():
        registry.add(tool)
    for tool in knowledge.build(store):
        registry.add(tool)
    for tool in undo_tool.build(undo_store):
        registry.add(tool)
    # Die Shell kommt nur dazu, wenn sie eingerichtet ist. Ein nicht
    # registriertes Werkzeug ist ehrlicher als eines, das bei jedem Aufruf
    # scheitert.
    if config.shell.enabled:
        for tool in shell.build(policy):
            registry.add(tool)
    # ── Die Tool-Packs (Punkt 38: nicht alles hart im Kern) ──────────────
    # Jedes Pack bekommt denselben ToolContext und gibt eine Liste zurück.
    # Ein Pack, das beim Bauen scheitert, darf die übrigen nicht mitreißen --
    # dann fehlen seine Werkzeuge eben, und das steht in ``registry.pack_errors``
    # statt den ganzen Server am Start zu zerlegen.
    context = ToolContext(config=config, store=store, workspace=workspace,
                          home=Path(config.home),
                          services={"undo": undo_store, "history": history,
                                    "macros": macro_store})
    registry.pack_errors: dict[str, str] = {}
    for name, builder in PACKS:
        try:
            registry.extend(builder(context))
        except Exception as exc:  # noqa: BLE001 - siehe oben
            registry.pack_errors[name] = f"{type(exc).__name__}: {exc}"

    # ── Suchindex + jarvis.tools.* (Punkt 34/35/36) ───────────────────────
    # Erst jetzt, mit der fertigen Registry: der Suchindex braucht alle
    # Werkzeuge, die es gibt, und die jarvis.tools.*-Werkzeuge (Suche,
    # Favoriten, Verlauf) brauchen wiederum den Suchindex. Ein normaler Pack
    # bekommt absichtlich nur den ToolContext und keinen Zugriff auf die
    # Registry selbst (siehe packs/__init__.py) -- dieser eine Sonderfall
    # (Introspektion über den Werkzeugkasten) braucht sie zwangsläufig und
    # bekommt sie deshalb gezielt über ``services`` statt über die üblichen
    # ToolContext-Felder.
    discovery = ToolDiscovery(registry, history=history)
    meta_context = ToolContext(config=config, store=store, workspace=workspace,
                               home=Path(config.home),
                               services={**context.services, "registry": registry,
                                        "discovery": discovery})
    try:
        neue_werkzeuge = meta_pack.build(meta_context)
        registry.extend(neue_werkzeuge)
        # Einzeln nachgetragen statt discovery.index.rebuild(): der Index
        # wurde gerade erst über den ganzen (noch unvollständigen) Katalog
        # aufgebaut -- ein voller rebuild() hier würde alle ~390 bereits
        # indizierten Werkzeuge ein zweites Mal berechnen, nur um die
        # Handvoll jarvis.tools.* mit aufzunehmen.
        for tool in neue_werkzeuge:
            discovery.index.add(tool)
    except Exception as exc:  # noqa: BLE001 - siehe oben
        registry.pack_errors["meta"] = f"{type(exc).__name__}: {exc}"

    # Für Agent._run_tool (Permission-Snapshots) und ggf. weitere Werkzeuge,
    # die denselben Arbeitsbereich/dieselbe Undo-Historie brauchen.
    registry.workspace = workspace
    registry.undo_store = undo_store
    registry.macro_store = macro_store
    registry.tool_history = history
    registry.discovery = discovery
    registry.context = context
    return registry


#: Reihenfolge in der Oberfläche: was sich beheben lässt, zuerst -- bei
#: mehreren hundert grünen Einträgen gingen die übrigen am Ende sonst unter.
_STATUS_REIHENFOLGE = {"dep": 0, "off": 1, "none": 2, "os": 3, "ok": 4}


def tool_status(registry: Registry, config: Config) -> list[dict[str, str]]:
    """Was die Oberfläche in der Werkzeugliste anzeigt -- der echte Zustand
    auf DIESEM Rechner (``catalog.availability``), nicht bloß "ist
    registriert". Ein Werkzeug, dem ein Programm fehlt, ist nicht "bereit",
    nur weil es gebaut ist.

    ``ok`` läuft · ``dep`` fehlende Abhängigkeit · ``os`` falsches
    Betriebssystem · ``off`` vom Nutzer abgeschaltet · ``none`` aus bzw.
    nicht gebaut. Alles außer ``ok`` trägt einen ``grund``.
    """
    history = getattr(registry, "tool_history", None)
    abgeschaltet = history.disabled() if history is not None else {}
    rows: list[dict[str, str]] = []
    for tool in registry:
        zustand, grund = availability(tool)
        if tool.name in abgeschaltet:
            status = "off"
            grund = ("Von dir abgeschaltet"
                     + (f" ({abgeschaltet[tool.name]})" if abgeschaltet[tool.name] else "")
                     + " -- jarvis.tools.enable schaltet es wieder an.")
        elif runnable(tool):
            status, grund = "ok", ""
        elif zustand is Availability.MISSING_DEPENDENCY:
            status = "dep"
        elif zustand is Availability.UNSUPPORTED_PLATFORM:
            status = "os"
        else:
            status = "none"
        rows.append({"name": tool.name, "status": status, **({"grund": grund} if grund else {})})
    if not config.shell.enabled:
        rows.append({"name": "run_command", "status": "none",
                     "grund": "Aus per Voreinstellung -- jarvis.shell.enable schaltet es an."})
    rows.extend({"name": name, "status": "none", "grund": "Noch nicht gebaut."}
                for name in PLANNED)
    return sorted(rows, key=lambda r: (_STATUS_REIHENFOLGE[r["status"]], r["name"]))
