import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import server  # noqa: E402


class Fake:
    def __init__(self):
        self.calls = []

    def pointer(self):
        return (0, 0.25, 0.5)

    def __getattr__(self, name):
        def f(*a):
            self.calls.append((name, a))
            return b"jpg" if name == "screenshot" else "out"
        return f


@pytest.fixture
def srv():
    be = Fake()
    h = server.make_handler(be, "tok", allow_exec=False)
    s = ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield be, f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def call(url, path, data=None, token="tok"):
    req = urllib.request.Request(url + path, data=None if data is None else json.dumps(data).encode(),
                                 headers={"X-Token": token})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_auth_required(srv):
    be, url = srv
    assert call(url, "/api/move", {"dx": 1, "dy": 1}, token="bad")[0] == 401
    assert call(url, "/api/screen", token="")[0] == 401
    assert be.calls == []


def test_page_is_public(srv):
    assert call(url=srv[1], path="/", token="")[0] == 200


def test_move_click_type(srv):
    be, url = srv
    assert call(url, "/api/move", {"dx": 3, "dy": -4})[0] == 200
    assert call(url, "/api/click", {"button": "right", "double": True})[0] == 200
    assert call(url, "/api/type", {"text": "hé"})[0] == 200
    assert be.calls == [("move", (3.0, -4.0)), ("click", ("right", 2)), ("type", ("hé",))]


def test_validation(srv):
    _, url = srv
    assert call(url, "/api/move", {"dx": 99999, "dy": 0})[0] == 400
    assert call(url, "/api/click", {"button": "x"})[0] == 400
    assert call(url, "/api/open_url", {"url": "file:///etc/passwd"})[0] == 400
    assert call(url, "/api/power", {"name": "rm"})[0] == 400
    assert call(url, "/api/nope", {})[0] == 400


def test_exec_disabled_by_default(srv):
    be, url = srv
    assert call(url, "/api/run", {"cmd": "id"})[0] == 403
    assert be.calls == []


def test_screen(srv):
    code, body = call(srv[1], "/api/screen?w=400")
    assert (code, body) == (200, b"jpg")


def test_lockout_after_many_failures(srv):
    be, url = srv
    for _ in range(20):
        assert call(url, "/api/ping", token="bad")[0] == 401
    assert call(url, "/api/ping", token="bad")[0] == 429
    assert call(url, "/api/ping", token="tok")[0] == 429  # global lockout (tunnel hides IPs)


def test_ping_and_monitor_args(srv):
    be, url = srv
    assert call(url, "/api/screen?w=400&mon=1")[0] == 200
    assert call(url, "/api/move_to", {"x": 0.5, "y": 0.5, "mon": 1})[0] == 200
    assert ("screenshot", (400, 55, 1)) in be.calls
    assert ("move_to", (0.5, 0.5, 1)) in be.calls


def test_screen_region_is_passed_and_clamped(srv):
    be, url = srv
    assert call(url, "/api/screen?w=400&mon=0&x=0.9&y=-1&z=0.25")[0] == 200
    assert ("screenshot", (400, 55, 0, (0.75, 0.0, 0.25))) in be.calls


def test_screen_sends_pointer_header(srv):
    be, url = srv
    req = urllib.request.Request(url + "/api/screen?w=400", headers={"X-Token": "tok"})
    with urllib.request.urlopen(req) as r:
        assert r.headers["X-Pointer"] == "0,0.25000,0.50000"
