#!/usr/bin/env python3
"""Wake-on-LAN relay. Run on an always-on device in the same LAN as the PC
(Raspberry Pi, NAS, old laptop). Open its URL on your phone, tap "Anschalten".

  python wake.py --mac AA:BB:CC:DD:EE:FF
"""
import argparse
import hmac
import re
import secrets
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN_FILE = Path.home() / ".pc-remote-wake-token"
PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>PC anschalten</title><body style="background:#111;color:#eee;font:20px system-ui;text-align:center;padding:40px 16px">
<button id=b style="font-size:24px;padding:24px 40px;border-radius:14px;border:0;background:#4f8cff;color:#fff">PC anschalten</button>
<p id=m></p><p><a id=open href="#" style="color:#4f8cff;display:none">PC-Steuerung öffnen</a></p><script>
fetch('/cfg').then(r=>r.json()).then(c=>{if(c.pc_url){open.href=c.pc_url;open.style.display='inline'}});
let t=location.hash.slice(1);if(t){try{localStorage.t=t}catch(e){}history.replaceState(null,'',location.pathname)}else{try{t=localStorage.t||''}catch(e){}}
b.onclick=async()=>{const r=await fetch('/wake',{method:'POST',headers:{'X-Token':t}});m.textContent=r.ok?'Signal gesendet – dauert ~30 s':r.status==401?'Token ungültig':'Fehler'}
</script>"""


def magic_packet(mac):
    h = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(h) != 12:
        raise ValueError("MAC must have 12 hex digits")
    return bytes.fromhex("ff" * 6 + h * 16)


def send(mac, broadcast="255.255.255.255", port=9):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(magic_packet(mac), (broadcast, port))


def make_handler(token, mac, broadcast, sender=send, pc_url=""):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _out(self, code, body, ctype="text/plain"):
            body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self._out(200, PAGE, "text/html; charset=utf-8")
            elif self.path == "/cfg":
                import json
                self._out(200, json.dumps({"pc_url": pc_url}), "application/json")
            else:
                self._out(404, "")

        def do_POST(self):
            if self.path != "/wake":
                return self._out(404, "")
            if not hmac.compare_digest(self.headers.get("X-Token", "").encode(), token.encode()):
                return self._out(401, "unauthorized")
            sender(mac, broadcast)
            self._out(200, "ok")
    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mac", required=True)
    ap.add_argument("--broadcast", default="255.255.255.255")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--pc-url", default="", help="Adresse der PC-Steuerung, wird nach dem Wecken verlinkt")
    a = ap.parse_args()
    magic_packet(a.mac)  # validate early
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text().strip()
    else:
        tok = secrets.token_urlsafe(24)
        TOKEN_FILE.write_text(tok)
        TOKEN_FILE.chmod(0o600)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    print(f"\nWake-Relay läuft. Auf dem Handy öffnen:\n\n  http://{ip}:{a.port}/#{tok}\n")
    ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(tok, a.mac, a.broadcast, pc_url=a.pc_url)).serve_forever()


if __name__ == "__main__":
    main()
