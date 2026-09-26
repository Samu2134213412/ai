"""Das Datenbank-Pack: SQLite braucht keine externe Abhängigkeit und läuft
deshalb hier vollständig echt -- eine echte Datei, echtes SQL, kein Mock."""

from __future__ import annotations

import sqlite3

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


@pytest.fixture
def db(workspace):
    pfad = workspace / "test.db"
    conn = sqlite3.connect(pfad)
    conn.execute("CREATE TABLE personen (id INTEGER PRIMARY KEY, name TEXT, alter_ INTEGER)")
    conn.executemany("INSERT INTO personen (name, alter_) VALUES (?, ?)",
                     [("Alice", 30), ("Bob", 25), ("Carol", 40)])
    conn.commit()
    conn.close()
    return pfad


def test_tables(tools, db):
    res = erfolg(tools("db.sqlite.tables", path="test.db"))
    assert res.evidence["anzahl"] == 1
    assert "personen" in res.payload


def test_schema(tools, db):
    res = erfolg(tools("db.sqlite.schema", path="test.db", table_name="personen"))
    assert "personen" in res.payload.lower()


def test_info(tools, db):
    res = erfolg(tools("db.sqlite.info", path="test.db"))
    assert res.evidence["tabellen"] == 1
    assert res.evidence["bytes"] > 0


def test_query_select(tools, db):
    res = erfolg(tools("db.sqlite.query", path="test.db",
                       sql="SELECT name, alter_ FROM personen WHERE alter_ > ?",
                       params_list=[26]))
    assert res.evidence["anzahl"] == 2


def test_query_verweigert_nicht_select(tools, db):
    fehler(tools("db.sqlite.query", path="test.db", sql="DELETE FROM personen"))


def test_query_verweigert_mehrere_anweisungen(tools, db):
    fehler(tools("db.sqlite.query", path="test.db",
                 sql="SELECT 1; DROP TABLE personen"))


def test_create_table(tools, db):
    erfolg(tools("db.sqlite.create_table", path="test.db", table_name="notizen",
                 columns=[{"name": "id", "type": "INTEGER", "primary_key": True},
                         {"name": "text", "type": "TEXT", "not_null": True}]))
    res = erfolg(tools("db.sqlite.tables", path="test.db"))
    assert res.evidence["anzahl"] == 2


def test_insert(tools, db):
    res = erfolg(tools("db.sqlite.insert", path="test.db", table_name="personen",
                       values={"name": "Dave", "alter_": 22}))
    assert res.evidence["id"] > 0
    abfrage = erfolg(tools("db.sqlite.query", path="test.db",
                           sql="SELECT count(*) as n FROM personen"))
    assert "4" in abfrage.payload


def test_backup(tools, db, workspace):
    erfolg(tools("db.sqlite.backup", path="test.db", output="sicherung.db"))
    kopie = sqlite3.connect(workspace / "sicherung.db")
    zeilen = kopie.execute("SELECT count(*) FROM personen").fetchone()[0]
    kopie.close()
    assert zeilen == 3


def test_backup_ohne_overwrite_wird_abgelehnt(tools, db, workspace):
    (workspace / "sicherung.db").write_bytes(b"x")
    fehler(tools("db.sqlite.backup", path="test.db", output="sicherung.db"))
    erfolg(tools("db.sqlite.backup", path="test.db", output="sicherung.db", overwrite=True))


def test_update_verlangt_where(tools, db):
    fehler(tools("db.sqlite.update", path="test.db", table_name="personen",
                 set_values={"alter_": 99}, where=""))


def test_update_dry_run_veraendert_nichts(tools, db):
    vorschau = erfolg(tools("db.sqlite.update", path="test.db", table_name="personen",
                            set_values={"alter_": 99}, where="name = ?",
                            where_params=["Alice"], dry_run=True))
    assert vorschau.evidence["probelauf"] is True
    assert vorschau.evidence["betroffen"] == 1
    ergebnis = tools("db.sqlite.query", path="test.db",
                     sql="SELECT alter_ FROM personen WHERE name = 'Alice'")
    assert "30" in ergebnis.payload


def test_update_wirklich(tools, db):
    erfolg(tools("db.sqlite.update", path="test.db", table_name="personen",
                 set_values={"alter_": 99}, where="name = ?", where_params=["Alice"]))
    ergebnis = erfolg(tools("db.sqlite.query", path="test.db",
                            sql="SELECT alter_ FROM personen WHERE name = 'Alice'"))
    assert "99" in ergebnis.payload


def test_delete_verlangt_where(tools, db):
    fehler(tools("db.sqlite.delete", path="test.db", table_name="personen", where=""))


def test_delete_dry_run_loescht_nichts(tools, db):
    vorschau = erfolg(tools("db.sqlite.delete", path="test.db", table_name="personen",
                            where="name = ?", where_params=["Bob"], dry_run=True))
    assert vorschau.evidence["probelauf"] is True
    ergebnis = erfolg(tools("db.sqlite.query", path="test.db",
                            sql="SELECT count(*) FROM personen"))
    assert "3" in ergebnis.payload


def test_delete_wirklich(tools, db):
    erfolg(tools("db.sqlite.delete", path="test.db", table_name="personen",
                 where="name = ?", where_params=["Bob"]))
    ergebnis = erfolg(tools("db.sqlite.query", path="test.db",
                            sql="SELECT count(*) FROM personen"))
    assert "2" in ergebnis.payload


def test_drop_table_dry_run(tools, db):
    vorschau = erfolg(tools("db.sqlite.drop_table", path="test.db", table_name="personen",
                            dry_run=True))
    assert vorschau.evidence["probelauf"] is True
    erfolg(tools("db.sqlite.tables", path="test.db"))  # existiert noch


def test_drop_table_wirklich(tools, db):
    erfolg(tools("db.sqlite.drop_table", path="test.db", table_name="personen"))
    res = erfolg(tools("db.sqlite.tables", path="test.db"))
    assert res.evidence["anzahl"] == 0


# ═══════════════════════════════════════════════════════════════ Sicherheit
def test_ungueltiger_tabellenname_wird_abgelehnt(tools, db):
    fehler(tools("db.sqlite.schema", path="test.db", table_name="personen; DROP TABLE personen"))
    fehler(tools("db.sqlite.create_table", path="test.db",
                 table_name="a) ; DROP TABLE personen --",
                 columns=[{"name": "x", "type": "TEXT"}]))


def test_ungueltiger_spaltenname_wird_abgelehnt(tools, db):
    fehler(tools("db.sqlite.insert", path="test.db", table_name="personen",
                 values={"name; DROP TABLE personen --": "x"}))


def test_pfad_ausserhalb_des_arbeitsbereichs_wird_abgelehnt(tools):
    fehler(tools("db.sqlite.tables", path="/etc/hostname"))


def test_keine_sqlite_datei_wird_ehrlich_abgelehnt(tools, workspace):
    (workspace / "kaputt.db").write_bytes(b"das ist kein sqlite")
    fehler(tools("db.sqlite.tables", path="kaputt.db"))


def test_nicht_existierende_tabelle_wird_abgelehnt(tools, db):
    fehler(tools("db.sqlite.schema", path="test.db", table_name="gibtsnicht"))
    fehler(tools("db.sqlite.drop_table", path="test.db", table_name="gibtsnicht"))
