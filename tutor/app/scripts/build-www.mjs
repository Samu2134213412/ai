// Kopiert die Web-Oberfläche (../web) und den System-Prompt nach www/ für Capacitor.
import { cpSync, rmSync, mkdirSync, copyFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const www = join(app, "www");
rmSync(www, { recursive: true, force: true });
cpSync(join(app, "..", "web"), www, { recursive: true });
mkdirSync(join(www, "prompts"), { recursive: true });
copyFileSync(join(app, "..", "prompts", "tutor.md"), join(www, "prompts", "tutor.md"));
writeFileSync(join(www, "manifest.webmanifest"), JSON.stringify({ name: "Tutor", short_name: "Tutor", start_url: "/", display: "standalone" }));
console.log("www/ gebaut");
