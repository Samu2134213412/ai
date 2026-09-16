from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.config import Config, ShellConfig  # noqa: E402
from jarvis.memory import MemoryStore  # noqa: E402
from jarvis.tools import build_registry  # noqa: E402


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

    async def chat(self, messages, tools=None):
        from jarvis.ollama import ChatTurn
        self.calls.append(list(messages))
        if not self.turns:
            return ChatTurn(text="(nichts mehr)")
        return self.turns.pop(0)

    async def health(self):
        from jarvis.ollama import Health
        return Health(online=True, version="test", models=[], model_present=True)


@pytest.fixture
def fake_ollama():
    return FakeOllama
