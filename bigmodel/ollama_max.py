#!/usr/bin/env python3
"""ollama_max - run the best Ollama model your machine can hold, for quality.

Speed is not the goal. The program

1. measures GPU VRAM (nvidia-smi), system RAM and free disk space,
2. walks a quality-ranked list of models and picks the best one whose real
   download size (read from the Ollama registry, no download needed) fits in
   VRAM + RAM; Ollama splits the layers between GPU and CPU on its own,
3. pulls it only after you confirm,
4. answers with a multi-stage pipeline: several independent drafts with
   thinking enabled, a synthesis, a harsh self-critique and a final revision.

Standard library only; works on Windows, Linux and macOS.

    python ollama_max.py --check                 # show hardware + choice, change nothing
    python ollama_max.py "Your question"         # one question
    python ollama_max.py                         # interactive
    python ollama_max.py --file prompt.txt --out answer.md
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from stream_backend import LlamaServer, download_llama_server, find_llama_server, is_gguf, ollama_blob, sec_per_token

GB = 1e9

# Ranked best first. Sizes are fallbacks only (download GB at the default
# quantisation); the real size is read from the registry at run time, and a tag
# the registry does not know is skipped. kv_32k is a rough estimate of the KV
# cache in GB for 32K context. Edit freely - the first entry that fits wins.
# total/active are parameters in billions; active < total marks a MoE model,
# which is what makes streaming from disk (--mode stream) practical.
CATALOG: list[dict] = [
    {"tag": "deepseek-v3.1:671b", "size": 404, "kv_32k": 8, "total": 671, "active": 37, "note": "671B MoE (37B aktiv)"},
    {"tag": "qwen3:235b", "size": 142, "kv_32k": 6, "total": 235, "active": 22, "note": "235B MoE (22B aktiv)"},
    {"tag": "gpt-oss:120b", "size": 65, "kv_32k": 3, "total": 117, "active": 5.1, "note": "117B MoE (5B aktiv)"},
    {"tag": "qwen3.6:27b", "size": 17, "kv_32k": 4, "total": 27, "active": 27, "note": "27B dense"},
    {"tag": "qwen3:32b", "size": 20, "kv_32k": 8, "total": 32, "active": 32, "note": "32B dense"},
    {"tag": "gemma3:27b", "size": 17, "kv_32k": 8, "total": 27, "active": 27, "note": "27B dense"},
    {"tag": "gpt-oss:20b", "size": 14, "kv_32k": 2, "total": 21, "active": 3.6, "note": "21B MoE"},
    {"tag": "qwen3:14b", "size": 9, "kv_32k": 5, "total": 14, "active": 14, "note": "14B dense"},
]

REGISTRY = "https://registry.ollama.ai/v2/library"
MANIFEST_ACCEPT = "application/vnd.docker.distribution.manifest.v2+json"


# --------------------------------------------------------------------- hardware

def detect_vram_gb() -> float | None:
    """Total VRAM over all NVIDIA GPUs, or None if nvidia-smi is unavailable."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    mib = [float(x) for x in out.split() if x.strip().replace(".", "", 1).isdigit()]
    return sum(mib) * 1024 * 1024 / GB if mib else None


def detect_ram_gb() -> float | None:
    system = platform.system()
    try:
        if system == "Windows":
            class MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MemStatus()
            stat.dwLength = ctypes.sizeof(MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
            return stat.ullTotalPhys / GB
        if system == "Darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
            return int(out.stdout.strip()) / GB
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024 / GB
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        pass
    return None


def models_dir() -> Path:
    env = os.environ.get("OLLAMA_MODELS")
    return Path(env) if env else Path.home() / ".ollama" / "models"


def free_disk_gb(path: Path) -> float | None:
    p = path
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free / GB
    except OSError:
        return None


# ------------------------------------------------------------------ selection

@dataclass
class Budget:
    vram: float
    ram: float
    reserve: float

    @property
    def total(self) -> float:
        return self.vram + self.ram - self.reserve


def make_budget(vram: float, ram: float, reserve: float | None = None) -> Budget:
    # The OS, Ollama itself and your other programs need RAM too.
    if reserve is None:
        reserve = max(6.0, 0.12 * ram)
    return Budget(vram, ram, reserve)


def required_gb(size_gb: float, kv_32k: float, num_ctx: int) -> float:
    """Weights + runtime buffers + KV cache for num_ctx tokens (estimate)."""
    return size_gb * 1.08 + 2.0 + kv_32k * num_ctx / 32768


@dataclass
class Choice:
    tag: str
    size: float
    need: float
    installed: bool
    note: str
    size_source: str
    spt: float = 0.0  # estimated seconds per token when streaming from disk
    moe: bool = False


def rank(tag: str) -> int:
    for i, e in enumerate(CATALOG):
        if e["tag"] == tag:
            return i
    return len(CATALOG)


def choose(
    budget: Budget, num_ctx: int, disk_free: float | None,
    installed: dict[str, float], size_lookup, log=print,
) -> Choice | None:
    for entry in CATALOG:
        tag = entry["tag"]
        if tag in installed:
            size, src, is_installed = installed[tag], "installiert", True
        else:
            size, src = size_lookup(tag, entry["size"])
            is_installed = False
            if size is None:
                log(f"  - {tag:<22} existiert nicht in der Registry, übersprungen")
                continue
        need = required_gb(size, entry["kv_32k"], num_ctx)
        if need > budget.total:
            log(f"  - {tag:<22} {size:6.0f} GB  braucht ~{need:.0f} GB > {budget.total:.0f} GB verfügbar")
            continue
        if not is_installed and disk_free is not None and size * 1.05 > disk_free:
            log(f"  - {tag:<22} {size:6.0f} GB  passt in den Speicher, aber nur {disk_free:.0f} GB Platte frei")
            continue
        log(f"  + {tag:<22} {size:6.0f} GB  braucht ~{need:.0f} GB von {budget.total:.0f} GB  ({src})")
        return Choice(tag, size, need, is_installed, entry["note"], src)
    return None


def choose_stream(
    budget: Budget, num_ctx: int, disk_free: float | None,
    installed: dict[str, float], size_lookup, disk_gb_s: float, max_spt: float, log=print,
) -> Choice | None:
    """Best model that fits on disk and streams at <= max_spt seconds per token."""
    for entry in CATALOG:
        tag = entry["tag"]
        if tag in installed:
            size, src, is_installed = installed[tag], "installiert", True
        else:
            size, src = size_lookup(tag, entry["size"])
            is_installed = False
            if size is None:
                log(f"  - {tag:<22} existiert nicht in der Registry, übersprungen")
                continue
        if entry["kv_32k"] * num_ctx / 32768 + 3 > budget.vram:
            log(f"  - {tag:<22} Kontext passt nicht in den VRAM")
            continue
        if not is_installed and disk_free is not None and size * 1.02 > disk_free:
            log(f"  - {tag:<22} {size:6.0f} GB  nur {disk_free:.0f} GB Platte frei")
            continue
        spt = sec_per_token(size, entry["total"], entry["active"], budget.total, disk_gb_s)
        if spt > max_spt:
            log(f"  - {tag:<22} {size:6.0f} GB  ca. {spt:.1f} s/Token > Limit {max_spt:g} (--max-spt)")
            continue
        log(f"  + {tag:<22} {size:6.0f} GB  ca. {spt:.1f} s/Token  ({src})")
        return Choice(tag, size, required_gb(size, entry["kv_32k"], num_ctx), is_installed,
                      entry["note"], src, spt, entry["active"] < entry["total"])
    return None


def registry_size_gb(tag: str, fallback: float) -> tuple[float | None, str]:
    """Real download size from the registry manifest; None if the tag is unknown."""
    name, _, version = tag.partition(":")
    url = f"{REGISTRY}/{name}/manifests/{version or 'latest'}"
    req = urllib.request.Request(url, headers={"Accept": MANIFEST_ACCEPT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        return sum(layer["size"] for layer in data.get("layers", [])) / GB, "Registry"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, "unbekannt"
        return fallback, "Schätzung"
    except (OSError, ValueError, KeyError):
        return fallback, "Schätzung"


# --------------------------------------------------------------------- ollama

class Ollama:
    def __init__(self, host: str):
        self.host = host.rstrip("/")

    def _request(self, path: str, body: dict | None = None, timeout: float | None = 30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.host + path, data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        return urllib.request.urlopen(req, timeout=timeout)

    def alive(self) -> bool:
        try:
            with self._request("/api/version", timeout=3):
                return True
        except OSError:
            return False

    def ensure_running(self) -> None:
        if self.alive():
            return
        exe = shutil.which("ollama")
        if not exe:
            sys.exit("Ollama läuft nicht und wurde nicht gefunden. Installieren: https://ollama.com/download")
        print("Ollama läuft nicht - starte 'ollama serve' (Flash-Attention + q8_0 KV-Cache) ...")
        env = dict(os.environ)
        env.setdefault("OLLAMA_FLASH_ATTENTION", "1")
        env.setdefault("OLLAMA_KV_CACHE_TYPE", "q8_0")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0  # type: ignore[attr-defined]
        subprocess.Popen([exe, "serve"], env=env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=flags)
        for _ in range(60):
            time.sleep(1)
            if self.alive():
                return
        sys.exit(f"Ollama antwortet nicht unter {self.host}.")

    def installed(self) -> dict[str, float]:
        with self._request("/api/tags") as resp:
            models = json.load(resp).get("models", [])
        out = {}
        for m in models:
            name = m["name"]
            out[name] = m.get("size", 0) / GB
            if name.endswith(":latest"):
                out[name[: -len(":latest")]] = out[name]
        return out

    def unload_all(self) -> None:
        """Free the VRAM Ollama holds, so llama-server gets all of it."""
        try:
            with self._request("/api/ps") as resp:
                running = json.load(resp).get("models", [])
            for m in running:
                with self._request("/api/generate", {"model": m["name"], "keep_alive": 0}):
                    pass
        except (OSError, ValueError, KeyError):
            pass

    def capabilities(self, model: str) -> list[str]:
        try:
            with self._request("/api/show", {"model": model}) as resp:
                return json.load(resp).get("capabilities", []) or []
        except (OSError, ValueError):
            return []

    def pull(self, model: str) -> None:
        last = ""
        with self._request("/api/pull", {"model": model, "stream": True}, timeout=None) as resp:
            for raw in resp:
                msg = json.loads(raw)
                if "error" in msg:
                    sys.exit(f"\nPull fehlgeschlagen: {msg['error']}")
                status = msg.get("status", "")
                if msg.get("total"):
                    pct = 100 * msg.get("completed", 0) / msg["total"]
                    line = f"{status[:40]:<40} {pct:5.1f}%  von {msg['total'] / GB:.1f} GB"
                else:
                    line = status
                if line != last:
                    print("\r" + line.ljust(78), end="", flush=True)
                    last = line
        print()

    def chat(self, model: str, messages: list[dict], options: dict, think,
             on_token=None, on_thinking=None) -> str:
        body = {"model": model, "messages": messages, "stream": True,
                "options": options, "keep_alive": "30m"}
        if think is not None:
            body["think"] = think
        parts: list[str] = []
        with self._request("/api/chat", body, timeout=None) as resp:
            for raw in resp:
                msg = json.loads(raw)
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                m = msg.get("message", {})
                if m.get("thinking") and on_thinking:
                    on_thinking(m["thinking"])
                if m.get("content"):
                    parts.append(m["content"])
                    if on_token:
                        on_token(m["content"])
        return "".join(parts).strip()


# ------------------------------------------------------------------- pipeline

SYSTEM = (
    "You are a meticulous domain expert. Think the problem through completely before "
    "answering, check every fact and every calculation, state assumptions explicitly, "
    "and say so plainly when something is uncertain. Answer in the language of the question."
)

CRITIQUE = (
    "Below are a question and a candidate answer. Act as a harsh, expert reviewer. List every "
    "factual error, calculation or logic mistake, gap, missing aspect, unclear passage and "
    "unjustified claim, each with the concrete fix. Do not rewrite the answer. If it is "
    "genuinely flawless, say so.\n\n## Question\n{q}\n\n## Candidate answer\n{a}"
)

SYNTHESIS = (
    "Below are a question and {n} independently written answers. Where they disagree, work out "
    "which is correct. Write the single best possible answer, combining the strongest parts and "
    "fixing any mistake. Output only the final answer itself, without mentioning the drafts.\n\n"
    "## Question\n{q}\n\n{drafts}"
)

REVISION = (
    "Below are a question, an answer and an expert review of that answer. Write the final, "
    "improved answer: apply every valid point of the review, ignore invalid ones, keep what was "
    "already right. Output only the final answer itself, without mentioning the review.\n\n"
    "## Question\n{q}\n\n## Answer\n{a}\n\n## Review\n{c}"
)


class Runner:
    def __init__(self, api: Ollama, model: str, num_ctx: int, verbose: bool):
        self.api, self.model, self.verbose = api, model, verbose
        self.num_ctx = num_ctx
        caps = api.capabilities(model)
        if "thinking" in caps:
            self.think = "high" if model.startswith("gpt-oss") else True
        else:
            self.think = None

    def ask(self, prompt: str, temperature: float, label: str, stream: bool) -> str:
        options = {"num_ctx": self.num_ctx, "temperature": temperature, "top_p": 0.95, "num_predict": -1}
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        start = time.time()
        counter = {"think": 0, "out": 0}

        def progress():
            print(f"\r  {label}: denkt {counter['think']} / schreibt {counter['out']} Tokens "
                  f"({time.time() - start:.0f}s)", end="", flush=True, file=sys.stderr)

        def on_thinking(t):
            counter["think"] += 1
            if self.verbose:
                print(t, end="", flush=True, file=sys.stderr)
            elif counter["think"] % 20 == 0:
                progress()

        def on_token(t):
            counter["out"] += 1
            if stream:
                print(t, end="", flush=True)
            elif self.verbose:
                print(t, end="", flush=True, file=sys.stderr)
            elif counter["out"] % 20 == 0:
                progress()

        if not stream and not self.verbose:
            progress()
        try:
            text = self.api.chat(self.model, messages, options, self.think, on_token, on_thinking)
        except RuntimeError as e:
            if self.think is not None and "think" in str(e).lower():
                self.think = None
                return self.ask(prompt, temperature, label, stream)
            raise
        if not stream:
            print(f"\r  {label}: fertig ({counter['out']} Tokens, {time.time() - start:.0f}s)".ljust(78),
                  file=sys.stderr)
        else:
            print()
        return text

    def solve(self, question: str, level: int, drafts: int) -> tuple[str, list[tuple[str, str]]]:
        """Returns (final answer, [(stage, text), ...])."""
        log: list[tuple[str, str]] = []
        if level <= 1:
            final = self.ask(question, 0.6, "Antwort", stream=True)
            return final, [("Antwort", final)]

        n = drafts if level >= 3 else 1
        answers = []
        for i in range(n):
            a = self.ask(question, 0.7, f"Entwurf {i + 1}/{n}", stream=False)
            answers.append(a)
            log.append((f"Entwurf {i + 1}", a))

        if n > 1:
            joined = "\n\n".join(f"## Answer {i + 1}\n{a}" for i, a in enumerate(answers))
            current = self.ask(SYNTHESIS.format(n=n, q=question, drafts=joined), 0.3, "Synthese", stream=False)
            log.append(("Synthese", current))
        else:
            current = answers[0]

        critique = self.ask(CRITIQUE.format(q=question, a=current), 0.3, "Kritik", stream=False)
        log.append(("Kritik", critique))
        print("\n" + "=" * 78 + "\nENDGÜLTIGE ANTWORT\n" + "=" * 78, flush=True)
        final = self.ask(REVISION.format(q=question, a=current, c=critique), 0.3, "Final", stream=True)
        log.append(("Final", final))
        return final, log


def write_report(path: Path, model: str, question: str, final: str, log: list[tuple[str, str]]) -> None:
    lines = [f"# Antwort ({model})", "", "## Frage", "", question, "", "## Antwort", "", final, ""]
    if len(log) > 1:
        lines += ["---", "", "## Zwischenschritte", ""]
        for stage, text in log[:-1]:
            lines += [f"### {stage}", "", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nGespeichert: {path}")


# ------------------------------------------------------------------------ main

def confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    return input(f"{question} [j/N] ").strip().lower() in ("j", "ja", "y", "yes")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Bestes Ollama-Modell für deine Hardware, mit Qualitäts-Pipeline.")
    ap.add_argument("prompt", nargs="*", help="Frage (leer = interaktiv)")
    ap.add_argument("--file", type=Path, help="Frage aus Datei lesen")
    ap.add_argument("--out", type=Path, help="Antwort + Zwischenschritte als Markdown speichern")
    ap.add_argument("--model", help="Modell erzwingen statt automatisch wählen")
    ap.add_argument("--mode", choices=["auto", "ram", "stream"], default="auto",
                    help="ram = nur was in VRAM+RAM passt (Ollama); stream = Modell von der SSD streamen "
                         "(llama.cpp, mmap); auto = das bessere von beiden (Standard)")
    ap.add_argument("--gguf", type=Path, help="Eigene GGUF-Datei im Stream-Modus verwenden (statt Ollama-Modell)")
    ap.add_argument("--quality", type=int, choices=[1, 2, 3],
                    help="1 = eine Antwort, 2 = Antwort+Kritik+Revision, 3 = mehrere Entwürfe+Synthese+Kritik+Revision "
                         "(Standard: 3, im Stream-Modus 2)")
    ap.add_argument("--drafts", type=int, default=3, help="Anzahl Entwürfe bei --quality 3 (Standard 3)")
    ap.add_argument("--ctx", type=int, default=32768, help="Kontextfenster in Tokens (Standard 32768)")
    ap.add_argument("--vram", type=float, help="VRAM in GB überschreiben (Standard: nvidia-smi, sonst 24)")
    ap.add_argument("--ram", type=float, help="RAM in GB überschreiben")
    ap.add_argument("--reserve", type=float, help="RAM in GB, der frei bleiben soll (Standard max(6, 12%%))")
    ap.add_argument("--disk-speed", type=float, default=2.5,
                    help="Lesegeschwindigkeit der SSD in GB/s für die Zeitschätzung (Standard 2.5 = NVMe)")
    ap.add_argument("--max-spt", type=float, default=10.0,
                    help="Stream-Modus: höchstens so viele Sekunden pro Token (Standard 10)")
    ap.add_argument("--llama-server", help="Pfad zu llama-server (sonst PATH oder automatischer Download)")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ap.add_argument("--check", action="store_true", help="Nur Hardware und Modellwahl anzeigen")
    ap.add_argument("--yes", action="store_true", help="Downloads ohne Rückfrage")
    ap.add_argument("--verbose", action="store_true", help="Denken und Zwischenschritte live anzeigen")
    args = ap.parse_args(argv)

    host = args.host if args.host.startswith("http") else "http://" + args.host
    api = Ollama(host)

    vram = args.vram if args.vram is not None else detect_vram_gb()
    if vram is None:
        print("nvidia-smi nicht gefunden - nehme 24 GB VRAM an (--vram zum Ändern).")
        vram = 24.0
    ram = args.ram if args.ram is not None else detect_ram_gb()
    if ram is None:
        sys.exit("RAM konnte nicht ermittelt werden - bitte --ram angeben.")
    budget = make_budget(vram, ram, args.reserve)
    disk = free_disk_gb(models_dir())

    print(f"VRAM {vram:.0f} GB + RAM {ram:.0f} GB - Reserve {budget.reserve:.0f} GB "
          f"= {budget.total:.0f} GB für das Modell; Platte frei: "
          f"{'?' if disk is None else f'{disk:.0f} GB'}; Kontext {args.ctx} Tokens")

    gguf: Path | None = None
    moe = False
    if args.gguf:
        if not is_gguf(args.gguf):
            sys.exit(f"{args.gguf} ist keine GGUF-Datei.")
        gguf, model, mode, need_pull = args.gguf, args.gguf.name, "stream", False
        print(f"Eigene GGUF-Datei: {gguf} ({gguf.stat().st_size / GB:.0f} GB)")
    else:
        if not args.check:
            api.ensure_running()
        installed = api.installed() if api.alive() else {}

        if args.model:
            model = args.model
            entry = next((e for e in CATALOG if e["tag"] == model), None)
            size = installed.get(model) or registry_size_gb(model, entry["size"] if entry else 0)[0] or 0
            fits = size > 0 and required_gb(size, entry["kv_32k"] if entry else 6, args.ctx) <= budget.total
            mode = args.mode if args.mode != "auto" else ("ram" if fits else "stream")
            moe = bool(entry and entry["active"] < entry["total"])
            print(f"Modell (vorgegeben): {model}, ~{size:.0f} GB, Modus {mode}")
            need_pull = model not in installed
        else:
            ram_choice = stream_choice = None
            if args.mode in ("auto", "ram"):
                print("\nPasst komplett in VRAM + RAM (schnell, Ollama):")
                ram_choice = choose(budget, args.ctx, disk, installed, registry_size_gb)
            if args.mode in ("auto", "stream"):
                print("\nVon der SSD gestreamt (langsam, llama.cpp):")
                stream_choice = choose_stream(budget, args.ctx, disk, installed, registry_size_gb,
                                              args.disk_speed, args.max_spt)
            if stream_choice and (ram_choice is None or rank(stream_choice.tag) < rank(ram_choice.tag)):
                choice, mode = stream_choice, "stream"
            elif ram_choice:
                choice, mode = ram_choice, "ram"
            else:
                sys.exit("Kein Modell aus der Liste passt. Mehr Plattenplatz, --max-spt erhöhen oder --model angeben.")
            model, moe, need_pull = choice.tag, choice.moe, not choice.installed
            print(f"\nGewählt: {model} ({choice.note}), ~{choice.size:.0f} GB, Modus {mode}.")
            if mode == "ram":
                on_gpu = min(1.0, vram / choice.need) * 100
                print(f"Etwa {on_gpu:.0f}% auf der GPU, Rest im RAM.")
            else:
                print(f"Geschätzt {choice.spt:.1f} s pro Token = {choice.spt * 1000 / 3600:.1f} h pro 1000 Tokens. "
                      "Denkende Modelle schreiben oft 2000-8000 Tokens pro Schritt.")
                print("Die SSD liest dabei dauernd - eine NVMe-SSD ist Pflicht, auf einer HDD ist es hoffnungslos.")

    quality = args.quality or (2 if mode == "stream" else 3)

    if args.check:
        return

    if need_pull:
        if not confirm(f"{model} ist nicht installiert. Jetzt herunterladen?", args.yes):
            sys.exit("Abgebrochen - nichts heruntergeladen.")
        api.pull(model)

    backend = api
    if mode == "stream":
        exe = find_llama_server(args.llama_server)
        if exe is None:
            if not confirm("llama.cpp (llama-server) fehlt. Offizielles Release von GitHub herunterladen?", args.yes):
                sys.exit("Ohne llama-server kein Stream-Modus. Installieren: https://github.com/ggml-org/llama.cpp/releases "
                         "oder --llama-server PFAD angeben.")
            exe = download_llama_server()
            if exe is None:
                sys.exit("Download fehlgeschlagen. Bitte manuell installieren und --llama-server angeben.")
        if gguf is None:
            gguf = ollama_blob(model, models_dir())
            if gguf is None or not is_gguf(gguf):
                sys.exit(f"Modelldatei von {model} nicht gefunden. Mit --gguf PFAD direkt angeben.")
        if api.alive():
            api.unload_all()
        backend = LlamaServer(exe, gguf, args.ctx, moe)
        backend.start()

    runner = Runner(backend, model, args.ctx, args.verbose)
    print(f"Thinking: {runner.think if runner.think is not None else 'nicht unterstützt'}; "
          f"Qualitätsstufe {quality}. Das erste Laden kann Minuten dauern.\n")

    def run_once(question: str, out: Path | None) -> None:
        final, log = runner.solve(question, quality, max(1, args.drafts))
        if out:
            write_report(out, model, question, final, log)

    if args.file:
        run_once(args.file.read_text(encoding="utf-8"), args.out)
    elif args.prompt:
        run_once(" ".join(args.prompt), args.out)
    else:
        print("Interaktiv. Leere Zeile = absenden, 'exit' = beenden.")
        n = 0
        while True:
            lines = []
            try:
                line = input("\n> ")
                if line.strip().lower() in ("exit", "quit"):
                    break
                while line.strip():
                    lines.append(line)
                    line = input("  ")
            except EOFError:
                break
            question = "\n".join(lines).strip()
            if question:
                n += 1
                out = args.out.with_stem(f"{args.out.stem}_{n}") if args.out else None
                run_once(question, out)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
