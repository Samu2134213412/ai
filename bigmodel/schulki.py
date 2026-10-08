#!/usr/bin/env python3
"""SchulKI - a shared AI for a school network, with no central server.

Every device that runs this program joins the pool. A device that is strong
enough runs a complete model on its own Ollama and answers questions from the
whole pool. Every device also serves the chat page, so phones, tablets and
Chromebooks use it in the browser. Questions go to the device that can
answer best right now; if a device disappears (laptop closed), the others
carry on.

Fairness: whoever contributes compute gets served first. Questions from a
device that only uses the pool wait while contributors are queued.

    python schulki.py --key KLASSENPASSWORT              # join, contribute if possible
    python schulki.py --key ... --no-contribute          # only use the pool
    python schulki.py --key ... --peer 10.0.0.12         # if the network blocks discovery

Devices find each other by UDP broadcast and then share their peer lists, so a
single known address (--peer) is enough when broadcast is blocked.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import hmac
import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ollama_max import CRITIQUE, GB, REVISION, SYSTEM, Ollama, confirm, detect_ram_gb, detect_vram_gb

HTTP_PORT = 47801
BEACON_PORT = 47800
VERSION = 1

# Best first. size = download GB. A device runs the best one that fits
# without making the device unusable for its owner.
POOL_MODELS: list[dict] = [
    {"tag": "qwen3.6:27b", "size": 17},
    {"tag": "qwen3:14b", "size": 9.3},
    {"tag": "qwen3:8b", "size": 5.2},
    {"tag": "qwen3:4b", "size": 2.5},
    {"tag": "qwen3:1.7b", "size": 1.4},
]


def pool_rank(tag: str | None) -> int:
    for i, m in enumerate(POOL_MODELS):
        if m["tag"] == tag:
            return i
    return len(POOL_MODELS)


def pick_pool_model(vram: float | None, ram: float | None) -> tuple[str | None, str]:
    """Best model a device can run while staying usable. Returns (tag, where)."""
    for m in POOL_MODELS:
        if vram and m["size"] + 2.5 <= vram:
            return m["tag"], "GPU"
    for m in POOL_MODELS:
        # CPU only: at most 40% of the RAM (the owner still needs the device) and
        # at most 8B, bigger models are too slow on a CPU to help the pool.
        if ram and m["size"] * 1.2 + 1 <= ram * 0.4 and m["size"] <= 5.2:
            return m["tag"], "CPU"
    return None, ""


# ------------------------------------------------------------------- helpers

def token_for(key: str) -> str:
    return hashlib.sha256(("schulki:" + key).encode()).hexdigest()


def beacon_sign(key: str, payload: bytes) -> str:
    return hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class WorkQueue:
    """One generation at a time; lower priority number goes first, FIFO within."""

    def __init__(self, limit: int = 8):
        self.cv = threading.Condition()
        self.heap: list[tuple[int, int]] = []
        self.counter = 0
        self.busy = False
        self.limit = limit

    def length(self) -> int:
        with self.cv:
            return len(self.heap) + int(self.busy)

    def acquire(self, prio: int) -> bool:
        with self.cv:
            if len(self.heap) >= self.limit:
                return False
            ticket = (prio, self.counter)
            self.counter += 1
            heapq.heappush(self.heap, ticket)
            while self.busy or self.heap[0] != ticket:
                self.cv.wait()
            heapq.heappop(self.heap)
            self.busy = True
            return True

    def release(self) -> None:
        with self.cv:
            self.busy = False
            self.cv.notify_all()


# ---------------------------------------------------------------------- node

class Node:
    def __init__(self, key: str, name: str, port: int, model: str | None,
                 ollama: Ollama | None, advertise: str | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.key, self.token = key, token_for(key)
        self.name, self.port, self.model, self.ollama = name, port, model, ollama
        self.addr = f"{advertise or local_ip()}:{port}"
        self.queue = WorkQueue()
        self.peers: dict[str, dict] = {}     # addr -> last status
        self.fails: dict[str, int] = {}
        self.manual: set[str] = set()
        self.lock = threading.Lock()
        self.think = None
        if ollama and model:
            self.think = True if "thinking" in ollama.capabilities(model) else None
        self.server: ThreadingHTTPServer | None = None

    @property
    def contributing(self) -> bool:
        return bool(self.model and self.ollama)

    def status(self) -> dict:
        with self.lock:
            peers = [a for a, p in self.peers.items() if p]
        return {"v": VERSION, "id": self.id, "name": self.name, "addr": self.addr,
                "model": self.model if self.contributing else None,
                "rank": pool_rank(self.model) if self.contributing else None,
                "queue": self.queue.length(), "contributing": self.contributing,
                "peers": peers}

    # ---- membership

    def add_peer(self, addr: str, manual: bool = False) -> None:
        if addr == self.addr:
            return
        with self.lock:
            self.peers.setdefault(addr, {})
            if manual:
                self.manual.add(addr)

    def poll_peers(self) -> None:
        with self.lock:
            addrs = list(self.peers)
        for addr in addrs:
            try:
                req = urllib.request.Request(f"http://{addr}/api/status", headers={"X-Pool-Token": self.token})
                with urllib.request.urlopen(req, timeout=3) as r:
                    st = json.load(r)
                if st.get("id") == self.id:
                    with self.lock:
                        self.peers.pop(addr, None)
                    continue
                with self.lock:
                    self.peers[addr] = st
                    self.fails[addr] = 0
                for other in st.get("peers", []):
                    self.add_peer(other)
            except (OSError, ValueError):
                with self.lock:
                    self.fails[addr] = self.fails.get(addr, 0) + 1
                    self.peers[addr] = {}
                    if self.fails[addr] >= 3 and addr not in self.manual:
                        self.peers.pop(addr, None)
                        self.fails.pop(addr, None)

    def alive_peers(self) -> list[dict]:
        with self.lock:
            return [p for p in self.peers.values() if p]

    def is_contributor_ip(self, ip: str) -> bool:
        if ip in ("127.0.0.1", "::1") or ip == self.addr.split(":")[0]:
            return self.contributing
        return any(p.get("contributing") and p["addr"].split(":")[0] == ip for p in self.alive_peers())

    def candidates(self, thorough: bool) -> list[dict]:
        nodes = [p for p in self.alive_peers() if p.get("contributing")]
        if self.contributing:
            nodes.append(self.status())
        # Quick questions: idle devices first. Thorough ones: best model first.
        key = (lambda n: (n["rank"], n["queue"])) if thorough else (lambda n: (n["queue"], n["rank"]))
        return sorted(nodes, key=key)

    # ---- generation on this device

    def generate(self, messages: list[dict], thorough: bool, emit) -> None:
        options = {"num_ctx": 8192, "temperature": 0.6, "top_p": 0.95}
        msgs = [{"role": "system", "content": SYSTEM}] + messages
        if not thorough:
            self.ollama.chat(self.model, msgs, options, None if self.think is None else False,
                             on_token=lambda t: emit({"t": t}))
            return
        question = messages[-1]["content"]
        emit({"stage": "Entwurf"})
        draft = self.ollama.chat(self.model, msgs, options, self.think)
        emit({"stage": "Kritik"})
        critique = self.ollama.chat(self.model, [{"role": "system", "content": SYSTEM},
                                                 {"role": "user", "content": CRITIQUE.format(q=question, a=draft)}],
                                    {**options, "temperature": 0.3}, self.think)
        emit({"stage": "Endfassung"})
        self.ollama.chat(self.model, [{"role": "system", "content": SYSTEM},
                                      {"role": "user", "content": REVISION.format(q=question, a=draft, c=critique)}],
                         {**options, "temperature": 0.3}, self.think, on_token=lambda t: emit({"t": t}))

    # ---- routing

    def route(self, messages: list[dict], thorough: bool, prio: int, emit) -> None:
        tried = 0
        for cand in self.candidates(thorough):
            tried += 1
            started = False

            def relay(ev):
                nonlocal started
                started = True
                emit(ev)

            try:
                emit({"node": cand["name"], "model": cand["model"]})
                if cand["id"] == self.id:
                    if not self.queue.acquire(prio):
                        continue
                    try:
                        self.generate(messages, thorough, relay)
                    finally:
                        self.queue.release()
                else:
                    self.forward(cand["addr"], messages, thorough, prio, relay)
                emit({"done": True})
                return
            except (OSError, RuntimeError, ValueError) as e:
                if started:
                    emit({"error": f"{cand['name']} ist ausgefallen: {e}"})
                    return
                continue
        emit({"error": "Gerade kann kein Gerät antworten." if tried else
              "Kein Gerät im Pool rechnet mit. Mindestens ein PC muss SchulKI mit Modell laufen lassen."})

    def forward(self, addr: str, messages: list[dict], thorough: bool, prio: int, emit) -> None:
        body = json.dumps({"messages": messages, "thorough": thorough, "prio": prio}).encode()
        req = urllib.request.Request(f"http://{addr}/api/work", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "X-Pool-Token": self.token})
        try:
            resp = urllib.request.urlopen(req, timeout=None)
        except urllib.error.HTTPError as e:
            raise OSError(f"HTTP {e.code}") from e
        with resp:
            for raw in resp:
                ev = json.loads(raw)
                if "error" in ev:
                    raise RuntimeError(ev["error"])
                if ev.get("done"):
                    return
                emit(ev)
        raise OSError("Verbindung abgebrochen")

    # ---- background threads

    def start(self, broadcast: bool = True) -> None:
        handler = type("H", (Handler,), {"node": self})
        self.server = ThreadingHTTPServer(("0.0.0.0", self.port), handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self._poll_loop, daemon=True).start()
        if broadcast:
            threading.Thread(target=self._beacon_send, daemon=True).start()
            threading.Thread(target=self._beacon_listen, daemon=True).start()

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    def _poll_loop(self) -> None:
        while True:
            self.poll_peers()
            time.sleep(5)

    def _beacon_send(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = json.dumps({"addr": self.addr, "id": self.id}).encode()
        msg = json.dumps({"p": payload.decode(), "sig": beacon_sign(self.key, payload)}).encode()
        while True:
            try:
                s.sendto(msg, ("255.255.255.255", BEACON_PORT))
            except OSError:
                pass
            time.sleep(3)

    def _beacon_listen(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", BEACON_PORT))
        except OSError:
            return  # another SchulKI on this device already listens
        while True:
            try:
                data, _ = s.recvfrom(4096)
                msg = json.loads(data)
                payload = msg["p"].encode()
                if hmac.compare_digest(beacon_sign(self.key, payload), msg["sig"]):
                    info = json.loads(payload)
                    if info["id"] != self.id:
                        self.add_peer(info["addr"])
            except (OSError, ValueError, KeyError):
                continue


# --------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    node: Node
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _authed(self) -> bool:
        return hmac.compare_digest(self.headers.get("X-Pool-Token", ""), self.node.token)

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self, fn) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(ev):
            self.wfile.write((json.dumps(ev) + "\n").encode())
            self.wfile.flush()

        try:
            fn(emit)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if n > 1_000_000:
            raise ValueError("zu groß")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            if not self._authed():
                return self._json(401, {"error": "Falsches Passwort"})
            st = self.node.status()
            st["pool"] = self.node.alive_peers()
            self._json(200, st)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            return self._json(401, {"error": "Falsches Passwort"})
        try:
            req = self._body()
            messages = [{"role": m["role"], "content": str(m["content"])} for m in req["messages"]
                        if m.get("role") in ("user", "assistant")][-20:]
            if not messages or messages[-1]["role"] != "user":
                raise ValueError("letzte Nachricht muss vom Nutzer sein")
        except (ValueError, KeyError, TypeError) as e:
            return self._json(400, {"error": str(e)})
        thorough = bool(req.get("thorough"))

        if self.path == "/api/chat":
            prio = 0 if self.node.is_contributor_ip(self.client_address[0]) else 1
            self._stream(lambda emit: self.node.route(messages, thorough, prio, emit))
        elif self.path == "/api/work":
            if not self.node.contributing:
                return self._json(503, {"error": "rechnet nicht mit"})
            prio = 0 if req.get("prio") == 0 else 1
            if not self.node.queue.acquire(prio):
                return self._json(503, {"error": "Warteschlange voll"})

            def work(emit):
                try:
                    self.node.generate(messages, thorough, emit)
                    emit({"done": True})
                except (OSError, RuntimeError) as e:
                    emit({"error": str(e)})
                finally:
                    self.node.queue.release()
            self._stream(work)
        else:
            self._json(404, {"error": "not found"})


PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SchulKI</title>
<style>
:root{--bg:#f6f7f9;--fg:#1b1f24;--muted:#667;--card:#fff;--line:#dde1e6;--accent:#2563eb;--me:#e8efff}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--fg:#e8eaed;--muted:#99a;--card:#1b2026;--line:#2c333b;--accent:#6b9bff;--me:#1d2a44}}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
header{display:flex;gap:12px;align-items:center;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--card)}
header b{font-size:18px}#pool{color:var(--muted);font-size:13px;margin-left:auto;text-align:right}
main{max-width:820px;margin:0 auto;padding:16px 16px 140px}
.msg{white-space:pre-wrap;padding:10px 14px;border-radius:12px;margin:10px 0;background:var(--card);border:1px solid var(--line)}
.me{background:var(--me)}.meta{color:var(--muted);font-size:12px;margin-bottom:4px}
form{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);padding:10px 16px}
.row{display:flex;gap:8px;max-width:820px;margin:0 auto}textarea{flex:1;font:inherit;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg);resize:none}
button{font:inherit;padding:8px 16px;border:0;border-radius:8px;background:var(--accent);color:#fff}
label{font-size:13px;color:var(--muted)}.opts{max-width:820px;margin:0 auto 6px;display:flex;gap:16px}
#login{max-width:420px;margin:15vh auto;padding:16px}#login input{width:100%;font:inherit;padding:8px;margin:8px 0;border-radius:8px;border:1px solid var(--line)}
</style></head><body>
<div id="login" hidden><h2>SchulKI</h2><p>Passwort des Pools (bekommst du von der Lehrkraft):</p>
<input id="pw" type="password" autocomplete="current-password"><button id="go">Los</button><p id="lerr"></p></div>
<div id="app" hidden><header><b>SchulKI</b><span id="pool">verbinde …</span></header>
<main id="log"></main>
<form id="f"><div class="opts"><label><input type="checkbox" id="th"> gründlich (langsamer, mit Selbstkontrolle)</label>
<label><a href="#" id="new">neues Gespräch</a></label></div>
<div class="row"><textarea id="q" rows="2" placeholder="Frage stellen …"></textarea><button>Senden</button></div></form></div>
<script>
const $=id=>document.getElementById(id);let token=null,history=[];
function store(k,v){try{v===undefined?null:localStorage.setItem(k,v);return localStorage.getItem(k)}catch(e){return null}}
async function sha(s){if(crypto.subtle){const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));return[...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join('')}return sha256(s)}
function sha256(m){/* fallback for http:// pages without crypto.subtle */const K=[1116352408,1899447441,3049323471,3921009573,961987163,1508970993,2453635748,2870763221,3624381080,310598401,607225278,1426881987,1925078388,2162078206,2614888103,3248222580,3835390401,4022224774,264347078,604807628,770255983,1249150122,1555081692,1996064986,2554220882,2821834349,2952996808,3210313671,3336571891,3584528711,113926993,338241895,666307205,773529912,1294757372,1396182291,1695183700,1986661051,2177026350,2456956037,2730485921,2820302411,3259730800,3345764771,3516065817,3600352804,4094571909,275423344,430227734,506948616,659060556,883997877,958139571,1322822218,1537002063,1747873779,1955562222,2024104815,2227730452,2361852424,2428436474,2756734187,3204031479,3329325298];
const b=[...new TextEncoder().encode(m)],l=b.length*8;b.push(128);while(b.length%64!=56)b.push(0);for(let i=7;i>=0;i--)b.push(Math.floor(l/2**(8*i))&255);
let H=[1779033703,3144134277,1013904242,2773480762,1359893119,2600822924,528734635,1541459225];const r=(x,n)=>(x>>>n)|(x<<(32-n));
for(let o=0;o<b.length;o+=64){const w=[];for(let i=0;i<16;i++)w[i]=(b[o+4*i]<<24)|(b[o+4*i+1]<<16)|(b[o+4*i+2]<<8)|b[o+4*i+3];
for(let i=16;i<64;i++){const s0=r(w[i-15],7)^r(w[i-15],18)^(w[i-15]>>>3),s1=r(w[i-2],17)^r(w[i-2],19)^(w[i-2]>>>10);w[i]=(w[i-16]+s0+w[i-7]+s1)|0}
let[a,c,d,e,f,g,h,k]=H;for(let i=0;i<64;i++){const S1=r(f,6)^r(f,11)^r(f,25),ch=(f&g)^(~f&h),t1=(k+S1+ch+K[i]+w[i])|0,S0=r(a,2)^r(a,13)^r(a,22),mj=(a&c)^(a&d)^(c&d),t2=(S0+mj)|0;
k=h;h=g;g=f;f=(e+t1)|0;e=d;d=c;c=a;a=(t1+t2)|0}H=H.map((x,i)=>(x+[a,c,d,e,f,g,h,k][i])|0)}return H.map(x=>(x>>>0).toString(16).padStart(8,'0')).join('')}
async function login(pw){token=await sha('schulki:'+pw);const r=await fetch('/api/status',{headers:{'X-Pool-Token':token}});
if(r.status==401){$('lerr').textContent='Falsches Passwort.';$('login').hidden=false;$('app').hidden=true;return}
store('schulki_pw',pw);$('login').hidden=true;$('app').hidden=false;refresh();setInterval(refresh,5000)}
async function refresh(){try{const s=await(await fetch('/api/status',{headers:{'X-Pool-Token':token}})).json();
const all=[s,...s.pool].filter(n=>n.contributing);$('pool').textContent=all.length?all.length+' Gerät(e) rechnen: '+all.map(n=>n.name+(n.queue?' ('+n.queue+' in Arbeit)':'')).join(', '):'Kein Gerät rechnet mit'}catch(e){$('pool').textContent='Verbindung verloren'}}
function add(cls,text,meta){const d=document.createElement('div');d.className='msg '+cls;if(meta){const m=document.createElement('div');m.className='meta';m.textContent=meta;d.appendChild(m)}
const t=document.createElement('div');t.textContent=text;d.appendChild(t);$('log').appendChild(d);d.scrollIntoView();return[t,d]}
$('go').onclick=()=>login($('pw').value);$('pw').onkeydown=e=>{if(e.key=='Enter')login($('pw').value)};
$('new').onclick=e=>{e.preventDefault();history=[];$('log').innerHTML=''};
$('q').onkeydown=e=>{if(e.key=='Enter'&&!e.shiftKey){e.preventDefault();$('f').requestSubmit()}};
$('f').onsubmit=async e=>{e.preventDefault();const q=$('q').value.trim();if(!q)return;$('q').value='';add('me',q);history.push({role:'user',content:q});
const[t,d]=add('', '…','wartet auf ein freies Gerät');let text='';const meta=d.firstChild;
try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Pool-Token':token},body:JSON.stringify({messages:history,thorough:$('th').checked})});
const rd=r.body.getReader(),dec=new TextDecoder();let buf='';for(;;){const{value,done}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
while((i=buf.indexOf('\\n'))>=0){const ev=JSON.parse(buf.slice(0,i));buf=buf.slice(i+1);
if(ev.node)meta.textContent=ev.node+' · '+ev.model;if(ev.stage)t.textContent='… '+ev.stage;if(ev.t){text+=ev.t;t.textContent=text}if(ev.error){t.textContent=(text?text+'\\n\\n':'')+'⚠ '+ev.error}}}
if(text)history.push({role:'assistant',content:text});else history.pop()}catch(err){t.textContent='⚠ '+err}};
const saved=store('schulki_pw');if(saved)login(saved);else $('login').hidden=false;
</script></body></html>
"""


# ---------------------------------------------------------------------- main

def config_path() -> Path:
    return Path.home() / ".schulki.json"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="SchulKI: geteilte KI im Schulnetz, ohne Server.")
    ap.add_argument("--key", default=os.environ.get("SCHULKI_KEY"), help="Pool-Passwort (alle Geräte gleich)")
    ap.add_argument("--name", default=socket.gethostname(), help="Anzeigename dieses Geräts")
    ap.add_argument("--port", type=int, default=HTTP_PORT)
    ap.add_argument("--peer", action="append", default=[], help="Adresse eines anderen Geräts (IP oder IP:Port)")
    ap.add_argument("--no-contribute", action="store_true", help="Nur nutzen, nicht mitrechnen")
    ap.add_argument("--model", help="Modell erzwingen")
    ap.add_argument("--advertise", help="Eigene IP, wie andere Geräte sie erreichen")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ap.add_argument("--yes", action="store_true", help="Modell ohne Rückfrage herunterladen")
    args = ap.parse_args(argv)

    cfg = {}
    try:
        cfg = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    key = args.key or cfg.get("key") or input("Pool-Passwort (für alle Geräte gleich): ").strip()
    if len(key) < 6:
        sys.exit("Das Passwort muss mindestens 6 Zeichen haben.")
    peers = set(args.peer) | set(cfg.get("peers", []))
    try:
        config_path().write_text(json.dumps({"key": key, "peers": sorted(peers)}), encoding="utf-8")
    except OSError:
        pass

    model, ollama = None, None
    if not args.no_contribute:
        vram, ram = detect_vram_gb(), detect_ram_gb()
        model, where = (args.model, "vorgegeben") if args.model else pick_pool_model(vram, ram)
        host = args.host if args.host.startswith("http") else "http://" + args.host
        if model is None:
            print(f"Dieses Gerät ist zu schwach zum Mitrechnen (RAM {ram or 0:.0f} GB) - es nutzt den Pool nur.")
        elif not shutil.which("ollama") and not Ollama(host).alive():
            print("Ollama ist nicht installiert - dieses Gerät nutzt den Pool nur. "
                  "Zum Mitrechnen: https://ollama.com/download")
            model = None
        else:
            ollama = Ollama(host)
            ollama.ensure_running()
            if model not in ollama.installed():
                if not confirm(f"Zum Mitrechnen wird {model} gebraucht. Jetzt herunterladen?", args.yes):
                    print("Nicht heruntergeladen - dieses Gerät nutzt den Pool nur.")
                    model, ollama = None, None
                else:
                    ollama.pull(model)
            if model:
                print(f"Rechnet mit: {model} ({where})")

    node = Node(key, args.name, args.port, model, ollama, args.advertise)
    for p in peers:
        node.add_peer(p if ":" in p else f"{p}:{HTTP_PORT}", manual=True)
    try:
        node.start()
    except OSError as e:
        sys.exit(f"Port {args.port} ist belegt: {e}")

    print(f"\nSchulKI läuft. Im Browser öffnen (auch auf Handys im selben WLAN):\n  http://{node.addr}\n")
    print("Andere Geräte finden sich automatisch. Falls nicht (manche Schul-WLANs blockieren das):")
    print(f"  dort starten mit  --peer {node.addr}\n")
    print("Beenden mit Strg+C.")
    try:
        last = None
        while True:
            time.sleep(5)
            n = [p for p in node.alive_peers()]
            line = f"{len(n)} weitere(s) Gerät(e) im Pool, {sum(1 for p in n if p.get('contributing'))} rechnen mit; " \
                   f"Warteschlange hier: {node.queue.length()}"
            if line != last:
                print(line)
                last = line
    except KeyboardInterrupt:
        node.stop()
        print("\nBeendet.")


if __name__ == "__main__":
    main()
