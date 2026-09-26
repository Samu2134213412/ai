"""Der Start über die Kommandozeile -- vor allem die Adresse, die er nennt.

Anlass: ``--open-network`` band zwar richtig auf 0.0.0.0, gab aber genau
diese Adresse als Ziel aus. Wer sie auf dem Handy eintippt, landet nirgends.
"""

from __future__ import annotations

import socket
import sys
import types

import pytest

from jarvis.__main__ import lan_addresses, main, tailscale_addresses


def _abbrechendes_uvicorn(monkeypatch):
    """uvicorn nicht wirklich starten -- geprüft wird die Ausgabe davor."""
    class _Abbruch(Exception):
        pass

    falsches_uvicorn = types.ModuleType("uvicorn")

    def _run(*args, **kwargs):
        raise _Abbruch()
    falsches_uvicorn.run = _run
    monkeypatch.setitem(sys.modules, "uvicorn", falsches_uvicorn)
    return _Abbruch


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

    import jarvis.__main__ as cli
    monkeypatch.setattr(cli, "lan_addresses", lambda: ["192.168.1.42"])
    monkeypatch.setattr(cli, "tailscale_addresses", lambda: [])
    abbruch = _abbrechendes_uvicorn(monkeypatch)

    with pytest.raises(abbruch):
        main(["--config", str(ziel), "--open-network"])

    ausgabe = capsys.readouterr().out
    assert "0.0.0.0" not in ausgabe, "0.0.0.0 ist kein Ziel, das man eintippen kann"
    assert "http://192.168.1.42:" in ausgabe
    assert "Handy" in ausgabe
    assert "Token:" in ausgabe
    assert "?token=" in ausgabe


def test_open_network_token_bleibt_ueber_einen_neustart_hinweg(tmp_path, capsys, monkeypatch):
    """Der eigentliche Fehler: ein frisch erzeugtes Token wurde nie in die
    Konfiguration zurückgeschrieben, solange die Datei schon existierte --
    jeder weitere Start von --open-network erzeugte ein ANDERES Token, und
    jede zuvor aufs Handy eingetippte oder als App installierte Adresse
    wurde damit beim nächsten Serverstart ungültig."""
    ziel = tmp_path / "jarvis.json"
    main(["--config", str(ziel), "--init"])
    capsys.readouterr()
    abbruch = _abbrechendes_uvicorn(monkeypatch)

    def _token_aus(ausgabe: str) -> str:
        zeile = next(z for z in ausgabe.splitlines() if z.startswith("Token: "))
        return zeile.removeprefix("Token: ")

    with pytest.raises(abbruch):
        main(["--config", str(ziel), "--open-network"])
    erstes_token = _token_aus(capsys.readouterr().out)
    assert f'"token": "{erstes_token}"' in ziel.read_text(encoding="utf-8")

    with pytest.raises(abbruch):
        main(["--config", str(ziel), "--open-network"])
    zweites_token = _token_aus(capsys.readouterr().out)

    assert zweites_token == erstes_token


def test_ohne_open_network_steht_der_hinweis_fuers_handy(tmp_path, capsys, monkeypatch):
    ziel = tmp_path / "jarvis.json"
    main(["--config", str(ziel), "--init"])
    capsys.readouterr()
    abbruch = _abbrechendes_uvicorn(monkeypatch)

    with pytest.raises(abbruch):
        main(["--config", str(ziel)])

    ausgabe = capsys.readouterr().out
    assert "127.0.0.1" in ausgabe
    assert "--open-network" in ausgabe


# ═══════════════════════════════════════ Tailscale (unterwegs erreichbar)
def test_tailscale_adressen_erkennt_nur_den_eigenen_bereich(monkeypatch):
    """100.64.0.0/10 ist Tailscales Bereich (RFC 6598) -- eine gewöhnliche
    LAN- oder Loopback-Adresse auf derselben Maschine darf nicht mit
    hineinrutschen."""
    import jarvis.__main__ as cli

    class _Adresse:
        def __init__(self, family, address):
            self.family = family
            self.address = address

    fake_psutil = types.ModuleType("psutil")
    fake_psutil.net_if_addrs = lambda: {
        "tailscale0": [_Adresse(socket.AF_INET, "100.101.102.103")],
        "eth0": [_Adresse(socket.AF_INET, "192.168.1.42")],
        "lo": [_Adresse(socket.AF_INET, "127.0.0.1")],
    }
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    assert cli.tailscale_addresses() == ["100.101.102.103"]


def test_tailscale_adressen_ohne_tailscale_ist_leer(monkeypatch):
    import jarvis.__main__ as cli

    class _Adresse:
        def __init__(self, family, address):
            self.family = family
            self.address = address

    fake_psutil = types.ModuleType("psutil")
    fake_psutil.net_if_addrs = lambda: {"eth0": [_Adresse(socket.AF_INET, "192.168.1.42")]}
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    assert cli.tailscale_addresses() == []


def test_tailscale_adressen_ohne_psutil_bricht_nicht_ab(monkeypatch):
    monkeypatch.setitem(sys.modules, "psutil", None)  # import psutil -> ImportError
    assert tailscale_addresses() == []


def test_open_network_zeigt_tailscale_adresse_wenn_vorhanden(tmp_path, capsys, monkeypatch):
    ziel = tmp_path / "jarvis.json"
    main(["--config", str(ziel), "--init"])
    capsys.readouterr()

    import jarvis.__main__ as cli
    monkeypatch.setattr(cli, "lan_addresses", lambda: ["192.168.1.42"])
    monkeypatch.setattr(cli, "tailscale_addresses", lambda: ["100.101.102.103"])
    abbruch = _abbrechendes_uvicorn(monkeypatch)

    with pytest.raises(abbruch):
        main(["--config", str(ziel), "--open-network"])

    ausgabe = capsys.readouterr().out
    assert "http://100.101.102.103:" in ausgabe
    assert "unterwegs" in ausgabe


def test_open_network_ohne_tailscale_verweist_aufs_readme(tmp_path, capsys, monkeypatch):
    ziel = tmp_path / "jarvis.json"
    main(["--config", str(ziel), "--init"])
    capsys.readouterr()

    import jarvis.__main__ as cli
    monkeypatch.setattr(cli, "lan_addresses", lambda: ["192.168.1.42"])
    monkeypatch.setattr(cli, "tailscale_addresses", lambda: [])
    abbruch = _abbrechendes_uvicorn(monkeypatch)

    with pytest.raises(abbruch):
        main(["--config", str(ziel), "--open-network"])

    ausgabe = capsys.readouterr().out
    assert "Tailscale" in ausgabe
    assert "README" in ausgabe
