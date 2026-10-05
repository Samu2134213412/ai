import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node nicht installiert")
class ExtensionLogic(unittest.TestCase):
    def test_node_suite(self):
        r = subprocess.run(["node", "--test", str(ROOT / "tests" / "extension.test.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_manifest_permissions_minimal(self):
        import json
        m = json.loads((ROOT / "extension" / "manifest.json").read_text())
        self.assertEqual(m["manifest_version"], 3)
        self.assertEqual(sorted(m["permissions"]), ["alarms", "notifications", "storage", "tabs"])
        self.assertTrue(all("127.0.0.1" in h or "localhost" in h for h in m["host_permissions"]))


if __name__ == "__main__":
    unittest.main()
