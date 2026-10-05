"""Lernplaner: Aufgaben, Wochenplan, Fokus-Sitzung, Kalender-Export (.ics).

Alles lokal in einer JSON-Datei (data/planner.json). Die Planung ist bewusst
deterministisch (früheste Frist zuerst), das Sprachmodell liest nur Aufgaben
aus Seiten aus.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_BLOCKLIST = [
    "youtube.com", "youtu.be", "instagram.com", "tiktok.com", "netflix.com",
    "twitch.tv", "x.com", "twitter.com", "facebook.com", "reddit.com", "snapchat.com",
]
MAX_BLOCK_MIN = 45          # längste Lerneinheit am Stück
BREAK_MIN = 10


def _clean_date(value) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return ""


def _clean_task(raw: dict) -> dict | None:
    title = str(raw.get("title", "")).strip()[:120]
    if not title:
        return None
    try:
        minutes = max(5, min(480, int(raw.get("minutes") or 30)))
    except (TypeError, ValueError):
        minutes = 30
    return {"title": title, "subject": str(raw.get("subject", "")).strip()[:40],
            "due": _clean_date(raw.get("due", "")), "minutes": minutes}


def parse_tasks_json(text: str) -> list[dict]:
    """Holt eine Aufgabenliste aus einer Modellantwort (Fließtext + JSON-Array)."""
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    tasks = [_clean_task(x) for x in data if isinstance(x, dict)]
    return [t for t in tasks if t]


class Planner:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = {"tasks": [], "reminders": {"enabled": False, "time": "16:00"},
                     "blocklist": list(DEFAULT_BLOCKLIST), "focus": {"ends_at": 0, "minutes": 0}}
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # -- Aufgaben ------------------------------------------------------------

    def tasks(self) -> list[dict]:
        with self.lock:
            return [dict(t) for t in self.data["tasks"]]

    def add(self, raw: dict) -> dict | None:
        task = _clean_task(raw)
        if not task:
            return None
        task.update(id=uuid.uuid4().hex[:8], done=False,
                    created=datetime.now().isoformat(timespec="seconds"))
        with self.lock:
            self.data["tasks"].append(task)
            self._save()
        return dict(task)

    def update(self, task_id: str, fields: dict) -> bool:
        with self.lock:
            for t in self.data["tasks"]:
                if t["id"] == task_id:
                    if "done" in fields:
                        t["done"] = bool(fields["done"])
                    merged = _clean_task({**t, **fields})
                    if merged:
                        t.update(merged)
                    self._save()
                    return True
        return False

    def delete(self, task_id: str) -> bool:
        with self.lock:
            n = len(self.data["tasks"])
            self.data["tasks"] = [t for t in self.data["tasks"] if t["id"] != task_id]
            self._save()
            return len(self.data["tasks"]) < n

    def open_tasks(self) -> list[dict]:
        far = "9999-12-31"
        return sorted((t for t in self.tasks() if not t["done"]),
                      key=lambda t: (t["due"] or far, t["created"]))

    # -- Einstellungen / Fokus ------------------------------------------------

    def set_reminders(self, enabled: bool, time: str) -> None:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time or ""):
            time = "16:00"
        with self.lock:
            self.data["reminders"] = {"enabled": bool(enabled), "time": time}
            self._save()

    def set_blocklist(self, items) -> list[str]:
        out = []
        for raw in items if isinstance(items, list) else str(items).split():
            host = re.sub(r"^(https?://)?(www\.)?", "", str(raw).strip().lower()).split("/")[0]
            if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host) and host not in out:
                out.append(host)
        with self.lock:
            self.data["blocklist"] = out
            self._save()
        return out

    def start_focus(self, minutes: int, now: float) -> None:
        minutes = max(1, min(240, int(minutes)))
        with self.lock:
            self.data["focus"] = {"ends_at": now + minutes * 60, "minutes": minutes}
            self._save()

    def stop_focus(self) -> None:
        with self.lock:
            self.data["focus"] = {"ends_at": 0, "minutes": 0}
            self._save()

    def focus(self, now: float) -> dict:
        with self.lock:
            ends = self.data["focus"].get("ends_at", 0)
            remaining = max(0, int(ends - now))
            return {"active": remaining > 0, "remaining": remaining, "ends_at": ends,
                    "minutes": self.data["focus"].get("minutes", 0),
                    "blocklist": list(self.data["blocklist"])}

    # -- Plan ---------------------------------------------------------------

    def plan(self, now: datetime, days: int = 7, daily_minutes: int = 90,
             start: str = "16:00") -> dict:
        """Früheste Frist zuerst; Einheiten ≤ 45 min mit 10 min Pause, Tageslimit."""
        sh, sm = (int(x) for x in start.split(":"))
        blocks, unplaced = [], []
        used: dict[str, int] = {}                      # Minuten pro Tag
        cursor: dict[str, datetime] = {}               # nächster Start pro Tag
        for t in self.open_tasks():
            left = t["minutes"]
            last_day = date.fromisoformat(t["due"]) if t["due"] else None
            placed_any = False
            for i in range(days):
                day = now.date() + timedelta(days=i)
                if last_day and day > last_day:
                    break
                key = day.isoformat()
                begin = datetime.combine(day, datetime.min.time()).replace(hour=sh, minute=sm)
                if day == now.date():
                    begin = max(begin, now.replace(second=0, microsecond=0) + timedelta(minutes=5))
                cur = cursor.get(key, begin)
                while left > 0 and used.get(key, 0) < daily_minutes and cur.date() == day:
                    chunk = min(left, MAX_BLOCK_MIN, daily_minutes - used.get(key, 0))
                    if chunk < 5:
                        break
                    blocks.append({"date": key, "start": cur.strftime("%H:%M"), "minutes": chunk,
                                   "task_id": t["id"], "title": t["title"], "subject": t["subject"]})
                    used[key] = used.get(key, 0) + chunk
                    cur += timedelta(minutes=chunk + BREAK_MIN)
                    left -= chunk
                    placed_any = True
                cursor[key] = cur
                if left <= 0:
                    break
            if left > 0:
                unplaced.append({"task_id": t["id"], "title": t["title"], "missing": left,
                                 "reason": "bis zur Frist nicht genug Zeit" if last_day else "Plan zu kurz"})
            _ = placed_any
        blocks.sort(key=lambda b: (b["date"], b["start"]))
        return {"blocks": blocks, "unplaced": unplaced}

    # -- Kalender ---------------------------------------------------------------

    def ics(self, now: datetime, **plan_kwargs) -> str:
        plan = self.plan(now, **plan_kwargs)
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//tutor//DE", "CALSCALE:GREGORIAN"]
        stamp = now.strftime("%Y%m%dT%H%M%S")

        def esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")

        def event(uid, start, minutes, summary, alarm_min, extra=()):
            end = start + timedelta(minutes=minutes)
            lines.extend(["BEGIN:VEVENT", f"UID:{uid}@tutor", f"DTSTAMP:{stamp}",
                          f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}",
                          f"SUMMARY:{esc(summary)}", *extra,
                          "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(summary)}",
                          f"TRIGGER:-PT{alarm_min}M", "END:VALARM", "END:VEVENT"])

        for b in plan["blocks"]:
            start = datetime.fromisoformat(f"{b['date']}T{b['start']}:00")
            label = f"Lernen: {b['title']}" + (f" ({b['subject']})" if b["subject"] else "")
            event(f"{b['task_id']}-{b['date']}-{b['start']}", start, b["minutes"], label, 10)
        r = self.data["reminders"]
        if r["enabled"]:
            h, m = (int(x) for x in r["time"].split(":"))
            start = now.replace(hour=h, minute=m, second=0, microsecond=0)
            event("daily", start, 15, "Zeit zum Lernen 📚", 0, ["RRULE:FREQ=DAILY"])
        lines.append("END:VCALENDAR")
        folded = []
        for ln in lines:
            while len(ln.encode()) > 74:
                cut = 74
                while len(ln[:cut].encode()) > 74:
                    cut -= 1
                folded.append(ln[:cut]); ln = " " + ln[cut:]
            folded.append(ln)
        return "\r\n".join(folded) + "\r\n"


def planner_block(tasks: list[dict], today: date) -> str:
    """Kurzer Kontext für den Tutor-Prompt: was liegt an?"""
    if not tasks:
        return ""
    rows = []
    for t in tasks[:6]:
        due = f", fällig {t['due']}" if t["due"] else ""
        rows.append(f"- {t['title']}{' (' + t['subject'] + ')' if t['subject'] else ''}{due}")
    return ("\n\n# Offene Aufgaben des Lernenden (aus dem Planer)\n"
            f"Heute ist {today.isoformat()}. Nur erwähnen, wenn der Lernende nach Planung "
            "fragt oder eine Frist nah ist; kurz, ohne Druck.\n" + "\n".join(rows) + "\n")
