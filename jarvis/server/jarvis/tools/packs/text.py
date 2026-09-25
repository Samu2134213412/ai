"""Tool Pack: Text, Daten und Kodierungen.

Alles hier ist **rein lokal und deterministisch** -- kein Modellaufruf, keine
Netzverbindung. Das ist der Punkt: Base64 dekodieren, JSON formatieren oder
eine Prüfsumme bilden sind Aufgaben mit genau einer richtigen Antwort. Ein
Sprachmodell dafür zu befragen wäre langsamer, teurer und unzuverlässiger.

Die Werkzeuge, für die man wirklich ein Modell braucht -- zusammenfassen,
übersetzen, den Ton ändern --, stehen bewusst **nicht** hier. Sie gehören in
den Chat-Zug, wo das Modell ohnehin läuft; als Werkzeug getarnt wären sie ein
zweiter Modellaufruf mitten im ersten.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import csv
import difflib
import hashlib
import html as html_mod
import io
import json
import re
import secrets
import string
import textwrap
import time
import unicodedata
import urllib.parse
import uuid as uuid_mod
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext
from ._base import INT, STR, flag, integer, ok, params, table, text

try:  # pragma: no cover - hängt von der Installation ab
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

MAX_TEXT = 500_000
_HASHES = ("md5", "sha1", "sha256", "sha512")

#: Häufigste Funktionswörter je Sprache. Reicht für eine **Schätzung** -- und
#: genau als solche wird das Ergebnis auch gemeldet, nicht als Feststellung.
_STOPWORDS = {
    "deutsch": {"der", "die", "das", "und", "ist", "nicht", "ein", "eine", "zu",
                "den", "mit", "sich", "auf", "für", "von", "dem", "im", "aber"},
    "englisch": {"the", "and", "is", "not", "a", "an", "to", "of", "in", "that",
                 "it", "for", "with", "as", "was", "on", "are", "but"},
    "französisch": {"le", "la", "les", "et", "est", "pas", "un", "une", "de",
                    "du", "des", "que", "qui", "dans", "pour", "sur", "avec"},
    "spanisch": {"el", "la", "los", "las", "y", "es", "no", "un", "una", "de",
                 "que", "en", "por", "para", "con", "se", "del"},
    "italienisch": {"il", "lo", "la", "e", "è", "non", "un", "una", "di", "che",
                    "in", "per", "con", "si", "del", "da"},
}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"https?://[^\s<>\"'\)]+")
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_WORD = re.compile(r"[\w'äöüßÄÖÜ-]+", re.UNICODE)


class _TextExtractor(HTMLParser):
    """HTML zu Text, ohne zusätzliche Abhängigkeit. Skript- und Stilinhalte
    fliegen raus -- sie sind kein Text, den jemand lesen will."""

    SKIP = {"script", "style", "head", "noscript"}
    BREAK = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())

    def result(self) -> str:
        joined = " ".join(self.parts)
        return re.sub(r"\n\s*", "\n", re.sub(r"[ \t]+", " ", joined)).strip()


def _check(value: str, name: str = "text") -> str:
    if value is None:
        raise ToolError(f"{name} fehlt.")
    if len(value) > MAX_TEXT:
        raise ToolError(f"{name} ist zu lang: {len(value)} Zeichen "
                        f"(Grenze {MAX_TEXT}).")
    return value


def _words(value: str) -> list[str]:
    return _WORD.findall(value or "")


def build(ctx: ToolContext) -> list[Tool]:
    # ═══════════════════════════════════════════════════════════ Kodierung
    def base64_encode(text: str, urlsafe: bool = False) -> ToolResult:
        raw = _check(text).encode("utf-8")
        out = (base64.urlsafe_b64encode if urlsafe else base64.b64encode)(raw).decode()
        return ok("text.base64.encode", f"{len(raw)} Bytes kodiert", payload=out,
                  zeichen=len(out))

    def base64_decode(text: str, urlsafe: bool = False) -> ToolResult:
        value = _check(text).strip()
        try:
            raw = (base64.urlsafe_b64decode if urlsafe else base64.b64decode)(
                value + "=" * (-len(value) % 4))
        except (binascii.Error, ValueError) as exc:
            raise ToolError(f"Kein gültiges Base64: {exc}") from exc
        try:
            out = raw.decode("utf-8")
        except UnicodeDecodeError:
            return ok("text.base64.decode",
                      f"{len(raw)} Bytes dekodiert, aber kein UTF-8-Text",
                      payload=raw.hex(), bytes=len(raw), textform=False)
        return ok("text.base64.decode", f"{len(raw)} Bytes dekodiert", payload=out,
                  bytes=len(raw), textform=True)

    def url_encode(text: str, safe: str = "") -> ToolResult:
        out = urllib.parse.quote(_check(text), safe=safe or "")
        return ok("text.url.encode", f"{len(out)} Zeichen", payload=out)

    def url_decode(text: str) -> ToolResult:
        out = urllib.parse.unquote_plus(_check(text))
        return ok("text.url.decode", f"{len(out)} Zeichen", payload=out)

    def html_escape(text: str) -> ToolResult:
        out = html_mod.escape(_check(text), quote=True)
        return ok("text.html.escape", f"{len(out)} Zeichen", payload=out)

    def html_unescape(text: str) -> ToolResult:
        out = html_mod.unescape(_check(text))
        return ok("text.html.unescape", f"{len(out)} Zeichen", payload=out)

    def hex_encode(text: str) -> ToolResult:
        out = _check(text).encode("utf-8").hex()
        return ok("text.hex.encode", f"{len(out) // 2} Bytes", payload=out)

    def hex_decode(text: str) -> ToolResult:
        try:
            raw = bytes.fromhex(re.sub(r"[\s:]", "", _check(text)))
        except ValueError as exc:
            raise ToolError(f"Kein gültiges Hex: {exc}") from exc
        return ok("text.hex.decode", f"{len(raw)} Bytes",
                  payload=raw.decode("utf-8", errors="replace"), bytes=len(raw))

    def rot13(text: str) -> ToolResult:
        out = codecs.encode(_check(text), "rot13")
        return ok("text.rot13", "ROT13 angewendet (wieder anwenden hebt es auf)",
                  payload=out)

    def text_hash(text: str, algorithm: str = "sha256") -> ToolResult:
        algorithm = (algorithm or "sha256").lower()
        if algorithm not in _HASHES:
            raise ToolError(f"Unbekanntes Verfahren: {algorithm}. "
                            f"Möglich: {', '.join(_HASHES)}")
        value = hashlib.new(algorithm, _check(text).encode("utf-8")).hexdigest()
        return ok("text.hash", f"{algorithm}: {value}", payload=value,
                  verfahren=algorithm)

    def make_uuid(version: int = 4, count: int = 1) -> ToolResult:
        count = max(1, min(int(count or 1), 100))
        if int(version or 4) not in (1, 4):
            raise ToolError("Nur Version 1 (zeitbasiert) und 4 (zufällig).")
        maker = uuid_mod.uuid1 if int(version or 4) == 1 else uuid_mod.uuid4
        werte = [str(maker()) for _ in range(count)]
        return ok("text.uuid", f"{count} UUID(s) der Version {version or 4}",
                  payload="\n".join(werte), version=int(version or 4))

    def slugify(text: str, separator: str = "-") -> ToolResult:
        value = _check(text).lower()
        # Umlaute zuerst ausschreiben -- ohne das würde aus "Grüße" ein
        # "gre", weil die Zerlegung nur den Akzent entfernt.
        for umlaut, ersatz in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
            value = value.replace(umlaut, ersatz)
        value = unicodedata.normalize("NFKD", value)
        value = "".join(c for c in value if not unicodedata.combining(c))
        sep = separator or "-"
        out = re.sub(r"[^a-z0-9]+", sep, value).strip(sep)
        return ok("text.slug", out or "(leer)", payload=out)

    def random_string(length: int = 16, alphabet: str = "") -> ToolResult:
        size = max(1, min(int(length or 16), 4096))
        pool = alphabet or (string.ascii_letters + string.digits)
        out = "".join(secrets.choice(pool) for _ in range(size))
        return ok("text.random.string", f"{size} Zeichen", payload=out, laenge=size)

    def password_generate(length: int = 20, symbols: bool = True) -> ToolResult:
        """Aus ``secrets``, nicht aus ``random``: ein Passwort aus einem
        vorhersagbaren Zufallsgenerator ist kein Passwort."""
        size = max(8, min(int(length or 20), 128))
        pool = string.ascii_letters + string.digits + ("!@#$%^&*-_=+?" if symbols else "")
        while True:
            out = "".join(secrets.choice(pool) for _ in range(size))
            if (any(c.islower() for c in out) and any(c.isupper() for c in out)
                    and any(c.isdigit() for c in out)):
                break
        return ok("text.password.generate", f"{size} Zeichen erzeugt", payload=out,
                  laenge=size, sonderzeichen=bool(symbols))

    # ═════════════════════════════════════════════════════ Strukturformate
    def json_format(text: str, indent: int = 2, sort_keys: bool = False) -> ToolResult:
        try:
            data = json.loads(_check(text))
        except ValueError as exc:
            raise ToolError(f"Kein gültiges JSON: {exc}") from exc
        out = json.dumps(data, ensure_ascii=False, sort_keys=bool(sort_keys),
                         indent=max(0, min(int(indent or 2), 8)))
        return ok("text.json.format", f"{len(out)} Zeichen", payload=out,
                  typ=type(data).__name__)

    def json_minify(text: str) -> ToolResult:
        try:
            data = json.loads(_check(text))
        except ValueError as exc:
            raise ToolError(f"Kein gültiges JSON: {exc}") from exc
        out = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return ok("text.json.minify", f"{len(text)} → {len(out)} Zeichen", payload=out,
                  gespart=len(text) - len(out))

    def json_validate(text: str) -> ToolResult:
        try:
            data = json.loads(_check(text))
        except ValueError as exc:
            raise ToolError(f"Ungültiges JSON: {exc}") from exc
        groesse = len(data) if isinstance(data, (list, dict)) else 1
        return ok("text.json.validate", f"Gültiges JSON ({type(data).__name__})",
                  typ=type(data).__name__, eintraege=groesse)

    def json_keys(text: str, depth: int = 2) -> ToolResult:
        try:
            data = json.loads(_check(text))
        except ValueError as exc:
            raise ToolError(f"Kein gültiges JSON: {exc}") from exc
        grenze = max(1, min(int(depth or 2), 8))
        pfade: list[str] = []

        def walk(node, prefix: str, level: int) -> None:
            if level > grenze or len(pfade) > 2000:
                return
            if isinstance(node, dict):
                for key, value in node.items():
                    pfad = f"{prefix}.{key}" if prefix else str(key)
                    pfade.append(f"{pfad}  ({type(value).__name__})")
                    walk(value, pfad, level + 1)
            elif isinstance(node, list) and node:
                walk(node[0], f"{prefix}[]", level + 1)

        walk(data, "", 1)
        return ok("text.json.keys", f"{len(pfade)} Schlüsselpfade",
                  payload="\n".join(pfade) or "(keine)", pfade=len(pfade))

    def json_to_yaml(text: str) -> ToolResult:
        if yaml is None:
            raise ToolError("Dafür fehlt PyYAML: pip install PyYAML")
        try:
            data = json.loads(_check(text))
        except ValueError as exc:
            raise ToolError(f"Kein gültiges JSON: {exc}") from exc
        out = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        return ok("text.json.to_yaml", f"{len(out)} Zeichen", payload=out)

    def yaml_to_json(text: str, indent: int = 2) -> ToolResult:
        if yaml is None:
            raise ToolError("Dafür fehlt PyYAML: pip install PyYAML")
        try:
            data = yaml.safe_load(_check(text))
        except yaml.YAMLError as exc:
            raise ToolError(f"Kein gültiges YAML: {exc}") from exc
        out = json.dumps(data, ensure_ascii=False, indent=max(0, int(indent or 2)))
        return ok("text.yaml.to_json", f"{len(out)} Zeichen", payload=out)

    def yaml_validate(text: str) -> ToolResult:
        if yaml is None:
            raise ToolError("Dafür fehlt PyYAML: pip install PyYAML")
        try:
            data = yaml.safe_load(_check(text))
        except yaml.YAMLError as exc:
            raise ToolError(f"Ungültiges YAML: {exc}") from exc
        return ok("text.yaml.validate", f"Gültiges YAML ({type(data).__name__})",
                  typ=type(data).__name__)

    def xml_format(text: str, indent: int = 2) -> ToolResult:
        try:
            parsed = minidom.parseString(_check(text))
        except Exception as exc:  # noqa: BLE001 - expat wirft eigene Fehler
            raise ToolError(f"Kein gültiges XML: {exc}") from exc
        out = parsed.toprettyxml(indent=" " * max(0, min(int(indent or 2), 8)))
        out = "\n".join(line for line in out.splitlines() if line.strip())
        return ok("text.xml.format", f"{len(out)} Zeichen", payload=out)

    def xml_validate(text: str) -> ToolResult:
        try:
            root = ET.fromstring(_check(text))
        except ET.ParseError as exc:
            raise ToolError(f"Ungültiges XML: {exc}") from exc
        return ok("text.xml.validate", f"Gültiges XML, Wurzel <{root.tag}>",
                  wurzel=root.tag, kinder=len(list(root)))

    def csv_to_json(text: str, delimiter: str = "", header: bool = True) -> ToolResult:
        raw = _check(text)
        sep = delimiter or _sniff(raw)
        reader = csv.reader(io.StringIO(raw), delimiter=sep)
        zeilen = list(reader)
        if not zeilen:
            raise ToolError("Die CSV-Daten sind leer.")
        ungleich = 0
        if header:
            kopf, rest = zeilen[0], zeilen[1:]
            data = []
            for row in rest:
                # Ein bloßes zip() würde überzählige Werte stillschweigend
                # abschneiden -- lieber aufbewahren und die Zeile melden.
                eintrag = {k: (row[i] if i < len(row) else "") for i, k in enumerate(kopf)}
                if len(row) > len(kopf):
                    eintrag["_weitere"] = row[len(kopf):]
                if len(row) != len(kopf):
                    ungleich += 1
                data.append(eintrag)
        else:
            data = zeilen
        out = json.dumps(data, ensure_ascii=False, indent=2)
        hinweis = f" ({ungleich} mit abweichender Spaltenzahl)" if ungleich else ""
        return ok("text.csv.to_json", f"{len(data)} Datensätze{hinweis}", payload=out,
                  trenner=sep, datensaetze=len(data), abweichende_zeilen=ungleich)

    def json_to_csv(text: str, delimiter: str = ",") -> ToolResult:
        try:
            data = json.loads(_check(text))
        except ValueError as exc:
            raise ToolError(f"Kein gültiges JSON: {exc}") from exc
        if not isinstance(data, list) or not data:
            raise ToolError("Erwartet wird eine nicht-leere JSON-Liste.")
        if not all(isinstance(r, dict) for r in data):
            raise ToolError("Erwartet wird eine Liste von Objekten.")
        spalten: list[str] = []
        for row in data:
            for key in row:
                if key not in spalten:
                    spalten.append(key)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=spalten,
                                delimiter=delimiter or ",", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
        return ok("text.json.to_csv", f"{len(data)} Zeilen, {len(spalten)} Spalten",
                  payload=buffer.getvalue(), spalten=len(spalten))

    # ═════════════════════════════════════════════════════════ Umformungen
    def case_change(text: str, style: str = "lower") -> ToolResult:
        value = _check(text)
        style = (style or "lower").lower()
        woerter = re.split(r"[\s_\-.]+", value.strip())
        woerter = [w for w in woerter if w]
        umformer = {
            "lower": lambda: value.lower(),
            "upper": lambda: value.upper(),
            "title": lambda: value.title(),
            "sentence": lambda: value[:1].upper() + value[1:].lower(),
            "snake": lambda: "_".join(w.lower() for w in woerter),
            "kebab": lambda: "-".join(w.lower() for w in woerter),
            "camel": lambda: (woerter[0].lower()
                              + "".join(w.capitalize() for w in woerter[1:])) if woerter else "",
            "pascal": lambda: "".join(w.capitalize() for w in woerter),
            "swap": lambda: value.swapcase(),
        }
        if style not in umformer:
            raise ToolError(f"Unbekannter Stil: {style}. "
                            f"Möglich: {', '.join(sorted(umformer))}")
        out = umformer[style]()
        return ok("text.case", f"{style}: {out[:60]}", payload=out, stil=style)

    def text_trim(text: str, mode: str = "both") -> ToolResult:
        value = _check(text)
        out = {"both": value.strip(), "left": value.lstrip(),
               "right": value.rstrip(),
               "lines": "\n".join(l.strip() for l in value.splitlines()),
               "blank": "\n".join(l for l in value.splitlines() if l.strip()),
               }.get((mode or "both").lower())
        if out is None:
            raise ToolError("mode ist both, left, right, lines oder blank.")
        return ok("text.trim", f"{len(value)} → {len(out)} Zeichen", payload=out)

    def lines_sort(text: str, reverse: bool = False, numeric: bool = False,
                   ignore_case: bool = True) -> ToolResult:
        zeilen = _check(text).splitlines()
        if numeric:
            def key(line: str):
                match = _NUMBER.search(line)
                return (float(match.group().replace(",", ".")) if match else float("inf"))
        elif ignore_case:
            key = str.lower
        else:
            key = None
        out = sorted(zeilen, key=key, reverse=bool(reverse))
        return ok("text.lines.sort", f"{len(out)} Zeilen sortiert",
                  payload="\n".join(out), zeilen=len(out))

    def lines_unique(text: str, keep_order: bool = True,
                     ignore_case: bool = False) -> ToolResult:
        zeilen = _check(text).splitlines()
        gesehen, out = set(), []
        for line in zeilen:
            schluessel = line.lower() if ignore_case else line
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            out.append(line)
        if not keep_order:
            out.sort()
        return ok("text.lines.unique",
                  f"{len(zeilen)} → {len(out)} Zeilen ({len(zeilen) - len(out)} entfernt)",
                  payload="\n".join(out), entfernt=len(zeilen) - len(out))

    def lines_reverse(text: str) -> ToolResult:
        out = list(reversed(_check(text).splitlines()))
        return ok("text.lines.reverse", f"{len(out)} Zeilen umgedreht",
                  payload="\n".join(out), zeilen=len(out))

    def lines_number(text: str, start: int = 1) -> ToolResult:
        zeilen = _check(text).splitlines()
        breite = len(str(len(zeilen) + int(start or 1)))
        out = [f"{i:>{breite}}  {line}"
               for i, line in enumerate(zeilen, start=int(start or 1))]
        return ok("text.lines.number", f"{len(out)} Zeilen nummeriert",
                  payload="\n".join(out), zeilen=len(out))

    def lines_filter(text: str, pattern: str, invert: bool = False,
                     ignore_case: bool = True) -> ToolResult:
        try:
            regex = re.compile(pattern or "", re.I if ignore_case else 0)
        except re.error as exc:
            raise ToolError(f"Ungültiger regulärer Ausdruck: {exc}") from exc
        zeilen = _check(text).splitlines()
        out = [l for l in zeilen if bool(regex.search(l)) != bool(invert)]
        return ok("text.lines.filter", f"{len(out)} von {len(zeilen)} Zeilen",
                  payload="\n".join(out), treffer=len(out), gesamt=len(zeilen))

    def text_indent(text: str, spaces: int = 4, prefix: str = "") -> ToolResult:
        marke = prefix if prefix else " " * max(0, min(int(spaces or 4), 40))
        out = textwrap.indent(_check(text), marke)
        return ok("text.indent", f"{len(marke)} Zeichen Einzug", payload=out)

    def text_dedent(text: str) -> ToolResult:
        out = textwrap.dedent(_check(text))
        return ok("text.dedent", f"{len(text) - len(out)} Zeichen entfernt", payload=out)

    def text_wrap(text: str, width: int = 80) -> ToolResult:
        breite = max(20, min(int(width or 80), 500))
        absaetze = _check(text).split("\n\n")
        out = "\n\n".join(textwrap.fill(a, width=breite) for a in absaetze)
        return ok("text.wrap", f"auf {breite} Zeichen umbrochen", payload=out,
                  breite=breite)

    def text_replace(text: str, search: str, replace: str = "",
                     count: int = 0) -> ToolResult:
        if not search:
            raise ToolError("Es wurde kein Suchtext angegeben.")
        value = _check(text)
        treffer = value.count(search)
        out = value.replace(search, replace, int(count) if count else -1)
        return ok("text.replace", f"{treffer} Stellen ersetzt", payload=out,
                  treffer=treffer)

    def text_split(text: str, separator: str = "\n", limit: int = 0) -> ToolResult:
        teile = _check(text).split(separator or "\n", int(limit) if limit else -1)
        return ok("text.split", f"{len(teile)} Teile",
                  payload=json.dumps(teile, ensure_ascii=False, indent=2),
                  teile=len(teile))

    def text_join(text: str, separator: str = ", ") -> ToolResult:
        """Zeilen zu einer Zeile. Der häufigste Fall: eine Liste in einen
        kommagetrennten Aufzählungstext verwandeln."""
        teile = [l for l in _check(text).splitlines() if l.strip()]
        out = (separator if separator is not None else ", ").join(teile)
        return ok("text.join", f"{len(teile)} Teile verbunden", payload=out,
                  teile=len(teile))

    # ═══════════════════════════════════════════════════ Reguläre Ausdrücke
    def regex_test(pattern: str, text: str, ignore_case: bool = False) -> ToolResult:
        try:
            regex = re.compile(pattern or "", re.I if ignore_case else 0)
        except re.error as exc:
            raise ToolError(f"Ungültiger regulärer Ausdruck: {exc}") from exc
        treffer = list(regex.finditer(_check(text)))
        rows = [[m.start(), m.group()[:80]] for m in treffer[:200]]
        return ok("text.regex.test", f"{len(treffer)} Treffer",
                  payload=table(rows, ["position", "treffer"]) if rows else "(kein Treffer)",
                  treffer=len(treffer), gruppen=regex.groups)

    def regex_replace(pattern: str, text: str, replace: str = "",
                      ignore_case: bool = False, count: int = 0) -> ToolResult:
        try:
            regex = re.compile(pattern or "", re.I if ignore_case else 0)
        except re.error as exc:
            raise ToolError(f"Ungültiger regulärer Ausdruck: {exc}") from exc
        try:
            out, anzahl = regex.subn(replace, _check(text), count=max(0, int(count or 0)))
        except re.error as exc:
            raise ToolError(f"Ersatztext ist ungültig: {exc}") from exc
        return ok("text.regex.replace", f"{anzahl} Stellen ersetzt", payload=out,
                  treffer=anzahl)

    def regex_extract(pattern: str, text: str, group: int = 0,
                      ignore_case: bool = False) -> ToolResult:
        try:
            regex = re.compile(pattern or "", re.I if ignore_case else 0)
        except re.error as exc:
            raise ToolError(f"Ungültiger regulärer Ausdruck: {exc}") from exc
        nummer = max(0, int(group or 0))
        if nummer > regex.groups:
            raise ToolError(f"Gruppe {nummer} gibt es nicht -- das Muster hat "
                            f"{regex.groups} Gruppe(n).")
        werte = [m.group(nummer) for m in regex.finditer(_check(text))]
        return ok("text.regex.extract", f"{len(werte)} Fundstellen",
                  payload="\n".join(werte) or "(nichts gefunden)", treffer=len(werte))

    # ══════════════════════════════════════════════════════════════ Analyse
    def text_count(text: str) -> ToolResult:
        value = _check(text)
        woerter = _words(value)
        werte = {"zeichen": len(value),
                 "zeichen_ohne_leer": len(re.sub(r"\s", "", value)),
                 "woerter": len(woerter),
                 "zeilen": len(value.splitlines()),
                 "absaetze": len([a for a in value.split("\n\n") if a.strip()]),
                 "saetze": len([s for s in re.split(r"[.!?]+", value) if s.strip()])}
        return ok("text.count", f"{werte['woerter']} Wörter, {werte['zeichen']} Zeichen",
                  payload="\n".join(f"{k}: {v}" for k, v in werte.items()), **werte)

    def text_frequency(text: str, limit: int = 20, min_length: int = 3) -> ToolResult:
        woerter = [w.lower() for w in _words(_check(text))
                   if len(w) >= max(1, int(min_length or 3))]
        zaehler = Counter(woerter)
        top = zaehler.most_common(max(1, min(int(limit or 20), 500)))
        return ok("text.frequency", f"{len(zaehler)} verschiedene Wörter",
                  payload=table([[w, n] for w, n in top], ["wort", "anzahl"]),
                  verschieden=len(zaehler), gesamt=len(woerter))

    def text_diff(text_a: str, text_b: str, context: int = 3) -> ToolResult:
        a, b = _check(text_a, "text_a").splitlines(), _check(text_b, "text_b").splitlines()
        if a == b:
            return ok("text.diff", "Die Texte sind identisch", identisch=True)
        diff = list(difflib.unified_diff(a, b, fromfile="a", tofile="b", lineterm="",
                                         n=max(0, int(context or 3))))
        plus = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        minus = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        return ok("text.diff", f"+{plus} −{minus}", payload="\n".join(diff[:500]),
                  identisch=False, hinzugefuegt=plus, entfernt=minus)

    def text_similarity(text_a: str, text_b: str) -> ToolResult:
        quote = difflib.SequenceMatcher(None, _check(text_a, "text_a"),
                                        _check(text_b, "text_b")).ratio()
        return ok("text.similarity", f"Ähnlichkeit {quote * 100:.1f} %",
                  aehnlichkeit=round(quote, 4))

    def language_detect(text: str) -> ToolResult:
        """Eine **Schätzung** über Funktionswörter, keine Feststellung -- und
        sie wird auch als solche gemeldet. Für eine echte Erkennung bräuchte
        es ein Sprachmodell oder eine n-Gramm-Bibliothek."""
        woerter = {w.lower() for w in _words(_check(text))}
        if not woerter:
            raise ToolError("Der Text enthält keine erkennbaren Wörter.")
        treffer = {name: len(woerter & stop) for name, stop in _STOPWORDS.items()}
        beste = max(treffer, key=lambda k: treffer[k])
        if treffer[beste] == 0:
            # Ausdrücklich "unbekannt" statt None: ``ok()`` lässt None-Werte
            # aus dem Beleg fallen, und ein fehlendes Feld liest sich wie ein
            # Fehler im Werkzeug statt wie ein ehrliches "weiß ich nicht".
            return ok("text.language.detect",
                      "Keine der geprüften Sprachen erkennbar (zu kurz oder "
                      "eine andere Sprache)", sprache="unbekannt", treffer=0,
                      schaetzung=True, geprueft=", ".join(_STOPWORDS))
        return ok("text.language.detect",
                  f"Vermutlich {beste} ({treffer[beste]} Funktionswörter getroffen)",
                  payload=table([[k, v] for k, v in sorted(treffer.items(),
                                                           key=lambda kv: -kv[1])],
                                ["sprache", "treffer"]),
                  sprache=beste, treffer=treffer[beste], schaetzung=True)

    def extract_emails(text: str) -> ToolResult:
        werte = list(dict.fromkeys(_EMAIL.findall(_check(text))))
        return ok("text.extract.emails", f"{len(werte)} E-Mail-Adressen",
                  payload="\n".join(werte) or "(keine)", treffer=len(werte))

    def extract_urls(text: str) -> ToolResult:
        werte = list(dict.fromkeys(_URL.findall(_check(text))))
        return ok("text.extract.urls", f"{len(werte)} URLs",
                  payload="\n".join(werte) or "(keine)", treffer=len(werte))

    def extract_numbers(text: str) -> ToolResult:
        werte = _NUMBER.findall(_check(text))
        zahlen = [float(w.replace(",", ".")) for w in werte]
        summe = sum(zahlen)
        return ok("text.extract.numbers", f"{len(werte)} Zahlen, Summe {summe:g}",
                  payload="\n".join(werte) or "(keine)", treffer=len(werte),
                  summe=round(summe, 6),
                  mittel=round(summe / len(zahlen), 6) if zahlen else None)

    def extract_ips(text: str) -> ToolResult:
        # Die Regex findet auch 999.999.999.999 -- deshalb wird hier noch
        # geprüft, statt eine Fundstelle als IP auszugeben, die keine ist.
        gefunden = [ip for ip in dict.fromkeys(_IPV4.findall(_check(text)))
                    if all(0 <= int(teil) <= 255 for teil in ip.split("."))]
        return ok("text.extract.ips", f"{len(gefunden)} IPv4-Adressen",
                  payload="\n".join(gefunden) or "(keine)", treffer=len(gefunden))

    # ════════════════════════════════════════════════════════ HTML/Markdown
    def html_to_text(text: str) -> ToolResult:
        parser = _TextExtractor()
        parser.feed(_check(text))
        out = parser.result()
        return ok("text.html.to_text", f"{len(out)} Zeichen Text", payload=out,
                  zeichen=len(out))

    def markdown_headings(text: str) -> ToolResult:
        rows = []
        for nummer, line in enumerate(_check(text).splitlines(), start=1):
            match = re.match(r"^(#{1,6})\s+(.*)", line)
            if match:
                rows.append([nummer, len(match.group(1)), match.group(2).strip()])
        return ok("text.markdown.headings", f"{len(rows)} Überschriften",
                  payload=table(rows, ["zeile", "ebene", "titel"]) if rows
                  else "(keine)", treffer=len(rows))

    def markdown_to_html(text: str) -> ToolResult:
        """Ein bewusst **kleiner** Wandler: Überschriften, Fett, Kursiv, Code,
        Links, Listen, Absätze. Keine Tabellen, keine Fußnoten, kein HTML im
        Markdown. Was er nicht kann, steht hier, damit niemand mehr erwartet,
        als er liefert."""
        zeilen = _check(text).splitlines()
        out: list[str] = []
        in_liste = False
        in_code = False
        for line in zeilen:
            if line.strip().startswith("```"):
                out.append("</pre>" if in_code else "<pre>")
                in_code = not in_code
                continue
            if in_code:
                out.append(html_mod.escape(line))
                continue
            kopf = re.match(r"^(#{1,6})\s+(.*)", line)
            listenpunkt = re.match(r"^\s*[-*+]\s+(.*)", line)
            if listenpunkt and not in_liste:
                out.append("<ul>")
                in_liste = True
            elif not listenpunkt and in_liste:
                out.append("</ul>")
                in_liste = False
            if kopf:
                ebene = len(kopf.group(1))
                out.append(f"<h{ebene}>{_inline(kopf.group(2))}</h{ebene}>")
            elif listenpunkt:
                out.append(f"  <li>{_inline(listenpunkt.group(1))}</li>")
            elif line.strip():
                out.append(f"<p>{_inline(line.strip())}</p>")
        if in_liste:
            out.append("</ul>")
        if in_code:
            out.append("</pre>")
        html_out = "\n".join(out)
        return ok("text.markdown.to_html", f"{len(html_out)} Zeichen HTML",
                  payload=html_out, hinweis="ohne Tabellen, Fußnoten und rohes HTML")

    # ══════════════════════════════════════════════════════════════ Zeit
    def timestamp_now(format: str = "") -> ToolResult:
        jetzt = time.time()
        muster = format or "%Y-%m-%d %H:%M:%S"
        try:
            formatiert = time.strftime(muster, time.localtime(jetzt))
        except ValueError as exc:
            raise ToolError(f"Ungültiges Zeitformat: {exc}") from exc
        return ok("text.timestamp.now", formatiert, payload=formatiert,
                  unix=round(jetzt, 3),
                  utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(jetzt)))

    def timestamp_parse(value: str) -> ToolResult:
        """Nimmt eine Unix-Zeit oder ein ISO-Datum und gibt beides zurück --
        die Umrechnung, die man in Logdateien ständig braucht."""
        rohwert = (value or "").strip()
        if not rohwert:
            raise ToolError("Es wurde kein Zeitwert angegeben.")
        if re.fullmatch(r"-?\d+(\.\d+)?", rohwert):
            sekunden = float(rohwert)
            # Millisekunden erkennen: alles ab 10^11 ist als Sekunde das Jahr
            # 5138 -- praktisch immer eine Zeit in Millisekunden.
            if abs(sekunden) > 1e11:
                sekunden /= 1000.0
        else:
            for muster in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                           "%Y-%m-%d", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
                try:
                    sekunden = time.mktime(time.strptime(rohwert.rstrip("Z"), muster))
                    break
                except ValueError:
                    continue
            else:
                raise ToolError(f"Zeitformat nicht erkannt: {rohwert}")
        return ok("text.timestamp.parse",
                  time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sekunden)),
                  unix=round(sekunden, 3),
                  lokal=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sekunden)),
                  utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sekunden)),
                  wochentag=time.strftime("%A", time.localtime(sekunden)))

    # ═══════════════════════════════════════════════════════ Registrierung
    _t = text("Der Eingabetext")
    return [
        # Kodierung
        Tool("text.base64.encode", "Kodiert Text als Base64.",
             params("text", text=_t, urlsafe=flag("URL-sicheres Alphabet")),
             base64_encode, level=P.SAFE, tags=("kodierung", "base64"),
             phrases=("base64 kodieren", "in base64 umwandeln")),
        Tool("text.base64.decode", "Dekodiert Base64 zurück zu Text.",
             params("text", text=text("Der Base64-Text"), urlsafe=flag("URL-sicher")),
             base64_decode, level=P.SAFE, tags=("kodierung", "base64"),
             phrases=("base64 dekodieren", "was steht in dem base64")),
        Tool("text.url.encode", "Kodiert Text für die Verwendung in einer URL.",
             params("text", text=_t, safe=text("Zeichen, die bleiben dürfen")),
             url_encode, level=P.SAFE, tags=("kodierung", "url")),
        Tool("text.url.decode", "Dekodiert prozentkodierten URL-Text.",
             params("text", text=_t), url_decode, level=P.SAFE,
             tags=("kodierung", "url")),
        Tool("text.html.escape", "Macht Text HTML-sicher (< > & \" ').",
             params("text", text=_t), html_escape, level=P.SAFE,
             tags=("kodierung", "html")),
        Tool("text.html.unescape", "Wandelt HTML-Entities zurück in Zeichen.",
             params("text", text=_t), html_unescape, level=P.SAFE,
             tags=("kodierung", "html")),
        Tool("text.hex.encode", "Kodiert Text als Hexadezimal.",
             params("text", text=_t), hex_encode, level=P.SAFE, tags=("kodierung", "hex")),
        Tool("text.hex.decode", "Dekodiert Hexadezimal zurück zu Text.",
             params("text", text=_t), hex_decode, level=P.SAFE, tags=("kodierung", "hex")),
        Tool("text.rot13", "Wendet ROT13 an (zweimal anwenden hebt es auf).",
             params("text", text=_t), rot13, level=P.SAFE, tags=("kodierung",)),
        Tool("text.hash", "Bildet eine Prüfsumme über einen Text.",
             params("text", text=_t, algorithm=text("md5, sha1, sha256, sha512")),
             text_hash, level=P.SAFE, tags=("hash", "pruefsumme"),
             phrases=("hash von dem text", "sha256 bilden")),
        Tool("text.uuid", "Erzeugt eine oder mehrere UUIDs.",
             params(version=integer("1 oder 4 (Vorgabe)"), count=INT),
             make_uuid, level=P.SAFE, tags=("id", "uuid"),
             phrases=("uuid erzeugen", "eine zufällige id")),
        Tool("text.slug", "Macht aus einem Titel einen URL-tauglichen Slug.",
             params("text", text=_t, separator=text("Trennzeichen, Vorgabe '-'")),
             slugify, level=P.SAFE, tags=("url", "text"),
             phrases=("slug erzeugen", "url-freundlich machen")),
        Tool("text.random.string", "Erzeugt eine zufällige Zeichenkette.",
             params(length=INT, alphabet=text("Erlaubte Zeichen")),
             random_string, level=P.SAFE, tags=("zufall",)),
        Tool("text.password.generate",
             "Erzeugt ein Passwort aus kryptografischem Zufall.",
             params(length=integer("8–128, Vorgabe 20"),
                    symbols=flag("Sonderzeichen erlauben")),
             password_generate, level=P.SAFE, tags=("zufall", "passwort"),
             phrases=("passwort erzeugen", "sicheres passwort")),

        # Strukturformate
        Tool("text.json.format", "Formatiert JSON lesbar und eingerückt.",
             params("text", text=text("Das JSON"), indent=INT,
                    sort_keys=flag("Schlüssel alphabetisch sortieren")),
             json_format, level=P.SAFE, tags=("json", "format"),
             phrases=("json formatieren", "json schön machen", "json einrücken")),
        Tool("text.json.minify", "Entfernt alle Leerzeichen aus JSON.",
             params("text", text=STR), json_minify, level=P.SAFE, tags=("json",)),
        Tool("text.json.validate", "Prüft, ob ein Text gültiges JSON ist.",
             params("text", text=STR), json_validate, level=P.SAFE,
             tags=("json", "pruefen"), phrases=("ist das gültiges json",)),
        Tool("text.json.keys", "Listet die Schlüsselpfade eines JSON-Dokuments.",
             params("text", text=STR, depth=integer("Tiefe, Vorgabe 2")),
             json_keys, level=P.SAFE, tags=("json", "struktur"),
             phrases=("welche felder hat das json", "struktur des json")),
        Tool("text.json.to_yaml", "Wandelt JSON in YAML um.",
             params("text", text=STR), json_to_yaml, level=P.SAFE,
             tags=("json", "yaml"), requires=("yaml",)),
        Tool("text.yaml.to_json", "Wandelt YAML in JSON um.",
             params("text", text=STR, indent=INT), yaml_to_json, level=P.SAFE,
             tags=("json", "yaml"), requires=("yaml",)),
        Tool("text.yaml.validate", "Prüft, ob ein Text gültiges YAML ist.",
             params("text", text=STR), yaml_validate, level=P.SAFE,
             tags=("yaml", "pruefen"), requires=("yaml",)),
        Tool("text.xml.format", "Formatiert XML lesbar und eingerückt.",
             params("text", text=STR, indent=INT), xml_format, level=P.SAFE,
             tags=("xml", "format")),
        Tool("text.xml.validate", "Prüft, ob ein Text wohlgeformtes XML ist.",
             params("text", text=STR), xml_validate, level=P.SAFE,
             tags=("xml", "pruefen")),
        Tool("text.csv.to_json", "Wandelt CSV-Text in JSON-Datensätze um.",
             params("text", text=STR, delimiter=text("Trennzeichen, sonst geraten"),
                    header=flag("Erste Zeile ist die Kopfzeile")),
             csv_to_json, level=P.SAFE, tags=("csv", "json")),
        Tool("text.json.to_csv", "Wandelt eine JSON-Objektliste in CSV um.",
             params("text", text=STR, delimiter=STR), json_to_csv, level=P.SAFE,
             tags=("csv", "json")),

        # Umformungen
        Tool("text.case",
             "Ändert die Schreibweise: lower, upper, title, sentence, snake, "
             "kebab, camel, pascal, swap.",
             params("text", text=_t, style=text("Der Zielstil")),
             case_change, level=P.SAFE, tags=("text", "schreibweise"),
             phrases=("in großbuchstaben", "snake_case machen", "camelcase")),
        Tool("text.trim", "Entfernt Leerraum: both, left, right, lines, blank.",
             params("text", text=_t, mode=text("both (Vorgabe), left, right, lines, blank")),
             text_trim, level=P.SAFE, tags=("text", "aufraeumen")),
        Tool("text.lines.sort", "Sortiert Zeilen alphabetisch oder numerisch.",
             params("text", text=_t, reverse=flag("Absteigend"),
                    numeric=flag("Nach der ersten Zahl je Zeile"),
                    ignore_case=flag("Groß/Klein ignorieren")),
             lines_sort, level=P.SAFE, tags=("text", "zeilen", "sortieren"),
             phrases=("zeilen sortieren", "alphabetisch ordnen")),
        Tool("text.lines.unique", "Entfernt doppelte Zeilen.",
             params("text", text=_t, keep_order=flag("Reihenfolge beibehalten"),
                    ignore_case=flag("Groß/Klein ignorieren")),
             lines_unique, level=P.SAFE, tags=("text", "zeilen", "duplikate"),
             phrases=("doppelte zeilen entfernen", "duplikate raus")),
        Tool("text.lines.reverse", "Dreht die Reihenfolge der Zeilen um.",
             params("text", text=_t), lines_reverse, level=P.SAFE,
             tags=("text", "zeilen")),
        Tool("text.lines.number", "Stellt jeder Zeile ihre Nummer voran.",
             params("text", text=_t, start=INT), lines_number, level=P.SAFE,
             tags=("text", "zeilen")),
        Tool("text.lines.filter", "Behält nur Zeilen, die ein Muster treffen.",
             params("text", "pattern", text=_t,
                    pattern=text("Regulärer Ausdruck"),
                    invert=flag("Stattdessen die Treffer entfernen"),
                    ignore_case=flag("Groß/Klein ignorieren")),
             lines_filter, level=P.SAFE, tags=("text", "zeilen", "filter"),
             phrases=("zeilen filtern", "nur die zeilen mit")),
        Tool("text.indent", "Rückt alle Zeilen ein.",
             params("text", text=_t, spaces=INT, prefix=text("Eigenes Präfix")),
             text_indent, level=P.SAFE, tags=("text", "format")),
        Tool("text.dedent", "Entfernt den gemeinsamen Einzug aller Zeilen.",
             params("text", text=_t), text_dedent, level=P.SAFE, tags=("text", "format")),
        Tool("text.wrap", "Bricht Text auf eine feste Zeilenbreite um.",
             params("text", text=_t, width=integer("Vorgabe 80")),
             text_wrap, level=P.SAFE, tags=("text", "format")),
        Tool("text.replace", "Ersetzt Text (wörtlich, nicht als Muster).",
             params("text", "search", text=_t, search=STR, replace=STR, count=INT),
             text_replace, level=P.SAFE, tags=("text", "ersetzen")),
        Tool("text.split", "Zerlegt Text an einem Trennzeichen.",
             params("text", text=_t, separator=STR, limit=INT),
             text_split, level=P.SAFE, tags=("text", "zerlegen")),
        Tool("text.join", "Verbindet Zeilen zu einer Zeile.",
             params("text", text=_t, separator=text("Trenner, Vorgabe ', '")),
             text_join, level=P.SAFE, tags=("text", "verbinden")),

        # Reguläre Ausdrücke
        Tool("text.regex.test", "Probiert einen regulären Ausdruck an einem Text aus.",
             params("pattern", "text", pattern=STR, text=_t,
                    ignore_case=flag("Groß/Klein ignorieren")),
             regex_test, level=P.SAFE, tags=("regex", "pruefen"),
             phrases=("regex testen", "passt der ausdruck")),
        Tool("text.regex.replace", "Ersetzt über einen regulären Ausdruck.",
             params("pattern", "text", pattern=STR, text=_t, replace=STR,
                    ignore_case=flag("Groß/Klein ignorieren"), count=INT),
             regex_replace, level=P.SAFE, tags=("regex", "ersetzen")),
        Tool("text.regex.extract", "Holt alle Treffer (oder eine Gruppe) heraus.",
             params("pattern", "text", pattern=STR, text=_t,
                    group=integer("Gruppennummer, 0 = ganzer Treffer"),
                    ignore_case=flag("Groß/Klein ignorieren")),
             regex_extract, level=P.SAFE, tags=("regex", "extrahieren")),

        # Analyse
        Tool("text.count", "Zählt Zeichen, Wörter, Zeilen, Sätze und Absätze.",
             params("text", text=_t), text_count, level=P.SAFE,
             tags=("text", "zaehlen"),
             phrases=("wie viele wörter", "zeichen zählen", "wortanzahl")),
        Tool("text.frequency", "Zählt, welche Wörter am häufigsten vorkommen.",
             params("text", text=_t, limit=INT,
                    min_length=integer("Kürzere Wörter überspringen")),
             text_frequency, level=P.SAFE, tags=("text", "statistik"),
             phrases=("häufigste wörter", "worthäufigkeit")),
        Tool("text.diff", "Zeigt die Unterschiede zwischen zwei Texten.",
             params("text_a", "text_b", text_a=STR, text_b=STR, context=INT),
             text_diff, level=P.SAFE, tags=("vergleich", "diff"),
             phrases=("was ist anders", "texte vergleichen")),
        Tool("text.similarity", "Misst, wie ähnlich zwei Texte sind (0 bis 1).",
             params("text_a", "text_b", text_a=STR, text_b=STR),
             text_similarity, level=P.SAFE, tags=("vergleich",)),
        Tool("text.language.detect",
             "Schätzt die Sprache anhand häufiger Funktionswörter.",
             params("text", text=_t), language_detect, level=P.SAFE,
             tags=("text", "sprache"), returns="Vermutete Sprache mit Trefferzahl",
             phrases=("welche sprache ist das",)),
        Tool("text.extract.emails", "Holt alle E-Mail-Adressen aus einem Text.",
             params("text", text=_t), extract_emails, level=P.SAFE,
             tags=("extrahieren", "email")),
        Tool("text.extract.urls", "Holt alle URLs aus einem Text.",
             params("text", text=_t), extract_urls, level=P.SAFE,
             tags=("extrahieren", "url")),
        Tool("text.extract.numbers", "Holt alle Zahlen heraus, mit Summe und Mittel.",
             params("text", text=_t), extract_numbers, level=P.SAFE,
             tags=("extrahieren", "zahlen")),
        Tool("text.extract.ips", "Holt gültige IPv4-Adressen aus einem Text.",
             params("text", text=_t), extract_ips, level=P.SAFE,
             tags=("extrahieren", "netzwerk")),

        # HTML/Markdown
        Tool("text.html.to_text", "Macht aus HTML reinen Text.",
             params("text", text=text("Das HTML")), html_to_text, level=P.SAFE,
             tags=("html", "text"), phrases=("html zu text", "tags entfernen")),
        Tool("text.markdown.headings", "Listet die Überschriften eines Markdown-Texts.",
             params("text", text=STR), markdown_headings, level=P.SAFE,
             tags=("markdown", "struktur")),
        Tool("text.markdown.to_html",
             "Wandelt einfaches Markdown in HTML (ohne Tabellen und Fußnoten).",
             params("text", text=STR), markdown_to_html, level=P.SAFE,
             tags=("markdown", "html")),

        # Zeit
        Tool("text.timestamp.now", "Die aktuelle Zeit, lokal und als Unix-Zeit.",
             params(format=text("strftime-Muster")), timestamp_now, level=P.SAFE,
             tags=("zeit",), phrases=("wie spät ist es", "aktuelle zeit", "datum")),
        Tool("text.timestamp.parse",
             "Rechnet eine Unix-Zeit oder ein Datum in beide Richtungen um.",
             params("value", value=text("Unix-Zeit oder ISO-Datum")),
             timestamp_parse, level=P.SAFE, tags=("zeit", "umrechnen"),
             phrases=("was ist das für ein zeitstempel", "unix zeit umrechnen")),
    ]


def _inline(value: str) -> str:
    """Die Inline-Auszeichnungen von Markdown. Bewusst nach dem Escapen, damit
    fremdes HTML im Markdown nicht durchschlägt."""
    out = html_mod.escape(value)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)
    return out


def _sniff(raw: str) -> str:
    first = (raw.splitlines() or [""])[0]
    counts = {sep: first.count(sep) for sep in (",", ";", "\t", "|")}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] else ","
