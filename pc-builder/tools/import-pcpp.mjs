#!/usr/bin/env node
// Importiert den PCPartPicker-Datensatz von github.com/docyx/pc-part-dataset
// und schreibt ihn als js/parts-db.js im Format der App.
//
//   node tools/import-pcpp.mjs                 # alle Teile
//   node tools/import-pcpp.mjs --nur-mit-preis # nur Teile mit aktuellem Preis
//   node tools/import-pcpp.mjs --dir <pfad>    # lokale Kopie von data/json statt Download
//
// Der Datensatz hat nicht alle Felder, die die Kompatibilitätsprüfung braucht
// (z. B. CPU-Sockel, GPU-Leistungsaufnahme, RAM-Typ des Mainboards). Diese
// werden hier aus Architektur, Chipsatz und Namen abgeleitet; was sich nicht
// ableiten lässt, wird als unbekannt markiert und bei der Prüfung übersprungen.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BASE = "https://raw.githubusercontent.com/docyx/pc-part-dataset/main/data/json/";
const USD_TO_EUR = 0.86; // grobe Umrechnung, US-Preise sind nur Richtwerte

const args = process.argv.slice(2);
const onlyPriced = args.includes("--nur-mit-preis");
const dirIdx = args.indexOf("--dir");
const localDir = dirIdx >= 0 ? args[dirIdx + 1] : null;
const outFile = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "js", "parts-db.js");

async function load(file) {
  if (localDir) return JSON.parse(await fs.readFile(path.join(localDir, `${file}.json`), "utf8"));
  const res = await fetch(BASE + file + ".json");
  if (!res.ok) throw new Error(`${file}.json: HTTP ${res.status}`);
  return res.json();
}

const eur = (usd) => (typeof usd === "number" ? Math.round(usd * USD_TO_EUR) : null);
const splitBrand = (full) => {
  const i = full.indexOf(" ");
  return i < 0 ? { brand: full, name: full } : { brand: full.slice(0, i), name: full.slice(i + 1) };
};
const range = (v) => (Array.isArray(v) ? v[v.length - 1] : v);

// ---------- CPU ----------

const ARCH_SOCKET = {
  "Zen 5": "AM5", "Zen 4": "AM5", "Zen 3": "AM4", "Zen 2": "AM4", "Zen+": "AM4", Zen: "AM4",
  "Arrow Lake": "LGA1851", "Raptor Lake Refresh": "LGA1700", "Raptor Lake": "LGA1700", "Alder Lake": "LGA1700",
  "Rocket Lake": "LGA1200", "Comet Lake": "LGA1200", "Coffee Lake Refresh": "LGA1151", "Coffee Lake": "LGA1151",
  "Kaby Lake": "LGA1151", Skylake: "LGA1151", "Cascade Lake": "LGA2066",
  "Haswell Refresh": "LGA1150", Haswell: "LGA1150", Broadwell: "LGA1150",
  "Ivy Bridge": "LGA1155", "Sandy Bridge": "LGA1155", Westmere: "LGA1156", Nehalem: "LGA1156",
  Core: "LGA775", Wolfdale: "LGA775", Yorkfield: "LGA775",
  Piledriver: "AM3+", Bulldozer: "AM3+", Steamroller: "FM2+", Excavator: "?", K10: "AM3",
};

function cpuSocket(c) {
  if (/Threadripper/i.test(c.name)) return /Zen 4|Zen 5/.test(c.microarchitecture) ? "sTR5" : "sTRX4";
  if (/Xeon/i.test(c.name)) return "?";
  if (c.microarchitecture === "Skylake" && /-\d{4}X/.test(c.name)) return "LGA2066";
  if (c.microarchitecture === "Haswell" && /-5\d{3}K?$/.test(c.name) && /i7-58|i7-59/.test(c.name)) return "LGA2011-3";
  return ARCH_SOCKET[c.microarchitecture] ?? "?";
}

// ---------- GPU-Leistungsaufnahme (Referenzwerte) ----------

const GPU_TDP = [
  [/RTX 5090/, 575], [/RTX 5080/, 360], [/RTX 5070 Ti/, 300], [/RTX 5070/, 250], [/RTX 5060 Ti/, 180], [/RTX 5060/, 145], [/RTX 5050/, 130],
  [/RTX 4090/, 450], [/RTX 4080/, 320], [/RTX 4070 Ti/, 285], [/RTX 4070 SUPER/i, 220], [/RTX 4070/, 200], [/RTX 4060 Ti/, 165], [/RTX 4060/, 115],
  [/RTX 3090 Ti/, 450], [/RTX 3090/, 350], [/RTX 3080 Ti/, 350], [/RTX 3080/, 320], [/RTX 3070 Ti/, 290], [/RTX 3070/, 220], [/RTX 3060 Ti/, 200], [/RTX 3060/, 170], [/RTX 3050/, 130],
  [/RTX 2080 Ti/, 250], [/RTX 2080/, 225], [/RTX 2070/, 190], [/RTX 2060/, 165],
  [/GTX 1660/, 120], [/GTX 1650/, 75], [/GTX 1080 Ti/, 250], [/GTX 1080/, 180], [/GTX 1070/, 160], [/GTX 1060/, 120], [/GTX 1050/, 75],
  [/GTX 9[78]0/, 165], [/GTX 9[56]0/, 100], [/GT \d{3,4}/, 30], [/TITAN/i, 280], [/Quadro|RTX A\d|RTX PRO/i, 200],
  [/RX 9070 XT/, 304], [/RX 9070/, 220], [/RX 9060 XT/, 160], [/RX 9060/, 130],
  [/RX 7900 XTX/, 355], [/RX 7900 XT/, 315], [/RX 7900 GRE/, 260], [/RX 7800 XT/, 263], [/RX 7700 XT/, 245], [/RX 7600 XT/, 190], [/RX 7600/, 165],
  [/RX 6950 XT/, 335], [/RX 6900 XT/, 300], [/RX 6800 XT/, 300], [/RX 6800/, 250], [/RX 6750/, 250], [/RX 6700/, 230], [/RX 6650/, 180], [/RX 6600/, 140], [/RX 6500/, 107], [/RX 6400/, 53],
  [/RX 5700/, 225], [/RX 5600/, 150], [/RX 5500/, 130], [/RX 590/, 225], [/RX 580/, 185], [/RX 570/, 150], [/RX 5[56]0/, 75], [/Vega 64/, 295], [/Vega 56/, 210], [/Radeon VII/, 300],
  [/R9 (390|290)/, 275], [/R9/, 200], [/R7/, 100],
  [/Arc B580/, 190], [/Arc B570/, 150], [/Arc A7[57]0/, 225], [/Arc A580/, 185], [/Arc A[34]\d0/, 75],
];

function gpuTdp(g) {
  for (const [re, w] of GPU_TDP) if (re.test(g.chipset)) return w;
  return g.memory >= 16 ? 250 : g.memory >= 8 ? 180 : 100;
}

// ---------- Mainboard ----------

const FORM = { ATX: "ATX", EATX: "EATX", "XL ATX": "EATX", "SSI EEB": "EATX", "SSI CEB": "EATX", HPTX: "EATX", "Micro ATX": "mATX", "Flex ATX": "mATX", "Mini ITX": "ITX", "Thin Mini ITX": "ITX", "Mini DTX": "ITX" };

function moboMemType(m) {
  if (/DDR4|D4\b/i.test(m.name)) return "DDR4";
  if (/DDR5|D5\b/i.test(m.name)) return "DDR5";
  if (["AM5", "LGA1851", "sTR5"].includes(m.socket)) return "DDR5";
  if (m.socket === "LGA1700") return "DDR5";
  if (["AM4", "LGA1200", "LGA1151", "LGA2066", "sTRX4", "TR4", "LGA2011-3"].includes(m.socket)) return "DDR4";
  if (["LGA775", "AM3/AM2+/AM2"].includes(m.socket)) return "DDR2";
  return "DDR3";
}

// ---------- Gehäuse ----------

function caseFit(type) {
  if (/Full Tower/.test(type)) return { formFactors: ["EATX", "ATX", "mATX", "ITX"], maxGpuMm: 420, maxCoolerMm: 180 };
  if (/^ATX/.test(type)) return { formFactors: ["ATX", "mATX", "ITX"], maxGpuMm: /Desktop|Mini/.test(type) ? 320 : 360, maxCoolerMm: /Desktop/.test(type) ? 120 : 165 };
  if (/^MicroATX/.test(type)) return { formFactors: ["mATX", "ITX"], maxGpuMm: /Slim|Desktop/.test(type) ? 250 : 330, maxCoolerMm: /Slim|Desktop/.test(type) ? 70 : 160 };
  if (/Mini ITX/.test(type)) return { formFactors: ["ITX"], maxGpuMm: /Desktop/.test(type) ? 280 : 320, maxCoolerMm: /Desktop/.test(type) ? 70 : 155 };
  if (/HTPC/.test(type)) return { formFactors: ["mATX", "ITX"], maxGpuMm: 250, maxCoolerMm: 70 };
  return { formFactors: ["ATX", "mATX", "ITX"], maxGpuMm: 360, maxCoolerMm: 165 };
}

// ---------- Umwandlung ----------

const CONVERT = {
  cpu: ["cpu", (c) => ({ ...splitBrand(c.name), socket: cpuSocket(c), tdp: c.tdp ?? 95, cores: c.core_count ?? 0, igpu: !!c.graphics })],
  motherboard: ["mobo", (m) => {
    const ff = FORM[m.form_factor] ?? "ATX";
    return { ...splitBrand(m.name), socket: m.socket ?? "?", memType: moboMemType(m), formFactor: ff, m2Slots: ff === "ITX" ? 2 : 3, ramSlots: m.memory_slots ?? 4 };
  }],
  memory: ["ram", (r) => {
    const [sticks, per] = r.modules ?? [2, 8];
    const gen = Array.isArray(r.speed) ? r.speed[0] : 4;
    return { ...splitBrand(r.name), memType: `DDR${gen}`, sizeGB: sticks * per, sticks, speed: Array.isArray(r.speed) ? r.speed[1] : null, watt: Math.max(3, sticks * 4) };
  }],
  "video-card": ["gpu", (g) => {
    const { brand, name } = splitBrand(g.name);
    return { brand, name: name.includes(g.chipset) ? name : `${name} ${g.chipset}`.trim(), tdp: gpuTdp(g), lengthMm: g.length ?? 280, vramGB: g.memory ?? 0 };
  }],
  "internal-hard-drive": ["storage", (s) => {
    const m2 = /M\.2/.test(`${s.form_factor} ${s.interface}`);
    return { ...splitBrand(s.name), kind: m2 ? "m2" : "sata", sizeGB: s.capacity ?? 0, watt: s.type === "SSD" ? (m2 ? 7 : 4) : 8, hdd: s.type !== "SSD" };
  }],
  "cpu-cooler": ["cooler", (c) => {
    const aio = typeof range(c.size) === "number" && range(c.size) >= 120;
    const rad = range(c.size);
    return { ...splitBrand(c.name), sockets: null, maxTdp: aio ? (rad >= 360 ? 300 : rad >= 280 ? 280 : rad >= 240 ? 250 : 160) : 200, heightMm: aio ? 0 : null, watt: aio ? 12 : 4 };
  }],
  "power-supply": ["psu", (p) => ({ ...splitBrand(p.name), watt: p.wattage ?? 500, efficiency: p.efficiency ? `80+ ${p.efficiency[0].toUpperCase()}${p.efficiency.slice(1)}` : "–" })],
  case: ["case", (c) => ({ ...splitBrand(c.name), ...caseFit(c.type ?? ""), estimated: true, type: c.type })],
};

const out = [];
for (const [file, [cat, fn]] of Object.entries(CONVERT)) {
  const rows = await load(file);
  let n = 0;
  rows.forEach((row, i) => {
    if (!row.name || (onlyPriced && typeof row.price !== "number")) return;
    out.push({ id: `pp-${cat}-${i}`, cat, price: eur(row.price), ...fn(row) });
    n++;
  });
  console.log(`${cat.padEnd(8)} ${String(n).padStart(6)} Teile`);
}

const header = `// Automatisch erzeugt von tools/import-pcpp.mjs – nicht von Hand bearbeiten.\n// Quelle: github.com/docyx/pc-part-dataset (Daten von PCPartPicker), Preise aus USD umgerechnet.\n`;
await fs.writeFile(outFile, `${header}export default ${JSON.stringify(out)};\n`);
console.log(`\n${out.length} Teile → ${path.relative(process.cwd(), outFile)}`);
