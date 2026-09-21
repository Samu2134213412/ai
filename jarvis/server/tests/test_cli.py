"""Der Start über die Kommandozeile -- vor allem die Adresse, die er nennt.

Anlass: ``--open-network`` band zwar richtig auf 0.0.0.0, gab aber genau
diese Adresse als Ziel aus. Wer sie auf dem Handy eintippt, landet nirgends.
"""

from __future__ import annotations

import socket

import pytest

from jarvis.__main__ import lan_addresses, main


def test_lan_adressen_sind_echte_adressen():
    """Was hier herauskommt, muss man aufs Handy tippen können -- also keine
    Platzhalter und kein localhost."""
    for adresse in lan_addresses():
        socket.inet_aton(adresse)          # wirft, wenn es keine IPv4 ist
        assert not adresse.startswith("127."), "localhost hilft dem Handy nicht"
        assert adresse != "0.0.0.0"        # noqa: S104 - genau das ist der Prüffall


def test_init_nennt_nur_die_lokale_adresse(tmp_path, capsys):
    ziel = tmp_path / "jarvis.json"
    assert main(["--config", str(ziel), "--init"]) == 0
    ausgabe = capsys.readouterr().out
    assert str(ziel) in ausgabe


def test_open_network_nennt_eine_tippbare_adresse(tmp_path, capsys, monkeypatch):
    """Der eigentliche Prüfpunkt: nach --open-network steht dort eine Adresse,
    die ein Handy erreichen kann, und ein Token."""
    ziel = tmp_path / "jarvis.json"
    main(["--config", str(ziel), "--init"])
    capsys.readouterr()

    # uvicorn nicht wirklich starten -- geprüft wird die Ausgabe davor.
    import jarvis.__main__ as cli
    monkeypatch.setattr(cli, "lan_addresses", lambda: ["192.168.1.42"])

    class _Abbruch(Exception):
        pass

    import sys
    import types
    falsches_uvicorn = types.ModuleType("uvicorn")

    def _run(*args, **kwargs):
        raise _Abbruch()
    falsches_uvicorn.run = _run
    monkeypatch.setitem(sys.modules, "uvicorn", falsches_uvicorn)

    with pytest.raises(_Abbruch):
        main(["--config", str(ziel), "--open-network"])

    ausgabe = capsys.readouterr().out
    assert "0.0.0.0" not in ausgabe, "0.0.0.0 ist kein Ziel, das man eintippen kann"
    assert "http://192.168.1.42:" in ausgabe
    assert "Handy" in ausgabe
    assert "Token:" in ausgabe
    assert "?token=" in ausgabe


def test_ohne_open_network_steht_der_hinweis_fuers_handy(tmp_path, capsys, monkeypatch):
    ziel = tmp_path / "jarvis.json"
    main(["--config", str(ziel), "--init"])
    capsys.readouterr()

    import sys
    import types

    class _Abbruch(Exception):
        pass

    falsches_uvicorn = types.ModuleType("uvicorn")

    def _run(*args, **kwargs):
        raise _Abbruch()
    falsches_uvicorn.run = _run
    monkeypatch.setitem(sys.modules, "uvicorn", falsches_uvicorn)

    with pytest.raises(_Abbruch):
        main(["--config", str(ziel)])

    ausgabe = capsys.readouterr().out
    assert "127.0.0.1" in ausgabe
    assert "--open-network" in ausgabe
