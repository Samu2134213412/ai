// Kopiert die Web-Oberfläche (web/) und den System-Prompt in einen Zielordner,
// den Capacitor (app/www) bzw. Electron (desktop/www) ausliefert.
// Aufruf: node scripts/build-www.mjs <zielordner>
import { cpSync, rmSync, mkdirSync, copyFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const target = process.argv[2];
if (!target) { console.error("Zielordner fehlt: node scripts/build-www.mjs <ordner>"); process.exit(1); }
const out = resolve(process.cwd(), target);
rmSync(out, { recursive: true, force: true });
cpSync(join(root, "web"), out, { recursive: true });
mkdirSync(join(out, "prompts"), { recursive: true });
copyFileSync(join(root, "prompts", "tutor.md"), join(out, "prompts", "tutor.md"));
writeFileSync(join(out, "manifest.webmanifest"),
  JSON.stringify({ name: "Tutor", short_name: "Tutor", start_url: "/", display: "standalone" }));
console.log("gebaut:", out);
