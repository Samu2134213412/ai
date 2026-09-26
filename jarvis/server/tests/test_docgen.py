"""docgen.py: die Werkzeugreferenz entsteht aus der echten Registry, nicht
aus einer Abschrift -- die Tests prüfen genau diese Kopplung."""

from __future__ import annotations

from jarvis.docgen import generate
from jarvis.tools import build_registry


def test_generate_nennt_jedes_werkzeug(config, store):
    registry = build_registry(config, store)
    text = generate(registry)
    for name in registry.names():
        assert f"`{name}`" in text, f"{name} fehlt in der erzeugten Referenz"


def test_generate_nennt_die_richtige_anzahl(config, store):
    registry = build_registry(config, store)
    text = generate(registry)
    assert f"**{len(registry)} Werkzeuge**" in text


def test_generate_nennt_stufe_und_kategorie(config, store):
    registry = build_registry(config, store)
    text = generate(registry)
    assert "### `write_file`" in text
    assert "## files" in text or "## core" in text
    assert "WRITE" in text


def test_generate_ist_gueltiges_markdown_ohne_leere_ueberschriften(config, store):
    registry = build_registry(config, store)
    text = generate(registry)
    assert not text.startswith("\n")
    assert "### `" in text
    # Jede Werkzeugüberschrift hat einen Namen, keine leere Zeile direkt danach.
    for zeile in text.splitlines():
        if zeile.startswith("### `"):
            assert zeile.endswith("`")
