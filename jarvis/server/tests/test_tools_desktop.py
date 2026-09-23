"""Das Desktop-Pack: Bildschirmfoto und Maus/Tastatur.

Ohne echten Bildschirm in der Testumgebung wird genau die eine Stelle
ersetzt, die einen braucht (``ImageGrab.grab()``/``pyautogui``), nicht der
Rest des Wegs -- ``screen_capture`` speichert ein echtes Pillow-Bild über
den echten Workspace, und die Maus/Tastatur-Aufrufe werden an einem
mitschreibenden Fake geprüft, nicht nur "hat nicht geworfen".
"""

from __future__ import annotations

import pytest
from PIL import Image

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult
from jarvis.tools.packs import desktop as desktop_pack


@pytest.fixture
def tools(config, store):
    registry = build_registry(config, store)

    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)

    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


def fehler(result: ToolResult) -> ToolResult:
    assert not result.ok, f"{result.tool} hätte fehlschlagen müssen: {result.summary}"
    return result


class FakeImageGrab:
    """Ersetzt nur den einen Schritt, der einen echten Bildschirm braucht --
    das zurückgegebene Bild ist ein echtes Pillow-Bild mit echtem .save()."""

    def __init__(self, groesse=(800, 600)):
        self.groesse = groesse
        self.aufrufe = 0

    def grab(self):
        self.aufrufe += 1
        return Image.new("RGB", self.groesse, color=(10, 20, 30))


class FakeAutomation:
    """Zeichnet jeden Aufruf auf -- Beleg statt Vermutung, auch im Test."""

    FAILSAFE = True

    def __init__(self, bildschirm=(1920, 1080), maus=(100, 100)):
        self._bildschirm = bildschirm
        self._maus = maus
        self.aufrufe: list[tuple[str, tuple, dict]] = []

    def size(self):
        return self._bildschirm

    def position(self):
        return self._maus

    def moveTo(self, x, y, duration=0.0):
        self.aufrufe.append(("moveTo", (x, y), {"duration": duration}))
        self._maus = (x, y)

    def click(self, x, y, clicks=1, button="left"):
        self.aufrufe.append(("click", (x, y), {"clicks": clicks, "button": button}))
        self._maus = (x, y)

    def write(self, text, interval=0.0):
        self.aufrufe.append(("write", (text,), {"interval": interval}))

    def press(self, key):
        self.aufrufe.append(("press", (key,), {}))

    def hotkey(self, *keys):
        self.aufrufe.append(("hotkey", keys, {}))


@pytest.fixture
def fake_grab(monkeypatch):
    fake = FakeImageGrab()
    monkeypatch.setattr(desktop_pack, "ImageGrab", fake)
    return fake


@pytest.fixture
def fake_automation(monkeypatch):
    fake = FakeAutomation()
    monkeypatch.setattr(desktop_pack, "pyautogui", fake)
    return fake


# ═══════════════════════════════════════════════════════ desktop.screen.capture
def test_screen_capture_speichert_ein_echtes_bild(tools, workspace, fake_grab):
    res = erfolg(tools("desktop.screen.capture", path="foto.png"))
    ziel = workspace / "foto.png"
    assert ziel.is_file()
    assert res.evidence["breite"] == 800
    assert res.evidence["hoehe"] == 600
    with Image.open(ziel) as bild:
        assert bild.size == (800, 600)


def test_screen_capture_ohne_overwrite_lehnt_bestehendes_ziel_ab(tools, workspace, fake_grab):
    (workspace / "foto.png").write_bytes(b"schon da")
    fehler(tools("desktop.screen.capture", path="foto.png"))


def test_screen_capture_mit_overwrite_ersetzt(tools, workspace, fake_grab):
    (workspace / "foto.png").write_bytes(b"schon da")
    erfolg(tools("desktop.screen.capture", path="foto.png", overwrite=True))
    with Image.open(workspace / "foto.png") as bild:
        assert bild.size == (800, 600)


def test_screen_capture_ohne_pillow_meldet_fehlende_abhaengigkeit(tools, monkeypatch):
    monkeypatch.setattr(desktop_pack, "ImageGrab", None)
    res = fehler(tools("desktop.screen.capture", path="foto.png"))
    assert "Pillow" in res.summary


# ══════════════════════════════════════════════════════════ desktop.mouse.*
def test_mouse_position_liest_echten_stand(tools, fake_automation):
    res = erfolg(tools("desktop.mouse.position"))
    assert (res.evidence["x"], res.evidence["y"]) == (100, 100)


def test_mouse_move_bewegt_wirklich(tools, fake_automation):
    erfolg(tools("desktop.mouse.move", x=500, y=300))
    assert fake_automation.aufrufe == [("moveTo", (500, 300), {"duration": 0.0})]


def test_mouse_move_dry_run_bewegt_nichts(tools, fake_automation):
    res = tools("desktop.mouse.move", x=500, y=300, dry_run=True)
    assert res.ok
    assert res.evidence.get("probelauf") is True
    assert fake_automation.aufrufe == []


def test_mouse_move_ausserhalb_des_bildschirms_wird_abgelehnt(tools, fake_automation):
    fehler(tools("desktop.mouse.move", x=5000, y=5000))
    assert fake_automation.aufrufe == []


def test_mouse_click_klickt_wirklich(tools, fake_automation):
    erfolg(tools("desktop.mouse.click", x=10, y=20, button="right", clicks=2))
    assert fake_automation.aufrufe == [("click", (10, 20), {"clicks": 2, "button": "right"})]


def test_mouse_click_unbekannte_taste_wird_abgelehnt(tools, fake_automation):
    fehler(tools("desktop.mouse.click", x=10, y=20, button="mitte-links-oben"))
    assert fake_automation.aufrufe == []


def test_mouse_click_mit_null_klicks_wird_abgelehnt(tools, fake_automation):
    # clicks=0 heißt "kein Klick" -- das ehrlich ablehnen statt es
    # stillschweigend zu einem echten Klick zu machen (int(clicks or 1)
    # würde genau das tun).
    fehler(tools("desktop.mouse.click", x=10, y=20, clicks=0))
    assert fake_automation.aufrufe == []


def test_mouse_click_mit_zu_vielen_klicks_wird_abgelehnt(tools, fake_automation):
    fehler(tools("desktop.mouse.click", x=10, y=20, clicks=11))
    assert fake_automation.aufrufe == []


def test_mouse_ohne_pyautogui_meldet_fehlende_abhaengigkeit(tools, monkeypatch):
    monkeypatch.setattr(desktop_pack, "pyautogui", None)
    res = fehler(tools("desktop.mouse.position"))
    assert "PyAutoGUI" in res.summary


# ═══════════════════════════════════════════════════════ desktop.keyboard.*
def test_keyboard_type_tippt_wirklich(tools, fake_automation):
    erfolg(tools("desktop.keyboard.type", text="hallo welt"))
    assert fake_automation.aufrufe == [("write", ("hallo welt",), {"interval": 0.0})]


def test_keyboard_type_leerer_text_wird_abgelehnt(tools, fake_automation):
    fehler(tools("desktop.keyboard.type", text=""))
    assert fake_automation.aufrufe == []


def test_keyboard_press_einzelne_taste(tools, fake_automation):
    erfolg(tools("desktop.keyboard.press", keys="enter"))
    assert fake_automation.aufrufe == [("press", ("enter",), {})]


def test_keyboard_press_kombination_wird_zu_hotkey(tools, fake_automation):
    erfolg(tools("desktop.keyboard.press", keys="ctrl+c"))
    assert fake_automation.aufrufe == [("hotkey", ("ctrl", "c"), {})]


def test_keyboard_press_dry_run_drueckt_nichts(tools, fake_automation):
    res = tools("desktop.keyboard.press", keys="ctrl+c", dry_run=True)
    assert res.ok
    assert res.evidence.get("probelauf") is True
    assert fake_automation.aufrufe == []


def test_keyboard_press_strg_plus_wird_nicht_verschluckt(tools, fake_automation):
    # "ctrl++" (Strg+Plus, verbreitetes Zoom-Kürzel) zerlegt sich naiv zu
    # ["ctrl", "", ""] -- ein einfacher Leerstring-Filter würde die gemeinte
    # letzte Taste ("+") spurlos verschlucken statt sie zu drücken.
    erfolg(tools("desktop.keyboard.press", keys="ctrl++"))
    assert fake_automation.aufrufe == [("hotkey", ("ctrl", "+"), {})]


def test_keyboard_press_nur_plus_ist_eine_einzelne_taste(tools, fake_automation):
    erfolg(tools("desktop.keyboard.press", keys="+"))
    assert fake_automation.aufrufe == [("press", ("+",), {})]
