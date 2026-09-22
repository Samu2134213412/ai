"""Das Produktivitäts-Pack: reine Berechnungen, kein externer Zustand --
läuft deshalb vollständig echt, kein Mock nötig."""

from __future__ import annotations

import shutil

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult


@pytest.fixture
def tools(config, store):
    registry = build_registry(config, store)

    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)

    call.registry = registry
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


def fehler(result: ToolResult) -> ToolResult:
    assert not result.ok, f"{result.tool} hätte fehlschlagen müssen: {result.summary}"
    return result


# ═══════════════════════════════════════════════════════════════ calculate
@pytest.mark.parametrize("ausdruck,erwartet", [
    ("2 + 2", 4), ("(3 + 4) * 2", 14), ("2 ** 10", 1024), ("10 // 3", 3),
    ("10 % 3", 1), ("-5 + 2", -3), ("pi", pytest.approx(3.14159, abs=1e-4)),
])
def test_calculate_richtige_ergebnisse(tools, ausdruck, erwartet):
    res = erfolg(tools("productivity.calculate", expression=ausdruck))
    assert res.evidence["ergebnis"] == erwartet


@pytest.mark.parametrize("ausdruck", [
    "__import__('os')", "1 .__class__", "open('x')", "[1,2,3]", "1; 2",
])
def test_calculate_verweigert_alles_ausser_arithmetik(tools, ausdruck):
    fehler(tools("productivity.calculate", expression=ausdruck))


def test_calculate_division_durch_null(tools):
    fehler(tools("productivity.calculate", expression="1/0"))


# ═══════════════════════════════════════════════════════════════ unit.convert
def test_unit_convert_laenge(tools):
    res = erfolg(tools("productivity.unit.convert", value=1, from_unit="km", to_unit="m"))
    assert res.evidence["ergebnis"] == 1000


def test_unit_convert_temperatur(tools):
    res = erfolg(tools("productivity.unit.convert", value=0, from_unit="c", to_unit="f"))
    assert res.evidence["ergebnis"] == 32.0
    res2 = erfolg(tools("productivity.unit.convert", value=100, from_unit="c", to_unit="k"))
    assert res2.evidence["ergebnis"] == pytest.approx(373.15)


def test_unit_convert_unpassende_einheiten(tools):
    fehler(tools("productivity.unit.convert", value=1, from_unit="km", to_unit="kg"))
    fehler(tools("productivity.unit.convert", value=1, from_unit="unsinn", to_unit="m"))


# ═══════════════════════════════════════════════════════════════ color.convert
def test_color_convert_hex_zu_rgb_hsl(tools):
    res = erfolg(tools("productivity.color.convert", value="#ff0000"))
    assert res.evidence["rgb"] == [255, 0, 0]
    assert res.evidence["hsl"] == [0, 100, 50]


def test_color_convert_kurzform_und_rgb_eingabe(tools):
    kurz = erfolg(tools("productivity.color.convert", value="#0f0"))
    assert kurz.evidence["rgb"] == [0, 255, 0]
    voll = erfolg(tools("productivity.color.convert", value="rgb(0, 255, 0)"))
    assert voll.evidence["hex"] == "#00ff00"


def test_color_convert_ungueltig(tools):
    fehler(tools("productivity.color.convert", value="banane"))


# ═══════════════════════════════════════════════════════════════ passphrase
def test_passphrase_generate_anzahl_und_trennzeichen(tools):
    res = erfolg(tools("productivity.passphrase.generate", words=6, separator="_"))
    assert res.evidence["woerter"] == 6
    assert res.payload.count("_") == 5


def test_passphrase_generate_grossschreibung(tools):
    res = erfolg(tools("productivity.passphrase.generate", words=4, capitalize=True))
    teile = res.payload.split("-")
    assert all(t[0].isupper() for t in teile)


# ═══════════════════════════════════════════════════════════════ lorem
def test_lorem_generate_anzahl_woerter(tools):
    res = erfolg(tools("productivity.lorem.generate", words=25))
    assert res.evidence["woerter"] == 25
    assert len(res.payload.split()) == 25


# ═══════════════════════════════════════════════════════════════ date
def test_date_diff(tools):
    res = erfolg(tools("productivity.date.diff", date_a="2026-01-01", date_b="2026-01-11"))
    assert res.evidence["tage"] == 10


def test_date_diff_rueckwaerts(tools):
    res = erfolg(tools("productivity.date.diff", date_a="2026-01-11", date_b="2026-01-01"))
    assert res.evidence["tage"] == -10


def test_date_add_monatsuebergang(tools):
    res = erfolg(tools("productivity.date.add", date="2026-01-31", days=1))
    assert res.evidence["datum"] == "2026-02-01"


def test_date_add_wochentag_ist_deutsch(tools):
    res = erfolg(tools("productivity.date.add", date="2026-09-21", days=0))
    assert res.evidence["wochentag"] == "Montag"


def test_date_ungueltiges_format(tools):
    fehler(tools("productivity.date.diff", date_a="21.13.2026", date_b="2026-01-01"))


# ═══════════════════════════════════════════════════════════════ timezone
def test_timezone_convert(tools):
    res = erfolg(tools("productivity.timezone.convert", value="2026-06-15T12:00:00",
                       from_zone="UTC", to_zone="America/New_York"))
    assert "08:00:00" in res.summary


def test_timezone_convert_unbekannte_zone(tools):
    fehler(tools("productivity.timezone.convert", value="2026-06-15T12:00:00",
                 from_zone="UTC", to_zone="Mars/Olympus_Mons"))


# ═══════════════════════════════════════════════════════════════ number.to_words
@pytest.mark.parametrize("zahl,erwartet", [
    (0, "null"), (1, "eins"), (21, "einundzwanzig"), (100, "einhundert"),
    (1000, "eintausend"), (1001, "eintausendeins"),
    (1000000, "eine Million"), (1000001, "eine Million eins"),
    (-7, "minus sieben"),
])
def test_number_to_words(tools, zahl, erwartet):
    res = erfolg(tools("productivity.number.to_words", value=zahl))
    assert res.payload == erwartet


# ═══════════════════════════════════════════════════════════════ roman
def test_roman_convert_beide_richtungen(tools):
    hin = erfolg(tools("productivity.roman.convert", value="1994"))
    assert hin.payload == "MCMXCIV"
    zurueck = erfolg(tools("productivity.roman.convert", value="MCMXCIV"))
    assert zurueck.payload == "1994"


def test_roman_convert_grenzen(tools):
    fehler(tools("productivity.roman.convert", value="0"))
    fehler(tools("productivity.roman.convert", value="4000"))
    fehler(tools("productivity.roman.convert", value="ABCXYZ"))


# ═══════════════════════════════════════════════════════════════ base.convert
def test_base_convert(tools):
    res = erfolg(tools("productivity.base.convert", value="255", from_base=10, to_base=16))
    assert res.evidence["ergebnis"] == "ff"
    zurueck = erfolg(tools("productivity.base.convert", value="ff", from_base=16, to_base=10))
    assert zurueck.evidence["ergebnis"] == "255"


def test_base_convert_ungueltige_basis(tools):
    fehler(tools("productivity.base.convert", value="1", from_base=1, to_base=10))
    fehler(tools("productivity.base.convert", value="xyz", from_base=10, to_base=2))


# ═══════════════════════════════════════════════════════════════ qrcode
_hat_qrcode = True
try:
    import qrcode  # noqa: F401
except ImportError:
    _hat_qrcode = False


@pytest.mark.skipif(not _hat_qrcode, reason="qrcode nicht installiert")
def test_qrcode_generate(tools, workspace):
    res = erfolg(tools("productivity.qrcode.generate", text="https://example.invalid",
                       output="code.png"))
    assert (workspace / "code.png").exists()
    assert res.evidence["zeichen"] > 0


def test_qrcode_generate_leerer_text_wird_abgelehnt(tools):
    if not _hat_qrcode:
        pytest.skip("qrcode nicht installiert")
    fehler(tools("productivity.qrcode.generate", text="", output="leer.png"))


def test_qrcode_ohne_overwrite_wird_abgelehnt(tools, workspace):
    if not _hat_qrcode:
        pytest.skip("qrcode nicht installiert")
    (workspace / "belegt.png").write_bytes(b"x")
    fehler(tools("productivity.qrcode.generate", text="x", output="belegt.png"))


# ═══════════════════════════════════════════════════════════════ automation.wait
def test_automation_wait_wartet_wirklich(tools):
    import time
    start = time.monotonic()
    res = erfolg(tools("automation.wait", seconds=0.3))
    dauer = time.monotonic() - start
    assert dauer >= 0.25
    assert res.evidence["sekunden"] == 0.3


def test_automation_wait_wird_auf_maximum_begrenzt(tools):
    res = erfolg(tools("automation.wait", seconds=0.01))
    assert res.evidence["sekunden"] == 0.01
