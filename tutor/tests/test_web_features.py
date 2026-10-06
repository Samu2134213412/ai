"""Schutz vor versehentlich gelöschten Funktionen der Oberfläche (so etwas fiel bei einem Umbau früher durch)."""

import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"

REQUIRED = {
    "app.js": ["api", "stream", "run", "readPage", "annotate", "onTap", "setPage", "openFile", "exportPng", "newTask", "giveUp",
               "switchModel", "grabFrame", "stopCapture", "toggleCapture", "pickWindow", "pollShot", "b64Blob", "showRoute", "pickNote"],
    "planner.js": ["load", "render", "setFocus", "paintFocus", "initSettings", "askNotifications", "tick", "openPlanner"],
    "overlay.js": ["readScreen", "lookAtScreen", "tidyScreen", "startPick", "annotate", "ask", "grabScreen", "tipTo", "goHome"],
    "tidy.js": ["build", "preview", "request", "exportFile", "open"],
    "notes.js": ["parse", "render", "buildPdf", "toPdf"],
    "vision.js": ["enhance", "crop", "bands", "tiles", "snapshot"],
}


class WebFeatures(unittest.TestCase):
    def test_functions_are_still_there(self):
        for fname, names in REQUIRED.items():
            src = (WEB / fname).read_text()
            for n in names:
                self.assertRegex(src, rf"(function\s+{n}\b|(const|let)\s+{n}\b|^\s+{n}\s*[:(,])", f"{fname}: {n} fehlt")

    def test_ui_still_wires_the_key_features(self):
        app = (WEB / "app.js").read_text()
        for needle in ("/api/shot", "/api/shot.img", "getDisplayMedia", "TutorDesktop.listWindows", "TutorNative.latestFrame",
                       "/api/page", "/api/chat", "$(\"capture\").addEventListener"):
            self.assertIn(needle, app, needle)

    def test_every_element_id_used_in_js_exists_in_html(self):
        html = (WEB / "index.html").read_text()
        for fname in ("app.js", "planner.js"):
            for id_ in set(re.findall(r'\$\("(\w+)"\)', (WEB / fname).read_text())):
                self.assertIn(f'id="{id_}"', html, f"{fname}: #{id_} fehlt in index.html")
        ohtml = (WEB / "overlay.html").read_text()
        for id_ in set(re.findall(r'\$\("(\w+)"\)', (WEB / "overlay.js").read_text())):
            self.assertIn(f'id="{id_}"', ohtml, f"overlay.js: #{id_} fehlt in overlay.html")


if __name__ == "__main__":
    unittest.main()
