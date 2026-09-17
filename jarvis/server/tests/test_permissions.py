"""Das Permission-System: Stufen, Regeln, und der Bestätigungs-Round-Trip."""

from __future__ import annotations

import asyncio

import pytest

from jarvis.permissions import (PermissionDenied, PermissionGate, PermissionLevel,
                                PermissionPolicy)


# ══════════════════════════════════════════════════════ PermissionLevel
def test_label_and_from_label_roundtrip():
    for level in PermissionLevel:
        assert PermissionLevel.from_label(level.label) is level


def test_from_label_ist_gross_klein_unempfindlich():
    assert PermissionLevel.from_label("safe") is PermissionLevel.SAFE
    assert PermissionLevel.from_label("Critical") is PermissionLevel.CRITICAL


def test_unbekannte_stufe_wirft():
    with pytest.raises(ValueError, match="Unbekannte Sicherheitsstufe"):
        PermissionLevel.from_label("gibtsnicht")


def test_reihenfolge_ist_risiko_aufsteigend():
    assert PermissionLevel.SAFE < PermissionLevel.READ < PermissionLevel.WRITE
    assert PermissionLevel.WRITE < PermissionLevel.SYSTEM < PermissionLevel.CRITICAL


# ══════════════════════════════════════════════════════ PermissionPolicy
def test_safe_verlangt_nie_bestaetigung():
    policy = PermissionPolicy(confirm_read=True, confirm_write=True, confirm_system=True)
    assert policy.requires_confirmation(PermissionLevel.SAFE) is False


def test_critical_verlangt_immer_bestaetigung_auch_bei_maximal_laxer_policy():
    """Der Kern der Regel: es gibt kein Feld, das das abschalten könnte."""
    policy = PermissionPolicy(confirm_read=False, confirm_write=False, confirm_system=False)
    assert policy.requires_confirmation(PermissionLevel.CRITICAL) is True


def test_read_write_system_folgen_der_konfiguration():
    policy = PermissionPolicy(confirm_read=False, confirm_write=True, confirm_system=True)
    assert policy.requires_confirmation(PermissionLevel.READ) is False
    assert policy.requires_confirmation(PermissionLevel.WRITE) is True
    assert policy.requires_confirmation(PermissionLevel.SYSTEM) is True


# ══════════════════════════════════════════════════════ PermissionGate
async def test_safe_laeuft_ohne_ereignis_und_ohne_warten():
    events: list[tuple[str, dict]] = []

    async def emit(kind, payload):
        events.append((kind, payload))

    gate = PermissionGate(emit=emit)
    await gate.check("read_file", PermissionLevel.SAFE, {"path": "a.txt"})
    assert events == []
    assert gate.pending == []


async def test_bestaetigte_aktion_laeuft_weiter():
    events: list[tuple[str, dict]] = []

    async def emit(kind, payload):
        events.append((kind, payload))

    gate = PermissionGate(emit=emit)
    task = asyncio.ensure_future(
        gate.check("write_file", PermissionLevel.WRITE, {"path": "a.txt"}, detail="schreibe a.txt"))
    await asyncio.sleep(0)  # dem Task erlauben, bis zum await zu laufen
    assert len(gate.pending) == 1
    request_id = gate.pending[0]

    assert gate.resolve(request_id, True) is True
    await task  # wirft nicht

    kinds = [k for k, _ in events]
    assert kinds == ["permission.requested", "permission.approved"]
    assert events[0][1]["tool"] == "write_file"
    assert events[0][1]["level"] == "WRITE"
    assert events[0][1]["detail"] == "schreibe a.txt"


async def test_abgelehnte_aktion_wirft_permissiondenied():
    gate = PermissionGate()
    task = asyncio.ensure_future(
        gate.check("delete_file", PermissionLevel.CRITICAL, {"path": "a.txt"}))
    await asyncio.sleep(0)
    request_id = gate.pending[0]
    gate.resolve(request_id, False)

    with pytest.raises(PermissionDenied, match="delete_file"):
        await task


async def test_zeitueberschreitung_lehnt_ab_statt_ewig_zu_warten():
    policy = PermissionPolicy(confirmation_timeout=0.05)
    events: list[str] = []

    async def emit(kind, _payload):
        events.append(kind)

    gate = PermissionGate(policy=policy, emit=emit)
    with pytest.raises(PermissionDenied):
        await gate.check("run_command", PermissionLevel.SYSTEM, {})

    assert "permission.timeout" in events
    assert gate.pending == []


def test_resolve_einer_unbekannten_anfrage_gibt_false():
    gate = PermissionGate()
    assert gate.resolve("nie-gestellt", True) is False


async def test_resolve_kann_nicht_zweimal_dieselbe_anfrage_beantworten():
    gate = PermissionGate()
    task = asyncio.ensure_future(
        gate.check("write_file", PermissionLevel.WRITE, {}))
    await asyncio.sleep(0)
    request_id = gate.pending[0]

    assert gate.resolve(request_id, True) is True
    assert gate.resolve(request_id, False) is False  # längst beantwortet
    await task
