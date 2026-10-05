import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import planner as pl  # noqa: E402

NOW = datetime(2026, 10, 5, 15, 0)


def make():
    return pl.Planner(Path(tempfile.mkdtemp()) / "p.json")


class PlannerTests(unittest.TestCase):
    def test_edf_order_and_limits(self):
        p = make()
        p.add({"title": "später", "due": "2026-10-20", "minutes": 30})
        p.add({"title": "dringend", "due": "2026-10-06", "minutes": 90})
        plan = p.plan(NOW)
        self.assertEqual(plan["blocks"][0]["title"], "dringend")
        self.assertTrue(all(b["minutes"] <= pl.MAX_BLOCK_MIN for b in plan["blocks"]))
        per_day = {}
        for b in plan["blocks"]:
            per_day[b["date"]] = per_day.get(b["date"], 0) + b["minutes"]
        self.assertTrue(all(v <= 90 for v in per_day.values()))
        self.assertEqual(sum(b["minutes"] for b in plan["blocks"] if b["title"] == "dringend"), 90)
        self.assertEqual(plan["unplaced"], [])

    def test_unplaceable_before_deadline(self):
        p = make()
        p.add({"title": "zu viel", "due": "2026-10-05", "minutes": 300})
        plan = p.plan(NOW)
        self.assertEqual(plan["unplaced"][0]["title"], "zu viel")
        self.assertGreater(plan["unplaced"][0]["missing"], 0)
        self.assertTrue(all(b["date"] <= "2026-10-05" for b in plan["blocks"]))

    def test_persistence_and_cleaning(self):
        p = make()
        t = p.add({"title": "  Mathe  ", "minutes": "abc", "due": "kaputt"})
        self.assertEqual((t["title"], t["minutes"], t["due"]), ("Mathe", 30, ""))
        self.assertIsNone(p.add({"title": ""}))
        again = pl.Planner(p.path)
        self.assertEqual(again.tasks()[0]["id"], t["id"])
        self.assertTrue(again.update(t["id"], {"done": True}))
        self.assertEqual(again.open_tasks(), [])
        self.assertTrue(again.delete(t["id"]))

    def test_focus_expiry(self):
        p = make()
        p.start_focus(10, now=1000)
        self.assertTrue(p.focus(1300)["active"])
        self.assertEqual(p.focus(1300)["remaining"], 300)
        self.assertFalse(p.focus(1700)["active"])

    def test_ics(self):
        p = make()
        p.add({"title": "Mathe; Blatt, 4", "minutes": 30})
        p.set_reminders(True, "17:30")
        text = p.ics(NOW)
        self.assertIn("BEGIN:VALARM", text)
        self.assertIn("Mathe\; Blatt\\, 4", text)
        self.assertIn("RRULE:FREQ=DAILY", text)
        self.assertIn("DTSTART:20261005T173000", text)
        self.assertTrue(all(len(ln.encode()) <= 75 for ln in text.split("\r\n")))

    def test_parse_tasks_json(self):
        raw = 'Hier: [{"title":"A","minutes":20,"due":"2026-10-09"},{"nix":1}] fertig'
        self.assertEqual(pl.parse_tasks_json(raw)[0]["title"], "A")
        self.assertEqual(pl.parse_tasks_json("kein json"), [])
        self.assertEqual(pl.parse_tasks_json("[kaputt"), [])

    def test_planner_block(self):
        self.assertEqual(pl.planner_block([], date(2026, 10, 5)), "")
        block = pl.planner_block([{"title": "Test", "subject": "Bio", "due": "2026-10-09"}],
                                 date(2026, 10, 5))
        self.assertIn("Test (Bio), fällig 2026-10-09", block)


if __name__ == "__main__":
    unittest.main()
