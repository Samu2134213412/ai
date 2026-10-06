#!/usr/bin/env node
/* Tutor-Server starten:
     node server/index.js                       nur dieser PC (http://127.0.0.1:8780)
     node server/index.js --host 0.0.0.0        auch im WLAN (Handy, iPad) – zeigt einen QR-Code
   Enter drücken = neuen Kopplungs-Link für ein weiteres Gerät; Name + Enter = neue Person (eigener Verlauf). */
const path = require("node:path");
const { createTutorServer, lanAddresses } = require("./server.js");

function arg(name, def) { const i = process.argv.indexOf("--" + name); return i > 0 ? process.argv[i + 1] : def; }
if (process.argv.includes("--help")) {
  console.log("Optionen: --host <ip> (127.0.0.1 | 0.0.0.0)  --port <n> (8780)  --ollama <url> (http://127.0.0.1:11434)\n          --data <ordner> (./tutor-data)  --www <ordner> (../web)");
  process.exit(0);
}

(async () => {
  const host = arg("host", "127.0.0.1");
  const srv = createTutorServer({ wwwDir: path.resolve(arg("www", path.join(__dirname, "..", "web"))),
    dataDir: path.resolve(arg("data", "tutor-data")), ollama: arg("ollama", process.env.OLLAMA_HOST_URL || "http://127.0.0.1:11434"),
    host, port: Number(arg("port", 8780)) });
  const { port } = await srv.start();
  let QR = null; try { QR = require("qrcode"); } catch (e) { /* optional */ }

  const show = async (code, label) => {
    const urls = srv.pairingUrls(code);
    console.log(`\n${label} – Link (10 Minuten gültig, einmalig):`);
    urls.forEach((u) => console.log("  " + u));
    if (QR && host === "0.0.0.0" && urls[0]) console.log(await QR.toString(urls[0], { type: "terminal", small: true }));
  };
  console.log(`Tutor-Server läuft auf Port ${port} (${host === "0.0.0.0" ? "WLAN: " + lanAddresses().join(", ") : "nur dieser PC"}).`);
  console.log(`Ollama: ${arg("ollama", "http://127.0.0.1:11434")}`);
  await show(srv.createPairing({ forOwner: true }), "Dieses Gerät koppeln");
  console.log("\nEnter = weiteres Gerät koppeln · Name + Enter = neue Person · Strg+C beendet.");
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", async (line) => {
    const name = line.trim();
    await show(srv.createPairing(name ? { name } : { forOwner: true }), name ? `Neue Person „${name}“` : "Weiteres Gerät");
  });
  process.on("SIGINT", async () => { await srv.stop(); process.exit(0); });
})().catch((e) => { console.error("Fehler:", e.message); process.exit(1); });
