import io
import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import boot_guard  # noqa: E402
import wake  # noqa: E402


def opener_returning(woken):
    return lambda req, timeout=0: io.BytesIO(json.dumps({"woken": woken}).encode())


def run(woken=None, uptime=30, boom=False):
    locked = []
    def op(req, timeout=0):
        if boom:
            raise OSError("relay down")
        return opener_returning(woken)(req, timeout)
    kept = boot_guard.guard("http://x", "t", uptime, lambda: locked.append(1), op)
    return kept, bool(locked)


def test_woken_stays_unlocked():
    assert run(woken=True) == (True, False)


def test_power_button_locks():
    assert run(woken=False) == (False, True)


def test_relay_down_locks():
    assert run(boom=True) == (False, True)


def test_old_session_not_touched():
    assert run(woken=False, uptime=3600) == (True, False)


def test_relay_flag_is_one_shot_and_expires():
    now = [1000.0]
    s = ThreadingHTTPServer(("127.0.0.1", 0), wake.make_handler("t", "aa:bb:cc:dd:ee:ff", "x", lambda m, b: None,
                                                                 window=600, clock=lambda: now[0]))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{s.server_port}"
    def post(path, tok="t"):
        return json.load(urllib.request.urlopen(urllib.request.Request(base + path, data=b"", headers={"X-Token": tok})))
    assert boot_guard.was_woken(base, "t") is False         # nothing sent yet
    urllib.request.urlopen(urllib.request.Request(base + "/wake", data=b"", headers={"X-Token": "t"}))
    assert boot_guard.was_woken(base, "t") is True           # woken by phone
    assert boot_guard.was_woken(base, "t") is False          # consumed
    urllib.request.urlopen(urllib.request.Request(base + "/wake", data=b"", headers={"X-Token": "t"}))
    now[0] += 601
    assert boot_guard.was_woken(base, "t") is False          # expired
    assert boot_guard.was_woken(base, "wrong") is False      # bad token
    s.shutdown()
