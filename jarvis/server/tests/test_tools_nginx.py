"""Das nginx-Pack: ohne installiertes nginx bleibt es bei der ehrlichen
Fehlermeldung -- läuft irgendwo ein echtes nginx, laufen die markierten
Tests zusätzlich live mit."""

from __future__ import annotations

import shutil

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult


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


_hat_nginx = shutil.which("nginx") is not None
braucht_nginx = pytest.mark.skipif(not _hat_nginx, reason="nginx nicht installiert")


def test_ohne_nginx_meldet_config_test_das_ehrlich(tools):
    if _hat_nginx:
        pytest.skip("nginx ist hier installiert")
    fehler(tools("nginx.config.test"))


def test_ohne_nginx_meldet_version_das_ehrlich(tools):
    if _hat_nginx:
        pytest.skip("nginx ist hier installiert")
    fehler(tools("nginx.version"))


@braucht_nginx
def test_config_test_und_version_live(tools):
    erfolg(tools("nginx.config.test"))
    erfolg(tools("nginx.version"))


@braucht_nginx
def test_sites_list_live(tools):
    # nicht jede Distribution nutzt sites-available/-enabled (RHEL z. B. nicht) --
    # ein ehrlicher Fehlschlag ist hier ebenfalls ein gueltiges Ergebnis.
    ergebnis = tools("nginx.sites.list")
    assert ergebnis.ok or "sites-available" in ergebnis.summary


def test_ungueltiger_seitenname_wird_abgelehnt(tools):
    fehler(tools("nginx.site.enable", site="../../etc/passwd"))
    fehler(tools("nginx.site.enable", site=""))
    fehler(tools("nginx.site.disable", site="."))
