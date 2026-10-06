// Kopiert den Tutor-Server (server/) neben die Desktop-App, damit er mit eingepackt wird.
import { cpSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "desktop", "server");
rmSync(out, { recursive: true, force: true });
cpSync(join(root, "server"), out, { recursive: true, filter: (src) => !/[\\/](test|node_modules)([\\/]|$)/.test(src) });
console.log("server kopiert:", out);
