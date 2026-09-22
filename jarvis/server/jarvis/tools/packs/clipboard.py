"""Tool Pack: Zwischenablage.

Es gibt kein plattformübergreifendes Kommandozeilenprogramm für die
Zwischenablage -- deshalb hier eine kleine Werkzeugkette je Betriebssystem
(Windows: PowerShell, macOS: pbcopy/pbpaste, Linux: xclip, dann xsel, dann
wl-clipboard, je nachdem was da ist). Auf einem Server ohne grafische Sitzung
(kein ``DISPLAY``/``WAYLAND_DISPLAY`` unter Linux) gibt es schlicht keine
Zwischenablage zum Anfassen -- das wird ehrlich gemeldet, nicht stillschweigend
übergangen.
"""

from __future__ import annotations

import os

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, current_platform, run_process
from ._base import NO_PARAMS, ok, params, text

MAX_LEN = 100_000


def _kein_grafische_sitzung() -> bool:
    return (current_platform() == "linux"
            and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"))


def _lese_befehl() -> list[str] | None:
    import shutil
    system = current_platform()
    if system == "windows":
        return ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"]
    if system == "darwin":
        return ["pbpaste"]
    if system == "linux":
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard", "-o"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--output"]
        if shutil.which("wl-paste"):
            return ["wl-paste", "--no-newline"]
    return None


def _schreib_befehl() -> list[str] | None:
    import shutil
    system = current_platform()
    if system == "windows":
        return ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"]
    if system == "darwin":
        return ["pbcopy"]
    if system == "linux":
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--input"]
        if shutil.which("wl-copy"):
            return ["wl-copy"]
    return None


def _kein_werkzeug_fehler() -> ToolError:
    if _kein_grafische_sitzung():
        return ToolError("Keine grafische Sitzung erkannt (DISPLAY/WAYLAND_DISPLAY "
                         "nicht gesetzt) -- ein Server ohne Desktop hat keine "
                         "Zwischenablage zum Anfassen.")
    hinweis = {"linux": "installiere xclip, xsel oder wl-clipboard",
              "darwin": "pbcopy/pbpaste sollten immer vorhanden sein -- ungewöhnlich",
              "windows": "PowerShell sollte immer vorhanden sein -- ungewöhnlich"
              }.get(current_platform(), "unbekannte Plattform")
    return ToolError(f"Kein Werkzeug für die Zwischenablage gefunden ({hinweis}).")


def build(ctx: ToolContext) -> list[Tool]:

    def clipboard_read() -> ToolResult:
        befehl = _lese_befehl()
        if not befehl:
            raise _kein_werkzeug_fehler()
        res = run_process(befehl, timeout=10)
        if res.returncode != 0:
            raise ToolError((res.stderr or "Zwischenablage nicht lesbar").strip()[:500])
        inhalt = (res.stdout or "")[:MAX_LEN]
        return ok("clipboard.read", f"{len(inhalt)} Zeichen gelesen" if inhalt
                  else "Zwischenablage ist leer", payload=inhalt or "(leer)",
                  zeichen=len(inhalt))

    def clipboard_write(text: str) -> ToolResult:
        befehl = _schreib_befehl()
        if not befehl:
            raise _kein_werkzeug_fehler()
        inhalt = text or ""
        res = run_process(befehl, timeout=10, stdin_text=inhalt)
        if res.returncode != 0:
            raise ToolError((res.stderr or "Zwischenablage nicht beschreibbar").strip()[:500])
        # Nachpruefen statt annehmen: sofort zuruecklesen und vergleichen.
        lese = _lese_befehl()
        if lese:
            kontrolle = run_process(lese, timeout=10)
            if kontrolle.returncode == 0 and (kontrolle.stdout or "") != inhalt:
                raise ToolError("Zwischenablage enthält nach dem Schreiben einen "
                                "anderen Inhalt als erwartet.")
        return ok("clipboard.write", f"{len(inhalt)} Zeichen in die Zwischenablage "
                  "geschrieben", zeichen=len(inhalt))

    def clipboard_clear() -> ToolResult:
        return clipboard_write("")

    def clipboard_has_content() -> ToolResult:
        befehl = _lese_befehl()
        if not befehl:
            raise _kein_werkzeug_fehler()
        res = run_process(befehl, timeout=10)
        if res.returncode != 0:
            raise ToolError((res.stderr or "Zwischenablage nicht lesbar").strip()[:500])
        vorhanden = bool((res.stdout or "").strip())
        return ok("clipboard.has_content", "Zwischenablage enthält Text" if vorhanden
                  else "Zwischenablage ist leer", vorhanden=vorhanden)

    return [
        Tool("clipboard.read", "Liest den aktuellen Textinhalt der Zwischenablage.",
             NO_PARAMS, clipboard_read, level=P.READ, tags=("zwischenablage",),
             phrases=("was steht in der zwischenablage", "zwischenablage lesen")),
        Tool("clipboard.has_content", "Prüft, ob die Zwischenablage Text enthält, ohne "
             "ihn im Verlauf anzuzeigen.",
             NO_PARAMS, clipboard_has_content, level=P.SAFE, tags=("zwischenablage",)),
        Tool("clipboard.write", "Schreibt Text in die Zwischenablage.",
             params("text", text=text("Der zu kopierende Text")), clipboard_write,
             level=P.WRITE, tags=("zwischenablage",),
             phrases=("kopier das in die zwischenablage",)),
        Tool("clipboard.clear", "Leert die Zwischenablage.",
             NO_PARAMS, clipboard_clear, level=P.WRITE, tags=("zwischenablage",)),
    ]
