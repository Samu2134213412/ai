import http.client
import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
import server  # noqa: E402


class Rec:
    def __init__(self):
        self.calls = []

    def grab(self, mon=0):
        return Image.new("RGB", (1920, 1080), "red")

    def pointer(self):
        return None

    def __getattr__(self, n):
        return lambda *a: self.calls.append((n, a))


@pytest.fixture(autouse=True)
def clean_state():
    server.held_keys.clear()
    server.held_btns.clear()
    server.last_input[0] = server.last_control[0] = 0.0


def test_key_hold_and_release_all():
    be = Rec()
    server.dispatch(be, "key_down", {"key": "w"})
    server.dispatch(be, "press", {"button": "left", "down": True})
    assert server.held_keys == {"w"} and server.held_btns == {"left"}
    server.dispatch(be, "release_all", {})
    assert ("key_up", ("w",)) in be.calls and ("press", ("left", False)) in be.calls
    assert not server.held_keys and not server.held_btns


def test_watchdog_releases_stuck_keys():
    be = Rec()
    server.dispatch(be, "key_down", {"key": "w"})
    t = server.last_input[0]
    assert server.release_stale(be, now=t + 1) is False   # phone still recently active
    assert server.release_stale(be, now=t + 4) is True    # phone went silent
    assert ("key_up", ("w",)) in be.calls and not server.held_keys
    assert server.release_stale(be, now=t + 10) is False  # nothing held


def test_batch_keeps_order_and_rejects_nesting():
    be = Rec()
    server.dispatch(be, "batch", {"actions": [{"a": "key_down", "key": "w"}, {"a": "rmove", "dx": 5, "dy": -3},
                                              {"a": "key_up", "key": "w"}]})
    assert [c[0] for c in be.calls] == ["key_down", "rel_move", "key_up"]
    assert ("rel_move", (5, -3)) in be.calls
    with pytest.raises(ValueError):
        server.dispatch(be, "batch", {"actions": [{"a": "batch", "actions": []}]})
    with pytest.raises(ValueError):
        server.dispatch(be, "batch", {"actions": [{"a": "noop"}] * 65})


def test_quiet_input_does_not_trigger_glow():
    be = Rec()
    server.dispatch(be, "rmove", {"dx": 1, "dy": 1, "quiet": True})
    assert server.last_control[0] == 0.0
    server.dispatch(be, "rmove", {"dx": 1, "dy": 1})
    assert server.last_control[0] > 0


def test_stream_mjpeg_frames_and_pacing():
    chunks = []
    def write(b):
        chunks.append(b)
        if len(chunks) >= 10:
            raise BrokenPipeError
    t0 = time.perf_counter()
    with pytest.raises(BrokenPipeError):
        server.stream_mjpeg(Rec(), write, 0, 640, 30, 50)
    dt = time.perf_counter() - t0
    assert chunks[0].startswith(b"--frame\r\nContent-Type: image/jpeg") and b"\xff\xd8" in chunks[0]
    assert dt >= 0.25  # 10 frames at 30 fps can't be faster than ~0.3 s
    jpeg = chunks[0].split(b"\r\n\r\n", 1)[1]
    assert Image.open(__import__("io").BytesIO(jpeg)).width == 640


@pytest.fixture
def http_srv():
    be = Rec()
    s = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(be, "tok", False))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield be, s.server_port
    s.shutdown()


def test_stream_endpoint_auth_via_query_only_for_stream(http_srv):
    _, port = http_srv
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("GET", "/api/stream?t=bad")
    assert c.getresponse().status == 401
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("GET", "/api/ping?t=tok")          # token in URL must NOT work elsewhere
    assert c.getresponse().status == 401
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("GET", "/api/stream?t=tok&w=400&fps=60&q=40")
    r = c.getresponse()
    assert r.status == 200 and "multipart/x-mixed-replace" in r.getheader("Content-Type")
    assert r.read(60).startswith(b"--frame")
    c.close()


def test_keepalive_survives_rejected_post(http_srv):
    _, port = http_srv
    c = http.client.HTTPConnection("127.0.0.1", port)
    body = json.dumps({"a": "x" * 500})
    c.request("POST", "/api/noop", body=body, headers={"X-Token": "bad"})
    r = c.getresponse(); r.read()
    assert r.status == 401
    c.request("POST", "/api/noop", body="{}", headers={"X-Token": "tok"})   # same connection
    r = c.getresponse()
    assert r.status == 200 and json.loads(r.read())["ok"] is True


def test_stream_is_pipelined_and_ordered(monkeypatch):
    """Slow encoder (30 ms) must not cap fps at 1/30 s: frames are encoded in parallel but written in order."""
    n = [0]
    def slow_encode(img, width, quality, fast=False):
        i = n[0] = n[0] + 1
        time.sleep(0.03)
        return b"\xff\xd8" + i.to_bytes(4, "big")
    monkeypatch.setattr(server, "encode_jpeg", slow_encode)
    got = []
    t0 = time.perf_counter()
    def write(b):
        got.append(int.from_bytes(b.split(b"\r\n\r\n", 1)[1][2:6], "big"))
    server.stream_mjpeg(Rec(), write, 0, 640, 100, 50, should_stop=lambda: time.perf_counter() - t0 > 0.6)
    assert got == sorted(got)                 # in order
    assert len(got) >= 28                     # a single 30 ms encoder would give at most ~20 in 0.6 s


def test_fast_encode_matches_requested_width():
    img = Image.new("RGB", (1920, 1080), "blue")
    import io
    for w in (480, 640, 854, 1280, 1600):
        assert Image.open(io.BytesIO(server.encode_jpeg(img, w, 55, True))).width == w
