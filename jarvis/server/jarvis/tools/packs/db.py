"""Tool Pack: Datenbank (SQLite).

Aufgabenstellung Punkt 22: **DELETE/DROP/UPDATE nur mit Bestätigung, höhere
Permission für destruktive Aktionen.** Ein einzelnes Werkzeug hat aber nur
eine feste Sicherheitsstufe -- ein generisches ``db.execute(sql)`` könnte
also gar nicht unterscheiden, ob der Text gerade ein harmloses SELECT oder
ein DROP TABLE ist. Deshalb gibt es hier keine SQL-Zeichenkette, die
irgendetwas tun darf, sondern benannte Operatoren je Aktion mit der jeweils
passenden Stufe: lesen ist READ, anlegen/einfügen ist WRITE, ändern ist
SYSTEM, löschen ist CRITICAL -- und ``update``/``delete`` verweigern eine
leere WHERE-Klausel von sich aus (keine versehentliche Massenänderung).

Tabellen-/Spaltennamen lassen sich in SQLite nicht parametrisieren (``?``
funktioniert nur für Werte) -- deshalb werden sie hier gegen ein festes
Muster geprüft (``_ident``), bevor sie in ein Statement eingesetzt werden.
Werte selbst laufen immer über Platzhalter.

Nur SQLite: kommt mit Python (``sqlite3`` in der Standardbibliothek), keine
neue Abhängigkeit, keine Serverinstallation nötig. Postgres/MySQL sind bei
diesem Ausbau bewusst nicht dabei -- ohne einen laufenden Server zum
Gegenprüfen wären Werkzeuge dafür Behauptungen, keine geprüften Operatoren
(Punkt 40).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext
from ._base import flag, integer, ok, params, planned, table, text

MAX_ROWS = 500
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(name: str, art: str = "Name") -> str:
    n = (name or "").strip()
    if not _IDENT.match(n):
        raise ToolError(f"Kein gültiger {art}: {name!r} (nur Buchstaben, Ziffern, "
                        "Unterstrich, darf nicht mit einer Ziffer beginnen)")
    return n


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    def db_datei(raw: str, muss_existieren: bool = True) -> Path:
        pfad = ws.resolve(raw)
        if muss_existieren and not pfad.is_file():
            raise ToolError(f"Datenbankdatei existiert nicht: {pfad}")
        return pfad

    def verbindung(pfad: Path) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(str(pfad), timeout=10)
            conn.execute("SELECT 1")  # erzwingt sofort einen echten Fehler, falls
            return conn                # die Datei kein SQLite ist, statt erst spaeter
        except sqlite3.DatabaseError as exc:
            raise ToolError(f"Keine lesbare SQLite-Datenbank: {pfad} ({exc})") from exc

    # ══════════════════════════════════════════════════════════ Lesend
    def db_tables(path: str) -> ToolResult:
        conn = verbindung(db_datei(path))
        try:
            rows = conn.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        finally:
            conn.close()
        return ok("db.sqlite.tables", f"{len(rows)} Tabelle(n)/View(s)",
                  payload=table([list(r) for r in rows], headers=["Name", "Art"]),
                  anzahl=len(rows))

    def db_schema(path: str, table_name: str) -> ToolResult:
        t = _ident(table_name, "Tabellenname")
        conn = verbindung(db_datei(path))
        try:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
        finally:
            conn.close()
        if not row:
            raise ToolError(f"Tabelle nicht gefunden: {t}")
        return ok("db.sqlite.schema", f"Schema von {t}", payload=row[0], tabelle=t)

    def db_info(path: str) -> ToolResult:
        pfad = db_datei(path)
        conn = verbindung(pfad)
        try:
            anzahl_tabellen = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            seiten = conn.execute("PRAGMA page_count").fetchone()[0]
            seitengroesse = conn.execute("PRAGMA page_size").fetchone()[0]
        finally:
            conn.close()
        groesse = pfad.stat().st_size
        return ok("db.sqlite.info",
                  f"{anzahl_tabellen} Tabelle(n), {groesse / 1024:.1f} KB",
                  pfad=str(pfad), tabellen=anzahl_tabellen, bytes=groesse,
                  seiten=seiten, seitengroesse=seitengroesse)

    def db_query(path: str, sql: str, params_list: list[Any] | None = None,
                limit: int = 200) -> ToolResult:
        satz = (sql or "").strip()
        if not satz.lower().startswith("select"):
            raise ToolError("db.sqlite.query akzeptiert nur SELECT-Anweisungen -- für "
                            "Änderungen gibt es eigene Werkzeuge (insert/update/delete).")
        if ";" in satz.rstrip(";"):
            raise ToolError("Nur eine einzelne Anweisung, kein Semikolon mittendrin.")
        conn = verbindung(db_datei(path))
        try:
            cur = conn.execute(satz, tuple(params_list or ()))
            spalten = [d[0] for d in cur.description] if cur.description else []
            n = max(1, min(int(limit or 200), MAX_ROWS))
            zeilen = cur.fetchmany(n)
        except sqlite3.Error as exc:
            raise ToolError(f"SQL-Fehler: {exc}") from exc
        finally:
            conn.close()
        rows = [list(r) for r in zeilen]
        return ok("db.sqlite.query", f"{len(rows)} Zeile(n)" + (
                  f" (auf {n} begrenzt)" if len(rows) == n else ""),
                  payload=table(rows, headers=spalten) if spalten else "(keine Spalten)",
                  anzahl=len(rows), spalten=spalten)

    # ══════════════════════════════════════════════════════════ WRITE
    def db_create_table(path: str, table_name: str, columns: list[dict[str, str]]) -> ToolResult:
        t = _ident(table_name, "Tabellenname")
        if not columns:
            raise ToolError("Es wurden keine Spalten angegeben.")
        teile = []
        for spalte in columns:
            name = _ident(str(spalte.get("name", "")), "Spaltenname")
            typ = str(spalte.get("type", "TEXT")).strip().upper()
            if typ not in ("TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC"):
                raise ToolError(f"Unbekannter Spaltentyp: {typ!r} "
                                "(TEXT/INTEGER/REAL/BLOB/NUMERIC)")
            zusatz = " PRIMARY KEY" if spalte.get("primary_key") else ""
            zusatz += " NOT NULL" if spalte.get("not_null") and not spalte.get("primary_key") else ""
            teile.append(f'"{name}" {typ}{zusatz}')
        conn = verbindung(db_datei(path, muss_existieren=False))
        try:
            conn.execute(f'CREATE TABLE IF NOT EXISTS "{t}" ({", ".join(teile)})')
            conn.commit()
        except sqlite3.Error as exc:
            raise ToolError(f"CREATE TABLE fehlgeschlagen: {exc}") from exc
        finally:
            conn.close()
        return ok("db.sqlite.create_table", f"Tabelle angelegt: {t} ({len(teile)} Spalte(n))",
                  tabelle=t, spalten=len(teile))

    def db_insert(path: str, table_name: str, values: dict[str, Any]) -> ToolResult:
        t = _ident(table_name, "Tabellenname")
        if not values:
            raise ToolError("Es wurden keine Werte angegeben.")
        spalten = [_ident(k, "Spaltenname") for k in values]
        spalten_sql = ", ".join(f'"{s}"' for s in spalten)
        platzhalter = ", ".join("?" for _ in spalten)
        conn = verbindung(db_datei(path))
        try:
            cur = conn.execute(
                f'INSERT INTO "{t}" ({spalten_sql}) VALUES ({platzhalter})',
                tuple(values[k] for k in spalten))
            conn.commit()
        except sqlite3.Error as exc:
            raise ToolError(f"INSERT fehlgeschlagen: {exc}") from exc
        finally:
            conn.close()
        return ok("db.sqlite.insert", f"1 Zeile eingefügt in {t}", tabelle=t,
                  id=cur.lastrowid)

    def db_backup(path: str, output: str, overwrite: bool = False) -> ToolResult:
        quelle = db_datei(path)
        ziel = ws.resolve(output)
        if ziel.exists() and not overwrite:
            raise ToolError(f"Ziel existiert schon: {ziel}. Mit overwrite=true überschreiben.")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        quelle_conn = verbindung(quelle)
        ziel_conn = sqlite3.connect(str(ziel))
        try:
            quelle_conn.backup(ziel_conn)
        finally:
            ziel_conn.close()
            quelle_conn.close()
        return ok("db.sqlite.backup", f"Sicherung erstellt: {ziel.name}",
                  pfad=str(ziel), bytes=ziel.stat().st_size)

    # ══════════════════════════════════════════════════════════ SYSTEM
    def db_update(path: str, table_name: str, set_values: dict[str, Any], where: str,
                 where_params: list[Any] | None = None, dry_run: bool = False) -> ToolResult:
        t = _ident(table_name, "Tabellenname")
        if not set_values:
            raise ToolError("Es wurden keine zu ändernden Werte angegeben.")
        if not (where or "").strip():
            raise ToolError("where fehlt -- ein UPDATE ohne WHERE würde die ganze Tabelle "
                            "ändern. Absichtlich alle Zeilen treffen? Dann where='1=1' setzen.")
        spalten = [_ident(k, "Spaltenname") for k in set_values]
        setz_teil = ", ".join(f'"{s}" = ?' for s in spalten)
        conn = verbindung(db_datei(path))
        try:
            betroffen = conn.execute(
                f'SELECT count(*) FROM "{t}" WHERE {where}',
                tuple(where_params or ())).fetchone()[0]
            if dry_run:
                return planned("db.sqlite.update", f"{betroffen} Zeile(n) in {t} würden "
                               "geändert", tabelle=t, betroffen=betroffen)
            conn.execute(f'UPDATE "{t}" SET {setz_teil} WHERE {where}',
                        (*[set_values[k] for k in spalten], *(where_params or ())))
            conn.commit()
        except sqlite3.Error as exc:
            raise ToolError(f"UPDATE fehlgeschlagen: {exc}") from exc
        finally:
            conn.close()
        return ok("db.sqlite.update", f"{betroffen} Zeile(n) in {t} geändert",
                  tabelle=t, betroffen=betroffen)

    # ══════════════════════════════════════════════════════════ CRITICAL
    def db_delete(path: str, table_name: str, where: str, where_params: list[Any] | None = None,
                 dry_run: bool = False) -> ToolResult:
        t = _ident(table_name, "Tabellenname")
        if not (where or "").strip():
            raise ToolError("where fehlt -- ein DELETE ohne WHERE würde die ganze Tabelle "
                            "leeren. Absichtlich alle Zeilen löschen? Dann where='1=1' setzen.")
        conn = verbindung(db_datei(path))
        try:
            betroffen = conn.execute(
                f'SELECT count(*) FROM "{t}" WHERE {where}',
                tuple(where_params or ())).fetchone()[0]
            if dry_run:
                return planned("db.sqlite.delete", f"{betroffen} Zeile(n) in {t} würden "
                               "gelöscht", tabelle=t, betroffen=betroffen)
            conn.execute(f'DELETE FROM "{t}" WHERE {where}', tuple(where_params or ()))
            conn.commit()
        except sqlite3.Error as exc:
            raise ToolError(f"DELETE fehlgeschlagen: {exc}") from exc
        finally:
            conn.close()
        return ok("db.sqlite.delete", f"{betroffen} Zeile(n) aus {t} gelöscht",
                  tabelle=t, betroffen=betroffen)

    def db_drop_table(path: str, table_name: str, dry_run: bool = False) -> ToolResult:
        t = _ident(table_name, "Tabellenname")
        conn = verbindung(db_datei(path))
        try:
            existiert = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
                (t,)).fetchone()[0]
            if not existiert:
                raise ToolError(f"Tabelle nicht gefunden: {t}")
            zeilen = conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
            if dry_run:
                return planned("db.sqlite.drop_table",
                               f"{t} würde gelöscht ({zeilen} Zeile(n) darin)",
                               tabelle=t, zeilen=zeilen)
            conn.execute(f'DROP TABLE "{t}"')
            conn.commit()
        except sqlite3.Error as exc:
            raise ToolError(f"DROP TABLE fehlgeschlagen: {exc}") from exc
        finally:
            conn.close()
        return ok("db.sqlite.drop_table", f"Tabelle gelöscht: {t} ({zeilen} Zeile(n) "
                  "waren darin)", tabelle=t, zeilen=zeilen)

    _p = text("Pfad zur SQLite-Datenbankdatei (im Arbeitsbereich)")

    return [
        # ── Lesend ──────────────────────────────────────────────────────
        Tool("db.sqlite.tables", "Listet Tabellen und Views einer SQLite-Datenbank.",
             params("path", path=_p), db_tables, level=P.READ, tags=("datenbank", "sqlite")),
        Tool("db.sqlite.schema", "Zeigt die CREATE-TABLE-Anweisung einer Tabelle.",
             params("path", "table_name", path=_p, table_name=text("Tabellenname")),
             db_schema, level=P.READ, tags=("datenbank", "sqlite")),
        Tool("db.sqlite.info", "Größe, Tabellenzahl und Seiteninformationen der Datenbank.",
             params("path", path=_p), db_info, level=P.READ, tags=("datenbank", "sqlite")),
        Tool("db.sqlite.query", "Führt eine einzelne SELECT-Abfrage aus (für Änderungen "
             "gibt es eigene Werkzeuge).",
             params("path", "sql", path=_p, sql=text("SELECT-Anweisung, Platzhalter '?'"),
                    params_list={"type": "array", "items": {},
                                "description": "Werte für die '?'-Platzhalter"},
                    limit=integer(f"Max. Zeilen, Vorgabe 200, Obergrenze {MAX_ROWS}")),
             db_query, level=P.READ, tags=("datenbank", "sqlite", "sql"),
             phrases=("frag die datenbank ab", "sql select")),

        # ── WRITE ───────────────────────────────────────────────────────
        Tool("db.sqlite.create_table", "Legt eine neue Tabelle an.",
             params("path", "table_name", "columns", path=_p, table_name=text("Tabellenname"),
                    columns={"type": "array", "items": {"type": "object"},
                            "description": "[{name, type, primary_key?, not_null?}, ...]"}),
             db_create_table, level=P.WRITE, tags=("datenbank", "sqlite")),
        Tool("db.sqlite.insert", "Fügt eine Zeile in eine Tabelle ein.",
             params("path", "table_name", "values", path=_p, table_name=text("Tabellenname"),
                    values={"type": "object", "description": "{spalte: wert, ...}"}),
             db_insert, level=P.WRITE, tags=("datenbank", "sqlite"),
             phrases=("trag das in die datenbank ein",)),
        Tool("db.sqlite.backup", "Kopiert die gesamte Datenbank in eine neue Datei "
             "(konsistent, auch während sie in Benutzung ist).",
             params("path", "output", path=_p, output=text("Zielpfad"),
                    overwrite=flag("Bestehendes Ziel überschreiben")),
             db_backup, level=P.WRITE, tags=("datenbank", "sqlite", "backup")),

        # ── SYSTEM ──────────────────────────────────────────────────────
        Tool("db.sqlite.update", "Ändert Zeilen einer Tabelle. Eine WHERE-Klausel ist "
             "Pflicht (Punkt 22) -- 'where=\"1=1\"' für ausdrücklich alle Zeilen.",
             params("path", "table_name", "set_values", "where", path=_p,
                    table_name=text("Tabellenname"),
                    set_values={"type": "object", "description": "{spalte: neuer_wert, ...}"},
                    where=text("WHERE-Bedingung ohne das Wort WHERE, z. B. \"id = ?\""),
                    where_params={"type": "array", "items": {},
                                 "description": "Werte für '?' in where"},
                    dry_run=flag("Nur zeigen, wie viele Zeilen betroffen wären")),
             db_update, level=P.SYSTEM, tags=("datenbank", "sqlite"), dry_run=True),

        # ── CRITICAL ────────────────────────────────────────────────────
        Tool("db.sqlite.delete", "Löscht Zeilen aus einer Tabelle. Eine WHERE-Klausel ist "
             "Pflicht (Punkt 22) -- 'where=\"1=1\"' für ausdrücklich alle Zeilen.",
             params("path", "table_name", "where", path=_p, table_name=text("Tabellenname"),
                    where=text("WHERE-Bedingung ohne das Wort WHERE"),
                    where_params={"type": "array", "items": {},
                                 "description": "Werte für '?' in where"},
                    dry_run=flag("Nur zeigen, wie viele Zeilen betroffen wären")),
             db_delete, level=P.CRITICAL, tags=("datenbank", "sqlite", "loeschen"),
             dry_run=True),
        Tool("db.sqlite.drop_table", "Löscht eine ganze Tabelle samt Inhalt, unwiderruflich.",
             params("path", "table_name", path=_p, table_name=text("Tabellenname"),
                    dry_run=flag("Nur zeigen, wie viele Zeilen betroffen wären")),
             db_drop_table, level=P.CRITICAL, tags=("datenbank", "sqlite", "loeschen"),
             dry_run=True),
    ]
