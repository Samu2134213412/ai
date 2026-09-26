"""guardian.* -- der Virenschutz Guardian aus Jarvis heraus.

Zwei Arten von Tests:

* gegen die echte, gebaute ``guardian``-Datei (übersprungen, wenn Guardian
  nicht gebaut ist -- dieselbe Zurückhaltung wie bei Docker/ffmpeg) mit der
  EICAR-Testzeichenkette, einem harmlosen, genau dafür veröffentlichten
  Virenschutz-Prüfstring;
* gegen kleine Ersatz-Programme, die gezielt eine Fehlantwort liefern -- nur
  so lässt sich prüfen, dass Jarvis einer Erfolgsmeldung nicht blind glaubt.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from jarvis.config import GuardianConfig
from jarvis.permissions import PermissionLevel
from jarvis.tools import build_registry, tool_status
from jarvis.tools.base import ToolResult
from jarvis.tools.catalog import PROBES, probe
from jarvis.tools.packs.guardian import _EXE, _finde_guardian

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
EICAR_SHA256 = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"
GUARDIAN = Path(__file__).resolve().parents[3] / "guardian"
REPO_RULES = GUARDIAN / "rules"

_gebaut = bool(_finde_guardian(""))
braucht_guardian = pytest.mark.skipif(not _gebaut, reason="Guardian nicht gebaut "
                                      "(im Ordner guardian/: cargo build)")
nur_unix = pytest.mark.skipif(sys.platform == "win32",
                              reason="Ersatz-Programm als Shell-Skript")


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


def fehler(result: ToolResult) -> ToolResult:
    assert not result.ok, f"{result.tool} hätte fehlschlagen müssen: {result.summary}"
    return result


@pytest.fixture
def guardian_home(tmp_path, workspace):
    """Eine eigene Guardian-Konfiguration: Quarantäne/Protokoll im tmp_path,
    die mitgelieferten YARA-Regeln, EICAR als bekannter Hash."""
    (workspace / "downloads").mkdir()
    daten = tmp_path / "guardian-daten"
    (daten / "sig").mkdir(parents=True)
    (daten / "sig" / "malicious_hashes.txt").write_text(
        f"{EICAR_SHA256}  EICAR test signature\n", encoding="utf-8")
    toml = (f"rules_dir = {json.dumps(str(REPO_RULES))}\n"
            f"quarantine_dir = {json.dumps(str(daten / 'q'))}\n"
            f"log_path = {json.dumps(str(daten / 'events.jsonl'))}\n"
            f"hash_db_path = {json.dumps(str(daten / 'sig' / 'malicious_hashes.txt'))}\n"
            f"scan_roots = [{json.dumps(str(workspace / 'downloads'))}]\n"
            'extensions = ["exe","com","js","jar"]\n'
            "compute_legacy_hashes = false\n")
    pfad = daten / "config.toml"
    pfad.write_text(toml, encoding="utf-8")
    return pfad


@pytest.fixture
def tools(config, store, guardian_home):
    config.guardian = GuardianConfig(config=str(guardian_home))
    registry = build_registry(config, store)

    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)

    call.registry = registry
    call.config = config
    return call


def _ersatz(tmp_path: Path, stdout: str, stderr: str = "", code: int = 0) -> str:
    """Ein Programm, das sich als guardian ausgibt und fest vorgegeben
    antwortet -- ohne cargo und ohne echten Scan."""
    skript = tmp_path / "guardian-ersatz"
    skript.write_text("#!/bin/sh\n"
                      f"cat <<'JSON'\n{stdout}\nJSON\n"
                      f"echo {json.dumps(stderr)} >&2\n"
                      f"exit {code}\n", encoding="utf-8")
    skript.chmod(skript.stat().st_mode | stat.S_IEXEC)
    return str(skript)


# ══════════════════════════════════════════════════════ Einordnung
def test_pack_baut_ohne_fehler_und_ordnet_richtig_ein(tools):
    reg = tools.registry
    assert "guardian" not in reg.pack_errors
    assert reg.get("guardian.status").level is PermissionLevel.READ
    assert reg.get("guardian.check").level is PermissionLevel.WRITE
    assert reg.get("guardian.check").dry_run is True
    # Eine als Bedrohung eingestufte Datei zurückholen: immer bestätigen.
    assert reg.get("guardian.quarantine.restore").level is PermissionLevel.CRITICAL


def test_ohne_guardian_meldet_die_statusliste_nachruesten(config, store, tmp_path):
    config.guardian = GuardianConfig(binary=str(tmp_path / "gibt-es-nicht"))
    reg = build_registry(config, store)
    status = {r["name"]: r for r in tool_status(reg, config)}
    assert status["guardian.check"]["status"] == "dep"
    assert "cargo build" in status["guardian.check"]["grund"]
    res = fehler(reg.call("guardian.status", {}))
    assert "nicht gebaut" in res.summary


def test_konfigurierter_pfad_der_fehlt_wird_nicht_still_ersetzt(tmp_path):
    """Hat der Nutzer eine bestimmte Datei eingetragen, darf Jarvis nicht
    heimlich eine andere Guardian-Datei (PATH/Repo) nehmen."""
    assert _finde_guardian(str(tmp_path / "falsch" / "guardian")) == ""


def test_installierter_guardian_wird_auch_ohne_neuen_path_gefunden(tmp_path, monkeypatch):
    """Ein Jarvis, das vor install.bat gestartet wurde, kennt den neuen
    PATH-Eintrag nicht -- den Installationsort findet es trotzdem, und zwar
    vor einem (womöglich älteren) Build im Repo."""
    exe = tmp_path / "Programs" / "Guardian" / _EXE
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PATH", "")
    assert _finde_guardian("") == str(exe)


def test_der_hinweis_nennt_einen_installer_den_es_gibt():
    assert "install.bat" in PROBES["guardian"].install_hint
    for datei in ("install.bat", "uninstall.bat", "install.ps1"):
        assert (GUARDIAN / datei).is_file(), datei


# ══════════════════════════════════════════════════════ echte Guardian-Datei
@braucht_guardian
def test_status_kommt_aus_guardian(tools, guardian_home):
    res = erfolg(tools("guardian.status"))
    assert res.evidence["regeldateien"] == 1
    assert res.evidence["hashes"] == 1
    assert res.evidence["konfiguration"] == str(guardian_home)


@braucht_guardian
def test_probelauf_bewertet_wirklich_verschiebt_aber_nichts(tools, workspace):
    eicar = workspace / "downloads" / "eicar_test.com"
    eicar.write_bytes(EICAR)

    res = erfolg(tools("guardian.check", path="downloads", dry_run=True))
    assert res.evidence["probelauf"] is True
    assert res.evidence["bedrohungen"] == 1
    assert res.evidence["wuerde_verschieben"] == 1
    assert eicar.exists()
    assert erfolg(tools("guardian.events")).evidence["anzahl"] == 0


@braucht_guardian
def test_scan_quarantaene_und_zurueck(tools, workspace):
    eicar = workspace / "downloads" / "eicar_test.com"
    eicar.write_bytes(EICAR)
    harmlos = workspace / "downloads" / "harmlos.js"
    harmlos.write_text("console.log('hallo')", encoding="utf-8")

    res = erfolg(tools("guardian.check", path="downloads"))
    assert res.evidence["geprueft"] == 2
    assert res.evidence["bedrohungen"] == 1
    assert res.evidence["in_quarantaene"] == 1
    assert not eicar.exists()
    assert harmlos.exists(), "eine saubere Datei darf nie verschoben werden"

    liste = erfolg(tools("guardian.quarantine.list"))
    assert liste.evidence["anzahl"] == 1
    kennung = liste.payload.splitlines()[2].split()[0]

    zurueck = erfolg(tools("guardian.quarantine.restore", id=kennung))
    assert Path(zurueck.evidence["pfad"]) == eicar
    assert eicar.read_bytes() == EICAR
    fehler(tools("guardian.quarantine.restore", id=kennung))


@braucht_guardian
def test_sauberer_ordner_meldet_nichts_gefunden(tools, workspace):
    (workspace / "downloads" / "harmlos.js").write_text("1+1", encoding="utf-8")
    res = erfolg(tools("guardian.check", path="downloads"))
    assert res.evidence["bedrohungen"] == 0
    assert "nichts gefunden" in res.summary


@braucht_guardian
def test_voller_scan_nimmt_guardians_scan_ordner(tools, workspace):
    eicar = workspace / "downloads" / "eicar_test.com"
    eicar.write_bytes(EICAR)
    res = erfolg(tools("guardian.check", full=True))
    assert res.evidence["in_quarantaene"] == 1
    assert not eicar.exists()


@braucht_guardian
def test_regeln_und_ereignisse(tools, workspace):
    assert erfolg(tools("guardian.rules.update")).evidence["regeldateien"] == 1
    (workspace / "downloads" / "harmlos.js").write_text("1", encoding="utf-8")
    erfolg(tools("guardian.check", path="downloads"))
    assert erfolg(tools("guardian.events")).evidence["anzahl"] == 1


# ══════════════════════════════════════════════════════ Grenzen
@braucht_guardian
def test_scan_ausserhalb_des_arbeitsbereichs_wird_abgelehnt(tools, tmp_path):
    fremd = tmp_path / "fremd.com"
    fremd.write_bytes(EICAR)
    res = fehler(tools("guardian.check", path=str(fremd)))
    assert "außerhalb" in res.summary
    assert fremd.exists()


def test_scan_ohne_ziel_oder_mit_beidem_wird_abgelehnt(tools):
    fehler(tools("guardian.check"))
    fehler(tools("guardian.check", path="downloads", full=True))


# ══════════════════════════════════════════════════════ Nicht blind glauben
@nur_unix
def test_quarantaene_ohne_echte_verschiebung_ist_kein_erfolg(config, store, workspace,
                                                              tmp_path):
    """Das Ersatz-Programm behauptet "quarantined", die Datei liegt aber noch
    da -- Jarvis muss das bemerken, statt die Meldung weiterzureichen."""
    datei = workspace / "noch_da.com"
    datei.write_bytes(b"x")
    antwort = json.dumps({"scanned": 1, "worst": "quarantine", "report_only": False,
                          "results": [{"path": str(datei), "score": 100,
                                       "verdict": "quarantine", "action": "quarantined",
                                       "quarantine_id": "q-1", "reasons": []}],
                          "failed": [], "warnings": []})
    config.guardian = GuardianConfig(binary=_ersatz(tmp_path, antwort, code=1))
    reg = build_registry(config, store)
    res = fehler(reg.call("guardian.check", {"path": "noch_da.com"}))
    assert "liegt noch an ihrem Platz" in res.summary


@nur_unix
def test_zu_alte_guardian_version_ohne_json_wird_erkannt(config, store, tmp_path):
    config.guardian = GuardianConfig(binary=_ersatz(
        tmp_path, "", stderr="error: unexpected argument '--json' found", code=2))
    reg = build_registry(config, store)
    res = fehler(reg.call("guardian.status", {}))
    assert "neu bauen" in res.summary


@nur_unix
def test_wiederherstellen_ohne_datei_am_ziel_ist_kein_erfolg(config, store, tmp_path):
    antwort = json.dumps({"id": "q-1", "restored": str(tmp_path / "nie-angekommen.com")})
    config.guardian = GuardianConfig(binary=_ersatz(tmp_path, antwort))
    reg = build_registry(config, store)
    res = fehler(reg.call("guardian.quarantine.restore", {"id": "q-1"}))
    assert "keine Datei" in res.summary


def test_gefundener_pfad_steht_im_abhaengigkeitsbericht(tools):
    gefunden, pfad = probe("guardian")
    assert gefunden is _gebaut
    if gefunden:
        assert Path(pfad).is_file()
