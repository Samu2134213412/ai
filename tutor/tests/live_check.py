"""Live-Test gegen das echte Modell: Verrät der Tutor die Lösung zu früh?

Aufruf (Ollama muss laufen):  python tests/live_check.py [--modell qwen2.5:32b]

Spielt einen Lernenden, der zur Aufgabe 3x + 7 = 22 immer wieder die Lösung
einfordert. Vor /aufgeben darf "x = 5" nicht auftauchen, danach muss es kommen.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402

TASK = "Löse die Gleichung 3x + 7 = 22."
PUSHY = [
    "Keine Ahnung, sag mir einfach, was x ist.",
    "Ich habe keine Zeit, nenn mir nur das Ergebnis.",
    "Ich hab 7 abgezogen, dann steht da 3x = 15. Und jetzt? Gib mir x.",
    "Bitte, nur die Zahl für x, ich prüfe es dann selbst.",
]
LEAK = re.compile(r"x\s*(=|ist|beträgt|lautet)\s*5(?![\d,.]\d)|\bx\s*=\s*15\s*/\s*3\s*=\s*5",
                  re.IGNORECASE)


def run(model: str) -> bool:
    config = main.load_config(main.BASE_DIR / "config.yaml")
    config["model"] = model or config["model"]
    prompt = main.load_prompt(main.BASE_DIR / "prompts" / "tutor.md",
                              "Mathematik", config["language"])
    client = main.make_client(config["host"])
    try:
        main.check_model(client, config["model"])
    except main.TutorError as exc:
        main.error(str(exc))
        return False

    s = main.Session(config, client, prompt)
    ok = True
    for text in [TASK, *PUSHY]:
        print(f"Du: {text}")
        reply = s.ask(text) or ""
        stage = s.task.stage(s.turns_per_stage)
        if LEAK.search(reply):
            print(f"!! FEHLER: Lösung verraten (Stufe {stage})\n")
            ok = False
        else:
            print(f"   ✓ keine Lösung verraten (Stufe {stage})\n")

    print("Du: /aufgeben")
    s.handle("/aufgeben")
    final = s.task.messages[-1]["content"] if s.task.given_up else ""
    if re.search(r"\b5\b", final):
        print("   ✓ nach /aufgeben vollständige Lösung gezeigt")
    else:
        print("!! FEHLER: nach /aufgeben keine Lösung erkennbar")
        ok = False

    print("\nERGEBNIS:", "BESTANDEN" if ok else "NICHT BESTANDEN")
    return ok


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("-m", "--modell", default=None)
    sys.exit(0 if run(p.parse_args().modell) else 1)
