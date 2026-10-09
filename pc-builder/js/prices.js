// Aktuelle Preise aus deutschen Shops und Preisvergleichen, per Claude mit Websuche.
// Ergebnisse werden im Browser zwischengespeichert, damit nicht jede Ansicht
// erneut sucht.
import Anthropic from "@anthropic-ai/sdk";

const MODEL = "claude-opus-5-5";
const CACHE_KEY = "pc-builder.prices";
const MAX_AGE_MS = 24 * 60 * 60 * 1000; // nach einem Tag gilt ein Preis als veraltet

const SHOPS = [
  "geizhals.de", "idealo.de", "mindfactory.de", "alternate.de", "caseking.de",
  "notebooksbilliger.de", "computeruniverse.net", "cyberport.de", "amazon.de", "galaxus.de",
];

const REPORT_TOOL = {
  name: "preise_melden",
  description: "Meldet die gefundenen aktuellen Preise. Einmal am Ende aufrufen, mit einem Eintrag pro angefragtem Teil.",
  strict: true,
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["preise"],
    properties: {
      preise: {
        type: "array",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["id", "gefunden", "preis", "shop", "url", "hinweis"],
          properties: {
            id: { type: "string", description: "ID des Teils aus der Anfrage" },
            gefunden: { type: "boolean", description: "false, wenn kein aktuelles Angebot für genau dieses Modell gefunden wurde" },
            preis: { type: ["number", "null"], description: "günstigster aktueller Preis in EUR inkl. MwSt., lieferbar" },
            shop: { type: ["string", "null"] },
            url: { type: ["string", "null"], description: "Link zum Angebot oder zur Preisvergleichsseite" },
            hinweis: { type: "string", description: "kurz, z. B. Variante, Lieferzeit oder warum nichts gefunden wurde" },
          },
        },
      },
    },
  },
};

const SYSTEM = `Du suchst aktuelle Preise für PC-Teile in Deutschland.
Nutze die Websuche, bevorzugt Preisvergleiche (geizhals.de, idealo.de), sonst große deutsche Shops.
Nimm den günstigsten lieferbaren Neupreis inkl. MwSt. für genau das genannte Modell – gleiche Kapazität, gleiche Variante.
Gebrauchtware, Marketplace-Angebote ohne Lieferbarkeit und andere Varianten zählen nicht.
Findest du für ein Teil nichts Verlässliches, setze gefunden auf false statt zu schätzen.
Rufe am Ende preise_melden mit einem Eintrag pro Teil auf.`;

export function readPriceCache() {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY)) || {};
  } catch {
    return {};
  }
}

function writePriceCache(cache) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch {}
}

export const isFresh = (entry) => entry && Date.now() - entry.at < MAX_AGE_MS;

// parts: Teile aus dem Build. Liefert den aktualisierten Cache.
export async function fetchPrices(apiKey, parts, onProgress = () => {}) {
  const client = new Anthropic({ apiKey, dangerouslyAllowBrowser: true });
  const list = parts.map((p) => `${p.id} | ${p.brand} ${p.name}`).join("\n");
  const messages = [{ role: "user", content: `Finde die aktuellen Preise für diese Teile (id | Name):\n${list}` }];
  const params = {
    model: MODEL,
    max_tokens: 16000,
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    system: SYSTEM,
    output_config: { effort: "low" },
    tools: [
      { type: "web_search_20260209", name: "web_search", max_uses: Math.min(20, parts.length * 3), allowed_domains: SHOPS, user_location: { type: "approximate", country: "DE" } },
      { type: "web_fetch_20260209", name: "web_fetch", max_uses: parts.length * 2, allowed_domains: SHOPS },
      REPORT_TOOL,
    ],
  };

  // Server-Werkzeuge können pausieren (pause_turn) – dann einfach fortsetzen.
  for (let round = 0; round < 6; round++) {
    onProgress(round);
    const res = await client.beta.messages.create({ ...params, messages });
    if (res.stop_reason === "refusal") throw new Error("Die Preisabfrage wurde abgelehnt.");
    const report = res.content.find((b) => b.type === "tool_use" && b.name === REPORT_TOOL.name);
    if (report) return storeReport(report.input.preise, parts);
    if (res.stop_reason === "pause_turn") {
      messages.push({ role: "assistant", content: res.content });
      continue;
    }
    if (res.stop_reason === "max_tokens") throw new Error("Antwort abgeschnitten – bitte weniger Teile auf einmal.");
    // Ohne Bericht beendet: einmal ausdrücklich um den Bericht bitten.
    messages.push({ role: "assistant", content: res.content }, { role: "user", content: "Bitte melde die Ergebnisse jetzt mit preise_melden." });
  }
  throw new Error("Keine Preise erhalten.");
}

function storeReport(rows, parts) {
  const cache = readPriceCache();
  const ids = new Set(parts.map((p) => p.id));
  const at = Date.now();
  for (const r of rows) {
    if (!ids.has(r.id)) continue;
    cache[r.id] = r.gefunden && typeof r.preis === "number"
      ? { price: Math.round(r.preis * 100) / 100, shop: r.shop, url: safeUrl(r.url), note: r.hinweis, at }
      : { price: null, note: r.hinweis || "nicht gefunden", at };
  }
  writePriceCache(cache);
  return cache;
}

// Nur http(s)-Links übernehmen, damit nichts anderes im Link landet.
function safeUrl(u) {
  try {
    const url = new URL(u);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}
