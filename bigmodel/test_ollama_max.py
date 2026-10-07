"""Tests for ollama_max: model selection and the pipeline against a fake Ollama."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ollama_max as om


def sizes(table):
    return lambda tag, fallback: (table.get(tag, fallback), "test") if table.get(tag, 0) is not None else (None, "x")


def test_24gb_vram_64gb_ram_picks_gpt_oss_120b():
    budget = om.make_budget(24, 64)
    c = om.choose(budget, 32768, 1000, {}, sizes({}), log=lambda *_: None)
    assert c.tag == "gpt-oss:120b"


def test_24gb_vram_192gb_ram_picks_qwen3_235b():
    budget = om.make_budget(24, 192)
    c = om.choose(budget, 32768, 1000, {}, sizes({}), log=lambda *_: None)
    assert c.tag == "qwen3:235b"


def test_24gb_vram_32gb_ram_picks_a_27b_model():
    budget = om.make_budget(24, 32)
    c = om.choose(budget, 32768, 1000, {}, sizes({}), log=lambda *_: None)
    assert c.tag == "qwen3.6:27b"


def test_unknown_tag_is_skipped_and_disk_limit_respected():
    budget = om.make_budget(24, 512)
    table = {"deepseek-v3.1:671b": None}
    c = om.choose(budget, 32768, 100, {}, sizes(table), log=lambda *_: None)
    assert c.tag == "gpt-oss:120b"  # qwen3:235b fits in memory but not on a 100 GB disk


def test_installed_model_needs_no_disk():
    budget = om.make_budget(24, 192)
    c = om.choose(budget, 32768, 1, {"qwen3:235b": 142}, sizes({}), log=lambda *_: None)
    assert c.tag == "qwen3:235b" and c.installed


class FakeOllama(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._json({"version": "0.0.0"})
        elif self.path == "/api/tags":
            self._json({"models": [{"name": "fake:1b", "size": 1e9}]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/show":
            self._json({"capabilities": ["completion", "thinking"]})
            return
        FakeOllama.calls.append(req)
        prompt = req["messages"][-1]["content"]
        text = "REVIEW" if "harsh, expert reviewer" in prompt else f"ANSWER{len(FakeOllama.calls)}"
        self.send_response(200)
        self.end_headers()
        for chunk in ({"message": {"thinking": "hmm"}}, {"message": {"content": text}}, {"done": True}):
            self.wfile.write((json.dumps(chunk) + "\n").encode())


def test_pipeline_runs_all_stages(tmp_path, capsys):
    FakeOllama.calls = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        out = tmp_path / "a.md"
        om.main(["--model", "fake:1b", "--vram", "24", "--ram", "64", "--drafts", "2",
                 "--out", str(out), "--host", f"http://127.0.0.1:{srv.server_port}", "Was ist 2+2?"])
    finally:
        srv.shutdown()
    # 2 drafts + synthesis + critique + final
    assert len(FakeOllama.calls) == 5
    assert all(c["think"] is True and c["options"]["num_ctx"] == 32768 for c in FakeOllama.calls)
    synth, crit, final = (c["messages"][-1]["content"] for c in FakeOllama.calls[2:])
    assert "ANSWER1" in synth and "ANSWER2" in synth
    assert "ANSWER3" in crit
    assert "REVIEW" in final and "ANSWER3" in final
    report = out.read_text(encoding="utf-8")
    assert "ANSWER5" in report and "### Kritik" in report


# ------------------------------------------------------------- stream mode

import stream_backend as sb


def test_stream_with_32gb_ram_picks_deepseek_when_disk_allows():
    budget = om.make_budget(24, 32)
    c = om.choose_stream(budget, 32768, 2000, {}, sizes({}), 2.5, 10, log=lambda *_: None)
    assert c.tag == "deepseek-v3.1:671b" and c.moe and 5 < c.spt < 10


def test_stream_speed_limit_and_disk_limit():
    budget = om.make_budget(24, 32)
    c = om.choose_stream(budget, 32768, 2000, {}, sizes({}), 2.5, 5, log=lambda *_: None)
    assert c.tag == "qwen3:235b"
    c = om.choose_stream(budget, 32768, 300, {}, sizes({}), 2.5, 10, log=lambda *_: None)
    assert c.tag == "qwen3:235b"


def test_sec_per_token_no_disk_reads_when_model_fits():
    assert sb.sec_per_token(20, 32, 32, 50, 2.5) == 20 / 50
    # a dense model streamed from disk is far slower than a MoE of the same size
    assert sb.sec_per_token(400, 400, 400, 50, 2.5) > 10 * sb.sec_per_token(400, 671, 37, 50, 2.5)


def test_pick_assets_windows_cuda_with_runtime():
    assets = [{"name": n} for n in (
        "llama-b7000-bin-win-cpu-x64.zip", "llama-b7000-bin-win-cuda-12.4-x64.zip",
        "llama-b7000-bin-win-cuda-13.1-x64.zip", "cudart-llama-bin-win-cuda-12.4-x64.zip",
        "cudart-llama-bin-win-cuda-13.1-x64.zip", "llama-b7000-bin-ubuntu-vulkan-x64.zip")]
    names = [a["name"] for a in sb.pick_assets(assets, "Windows", "amd64")]
    assert names == ["llama-b7000-bin-win-cuda-13.1-x64.zip", "cudart-llama-bin-win-cuda-13.1-x64.zip"]
    assert [a["name"] for a in sb.pick_assets(assets, "Linux", "x86_64")] == ["llama-b7000-bin-ubuntu-vulkan-x64.zip"]


def test_ollama_blob_from_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(sb.shutil, "which", lambda _: None)
    blob = tmp_path / "blobs" / "sha256-abc"
    blob.parent.mkdir()
    blob.write_bytes(b"GGUF....")
    man = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen3" / "235b"
    man.parent.mkdir(parents=True)
    man.write_text(json.dumps({"layers": [
        {"mediaType": "application/vnd.ollama.image.template", "digest": "sha256:zzz"},
        {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:abc"}]}))
    assert sb.ollama_blob("qwen3:235b", tmp_path) == blob and sb.is_gguf(blob)


def test_llama_command_old_and_new_builds():
    srv = sb.LlamaServer(sb.Path("llama-server"), sb.Path("m.gguf"), 32768, moe=True)
    new = srv.command("--fit --cpu-moe --reasoning-format")
    assert "-ngl" not in new and "--reasoning-format" in new
    old = srv.command("--cpu-moe")
    assert old[-3:] == ["-ngl", "999", "--cpu-moe"]


class FakeLlama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for d in ({"reasoning_content": "denk"}, {"content": "Hal"}, {"content": "lo"}):
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': d}]})}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


def test_llama_chat_parses_sse():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeLlama)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        srv = sb.LlamaServer(sb.Path("x"), sb.Path("m.gguf"), 4096, moe=False, port=httpd.server_port)
        thinking = []
        out = srv.chat("m", [{"role": "user", "content": "hi"}], {"temperature": 0.3}, True,
                       on_thinking=thinking.append)
    finally:
        httpd.shutdown()
    assert out == "Hallo" and thinking == ["denk"]
