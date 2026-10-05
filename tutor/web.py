#!/usr/bin/env python3
"""Web-Oberfläche des Tutors: schlanke Leiste mit Blob-Gesicht, Seiten-Ansicht
und Randnotizen. Gedacht für den iPad-Split-View neben GoodNotes.

    python web.py                       # nur dieser Rechner: http://127.0.0.1:8765
    python web.py --host 0.0.0.0        # fürs iPad im selben WLAN (mit Zugangs-Token)
"""

from __future__ import annotations

import argparse
import json
import time
import mimetypes
import re
import secrets
import socket
import sys
import threading
from datetime import date, datetime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import main as core
import planner as pl

WEB_DIR = core.BASE_DIR / "web"
MAX_BODY = 16 * 1024 * 1024
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
STATIC = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
          "/style.css": "style.css", "/icon.svg": "icon.svg", "/sw.js": "sw.js",
          "/planner.js": "planner.js", "/core.js": "core.js",
          "/backend-local.js": "backend-local.js", "/native.js": "native.js"}
EXT_ORIGINS = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


class App:
    """Zustand der Web-Sitzung (ein Lernender, eine Sitzung)."""

    def __init__(self, config: dict, client, prompt_template: str, token: str | None,
                 planner: pl.Planner | None = None):
        self.config = config
        self.planner = planner or pl.Planner(core.BASE_DIR / "data" / "planner.json")
        self.client = client
        self.prompt_template = prompt_template
        self.token = token
        self.lock = threading.Lock()
        self.session = core.Session(config, client, self._prompt(config["subject"]))
        self.shot = {"version": 0, "data": b"", "ctype": "image/png"}   # letzter Screenshot (Kurzbefehl)
        self.session.context_extra = lambda: pl.planner_block(
            self.planner.open_tasks(), date.today())

    def _prompt(self, subject: str) -> str:
        return (self.prompt_template
                .replace("{{fach}}", f" für {subject}" if subject else "")
                .replace("{{sprache}}", self.config["language"]))

    def state(self) -> dict:
        s, t = self.session, self.session.task
        stage = t.stage(s.turns_per_stage)
        return {
            "model": s.model,
            "vision_model": self.config["vision_model"],
            "subject": self.config["subject"],
            "stage": stage,               # 1–3, 4 = Lösung freigegeben
            "attempts": t.attempts,
            "given_up": t.given_up,
            "title": t.title,
            "has_page": bool(t.page_notes),
        }

    def planner_state(self) -> dict:
        p = self.planner
        return {"tasks": p.tasks(), "plan": p.plan(datetime.now()),
                "reminders": p.data["reminders"], "blocklist": p.data["blocklist"],
                "focus": p.focus(time.time())}

    def models(self) -> list[str]:
        try:
            return sorted(core.installed_models(self.client))
        except core.TutorError:
            return []

    def set_subject(self, subject: str) -> None:
        subject = subject.strip()[:60]
        self.config["subject"] = subject
        self.session.system_prompt = self._prompt(subject)

    def set_model(self, name: str) -> None:
        core.check_model(self.client, name)
        self.session.model = name


PLANNER_ROUTES = {"/api/tasks", "/api/tasks/update", "/api/tasks/delete", "/api/tasks/extract",
                  "/api/reminders", "/api/blocklist", "/api/focus/start", "/api/focus/stop"}


class Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "tutor"

    def log_message(self, *args):  # ruhig bleiben
        pass

    # -- Hilfen ----------------------------------------------------------------

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin", "")
        if origin.startswith(EXT_ORIGINS):
            self.send_header("Access-Control-Allow-Origin", origin)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8")

    def _authorized(self) -> bool:
        if not self.app.token:
            return True
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        got = self.headers.get("X-Tutor-Token") or (
            jar["tutor_token"].value if "tutor_token" in jar else "")
        return secrets.compare_digest(got, self.app.token)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        if origin.startswith(EXT_ORIGINS):       # Browser-Erweiterung (Fokus-Modus)
            return True
        return urlparse(origin).netloc == self.headers.get("Host", "")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("Anfrage zu groß")
        data = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("JSON-Objekt erwartet")
        return data

    def _sse_start(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _sse(self, obj) -> bool:
        try:
            self.wfile.write(b"data: " + json.dumps(obj, ensure_ascii=False).encode() + b"\n\n")
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def do_OPTIONS(self):
        origin = self.headers.get("Origin", "")
        self.send_response(204)
        if origin.startswith(EXT_ORIGINS):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Tutor-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- GET -------------------------------------------------------------------

    def do_GET(self):
        url = urlparse(self.path)
        extra = {}
        if url.path == "/" and self.app.token:
            given = parse_qs(url.query).get("t", [""])[0]
            if given and secrets.compare_digest(given, self.app.token):
                extra["Set-Cookie"] = (f"tutor_token={self.app.token}; Path=/; HttpOnly; "
                                       "SameSite=Lax; Max-Age=31536000")
                # Token aus der URL entfernen, Cookie genügt
                self._send(302, b"", "text/plain", {**extra, "Location": "/"})
                return
        if url.path.startswith("/api/"):
            if not self._authorized():
                return self._json({"error": "Nicht autorisiert – URL mit ?t=… öffnen."}, 401)
            if url.path == "/api/state":
                return self._json({**self.app.state(), "models": self.app.models()})
            if url.path == "/api/planner":
                return self._json(self.app.planner_state())
            if url.path == "/api/focus":
                return self._json(self.app.planner.focus(time.time()))
            if url.path == "/api/shot":
                return self._json({"version": self.app.shot["version"]})
            if url.path == "/api/shot.img":
                shot = self.app.shot
                if not shot["data"]:
                    return self._json({"error": "Noch kein Screenshot."}, 404)
                return self._send(200, shot["data"], shot["ctype"])
            if url.path == "/api/plan.ics":
                body = self.app.planner.ics(datetime.now()).encode()
                return self._send(200, body, "text/calendar; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="lernplan.ics"'})
            return self._json({"error": "Unbekannt"}, 404)
        if url.path == "/manifest.webmanifest":
            start = "/" + (f"?t={self.app.token}" if self.app.token else "")
            manifest = {
                "name": "Tutor", "short_name": "Tutor", "start_url": start, "scope": "/",
                "display": "standalone", "background_color": "#fff7ec",
                "theme_color": "#ffd9a8", "lang": "de",
                "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
            }
            return self._send(200, json.dumps(manifest).encode(), "application/manifest+json")
        name = STATIC.get(url.path)
        if not name:
            return self._send(404, b"nicht gefunden", "text/plain; charset=utf-8")
        if not self._authorized():
            return self._send(401, "Zugriff nur mit Token-URL (siehe Terminal).".encode(),
                              "text/plain; charset=utf-8")
        path = WEB_DIR / name
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if name.endswith((".js", ".css", ".html", ".svg")):
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype)

    # -- POST ------------------------------------------------------------------

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self._json({"error": "Unbekannt"}, 404)
        if not self._authorized():
            return self._json({"error": "Nicht autorisiert – URL mit ?t=… öffnen."}, 401)
        if not self._origin_ok():
            return self._json({"error": "Falscher Origin"}, 403)
        if path == "/api/shot":
            return self._receive_shot()
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError) as exc:
            return self._json({"error": f"Ungültige Anfrage: {exc}"}, 400)

        app = self.app
        if path in PLANNER_ROUTES:
            return self._planner_route(path, body)
        if not app.lock.acquire(blocking=False):
            return self._json({"error": "Der Tutor antwortet noch – kurz warten."}, 409)
        try:
            self._route(path, body)
        finally:
            app.lock.release()

    def _route(self, path: str, body: dict):
        app, session = self.app, self.app.session
        if path == "/api/chat":
            text = str(body.get("text", "")).strip()
            if not text:
                return self._json({"error": "Leere Nachricht"}, 400)
            session.confirm_give_up = False
            return self._stream(text)
        if path == "/api/giveup":
            status, msg = session.request_give_up()
            if status != "ok":
                return self._json({"notice": msg, "state": app.state()})
            return self._stream(session.GIVE_UP_TEXT)
        if path == "/api/new":
            text = str(body.get("text", "")).strip()
            session.confirm_give_up = False
            if session.task.messages:
                session.tasks.append(core.Task())
            else:
                session.task.title, session.task.given_up = "", False
                session.task.page_notes.clear()
            if text:
                return self._stream(text)
            return self._json({"state": app.state()})
        if path == "/api/model":
            try:
                app.set_model(str(body.get("name", "")).strip())
            except core.TutorError as exc:
                return self._json({"error": str(exc)}, 400)
            return self._json({"state": app.state()})
        if path == "/api/subject":
            app.set_subject(str(body.get("subject", "")))
            return self._json({"state": app.state()})
        if path == "/api/page":
            return self._page(body)
        if path == "/api/page_text":
            return self._page_text(body)
        if path == "/api/save":
            saved = session.save()
            return self._json({"saved": str(saved) if saved else None})
        return self._json({"error": "Unbekannt"}, 404)

    def _receive_shot(self):
        """Roher Bild-Upload, z. B. aus einem iPad-Kurzbefehl („Inhalt von URL abrufen“)."""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        n = int(self.headers.get("Content-Length") or 0)
        if not ctype.startswith("image/") or ctype == "image/svg+xml":
            return self._json({"error": "Bild (PNG/JPEG) als Anfrage-Inhalt senden."}, 415)
        if not 100 < n <= MAX_BODY:
            return self._json({"error": "Bild fehlt oder ist zu groß."}, 400)
        data = self.rfile.read(n)
        shot = self.app.shot
        shot.update(data=data, ctype=ctype, version=shot["version"] + 1)
        return self._json({"ok": True, "version": shot["version"]})

    def _planner_route(self, path: str, body: dict):
        app = self.app
        p = app.planner
        if path == "/api/tasks":
            if not p.add(body):
                return self._json({"error": "Titel fehlt."}, 400)
        elif path == "/api/tasks/update":
            if not p.update(str(body.get("id", "")), body.get("fields") or {}):
                return self._json({"error": "Aufgabe nicht gefunden."}, 404)
        elif path == "/api/tasks/delete":
            p.delete(str(body.get("id", "")))
        elif path == "/api/tasks/extract":
            return self._extract_tasks(body)
        elif path == "/api/reminders":
            p.set_reminders(bool(body.get("enabled")), str(body.get("time", "")))
        elif path == "/api/blocklist":
            p.set_blocklist(body.get("items", []))
        elif path == "/api/focus/start":
            try:
                p.start_focus(int(body.get("minutes", 25)), time.time())
            except (TypeError, ValueError):
                return self._json({"error": "Ungültige Minuten."}, 400)
        elif path == "/api/focus/stop":
            p.stop_focus()
        return self._json(app.planner_state())

    def _extract_tasks(self, body: dict):
        app = self.app
        strip = lambda x: re.sub(r"^data:image/[a-z+]+;base64,", "", str(x))
        images = [strip(x) for x in (body.get("images") or [body.get("image", "")])][:4]
        images = [x for x in images if len(x) >= 100]
        if not images:
            return self._json({"error": "Kein Bild empfangen."}, 400)
        found, seen = [], set()
        try:
            for img in images:
                raw = core.extract_tasks_text(app.client, app.config["vision_model"], img,
                                              date.today().isoformat())
                for t in pl.parse_tasks_json(raw):
                    key = (t["title"].lower(), t["due"])
                    if key not in seen:       # Bänder überlappen → Duplikate
                        seen.add(key)
                        found.append(t)
        except core.TutorError as exc:
            return self._json({"error": str(exc)}, 400)
        return self._json({"candidates": found})

    def _stream(self, text: str):
        app, session = self.app, self.app.session
        self._sse_start()
        gen = session.stream_turn(text)
        try:
            for piece in gen:
                if not self._sse({"t": piece}):
                    break               # Client weg → Teilantwort bleibt im Verlauf
            else:
                self._sse({"done": True, "state": app.state()})
        except core.TutorError as exc:
            self._sse({"error": str(exc), "state": app.state()})
        finally:
            gen.close()

    def _page(self, body: dict):
        app, session = self.app, self.app.session
        strip = lambda x: re.sub(r"^data:image/[a-z+]+;base64,", "", str(x))
        images = [strip(x) for x in (body.get("images") or [body.get("image", "")])][:4]
        images = [x for x in images if len(x) >= 100]
        if not images:
            return self._json({"error": "Kein Bild empfangen."}, 400)
        focus = str(body.get("focus", ""))[:200]
        try:
            parts = [core.describe_image(app.client, app.config["vision_model"], img, focus)
                     for img in images]
        except core.TutorError as exc:
            return self._json({"error": str(exc)}, 400)
        summary = "\n".join(p for p in parts if p)
        if not summary:
            return self._json({"error": "Auf der Seite konnte ich nichts lesen."}, 422)
        note = f"Bereich: {summary}" if focus == "stelle" else summary
        session.task.page_notes.append(note[:2500])
        return self._json({"summary": summary, "unsure": summary.count("[?"),
                           "state": app.state()})

    def _page_text(self, body: dict):
        """Vom Lernenden korrigierte Abschrift ersetzt die automatische."""
        text = str(body.get("text", "")).strip()[:2500]
        notes = self.app.session.task.page_notes
        notes.clear()
        if text:
            notes.append(text)
        return self._json({"state": self.app.state()})


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def make_server(config: dict, client, prompt_template: str, host: str, port: int,
                token: str | None, planner: pl.Planner | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,),
                   {"app": App(config, client, prompt_template, token, planner)})
    return ThreadingHTTPServer((host, port), handler)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tutor-web", description="Tutor-Weboberfläche")
    p.add_argument("--config", type=Path, default=core.BASE_DIR / "config.yaml")
    p.add_argument("--host", help="0.0.0.0 = im WLAN erreichbar (iPad)")
    p.add_argument("--port", type=int)
    p.add_argument("-m", "--modell", dest="model")
    p.add_argument("--vision-modell", dest="vision_model")
    p.add_argument("-f", "--fach", dest="subject")
    p.add_argument("--kein-token", action="store_true",
                   help="Zugangs-Token auch bei Netzwerkzugriff abschalten")
    args = p.parse_args(argv)

    config = core.load_config(args.config)
    for key in ("model", "vision_model", "subject"):
        if getattr(args, key) is not None:
            config[key] = getattr(args, key)
    host = args.host or config["web"]["host"]
    port = args.port or config["web"]["port"]

    template = (core.BASE_DIR / "prompts" / "tutor.md").read_text(encoding="utf-8")
    client = core.make_client(config["host"])
    try:
        core.check_model(client, config["model"])
    except core.TutorError as exc:
        core.error(str(exc))
        return 1
    try:
        core.check_model(client, config["vision_model"])
    except core.TutorError as exc:
        core.info("Hinweis: Seiten lesen ist ohne Vision-Modell nicht möglich.\n" + str(exc))

    token = None if (host in LOOPBACK or args.kein_token) else secrets.token_urlsafe(12)
    server = make_server(config, client, template, host, port, token)
    shown = lan_ip() if host in ("0.0.0.0", "::") else host
    url = f"http://{shown}:{port}/" + (f"?t={token}" if token else "")
    print(f"Tutor-Oberfläche: {url}")
    if token:
        core.info("Auf dem iPad in Safari öffnen → Teilen → „Zum Home-Bildschirm“.\n"
                  "Die URL enthält den Zugangs-Token; nicht weitergeben.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if config["sessions"]["autosave"]:
            server.RequestHandlerClass.app.session.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
