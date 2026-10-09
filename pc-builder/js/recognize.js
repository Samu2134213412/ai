// Foto-Erkennung: schickt ein Bild an Claude und bekommt die erkannten
// PC-Teile als JSON zurück – zugeordnet zu Katalog-IDs, wo möglich.
import Anthropic from "@anthropic-ai/sdk";
import { PARTS, specLine } from "./parts.js";

const MODEL = "claude-opus-5-5";
const MAX_EDGE = 1568; // größere Bilder bringen der Erkennung nichts, kosten aber Tokens

const SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["parts"],
  properties: {
    parts: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["category", "catalogId", "brand", "name", "confidence", "evidence", "specs"],
        properties: {
          category: { type: "string", enum: ["cpu", "mobo", "ram", "gpu", "storage", "cooler", "psu", "case"] },
          catalogId: { type: ["string", "null"], description: "ID aus dem Katalog, wenn exakt dasselbe Modell, sonst null" },
          brand: { type: "string" },
          name: { type: "string", description: "Modellbezeichnung, so genau wie auf dem Foto erkennbar" },
          confidence: { type: "string", enum: ["hoch", "mittel", "niedrig"] },
          evidence: { type: "string", description: "Woran das Teil erkannt wurde (Aufdruck, Form, Logo)" },
          specs: {
            type: "object",
            additionalProperties: false,
            description: "Geschätzte Daten für Teile ohne Katalog-ID; Felder, die nicht zur Kategorie passen, null",
            required: ["price", "socket", "memType", "formFactor", "tdp", "watt", "sizeGB", "lengthMm", "kind"],
            properties: {
              price: { type: ["number", "null"], description: "aktueller Neupreis in EUR, geschätzt" },
              socket: { type: ["string", "null"] },
              memType: { type: ["string", "null"], enum: ["DDR4", "DDR5", null] },
              formFactor: { type: ["string", "null"], enum: ["ATX", "mATX", "ITX", null] },
              tdp: { type: ["number", "null"], description: "CPU/GPU-Leistungsaufnahme in W" },
              watt: { type: ["number", "null"], description: "Netzteil-Nennleistung in W" },
              sizeGB: { type: ["number", "null"] },
              lengthMm: { type: ["number", "null"], description: "Grafikkartenlänge" },
              kind: { type: ["string", "null"], enum: ["m2", "sata", null] },
            },
          },
        },
      },
    },
  },
};

const SYSTEM = `Du erkennst PC-Hardware auf Fotos – Teile in einem offenen PC, auf dem Tisch oder in der Verpackung.
Nenne jedes klar sichtbare Teil einmal. Lies Aufdrucke, Aufkleber und Logos, um das genaue Modell zu bestimmen.
Gibt es das Modell im Katalog, setze catalogId; ein ähnliches Modell ist kein Treffer (dann null und Daten schätzen).
Wenn du ein Teil nur vermutest, setze confidence auf "niedrig" und sag in evidence, warum.
Kabel, Lüfter allein und Schrauben sind keine Teile. Ist kein PC-Teil zu sehen, gib eine leere Liste zurück.`;

function catalogText() {
  return PARTS.map((p) => `${p.id} | ${p.cat} | ${p.brand} ${p.name} | ${specLine(p)}`).join("\n");
}

// Bild verkleinern und als JPEG-Base64 liefern.
export async function fileToBase64(file) {
  const bmp = await createImageBitmap(file);
  const scale = Math.min(1, MAX_EDGE / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bmp.width * scale);
  canvas.height = Math.round(bmp.height * scale);
  canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.88);
  return { data: dataUrl.split(",")[1], preview: dataUrl };
}

export async function recognizeParts(apiKey, base64Jpeg) {
  // Der Schlüssel bleibt im Browser des Nutzers und geht nur an api.anthropic.com.
  const client = new Anthropic({ apiKey, dangerouslyAllowBrowser: true });

  const response = await client.beta.messages.create({
    model: MODEL,
    max_tokens: 16000,
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    system: SYSTEM,
    output_config: { effort: "medium", format: { type: "json_schema", schema: SCHEMA } },
    messages: [
      {
        role: "user",
        content: [
          { type: "text", text: `Katalog (id | Kategorie | Name | Daten):\n${catalogText()}` },
          { type: "image", source: { type: "base64", media_type: "image/jpeg", data: base64Jpeg } },
          { type: "text", text: "Welche PC-Teile sind auf diesem Foto?" },
        ],
      },
    ],
  });

  if (response.stop_reason === "refusal") throw new Error("Die Anfrage wurde abgelehnt. Bitte ein anderes Foto versuchen.");
  if (response.stop_reason === "max_tokens") throw new Error("Antwort wurde abgeschnitten. Bitte weniger Teile pro Foto.");
  const text = response.content.find((b) => b.type === "text")?.text;
  if (!text) throw new Error("Keine Antwort erhalten.");
  return JSON.parse(text).parts;
}

// Ein erkanntes Teil ohne Katalogeintrag in ein Katalog-kompatibles Teil umwandeln.
// Fehlende Werte bekommen vorsichtige Standardwerte, damit die Prüfung funktioniert.
export function toCustomPart(r) {
  const s = r.specs;
  const base = { id: `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`, cat: r.category, brand: r.brand, name: r.name, price: s.price ?? 0, custom: true };
  switch (r.category) {
    case "cpu": return { ...base, socket: s.socket ?? "?", tdp: s.tdp ?? 105, cores: 0, igpu: false };
    case "mobo": return { ...base, socket: s.socket ?? "?", memType: s.memType ?? "DDR5", formFactor: s.formFactor ?? "ATX", m2Slots: 2, ramSlots: 4 };
    case "ram": return { ...base, memType: s.memType ?? "DDR5", sizeGB: s.sizeGB ?? 16, sticks: 2, watt: 8 };
    case "gpu": return { ...base, tdp: s.tdp ?? 200, lengthMm: s.lengthMm ?? 300, vramGB: 0 };
    case "storage": return { ...base, kind: s.kind ?? "m2", sizeGB: s.sizeGB ?? 1000, watt: 6 };
    case "cooler": return { ...base, sockets: ["AM4", "AM5", "LGA1700", "LGA1851"], maxTdp: 200, heightMm: 155, watt: 4 };
    case "psu": return { ...base, watt: s.watt ?? 650, efficiency: "?" };
    case "case": return { ...base, formFactors: ["ATX", "mATX", "ITX"], maxGpuMm: 360, maxCoolerMm: 165 };
  }
}
