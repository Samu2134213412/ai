#!/usr/bin/env python3
"""tutor – ein Lern-Tutor im Terminal, der lokal über Ollama läuft.

Der Tutor gibt keine fertigen Lösungen, sondern führt in Stufen
(Leitfrage → Denkanstoß → Teilschritt) zum Selbermachen.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

try:
    import readline  # noqa: F401  – Pfeiltasten/Verlauf in input()
except ImportError:  # Windows ohne pyreadline
    pass

import ollama

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_CONFIG = {
    "host": "http://localhost:11434",
    "model": "qwen2.5:32b",
    "vision_model": "qwen2.5vl:7b",
    "temperature": 0.6,
    "subject": "",
    "language": "Deutsch",
    "hints": {"turns_per_stage": 2, "min_attempts_before_giving_up": 2},
    "sessions": {"autosave": False, "directory": "sessions"},
    "web": {"host": "127.0.0.1", "port": 8765},
}

GIVEN_UP = 4  # Pseudo-Stufe: Lösung freigegeben

STAGE_TEXT = {
    1: "Stufe 1 – Leitfrage. Stelle genau EINE Leitfrage. Keine Formeln, keinen "
       "Code, keine Zwischenergebnisse der Aufgabe. Ist noch unklar, was der "
       "Lernende versucht hat und wo es hängt, frage zuerst danach.",
    2: "Stufe 2 – Denkanstoß. Nenne das passende Konzept oder eine Analogie, "
       "gern mit einem einfachen Beispiel mit ANDEREN Werten als in der Aufgabe. "
       "Rechne oder programmiere die Aufgabe selbst nicht vor.",
    3: "Stufe 3 – Teilschritt. Du darfst genau EINEN Zwischenschritt vormachen. "
       "Weitere Schritte und das Endergebnis muss der Lernende selbst finden.",
    GIVEN_UP: "AUFGEGEBEN – der Lernende hat per /aufgeben aufgegeben. Zeige jetzt "
              "die vollständige Lösung Schritt für Schritt, begründe jeden Schritt "
              "kurz und schließe mit einer kurzen Verständnisfrage.",
}

HELP = """\
Befehle:
  /hilfe            diese Hilfe
  /neu [Aufgabe]    neue Aufgabe beginnen (Hinweisstufe wird zurückgesetzt)
  /aufgeben         komplette Lösung mit Erklärung anzeigen lassen
  /modell <name>    Modell wechseln, z. B. /modell qwen2.5:14b
  /status           aktuelle Aufgabe, Versuche und Hinweisstufe
  /speichern        Verlauf nach sessions/*.json speichern
  /exit             beenden (auch /quit oder Strg+D)
Alles andere wird als Nachricht an den Tutor geschickt."""


# --------------------------------------------------------------------------- #
# Ausgabe
# --------------------------------------------------------------------------- #

_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def info(text: str) -> None:
    print(_c("2", text))


def error(text: str) -> None:
    print(_c("31", text), file=sys.stderr)


# --------------------------------------------------------------------------- #
# Konfiguration & Prompt
# --------------------------------------------------------------------------- #

def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path) -> dict:
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    with path.open(encoding="utf-8") as fh:
        return _merge(DEFAULT_CONFIG, yaml.safe_load(fh) or {})


def load_prompt(path: Path, subject: str, language: str) -> str:
    text = path.read_text(encoding="utf-8")
    fach = f" für {subject}" if subject else ""
    return text.replace("{{fach}}", fach).replace("{{sprache}}", language)


# --------------------------------------------------------------------------- #
# Aufgaben- und Hinweisstufen-Logik
# --------------------------------------------------------------------------- #

@dataclass
class Task:
    title: str = ""
    attempts: int = 0          # Nachrichten des Lernenden zu dieser Aufgabe
    given_up: bool = False
    messages: list = field(default_factory=list)  # user/assistant-Verlauf
    page_notes: list = field(default_factory=list)  # gelesene Seiteninhalte (Web-UI)

    def stage(self, turns_per_stage: int) -> int:
        """Aktuelle Hinweisstufe 1–3 bzw. GIVEN_UP."""
        if self.given_up:
            return GIVEN_UP
        per = max(1, int(turns_per_stage))
        return min(1 + max(self.attempts - 1, 0) // per, 3)


def page_block(task: Task) -> str:
    """Von der Bildanalyse gelesene Seiteninhalte (GoodNotes-Seite o. ä.)."""
    if not task.page_notes:
        return ""
    notes = "\n".join(f"- {n}" for n in task.page_notes[-4:])
    return (
        "\n\n# Seite des Lernenden (vom Programm per Bildanalyse gelesen)\n"
        "Der Lernende hat dir seine Notizseite gezeigt. Das ist die Abschrift "
        "(kann Lesefehler enthalten – frag bei Unklarem nach):\n" + notes + "\n"
        "Beziehe dich konkret auf Stellen der Seite. Für Lösungen gelten trotzdem "
        "dieselben Stufenregeln.\n"
    )


def status_block(task: Task, turns_per_stage: int) -> str:
    stage = task.stage(turns_per_stage)
    return (
        "\n\n# Status-Block (vom Programm gesetzt)\n"
        f"Nachricht Nr. {task.attempts} des Lernenden zu dieser Aufgabe.\n"
        f"Erlaubte Hilfe: {STAGE_TEXT[stage]}\n"
        + ("" if stage == GIVEN_UP else
           "Gehe NICHT über diese Stufe hinaus und nenne kein Endergebnis.\n")
    )


# --------------------------------------------------------------------------- #
# Ollama
# --------------------------------------------------------------------------- #

class TutorError(Exception):
    """Fehler mit verständlicher Meldung für den Lernenden."""


def _full_name(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


def _connection_hint(host: str) -> str:
    return (f"Ollama ist unter {host} nicht erreichbar.\n"
            "  → Ollama starten (App öffnen oder `ollama serve`) und erneut versuchen.")


def _missing_hint(model: str) -> str:
    return (f"Das Modell '{model}' ist nicht installiert.\n"
            f"  → ollama pull {model}")


def installed_models(client) -> list[str]:
    try:
        resp = client.list()
    except (ConnectionError, OSError) as exc:
        raise TutorError(_connection_hint(client_host(client))) from exc
    models = resp["models"] if isinstance(resp, dict) else resp.models
    names = []
    for m in models:
        name = (m.get("model") or m.get("name")) if isinstance(m, dict) else m.model
        if name:
            names.append(name)
    return names


def client_host(client) -> str:
    return getattr(client, "tutor_host", "http://localhost:11434")


def check_model(client, model: str) -> None:
    if _full_name(model) not in {_full_name(n) for n in installed_models(client)}:
        raise TutorError(_missing_hint(model))


def describe_image(client, model: str, image_b64: str, focus: str = "") -> str:
    """Lässt ein Vision-Modell eine Notizseite lesen (Text, Formeln, Handschrift)."""
    prompt = (
        "Das Bild ist eine Notiz-/Arbeitsseite eines Lernenden (z. B. aus GoodNotes). "
        "Schreibe ab, was darauf steht: Aufgabenstellung, Rechenschritte, Handschrift, "
        "Formeln, Skizzen (kurz beschrieben). Keine Bewertung, keine Lösung, "
        "nichts dazuerfinden. Antworte auf Deutsch, höchstens 200 Wörter."
    )
    if focus:
        prompt += f" Konzentriere dich besonders auf: {focus}"
    try:
        resp = client.chat(model=model, messages=[
            {"role": "user", "content": prompt, "images": [image_b64]}],
            options={"temperature": 0.1})
    except ollama.ResponseError as exc:
        if exc.status_code == 404:
            raise TutorError(_missing_hint(model)) from exc
        raise TutorError(f"Ollama-Fehler: {exc.error}") from exc
    except (ConnectionError, OSError) as exc:
        raise TutorError(_connection_hint(client_host(client))) from exc
    msg = resp["message"] if isinstance(resp, dict) else resp.message
    content = msg["content"] if isinstance(msg, dict) else msg.content
    return (content or "").strip()


def stream_reply(client, model: str, messages: list, temperature: float):
    """Liefert die Antwort des Modells Stück für Stück."""
    try:
        for chunk in client.chat(model=model, messages=messages, stream=True,
                                 options={"temperature": temperature}):
            piece = chunk["message"]["content"]
            if piece:
                yield piece
    except ollama.ResponseError as exc:
        if exc.status_code == 404:
            raise TutorError(_missing_hint(model)) from exc
        raise TutorError(f"Ollama-Fehler: {exc.error}") from exc
    except (ConnectionError, OSError) as exc:
        raise TutorError(_connection_hint(client_host(client))) from exc


# --------------------------------------------------------------------------- #
# Sitzung
# --------------------------------------------------------------------------- #

class Session:
    def __init__(self, config: dict, client, system_prompt: str, out=sys.stdout):
        self.config = config
        self.client = client
        self.system_prompt = system_prompt
        self.model = config["model"]
        self.out = out
        self.tasks: list[Task] = [Task()]
        self.confirm_give_up = False
        self.started = datetime.now()
        self.saved_to: Path | None = None

    @property
    def task(self) -> Task:
        return self.tasks[-1]

    @property
    def turns_per_stage(self) -> int:
        return self.config["hints"]["turns_per_stage"]

    # -- Modell-Anfrage -----------------------------------------------------

    def build_messages(self) -> list[dict]:
        system = (self.system_prompt + page_block(self.task)
                  + status_block(self.task, self.turns_per_stage))
        return [{"role": "system", "content": system}, *self.task.messages]

    def stream_turn(self, text: str):
        """Eine Runde: Nachricht des Lernenden → Antwort stückweise (Generator).

        Bei TutorError wird die Runde zurückgenommen (zählt nicht als Versuch).
        Bricht der Aufrufer den Generator ab, bleibt die Teilantwort im Verlauf.
        """
        task = self.task
        if not task.title:
            task.title = text[:80]
        task.attempts += 1
        task.messages.append({"role": "user", "content": text})
        parts: list[str] = []
        try:
            for piece in stream_reply(self.client, self.model, self.build_messages(),
                                      self.config["temperature"]):
                parts.append(piece)
                yield piece
        except TutorError:
            task.messages.pop()
            task.attempts -= 1
            raise
        finally:
            if parts:
                task.messages.append({"role": "assistant", "content": "".join(parts)})

    def ask(self, text: str) -> str | None:
        """Terminal-Variante: streamt die Antwort direkt nach self.out."""
        self.out.write(_c("36", "Tutor: "))
        self.out.flush()
        parts: list[str] = []
        try:
            for piece in self.stream_turn(text):
                parts.append(piece)
                self.out.write(piece)
                self.out.flush()
        except TutorError as exc:
            self.out.write("\n")
            error(str(exc))
            return None
        except KeyboardInterrupt:
            self.out.write(_c("2", " [abgebrochen]"))
        self.out.write("\n\n")
        return "".join(parts)

    # -- Befehle ------------------------------------------------------------

    def handle(self, line: str) -> bool:
        """Verarbeitet eine Eingabe. Gibt False zurück, wenn beendet werden soll."""
        line = line.strip()
        if not line:
            return True
        if not line.startswith("/"):
            self.confirm_give_up = False
            self.ask(line)
            return True

        cmd, _, arg = line.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        if cmd != "/aufgeben":
            self.confirm_give_up = False

        if cmd in ("/exit", "/quit", "/ende"):
            return False
        if cmd == "/hilfe":
            print(HELP)
        elif cmd == "/neu":
            self.new_task(arg)
        elif cmd == "/aufgeben":
            self.give_up()
        elif cmd == "/modell":
            self.switch_model(arg)
        elif cmd == "/status":
            self.print_status()
        elif cmd == "/speichern":
            self.save()
        else:
            error(f"Unbekannter Befehl {cmd}. /hilfe zeigt alle Befehle.")
        return True

    def new_task(self, text: str = "") -> None:
        if self.task.messages:
            self.tasks.append(Task())
        else:
            self.task.title, self.task.given_up = "", False
        info("Neue Aufgabe – Hinweisstufe zurückgesetzt.")
        if text:
            self.ask(text)
        else:
            info("Beschreibe die Aufgabe und was du schon versucht hast.")

    GIVE_UP_TEXT = ("Ich gebe auf. Bitte zeig mir die vollständige Lösung "
                    "und erkläre jeden Schritt.")

    def request_give_up(self) -> tuple[str, str]:
        """Prüft /aufgeben. Rückgabe (status, meldung); status 'ok' = freigegeben,
        danach muss GIVE_UP_TEXT als Nachricht gesendet werden."""
        task = self.task
        if task.attempts == 0:
            return "none", "Es gibt noch keine Aufgabe. Beschreibe zuerst, woran du arbeitest."
        if task.given_up:
            return "done", "Die Lösung ist für diese Aufgabe bereits freigegeben. /neu für die nächste."
        minimum = self.config["hints"]["min_attempts_before_giving_up"]
        if task.attempts < minimum and not self.confirm_give_up:
            self.confirm_give_up = True
            return "confirm", (f"Du hast erst {task.attempts} Versuch(e). Noch ein Anlauf "
                               "lohnt sich oft. Zum Bestätigen nochmal /aufgeben eingeben.")
        self.confirm_give_up = False
        task.given_up = True
        return "ok", ""

    def give_up(self) -> None:
        status, msg = self.request_give_up()
        if status != "ok":
            info(msg)
            return
        self.ask(self.GIVE_UP_TEXT)

    def switch_model(self, name: str) -> None:
        if not name:
            info(f"Aktuelles Modell: {self.model}. Wechseln mit /modell <name>.")
            return
        try:
            check_model(self.client, name)
        except TutorError as exc:
            error(str(exc))
            return
        self.model = name
        info(f"Modell gewechselt zu {name}.")

    def print_status(self) -> None:
        t = self.task
        stage = t.stage(self.turns_per_stage)
        label = "Lösung freigegeben" if stage == GIVEN_UP else f"{stage} von 3"
        info(f"Modell: {self.model} | Aufgabe {len(self.tasks)}: "
             f"{t.title or '(noch keine)'} | Versuche: {t.attempts} | "
             f"Hinweisstufe: {label}")

    # -- Speichern ----------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "started": self.started.isoformat(timespec="seconds"),
            "saved": datetime.now().isoformat(timespec="seconds"),
            "model": self.model,
            "subject": self.config.get("subject", ""),
            "tasks": [asdict(t) for t in self.tasks if t.messages],
        }

    def save(self) -> Path | None:
        data = self.to_dict()
        if not data["tasks"]:
            info("Noch nichts zu speichern.")
            return None
        directory = Path(self.config["sessions"]["directory"])
        if not directory.is_absolute():
            directory = BASE_DIR / directory
        directory.mkdir(parents=True, exist_ok=True)
        if self.saved_to is None:
            self.saved_to = directory / f"{self.started:%Y-%m-%d_%H-%M-%S}.json"
        self.saved_to.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        info(f"Gespeichert: {self.saved_to}")
        return self.saved_to


# --------------------------------------------------------------------------- #
# Start
# --------------------------------------------------------------------------- #

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tutor", description="Lern-Tutor über Ollama")
    p.add_argument("--config", type=Path, default=BASE_DIR / "config.yaml")
    p.add_argument("--prompt", type=Path, default=BASE_DIR / "prompts" / "tutor.md")
    p.add_argument("-m", "--modell", dest="model", help="Modellname, z. B. qwen2.5:14b")
    p.add_argument("-f", "--fach", dest="subject", help="Fach/Thema")
    p.add_argument("-t", "--temperature", type=float)
    p.add_argument("-s", "--speichern", dest="autosave", action="store_true",
                   help="Verlauf beim Beenden in sessions/ speichern")
    return p.parse_args(argv)


def make_client(host: str):
    client = ollama.Client(host=host)
    client.tutor_host = host
    return client


def main(argv=None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    for key in ("model", "subject", "temperature"):
        if getattr(args, key) is not None:
            config[key] = getattr(args, key)
    if args.autosave:
        config["sessions"]["autosave"] = True

    try:
        prompt = load_prompt(args.prompt, config["subject"], config["language"])
    except OSError as exc:
        error(f"System-Prompt nicht lesbar: {exc}")
        return 1

    client = make_client(config["host"])
    try:
        check_model(client, config["model"])
    except TutorError as exc:
        error(str(exc))
        return 1

    session = Session(config, client, prompt)
    subject = f" · Fach: {config['subject']}" if config["subject"] else ""
    print(_c("1", f"Tutor bereit ({config['model']}{subject})."))
    info("Beschreibe deine Aufgabe und was du schon versucht hast. /hilfe zeigt die Befehle.\n")

    try:
        while True:
            try:
                line = input(_c("32", "Du: "))
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
            if not session.handle(line):
                break
    finally:
        if config["sessions"]["autosave"]:
            session.save()
    info("Bis bald!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
