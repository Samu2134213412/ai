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
