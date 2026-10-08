#!/usr/bin/env python3
"""PC Remote - control this PC from your phone's browser.

Run:  python server.py        then open the printed URL on your phone.
Auth: a random token is stored in ~/.pc-remote-token and required for every
      request. Use only on a trusted network (home Wi-Fi / Tailscale), never
      port-forward it to the internet.
"""
import argparse
import hmac
import io
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
TOKEN_FILE = Path.home() / ".pc-remote-token"
MAX_BODY = 64 * 1024
MOUSE_BUTTONS = {"left", "right", "middle"}
MEDIA_KEYS = {
    "play_pause": "media_play_pause", "next": "media_next",
    "prev": "media_previous", "vol_up": "media_volume_up",
    "vol_down": "media_volume_down", "mute": "media_volume_mute",
}
POWER_CMDS = {
    "win32": {
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        "shutdown": ["shutdown", "/s", "/t", "30"],
        "restart": ["shutdown", "/r", "/t", "30"],
        "cancel": ["shutdown", "/a"],
    },
    "linux": {
        "lock": ["loginctl", "lock-session"],
        "sleep": ["systemctl", "suspend"],
        "shutdown": ["shutdown", "-h", "+1"],
        "restart": ["shutdown", "-r", "+1"],
        "cancel": ["shutdown", "-c"],
    },
    "darwin": {
        "lock": ["pmset", "displaysleepnow"],
        "sleep": ["pmset", "sleepnow"],
        "shutdown": ["shutdown", "-h", "+1"],
        "restart": ["shutdown", "-r", "+1"],
        "cancel": ["killall", "shutdown"],
    },
}


class Backend:
    """Talks to the real OS. Tests replace this with a fake."""

    def __init__(self):
        if sys.platform == "win32":  # make pynput + mss use the same physical pixels
            import ctypes
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        from pynput.keyboard import Controller as Kb, Key
        from pynput.mouse import Button, Controller as Ms
        self.kb, self.ms, self.Key, self.Button = Kb(), Ms(), Key, Button

    def _key(self, name):
        if len(name) == 1:
            return name
        key = getattr(self.Key, name, None)
        if key is None:
            raise ValueError(f"unknown key: {name}")
        return key

    def move(self, dx, dy):
        self.ms.move(int(dx), int(dy))

    def monitor_count(self):
        import mss
        with mss.mss() as s:
            return len(s.monitors) - 1

    def move_to(self, fx, fy, mon=0):
        import mss
        with mss.mss() as s:
            m = s.monitors[1 + min(max(int(mon), 0), len(s.monitors) - 2)]
        self.ms.position = (m["left"] + int(fx * (m["width"] - 1)),
                            m["top"] + int(fy * (m["height"] - 1)))

    def click(self, button, count):
        self.ms.click(getattr(self.Button, button), count)

    def press(self, button, down):
        b = getattr(self.Button, button)
        (self.ms.press if down else self.ms.release)(b)

    def scroll(self, dx, dy):
        self.ms.scroll(int(dx), int(dy))

    def type(self, text):
        self.kb.type(text)

    def key(self, name):
        self.kb.tap(self._key(name))

    def hotkey(self, names):
        keys = [self._key(n) for n in names]
        for k in keys:
            self.kb.press(k)
        for k in reversed(keys):
            self.kb.release(k)

    def media(self, name):
        self.kb.tap(getattr(self.Key, MEDIA_KEYS[name]))

    def screenshot(self, width, quality, mon=0):
        import mss
        from PIL import Image
        with mss.mss() as s:
            raw = s.grab(s.monitors[1 + min(max(int(mon), 0), len(s.monitors) - 2)])
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        if img.width > width:
            img = img.resize((width, round(img.height * width / img.width)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()

    def power(self, action):
        cmd = POWER_CMDS.get(sys.platform if sys.platform in POWER_CMDS else "linux")[action]
        subprocess.Popen(cmd)

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def run(self, cmd):
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return (p.stdout + p.stderr)[-4000:]


def num(d, k, lo=-5000, hi=5000):
    v = float(d.get(k, 0))
    if not lo <= v <= hi:
        raise ValueError(f"{k} out of range")
    return v


def dispatch(be, action, d, allow_exec=False):
    """Run one action. Raises ValueError on bad input."""
    if action == "move":
        be.move(num(d, "dx"), num(d, "dy"))
    elif action == "move_to":
        be.move_to(num(d, "x", 0, 1), num(d, "y", 0, 1), int(d.get("mon", 0)))
    elif action == "click":
        btn = d.get("button", "left")
        if btn not in MOUSE_BUTTONS:
            raise ValueError("bad button")
        be.click(btn, 2 if d.get("double") else 1)
    elif action == "press":
        if d.get("button", "left") not in MOUSE_BUTTONS:
            raise ValueError("bad button")
        be.press(d.get("button", "left"), bool(d.get("down")))
    elif action == "scroll":
        be.scroll(num(d, "dx", -100, 100), num(d, "dy", -100, 100))
    elif action == "type":
        text = str(d.get("text", ""))
        if len(text) > 2000:
            raise ValueError("text too long")
        be.type(text)
    elif action == "key":
        be.key(str(d.get("key", "")))
    elif action == "hotkey":
        keys = d.get("keys")
        if not isinstance(keys, list) or not 1 <= len(keys) <= 4:
            raise ValueError("keys must be a list of 1-4")
        be.hotkey([str(k) for k in keys])
    elif action == "media":
        if d.get("name") not in MEDIA_KEYS:
            raise ValueError("bad media key")
        be.media(d["name"])
    elif action == "power":
        if d.get("name") not in POWER_CMDS["linux"]:
            raise ValueError("bad power action")
        be.power(d["name"])
    elif action == "open_url":
        url = str(d.get("url", ""))
        if not url.startswith(("http://", "https://")):
            raise ValueError("only http(s) URLs")
        be.open_url(url)
    elif action == "run":
        if not allow_exec:
            raise PermissionError("shell commands disabled (start with --allow-exec)")
        return {"output": be.run(str(d.get("cmd", "")))}
    else:
        raise ValueError(f"unknown action: {action}")
    return {}


def load_token():
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    tok = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(tok)
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    return tok


def make_handler(be, token, allow_exec):
    fails = []
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authed(self):
            now = time.time()
            fails[:] = [t for t in fails if now - t < 60]
            if len(fails) >= 20:  # global lockout: tunnel hides client IPs
                self._send(429, {"error": "too many attempts"})
                return False
            got = self.headers.get("X-Token", "")
            ok = hmac.compare_digest(got.encode(), token.encode())
            if not ok:
                fails.append(now)
                time.sleep(0.5)  # slow down guessing
                self._send(401, {"error": "unauthorized"})
            return ok

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":  # page itself holds no secrets
                return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/favicon.ico":
                return self._send(404, b"", "text/plain")
            if not self._authed():
                return
            if u.path == "/api/screen":
                q = parse_qs(u.query)
                w = min(max(int(q.get("w", ["800"])[0]), 200), 1920)
                try:
                    mon = int(q.get("mon", ["0"])[0])
                    return self._send(200, be.screenshot(w, 55, mon), "image/jpeg")
                except Exception as e:
                    return self._send(500, {"error": str(e)})
            if u.path == "/api/ping":
                return self._send(200, {"host": socket.gethostname(), "exec": allow_exec,
                                             "monitors": be.monitor_count()})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authed():
                return
            u = urlparse(self.path)
            if not u.path.startswith("/api/"):
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._send(413, {"error": "too large"})
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
                res = dispatch(be, u.path[5:], data, allow_exec)
                self._send(200, {"ok": True, **res})
            except PermissionError as e:
                self._send(403, {"error": str(e)})
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
                self._send(400, {"error": str(e)})
            except Exception as e:
                self._send(500, {"error": str(e)})
    return H


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def start_tunnel(port, token):
    """Public HTTPS URL via Cloudflare quick tunnel (outbound only, no port forwarding)."""
    import shutil
    import threading
    exe = shutil.which("cloudflared")
    if not exe:
        sys.exit("cloudflared fehlt: Windows: 'winget install Cloudflare.cloudflared', dann neues Fenster öffnen.")
    p = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", f"http://127.0.0.1:{port}"],
                         stderr=subprocess.PIPE, text=True)

    def watch():
        shown = False
        print("Tunnel wird aufgebaut … (bis ~20 s)")
        for line in p.stderr:
            if "ERR" in line or "error" in line.lower():
                print("[cloudflared]", line.strip()[:200])
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m and not shown:
                shown = True
                show(f"{m.group(0)}/#{token}", "Öffentliche URL (von überall, HTTPS)")
        if not shown:
            print("Tunnel beendet, keine URL erhalten. Ausgabe oben prüfen / Internetverbindung?")
    threading.Thread(target=watch, daemon=True).start()


def show(url, title):
    print(f"\n{title}:\n\n  {url}\n")
    try:
        import qrcode
        q = qrcode.QRCode(border=1)
        q.add_data(url)
        q.print_ascii(invert=True)
    except ImportError:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--allow-exec", action="store_true", help="enable the shell-command tab")
    ap.add_argument("--tunnel", action="store_true", help="öffentliche HTTPS-URL über Cloudflare Tunnel")
    ap.add_argument("--reset-token", action="store_true")
    a = ap.parse_args()
    if a.reset_token:
        TOKEN_FILE.unlink(missing_ok=True)
    token = load_token()
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(Backend(), token, a.allow_exec))
    show(f"http://{lan_ip()}:{a.port}/#{token}", "PC Remote läuft. Im selben WLAN öffnen")
    if a.tunnel:
        if a.allow_exec:
            print("WARNUNG: --allow-exec zusammen mit --tunnel macht die Shell öffentlich erreichbar!")
        start_tunnel(a.port, token)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
