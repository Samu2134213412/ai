"""PC-Version: Node-Tests der Hauptprozess-Module + Konsistenz zwischen Oberfläche, Preload und main.js."""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESK = ROOT / "desktop"


@unittest.skipUnless(shutil.which("node"), "node nicht installiert")
class DesktopLib(unittest.TestCase):
    def test_node_suite(self):
        r = subprocess.run(["node", "--test", "--test-timeout=20000", str(DESK / "test" / "lib.test.js")],
                           capture_output=True, text=True, cwd=DESK)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-1000:])


class Bridge(unittest.TestCase):
    def test_ui_only_uses_exposed_functions(self):
        preload = (DESK / "preload.js").read_text()
        exposed = set(re.findall(r"^\s{2}(\w+):", preload.split("exposeInMainWorld")[1], re.M))
        used = set()
        for f in ("app.js", "planner.js", "native.js", "overlay.js"):
            src = (ROOT / "web" / f).read_text()
            used |= set(re.findall(r"\b(?:TutorDesktop|D)\.(\w+)", src))
        self.assertTrue(used, "keine Desktop-Aufrufe gefunden")
        self.assertLessEqual(used, exposed, used - exposed)

    def test_every_ipc_channel_has_a_handler(self):
        preload = (DESK / "preload.js").read_text()
        main = (DESK / "main.js").read_text()
        for kind, regex in (("send", r'ipcRenderer\.send\("([\w:]+)"'), ("invoke", r'ipcRenderer\.invoke\("([\w:]+)"')):
            for ch in re.findall(regex, preload):
                handler = f'ipcMain.{"on" if kind == "send" else "handle"}("{ch}"'
                self.assertIn(handler, main, ch)
        self.assertIn('send("focus:command"', main)
        self.assertIn('ipcRenderer.on("focus:command"', preload)

    def test_every_ipc_handler_checks_the_sender(self):
        main = (DESK / "main.js").read_text()
        handlers = re.findall(r'ipcMain\.(?:on|handle)\("([\w:]+)", (?:async )?\(e', main)
        self.assertGreaterEqual(len(handlers), 7)
        self.assertEqual(main.count("fromOurPage(e)"), len(handlers))      # jeder Handler prüft den Absender

    def test_lan_access_is_opt_in_and_server_is_protected(self):
        main = (DESK / "main.js").read_text()
        self.assertEqual(main.count("srv.enableLan("), 1)                  # nur im „Gerät koppeln“-Handler
        self.assertLess(main.index('ipcMain.handle("phone:start"'), main.index("srv.enableLan("))
        self.assertIn('host: "127.0.0.1"', main)                           # Standard: nur dieser PC
        server = (ROOT / "server" / "server.js").read_text() + (ROOT / "server" / "store.js").read_text()
        for needle in ("randomBytes", "timingSafeEqual", "HttpOnly", "SameSite=Lax", "sha256", "0o600"):
            self.assertIn(needle, server, needle)

    def test_overlay_window_is_transparent_click_through_and_on_top(self):
        main = (DESK / "main.js").read_text()
        overlay = main[main.index("function createOverlay"):main.index("function toggleOverlay")]
        for needle in ("transparent: true", "frame: false", "alwaysOnTop: true", "setIgnoreMouseEvents(true, { forward: true })",
                       "contextIsolation: true", "nodeIntegration: false", "sandbox: true", "overlay.html"):
            self.assertIn(needle, overlay, needle)
        html = (ROOT / "web" / "overlay.html").read_text()
        for src in ("/vision.js", "/overlay.js", "/overlay.css", "/style.css"):
            self.assertIn(src, html)
        capture = main[main.index('ipcMain.handle("overlay:capture"'):main.index("// Weiteres Gerät koppeln")]
        self.assertLess(capture.index("overlay.hide()"), capture.index("desktopCapturer.getSources"))   # Leiste nie im Foto
        self.assertIn("showInactive()", capture)                                                      # und danach ohne Fokusklau zurück

    def test_goodnotes_automation_is_opt_in_and_read_only(self):
        main = (DESK / "main.js").read_text()
        cfg = (DESK / "lib" / "config.js").read_text()
        self.assertIn("autoFocus: false, autoOverlay: false", cfg)                    # Voreinstellung: aus
        self.assertIn("startWatching()", main)
        for needle in ("desktopCapturer.getSources", "tasklist", '"ps"'):             # nur Fenster-/Prozessnamen lesen
            self.assertIn(needle, main[main.index("function startWatching"):main.index("app.whenReady")], needle)

    def test_no_os_input_control_in_the_project(self):
        """Der Tutor steuert keine Maus/Tastatur anderer Programme (z. B. GoodNotes) – bewusst nicht gebaut."""
        bad = ("nut-js", "robotjs", "SendInput", "CGEventPost", "xdotool", "pen:write", "setPosition(")
        for f in [*DESK.glob("*.js"), *(DESK / "lib").glob("*.js"), *(ROOT / "web").glob("*.js"), *(ROOT / "server").glob("*.js")]:
            src = f.read_text()
            for needle in bad:
                self.assertNotIn(needle, src, f"{f.name}: {needle}")
        self.assertNotIn("nut-tree", (DESK / "package.json").read_text())

    def test_secure_window_settings(self):
        main = (DESK / "main.js").read_text()
        for needle in ("contextIsolation: true", "nodeIntegration: false", "sandbox: true"):
            self.assertIn(needle, main)

    def test_packaging_config(self):
        pkg = json.loads((DESK / "package.json").read_text())
        files = pkg["build"]["files"]
        for need in ("main.js", "preload.js", "lib/**", "server/**", "www/**", "assets/**"):
            self.assertIn(need, files)
        for need in ("main.js", "preload.js", "assets/icon.png", "assets/icon.ico"):
            self.assertTrue((DESK / need).exists(), need)
        wf = (ROOT.parent / ".github" / "workflows" / "tutor-desktop.yml").read_text()
        for os_name in ("windows-latest", "macos-latest", "ubuntu-latest"):
            self.assertIn(os_name, wf)

    def test_extension_default_url_matches_desktop_port(self):
        ext = (ROOT / "extension" / "background.js").read_text()
        port = re.search(r"WANT_PORT = Number\(process\.env\.TUTOR_PORT\) \|\| (\d+)", (DESK / "main.js").read_text()).group(1)
        self.assertIn(f"127.0.0.1:{port}", ext)


if __name__ == "__main__":
    unittest.main()
