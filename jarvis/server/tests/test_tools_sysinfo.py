"""Das System-Pack: echte Messungen auf der Maschine, auf der der Test läuft.

Hier lässt sich nicht jeder Wert gegen eine Konstante prüfen -- die
CPU-Auslastung ist nun einmal jedes Mal anders. Geprüft wird deshalb, was
**immer** gelten muss: dass gemessen statt geraten wird, dass Grenzen
eingehalten sind, dass ein nicht verfügbarer Sensor ehrlich gemeldet wird,
und dass verändernde Werkzeuge die richtige Sicherheitsstufe tragen.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from jarvis.permissions import PermissionLevel
from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult
from jarvis.tools.catalog import Availability, availability

psutil = pytest.importorskip("psutil")


@pytest.fixture
def registry(config, store):
    return build_registry(config, store)


@pytest.fixture
def tools(registry):
    # Positional-only (das '/'), damit ein Tool-Argument namens
    # 'name' nicht mit dem Parameter des Helfers kollidiert.
    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


# ══════════════════════════════════════════════════════════════════ CPU
def test_cpu_auslastung_ist_ein_plausibler_messwert(tools):
    result = erfolg(tools("system.cpu.usage", interval=0.1))
    wert = result.evidence["auslastung_prozent"]
    assert 0.0 <= wert <= 100.0


def test_cpu_je_kern_liefert_so_viele_werte_wie_es_kerne_gibt(tools):
    result = erfolg(tools("system.cpu.usage", interval=0.1, per_core=True))
    assert result.evidence["kerne"] == psutil.cpu_count(logical=True)
    assert 0.0 <= result.evidence["spitze"] <= 100.0


def test_cpu_kerne_und_modell(tools):
    kerne = erfolg(tools("system.cpu.cores"))
    assert kerne.evidence["logisch"] >= kerne.evidence["physisch"] >= 0

    modell = erfolg(tools("system.cpu.model"))
    assert modell.evidence["architektur"]


def test_load_average_gibt_es_nur_auf_unix(tools):
    result = tools("system.cpu.load")
    if hasattr(os, "getloadavg"):
        erfolg(result)
        assert result.evidence["kerne"] >= 1
        assert isinstance(result.evidence["ausgelastet"], bool)
    else:  # pragma: no cover - nur unter Windows
        assert result.ok is False and "Unix" in result.summary


# ═══════════════════════════════════════════════════════════════ Speicher
def test_ram_werte_passen_zueinander(tools):
    result = erfolg(tools("system.ram.usage"))
    e = result.evidence
    assert e["gesamt_gb"] > 0
    assert e["belegt_gb"] <= e["gesamt_gb"]
    assert 0 <= e["auslastung_prozent"] <= 100


def test_swap_ohne_auslagerung_ist_kein_fehler(tools):
    result = erfolg(tools("system.swap.usage"))
    assert result.evidence["gesamt_gb"] >= 0


def test_ram_top_nennt_echte_prozesse(tools):
    result = erfolg(tools("system.ram.top", limit=5))
    assert result.evidence["prozesse"] > 0
    # Der eigene Testprozess muss in der Gesamtzahl enthalten sein.
    assert str(os.getpid()) in result.payload or result.evidence["prozesse"] > 1


# ════════════════════════════════════════════════════════════ Datenträger
def test_datentraeger_belegung(tools, workspace):
    result = erfolg(tools("system.disk.usage", path=str(workspace)))
    e = result.evidence
    assert e["gesamt_gb"] > 0
    assert round(e["belegt_gb"] + e["frei_gb"]) <= round(e["gesamt_gb"]) + 1

    assert tools("system.disk.usage", path="/gibt/es/nicht/wirklich").ok is False


def test_partitionen_und_io(tools):
    assert erfolg(tools("system.disk.partitions")).evidence["anzahl"] >= 1
    io = tools("system.disk.io")
    if io.ok:
        assert io.evidence["gelesen_bytes"] >= 0


def test_smart_ohne_smartctl_sagt_das_ehrlich(tools):
    result = tools("system.disk.smart", device="/dev/sda")
    assert result.ok is False
    # Entweder fehlt smartctl, oder es fehlt die Berechtigung -- beides wird
    # benannt, statt eine Gesundheitsaussage zu erfinden.
    assert "smartctl" in result.summary or "schlug fehl" in result.summary


# ════════════════════════════════════════════════════════ GPU und Sensoren
def test_gpu_ohne_herstellerwerkzeug_wird_nicht_geraten(tools):
    """Der Kernpunkt dieses Packs: keine erfundene Temperatur."""
    result = tools("system.gpu.info")
    if not result.ok:
        assert "nicht auslesen" in result.summary
        assert "geschätzt" in result.summary

    temp = tools("system.gpu.temperature")
    if not temp.ok:
        assert "nicht auslesen" in temp.summary or "keine Temperatur" in temp.summary


def test_temperatursensoren_melden_fehlen_statt_null(tools):
    result = tools("system.sensors.temperatures")
    if result.ok:
        assert result.evidence["sensoren"] > 0
    else:
        assert "keine Temperatursensoren" in result.summary or \
               "meldet psutil" in result.summary


def test_akku_auf_einem_standrechner_ist_kein_fehler(tools):
    result = erfolg(tools("system.battery"))
    assert isinstance(result.evidence["akku"], bool)


# ═══════════════════════════════════════════════════════════════ Prozesse
def test_prozessliste_und_sortierung(tools):
    result = erfolg(tools("system.process.list", limit=5, sort="memory"))
    assert result.evidence["gelistet"] <= 5
    assert result.evidence["gesamt"] >= result.evidence["gelistet"]

    assert tools("system.process.list", sort="zufall").ok is False


def test_prozess_finden_und_info_ueber_den_eigenen_prozess(tools):
    eigener = os.path.basename(sys.executable)
    gefunden = erfolg(tools("system.process.find", name=eigener))
    assert gefunden.evidence["laeuft"] is True

    info = erfolg(tools("system.process.info", pid=os.getpid()))
    assert info.evidence["pid"] == os.getpid()
    assert info.evidence["status"]
    assert info.evidence["threads"] >= 1


def test_unbekannte_pid_ist_ein_ehrlicher_fehler(tools):
    fehl = tools("system.process.info", pid=999_999_998)
    assert fehl.ok is False and "999999998" in fehl.summary
    assert tools("system.process.info", pid="keine zahl").ok is False


def test_kindprozesse_und_baum(tools):
    assert erfolg(tools("system.process.children",
                        pid=os.getpid())).evidence["anzahl"] >= 0
    baum = erfolg(tools("system.process.tree", limit=20))
    assert baum.evidence["prozesse"] > 0


def test_offene_dateien_des_eigenen_prozesses(tools, workspace):
    with open(workspace / "offen.txt", "w", encoding="utf-8") as fh:
        fh.write("x")
        fh.flush()
        result = tools("system.process.open_files", pid=os.getpid())
    if result.ok:
        assert result.evidence["anzahl"] >= 0
    else:
        assert "Berechtigung" in result.summary


def test_prozess_anhalten_und_fortsetzen_an_einem_echten_kindprozess(tools):
    import subprocess
    kind = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        angehalten = erfolg(tools("system.process.suspend", pid=kind.pid))
        assert psutil.Process(kind.pid).status() == psutil.STATUS_STOPPED
        # Der gemeldete Zustand muss der echte sein. SIGSTOP wirkt verzoegert;
        # wer sofort nachliest, sieht in etwa jedem fuenften Lauf noch
        # "running" und wuerde das als Beleg fuer "angehalten" ausgeben.
        assert angehalten.evidence["status"] == psutil.STATUS_STOPPED

        fortgesetzt = erfolg(tools("system.process.resume", pid=kind.pid))
        assert psutil.Process(kind.pid).status() != psutil.STATUS_STOPPED
        assert fortgesetzt.evidence["status"] != psutil.STATUS_STOPPED

        # Beenden prüft selbst nach, ob der Prozess wirklich weg ist.
        beendet = erfolg(tools("system.process.kill", pid=kind.pid))
        assert beendet.evidence["pid"] == kind.pid
        assert not psutil.pid_exists(kind.pid) or \
            psutil.Process(kind.pid).status() == psutil.STATUS_ZOMBIE
    finally:
        if kind.poll() is None:
            kind.kill()
        kind.wait(timeout=5)


# ════════════════════════════════════════════════════════════════ Dienste
def test_dienstliste_laeuft_oder_sagt_warum_nicht(tools):
    result = tools("system.service.list", limit=5)
    if result.ok:
        assert result.evidence["anzahl"] >= 0
    else:
        assert "systemd" in result.summary or "Dienste" in result.summary


def test_dienstname_muss_angegeben_werden(tools):
    assert tools("system.service.status", name="").ok is False


# ═══════════════════════════════════════════════════════════════ Umgebung
def test_systeminfo_und_uptime(tools):
    info = erfolg(tools("system.info"))
    assert info.evidence["rechner"] and info.evidence["kerne"] >= 1

    uptime = erfolg(tools("system.uptime"))
    assert uptime.evidence["sekunden"] > 0
    assert erfolg(tools("system.boot_time")).evidence["unix"] > 0


def test_umgebungsvariablen_verbergen_geheimnisse(tools, monkeypatch):
    """Eine Umgebungsvariable im Klartext auszugeben ist die einfachste Art,
    ein Token in einen Chatverlauf zu bekommen."""
    monkeypatch.setenv("JARVIS_TEST_API_TOKEN", "streng-geheim-123")
    monkeypatch.setenv("JARVIS_TEST_HARMLOS", "sichtbar")

    liste = erfolg(tools("system.env.list", filter="JARVIS_TEST"))
    assert "streng-geheim-123" not in liste.payload
    assert "«verborgen»" in liste.payload
    assert "sichtbar" in liste.payload

    einzeln = erfolg(tools("system.env.get", name="JARVIS_TEST_API_TOKEN"))
    assert einzeln.evidence["verborgen"] is True
    assert "streng-geheim-123" not in einzeln.summary
    assert einzeln.payload is None

    offen = erfolg(tools("system.env.get", name="JARVIS_TEST_HARMLOS"))
    assert offen.payload == "sichtbar"

    assert erfolg(tools("system.env.get",
                        name="GIBT_ES_NICHT_XYZ")).evidence["gesetzt"] is False


def test_env_set_sagt_dass_es_nicht_dauerhaft_ist(tools):
    result = erfolg(tools("system.env.set", name="JARVIS_TEST_GESETZT", value="ja"))
    assert "nicht dauerhaft" in result.summary
    assert os.environ["JARVIS_TEST_GESETZT"] == "ja"
    del os.environ["JARVIS_TEST_GESETZT"]


def test_benutzer_und_python(tools):
    benutzer = erfolg(tools("system.user.info"))
    assert benutzer.evidence["heim"]
    assert isinstance(benutzer.evidence["admin"], bool)

    py = erfolg(tools("system.python.info"))
    assert py.evidence["version"].startswith("3.")


# ══════════════════════════════════════════ Plattform- und Stufenehrlichkeit
def test_windows_werkzeuge_melden_sich_auf_linux_als_unpassend(registry):
    powershell = registry.get("system.windows.powershell")
    zustand, grund = availability(powershell)
    if sys.platform != "win32":
        assert zustand in (Availability.UNSUPPORTED_PLATFORM,
                           Availability.MISSING_DEPENDENCY)
        assert "windows" in grund.lower() or "PowerShell" in grund


def test_windows_werkzeug_verweigert_sich_auch_beim_direkten_aufruf(tools):
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("Auf Windows läuft es ja.")
    fehl = tools("system.windows.powershell", command="Get-Date")
    assert fehl.ok is False and "Windows" in fehl.summary


def test_veraendernde_werkzeuge_tragen_die_richtige_stufe(registry):
    """Die Stufe ist das, woran das Permission-System hängt. Ein Werkzeug,
    das Prozesse beendet, auf READ wäre ein stiller Dammbruch."""
    erwartet = {
        "system.process.kill": PermissionLevel.CRITICAL,
        "system.windows.powershell": PermissionLevel.CRITICAL,
        "system.process.suspend": PermissionLevel.SYSTEM,
        "system.process.priority": PermissionLevel.SYSTEM,
        "system.env.set": PermissionLevel.SYSTEM,
        "system.service.restart": PermissionLevel.SYSTEM,
        "system.cpu.usage": PermissionLevel.READ,
        "system.ram.usage": PermissionLevel.READ,
    }
    for name, stufe in erwartet.items():
        assert registry.get(name).level is stufe, f"{name} hat die falsche Stufe"


def test_alte_namen_zeigen_auf_die_neuen_operatoren(registry):
    """Router, Systemprompt und über hundert Tests benutzen die alten Namen.
    Es gibt aber nur noch eine Implementierung je Aufgabe."""
    for alt, neu in (("get_cpu_info", "system.cpu.usage"),
                     ("get_ram_info", "system.ram.usage"),
                     ("get_disk_info", "system.disk.usage"),
                     ("get_system_info", "system.info"),
                     ("list_processes", "system.process.list")):
        assert registry.resolve(alt) == neu
        assert registry.get(alt) is registry.get(neu)
