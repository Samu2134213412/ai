"""Tutor-Server (Node): Tests laufen lassen und prüfen, dass er alles bedient, was die Oberfläche aufruft."""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


@unittest.skipUnless(shutil.which("node"), "node nicht installiert")
class ServerSuite(unittest.TestCase):
    def test_node_suite(self):
        r = subprocess.run(["node", "--test", "--test-timeout=30000", str(ROOT / "server" / "test" / "server.test.js"), str(ROOT / "server" / "test" / "pool.test.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-1000:])


class RouteCoverage(unittest.TestCase):
    def handled(self):
        backend = (WEB / "backend-local.js").read_text()
        server = (ROOT / "server" / "server.js").read_text()
        groups = re.findall(r"\^\\/api\\/\(([\w|]+)\)", backend)
        return backend, server, [g.split("|") for g in groups]

    def test_every_route_the_ui_calls_is_served(self):
        backend, server, groups = self.handled()
        used = set()
        for f in ("app.js", "planner.js", "overlay.js"):
            used |= set(re.findall(r"""["'`](/api/[\w./-]+)["'`]""", (WEB / f).read_text()))
        self.assertGreater(len(used), 15)
        missing = []
        for path in sorted(used):
            first = path.split("/")[2]
            ok = f'"{path}"' in backend or f'"{path}"' in server or any(first in g for g in groups)
            if not ok:
                missing.append(path)
        self.assertEqual(missing, [])

    def test_server_does_not_expose_the_ollama_host_to_clients(self):
        server = (ROOT / "server" / "server.js").read_text()
        self.assertIn("lockHost: true", server)


class TabletHelper(unittest.TestCase):
    """Tablets rechnen im Klassen-Pool mit: Oberfläche, Server-Routen und Bibliothek passen zusammen."""

    def test_helper_is_wired_and_uses_only_local_assets(self):
        html = (WEB / "index.html").read_text()
        js = (WEB / "helper.js").read_text()
        self.assertIn('<script src="/helper.js"></script>', html)
        for el in ("helpSettings", "hOn", "hModel", "hState"):
            self.assertIn(f'id="{el}"', html)
        for route in ("/api/pool/status", "/api/pool/pull", "/api/pool/push", "/api/pool/model.gguf"):
            self.assertIn(route, js)
            self.assertIn(route.replace("?", ""), (ROOT / "server" / "server.js").read_text())
        self.assertNotIn("cdn.jsdelivr", js)                       # Schulnetz ohne Internet: alles vom PC
        self.assertIn("setCompat", js)                             # Safari/iPad: Kompatibilitäts-Build
        self.assertIn("window.TutorDesktop", js)                   # PC-App trägt mit Ollama bei, nicht über den Browser

    def test_only_small_models_for_tablets(self):
        src = (ROOT / "server" / "pullers.js").read_text()
        self.assertIn('const PULL_MODELS = ["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b"]', src)

    def test_vendor_script_and_gitignore(self):
        self.assertTrue((ROOT / "scripts" / "vendor-wllama.mjs").exists())
        self.assertIn("tutor/web/vendor/", (ROOT.parent / ".gitignore").read_text())
        self.assertIn("vendor-wllama.mjs", (ROOT / "desktop" / "package.json").read_text())


if __name__ == "__main__":
    unittest.main()
