import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import wake  # noqa: E402


def test_magic_packet():
    p = wake.magic_packet("aa:bb:cc:dd:ee:ff")
    assert len(p) == 102 and p[:6] == b"\xff" * 6 and p[6:12] == bytes.fromhex("aabbccddeeff")


def test_bad_mac():
    with pytest.raises(ValueError):
        wake.magic_packet("zz")


def test_wake_endpoint_auth_and_send():
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    sent = []
    s = ThreadingHTTPServer(("127.0.0.1", 0), wake.make_handler("t", "aa:bb:cc:dd:ee:ff", "x", lambda m, b: sent.append(m), "http://pc"))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{s.server_port}"
    def post(tok):
        try:
            return urllib.request.urlopen(urllib.request.Request(base + "/wake", data=b"", headers={"X-Token": tok})).status
        except urllib.error.HTTPError as e:
            return e.code
    assert post("bad") == 401 and sent == []
    assert post("t") == 200 and sent == ["aa:bb:cc:dd:ee:ff"]
    assert json.load(urllib.request.urlopen(base + "/cfg"))["pc_url"] == "http://pc"
    s.shutdown()
