"""Layer streaming: run models larger than VRAM + RAM with llama.cpp.

Ollama refuses to load a model that does not fit in VRAM + RAM. llama.cpp
memory-maps the GGUF file instead. It keeps what fits on the GPU (attention,
shared weights, as many layers or experts as fit) and leaves the rest in the
file. The operating system reads those pages from the SSD when a token needs
them and keeps the hot ones in RAM.

For Mixture-of-Experts models this is exactly "only use the parts you need
right now": every token only touches a few experts (DeepSeek V3: 37B of
671B parameters), so only those are read from disk. A dense model needs every
weight for every token, so it streams the whole file each token. That is why
the catalog ranks MoE models for this mode.

The GGUF file is the one Ollama already downloaded (ollama pull works
regardless of RAM). Alternatively pass any GGUF with --gguf.
"""
from __future__ import annotations

import atexit
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

GB = 1e9
HERE = Path(__file__).resolve().parent
LOCAL_LLAMA_DIR = HERE / "llama.cpp"
RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"


# ------------------------------------------------------------------ estimate

def sec_per_token(size_gb: float, total_b: float, active_b: float,
                  resident_gb: float, disk_gb_s: float, mem_gb_s: float = 50.0) -> float:
    """Rough seconds per generated token when the model is streamed from disk.

    size_gb      file size
    total_b      total parameters (billions)
    active_b     parameters used per token (= total_b for dense models)
    resident_gb  VRAM + RAM available to hold the model (the hot part stays there)
    """
    active_gb = size_gb * active_b / total_b
    miss = max(0.0, 1.0 - resident_gb / size_gb)
    return active_gb * miss / disk_gb_s + active_gb / mem_gb_s


# --------------------------------------------------------- model file lookup

def is_gguf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"GGUF"
    except OSError:
        return False


def ollama_blob(model: str, models_dir: Path) -> Path | None:
    """Path of the GGUF that Ollama stored for `model`."""
    exe = shutil.which("ollama")
    if exe:
        try:
            out = subprocess.run([exe, "show", "--modelfile", model],
                                 capture_output=True, text=True, timeout=60).stdout
            for line in out.splitlines():
                if line.startswith("FROM "):
                    p = Path(line[5:].strip())
                    if p.is_file():
                        return p
        except (OSError, subprocess.SubprocessError):
            pass
    name, _, tag = model.partition(":")
    if "/" not in name:
        name = f"library/{name}"
    manifest = models_dir / "manifests" / "registry.ollama.ai" / name / (tag or "latest")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for layer in data.get("layers", []):
        if layer.get("mediaType") == "application/vnd.ollama.image.model":
            p = models_dir / "blobs" / layer["digest"].replace(":", "-")
            return p if p.is_file() else None
    return None


# ------------------------------------------------------------ llama-server

def exe_name() -> str:
    return "llama-server.exe" if os.name == "nt" else "llama-server"


def find_llama_server(explicit: str | None = None) -> Path | None:
    for cand in (explicit, os.environ.get("LLAMA_SERVER")):
        if cand and Path(cand).is_file():
            return Path(cand)
    on_path = shutil.which("llama-server")
    if on_path:
        return Path(on_path)
    if LOCAL_LLAMA_DIR.is_dir():
        for p in LOCAL_LLAMA_DIR.rglob(exe_name()):
            return p
    return None


def pick_assets(assets: list[dict], system: str, machine: str) -> list[dict]:
    """Choose the release archives for this platform (main build first)."""
    names = {a["name"]: a for a in assets}

    def cuda_version(n: str) -> tuple[int, ...]:
        m = re.search(r"cuda-(\d+(?:\.\d+)*)", n)
        return tuple(int(x) for x in m.group(1).split(".")) if m else ()

    if system == "Windows":
        main = [n for n in names if "bin-win-cuda" in n and "x64" in n and not n.startswith("cudart")]
        if main:
            best = max(main, key=cuda_version)
            ver = re.search(r"cuda-[\d.]+", best).group(0)
            rt = [n for n in names if n.startswith("cudart") and ver in n and "x64" in n]
            return [names[best]] + [names[n] for n in rt[:1]]
        main = [n for n in names if "bin-win-vulkan" in n and "x64" in n]
        return [names[main[0]]] if main else []
    if system == "Linux":
        for key in ("bin-ubuntu-vulkan-x64", "bin-ubuntu-x64"):
            hit = [n for n in names if key in n]
            if hit:
                return [names[hit[0]]]
        return []
    if system == "Darwin":
        key = "bin-macos-arm64" if machine in ("arm64", "aarch64") else "bin-macos-x64"
        hit = [n for n in names if key in n]
        return [names[hit[0]]] if hit else []
    return []


def download_llama_server(log=print) -> Path | None:
    try:
        req = urllib.request.Request(RELEASES_API, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            release = json.load(resp)
    except (OSError, ValueError) as e:
        log(f"GitHub nicht erreichbar: {e}")
        return None
    assets = pick_assets(release.get("assets", []), platform.system(), platform.machine().lower())
    if not assets:
        log("Kein passendes llama.cpp-Paket für dieses System gefunden.")
        return None
    LOCAL_LLAMA_DIR.mkdir(exist_ok=True)
    for a in assets:
        log(f"Lade {a['name']} ({a['size'] / 1e6:.0f} MB) ...")
        target = LOCAL_LLAMA_DIR / a["name"]
        urllib.request.urlretrieve(a["browser_download_url"], target)
        if target.suffix == ".zip":
            with zipfile.ZipFile(target) as z:
                z.extractall(LOCAL_LLAMA_DIR)
        else:
            shutil.unpack_archive(str(target), str(LOCAL_LLAMA_DIR))
        target.unlink()
    exe = find_llama_server()
    if exe and os.name != "nt":
        for p in exe.parent.iterdir():
            if p.is_file() and p.name.startswith("llama"):
                p.chmod(p.stat().st_mode | 0o111)
    return exe


class LlamaServer:
    """Same chat() interface as ollama_max.Ollama, backed by llama-server."""

    def __init__(self, exe: Path, model_path: Path, ctx: int, moe: bool, port: int = 18080):
        self.exe, self.model_path, self.ctx, self.moe, self.port = exe, model_path, ctx, moe, port
        self.base = f"http://127.0.0.1:{port}"
        self.proc: subprocess.Popen | None = None
        self.log_path = Path(tempfile.gettempdir()) / "ollama_max_llama_server.log"

    def command(self, help_text: str) -> list[str]:
        cmd = [str(self.exe), "-m", str(self.model_path), "-c", str(self.ctx),
               "--host", "127.0.0.1", "--port", str(self.port), "-np", "1",
               "-ctk", "q8_0", "-ctv", "q8_0"]
        if "--reasoning-format" in help_text:
            cmd += ["--reasoning-format", "deepseek"]
        if "--fit" not in help_text:
            # Older builds have no automatic fitting: put every layer on the GPU and
            # keep the experts in the memory-mapped file instead.
            cmd += ["-ngl", "999"]
            if self.moe and "--cpu-moe" in help_text:
                cmd += ["--cpu-moe"]
        return cmd

    def start(self, timeout_s: int = 3600) -> None:
        try:
            help_text = subprocess.run([str(self.exe), "--help"], capture_output=True,
                                       text=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError) as e:
            sys.exit(f"llama-server lässt sich nicht starten: {e}")
        cmd = self.command(help_text)
        log = open(self.log_path, "w", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        atexit.register(self.stop)
        print(f"llama-server startet (Log: {self.log_path}) ...")
        start = time.time()
        while time.time() - start < timeout_s:
            if self.proc.poll() is not None:
                tail = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
                sys.exit("llama-server hat sich beendet:\n" + "\n".join(tail))
            try:
                with urllib.request.urlopen(self.base + "/health", timeout=5) as r:
                    if r.status == 200:
                        print(f"Modell geladen nach {time.time() - start:.0f}s.")
                        return
            except (OSError, urllib.error.HTTPError):
                pass
            time.sleep(2)
        sys.exit("llama-server wurde nicht rechtzeitig bereit.")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def capabilities(self, model: str) -> list[str]:
        return ["thinking"]  # the model's own chat template decides

    def chat(self, model: str, messages: list[dict], options: dict, think,
             on_token=None, on_thinking=None) -> str:
        body = {"messages": messages, "stream": True,
                "temperature": options.get("temperature", 0.6), "top_p": options.get("top_p", 0.95)}
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        parts: list[str] = []
        try:
            resp = urllib.request.urlopen(req, timeout=None)
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                msg = json.loads(payload)
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                for choice in msg.get("choices", []):
                    delta = choice.get("delta", {})
                    if delta.get("reasoning_content") and on_thinking:
                        on_thinking(delta["reasoning_content"])
                    if delta.get("content"):
                        parts.append(delta["content"])
                        if on_token:
                            on_token(delta["content"])
        return "".join(parts).strip()
