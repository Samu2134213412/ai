"""Tool Pack: Desktop -- Bildschirm und Eingabegeräte.

Zwei der vier in ``PLANNED`` zurückgestellten Werkzeuge (siehe
``tools/__init__.py``): ein Bildschirmfoto machen (``desktop.screen.capture``)
und Maus/Tastatur steuern (``desktop.mouse.*``/``desktop.keyboard.*``).

Beide bewusst vorsichtiger eingestuft, als ihre Mechanik allein nahelegen
würde:

* ``desktop.screen.capture`` läuft auf WRITE statt READ. Ein Bildschirmfoto
  ist technisch ein Lesevorgang, kann aber alles zeigen, was gerade auf dem
  Bildschirm steht -- Passwörter, private Nachrichten, ein fremdes Fenster.
  READ läuft standardmäßig OHNE Bestätigung (``confirm_read: false``);
  genau das wäre hier die falsche Vorgabe.
* Maus/Tastatur laufen auf SYSTEM (Bestätigung standardmäßig an): sie können
  im Prinzip jede Anwendung auf dem Rechner bedienen, nicht nur eine, die
  Jarvis selbst kennt. PyAutoGUIs eingebaute Notbremse bleibt aktiv
  (``FAILSAFE``): die Maus in eine Bildschirmecke bewegen bricht jeden
  laufenden Aufruf sofort ab.

Kein neuer Automatisierungsdialekt: dieselben kleinen, benannten Operatoren
wie überall sonst -- Maus bewegen, klicken, Text tippen, eine Taste drücken
-- statt eines Skripts, das beliebigen Code ausführt.
"""

from __future__ import annotations


from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext
from ._base import NO_PARAMS, flag, integer, number, ok, params, planned, text

try:  # pragma: no cover
    from PIL import ImageGrab
except ImportError:  # pragma: no cover
    ImageGrab = None

try:  # pragma: no cover - siehe Begründung unten
    import pyautogui
    pyautogui.FAILSAFE = True
except Exception:  # noqa: BLE001 - PyAutoGUI scheitert ohne Bildschirm nicht
    # mit einem ImportError, sondern beim Verbindungsaufbau zu X11/Xlib
    # (Linux ohne DISPLAY) mit einer ganz anderen Ausnahme. Derselbe breite
    # Fang wie in catalog.Probe.check() für genau diesen Fall: ein Paket,
    # das sich nicht benutzen lässt, gilt als nicht vorhanden, nicht als
    # Programmabsturz.
    pyautogui = None


def _grab():
    if ImageGrab is None:
        raise ToolError("Dafür fehlt das Paket 'Pillow': pip install Pillow")
    return ImageGrab


def _automation():
    if pyautogui is None:
        raise ToolError(
            "Maus/Tastatur-Steuerung ist hier nicht verfügbar -- entweder fehlt "
            "das Paket 'PyAutoGUI' (pip install pyautogui), oder es gibt keinen "
            "Bildschirm/Display, den es steuern könnte.")
    return pyautogui


def _koordinate(automation, x: int, y: int) -> tuple[int, int]:
    """Prüft die Koordinate gegen die echte Bildschirmgröße -- ein Klick weit
    außerhalb des Bildschirms landet sonst irgendwo undefiniert, statt einer
    ehrlichen Fehlermeldung."""
    breite, hoehe = automation.size()
    if not (0 <= x < breite and 0 <= y < hoehe):
        raise ToolError(f"({x}, {y}) liegt außerhalb des Bildschirms ({breite}x{hoehe}).")
    return x, y


def _tasten_kombination(keys: str) -> list[str]:
    """Zerlegt "ctrl+shift+p" in ["ctrl","shift","p"] -- mit einem
    Sonderfall für das Plus-Zeichen selbst: "ctrl++" (Strg+Plus, ein
    verbreitetes Zoom-Kürzel) endet nach dem Zerlegen auf ein leeres
    letztes Element ("ctrl++".split("+") == ["ctrl","",""]), das ein
    einfacher Leerstring-Filter verschlucken würde -- die gemeinte letzte
    Taste ("+") verschwände dann spurlos statt gedrückt zu werden."""
    rohe = (keys or "").split("+")
    if rohe and rohe[-1] == "":
        rohe = rohe[:-1] + ["+"]
    return [k.strip() for k in rohe if k.strip()]


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    # ══════════════════════════════════════════════════════════ Bildschirm
    def screen_capture(path: str, overwrite: bool = False) -> ToolResult:
        grab = _grab()
        ziel = ws.resolve(path)
        if ziel.exists() and not overwrite:
            raise ToolError(f"Ziel existiert schon: {ziel}. Mit overwrite=true überschreiben.")
        try:
            bild = grab.grab()
        except Exception as exc:  # noqa: BLE001 - z. B. kein Display trotz Pillow
            raise ToolError(f"Bildschirmfoto fehlgeschlagen: {exc}") from exc
        ziel.parent.mkdir(parents=True, exist_ok=True)
        bild.save(ziel)
        breite, hoehe = bild.size
        return ok("desktop.screen.capture", f"Bildschirmfoto gespeichert: {ziel.name} "
                  f"({breite}x{hoehe})", pfad=str(ziel), breite=breite, hoehe=hoehe)

    # ══════════════════════════════════════════════════════════════ Maus
    def mouse_position() -> ToolResult:
        automation = _automation()
        x, y = automation.position()
        return ok("desktop.mouse.position", f"Maus steht bei ({x}, {y})", x=x, y=y)

    def mouse_move(x: int, y: int, duration: float = 0.0,
                   dry_run: bool = False) -> ToolResult:
        automation = _automation()
        ziel_x, ziel_y = _koordinate(automation, int(x), int(y))
        if dry_run:
            return planned("desktop.mouse.move", f"Würde die Maus zu ({ziel_x}, {ziel_y}) "
                          "bewegen", x=ziel_x, y=ziel_y)
        automation.moveTo(ziel_x, ziel_y, duration=max(0.0, min(float(duration or 0), 5.0)))
        return ok("desktop.mouse.move", f"Maus zu ({ziel_x}, {ziel_y}) bewegt",
                  x=ziel_x, y=ziel_y)

    def mouse_click(x: int, y: int, button: str = "left", clicks: int = 1,
                    dry_run: bool = False) -> ToolResult:
        automation = _automation()
        ziel_x, ziel_y = _koordinate(automation, int(x), int(y))
        taste = (button or "left").strip().lower()
        if taste not in {"left", "right", "middle"}:
            raise ToolError(f"Unbekannte Maustaste: {button!r} (erlaubt: left, right, middle)")
        # Kein "clicks or 1": das würde ein ausdrücklich angefordertes
        # clicks=0 stillschweigend zu einem echten Klick machen -- etwas
        # anderes tun als verlangt, statt es ehrlich abzulehnen.
        if not 1 <= int(clicks) <= 10:
            raise ToolError(f"clicks muss zwischen 1 und 10 liegen, nicht {clicks!r}.")
        anzahl = int(clicks)
        if dry_run:
            return planned("desktop.mouse.click",
                          f"Würde {anzahl}x {taste} bei ({ziel_x}, {ziel_y}) klicken",
                          x=ziel_x, y=ziel_y, taste=taste, anzahl=anzahl)
        automation.click(ziel_x, ziel_y, clicks=anzahl, button=taste)
        return ok("desktop.mouse.click", f"{anzahl}x {taste} bei ({ziel_x}, {ziel_y}) geklickt",
                  x=ziel_x, y=ziel_y, taste=taste, anzahl=anzahl)

    # ═══════════════════════════════════════════════════════════ Tastatur
    def keyboard_type(text: str, interval: float = 0.0, dry_run: bool = False) -> ToolResult:
        automation = _automation()
        inhalt = text or ""
        if not inhalt:
            raise ToolError("Kein Text angegeben.")
        if dry_run:
            return planned("desktop.keyboard.type",
                          f"Würde {len(inhalt)} Zeichen tippen", zeichen=len(inhalt))
        automation.write(inhalt, interval=max(0.0, min(float(interval or 0), 1.0)))
        return ok("desktop.keyboard.type", f"{len(inhalt)} Zeichen getippt",
                  zeichen=len(inhalt))

    def keyboard_press(keys: str, dry_run: bool = False) -> ToolResult:
        automation = _automation()
        kombination = _tasten_kombination(keys)
        if not kombination:
            raise ToolError("Keine Taste angegeben, z. B. 'enter' oder 'ctrl+c'.")
        if dry_run:
            return planned("desktop.keyboard.press", f"Würde drücken: {'+'.join(kombination)}",
                          tasten=kombination)
        if len(kombination) == 1:
            automation.press(kombination[0])
        else:
            automation.hotkey(*kombination)
        return ok("desktop.keyboard.press", f"Gedrückt: {'+'.join(kombination)}",
                  tasten=kombination)

    return [
        Tool("desktop.screen.capture", "Macht ein Bildschirmfoto und speichert es als Bild. "
             "Kann alles zeigen, was gerade auf dem Bildschirm steht -- absichtlich WRITE "
             "statt READ, damit es immer bestätigt wird.",
             params("path", path=text("Zielpfad für das Bild (z. B. foto.png)"),
                    overwrite=flag("Bestehendes Ziel überschreiben")),
             screen_capture, level=P.WRITE, requires=("pillow",),
             platforms=("windows", "darwin"), tags=("desktop", "bildschirm", "screenshot"),
             phrases=("mach ein bildschirmfoto", "screenshot")),
        Tool("desktop.mouse.position", "Wo die Maus gerade steht.", NO_PARAMS,
             mouse_position, level=P.READ, requires=("pyautogui",), tags=("desktop", "maus")),
        Tool("desktop.mouse.move", "Bewegt die Maus zu einer Bildschirmposition.",
             params("x", "y", x=integer("X-Koordinate in Pixeln"),
                    y=integer("Y-Koordinate in Pixeln"),
                    duration=number("Sekunden für die Bewegung, Vorgabe sofort"),
                    dry_run=flag("Nur zeigen, wohin sie bewegt würde")),
             mouse_move, level=P.SYSTEM, requires=("pyautogui",), dry_run=True,
             tags=("desktop", "maus", "automatisierung")),
        Tool("desktop.mouse.click", "Bewegt die Maus zu einer Position und klickt dort.",
             params("x", "y", x=integer("X-Koordinate in Pixeln"),
                    y=integer("Y-Koordinate in Pixeln"),
                    button=text("left/right/middle, Vorgabe left"),
                    clicks=integer("Anzahl Klicks, Vorgabe 1 (2 = Doppelklick)"),
                    dry_run=flag("Nur zeigen, was geklickt würde")),
             mouse_click, level=P.SYSTEM, requires=("pyautogui",), dry_run=True,
             tags=("desktop", "maus", "automatisierung")),
        Tool("desktop.keyboard.type", "Tippt Text, als käme er von der Tastatur -- ins "
             "gerade fokussierte Fenster, welches das auch immer ist.",
             params("text", text=text("Der zu tippende Text"),
                    interval=number("Sekunden zwischen den Zeichen, Vorgabe 0"),
                    dry_run=flag("Nur zeigen, was getippt würde")),
             keyboard_type, level=P.SYSTEM, requires=("pyautogui",), dry_run=True,
             tags=("desktop", "tastatur", "automatisierung")),
        Tool("desktop.keyboard.press", "Drückt eine Taste oder Tastenkombination, z. B. "
             "'enter' oder 'ctrl+c'.",
             params("keys", keys=text("Taste(n), mit '+' verbunden für eine Kombination"),
                    dry_run=flag("Nur zeigen, was gedrückt würde")),
             keyboard_press, level=P.SYSTEM, requires=("pyautogui",), dry_run=True,
             tags=("desktop", "tastatur", "automatisierung")),
    ]
