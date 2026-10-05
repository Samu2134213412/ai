"""iPad-App: JS-Tests laufen lassen und die Swift-Plugins statisch gegen die JS-Brücke prüfen
(Swift selbst lässt sich nur mit Xcode kompilieren)."""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFT = ROOT / "app" / "plugins" / "tutor-native" / "ios" / "Sources" / "TutorNativePlugin"
EXT = ROOT / "app" / "native" / "BroadcastExtension"


@unittest.skipUnless(shutil.which("node"), "node nicht installiert")
class BackendJs(unittest.TestCase):
    def test_node_suite(self):
        r = subprocess.run(["node", "--test", str(ROOT / "tests" / "backend.test.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-1000:])


class SwiftBridge(unittest.TestCase):
    def plugins(self):
        out = {}
        for f in SWIFT.glob("*.swift"):
            src = f.read_text()
            js = re.search(r'jsName\s*=\s*"(\w+)"', src)
            if js:
                out[js.group(1)] = {
                    "methods": set(re.findall(r'CAPPluginMethod\(name:\s*"(\w+)"', src)),
                    "funcs": set(re.findall(r"@objc func (\w+)\(_ call: CAPPluginCall\)", src)),
                    "class": re.search(r'@objc\((\w+)\)', src).group(1),
                    "id": re.search(r'identifier\s*=\s*"(\w+)"', src).group(1),
                    "file": f.name,
                }
        return out

    def test_every_declared_method_is_implemented(self):
        plugins = self.plugins()
        self.assertEqual(set(plugins), {"FocusShield", "ScreenShare"})
        for name, p in plugins.items():
            self.assertEqual(p["methods"], p["funcs"], name)
            self.assertEqual(p["class"], p["id"], name)

    def test_js_only_calls_existing_methods(self):
        js = (ROOT / "web" / "native.js").read_text()
        plugins = self.plugins()
        for var, name in (("Shield", "FocusShield"), ("Share", "ScreenShare")):
            for method in set(re.findall(rf"\b{var}\.(\w+)\(", js)):
                self.assertIn(method, plugins[name]["methods"], f"{var}.{method}")
        for name in ("Preferences", "LocalNotifications", "FocusShield", "ScreenShare"):
            self.assertIn(f'plugin("{name}")', js)

    def test_braces_and_parens_balanced(self):
        for f in [*SWIFT.glob("*.swift"), *EXT.glob("*.swift")]:
            src = re.sub(r'"(?:\\.|[^"\\])*"', '""', re.sub(r"//.*", "", f.read_text()))
            for a, b in ("{}", "()", "[]"):
                self.assertEqual(src.count(a), src.count(b), f"{f.name}: {a}{b}")

    def test_app_group_and_extension_ids_consistent(self):
        share = (SWIFT / "ScreenSharePlugin.swift").read_text()
        handler = (EXT / "SampleHandler.swift").read_text()
        group = re.search(r'appGroup\s*=\s*"([\w.]+)"', share).group(1)
        self.assertIn(f'"{group}"', handler)
        ext_id = re.search(r'extensionBundleId\s*=\s*"([\w.]+)"', share).group(1)
        app_id = json.loads((ROOT / "app" / "capacitor.config.json").read_text())["appId"]
        self.assertEqual(ext_id, app_id + ".Broadcast")
        self.assertIn(group, (ROOT / "app" / "README.md").read_text())

    def test_package_matches_capacitor_expectations(self):
        pkg = json.loads((ROOT / "app" / "plugins" / "tutor-native" / "package.json").read_text())
        self.assertEqual(pkg["capacitor"]["ios"]["src"], "ios")
        swift = (ROOT / "app" / "plugins" / "tutor-native" / "Package.swift").read_text()
        self.assertIn('path: "ios/Sources/TutorNativePlugin"', swift)
        self.assertIn(".iOS(.v15)", swift)   # gleiche Mindestversion wie die App (sonst SPM-Fehler)

    def test_ios_project_is_ipad_with_multitasking(self):
        proj = (ROOT / "app" / "ios" / "App" / "App.xcodeproj" / "project.pbxproj").read_text()
        self.assertNotIn('TARGETED_DEVICE_FAMILY = "1,2"', proj)
        self.assertIn("TARGETED_DEVICE_FAMILY = 2;", proj)
        plist = (ROOT / "app" / "ios" / "App" / "App" / "Info.plist").read_text()
        self.assertNotIn("UIRequiresFullScreen", plist)      # Split View mit GoodNotes
        for key in ("NSAllowsLocalNetworking", "NSLocalNetworkUsageDescription", "NSCameraUsageDescription"):
            self.assertIn(key, plist)


if __name__ == "__main__":
    unittest.main()
