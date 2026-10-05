"""Tests der Web-API (Fake-Ollama, echter HTTP-Server)."""

import base64
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import main  # noqa: E402
import web  # noqa: E402
from test_tutor import FakeClient  # noqa: E402

PROMPT = "SYSTEM {{fach}} {{sprache}}"


def start(token=None, client=None):
    config = main.load_config(Path("/nonexistent"))
    server = web.make_server(config, client or FakeClient(models=["qwen2.5:32b", "x:1b", "qwen2.5vl:7b"]),
                             PROMPT, "127.0.0.1", 0, token)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def call(base, path, body=None, headers=None):
    req = urllib.request.Request(
        base + path, data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def events(raw: bytes):
    return [json.loads(line[5:]) for line in raw.decode().split("\n\n") if line.startswith("data:")]


class WebTests(unittest.TestCase):
    def setUp(self):
        self.server, self.base = start()
        self.client = self.server.RequestHandlerClass.app.client

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()

    def test_static_and_manifest(self):
        for path in ("/", "/app.js", "/style.css", "/icon.svg"):
            self.assertEqual(call(self.base, path)[0], 200, path)
        status, _, body = call(self.base, "/manifest.webmanifest")
        self.assertEqual(json.loads(body)["display"], "standalone")
        self.assertEqual(call(self.base, "/../main.py")[0], 404)

    def test_state(self):
        _, _, body = call(self.base, "/api/state")
        s = json.loads(body)
        self.assertEqual((s["stage"], s["attempts"], s["model"]), (1, 0, "qwen2.5:32b"))
        self.assertIn("x:1b", s["models"])

    def test_chat_streams_and_advances_stage(self):
        for i in range(3):
            _, headers, raw = call(self.base, "/api/chat", {"text": f"frage {i}"})
            self.assertIn("text/event-stream", headers["Content-Type"])
            evs = events(raw)
            self.assertEqual("".join(e.get("t", "") for e in evs).strip(),
                             "Was hast du schon versucht?")
            self.assertTrue(evs[-1]["done"])
        self.assertEqual(evs[-1]["state"]["stage"], 2)
        self.assertIn("Stufe 2", self.client.calls[-1]["messages"][0]["content"])

    def test_giveup_flow(self):
        _, _, raw = call(self.base, "/api/giveup", {})
        self.assertIn("notice", json.loads(raw))          # noch keine Aufgabe
        call(self.base, "/api/chat", {"text": "aufgabe"})
        _, _, raw = call(self.base, "/api/giveup", {})
        self.assertIn("Bestätigen", json.loads(raw)["notice"])
        _, _, raw = call(self.base, "/api/giveup", {})
        evs = events(raw)
        self.assertEqual(evs[-1]["state"]["stage"], 4)
        self.assertIn("AUFGEGEBEN", self.client.calls[-1]["messages"][0]["content"])

    def test_page_context_reaches_tutor_and_new_resets(self):
        img = base64.b64encode(b"x" * 300).decode()
        status, _, raw = call(self.base, "/api/page", {"image": "data:image/png;base64," + img})
        self.assertEqual(status, 200)
        self.assertIn("3x + 7 = 22", json.loads(raw)["summary"])
        self.assertEqual(self.client.calls[-1]["messages"][0]["images"], [img])
        call(self.base, "/api/chat", {"text": "hilf"})
        self.assertIn("Abschrift", self.client.calls[-1]["messages"][0]["content"])
        call(self.base, "/api/new", {})
        _, _, raw = call(self.base, "/api/state")
        self.assertFalse(json.loads(raw)["has_page"])

    def test_page_without_image(self):
        self.assertEqual(call(self.base, "/api/page", {"image": ""})[0], 400)

    def test_errors(self):
        self.assertEqual(call(self.base, "/api/chat", {"text": " "})[0], 400)
        status, _, raw = call(self.base, "/api/model", {"name": "nope:1b"})
        self.assertEqual(status, 400)
        self.assertIn("ollama pull nope:1b", json.loads(raw)["error"])
        self.assertEqual(call(self.base, "/api/model", {"name": "x:1b"})[0], 200)

    def test_chat_error_event(self):
        self.server.RequestHandlerClass.app.session.model = "weg:1b"
        _, _, raw = call(self.base, "/api/chat", {"text": "hi"})
        ev = events(raw)[-1]
        self.assertIn("ollama pull weg:1b", ev["error"])
        self.assertEqual(ev["state"]["attempts"], 0)

    def test_foreign_origin_rejected(self):
        status, *_ = call(self.base, "/api/chat", {"text": "hi"}, {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)

    def test_subject(self):
        call(self.base, "/api/subject", {"subject": "Physik"})
        call(self.base, "/api/chat", {"text": "hi"})
        self.assertIn("SYSTEM  für Physik Deutsch", self.client.calls[-1]["messages"][0]["content"])


class TokenTests(unittest.TestCase):
    def test_token_required(self):
        server, base = start(token="geheim")
        try:
            self.assertEqual(call(base, "/api/state")[0], 401)
            self.assertEqual(call(base, "/")[0], 401)
            self.assertEqual(call(base, "/api/state", headers={"Cookie": "tutor_token=falsch"})[0], 401)
            self.assertEqual(call(base, "/api/state", headers={"Cookie": "tutor_token=geheim"})[0], 200)
            _, _, body = call(base, "/manifest.webmanifest")
            self.assertIn("?t=geheim", json.loads(body)["start_url"])
        finally:
            server.shutdown(); server.server_close()


if __name__ == "__main__":
    unittest.main()
