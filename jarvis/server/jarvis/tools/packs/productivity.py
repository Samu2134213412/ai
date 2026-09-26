"""Tool Pack: Produktivität.

Was schon existiert, steht hier bewusst nicht nochmal: Passwort/UUID/Hash
und Zeitstempel-Umrechnung liegen bereits in ``text.py`` (``text.password.
generate``, ``text.uuid``, ``text.hash``, ``text.timestamp.*``), eine
schnelle Notiz ist bereits ``memory_add`` (``knowledge.py``). Neu ist hier,
was dort fehlt: ein Taschenrechner ohne ``eval`` (ein eigener, kleiner
AST-Auswerter, der nur Rechenoperationen zulässt -- keine Funktionsaufrufe,
keine Attributzugriffe, also auch keine Ausbruchsmöglichkeit), Einheiten-
und Farbumrechnung, Datumsarithmetik, ein Passphrasen-Generator mit
eingebauter Wortliste (kein `/usr/share/dict/words`, das auf vielen Systemen
gar nicht existiert) und QR-Codes.
"""

from __future__ import annotations

import ast
import datetime as dt
import operator
import random
import re
import time

from ...macros import MacroError, validate_steps
from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext
from ._base import NO_PARAMS, flag, integer, number, ok, params, table, text

try:  # pragma: no cover
    import qrcode
except ImportError:  # pragma: no cover
    qrcode = None

try:  # pragma: no cover
    from zoneinfo import ZoneInfo, available_timezones
except ImportError:  # pragma: no cover - Python < 3.9, hier nicht relevant
    ZoneInfo = None
    available_timezones = None


# ══════════════════════════════════════════════════════════ Taschenrechner
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_KONSTANTEN = {"pi": 3.141592653589793, "e": 2.718281828459045}

_STEPS = {"type": "array", "items": {"type": "object"},
         "description": "Liste von Makro-Schritten (kind: tool/if/loop/parallel/wait), "
                        "siehe macros.py für das genaue Format."}


def _auswerten(knoten: ast.AST) -> float:
    if isinstance(knoten, ast.Expression):
        return _auswerten(knoten.body)
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, (int, float)):
        return knoten.value
    if isinstance(knoten, ast.Name) and knoten.id in _KONSTANTEN:
        return _KONSTANTEN[knoten.id]
    if isinstance(knoten, ast.BinOp) and type(knoten.op) in _OPS:
        if isinstance(knoten.op, ast.Pow):
            exponent = _auswerten(knoten.right)
            if abs(exponent) > 1000:
                raise ToolError("Exponent zu groß.")
        return _OPS[type(knoten.op)](_auswerten(knoten.left), _auswerten(knoten.right))
    if isinstance(knoten, ast.UnaryOp) and type(knoten.op) in _OPS:
        return _OPS[type(knoten.op)](_auswerten(knoten.operand))
    raise ToolError(f"Nicht erlaubter Ausdrucksteil: {ast.dump(knoten)[:80]}")


def build(ctx: ToolContext) -> list[Tool]:

    def calculate(expression: str) -> ToolResult:
        ausdruck = (expression or "").strip()
        if not ausdruck:
            raise ToolError("Kein Ausdruck angegeben.")
        if len(ausdruck) > 200:
            raise ToolError("Ausdruck zu lang.")
        try:
            baum = ast.parse(ausdruck, mode="eval")
            ergebnis = _auswerten(baum)
        except (SyntaxError, ZeroDivisionError, OverflowError, ToolError) as exc:
            raise ToolError(f"Kann nicht ausgewertet werden: {exc}") from exc
        anzeige = int(ergebnis) if isinstance(ergebnis, float) and ergebnis.is_integer() \
            else round(ergebnis, 10)
        return ok("productivity.calculate", f"{ausdruck} = {anzeige}", payload=str(anzeige),
                  ergebnis=anzeige)

    # ══════════════════════════════════════════════════════════ Einheiten
    _LAENGE = {"mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
              "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344}
    _GEWICHT = {"mg": 0.001, "g": 1.0, "kg": 1000.0, "t": 1_000_000.0,
               "oz": 28.349523125, "lb": 453.59237}
    _VOLUMEN = {"ml": 0.001, "l": 1.0, "gal": 3.785411784, "pt": 0.473176473,
               "cup": 0.2365882365}
    _EINHEITEN = {"laenge": _LAENGE, "gewicht": _GEWICHT, "volumen": _VOLUMEN}

    def unit_convert(value: float, from_unit: str, to_unit: str) -> ToolResult:
        von, nach = from_unit.strip().lower(), to_unit.strip().lower()
        if {von, nach} <= {"c", "f", "k"}:
            v = float(value)
            celsius = v if von == "c" else (v - 32) * 5 / 9 if von == "f" else v - 273.15
            ergebnis = celsius if nach == "c" else celsius * 9 / 5 + 32 if nach == "f" \
                else celsius + 273.15
            return ok("productivity.unit.convert", f"{value} °{von.upper()} = "
                      f"{round(ergebnis, 4)} °{nach.upper()}", ergebnis=round(ergebnis, 6))
        for gruppe in _EINHEITEN.values():
            if von in gruppe and nach in gruppe:
                basis = float(value) * gruppe[von]
                ergebnis = basis / gruppe[nach]
                return ok("productivity.unit.convert",
                          f"{value} {from_unit} = {round(ergebnis, 6)} {to_unit}",
                          ergebnis=round(ergebnis, 8))
        raise ToolError(f"Unbekannte oder nicht zueinander passende Einheiten: "
                        f"{from_unit!r} → {to_unit!r}. Bekannt: Länge (mm/cm/m/km/in/ft/"
                        "yd/mi), Gewicht (mg/g/kg/t/oz/lb), Volumen (ml/l/gal/pt/cup), "
                        "Temperatur (c/f/k).")

    # ══════════════════════════════════════════════════════════ Farben
    def _hex_zu_rgb(wert: str) -> tuple[int, int, int]:
        h = wert.strip().lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", h):
            raise ToolError(f"Keine gültige Hex-Farbe: {wert!r}")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def color_convert(value: str, to: str = "all") -> ToolResult:
        wert = (value or "").strip()
        if wert.startswith("#") or re.fullmatch(r"[0-9a-fA-F]{3}|[0-9a-fA-F]{6}", wert):
            r, g, b = _hex_zu_rgb(wert)
        elif wert.lower().startswith("rgb"):
            zahlen = re.findall(r"\d+", wert)
            if len(zahlen) < 3:
                raise ToolError(f"Keine gültige rgb()-Angabe: {wert!r}")
            r, g, b = (int(z) for z in zahlen[:3])
        else:
            raise ToolError(f"Farbe nicht erkannt (Hex '#rrggbb' oder 'rgb(r,g,b)'): {wert!r}")
        hexfarbe = "#{:02x}{:02x}{:02x}".format(r, g, b)
        rn, gn, bn = r / 255, g / 255, b / 255
        mx, mn = max(rn, gn, bn), min(rn, gn, bn)
        l = (mx + mn) / 2
        if mx == mn:
            h = s = 0.0
        else:
            d = mx - mn
            s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
            if mx == rn:
                h = (gn - bn) / d + (6 if gn < bn else 0)
            elif mx == gn:
                h = (bn - rn) / d + 2
            else:
                h = (rn - gn) / d + 4
            h /= 6
        hsl = (round(h * 360), round(s * 100), round(l * 100))
        return ok("productivity.color.convert",
                  f"{hexfarbe} · rgb({r}, {g}, {b}) · hsl({hsl[0]}, {hsl[1]}%, {hsl[2]}%)",
                  hex=hexfarbe, rgb=[r, g, b], hsl=list(hsl))

    # ══════════════════════════════════════════════════════════ Passphrase
    _WOERTER = (
        "apfel banane berg blau boot brot brücke burg dach delfin donner "
        "drache eiche engel ernte feder fels feuer fisch fluss frosch "
        "garten gold hafen hase herbst himmel holz hügel insel katze "
        "kiefer klang kranich kreis kristall lachs lampe licht linde "
        "löwe mais meer mond morgen mühle nebel nest ozean panda pfad "
        "pfeil pilz quelle rabe regen reise ring sand schnee see sonne "
        "stein stern sturm tal teich tiger tulpe ufer vogel wald wasser "
        "welle wind winter wolke wurzel zeder zweig anker atlas basalt "
        "blitz dolch echo falke garn hummel iglu jaspis kompass laterne "
        "magnet nordlicht opal quarz rakete sichel taupunkt ulme vulkan "
        "weizen xylophon ysop zypresse"
    ).split()

    def passphrase_generate(words: int = 5, separator: str = "-",
                            capitalize: bool = False) -> ToolResult:
        n = max(3, min(int(words or 5), 12))
        gewaehlt = [random.SystemRandom().choice(_WOERTER) for _ in range(n)]
        if capitalize:
            gewaehlt = [w.capitalize() for w in gewaehlt]
        phrase = (separator or "-").join(gewaehlt)
        bits = round(n * (len(_WOERTER)).bit_length(), 1)
        return ok("productivity.passphrase.generate", phrase, payload=phrase,
                  woerter=n, geschaetzte_bits=bits)

    # ══════════════════════════════════════════════════════════ QR-Code
    def qrcode_generate(text: str, output: str, overwrite: bool = False) -> ToolResult:
        if qrcode is None:
            raise ToolError("Dafür fehlt das Paket 'qrcode': pip install qrcode")
        inhalt = (text or "").strip()
        if not inhalt:
            raise ToolError("Kein Inhalt angegeben.")
        ws = ctx.workspace
        ziel = ws.resolve(output)
        if ziel.exists() and not overwrite:
            raise ToolError(f"Ziel existiert schon: {ziel}. Mit overwrite=true überschreiben.")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        bild = qrcode.make(inhalt)
        bild.save(ziel)
        return ok("productivity.qrcode.generate", f"QR-Code erstellt: {ziel.name}",
                  pfad=str(ziel), zeichen=len(inhalt))

    # ══════════════════════════════════════════════════════════ Lorem Ipsum
    _LOREM = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do "
             "eiusmod tempor incididunt ut labore et dolore magna aliqua ut "
             "enim ad minim veniam quis nostrud exercitation ullamco laboris "
             "nisi ut aliquip ex ea commodo consequat duis aute irure dolor "
             "in reprehenderit in voluptate velit esse cillum dolore eu "
             "fugiat nulla pariatur excepteur sint occaecat cupidatat non "
             "proident sunt in culpa qui officia deserunt mollit anim id "
             "est laborum").split()

    def lorem_generate(words: int = 50) -> ToolResult:
        n = max(1, min(int(words or 50), 2000))
        gewaehlt = [random.choice(_LOREM) for _ in range(n)]
        gewaehlt[0] = gewaehlt[0].capitalize()
        text_ergebnis = " ".join(gewaehlt) + "."
        return ok("productivity.lorem.generate", f"{n} Wörter erzeugt",
                  payload=text_ergebnis, woerter=n)

    # ══════════════════════════════════════════════════════════ Datum
    def _datum_parsen(wert: str) -> dt.date:
        for muster in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return dt.datetime.strptime(wert.strip(), muster).date()
            except ValueError:
                continue
        raise ToolError(f"Datum nicht erkannt (erwartet JJJJ-MM-TT oder TT.MM.JJJJ): {wert!r}")

    def date_diff(date_a: str, date_b: str) -> ToolResult:
        a, b = _datum_parsen(date_a), _datum_parsen(date_b)
        delta = (b - a).days
        return ok("productivity.date.diff",
                  f"{abs(delta)} Tag(e) {'nach' if delta >= 0 else 'vor'} {date_a}",
                  tage=delta, wochen=round(delta / 7, 2))

    _WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                  "Samstag", "Sonntag")

    def date_add(date: str, days: int = 0, weeks: int = 0) -> ToolResult:
        basis = _datum_parsen(date)
        ergebnis = basis + dt.timedelta(days=int(days) + int(weeks) * 7)
        # Fester Name statt strftime("%A") -- das haengt von der Locale des
        # Server-Prozesses ab und liefert ohne eine gesetzte deutsche Locale
        # (der Normalfall) den englischen Namen.
        return ok("productivity.date.add", ergebnis.isoformat(), payload=ergebnis.isoformat(),
                  datum=ergebnis.isoformat(), wochentag=_WOCHENTAGE[ergebnis.weekday()])

    def timezone_convert(value: str, from_zone: str, to_zone: str) -> ToolResult:
        if ZoneInfo is None:
            raise ToolError("Zeitzonen-Unterstützung (zoneinfo) fehlt in diesem Python.")
        try:
            quelle_zone, ziel_zone = ZoneInfo(from_zone), ZoneInfo(to_zone)
        except Exception as exc:  # noqa: BLE001 - zoneinfo wirft je nach Plattform Unterschiedliches
            raise ToolError(f"Unbekannte Zeitzone: {exc}") from exc
        try:
            zeitpunkt = dt.datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise ToolError(f"Zeit nicht erkannt (ISO-Format erwartet): {exc}") from exc
        lokalisiert = zeitpunkt.replace(tzinfo=quelle_zone)
        umgerechnet = lokalisiert.astimezone(ziel_zone)
        text_ergebnis = umgerechnet.strftime("%Y-%m-%d %H:%M:%S %Z")
        return ok("productivity.timezone.convert", text_ergebnis, payload=text_ergebnis,
                  ergebnis_iso=umgerechnet.isoformat())

    # ══════════════════════════════════════════════════════════ Zahlen
    _EINER = ["", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun"]
    _ZEHN_BIS_NEUNZEHN = ["zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn",
                         "sechzehn", "siebzehn", "achtzehn", "neunzehn"]
    _ZEHNER = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig",
              "achtzig", "neunzig"]

    def _dreistellig_zu_wort(n: int) -> str:
        teile = []
        if n >= 100:
            teile.append(("ein" if n // 100 == 1 else _EINER[n // 100]) + "hundert")
            n %= 100
        if 10 <= n <= 19:
            teile.append(_ZEHN_BIS_NEUNZEHN[n - 10])
        elif n >= 20:
            # "einundzwanzig", nicht "einsundzwanzig" -- die Eins verliert
            # ihr 's', sobald sie mit "und" zusammengesetzt wird.
            einer_ziffer = n % 10
            einer = "ein" if einer_ziffer == 1 else _EINER[einer_ziffer]
            teile.append((einer + "und" if einer_ziffer else "") + _ZEHNER[n // 10])
        elif n > 0:
            teile.append(_EINER[n])
        return "".join(teile)

    def number_to_words(value: int) -> ToolResult:
        n = int(value)
        if abs(n) > 999_999_999:
            raise ToolError("Nur Zahlen bis unter einer Milliarde.")
        if n == 0:
            wort = "null"
        else:
            vorzeichen = "minus " if n < 0 else ""
            n = abs(n)
            millionen, rest = divmod(n, 1_000_000)
            tausender, hundert_rest = divmod(rest, 1000)
            # "Million"/"Millionen" ist im Deutschen ein eigenes Wort (Leerzeichen
            # davor und danach), "tausend" dagegen verschmilzt mit dem Rest zu
            # einem einzigen Wort ("eintausendeins", nicht "eintausend eins").
            teile = []
            if millionen:
                teile.append("eine Million" if millionen == 1
                             else _dreistellig_zu_wort(millionen) + " Millionen")
            tausend_und_rest = ""
            if tausender:
                tausend_und_rest += ("ein" if tausender == 1
                                     else _dreistellig_zu_wort(tausender)) + "tausend"
            if hundert_rest or not (millionen or tausender):
                tausend_und_rest += _dreistellig_zu_wort(hundert_rest) or "null"
            if tausend_und_rest:
                teile.append(tausend_und_rest)
            wort = vorzeichen + " ".join(teile)
        return ok("productivity.number.to_words", wort, payload=wort)

    _ROEMISCH = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
                (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
                (5, "V"), (4, "IV"), (1, "I")]

    def roman_convert(value: str) -> ToolResult:
        wert = (value or "").strip()
        if wert.isdigit() or (wert.startswith("-") and wert[1:].isdigit()):
            n = int(wert)
            if not 1 <= n <= 3999:
                raise ToolError("Nur Zahlen von 1 bis 3999 lassen sich als römische "
                                "Zahl darstellen.")
            ergebnis = ""
            rest = n
            for zahl, symbol in _ROEMISCH:
                while rest >= zahl:
                    ergebnis += symbol
                    rest -= zahl
            return ok("productivity.roman.convert", ergebnis, payload=ergebnis)
        muster = wert.upper()
        if not re.fullmatch(r"[MDCLXVI]+", muster):
            raise ToolError(f"Weder eine Zahl noch eine gültige römische Zahl: {value!r}")
        rest, ergebnis = muster, 0
        for zahl, symbol in _ROEMISCH:
            while rest.startswith(symbol):
                ergebnis += zahl
                rest = rest[len(symbol):]
        if rest:
            raise ToolError(f"Keine gültige römische Zahl: {value!r}")
        return ok("productivity.roman.convert", str(ergebnis), payload=str(ergebnis),
                  wert=ergebnis)

    def base_convert(value: str, from_base: int, to_base: int) -> ToolResult:
        for basis in (from_base, to_base):
            if not 2 <= int(basis) <= 36:
                raise ToolError("Basis muss zwischen 2 und 36 liegen.")
        try:
            n = int((value or "").strip(), int(from_base))
        except ValueError as exc:
            raise ToolError(f"'{value}' ist keine gültige Zahl zur Basis {from_base}: "
                            f"{exc}") from exc
        if n == 0:
            ergebnis = "0"
        else:
            ziffern = "0123456789abcdefghijklmnopqrstuvwxyz"
            rest, ergebnis = abs(n), ""
            while rest:
                rest, r = divmod(rest, int(to_base))
                ergebnis = ziffern[r] + ergebnis
            ergebnis = ("-" if n < 0 else "") + ergebnis
        return ok("productivity.base.convert",
                  f"{value} (Basis {from_base}) = {ergebnis} (Basis {to_base})",
                  payload=ergebnis, ergebnis=ergebnis)

    # ══════════════════════════════════════════════════════════ Automation
    def automation_wait(seconds: float) -> ToolResult:
        # Synchron per time.sleep: Registry.call() laeuft in einem eigenen
        # Thread (siehe agent.py, asyncio.to_thread) -- eine Koroutine hier
        # wuerde nie ausgefuehrt, nur als Objekt zurueckgegeben.
        s = max(0.0, min(float(seconds), 300.0))
        time.sleep(s)
        return ok("automation.wait", f"{s}s gewartet", sekunden=s)

    # ══════════════════════════════════════════════════════════ Makros
    # Ablage über den Dienst "macros" (siehe tools/__init__.py::build_registry).
    # Die Ausführung selbst ist bewusst KEIN Werkzeug hier: ein Makroschritt
    # muss über Agent._run_tool laufen (Permission-Gate, Undo, Audit -- siehe
    # macros.py-Docstring), und ein Pack kennt den Agent nicht. Nur die reine
    # Datenverwaltung (anlegen/auflisten/ansehen/löschen) gehört hierher.
    # Die Prüfung der Schrittliste selbst (``validate_steps``) kommt aus
    # macros.py -- dieselbe Form, die ``MacroEngine`` zur Laufzeit erwartet,
    # nicht eine hier unabhängig gepflegte zweite Kopie.

    def _makro_ablage():
        store = ctx.services.get("macros")
        if store is None:
            raise ToolError("Makro-Ablage ist nicht verfügbar.")
        return store

    def macro_create(name: str, steps: list, description: str = "") -> ToolResult:
        ablage = _makro_ablage()
        try:
            validate_steps(steps)
            definition = ablage.save(name, steps, description or "")
        except MacroError as exc:
            raise ToolError(str(exc)) from exc
        return ok("automation.macro.create",
                  f"Makro '{definition.name}' gespeichert ({len(definition.steps)} Schritt(e))",
                  id=definition.id, name=definition.name,
                  anzahl_schritte=len(definition.steps))

    def macro_list() -> ToolResult:
        makros = _makro_ablage().list()
        zeilen = [[m.name, str(len(m.steps)), m.description or "-"] for m in makros]
        return ok("automation.macro.list", f"{len(makros)} Makro(s)",
                  payload=table(zeilen, headers=["Name", "Schritte", "Beschreibung"]),
                  anzahl=len(makros))

    def macro_get(name: str) -> ToolResult:
        definition = _makro_ablage().get_by_name((name or "").strip())
        if definition is None:
            raise ToolError(f"Kein Makro mit dem Namen '{name}' gefunden.")
        return ok("automation.macro.get",
                  f"Makro '{definition.name}' ({len(definition.steps)} Schritt(e))",
                  payload=definition.steps, name=definition.name,
                  beschreibung=definition.description,
                  anzahl_schritte=len(definition.steps))

    def macro_delete(name: str) -> ToolResult:
        n = (name or "").strip()
        if not _makro_ablage().delete(n):
            raise ToolError(f"Kein Makro mit dem Namen '{n}' gefunden.")
        return ok("automation.macro.delete", f"Makro '{n}' gelöscht", name=n)

    _out = text("Zielpfad im Arbeitsbereich")

    return [
        Tool("productivity.calculate", "Wertet einen mathematischen Ausdruck aus "
             "(+ - * / // % **, Klammern, Konstanten pi/e) -- kein eval, kein "
             "Funktionsaufruf möglich.",
             params("expression", expression=text("z. B. '(3 + 4) * 2 / 7'")),
             calculate, level=P.SAFE, tags=("produktivitaet", "rechnen"),
             phrases=("rechne mal", "was ist")),
        Tool("productivity.unit.convert", "Rechnet zwischen Maßeinheiten um "
             "(Länge, Gewicht, Volumen, Temperatur).",
             params("value", "from_unit", "to_unit", value=number("Ausgangswert"),
                    from_unit=text("z. B. km, lb, c"), to_unit=text("z. B. mi, kg, f")),
             unit_convert, level=P.SAFE, tags=("produktivitaet", "einheiten"),
             phrases=("wie viel sind", "rechne um in")),
        Tool("productivity.color.convert", "Wandelt eine Farbe zwischen Hex/RGB/HSL um.",
             params("value", value=text("z. B. #3366ff oder rgb(51,102,255)")),
             color_convert, level=P.SAFE, tags=("produktivitaet", "farbe")),
        Tool("productivity.passphrase.generate", "Erzeugt eine leicht zu merkende "
             "Passphrase aus mehreren Wörtern (mit eingebauter Wortliste).",
             params(words=integer("Anzahl Wörter, Vorgabe 5"),
                    separator=text("Trennzeichen, Vorgabe '-'"),
                    capitalize=flag("Wörter großschreiben")),
             passphrase_generate, level=P.SAFE, tags=("produktivitaet", "sicherheit"),
             phrases=("gib mir eine passphrase",)),
        Tool("productivity.qrcode.generate", "Erstellt einen QR-Code als Bild.",
             params("text", "output", text=text("Inhalt des QR-Codes"), output=_out,
                    overwrite=flag("Bestehendes Ziel überschreiben")),
             qrcode_generate, level=P.WRITE, requires=("qrcode",),
             tags=("produktivitaet", "qrcode"), phrases=("mach einen qr code",)),
        Tool("productivity.lorem.generate", "Erzeugt Platzhaltertext (Lorem Ipsum).",
             params(words=integer("Anzahl Wörter, Vorgabe 50")), lorem_generate,
             level=P.SAFE, tags=("produktivitaet", "text")),
        Tool("productivity.date.diff", "Anzahl Tage zwischen zwei Daten.",
             params("date_a", "date_b", date_a=text("JJJJ-MM-TT"), date_b=text("JJJJ-MM-TT")),
             date_diff, level=P.SAFE, tags=("produktivitaet", "datum")),
        Tool("productivity.date.add", "Addiert Tage/Wochen zu einem Datum.",
             params("date", date=text("JJJJ-MM-TT"), days=integer("Tage"),
                    weeks=integer("Wochen")), date_add, level=P.SAFE,
             tags=("produktivitaet", "datum")),
        Tool("productivity.timezone.convert", "Rechnet eine Uhrzeit zwischen Zeitzonen um.",
             params("value", "from_zone", "to_zone",
                    value=text("ISO-Zeit ohne Zone, z. B. 2026-01-15T14:00:00"),
                    from_zone=text("z. B. Europe/Berlin"), to_zone=text("z. B. America/New_York")),
             timezone_convert, level=P.SAFE, tags=("produktivitaet", "zeit")),
        Tool("productivity.number.to_words", "Schreibt eine Zahl auf Deutsch aus.",
             params("value", value=integer("Die Zahl")), number_to_words, level=P.SAFE,
             tags=("produktivitaet", "zahlen")),
        Tool("productivity.roman.convert", "Wandelt zwischen arabischen und römischen "
             "Zahlen um (in beide Richtungen erkannt).",
             params("value", value=text("Zahl oder römische Zahl, z. B. 1994 oder MCMXCIV")),
             roman_convert, level=P.SAFE, tags=("produktivitaet", "zahlen")),
        Tool("productivity.base.convert", "Wandelt eine Zahl zwischen Zahlensystemen um "
             "(Basis 2-36).",
             params("value", "from_base", "to_base", value=text("Die Zahl als Text"),
                    from_base=integer("Ausgangsbasis, z. B. 10"),
                    to_base=integer("Zielbasis, z. B. 16")),
             base_convert, level=P.SAFE, tags=("produktivitaet", "zahlen"),
             phrases=("wandle die zahl ins binärsystem um",)),
        Tool("automation.wait", "Wartet eine bestimmte Zeit, bevor der nächste Schritt "
             "läuft -- als Baustein in mehrstufigen Aufträgen.",
             params("seconds", seconds=number("Sekunden, max. 300")), automation_wait,
             level=P.SAFE, tags=("automation",), timeout=310.0),
        Tool("automation.macro.create", "Speichert eine benannte Schrittfolge (Werkzeug-"
             "aufrufe mit optional IF/LOOP/PARALLEL/WAIT) unter einem Namen, zum späteren "
             "Ausführen ohne erneute Planung. Siehe macros.py für das Schrittformat.",
             params("name", "steps", name=text("Name des Makros"), steps=_STEPS,
                    description=text("Kurzbeschreibung, optional")),
             macro_create, level=P.WRITE, tags=("automation", "makro"),
             phrases=("speichere das als makro", "leg ein makro an")),
        Tool("automation.macro.list", "Listet gespeicherte Makros auf.", NO_PARAMS,
             macro_list, level=P.READ, tags=("automation", "makro"),
             phrases=("welche makros gibt es",)),
        Tool("automation.macro.get", "Zeigt die Schritte eines gespeicherten Makros.",
             params("name", name=text("Name des Makros")), macro_get, level=P.READ,
             tags=("automation", "makro")),
        Tool("automation.macro.delete", "Löscht ein gespeichertes Makro endgültig.",
             params("name", name=text("Name des Makros")), macro_delete,
             level=P.CRITICAL, tags=("automation", "makro", "loeschen")),
    ]
