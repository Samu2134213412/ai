"""Der Selbststart von CodePilot.

CodePilot lädt ein 18-GB-Modell, darf also nicht dauerhaft mitlaufen. Jarvis
startet es erst, wenn eine Codeaufgabe kommt. Diese Tests halten fest, dass
das klappt — und dass jeder Fehlschlag mit Begründung endet statt stumm.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jarvis.tools.base import ToolError
from jarvis.tools.codepilot import CodePilotLink, default_start_dir

REPO = Path(__file__).resolve().parents[4]


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ═══════════════════════════════════════════════════ ohne echten Serverstart
def test_laufender_server_wird_nicht_neu_gestartet(monkeypatch):
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p")
    monkeypatch.setattr(link, "is_healthy", lambda *a, **k: True)
    monkeypatch.setattr(link, "_spawn", lambda *a: pytest.fail("darf nicht starten"))

    assert link.ensure_running() == "lief bereits"


def test_abgeschalteter_selbststart_sagt_wie_es_von_hand_geht(monkeypatch):
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p",
                         autostart=False)
    monkeypatch.setattr(link, "is_healthy", lambda *a, **k: False)

    with pytest.raises(ToolError) as fehler:
        link.ensure_running()

    assert "abgeschaltet" in str(fehler.value)
    assert "start.bat" in str(fehler.value)


def test_fehlendes_codepilot_nennt_den_gesuchten_pfad(monkeypatch, tmp_path):
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p",
                         start_dir=str(tmp_path))
    monkeypatch.setattr(link, "is_healthy", lambda *a, **k: False)

    with pytest.raises(ToolError) as fehler:
        link.ensure_running()

    assert str(tmp_path) in str(fehler.value)
    assert "start_dir" in str(fehler.value)


def test_sofort_beendeter_prozess_zeigt_seine_ausgabe(monkeypatch, tmp_path):
    """Startet der Prozess und stirbt gleich, muss die Ursache sichtbar sein."""
    (tmp_path / "codepilot").mkdir()
    log = tmp_path / "start.log"
    log.write_text("ModuleNotFoundError: No module named 'codepilot'\n", encoding="utf-8")

    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p",
                         start_dir=str(tmp_path), start_timeout=5)
    monkeypatch.setattr(link, "is_healthy", lambda *a, **k: False)
    tot = subprocess.Popen([sys.executable, "-c", "raise SystemExit(1)"])
    tot.wait()
    monkeypatch.setattr(link, "_spawn", lambda workdir: (tot, log))

    with pytest.raises(ToolError) as fehler:
        link.ensure_running()

    assert "sofort beendet" in str(fehler.value)
    assert "ModuleNotFoundError" in str(fehler.value)


def test_zeitueberschreitung_nennt_die_wartezeit(monkeypatch, tmp_path):
    (tmp_path / "codepilot").mkdir()
    log = tmp_path / "start.log"
    log.write_text("laeuft, antwortet aber nicht\n", encoding="utf-8")

    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p",
                         start_dir=str(tmp_path), start_timeout=2)
    monkeypatch.setattr(link, "is_healthy", lambda *a, **k: False)
    lebt = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    monkeypatch.setattr(link, "_spawn", lambda workdir: (lebt, log))
    try:
        with pytest.raises(ToolError) as fehler:
            link.ensure_running()
        assert "2 s nach dem Start" in str(fehler.value)
        assert "antwortet aber nicht" in str(fehler.value)
    finally:
        lebt.kill()
        lebt.wait()


def test_repo_layout_wird_gefunden():
    """Der Standardpfad zeigt auf CodePilot neben jarvis/ im selben Repo."""
    assert (default_start_dir() / "codepilot").is_dir()


def test_windows_flags_verzichten_auf_detached_process(monkeypatch):
    """Das Flackern kam von DETACHED_PROCESS -- CREATE_NO_WINDOW ist das,
    was Windows fuer 'kein Fenster, auch nicht kurz' vorsieht.

    Prueft die reine Flag-Berechnung, ohne os.name global umzubiegen -- das
    wuerde pytests eigene Pfadverwaltung (WindowsPath auf Linux) brechen.
    """
    from jarvis.tools import codepilot as mod
    monkeypatch.setattr(mod.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(mod.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(mod.subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)

    flags = mod.windows_creationflags()

    assert flags & 0x08000000                       # CREATE_NO_WINDOW gesetzt
    assert flags & 0x200                             # CREATE_NEW_PROCESS_GROUP gesetzt
    assert not (flags & 0x00000008)                  # DETACHED_PROCESS nicht mehr


def test_spawn_reicht_die_windows_flags_nur_unter_windows_durch(monkeypatch, tmp_path):
    """Unter Linux -- also in dieser Testumgebung -- greift start_new_session,
    nicht die Windows-Flags. Die Verzweigung selbst wird hier geprueft."""
    (tmp_path / "codepilot").mkdir()
    gesehen = {}

    def fake_popen(argv, **kwargs):
        gesehen.update(kwargs)
        class Attrappe:
            def poll(self): return None
        return Attrappe()

    monkeypatch.setattr("jarvis.tools.codepilot.subprocess.Popen", fake_popen)
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p",
                         log_path=str(tmp_path / "log.txt"))
    link._spawn(tmp_path)

    if __import__("os").name == "nt":
        assert "creationflags" in gesehen
    else:
        assert gesehen.get("start_new_session") is True


# ═══════════════════════════════════ mit einem echt gestarteten Prozess
def test_wartet_bis_der_gestartete_prozess_antwortet(tmp_path, monkeypatch):
    """Die Warteschleife gegen einen wirklich laufenden HTTP-Server.

    Hier startet absichtlich nicht CodePilot selbst, sondern ein simpler
    Server auf demselben Port: geprüft wird die Schleife -- anstoßen, warten,
    erkennen, dass etwas antwortet -- ohne einen losgelösten CodePilot
    zurückzulassen, den die Suite nicht mehr einfangen kann.
    """
    port = freier_port()
    (tmp_path / "codepilot").mkdir()
    log = tmp_path / "start.log"
    log.write_text("", encoding="utf-8")
    # is_healthy verlangt /api/health mit Status < 400 -- sonst wäre jeder
    # beliebige Server auf dem Port „CodePilot". Also eine Datei anlegen,
    # die http.server unter genau diesem Pfad ausliefert.
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "health").write_text('{"service": "test"}', encoding="utf-8")

    link = CodePilotLink(url=f"http://127.0.0.1:{port}", token="t", project_id="p",
                         start_dir=str(tmp_path), start_timeout=15)
    assert link.is_healthy(0.5) is False

    gestartet: list[subprocess.Popen] = []

    def spawn(_workdir):
        # Erst hier starten -- sonst liefe der Server schon vor dem Aufruf und
        # ensure_running würde "lief bereits" melden statt zu warten.
        proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=str(tmp_path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        gestartet.append(proc)
        return proc, log

    monkeypatch.setattr(link, "_spawn", spawn)
    try:
        hinweis = link.ensure_running()
        assert "gestartet" in hinweis
        assert link.is_healthy(2.0) is True
        assert len(gestartet) == 1
    finally:
        for proc in gestartet:
            proc.kill()
            proc.wait()


def test_zweiter_aufruf_startet_nicht_noch_einmal(monkeypatch):
    """Zwei Codeaufgaben kurz hintereinander dürfen nicht zwei Server starten."""
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p")
    zustand = {"laeuft": False, "starts": 0}

    def gesund(*_a, **_k):
        return zustand["laeuft"]

    def spawn(_workdir):
        zustand["starts"] += 1
        zustand["laeuft"] = True
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"]), Path("/dev/null")

    monkeypatch.setattr(link, "is_healthy", gesund)
    monkeypatch.setattr(link, "_spawn", spawn)
    monkeypatch.setattr(link, "resolved_start_dir", lambda: Path("/"))
    monkeypatch.setattr(Path, "is_dir", lambda self: True)

    assert "gestartet" in link.ensure_running()
    assert link.ensure_running() == "lief bereits"
    assert zustand["starts"] == 1


# ═══════════════════════════════════════════ warum ein Auftrag scheiterte
class FakeAntwort:
    def __init__(self, status=200, daten=None):
        self.status_code = status
        self._daten = daten if daten is not None else {}

    def json(self):
        return self._daten


def test_vorabpruefung_nennt_was_fehlt(monkeypatch):
    """Ein fehlendes Modell soll sofort gesagt werden, nicht nach 96 s."""
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p")

    class Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, _pfad):
            return FakeAntwort(200, {
                "claude": {"available": True},
                "ollama": {"available": False,
                           "detail": "no server reachable at http://127.0.0.1:11434"},
                "model": {"available": False, "detail": "qwen3-coder:30b is not pulled"},
            })

    monkeypatch.setattr(link, "_client", Client)
    with pytest.raises(ToolError) as fehler:
        link.check_chain()

    text = str(fehler.value)
    assert "Ollama" in text and "no server reachable" in text
    assert "qwen3-coder:30b is not pulled" in text
    assert "--doctor" in text


def test_vorabpruefung_schweigt_wenn_alles_bereit_ist(monkeypatch):
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p")

    class Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, _pfad):
            return FakeAntwort(200, {"claude": {"available": True},
                                     "ollama": {"available": True},
                                     "model": {"available": True}})

    monkeypatch.setattr(link, "_client", Client)
    link.check_chain()  # darf nicht werfen


def test_vorabpruefung_blockiert_nicht_bei_fehlendem_statusbericht(monkeypatch):
    """Ohne Statusbericht wird nicht geraten -- der Auftrag läuft einfach."""
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p")

    class Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, _pfad):
            return FakeAntwort(404, {})

    monkeypatch.setattr(link, "_client", Client)
    link.check_chain()  # darf nicht werfen


# ═══════════════════════════════════════════════════ Statusmelder
def test_status_ohne_konfiguration(monkeypatch):
    link = CodePilotLink(url="http://127.0.0.1:1", token="", project_id="")
    assert link.status_snapshot() == {"configured": False, "running": False, "problems": []}


def test_status_konfiguriert_aber_nicht_erreichbar(monkeypatch):
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p")
    monkeypatch.setattr(link, "is_healthy", lambda *a, **k: False)
    assert link.status_snapshot() == {"configured": True, "running": False, "problems": []}


def test_status_laeuft_und_kette_ist_bereit(monkeypatch):
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p")
    monkeypatch.setattr(link, "is_healthy", lambda *a, **k: True)

    class Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, _pfad):
            return FakeAntwort(200, {"claude": {"available": True},
                                     "ollama": {"available": True},
                                     "model": {"available": True}})
    monkeypatch.setattr(link, "_client", Client)

    assert link.status_snapshot() == {"configured": True, "running": True, "problems": []}


def test_status_laeuft_aber_kette_hat_luecken(monkeypatch):
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p")
    monkeypatch.setattr(link, "is_healthy", lambda *a, **k: True)

    class Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, _pfad):
            return FakeAntwort(200, {"claude": {"available": True},
                                     "ollama": {"available": False, "detail": "offline"},
                                     "model": {"available": True}})
    monkeypatch.setattr(link, "_client", Client)

    status = link.status_snapshot()
    assert status["running"] is True
    assert any("Ollama" in p and "offline" in p for p in status["problems"])


def test_status_wirft_nie(monkeypatch):
    """Der Melder laeuft periodisch im Hintergrund -- er darf niemals reissen,
    auch nicht bei einer voellig unerwarteten Ausnahme."""
    link = CodePilotLink(url="http://127.0.0.1:1", token="t", project_id="p")

    def kaputt(*a, **k):
        raise RuntimeError("etwas ganz Unerwartetes")
    monkeypatch.setattr(link, "is_healthy", kaputt)

    status = link.status_snapshot()

    assert status["configured"] is True
    assert status["running"] is False
    assert "Unerwartetes" in status["problems"][0]
