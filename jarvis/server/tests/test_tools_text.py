"""Das Text-Pack: jedes Werkzeug einmal wirklich ausgeführt.

Rein lokal und deterministisch -- genau deshalb lässt sich hier jedes
Ergebnis gegen einen bekannten Wert prüfen und nicht nur gegen „ok=True".
"""

from __future__ import annotations

import json

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult


@pytest.fixture
def tools(config, store):
    registry = build_registry(config, store)

    # Positional-only (das '/'), damit ein Tool-Argument namens
    # 'name' nicht mit dem Parameter des Helfers kollidiert.
    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


# ═══════════════════════════════════════════════════════════════ Kodierung
def test_base64_hin_und_zurueck(tools):
    kodiert = erfolg(tools("text.base64.encode", text="Grüße aus Jarvis"))
    assert kodiert.payload == "R3LDvMOfZSBhdXMgSmFydmlz"
    assert erfolg(tools("text.base64.decode",
                        text=kodiert.payload)).payload == "Grüße aus Jarvis"


def test_base64_ohne_padding_wird_trotzdem_dekodiert(tools):
    """Base64 aus JWTs kommt oft ohne '='. Das abzulehnen wäre unnötig streng."""
    assert erfolg(tools("text.base64.decode", text="SGFsbG8")).payload == "Hallo"


def test_base64_mit_binaerinhalt_wird_ehrlich_gemeldet(tools):
    result = erfolg(tools("text.base64.decode", text="/w=="))
    assert result.evidence["textform"] is False
    assert result.payload == "ff"


def test_kaputtes_base64_ist_ein_ehrlicher_fehler(tools):
    assert tools("text.base64.decode", text="!!! kein base64 !!!").ok is False


def test_url_und_html_kodierung(tools):
    assert erfolg(tools("text.url.encode", text="a b&c=d")).payload == "a%20b%26c%3Dd"
    assert erfolg(tools("text.url.decode", text="a%20b%26c")).payload == "a b&c"
    assert erfolg(tools("text.html.escape", text='<a href="x">')).payload == \
        "&lt;a href=&quot;x&quot;&gt;"
    assert erfolg(tools("text.html.unescape", text="&lt;b&gt;")).payload == "<b>"


def test_hex_und_rot13(tools):
    hexwert = erfolg(tools("text.hex.encode", text="Hi"))
    assert hexwert.payload == "4869"
    assert erfolg(tools("text.hex.decode", text="48 69")).payload == "Hi"
    assert tools("text.hex.decode", text="xyz").ok is False

    einmal = erfolg(tools("text.rot13", text="Jarvis")).payload
    assert einmal == "Wneivf"
    assert erfolg(tools("text.rot13", text=einmal)).payload == "Jarvis"


def test_hash_ist_der_bekannte_wert(tools):
    md5 = erfolg(tools("text.hash", text="abc", algorithm="md5"))
    assert md5.payload == "900150983cd24fb0d6963f7d28e17f72"
    sha = erfolg(tools("text.hash", text="abc"))
    assert sha.payload.startswith("ba7816bf")
    assert tools("text.hash", text="abc", algorithm="crc32").ok is False


def test_uuid_und_zufall(tools):
    werte = erfolg(tools("text.uuid", count=3)).payload.splitlines()
    assert len(werte) == 3 and len(set(werte)) == 3
    assert all(len(w) == 36 for w in werte)
    assert tools("text.uuid", version=7).ok is False

    zufall = erfolg(tools("text.random.string", length=24))
    assert len(zufall.payload) == 24


def test_slug_behandelt_umlaute_richtig(tools):
    """Ohne die Sonderbehandlung würde aus 'Grüße' ein 'gre'."""
    assert erfolg(tools("text.slug", text="Grüße aus München!")).payload == \
        "gruesse-aus-muenchen"
    assert erfolg(tools("text.slug", text="A B", separator="_")).payload == "a_b"


def test_passwort_erfuellt_seine_zusage(tools):
    result = erfolg(tools("text.password.generate", length=24))
    wert = result.payload
    assert len(wert) == 24
    assert any(c.islower() for c in wert)
    assert any(c.isupper() for c in wert)
    assert any(c.isdigit() for c in wert)
    # Zwei Aufrufe dürfen nie dasselbe liefern.
    assert wert != erfolg(tools("text.password.generate", length=24)).payload


# ══════════════════════════════════════════════════════════ Strukturformate
def test_json_formatieren_minimieren_pruefen(tools):
    roh = '{"b":1,"a":[1,2]}'
    schoen = erfolg(tools("text.json.format", text=roh, sort_keys=True))
    assert schoen.payload.startswith('{\n  "a"')

    klein = erfolg(tools("text.json.minify", text=schoen.payload))
    assert klein.payload == '{"a":[1,2],"b":1}'

    assert erfolg(tools("text.json.validate", text=roh)).evidence["typ"] == "dict"
    assert tools("text.json.validate", text="{kaputt").ok is False


def test_json_schluesselpfade(tools):
    roh = json.dumps({"server": {"port": 8770, "hosts": [{"ip": "127.0.0.1"}]}})
    result = erfolg(tools("text.json.keys", text=roh, depth=4))
    assert "server.port" in result.payload
    assert "server.hosts[].ip" in result.payload


def test_yaml_und_json_hin_und_zurueck(tools):
    y = erfolg(tools("text.json.to_yaml", text='{"a": 1, "b": [2, 3]}'))
    assert "a: 1" in y.payload
    zurueck = erfolg(tools("text.yaml.to_json", text=y.payload))
    assert json.loads(zurueck.payload) == {"a": 1, "b": [2, 3]}
    assert erfolg(tools("text.yaml.validate", text="a: 1")).evidence["typ"] == "dict"
    assert tools("text.yaml.validate", text="a: [1,\n b").ok is False


def test_xml_formatieren_und_pruefen(tools):
    result = erfolg(tools("text.xml.format", text="<a><b>x</b></a>"))
    assert "<b>x</b>" in result.payload
    assert erfolg(tools("text.xml.validate",
                        text="<a><b/></a>")).evidence["wurzel"] == "a"
    assert tools("text.xml.validate", text="<a><b></a>").ok is False


def test_csv_und_json_hin_und_zurueck(tools):
    csv_text = "name;menge\nSchraube;12\nMutter;30"
    als_json = erfolg(tools("text.csv.to_json", text=csv_text))
    daten = json.loads(als_json.payload)
    assert daten == [{"name": "Schraube", "menge": "12"},
                     {"name": "Mutter", "menge": "30"}]
    assert als_json.evidence["trenner"] == ";"

    zurueck = erfolg(tools("text.json.to_csv", text=als_json.payload, delimiter=";"))
    assert zurueck.payload.splitlines()[0] == "name;menge"
    assert tools("text.json.to_csv", text='{"a":1}').ok is False


# ═══════════════════════════════════════════════════════════ Umformungen
@pytest.mark.parametrize("stil,erwartet", [
    ("upper", "HALLO WELT DU"), ("lower", "hallo welt du"),
    ("snake", "hallo_welt_du"), ("kebab", "hallo-welt-du"),
    ("camel", "halloWeltDu"), ("pascal", "HalloWeltDu"),
])
def test_schreibweisen(tools, stil, erwartet):
    assert erfolg(tools("text.case", text="Hallo Welt Du", style=stil)).payload == erwartet


def test_unbekannter_stil_ist_ein_ehrlicher_fehler(tools):
    fehl = tools("text.case", text="x", style="klingonisch")
    assert fehl.ok is False and "Möglich" in fehl.summary


def test_trim_varianten(tools):
    assert erfolg(tools("text.trim", text="  x  ")).payload == "x"
    assert erfolg(tools("text.trim", text="  a\n  b", mode="lines")).payload == "a\nb"
    assert erfolg(tools("text.trim", text="a\n\nb", mode="blank")).payload == "a\nb"
    assert tools("text.trim", text="x", mode="irgendwie").ok is False


def test_zeilenwerkzeuge(tools):
    roh = "banane\nApfel\nbanane\nCitrone"
    assert erfolg(tools("text.lines.sort", text=roh)).payload.splitlines()[0] == "Apfel"
    entdoppelt = erfolg(tools("text.lines.unique", text=roh))
    assert entdoppelt.evidence["entfernt"] == 1
    assert erfolg(tools("text.lines.reverse", text=roh)).payload.splitlines()[0] == "Citrone"
    assert "1  banane" in erfolg(tools("text.lines.number", text=roh)).payload

    gefiltert = erfolg(tools("text.lines.filter", text=roh, pattern="an"))
    assert gefiltert.evidence["treffer"] == 2
    umgekehrt = erfolg(tools("text.lines.filter", text=roh, pattern="an", invert=True))
    assert umgekehrt.evidence["treffer"] == 2
    assert tools("text.lines.filter", text=roh, pattern="[kaputt").ok is False


def test_numerisch_sortieren(tools):
    roh = "Datei 10\nDatei 2\nDatei 1"
    numerisch = erfolg(tools("text.lines.sort", text=roh, numeric=True))
    assert numerisch.payload.splitlines() == ["Datei 1", "Datei 2", "Datei 10"]


def test_einzug_umbruch_ersetzen(tools):
    assert erfolg(tools("text.indent", text="a\nb", spaces=2)).payload == "  a\n  b"
    assert erfolg(tools("text.dedent", text="  a\n  b")).payload == "a\nb"
    lang = erfolg(tools("text.wrap", text="wort " * 40, width=30))
    assert all(len(z) <= 30 for z in lang.payload.splitlines())

    ersetzt = erfolg(tools("text.replace", text="a-a-a", search="a", replace="b"))
    assert ersetzt.payload == "b-b-b" and ersetzt.evidence["treffer"] == 3
    assert tools("text.replace", text="x", search="").ok is False


def test_split_und_join(tools):
    teile = erfolg(tools("text.split", text="a,b,c", separator=","))
    assert json.loads(teile.payload) == ["a", "b", "c"]
    assert erfolg(tools("text.join", text="a\nb\nc")).payload == "a, b, c"


# ═══════════════════════════════════════════════════ Reguläre Ausdrücke
def test_regex_werkzeuge(tools):
    probe = erfolg(tools("text.regex.test", pattern=r"\d+", text="a1 b22 c333"))
    assert probe.evidence["treffer"] == 3

    ersetzt = erfolg(tools("text.regex.replace", pattern=r"\d+", text="a1 b22",
                           replace="#"))
    assert ersetzt.payload == "a# b#"

    gruppe = erfolg(tools("text.regex.extract", pattern=r"(\w)(\d+)",
                          text="a1 b22", group=2))
    assert gruppe.payload == "1\n22"

    assert tools("text.regex.test", pattern="[", text="x").ok is False
    fehl = tools("text.regex.extract", pattern=r"\d", text="1", group=5)
    assert fehl.ok is False and "Gruppe 5" in fehl.summary


# ══════════════════════════════════════════════════════════════ Analyse
def test_zaehlen_und_haeufigkeit(tools):
    result = erfolg(tools("text.count", text="Eins zwei. Drei vier!\n\nFünf."))
    assert result.evidence["woerter"] == 5
    assert result.evidence["saetze"] == 3
    assert result.evidence["absaetze"] == 2

    haeufig = erfolg(tools("text.frequency", text="haus haus baum haus baum tor"))
    assert haeufig.payload.splitlines()[2].startswith("haus")


def test_diff_und_aehnlichkeit(tools):
    gleich = erfolg(tools("text.diff", text_a="a\nb", text_b="a\nb"))
    assert gleich.evidence["identisch"] is True

    anders = erfolg(tools("text.diff", text_a="a\nb", text_b="a\nc"))
    assert anders.evidence == {"identisch": False, "hinzugefuegt": 1, "entfernt": 1}

    quote = erfolg(tools("text.similarity", text_a="Jarvis", text_b="Jarvis"))
    assert quote.evidence["aehnlichkeit"] == 1.0


def test_spracherkennung_meldet_sich_als_schaetzung(tools):
    deutsch = erfolg(tools("text.language.detect",
                           text="Der Hund ist nicht auf dem Sofa und das ist gut"))
    assert deutsch.evidence["sprache"] == "deutsch"
    assert deutsch.evidence["schaetzung"] is True

    englisch = erfolg(tools("text.language.detect",
                            text="The dog is not on the sofa and that is fine"))
    assert englisch.evidence["sprache"] == "englisch"

    unklar = erfolg(tools("text.language.detect", text="xyzzy plugh frobnitz"))
    assert unklar.evidence["sprache"] == "unbekannt"
    assert tools("text.language.detect", text="   ").ok is False


def test_extrahieren(tools):
    roh = ("Schreib an a@b.de oder chef@firma.com, siehe https://example.org/x "
           "— Server 10.0.0.5 und 999.1.1.1, Menge 12 und 3,5")
    assert erfolg(tools("text.extract.emails", text=roh)).evidence["treffer"] == 2
    assert erfolg(tools("text.extract.urls", text=roh)).evidence["treffer"] == 1

    zahlen = erfolg(tools("text.extract.numbers", text="Menge 12 und 3,5"))
    assert zahlen.evidence["summe"] == 15.5

    ips = erfolg(tools("text.extract.ips", text=roh))
    assert ips.evidence["treffer"] == 1, "999.1.1.1 ist keine gültige IPv4"
    assert "10.0.0.5" in ips.payload


# ═══════════════════════════════════════════════════════════ HTML/Markdown
def test_html_zu_text_wirft_skripte_weg(tools):
    html = "<html><head><style>p{color:red}</style></head><body><p>Hallo</p>" \
           "<script>alert(1)</script><p>Welt</p></body></html>"
    result = erfolg(tools("text.html.to_text", text=html))
    assert "alert" not in result.payload and "color" not in result.payload
    assert "Hallo" in result.payload and "Welt" in result.payload


def test_markdown_ueberschriften_und_html(tools):
    md = "# Titel\n\nText mit **fett** und `code`.\n\n- eins\n- zwei\n\n## Unten"
    kopf = erfolg(tools("text.markdown.headings", text=md))
    assert kopf.evidence["treffer"] == 2 and "Titel" in kopf.payload

    html = erfolg(tools("text.markdown.to_html", text=md))
    assert "<h1>Titel</h1>" in html.payload
    assert "<strong>fett</strong>" in html.payload
    assert "<code>code</code>" in html.payload
    assert "<ul>" in html.payload and "<li>eins</li>" in html.payload


def test_markdown_laesst_fremdes_html_nicht_durch(tools):
    """Rohes HTML im Markdown wird escapt, nicht übernommen -- sonst wäre der
    Wandler ein Einfallstor."""
    result = erfolg(tools("text.markdown.to_html", text="Hallo <script>böse</script>"))
    assert "<script>" not in result.payload
    assert "&lt;script&gt;" in result.payload


# ══════════════════════════════════════════════════════════════════ Zeit
def test_zeitstempel(tools):
    jetzt = erfolg(tools("text.timestamp.now"))
    assert jetzt.evidence["unix"] > 1_600_000_000

    geparst = erfolg(tools("text.timestamp.parse", value="1700000000"))
    assert geparst.evidence["utc"] == "2023-11-14T22:13:20Z"

    # Millisekunden werden als solche erkannt, nicht als Jahr 55000.
    millis = erfolg(tools("text.timestamp.parse", value="1700000000000"))
    assert millis.evidence["utc"] == "2023-11-14T22:13:20Z"

    iso = erfolg(tools("text.timestamp.parse", value="2024-01-02"))
    assert iso.evidence["lokal"].startswith("2024-01-02")

    assert tools("text.timestamp.parse", value="irgendwann").ok is False
    assert tools("text.timestamp.parse", value="").ok is False
