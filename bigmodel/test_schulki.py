"""SchulKI pool tests: routing, fairness, failover and auth, against a fake Ollama."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import schulki as sk
from ollama_max import Ollama


class FakeOllama(BaseHTTPRequestHandler):
    reply = "Antwort"

    def log_message(self, *a):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/show":
            body = json.dumps({"capabilities": ["completion"]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.end_headers()
        text = f"{self.server.label}:{req['messages'][-1]['content'][:20]}"
        for part in (text[:3], text[3:]):
            self.wfile.write((json.dumps({"message": {"content": part}}) + "\n").encode())
        self.wfile.write(b'{"done": true}\n')


def fake_ollama(label):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    srv.label = label
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, Ollama(f"http://127.0.0.1:{srv.server_port}")


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def node(key, name, model=None, ollama=None):
    port = free_port()
    n = sk.Node(key, name, port, model, ollama, advertise="127.0.0.1")
    n.start(broadcast=False)
    return n


def chat(n, text, key="geheim123", thorough=False):
    req = urllib.request.Request(
        f"http://127.0.0.1:{n.port}/api/chat",
        data=json.dumps({"messages": [{"role": "user", "content": text}], "thorough": thorough}).encode(),
        headers={"Content-Type": "application/json", "X-Pool-Token": sk.token_for(key)}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return [json.loads(line) for line in r]


def text_of(events):
    return "".join(e.get("t", "") for e in events)


def test_browser_only_node_routes_to_contributor_and_discovers_via_gossip():
    o1, api1 = fake_ollama("A")
    a = node("geheim123", "pc-a", "qwen3:8b", api1)
    b = node("geheim123", "pc-b", "qwen3:14b", fake_ollama("B")[1])
    c = node("geheim123", "handy")                    # contributes nothing
    a.add_peer(b.addr, manual=True)
    c.add_peer(a.addr, manual=True)                   # c only knows a
    for _ in range(2):
        for n in (a, b, c):
            n.poll_peers()
    assert {p["name"] for p in c.alive_peers()} == {"pc-a", "pc-b"}   # learned b through a
    ev = chat(c, "Was ist 2+2?")
    assert ev[0]["node"] in ("pc-a", "pc-b") and ev[-1] == {"done": True}
    assert text_of(ev).endswith("Was ist 2+2?")
    # thorough questions go to the best model
    ev = chat(c, "Erkläre Photosynthese", thorough=True)
    assert ev[0]["node"] == "pc-b" and any(e.get("stage") == "Kritik" for e in ev)
    for n in (a, b, c):
        n.stop()


def test_failover_when_a_device_disappears():
    a = node("geheim123", "pc-a", "qwen3:14b", fake_ollama("A")[1])
    b = node("geheim123", "pc-b", "qwen3:8b", fake_ollama("B")[1])
    c = node("geheim123", "handy")
    for x in (a, b):
        c.add_peer(x.addr, manual=True)
    c.poll_peers()
    a.stop()                                          # laptop closed, c does not know yet
    ev = chat(c, "Hallo", thorough=True)              # would prefer pc-a (better model)
    assert ev[-1] == {"done": True} and text_of(ev).startswith("B:")
    b.stop()
    c.stop()


def test_no_contributor_gives_clear_error():
    c = node("geheim123", "handy")
    ev = chat(c, "Hallo")
    assert "error" in ev[-1] and "Kein Gerät" in ev[-1]["error"]
    c.stop()


def test_wrong_password_rejected_and_foreign_pool_ignored():
    a = node("geheim123", "pc-a", "qwen3:8b", fake_ollama("A")[1])
    with pytest.raises(urllib.error.HTTPError) as e:
        chat(a, "Hallo", key="falsch999")
    assert e.value.code == 401
    other = node("anderes-pw", "fremd")
    other.add_peer(a.addr)
    other.poll_peers()
    assert other.alive_peers() == []
    a.stop()
    other.stop()


def test_contributors_are_served_first():
    q = sk.WorkQueue()
    assert q.acquire(1)                                # someone is being served
    order = []

    def wait(prio, tag):
        q.acquire(prio)
        order.append(tag)
        q.release()

    t1 = threading.Thread(target=wait, args=(1, "nur-nutzer"))
    t1.start()
    time.sleep(0.05)
    t2 = threading.Thread(target=wait, args=(0, "mitrechner"))
    t2.start()
    time.sleep(0.05)
    q.release()
    t1.join(2)
    t2.join(2)
    assert order == ["mitrechner", "nur-nutzer"]


def test_pick_pool_model():
    assert sk.pick_pool_model(24, 32) == ("qwen3.6:27b", "GPU")
    assert sk.pick_pool_model(8, 16) == ("qwen3:8b", "GPU")
    assert sk.pick_pool_model(6, 16) == ("qwen3:4b", "GPU")
    assert sk.pick_pool_model(None, 16) == ("qwen3:4b", "CPU")
    assert sk.pick_pool_model(None, 32) == ("qwen3:8b", "CPU")
    assert sk.pick_pool_model(None, 4) == (None, "")


def test_beacon_signature():
    payload = b'{"addr": "1.2.3.4:47801"}'
    sig = sk.beacon_sign("geheim123", payload)
    assert sig == sk.beacon_sign("geheim123", payload) != sk.beacon_sign("anders", payload)
