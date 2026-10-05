"""Offline-Tests (ohne Ollama): python -m unittest discover -s tests"""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ollama  # noqa: E402

import main  # noqa: E402


class FakeClient:
    """Ersetzt ollama.Client: merkt sich Anfragen, streamt feste Antworten."""

    def __init__(self, models=("qwen2.5:32b",), reply="Was hast du schon versucht?",
                 fail=None, replies=None):
        self.replies = replies or {}          # Modell -> Text oder Liste (je Aufruf der nächste)
        self.models = list(models)
        self.reply = reply
        self.fail = fail
        self.calls = []
        self.tutor_host = "http://localhost:11434"

    def list(self):
        if self.fail == "connection":
            raise ConnectionError("Failed to connect to Ollama")
        return {"models": [{"model": m} for m in self.models]}

    def chat(self, model, messages, stream=False, options=None, keep_alive=None):
        self.calls.append({"model": model, "messages": messages, "options": options})
        if self.fail == "connection":
            raise ConnectionError("Failed to connect to Ollama")
        if model not in self.models:
            raise ollama.ResponseError(f"model '{model}' not found", 404)
        if not stream:
            prompt = messages[0]["content"]
            if "JSON-Array" in prompt and getattr(self, "vision_reply", None):
                return {"message": {"content": self.vision_reply}}
            return {"message": {"content": "Abschrift: 3x + 7 = 22"}}
        return self._stream(model)

    def _stream(self, model=None):
        reply = self.replies.get(model, self.reply)
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        for word in reply.split(" "):
            yield {"message": {"content": word + " "}}


def make_session(client=None, **hints):
    config = main.load_config(Path("/nonexistent"))
    config["hints"].update(hints)
    return main.Session(config, client or FakeClient(), "SYSTEM", out=io.StringIO())


def system_of(call):
    return call["messages"][0]["content"]


class StageTests(unittest.TestCase):
    def test_stage_progression(self):
        task = main.Task()
        stages = []
        for _ in range(7):
            task.attempts += 1
            stages.append(task.stage(2))
        self.assertEqual(stages, [1, 1, 2, 2, 3, 3, 3])

    def test_given_up(self):
        self.assertEqual(main.Task(attempts=1, given_up=True).stage(2), main.GIVEN_UP)

    def test_status_injected_into_system_prompt(self):
        s = make_session()
        for _ in range(5):
            s.handle("hilf mir")
        prompts = [system_of(c) for c in s.client.calls]
        self.assertIn("Stufe 1 – Leitfrage", prompts[0])
        self.assertIn("Stufe 2 – Denkanstoß", prompts[2])
        self.assertIn("Stufe 3 – Teilschritt", prompts[4])
        self.assertTrue(all(p.startswith("SYSTEM") for p in prompts))
        self.assertNotIn("AUFGEGEBEN", prompts[4])

    def test_neu_resets_counter_and_history(self):
        s = make_session()
        for _ in range(4):
            s.handle("frage")
        s.handle("/neu Neue Aufgabe: 2x = 8")
        self.assertEqual(len(s.tasks), 2)
        self.assertEqual(s.task.attempts, 1)
        last = s.client.calls[-1]
        self.assertIn("Stufe 1", system_of(last))
        self.assertEqual(len(last["messages"]), 2)  # System + 1 Nachricht

    def test_aufgeben_needs_confirmation_when_early(self):
        s = make_session(min_attempts_before_giving_up=2)
        s.handle("Aufgabe")
        s.handle("/aufgeben")
        self.assertFalse(s.task.given_up)
        s.handle("/aufgeben")
        self.assertTrue(s.task.given_up)
        self.assertIn("AUFGEGEBEN", system_of(s.client.calls[-1]))

    def test_aufgeben_after_attempts(self):
        s = make_session()
        s.handle("Aufgabe")
        s.handle("Versuch")
        s.handle("/aufgeben")
        self.assertTrue(s.task.given_up)

    def test_aufgeben_without_task(self):
        s = make_session()
        s.handle("/aufgeben")
        self.assertEqual(s.client.calls, [])


class OllamaErrorTests(unittest.TestCase):
    def test_not_running(self):
        with self.assertRaises(main.TutorError) as ctx:
            main.check_model(FakeClient(fail="connection"), "qwen2.5:32b")
        self.assertIn("nicht erreichbar", str(ctx.exception))

    def test_model_missing(self):
        with self.assertRaises(main.TutorError) as ctx:
            main.check_model(FakeClient(models=["llama3:latest"]), "qwen2.5:32b")
        self.assertIn("ollama pull qwen2.5:32b", str(ctx.exception))

    def test_latest_tag(self):
        main.check_model(FakeClient(models=["llama3:latest"]), "llama3")

    def test_chat_error_does_not_count(self):
        s = make_session(FakeClient(models=["andere:7b"]))
        s.handle("Aufgabe")
        self.assertEqual(s.task.attempts, 0)
        self.assertEqual(s.task.messages, [])

    def test_switch_model(self):
        s = make_session(FakeClient(models=["qwen2.5:32b", "qwen2.5:14b"]))
        s.handle("/modell gibtsnicht:1b")
        self.assertEqual(s.model, "qwen2.5:32b")
        s.handle("/modell qwen2.5:14b")
        self.assertEqual(s.model, "qwen2.5:14b")


class MiscTests(unittest.TestCase):
    def test_prompt_placeholders(self):
        text = main.load_prompt(main.BASE_DIR / "prompts" / "tutor.md", "Physik", "Deutsch")
        self.assertIn("Tutor für Physik", text)
        self.assertNotIn("{{", text)

    def test_save(self):
        import tempfile
        s = make_session()
        with tempfile.TemporaryDirectory() as tmp:
            s.config["sessions"]["directory"] = tmp
            s.handle("Aufgabe")
            path = s.save()
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["tasks"][0]["messages"][0]["content"], "Aufgabe")

    def test_exit(self):
        self.assertFalse(make_session().handle("/exit"))


if __name__ == "__main__":
    unittest.main()
