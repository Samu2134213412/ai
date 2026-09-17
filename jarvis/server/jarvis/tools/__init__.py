"""Der Werkzeugkasten. Was hier nicht registriert ist, kann Jarvis nicht tun.

Genau das ist erwünscht: fehlt ein Werkzeug, sagt Jarvis „dafür habe ich kein
Tool" — statt sich etwas auszudenken.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..memory import MemoryStore
from ..undo import UndoContext, UndoStore
from . import codepilot, files, knowledge, shell, system
from . import undo as undo_tool
from .base import Registry, Tool, ToolError, ToolMissing, ToolResult

#: Werkzeuge, die vorgesehen, aber noch nicht gebaut sind. Die Oberfläche zeigt
#: sie als „fehlt", damit klar ist, was Jarvis heute wirklich kann.
PLANNED = ["screen_capture", "web_search", "mouse_keyboard", "open_program"]

__all__ = ["Registry", "Tool", "ToolError", "ToolMissing", "ToolResult",
           "build_registry", "tool_status", "PLANNED"]


def build_registry(config: Config, store: MemoryStore) -> Registry:
    registry = Registry()
    workspace = files.Workspace(config.roots)
    policy = shell.ShellPolicy(
        enabled=config.shell.enabled, allowlist=config.shell.allowlist,
        cwd=config.shell.cwd or (config.roots[0] if config.roots else None),
        timeout=config.shell.timeout)
    link = codepilot.CodePilotLink(
        url=config.codepilot.url, token=config.codepilot.token,
        project_id=config.codepilot.project_id, timeout=config.codepilot.timeout,
        autostart=config.codepilot.autostart, start_dir=config.codepilot.start_dir,
        start_timeout=config.codepilot.start_timeout,
        log_path=str(Path(config.home) / "codepilot-start.log"))
    undo_store = UndoStore(str(config.undo_db_path),
                          context=UndoContext(workspace=workspace, store=store))

    for tool in files.build(workspace):
        registry.add(tool)
    for tool in system.build():
        registry.add(tool)
    for tool in knowledge.build(store):
        registry.add(tool)
    for tool in undo_tool.build(undo_store):
        registry.add(tool)
    # Die beiden riskanten Werkzeuge kommen nur dazu, wenn sie eingerichtet
    # sind. Ein nicht registriertes Werkzeug ist ehrlicher als eines, das bei
    # jedem Aufruf scheitert.
    if config.shell.enabled:
        for tool in shell.build(policy):
            registry.add(tool)
    if link.configured:
        for tool in codepilot.build(link):
            registry.add(tool)
    # Für den Statusmelder in app.py: der Link existiert immer (auch
    # unkonfiguriert), status_snapshot() sagt dann einfach "configured: false".
    registry.codepilot_link = link
    # Für Agent._run_tool (Permission-Snapshots) und ggf. weitere Werkzeuge,
    # die denselben Arbeitsbereich/dieselbe Undo-Historie brauchen.
    registry.workspace = workspace
    registry.undo_store = undo_store
    return registry


def tool_status(registry: Registry, config: Config) -> list[dict[str, str]]:
    """Was die Oberfläche in der Werkzeugliste anzeigt."""
    rows = [{"name": name, "status": "ok"} for name in registry.names()]
    if not config.shell.enabled:
        rows.append({"name": "run_command", "status": "none"})
    if "codepilot_task" not in registry:
        rows.append({"name": "codepilot_task", "status": "none"})
    rows.extend({"name": name, "status": "none"} for name in PLANNED)
    return sorted(rows, key=lambda r: (r["status"] != "ok", r["name"]))
