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


if __name__ == "__main__":
    unittest.main()
