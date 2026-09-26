"""Das Audit Log: schreiben, wiederfinden, filtern."""

from __future__ import annotations

import time

import pytest

from jarvis.audit import AuditLog
from jarvis.permissions import PermissionLevel


@pytest.fixture
def log() -> AuditLog:
    audit = AuditLog(":memory:")
    yield audit
    audit.close()


def test_record_liest_sich_wieder_aus(log: AuditLog):
    entry = log.record(tool="write_file", level=PermissionLevel.WRITE,
                       arguments={"path": "a.txt"}, ok=True,
                       summary="Datei geschrieben: a.txt", request="schreib a.txt")
    hits = log.query()
    assert len(hits) == 1
    assert hits[0].id == entry.id
    assert hits[0].tool == "write_file"
    assert hits[0].level is PermissionLevel.WRITE
    assert hits[0].arguments == {"path": "a.txt"}
    assert hits[0].ok is True
    assert hits[0].request == "schreib a.txt"


def test_as_dict_hat_die_form_aus_der_aufgabenstellung(log: AuditLog):
    entry = log.record(tool="restart_server", level=PermissionLevel.SAFE,
                       arguments={}, ok=True, summary="Erfolg",
                       request="Restart Minecraft server")
    d = entry.as_dict()
    assert d["anfrage"] == "Restart Minecraft server"
    assert d["werkzeug"] == "restart_server"
    assert d["stufe"] == "SAFE"
    assert d["erfolg"] is True
    assert "zeit" in d


def test_filter_nach_werkzeug(log: AuditLog):
    log.record(tool="write_file", level=PermissionLevel.WRITE, arguments={}, ok=True, summary="")
    log.record(tool="delete_file", level=PermissionLevel.CRITICAL, arguments={}, ok=True, summary="")
    hits = log.query(tool="delete_file")
    assert len(hits) == 1
    assert hits[0].tool == "delete_file"


def test_filter_nach_stufe(log: AuditLog):
    log.record(tool="a", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="")
    log.record(tool="b", level=PermissionLevel.CRITICAL, arguments={}, ok=True, summary="")
    hits = log.query(level=PermissionLevel.CRITICAL)
    assert [h.tool for h in hits] == ["b"]


def test_filter_nach_erfolg(log: AuditLog):
    log.record(tool="a", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="")
    log.record(tool="b", level=PermissionLevel.SAFE, arguments={}, ok=False, summary="kaputt")
    hits = log.query(ok=False)
    assert len(hits) == 1
    assert hits[0].summary == "kaputt"


def test_filter_nach_zeitraum(log: AuditLog):
    log.record(tool="alt", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="")
    schnitt = time.time() + 0.01
    time.sleep(0.02)
    log.record(tool="neu", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="")
    hits = log.query(since=schnitt)
    assert [h.tool for h in hits] == ["neu"]


def test_neueste_zuerst(log: AuditLog):
    log.record(tool="eins", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="")
    time.sleep(0.01)
    log.record(tool="zwei", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="")
    hits = log.query()
    assert [h.tool for h in hits] == ["zwei", "eins"]


def test_limit_wird_begrenzt(log: AuditLog):
    for i in range(5):
        log.record(tool=f"t{i}", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="")
    assert len(log.query(limit=2)) == 2
    assert len(log.query(limit=10_000)) == 5  # geclampt auf sinnvolle Obergrenze, wirft nicht


def test_count(log: AuditLog):
    assert log.count() == 0
    log.record(tool="a", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="")
    assert log.count() == 1


def test_task_id_wird_gespeichert(log: AuditLog):
    log.record(tool="a", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="",
              task_id="task123")
    assert log.query()[0].task_id == "task123"


def test_datei_wird_bei_bedarf_angelegt(tmp_path):
    path = tmp_path / "unterordner" / "protokoll.sqlite3"
    audit = AuditLog(path)
    audit.record(tool="a", level=PermissionLevel.SAFE, arguments={}, ok=True, summary="")
    audit.close()
    assert path.is_file()

    wieder = AuditLog(path)
    assert wieder.count() == 1
    wieder.close()
