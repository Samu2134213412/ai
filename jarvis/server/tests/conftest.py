from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.config import Config, ShellConfig  # noqa: E402
from jarvis.memory import MemoryStore  # noqa: E402
from jarvis.tools import build_registry  # noqa: E402


# ══════════════════════════════════════════════════ Werkzeug-Abdeckung
# Bei 398 Werkzeugen ist ein einzelner "ruf alle mit Beispielargumenten
# auf"-Test keine echte Prüfung mehr (siehe test_tool_registry.py-Docstring
# -- fast keines trägt echte Beispielargumente). Stattdessen zeichnet dieser
# Patch jeden tatsächlichen Aufruf über ``Registry.call`` mit auf, egal aus
# welchem Testmodul er kommt, und am Ende der ganzen Sitzung steht ein
# ehrlicher Bericht: welche Werkzeuge in DIESEM Lauf nie liefen. Bewusst kein
# Fehlschlag -- manche Werkzeuge sind absichtlich nur über einen laufenden
# Dienst (Docker/nginx/Minecraft) oder destruktiv prüfbar und werden in ihrer
# eigenen Testdatei bedingt übersprungen (siehe dort), nicht hier erzwungen.
_AUFGERUFENE_WERKZEUGE: set[str] = set()


def _mit_abdeckung(original):
    def aufruf(self, name, arguments):
        try:
            self._AUFGERUFENE_WERKZEUGE_merken(name)
        except Exception:  # noqa: BLE001 - die Aufzeichnung darf nie einen Test kippen
            pass
        return original(self, name, arguments)
    return aufruf


def _merken(self, name: str) -> None:
    _AUFGERUFENE_WERKZEUGE.add(self.resolve(name))


def _patch_registry_abdeckung() -> None:
    from jarvis.tools.base import Registry
    if getattr(Registry.call, "_abdeckung_gepatcht", False):
        return
    Registry._AUFGERUFENE_WERKZEUGE_merken = _merken
    gepatcht = _mit_abdeckung(Registry.call)
    gepatcht._abdeckung_gepatcht = True
    Registry.call = gepatcht


_patch_registry_abdeckung()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # noqa: ARG001
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as heim:
            alle = set(build_registry(
                Config(home=heim, roots=[]), MemoryStore(":memory:")).names())
    except Exception:  # noqa: BLE001 - der Bericht ist nie wichtiger als die Testergebnisse
        return
    fehlend = sorted(alle - _AUFGERUFENE_WERKZEUGE)
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    schreiben = reporter.write_line if reporter else print
    if not fehlend:
        schreiben(f"[Werkzeug-Abdeckung] Alle {len(alle)} Werkzeuge liefen "
                  "mindestens einmal über Registry.call().")
        return
    schreiben(f"[Werkzeug-Abdeckung] {len(alle) - len(fehlend)}/{len(alle)} Werkzeuge "
              f"liefen in dieser Sitzung. Nie aufgerufen ({len(fehlend)}): "
              + ", ".join(fehlend))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "arbeitsbereich"
    root.mkdir()
    return root


@pytest.fixture
def config(tmp_path: Path, workspace: Path) -> Config:
    return Config(home=str(tmp_path / "home"), roots=[str(workspace)],
                  shell=ShellConfig(enabled=False))


@pytest.fixture
def store() -> MemoryStore:
    memory = MemoryStore(":memory:")
    yield memory
    memory.close()


@pytest.fixture
def registry(config: Config, store: MemoryStore):
    return build_registry(config, store)


class FakeOllama:
    """Ein Modell, dessen Antworten der Test vorgibt.

    Damit lässt sich prüfen, was passiert, wenn das Modell lügt — der Fall, an
    dem der Vorgänger dieses Projekts gescheitert ist.
    """

    def __init__(self, turns):
        from jarvis.ollama import ChatTurn
        self.turns = [t if isinstance(t, ChatTurn) else ChatTurn(text=t) for t in turns]
        self.calls: list[list[dict]] = []
        #: Welche Werkzeugschemata je Anfrage mitgeschickt wurden. Seit die
        #: Auswahl eingegrenzt wird (Discovery, Code-Modus), ist das prüfbar
        #: und damit ein eigener Testgegenstand.
        self.tool_schemas: list[list[dict]] = []

    async def chat(self, messages, tools=None):
        from jarvis.ollama import ChatTurn
        self.calls.append(list(messages))
        self.tool_schemas.append(list(tools or []))
        if not self.turns:
            return ChatTurn(text="(nichts mehr)")
        return self.turns.pop(0)

    async def health(self):
        from jarvis.ollama import Health
        return Health(online=True, version="test", models=[], model_present=True)


@pytest.fixture
def fake_ollama():
    return FakeOllama
