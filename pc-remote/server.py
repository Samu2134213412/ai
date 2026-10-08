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
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
CONTROL_ACTIONS = {"move", "move_to", "click", "press", "scroll", "type", "key", "hotkey", "media",
                   "key_down", "key_up", "rmove"}
last_control = [0.0]  # time of the last phone input; drives the glowing pointer on the PC
last_input = [0.0]    # any input at all; feeds the stuck-key watchdog
held_keys, held_btns = set(), set()  # keys/buttons the phone is holding down (game mode)
STALE_S = 3.0         # release everything if the phone goes silent this long while holding
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

    def pointer_xy(self):
        return tuple(self.ms.position)

    def monitor_count(self):
        import mss
        with mss.mss() as s:
            return len(s.monitors) - 1

    def pointer(self):
        """(monitor index, x fraction, y fraction) of the real mouse pointer."""
        import mss
        px, py = self.ms.position
        with mss.mss() as s:
            for i, m in enumerate(s.monitors[1:]):
                if m["left"] <= px < m["left"] + m["width"] and m["top"] <= py < m["top"] + m["height"]:
                    return i, (px - m["left"]) / max(m["width"] - 1, 1), (py - m["top"]) / max(m["height"] - 1, 1)
        return None

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

    _cams, _last, _dx_ok, _lock = {}, {}, True, threading.Lock()

    def grab(self, mon=0):
        """Full-resolution PIL frame of a monitor. Uses dxcam (fast, Windows) if installed, else mss."""
        from PIL import Image
        if self._dx_ok:
            try:
                import dxcam
                with self._lock:
                    cam = self._cams.get(mon) or self._cams.setdefault(
                        mon, dxcam.create(output_idx=mon, output_color="RGB"))
                    frame = cam.grab()
                    if frame is None:  # screen unchanged since last grab
                        frame = self._last.get(mon)
                    else:
                        self._last[mon] = frame
                if frame is not None:
                    return Image.fromarray(frame)
            except ImportError:
                self._dx_ok = False
            except Exception:
                self._dx_ok = False  # DXGI refused (RDP, remote session, ...): stay on mss
        import mss
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[1 + min(max(int(mon), 0), len(sct.monitors) - 2)])
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    def screenshot(self, width, quality, mon=0, region=None):
        img = self.grab(mon)
        if region:  # (x0, y0, w) as fractions of the monitor; zoomed view stays sharp
            x0, y0, w = region
            W, H = img.size
            img = img.crop((int(x0 * W), int(y0 * H), max(int(x0 * W) + 1, int((x0 + w) * W)),
                            max(int(y0 * H) + 1, int((y0 + w) * H))))
        return encode_jpeg(img, width, quality)

    def key_down(self, name):
        self.kb.press(self._key(name))

    def key_up(self, name):
        self.kb.release(self._key(name))

    def rel_move(self, dx, dy):
        """Relative mouse movement (what games read as mouse-look)."""
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)  # MOUSEEVENTF_MOVE
        else:
            self.ms.move(int(dx), int(dy))

    def power(self, action):
        cmd = POWER_CMDS.get(sys.platform if sys.platform in POWER_CMDS else "linux")[action]
        subprocess.Popen(cmd)

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def run(self, cmd):
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return (p.stdout + p.stderr)[-4000:]


def encode_jpeg(img, width, quality):
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), reducing_gap=2.0)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def stream_mjpeg(be, write, mon, width, fps, quality, should_stop=lambda: False):
    """Push multipart JPEG frames through write() at up to `fps` until write() raises or should_stop()."""
    step = 1.0 / fps
    due = time.perf_counter()
    while not should_stop():
        frame = encode_jpeg(be.grab(mon), width, quality)
        write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(frame) + frame + b"\r\n")
        due += step
        lag = due - time.perf_counter()
        if lag > 0:
            time.sleep(lag)
        else:
            due = time.perf_counter()  # can't keep up: don't try to catch up


def release_all(be):
    for k in list(held_keys):
        be.key_up(k)
    for b in list(held_btns):
        be.press(b, False)
    held_keys.clear()
    held_btns.clear()


def release_stale(be, now=None, timeout=STALE_S):
    """Watchdog: phone vanished while holding keys (lost signal, closed tab) -> let go of everything."""
    now = time.time() if now is None else now
    if (held_keys or held_btns) and now - last_input[0] > timeout:
        release_all(be)
        return True
    return False


def num(d, k, lo=-5000, hi=5000):
    v = float(d.get(k, 0))
    if not lo <= v <= hi:
        raise ValueError(f"{k} out of range")
    return v


def dispatch(be, action, d, allow_exec=False):
    """Run one action. Raises ValueError on bad input."""
    last_input[0] = time.time()
    if action in CONTROL_ACTIONS and not d.get("quiet"):
        last_control[0] = last_input[0]
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
        btn = d.get("button", "left")
        if btn not in MOUSE_BUTTONS:
            raise ValueError("bad button")
        be.press(btn, bool(d.get("down")))
        (held_btns.add if d.get("down") else held_btns.discard)(btn)
    elif action in ("key_down", "key_up"):
        name = str(d.get("key", ""))
        if not name or len(name) > 12:
            raise ValueError("bad key")
        getattr(be, action)(name)
        (held_keys.add if action == "key_down" else held_keys.discard)(name)
    elif action == "rmove":
        be.rel_move(int(num(d, "dx", -3000, 3000)), int(num(d, "dy", -3000, 3000)))
    elif action == "release_all":
        release_all(be)
    elif action == "noop":
        pass
    elif action == "batch":  # ordered list, one round trip: key down/up must never be reordered
        items = d.get("actions")
        if not isinstance(items, list) or len(items) > 64:
            raise ValueError("actions must be a list of at most 64")
        for it in items:
            if not isinstance(it, dict) or it.get("a") in (None, "batch"):
                raise ValueError("bad batch item")
            dispatch(be, str(it["a"]), it, allow_exec)
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
        protocol_version = "HTTP/1.1"  # keep-alive: no new TCP handshake per input event
        timeout = 30

        def setup(self):
            super().setup()
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        def handle(self):
            try:
                super().handle()
            except (ConnectionError, TimeoutError):
                pass  # phone closed/lost the connection

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", headers=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _authed(self, query_token=""):
            now = time.time()
            fails[:] = [t for t in fails if now - t < 60]
            if len(fails) >= 20:  # global lockout: tunnel hides client IPs
                self._send(429, {"error": "too many attempts"})
                return False
            got = self.headers.get("X-Token", "") or query_token
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
            if u.path == "/api/stream":  # <img> can't send headers, so this one takes ?t=TOKEN
                q = parse_qs(u.query)
                if not self._authed(q.get("t", [""])[0]):
                    return
                return self._stream(q)
            if not self._authed():
                return
            if u.path == "/api/screen":
                q = parse_qs(u.query)
                w = min(max(int(q.get("w", ["800"])[0]), 200), 1920)
                try:
                    mon = int(q.get("mon", ["0"])[0])
                    z = min(max(float(q.get("z", ["1"])[0]), 0.05), 1.0)
                    hdr = {}
                    try:
                        p = be.pointer()
                        if isinstance(p, tuple):
                            hdr["X-Pointer"] = "%d,%.5f,%.5f" % p
                    except Exception:
                        pass
                    if z < 1.0:
                        x0 = min(max(float(q.get("x", ["0"])[0]), 0.0), 1.0 - z)
                        y0 = min(max(float(q.get("y", ["0"])[0]), 0.0), 1.0 - z)
                        return self._send(200, be.screenshot(w, 55, mon, (x0, y0, z)), "image/jpeg", hdr)
                    return self._send(200, be.screenshot(w, 55, mon), "image/jpeg", hdr)
                except Exception as e:
                    return self._send(500, {"error": str(e)})
            if u.path == "/api/ping":
                return self._send(200, {"host": socket.gethostname(), "exec": allow_exec,
                                             "monitors": be.monitor_count()})
            self._send(404, {"error": "not found"})

        def _stream(self, q):
            def num_arg(k, default, lo, hi):
                return min(max(int(float(q.get(k, [default])[0])), lo), hi)
            mon, w, fps, qual = num_arg("mon", 0, 0, 16), num_arg("w", 854, 320, 1920), num_arg("fps", 30, 5, 60), num_arg("q", 55, 20, 90)
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                stream_mjpeg(be, lambda b: (self.wfile.write(b), self.wfile.flush()), mon, w, fps, qual)
            except (OSError, ValueError):
                pass  # phone went away

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                self.close_connection = True
                return self._send(413, {"error": "too large"})
            raw = self.rfile.read(n)  # always consume the body or keep-alive desyncs
            if not self._authed():
                return
            u = urlparse(self.path)
            if not u.path.startswith("/api/"):
                return self._send(404, {"error": "not found"})
            try:
                data = json.loads(raw or b"{}")
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
    ap.add_argument("--no-overlay", action="store_true", help="kein blauer Cursor am PC")
    ap.add_argument("--reset-token", action="store_true")
    a = ap.parse_args()
    if a.reset_token:
        TOKEN_FILE.unlink(missing_ok=True)
    token = load_token()
    be = Backend()
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(be, token, a.allow_exec))
    def watchdog():
        while True:
            time.sleep(0.5)
            try:
                release_stale(be)
            except Exception:
                pass
    threading.Thread(target=watchdog, daemon=True).start()
    if not a.no_overlay:
        from overlay import Overlay
        Overlay(lambda: last_control[0], be.pointer_xy).start()
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
