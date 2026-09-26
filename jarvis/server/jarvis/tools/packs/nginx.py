"""Tool Pack: nginx.

Starten/Stoppen/Neustarten des nginx-**Dienstes** übernimmt schon
``system.service.*`` (``sysinfo.py``, über systemd) -- das hier neu zu bauen
wäre dieselbe Funktion zweimal. Was hier steht, ist nginx-spezifisch:
Konfiguration prüfen, neu laden, Seiten ein-/ausschalten, Logs lesen.

Die Pfade (``/etc/nginx/...``) sind feste Systemorte, keine vom Nutzer
angegebenen Pfade -- deshalb laufen sie bewusst **nicht** durch
``Workspace.resolve`` (das ist für den freigegebenen Arbeitsbereich da, nicht
für Systemkonfiguration). Eine Konfigurationsänderung wird immer zuerst mit
``nginx -t`` geprüft, bevor sie geladen wird (Punkt 30: Probelauf vor
verändernden Aktionen).
"""

from __future__ import annotations

from pathlib import Path

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, run_process
from ._base import NO_PARAMS, integer, ok, params, table, text

MAX_OUTPUT = 20_000
KONFIG_ORDNER = Path("/etc/nginx")
VERFUEGBAR = KONFIG_ORDNER / "sites-available"
AKTIV = KONFIG_ORDNER / "sites-enabled"


def _clip(value: str) -> str:
    value = value or ""
    if len(value) <= MAX_OUTPUT:
        return value
    return value[:MAX_OUTPUT] + f"\n… gekürzt ({len(value) - MAX_OUTPUT} weitere Zeichen)"


def _kein_flag(value: str, label: str) -> str:
    wert = (value or "").strip()
    if not wert or "/" in wert or wert.startswith("."):
        raise ToolError(f"Kein gültiger Seitenname: {value!r}")
    return wert


def build(ctx: ToolContext) -> list[Tool]:

    def nginx_config_test() -> ToolResult:
        res = run_process(["nginx", "-t"], timeout=15)
        text_ausgabe = ((res.stdout or "") + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(text_ausgabe or "nginx -t fehlgeschlagen"))
        return ok("nginx.config.test", "Konfiguration ist gültig", payload=_clip(text_ausgabe))

    def nginx_reload() -> ToolResult:
        # Erst pruefen, dann laden -- ein kaputtes reload wuerde nginx mit der
        # alten Konfiguration weiterlaufen lassen, aber die Absicht war ja
        # gerade, die neue zu übernehmen. Besser vorher ehrlich scheitern.
        test = run_process(["nginx", "-t"], timeout=15)
        if test.returncode != 0:
            raise ToolError("Konfiguration ist ungültig, nicht neu geladen: "
                            + _clip(((test.stdout or "") + (test.stderr or "")).strip()))
        res = run_process(["nginx", "-s", "reload"], timeout=15)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "nginx -s reload fehlgeschlagen").strip()))
        return ok("nginx.reload", "Konfiguration neu geladen",
                  payload=_clip(((test.stdout or "") + (test.stderr or "")).strip()))

    def nginx_version() -> ToolResult:
        res = run_process(["nginx", "-v"], timeout=10)
        text_ausgabe = ((res.stdout or "") + (res.stderr or "")).strip()
        if res.returncode != 0:
            raise ToolError(_clip(text_ausgabe or "nginx -v fehlgeschlagen"))
        return ok("nginx.version", text_ausgabe, payload=text_ausgabe)

    def nginx_sites_list() -> ToolResult:
        if not VERFUEGBAR.is_dir():
            raise ToolError(f"{VERFUEGBAR} existiert nicht -- diese Distribution "
                            "verwendet vermutlich kein sites-available/sites-enabled-Layout.")
        aktive = {p.name for p in AKTIV.iterdir()} if AKTIV.is_dir() else set()
        rows = [[p.name, "aktiv" if p.name in aktive else "inaktiv"]
               for p in sorted(VERFUEGBAR.iterdir())]
        return ok("nginx.sites.list", f"{len(rows)} Seite(n), {len(aktive)} aktiv",
                  payload=table(rows, headers=["Seite", "Status"]), anzahl=len(rows))

    def nginx_site_enable(site: str) -> ToolResult:
        name = _kein_flag(site, "site")
        quelle = VERFUEGBAR / name
        if not quelle.is_file():
            raise ToolError(f"Nicht gefunden: {quelle}")
        ziel = AKTIV / name
        if ziel.exists():
            return ok("nginx.site.enable", f"{name} ist bereits aktiv", seite=name)
        AKTIV.mkdir(parents=True, exist_ok=True)
        ziel.symlink_to(quelle)
        return ok("nginx.site.enable", f"{name} aktiviert -- nginx.reload nicht vergessen",
                  seite=name)

    def nginx_site_disable(site: str) -> ToolResult:
        name = _kein_flag(site, "site")
        ziel = AKTIV / name
        if not ziel.exists():
            return ok("nginx.site.disable", f"{name} war nicht aktiv", seite=name)
        if not ziel.is_symlink():
            raise ToolError(f"{ziel} ist kein von nginx.site.enable angelegter Symlink -- "
                            "wird zur Sicherheit nicht angefasst.")
        ziel.unlink()
        return ok("nginx.site.disable", f"{name} deaktiviert -- nginx.reload nicht vergessen",
                  seite=name)

    def nginx_access_log_tail(lines: int = 50) -> ToolResult:
        datei = Path("/var/log/nginx/access.log")
        if not datei.is_file():
            raise ToolError(f"Nicht gefunden: {datei}")
        zeilen = datei.read_text(encoding="utf-8", errors="replace").splitlines()
        n = max(1, min(int(lines or 50), 1000))
        return ok("nginx.access_log.tail", f"Letzte {min(n, len(zeilen))} Zeile(n)",
                  payload=_clip("\n".join(zeilen[-n:])))

    def nginx_error_log_tail(lines: int = 50) -> ToolResult:
        datei = Path("/var/log/nginx/error.log")
        if not datei.is_file():
            raise ToolError(f"Nicht gefunden: {datei}")
        zeilen = datei.read_text(encoding="utf-8", errors="replace").splitlines()
        n = max(1, min(int(lines or 50), 1000))
        return ok("nginx.error_log.tail", f"Letzte {min(n, len(zeilen))} Zeile(n)",
                  payload=_clip("\n".join(zeilen[-n:])))

    return [
        Tool("nginx.config.test", "Prüft die nginx-Konfiguration auf Syntaxfehler, ohne "
             "etwas zu laden.",
             NO_PARAMS, nginx_config_test, level=P.READ, requires=("nginx",),
             tags=("nginx", "konfiguration"),
             phrases=("ist die nginx konfiguration okay", "nginx -t")),
        Tool("nginx.version", "Installierte nginx-Version.",
             NO_PARAMS, nginx_version, level=P.READ, requires=("nginx",), tags=("nginx",)),
        Tool("nginx.sites.list", "Verfügbare und aktive Seiten (sites-available/-enabled).",
             NO_PARAMS, nginx_sites_list, level=P.READ, requires=("nginx",),
             tags=("nginx", "seiten")),
        Tool("nginx.access_log.tail", "Die letzten Zeilen des Zugriffs-Logs.",
             params(lines=integer("Vorgabe 50")), nginx_access_log_tail, level=P.READ,
             requires=("nginx",), tags=("nginx", "log")),
        Tool("nginx.error_log.tail", "Die letzten Zeilen des Fehler-Logs.",
             params(lines=integer("Vorgabe 50")), nginx_error_log_tail, level=P.READ,
             requires=("nginx",), tags=("nginx", "log")),
        Tool("nginx.site.enable", "Aktiviert eine Seite (Symlink nach sites-enabled).",
             params("site", site=text("Dateiname in sites-available")), nginx_site_enable,
             level=P.WRITE, requires=("nginx",), tags=("nginx", "seiten")),
        Tool("nginx.site.disable", "Deaktiviert eine Seite (entfernt den Symlink).",
             params("site", site=text("Dateiname in sites-enabled")), nginx_site_disable,
             level=P.WRITE, requires=("nginx",), tags=("nginx", "seiten")),
        Tool("nginx.reload", "Prüft die Konfiguration und lädt sie bei Erfolg neu -- "
             "ohne Verbindungsabbrüche.",
             NO_PARAMS, nginx_reload, level=P.SYSTEM, requires=("nginx",),
             tags=("nginx", "konfiguration"),
             phrases=("lad die nginx konfiguration neu", "nginx reload")),
    ]
