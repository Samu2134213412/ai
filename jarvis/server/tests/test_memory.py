"""Das Gedächtnis: ablegen, verknüpfen, und vor allem — von selbst wiederfinden."""

from __future__ import annotations

from jarvis.memory import DEFAULT_SEED, MemoryStore


def test_anlegen_und_zurueckholen(store):
    node = store.add(label="Kaffee", kind="vorliebe", text="schwarz, ohne Zucker")
    holen = store.get(node.id)
    assert holen.label == "Kaffee"
    assert holen.kind == "vorliebe"


def test_unbekannte_art_faellt_auf_fakt_zurueck(store):
    assert store.add(label="X", kind="quatsch").kind == "fakt"


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
    assert zweiter.graph() == graph
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


def test_datei_ueberlebt_den_neustart(tmp_path):
    pfad = tmp_path / "unterordner" / "gedaechtnis.sqlite3"
    erste = MemoryStore(pfad)
    erste.add(label="Bleibt", kind="fakt", text="auch nach dem Schließen")
    erste.close()

    zweite = MemoryStore(pfad)
    assert [m.label for m in zweite.all()] == ["Bleibt"]
    zweite.close()
