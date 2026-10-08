// Kopiert wllama (llama.cpp als WebAssembly, MIT) nach web/vendor/wllama – damit Tablets im Klassen-Pool ein kleines
// Modell im Browser rechnen können, ohne Internet/CDN. Quelle: desktop/node_modules (npm i in desktop/).
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const nm = join(root, "desktop", "node_modules", "@wllama");
const out = join(root, "web", "vendor", "wllama");
if (!existsSync(join(nm, "wllama", "esm", "index.min.js"))) {
  console.warn("wllama fehlt – in desktop/ zuerst `npm i` ausführen. (Tablets können sonst nicht mitrechnen.)");
  process.exit(0);
}
mkdirSync(join(out, "compat"), { recursive: true });
cpSync(join(nm, "wllama", "esm", "index.min.js"), join(out, "index.js"));
cpSync(join(nm, "wllama", "esm", "wasm", "wllama.wasm"), join(out, "wllama.wasm"));
cpSync(join(nm, "wllama", "LICENCE"), join(out, "LICENCE"));
if (existsSync(join(nm, "wllama-compat", "wasm"))) {             // Safari/iPad: ohne JSPI → Kompatibilitäts-Build
  cpSync(join(nm, "wllama-compat", "wasm", "wllama.js"), join(out, "compat", "wllama.js"));
  cpSync(join(nm, "wllama-compat", "wasm", "wllama.wasm"), join(out, "compat", "wllama.wasm"));
}
console.log("wllama kopiert:", out);
