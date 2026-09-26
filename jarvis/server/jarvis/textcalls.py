"""Werkzeugaufrufe, die ein Modell als Text schreibt statt über die Schnittstelle.

Ollama erkennt einen Werkzeugaufruf am Format des jeweiligen Modells. Gerät
das Modell aus dem Tritt -- Qwen3-Coder lässt z. B. gern das öffnende
``<tool_call>`` weg --, kommt der Aufruf als gewöhnlicher Text in
``content`` an. Jarvis hielt ihn dann für die fertige Antwort: Das Modell
kündigte "ich schaue mir jetzt den Desktop an" an, und danach passierte
nichts mehr.

Gelesen werden die verbreiteten Textformen:

* Qwen3-Coder-XML -- die Rahmen ``<tool_call>``/``</tool_call>`` dürfen fehlen::

      <tool_call>
      <function=list_dir>
      <parameter=path>
      C:\\Users\\...\\Desktop
      </parameter>
      </function>
      </tool_call>

* Hermes-/Qwen2.5-JSON: ``<tool_call>{"name": ..., "arguments": {...}}</tool_call>``
* reines JSON als *ganze* Antwort (auch im ```json-Zaun oder als Liste):
  ``{"name": ..., "arguments"|"parameters": {...}}`` -- nur für Werkzeuge,
  die gerade angeboten sind, weil gewöhnliches JSON sonst zu leicht als
  Aufruf durchginge.

Was dabei herauskommt, ist ein gewöhnlicher Werkzeugaufruf: Er läuft durch
dasselbe Permission-Gate, dieselbe Bestätigung und dasselbe Audit wie jeder
andere -- Ollamas eigener Parser liest dieselben Zeichen, nur eben nicht, wenn
ein Rahmen fehlt. Zwei Grenzen gelten zusätzlich:

* Gelesen wird nur, wenn die Anfrage überhaupt Werkzeuge angeboten hat.
* Text in Code-Zäunen (```) bleibt Text: Ein Modell, das einen Aufruf nur
  *zeigt*, etwa als Beispiel, löst ihn damit nicht aus.
"""

from __future__ import annotations

import json
import re
from typing import Any

#: Ein Aufruf als (Werkzeugname, Argumente).
Call = tuple[str, dict[str, Any]]

_ZAUN = re.compile(r"```.*?(?:```|\Z)", re.S)
_RAHMEN = re.compile(r"</?tool_call>")
_XML_FUNKTION = re.compile(r"<function=([^>\s]+)\s*>(.*?)(?:</function>|(?=<function=)|\Z)", re.S)
_XML_PARAMETER = re.compile(
    r"<parameter=([^>\s]+)\s*>(.*?)(?:</parameter>|(?=<parameter=)|(?=</function>)|\Z)", re.S)
_JSON_START = re.compile(r"<tool_call>\s*(?=\{)")
_GANZER_ZAUN = re.compile(r"\A```(?:json)?\s*\n?(.*?)\n?```\Z", re.S)


def extract(text: str, tools: list[dict[str, Any]] | None) -> tuple[str, list[Call]]:
    """Liest Werkzeugaufrufe aus ``text``.

    Gibt ``(übriger Text, Aufrufe)`` zurück; ohne Treffer unverändert
    ``(text, [])``. Der übrige Text ist das, was das Modell außerhalb der
    Aufrufe geschrieben hat ("Ich schaue mir das an ...")."""
    if not text or not tools:
        return text, []
    eigenschaften = _eigenschaften(tools)
    zaeune = [m.span() for m in _ZAUN.finditer(text)]

    def im_zaun(pos: int) -> bool:
        return any(a <= pos < b for a, b in zaeune)

    treffer: list[tuple[int, int, Call]] = []

    # Hermes-JSON: <tool_call>{...}</tool_call>
    decoder = json.JSONDecoder()
    for m in _JSON_START.finditer(text):
        if im_zaun(m.start()):
            continue
        try:
            obj, ende = decoder.raw_decode(text, m.end())
        except ValueError:
            continue
        call = _aus_json(obj, None)
        if call:
            treffer.append((m.start(), ende, call))

    # Qwen3-Coder-XML: <function=NAME><parameter=P>wert</parameter></function>
    for m in _XML_FUNKTION.finditer(text):
        if im_zaun(m.start()) or any(a <= m.start() < b for a, b, _ in treffer):
            continue
        name = m.group(1)
        typen = eigenschaften.get(name, {})
        argumente = {p.group(1): _wert(p.group(2), (typen.get(p.group(1)) or {}).get("type"))
                     for p in _XML_PARAMETER.finditer(m.group(2))}
        treffer.append((m.start(), m.end(), (name, argumente)))

    if treffer:
        treffer.sort(key=lambda t: t[0])
        rest, pos = [], 0
        for anfang, ende, _ in treffer:
            rest.append(text[pos:anfang])
            pos = max(pos, ende)
        rest.append(text[pos:])
        uebrig = "".join(rest)
        # Übrig gebliebene Rahmen (<tool_call> ohne Inhalt) gehören nicht in
        # die Antwort -- außer sie stehen in einem Zaun.
        uebrig = _ohne_rahmen(uebrig)
        return uebrig.strip(), [call for _, _, call in treffer]

    # Reines JSON als ganze Antwort -- nur mit angebotenem Werkzeugnamen.
    roh = text.strip()
    zaun = _GANZER_ZAUN.match(roh)
    if zaun:
        roh = zaun.group(1).strip()
    if roh and roh[0] in "{[":
        try:
            obj = json.loads(roh)
        except ValueError:
            return text, []
        objekte = obj if isinstance(obj, list) else [obj]
        calls = [_aus_json(o, eigenschaften) for o in objekte]
        if objekte and all(calls):
            return "", [c for c in calls if c]
    return text, []


def _eigenschaften(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Werkzeugname → JSON-Schema-``properties`` der angebotenen Werkzeuge."""
    ergebnis: dict[str, dict[str, Any]] = {}
    for schema in tools:
        fn = (schema or {}).get("function") or {}
        if fn.get("name"):
            ergebnis[fn["name"]] = ((fn.get("parameters") or {}).get("properties") or {})
    return ergebnis


def _aus_json(obj: Any, angeboten: dict[str, dict[str, Any]] | None) -> Call | None:
    """``{"name": ..., "arguments": {...}}`` → Aufruf. Mit ``angeboten`` nur
    für bekannte Namen (reines JSON ist sonst nicht eindeutig ein Aufruf)."""
    if not isinstance(obj, dict) or not isinstance(obj.get("name"), str):
        return None
    if angeboten is not None and obj["name"] not in angeboten:
        return None
    argumente = obj.get("arguments", obj.get("parameters", {}))
    if isinstance(argumente, str):
        try:
            argumente = json.loads(argumente)
        except ValueError:
            return None
    if not isinstance(argumente, dict):
        return None
    return obj["name"], argumente


def _wert(roh: str, typ: Any) -> Any:
    """Ein XML-Parameter ist immer Text; das Schema sagt, was er sein soll.

    Wie Qwens eigener Parser: genau ein Zeilenumbruch vorn und hinten gehört
    zum Format, nicht zum Wert -- weitere (etwa in Dateiinhalten) bleiben."""
    if roh.startswith("\n"):
        roh = roh[1:]
    if roh.endswith("\n"):
        roh = roh[:-1]
    typen = typ if isinstance(typ, list) else [typ]
    if typ is None or "string" in typen:
        return roh
    try:
        return json.loads(roh)
    except ValueError:
        pass
    if "boolean" in typen and roh.strip().lower() in ("true", "false"):
        return roh.strip().lower() == "true"
    return roh


def _ohne_rahmen(text: str) -> str:
    zaeune = [m.span() for m in _ZAUN.finditer(text)]
    return _RAHMEN.sub(
        lambda m: m.group(0) if any(a <= m.start() < b for a, b in zaeune) else "", text)
