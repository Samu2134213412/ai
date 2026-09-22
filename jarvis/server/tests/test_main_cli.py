"""Die Kommandozeile (``python -m jarvis``) -- bislang ungetestet. Hier nur
``--generate-docs``, direkt für Punkt 49; die übrigen Flags starten einen
echten Server und brauchen ein eigenes Vorgehen (nicht Teil dieser Aufgabe)."""

from __future__ import annotations

from pathlib import Path

from jarvis.__main__ import main


def test_generate_docs_legt_keine_konfiguration_an(tmp_path: Path):
    """--generate-docs braucht keinen laufenden Server und keine gespeicherte
    Konfiguration -- anders als --init soll dabei nichts angelegt werden."""
    config_pfad = tmp_path / "cfg.json"
    code = main(["--config", str(config_pfad), "--generate-docs",
                str(tmp_path / "referenz.md")])
    assert code == 0
    assert not config_pfad.exists()


def test_generate_docs_mit_eigenem_pfad(tmp_path: Path):
    ziel = tmp_path / "unterordner" / "referenz.md"
    code = main(["--config", str(tmp_path / "cfg.json"), "--generate-docs", str(ziel)])
    assert code == 0
    assert ziel.is_file()
    text = ziel.read_text(encoding="utf-8")
    assert "write_file" in text
    assert "Werkzeuge" in text
