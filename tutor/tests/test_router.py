"""Automatische Modellwahl (schnell/groß), Übergabe, Sprach-Wächter, Fallbacks."""

import io
import json
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import main  # noqa: E402
import router  # noqa: E402
from test_tutor import FakeClient  # noqa: E402

MAIN, LIGHT = "qwen2.5:32b", "qwen2.5:3b"


def make(replies=None, models=(MAIN, LIGHT), **cfg):
    config = main.load_config(Path("/nonexistent"))
    config.update(cfg)
    client = FakeClient(models=list(models), replies=replies or {})
    return main.Session(config, client, "SYSTEM", out=io.StringIO()), client


def run(session, text):
    out = []
    for p in session.stream_turn(text):
        out.append(p)
    return out


def text_of(pieces):
    """Wie die Oberfläche: RESET verwirft das Bisherige."""
    acc = ""
    for p in pieces:
        acc = "" if p is main.RESET else acc + p
    return acc.strip()


class Classify(unittest.TestCase):
    CASES = [
        ("moin", {}, "light"), ("Hallo, wie geht's?", {}, "light"), ("Danke!", {}, "light"),
        ("Was ist eine Primzahl?", {}, "light"), ("Wer war Goethe?", {}, "light"),
        ("Plan für nächste Woche?", {}, "light"), ("Wann ist der Test?", {}, "light"),
        ("Wie löse ich 3x+7=22?", {}, "main"), ("x=5", {}, "main"), ("Hilf mir bei Mathe", {}, "main"),
        ("Erkläre mir die Photosynthese", {}, "main"), ("Schreib mir einen Aufsatz über Goethe", {}, "main"),
        ("def f(x): return x", {}, "main"), ("a" * 200, {}, "main"),
        ("Ich habe 7 abgezogen", {"attempts": 1, "last_tier": "main"}, "main"),
        ("ok", {"attempts": 2, "last_tier": "main"}, "main"),          # Antwort auf die Tutor-Frage
        ("danke", {"attempts": 2, "last_tier": "main"}, "light"),
        ("moin", {"has_page": True}, "light"), ("Was steht da?", {"has_page": True}, "main"),
        ("moin", {"given_up": True}, "main"), ("moin", {"has_image": True}, "main"),
    ]

    def test_table(self):
        for text, ctx, want in self.CASES:
            self.assertEqual(router.classify(text, ctx)[0], want, (text, ctx))

    def test_cjk_helpers(self):
        self.assertTrue(router.has_cjk("im Thema卡特尔"))
        self.assertTrue(router.has_cjk("、"))
        self.assertFalse(router.has_cjk("Müller äöü ß – „Zitat“ … 3×4"))
        self.assertEqual(router.strip_cjk("a卡b"), "ab")


class Routing(unittest.TestCase):
    def test_small_talk_uses_light_model_and_keeps_alive(self):
        s, c = make({LIGHT: "Moin! Woran arbeitest du?"})
        self.assertEqual(text_of(run(s, "moin")), "Moin! Woran arbeitest du?")
        self.assertEqual([x["model"] for x in c.calls], [LIGHT])
        self.assertEqual(s.last_route["tier"], "light")
        self.assertIn("Schnell-Modus", c.calls[0]["messages"][0]["content"])
        self.assertEqual(s.task.messages[-1]["content"].strip(), "Moin! Woran arbeitest du?")

    def test_tasks_go_to_main_without_light_prompt(self):
        s, c = make()
        run(s, "Wie löse ich 3x+7=22?")
        self.assertEqual([x["model"] for x in c.calls], [MAIN])
        self.assertNotIn("Schnell-Modus", c.calls[0]["messages"][0]["content"])
        self.assertEqual(s.last_route["tier"], "main")

    def test_stays_on_main_during_a_task(self):
        s, c = make()
        run(s, "Wie löse ich 3x+7=22?")
        run(s, "ok")
        self.assertEqual([x["model"] for x in c.calls], [MAIN, MAIN])

    def test_light_model_can_hand_over(self):
        s, c = make({LIGHT: "[[WEITER]]", MAIN: "Was hast du versucht?"})
        pieces = run(s, "Was ist mit Brüchen")             # sieht einfach aus, ist es aber nicht
        self.assertEqual(text_of(pieces), "Was hast du versucht?")
        self.assertNotIn(router.ESCAPE, "".join(p for p in pieces if isinstance(p, str)))
        self.assertEqual([x["model"] for x in c.calls], [LIGHT, MAIN])
        self.assertEqual(s.last_route["tier"], "main")
        self.assertIn("übergeben", s.last_route["reason"])
        self.assertEqual(len(s.task.messages), 2)           # eine Nutzer-, eine Tutor-Nachricht

    def test_short_prefix_of_escape_word_is_not_swallowed(self):
        s, _ = make({LIGHT: "[[WE"})
        self.assertEqual(text_of(run(s, "moin")), "[[WE")

    def test_chinese_drift_is_discarded_and_retried_strictly(self):
        s, c = make({MAIN: ["Moin! Was bist 卡特尔语言模型", "Moin! Was möchtest du lernen?"]}, light_model="")
        pieces = run(s, "Hilf mir bitte bei der Aufgabe")
        self.assertIn(main.RESET, pieces)
        self.assertEqual(text_of(pieces), "Moin! Was möchtest du lernen?")
        self.assertEqual([x["model"] for x in c.calls], [MAIN, MAIN])
        self.assertNotIn("Sprache (wichtig)", c.calls[0]["messages"][0]["content"])
        self.assertIn("Sprache (wichtig)", c.calls[1]["messages"][0]["content"])
        self.assertLessEqual(c.calls[1]["options"]["temperature"], 0.3)
        self.assertFalse(router.has_cjk(s.task.messages[-1]["content"]))

    def test_light_drifts_then_main_answers(self):
        s, c = make({LIGHT: "Hi 你好 du", MAIN: "Hallo! Woran arbeitest du?"})
        self.assertEqual(text_of(run(s, "moin")), "Hallo! Woran arbeitest du?")
        self.assertEqual([x["model"] for x in c.calls], [LIGHT, LIGHT, MAIN])

    def test_everything_drifts_gives_polite_german_fallback(self):
        s, _ = make({MAIN: "Was 卡特尔 ist"}, light_model="")
        reply = text_of(run(s, "Hilf mir bei Mathe"))
        self.assertIn("Entschuldige", reply)
        self.assertFalse(router.has_cjk(reply))

    def test_missing_light_model_falls_back_once_with_notice(self):
        s, c = make({MAIN: "Moin!"}, models=(MAIN,))
        run(s, "moin")
        self.assertEqual([x["model"] for x in c.calls], [LIGHT, MAIN])    # einmal versucht, dann das große
        self.assertIn("ollama pull " + LIGHT, s.last_route["notice"])
        self.assertFalse(s.light_ok)
        before = len(c.calls)
        run(s, "danke")                                                    # danach gar nicht erst versucht
        self.assertEqual([x["model"] for x in c.calls[before:]], [MAIN])

    def test_same_model_or_disabled_means_no_routing(self):
        for cfg in ({"light_model": ""}, {"light_model": MAIN}):
            s, c = make({MAIN: "ok"}, **cfg)
            run(s, "moin")
            self.assertEqual([x["model"] for x in c.calls], [MAIN], cfg)

    def test_main_failure_still_rolls_back(self):
        s, _ = make(models=(LIGHT,))                          # großes Modell fehlt
        with self.assertRaises(main.TutorError):
            run(s, "Wie löse ich 3x+7=22?")
        self.assertEqual((s.task.attempts, s.task.messages), (0, []))

    def test_cli_prints_reset_marker(self):
        s, _ = make({MAIN: ["Hi 你好", "Hallo du"]}, light_model="")
        s.ask("Hilf mir bei Mathe")
        out = s.out.getvalue()
        self.assertIn("neuer Versuch", out)
        self.assertIn("Hallo du", out.split("neuer Versuch")[1])
        self.assertIn("🧠 " + MAIN, out)


class WebEvents(unittest.TestCase):
    def test_sse_reset_and_route(self):
        import planner as pl
        import tempfile
        import web
        client = FakeClient(models=[MAIN, LIGHT, "qwen2.5vl:7b"], replies={MAIN: ["Hi 你好", "Hallo du"]})
        config = main.load_config(Path("/nonexistent"))
        server = web.make_server(config, client, "SYSTEM", "127.0.0.1", 0, None,
                                 pl.Planner(Path(tempfile.mkdtemp()) / "p.json"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            req = urllib.request.Request(base + "/api/chat", data=json.dumps({"text": "Wie löse ich x=5?"}).encode(),
                                         headers={"Content-Type": "application/json"})
            raw = urllib.request.urlopen(req).read().decode()
            events = [json.loads(l[5:]) for l in raw.split("\n\n") if l.startswith("data:")]
            self.assertTrue(any(e.get("reset") for e in events))
            self.assertEqual(events[-1]["route"]["tier"], "main")
            self.assertEqual(events[-1]["state"]["light_model"], LIGHT)
        finally:
            server.shutdown(); server.server_close()


if __name__ == "__main__":
    unittest.main()
