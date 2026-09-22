"""Das Docker-Pack: die Kommandozeile bekommt hier echte Aufrufe zu sehen
(``docker`` ist installiert), aber ohne laufenden Daemon bleibt es bei der
ehrlichen "nicht erreichbar"-Meldung -- genau der Fall, den ein Nutzer ohne
gestartetes Docker Desktop / dockerd auch sieht. Läuft irgendwo ein echter
Daemon, laufen die markierten Tests zusätzlich live mit."""

from __future__ import annotations

import shutil

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult
from jarvis.tools.catalog import run_process


@pytest.fixture
def tools(config, store):
    registry = build_registry(config, store)

    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)

    call.registry = registry
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


def fehler(result: ToolResult) -> ToolResult:
    assert not result.ok, f"{result.tool} hätte fehlschlagen müssen: {result.summary}"
    return result


def _daemon_erreichbar() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return run_process(["docker", "info"], timeout=5).returncode == 0
    except Exception:  # noqa: BLE001 - jeder Fehlschlag heißt "nicht erreichbar"
        return False


_hat_docker = shutil.which("docker") is not None
_hat_daemon = _daemon_erreichbar()
braucht_docker = pytest.mark.skipif(not _hat_docker, reason="docker nicht installiert")
braucht_daemon = pytest.mark.skipif(not _hat_daemon, reason="kein laufender Docker-Daemon")


@braucht_docker
def test_ohne_laufenden_daemon_meldet_das_ehrlich(tools):
    if _hat_daemon:
        pytest.skip("hier läuft tatsächlich ein Docker-Daemon -- der Fehlerfall "
                    "lässt sich so nicht auslösen")
    res = fehler(tools("docker.ps"))
    assert "daemon" in res.summary.lower() or "docker.sock" in res.summary.lower()


@braucht_daemon
def test_ps_und_images_live(tools):
    erfolg(tools("docker.ps"))
    erfolg(tools("docker.images"))
    erfolg(tools("docker.volumes.list"))
    erfolg(tools("docker.networks.list"))


@braucht_daemon
def test_run_stop_logs_remove_lebenszyklus(tools):
    lauf = erfolg(tools("docker.run", image="alpine:latest", name="jarvis-test-container",
                        command=["sleep", "30"]))
    assert lauf.ok
    try:
        erfolg(tools("docker.logs", name="jarvis-test-container"))
        erfolg(tools("docker.inspect", name="jarvis-test-container"))
        erfolg(tools("docker.stop", name="jarvis-test-container", timeout_sekunden=2))
    finally:
        tools("docker.remove", name="jarvis-test-container", force=True)


# ═══════════════════════════════════════════════════════════════ Sicherheit
def test_name_mit_fuehrendem_bindestrich_wird_abgelehnt(tools):
    fehler(tools("docker.logs", name="--all"))
    fehler(tools("docker.stop", name="-f"))
    fehler(tools("docker.run", image="-x"))
