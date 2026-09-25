"""Das Gedächtnis: ablegen, verknüpfen, und vor allem — von selbst wiederfinden."""

from __future__ import annotations

import sqlite3
import time

from jarvis.memory import DEFAULT_SEED, MemoryStore


def test_anlegen_und_zurueckholen(store):
    node = store.add(label="Kaffee", kind="vorliebe", text="schwarz, ohne Zucker")
    holen = store.get(node.id)
    assert holen.label == "Kaffee"
    assert holen.kind == "vorliebe"


def test_unbekannte_art_faellt_auf_fakt_zurueck(store):
    assert store.add(label="X", kind="quatsch").kind == "fakt"


# ═══════════════════════════════════════════════════ Metadatenfelder (Phase 2)
def test_metadaten_werden_gespeichert_und_zurueckgelesen(store):
    node = store.add(label="Wichtig", text="nie vergessen", kind="regel",
                     importance=0.9, source="modell", confidence=0.4)
    assert (node.importance, node.source, node.confidence) == (0.9, "modell", 0.4)
    geholt = store.get(node.id)
    assert (geholt.importance, geholt.source, geholt.confidence) == (0.9, "modell", 0.4)


def test_metadaten_haben_vernuenftige_vorgaben(store):
    node = store.add(label="X")
    assert (node.importance, node.source, node.confidence) == (0.5, "", 1.0)


def test_importance_wird_auf_gueltigen_bereich_begrenzt(store):
    zu_hoch = store.add(label="A", importance=5.0)
    zu_niedrig = store.add(label="B", importance=-2.0)
    assert zu_hoch.importance == 1.0
    assert zu_niedrig.importance == 0.0


def test_created_bleibt_bei_erneutem_add_mit_gleicher_id_erhalten(store):
    erste = store.add(label="A", node_id="a")
    zweite = store.add(label="A geändert", node_id="a")
    assert zweite.created == erste.created
    assert zweite.updated >= erste.updated
    assert zweite.label == "A geändert"


def test_hohe_wichtigkeit_hebt_die_rangfolge_unter_treffern(store):
    store.add(label="Server A", kind="fakt", text="läuft stabil", importance=0.1)
    store.add(label="Server B", kind="fakt", text="läuft stabil", importance=0.9)
    treffer = store.search("Server läuft stabil")
    assert treffer[0].label == "Server B"


def test_verknuepfen_ist_richtungslos(store):
    a = store.add(label="A")
    b = store.add(label="B")
    store.link(a.id, b.id)
    assert [n.id for n in store.neighbours(b.id)] == [a.id]
    store.link(b.id, a.id)                       # dieselbe Kante, nicht zwei
    assert len(store.graph()["links"]) == 1


def test_loeschen_nimmt_die_kanten_mit(store):
    a = store.add(label="A")
    b = store.add(label="B")
    store.link(a.id, b.id)
    store.delete(a.id)
    assert store.graph()["links"] == []
    assert store.neighbours(b.id) == []


# ═══════════════════════════════════════════════════════ selbständiger Abruf
def test_titeltreffer_wiegt_schwerer_als_fliesstext(store):
    store.add(label="Raspberry Pi", kind="hardware", text="2 GB RAM")
    store.add(label="Notizen", kind="fakt", text="Irgendwas über Raspberry am Rande")
    treffer = store.search("Raspberry")
    assert treffer[0].label == "Raspberry Pi"


def test_regeln_werden_angehoben(store):
    """Was Jarvis nie tun darf, soll nicht aus dem Kontext fallen."""
    store.add(label="Grundregel", kind="regel", text="Kein Erfolg ohne Werkzeug.")
    store.add(label="Werkzeugkiste", kind="fakt", text="Kein Werkzeug ist auch eine Antwort.")
    treffer = store.search("Werkzeug")
    assert treffer[0].kind == "regel"


def test_fuellwoerter_erzeugen_keine_treffer(store):
    store.add(label="Kaffee", kind="vorliebe", text="schwarz")
    assert store.search("wie ist das und der von mit") == []


def test_kontextblock_ist_leer_wenn_nichts_passt(store):
    store.add(label="Kaffee", kind="vorliebe", text="schwarz")
    assert store.context_for("Quantenchromodynamik") == ""


def test_kontextblock_traegt_art_und_text(store):
    store.add(label="Kaffee", kind="vorliebe", text="schwarz, ohne Zucker")
    block = store.context_for("Kaffee")
    assert "[vorliebe]" in block and "ohne Zucker" in block


# ═══════════════════════════════════════════════════════════════ Graph
def test_graph_und_ruecknahme_sind_symmetrisch(store):
    store.add(label="A", node_id="a", kind="projekt", text="erste")
    store.add(label="B", node_id="b")
    store.link("a", "b")
    graph = store.graph()

    zweiter = MemoryStore(":memory:")
    zweiter.replace_graph(graph)
    zurueck = zweiter.graph()
    # "created"/"updated" unterscheiden sich zurecht -- der zweite Speicher
    # legt die Knoten gerade erst an, statt sie aus der Vergangenheit zu
    # übernehmen. Alles inhaltliche muss trotzdem identisch sein.
    def ohne_zeit(g):
        return [{k: v for k, v in n.items() if k not in ("created", "updated")}
                for n in g["nodes"]]
    assert ohne_zeit(zurueck) == ohne_zeit(graph)
    assert zurueck["links"] == graph["links"]
    zweiter.close()


def test_positionen_ueberleben_den_umweg_ueber_die_oberflaeche(store):
    store.add(label="A", node_id="a", x=0.25, y=-0.5)
    store.replace_graph(store.graph())
    knoten = store.graph()["nodes"][0]
    assert (knoten["x"], knoten["y"]) == (0.25, -0.5)


def test_seed_laeuft_nur_einmal(store):
    store.seed(DEFAULT_SEED)
    erste = len(store.all())
    store.seed(DEFAULT_SEED)
    assert len(store.all()) == erste
    assert any(m.kind == "regel" for m in store.all())


def test_alte_datenbank_ohne_metadatenspalten_wird_nachgeruestet(tmp_path):
    # Simuliert eine echte, schon benutzte Datenbank auf der Maschine des
    # Nutzers, angelegt bevor es importance/source/confidence gab -- die
    # Migration muss sie öffnen können, ohne die vorhandene Erinnerung zu
    # verlieren, und die neuen Spalten mit brauchbaren Vorgaben nachrüsten.
    pfad = tmp_path / "alt.sqlite3"
    roh = sqlite3.connect(str(pfad))
    roh.executescript("""
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'fakt',
            text TEXT NOT NULL DEFAULT '', x REAL, y REAL,
            created REAL NOT NULL, updated REAL NOT NULL
        );
        CREATE TABLE links (
            a TEXT NOT NULL, b TEXT NOT NULL, PRIMARY KEY (a, b)
        );
    """)
    jetzt = time.time()
    roh.execute("INSERT INTO nodes (id,label,kind,text,created,updated) VALUES "
               "('n1','Alte Erinnerung','fakt','aus der Zeit davor',?,?)", (jetzt, jetzt))
    roh.commit()
    roh.close()

    geoeffnet = MemoryStore(pfad)
    alte = geoeffnet.get("n1")
    assert alte.label == "Alte Erinnerung"
    assert (alte.importance, alte.source, alte.confidence) == (0.5, "", 1.0)

    neue = geoeffnet.add(label="Neu", importance=0.8, source="modell")
    assert (neue.importance, neue.source) == (0.8, "modell")
    geoeffnet.close()


def test_datei_ueberlebt_den_neustart(tmp_path):
    pfad = tmp_path / "unterordner" / "gedaechtnis.sqlite3"
    erste = MemoryStore(pfad)
    erste.add(label="Bleibt", kind="fakt", text="auch nach dem Schließen")
    erste.close()

    zweite = MemoryStore(pfad)
    assert [m.label for m in zweite.all()] == ["Bleibt"]
    zweite.close()


# ═══════════════════════════════════════ Session-Ebene (Phase 2, "sitzung")
def test_sitzung_ist_eine_gueltige_art(store):
    assert store.add(label="X", kind="sitzung").kind == "sitzung"


def test_ohne_expires_ist_eine_erinnerung_dauerhaft(store):
    node = store.add(label="Dauerhaft")
    assert node.expires is None


def test_expires_wird_gespeichert_und_zurueckgelesen(store):
    ablauf = time.time() + 3600
    node = store.add(label="Sitzung", kind="sitzung", expires=ablauf)
    assert node.expires == ablauf
    assert store.get(node.id).expires == ablauf


def test_abgelaufene_erinnerung_faellt_aus_der_suche(store):
    store.add(label="Vorbei", kind="sitzung", text="laengst passe",
             expires=time.time() - 1)
    assert store.search("passe") == []
    assert store.context_for("passe") == ""


def test_abgelaufene_erinnerung_faellt_aus_all_und_graph(store):
    store.add(label="Noch da", node_id="frisch")
    store.add(label="Vorbei", node_id="alt", kind="sitzung", expires=time.time() - 1)
    assert [m.id for m in store.all()] == ["frisch"]
    assert [n["id"] for n in store.graph()["nodes"]] == ["frisch"]


def test_abgelaufene_erinnerung_faellt_als_nachbar_und_kante_weg(store):
    store.add(label="Bleibt", node_id="a")
    store.add(label="Verblasst", node_id="b", kind="sitzung", expires=time.time() - 1)
    store.link("a", "b")
    assert store.neighbours("a") == []
    assert store.graph()["links"] == []


def test_get_findet_eine_abgelaufene_erinnerung_noch_vor_dem_aufraeumen(store):
    """expires steuert, was beim Abrufen/Stöbern auftaucht -- ein gezielter
    Zugriff über die bekannte id (z. B. durch memory_forget oder undo) soll
    trotzdem noch funktionieren, solange purge_expired sie nicht schon
    endgültig entfernt hat."""
    node = store.add(label="Verblasst", kind="sitzung", expires=time.time() - 1)
    assert store.get(node.id) is not None


def test_purge_expired_entfernt_abgelaufene_endgueltig(store):
    store.add(label="Bleibt", node_id="a")
    store.add(label="Verblasst", node_id="b", kind="sitzung", expires=time.time() - 1)
    store.link("a", "b")

    entfernt = store.purge_expired()

    assert entfernt == 1
    assert store.get("a") is not None
    assert store.get("b") is None


def test_purge_expired_laesst_dauerhaftes_und_zukuenftiges_in_ruhe(store):
    store.add(label="Dauerhaft", node_id="a")
    store.add(label="Läuft noch", node_id="b", kind="sitzung", expires=time.time() + 3600)
    assert store.purge_expired() == 0
    assert store.get("a") is not None
    assert store.get("b") is not None


def test_neue_instanz_raeumt_abgelaufenes_beim_start_weg(tmp_path):
    pfad = tmp_path / "gedaechtnis.sqlite3"
    erste = MemoryStore(pfad)
    erste.add(label="Verblasst", node_id="b", kind="sitzung", expires=time.time() - 1)
    erste.close()

    zweite = MemoryStore(pfad)
    assert zweite.get("b") is None
    zweite.close()


def test_replace_graph_behaelt_expires_bei(store):
    store.add(label="Sitzung", node_id="s", kind="sitzung", expires=time.time() + 3600)
    graph = store.graph()

    zweiter = MemoryStore(":memory:")
    zweiter.replace_graph(graph)
    assert zweiter.get("s").expires == graph["nodes"][0]["expires"]
    zweiter.close()


def test_alte_datenbank_ohne_expires_spalte_wird_nachgeruestet(tmp_path):
    """Wie test_alte_datenbank_ohne_metadatenspalten_wird_nachgeruestet, nur
    für die Session-Ebene: eine Datenbank von vor dieser Version hat noch
    keine expires-Spalte. Die Migration muss sie nachrüsten, ohne die
    bestehende Erinnerung als "abgelaufen" zu behandeln (NULL, nicht 0)."""
    pfad = tmp_path / "ohne_expires.sqlite3"
    roh = sqlite3.connect(str(pfad))
    roh.executescript("""
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'fakt',
            text TEXT NOT NULL DEFAULT '', x REAL, y REAL,
            importance REAL NOT NULL DEFAULT 0.5, source TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 1.0,
            created REAL NOT NULL, updated REAL NOT NULL
        );
        CREATE TABLE links (
            a TEXT NOT NULL, b TEXT NOT NULL, PRIMARY KEY (a, b)
        );
    """)
    jetzt = time.time()
    roh.execute("INSERT INTO nodes (id,label,kind,text,created,updated) VALUES "
               "('n1','Alt','fakt','von vorher',?,?)", (jetzt, jetzt))
    roh.commit()
    roh.close()

    geoeffnet = MemoryStore(pfad)
    alte = geoeffnet.get("n1")
    assert alte.expires is None
    geoeffnet.close()
