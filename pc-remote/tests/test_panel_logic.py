import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import panel_logic as L  # noqa: E402


def test_config_defaults_roundtrip_and_garbage(tmp_path):
    f = tmp_path / "c.json"
    assert L.load_config(f) == L.DEFAULTS                      # missing file
    L.save_config({"port": 9000, "overlay": False, "allow_exec": True}, f)
    assert L.load_config(f) == {"port": 9000, "overlay": False, "allow_exec": True}
    f.write_text('{"port": "x", "overlay": 5}')                # wrong types are ignored
    assert L.load_config(f)["port"] == 8765
    f.write_text("not json")
    assert L.load_config(f) == L.DEFAULTS


def test_autostart_toggle(tmp_path):
    assert not L.autostart_enabled(tmp_path)
    L.set_autostart(True, r"C:\Py\pythonw.exe", r"C:\x y\server.py", tmp_path)
    assert L.autostart_enabled(tmp_path)
    text = (tmp_path / "PCRemote.vbs").read_text()
    assert '"""C:\\Py\\pythonw.exe"" ""C:\\x y\\server.py"""' in text and ", 0, False" in text
    L.set_autostart(False, "", "", tmp_path)
    assert not L.autostart_enabled(tmp_path)


def test_stop_server_only_kills_when_something_answers(tmp_path):
    pid_file = tmp_path / "pid"
    pid_file.write_text("4242")
    killed = []
    assert L.stop_server(8765, pid_file, killed.append, running=lambda p: False) is False
    assert killed == [] and not pid_file.exists()              # stale pid file: removed, nobody killed
    pid_file.write_text("4242")
    assert L.stop_server(8765, pid_file, killed.append, running=lambda p: True) is True
    assert killed == [4242] and not pid_file.exists()


def test_server_running_via_opener():
    import types
    ok = lambda url, timeout=0: types.SimpleNamespace(status=200, __enter__=lambda s: s, __exit__=lambda *a: None)
    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
    assert L.server_running(8765, lambda url, timeout=0: R()) is True
    def boom(url, timeout=0): raise OSError
    assert L.server_running(8765, boom) is False


def test_read_links_and_missing_modules(tmp_path):
    f = tmp_path / "l.txt"
    f.write_text("WLAN:      http://1.2.3.4:8765/#T\nOEFFENTLICH: https://pc.ts.net/#T\n")
    assert L.read_links(f) == {"wlan": "http://1.2.3.4:8765/#T", "public": "https://pc.ts.net/#T"}
    assert L.read_links(tmp_path / "none") == {}
    assert L.missing_modules(["json", "definitely_not_a_module_xyz"]) == ["definitely_not_a_module_xyz"]


def test_start_server_command():
    seen = {}
    L.start_server("/py", "/srv/server.py", popen=lambda cmd, **kw: seen.update(cmd=cmd, kw=kw) or "proc")
    assert seen["cmd"] == ["/py", "/srv/server.py"]


def test_parse_getmac_only_connected_adapters():
    txt = ('"AA-BB-CC-DD-EE-01","\\Device\\Tcpip_{1234}"\r\n'
           '"AA-BB-CC-DD-EE-02","Media disconnected"\r\n'
           '"AA-BB-CC-DD-EE-03","Hardware not present"\r\n')
    assert L.parse_getmac(txt) == ["AA-BB-CC-DD-EE-01"]


def test_local_macs_fallback_format():
    m = L.local_macs()
    assert m and len(m[0].split("-")) == 6


def test_single_instance_lock():
    a = L.acquire_single_instance(48999)
    assert a is not None
    assert L.acquire_single_instance(48999) is None   # second panel refuses to start
    a.close()
    b = L.acquire_single_instance(48999)
    assert b is not None
    b.close()
