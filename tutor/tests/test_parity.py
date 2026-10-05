"""Der JS-Kern (web/core.js, in der iPad-App) muss dasselbe liefern wie Python."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import main  # noqa: E402
import planner as pl  # noqa: E402
from test_router import Classify  # noqa: E402

TASKS = [
    {"id": "a1", "title": "Mathe; Blatt, 4", "subject": "Mathe", "due": "2026-10-07", "minutes": 100,
     "done": False, "created": "2026-10-01T10:00:00"},
    {"id": "b2", "title": "Vokabeln", "subject": "", "due": "", "minutes": 30, "done": False,
     "created": "2026-10-02T10:00:00"},
    {"id": "c3", "title": "Zu viel", "subject": "Bio", "due": "2026-10-05", "minutes": 300,
     "done": False, "created": "2026-10-03T10:00:00"},
    {"id": "d4", "title": "Fertig", "subject": "", "due": "2026-10-06", "minutes": 20, "done": True,
     "created": "2026-10-03T11:00:00"},
]


def make_planner():
    p = pl.Planner(Path(tempfile.mkdtemp()) / "p.json")
    p.data["tasks"] = [dict(t) for t in TASKS]
    return p


class Capture:
    def chat(self, model, messages, options=None, stream=False):
        self.prompt = messages[0]["content"]
        return {"message": {"content": ""}}


@unittest.skipUnless(shutil.which("node"), "node nicht installiert")
class Parity(unittest.TestCase):
    CASES = [
        *[(t, c) for t, c, _ in Classify.CASES],
        ("Übung 3 bitte", {}), ("Erkläre mir die Ökologie", {}), ("Was ist ein Äquator?", {}),
        ("Wie heißt die Hauptstadt von Österreich?", {}), ("Ich versteh das nicht", {}),
        ("Hilfe!", {}), ("hi 😀", {}), ("😀" * 30, {}), ("Moin, wie löse ich das?", {}),
        ("Guten Morgen", {"attempts": 3, "last_tier": "main"}), ("JA", {"attempts": 1, "last_tier": "main"}),
        ("Ist 3 < 5?", {}), ("f(x) ableiten", {}), ("Wann ist die Frist für den Test?", {}),
        ("Plan", {"has_page": True}), ("   ", {}), ("Tschüss!", {"attempts": 5, "last_tier": "main"}),
    ]

    @classmethod
    def setUpClass(cls):
        import tempfile
        cases = Path(tempfile.mkdtemp()) / "cases.json"
        cases.write_text(json.dumps(cls.CASES))
        out = subprocess.run(["node", str(ROOT / "tests" / "parity.js"), str(cases)], capture_output=True,
                             text=True, check=True).stdout
        cls.js = json.loads(out)

    def test_stages_and_blocks(self):
        js = self.js
        self.assertEqual(js["stage"], [main.Task(attempts=a).stage(2) for a in (0, 1, 2, 3, 4, 5, 6, 9)])
        self.assertEqual(js["stageGivenUp"], main.Task(attempts=1, given_up=True).stage(2))
        self.assertEqual(js["stageText"], {str(k): v for k, v in main.STAGE_TEXT.items()})
        self.assertEqual(js["status"], main.status_block(main.Task(attempts=3), 2))
        self.assertEqual(js["statusUp"], main.status_block(main.Task(attempts=3, given_up=True), 2))
        self.assertEqual(js["page"], main.page_block(main.Task(page_notes=list("abcde"))))

    def test_prompts(self):
        self.assertEqual(js_prompt := self.js["prompt"], "X für PhysikYDeutsch")
        self.assertEqual(self.js["promptNoSubject"], "XYDeutsch")
        self.assertEqual(self.js["handwriting"], main.HANDWRITING_PROMPT)
        cap = Capture()
        main.extract_tasks_text(cap, "m", "img", "2026-10-05")
        self.assertEqual(self.js["extract"], cap.prompt)
        _ = js_prompt

    def test_plan(self):
        p = make_planner()
        self.assertEqual(self.js["planNoon"], p.plan(datetime(2026, 10, 5, 15, 0)))
        self.assertEqual(self.js["planLate"], p.plan(datetime(2026, 10, 5, 23, 30)))
        self.assertEqual(self.js["planShort"],
                         p.plan(datetime(2026, 10, 5, 15, 0), days=2, daily_minutes=50, start="08:00"))
        self.assertEqual(self.js["plannerBlock"], pl.planner_block(p.open_tasks(), date(2026, 10, 5)))

    def test_parsing_and_blocklist(self):
        raw = 'Hier: [{"title":"A","minutes":"20","due":"2026-10-09"},{"nix":1},{"title":" B ","due":"2026-02-30","minutes":9999},5] ok'
        self.assertEqual(self.js["parse"], pl.parse_tasks_json(raw))
        self.assertEqual(self.js["parseBad"], [pl.parse_tasks_json("kein json"), pl.parse_tasks_json("[kaputt")])
        p = make_planner()
        self.assertEqual(self.js["blocklist"],
                         p.set_blocklist(["https://www.Foo.com/x", "kaputt", "foo.com", "a.b"]))

    def test_router_patterns_and_decisions(self):
        import router
        for key, (src, flags) in self.js["patterns"].items():
            self.assertEqual(getattr(router, key).pattern, src, key)
            py_flags = "".join(f for f, bit in (("i", router.re.I), ("m", router.re.M)) if getattr(router, key).flags & bit)
            self.assertEqual(flags, py_flags, key)
        for (text, ctx), got in zip(self.CASES, self.js["route"]):
            self.assertEqual(got, list(router.classify(text, ctx)), (text, ctx))
        consts = self.js["routerConsts"]
        self.assertEqual(consts, {"ESCAPE": router.ESCAPE, "LIGHT_BLOCK": router.LIGHT_BLOCK,
                                  "STRICT_LANG": router.STRICT_LANG, "KEEP_ALIVE": main.KEEP_ALIVE})
        for text, (has, stripped) in zip(["im Thema卡特尔", "、", "Müller äöü ß – „Zitat“ … 3×4", "한국어", "ひらがな", "ＡＢＣ"], self.js["cjk"]):
            self.assertEqual((has, stripped), (router.has_cjk(text), router.strip_cjk(text)), text)

    def test_ics(self):
        p = make_planner()
        p.set_reminders(True, "17:30")
        self.assertEqual(self.js["ics"], p.ics(datetime(2026, 10, 5, 15, 0)))
        p.set_reminders(False, "17:30")
        self.assertEqual(self.js["icsNoRem"], p.ics(datetime(2026, 10, 5, 23, 30)))


if __name__ == "__main__":
    unittest.main()
