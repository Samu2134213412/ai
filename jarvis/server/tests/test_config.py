"""Konfiguration laden und speichern — auch, wenn sie von Windows kommt.

Die Einrichtungsskripte für Windows schreiben ``jarvis.json`` mit PowerShell.
Windows-PowerShell 5.1 setzt bei ``Set-Content -Encoding UTF8`` eine BOM an den
Dateianfang. Der strenge ``utf-8``-Decoder stolpert darüber, und der Server
startete dann nicht mehr — an einer Datei, die seine eigenen Skripte erzeugt
hatten. Diese Tests halten den Fall fest.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.config import Config


def schreibe(path: Path, daten: dict, *, bom: bool) -> Path:
    roh = json.dumps(daten, indent=2, ensure_ascii=False).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + roh)
    return path


@pytest.mark.parametrize("bom", [False, True], ids=["ohne_bom", "mit_bom"])
def test_konfiguration_laedt_mit_und_ohne_bom(tmp_path, bom):
    ziel = schreibe(tmp_path / "jarvis.json",
                    {"model": "qwen3:14b", "port": 8899}, bom=bom)

    config = Config.load(ziel)

    assert config.model == "qwen3:14b"
    assert config.port == 8899


def test_bom_bleibt_auch_bei_verschachtelten_bloecken_lesbar(tmp_path):
    """Die Skripte schreiben den ganzen codepilot-Block mit -- der muss
    genauso ankommen wie die flachen Felder."""
    ziel = schreibe(tmp_path / "jarvis.json", {
        "model": "qwen3:14b",
        "codepilot": {"url": "http://127.0.0.1:8765", "token": "abc",
                      "project_id": "xyz", "timeout": 900},
        "shell": {"enabled": True, "allowlist": ["python"], "cwd": "", "timeout": 60},
    }, bom=True)

    config = Config.load(ziel)

    assert config.codepilot.token == "abc"
    assert config.codepilot.project_id == "xyz"
    assert config.shell.enabled is True
    assert config.shell.allowlist == ["python"]


def test_kaputtes_json_sagt_welche_datei_gemeint_ist(tmp_path):
    ziel = tmp_path / "jarvis.json"
    ziel.write_text("{ das ist kein json", encoding="utf-8")

    with pytest.raises(SystemExit) as fehler:
        Config.load(ziel)

    assert str(ziel) in str(fehler.value)


def test_fehlende_datei_ergibt_die_vorgaben(tmp_path):
    config = Config.load(tmp_path / "gibtsnicht.json")

    assert config.model == "qwen3:14b"
    assert config.port == 8770


def test_gespeicherte_konfiguration_liest_sich_selbst_wieder(tmp_path):
    original = Config(home=str(tmp_path), model="qwen3:14b", port=8123)
    original.codepilot.token = "geheim"
    pfad = original.save()

    zurueck = Config.load(pfad)

    assert zurueck.model == "qwen3:14b"
    assert zurueck.port == 8123
    assert zurueck.codepilot.token == "geheim"
