"""Tests der Web-API (Fake-Ollama, echter HTTP-Server)."""

import base64
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import main  # noqa: E402
import planner as pl  # noqa: E402
import web  # noqa: E402
from test_tutor import FakeClient  # noqa: E402

PROMPT = "SYSTEM {{fach}} {{sprache}}"


def start(token=None, client=None):
    config = main.load_config(Path("/nonexistent"))
    server = web.make_server(config, client or FakeClient(models=["qwen2.5:32b", "x:1b", "qwen2.5vl:7b"]),
                             PROMPT, "127.0.0.1", 0, token,
                             pl.Planner(Path(tempfile.mkdtemp()) / "p.json"))
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


class PlannerWebTests(unittest.TestCase):
    def setUp(self):
        self.server, self.base = start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()

    def test_tasks_plan_ics(self):
        _, _, raw = call(self.base, "/api/tasks", {"title": "Bio lernen", "subject": "Bio",
                                                   "due": "2099-01-02", "minutes": 60})
        state = json.loads(raw)
        self.assertEqual(state["tasks"][0]["title"], "Bio lernen")
        self.assertTrue(state["plan"]["blocks"])
        tid = state["tasks"][0]["id"]
        call(self.base, "/api/tasks/update", {"id": tid, "fields": {"done": True}})
        _, _, raw = call(self.base, "/api/planner")
        self.assertEqual(json.loads(raw)["plan"]["blocks"], [])
        status, headers, body = call(self.base, "/api/plan.ics")
        self.assertIn("text/calendar", headers["Content-Type"])
        self.assertIn(b"BEGIN:VCALENDAR", body)
        self.assertEqual(call(self.base, "/api/tasks", {"title": " "})[0], 400)

    def test_tutor_sees_open_tasks(self):
        call(self.base, "/api/tasks", {"title": "Vokabeltest", "due": "2099-01-02"})
        call(self.base, "/api/chat", {"text": "hi"})
        client = self.server.RequestHandlerClass.app.client
        self.assertIn("Vokabeltest", client.calls[-1]["messages"][0]["content"])

    def test_focus_and_blocklist(self):
        _, _, raw = call(self.base, "/api/focus/start", {"minutes": 25})
        self.assertTrue(json.loads(raw)["focus"]["active"])
        _, _, raw = call(self.base, "/api/focus")
        f = json.loads(raw)
        self.assertTrue(f["active"])
        self.assertIn("youtube.com", f["blocklist"])
        call(self.base, "/api/blocklist", {"items": ["https://www.Foo.com/x", "kaputt", "foo.com"]})
        _, _, raw = call(self.base, "/api/focus")
        self.assertEqual(json.loads(raw)["blocklist"], ["foo.com"])
        _, _, raw = call(self.base, "/api/focus/stop", {})
        self.assertFalse(json.loads(raw)["focus"]["active"])

    def test_extension_origin_allowed_and_token_header(self):
        status, headers, _ = call(self.base, "/api/focus/start", {"minutes": 1},
                                  {"Origin": "chrome-extension://abc"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "chrome-extension://abc")
        server, base = start(token="geheim")
        try:
            self.assertEqual(call(base, "/api/focus", headers={"X-Tutor-Token": "geheim"})[0], 200)
            self.assertEqual(call(base, "/api/focus")[0], 401)
        finally:
            server.shutdown(); server.server_close()

    def test_extract_tasks(self):
        client = self.server.RequestHandlerClass.app.client
        client.vision_reply = '[{"title":"Mathe S. 12","due":"2099-03-04","minutes":20},{"x":1}]'
        img = base64.b64encode(b"x" * 300).decode()
        _, _, raw = call(self.base, "/api/tasks/extract", {"images": [img, img]})   # Überlappung
        self.assertEqual(json.loads(raw)["candidates"][0]["title"], "Mathe S. 12")
        self.assertEqual(len(json.loads(raw)["candidates"]), 1)

    def test_multi_image_and_corrected_text(self):
        img = base64.b64encode(b"x" * 300).decode()
        _, _, raw = call(self.base, "/api/page", {"images": [img, img]})
        self.assertEqual(json.loads(raw)["summary"].count("Abschrift"), 2)
        call(self.base, "/api/page_text", {"text": "3x + 7 = 22"})
        call(self.base, "/api/chat", {"text": "hilf"})
        sys_prompt = self.server.RequestHandlerClass.app.client.calls[-1]["messages"][0]["content"]
        self.assertIn("3x + 7 = 22", sys_prompt)
        self.assertNotIn("Abschrift: 3x", sys_prompt)


class ShotTests(unittest.TestCase):
    def setUp(self):
        self.server, self.base = start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()

    def upload(self, data, ctype="image/png", headers=None):
        req = urllib.request.Request(self.base + "/api/shot", data=data,
                                     headers={"Content-Type": ctype, **(headers or {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_raw_upload_roundtrip(self):
        self.assertEqual(json.loads(call(self.base, "/api/shot")[2])["version"], 0)
        self.assertEqual(call(self.base, "/api/shot.img")[0], 404)
        png = b"\x89PNG" + b"x" * 400
        self.assertEqual(self.upload(png), (200, {"ok": True, "version": 1}))
        status, headers, body = call(self.base, "/api/shot.img")
        self.assertEqual((status, body, headers["Content-Type"]), (200, png, "image/png"))
        self.assertEqual(self.upload(png, "image/jpeg")[1]["version"], 2)

    def test_rejects_non_images_and_tiny(self):
        self.assertEqual(self.upload(b"x" * 400, "text/html")[0], 415)
        self.assertEqual(self.upload(b"x" * 400, "image/svg+xml")[0], 415)
        self.assertEqual(self.upload(b"x" * 10)[0], 400)

    def test_token_and_origin(self):
        server, base = start(token="geheim")
        try:
            req = lambda h: urllib.request.Request(base + "/api/shot", data=b"x" * 400,
                                                   headers={"Content-Type": "image/png", **h})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req({}))
            self.assertEqual(ctx.exception.code, 401)
            self.assertEqual(urllib.request.urlopen(req({"X-Tutor-Token": "geheim"})).status, 200)
        finally:
            server.shutdown(); server.server_close()
        self.assertEqual(self.upload(b"x" * 400, headers={"Origin": "http://evil.example"})[0], 403)


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
