"""Ein-Befehl-Installer: install.sh wird wirklich ausgeführt (lokal, mit fertiger Datei);
install.ps1 lässt sich hier nicht ausführen und wird statisch geprüft."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallSh(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bash") and shutil.which("tar"), "bash/tar fehlen")
    def test_local_install_puts_folder_and_program_on_desktop(self):
        tmp = Path(tempfile.mkdtemp())
        prebuilt = tmp / "fertig.bin"
        prebuilt.write_text("programm")
        desktop = tmp / "Desktop"
        env = {**os.environ, "TUTOR_DESKTOP_DIR": str(desktop), "TUTOR_PREBUILT": str(prebuilt)}
        r = subprocess.run(["bash", str(ROOT / "install.sh")], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        name = "Tutor.dmg" if os.uname().sysname == "Darwin" else "Tutor.AppImage"
        self.assertTrue((desktop / name).is_file())
        self.assertTrue((desktop / "Tutor" / name).is_file())
        self.assertTrue((desktop / "Tutor" / "desktop" / "package.json").is_file())
        self.assertTrue((desktop / "Tutor" / "web" / "index.html").is_file())
        self.assertFalse((desktop / "Tutor" / "desktop" / "node_modules").exists())
        # zweiter Lauf (Aktualisierung) funktioniert auch und lässt Nutzerdaten stehen
        (desktop / "Tutor" / "sessions").mkdir(exist_ok=True)
        (desktop / "Tutor" / "sessions" / "meins.json").write_text("{}")
        r = subprocess.run(["bash", str(ROOT / "install.sh")], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((desktop / "Tutor" / "sessions" / "meins.json").exists())

    def test_running_from_the_installed_folder_is_fine(self):
        if not shutil.which("bash"):
            self.skipTest("bash fehlt")
        tmp = Path(tempfile.mkdtemp())
        (tmp / "x").write_text("p")
        env = {**os.environ, "TUTOR_DESKTOP_DIR": str(tmp / "D"), "TUTOR_PREBUILT": str(tmp / "x")}
        subprocess.run(["bash", str(ROOT / "install.sh")], env=env, check=True, capture_output=True)
        again = subprocess.run(["bash", str(tmp / "D" / "Tutor" / "install.sh")], env=env, capture_output=True, text=True)
        self.assertEqual(again.returncode, 0, again.stderr)


class InstallPs1(unittest.TestCase):
    def setUp(self):
        self.src = (ROOT / "install.ps1").read_text()

    def test_balanced_and_ascii(self):
        code = re.sub(r"#.*", "", re.sub(r'"(?:`.|[^"`])*"', '""', self.src))
        code = re.sub(r"'[^']*'", "''", code)
        for a, b in ("{}", "()", "[]"):
            self.assertEqual(code.count(a), code.count(b), a + b)
        self.assertFalse(re.search(r"[^\x00-\x7F]", self.src), "Nicht-ASCII-Zeichen (Encoding-Risiko bei irm | iex)")

    def test_does_what_it_promises(self):
        for needle in ('GetFolderPath("Desktop")', '"Tutor.exe"', "robocopy", "dist:exe", "TUTOR_PREBUILT",
                       "releases", "OpenJS.NodeJS.LTS", "finally"):
            self.assertIn(needle, self.src, needle)
        self.assertNotIn("param(", self.src.lower())      # param-Block würde bei `irm | iex` stören

    def test_npm_scripts_and_artifact_names_match(self):
        pkg = json.loads((ROOT / "desktop" / "package.json").read_text())
        self.assertIn("electron-builder --win portable", pkg["scripts"]["dist:exe"])
        self.assertEqual(pkg["build"]["portable"]["artifactName"], "Tutor.exe")
        self.assertEqual(pkg["build"]["appImage"]["artifactName"], "Tutor.AppImage")
        self.assertEqual(pkg["build"]["dmg"]["artifactName"], "Tutor.dmg")
        self.assertIsNone(pkg["build"]["publish"])          # sonst scheitert der AppImage-Build
        self.assertIn(r'desktop\dist\Tutor.exe', self.src)

    def test_cmd_wrapper_and_readme_commands(self):
        cmd = (ROOT / "Tutor-installieren.cmd").read_bytes()
        self.assertIn(b"install.ps1", cmd)
        self.assertIn(b"\r\n", cmd)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("tutor/install.ps1 | iex", readme)
        self.assertIn("tutor/install.sh | bash", readme)


if __name__ == "__main__":
    unittest.main()
