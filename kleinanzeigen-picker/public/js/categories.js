import { extractModel, normalize } from './query.js';

// Rough parcel prices for when a listing only says "Versand möglich".
// Shown as "geschätzt" in the UI and overridable per item.
export const SHIPPING_ESTIMATE = { NONE: 0, S: 5.49, M: 6.99, L: 10.49, XL: 16.99 };

export const CATEGORIES = [
  { id: 'cpu', label: 'CPU', choose: 'CPU wählen', size: 'S' },
  { id: 'cooler', label: 'CPU-Kühler', choose: 'CPU-Kühler wählen', size: 'M' },
  { id: 'mainboard', label: 'Mainboard', choose: 'Mainboard wählen', size: 'M' },
  { id: 'ram', label: 'Arbeitsspeicher', choose: 'Arbeitsspeicher wählen', size: 'S' },
  { id: 'storage', label: 'Speicher', choose: 'SSD / HDD wählen', size: 'S' },
  { id: 'gpu', label: 'Grafikkarte', choose: 'Grafikkarte wählen', size: 'M' },
  { id: 'case', label: 'Gehäuse', choose: 'Gehäuse wählen', size: 'XL' },
  { id: 'psu', label: 'Netzteil', choose: 'Netzteil wählen', size: 'M' },
  { id: 'os', label: 'Betriebssystem', choose: 'Betriebssystem wählen', size: 'NONE' },
  { id: 'monitor', label: 'Monitor', choose: 'Monitor wählen', size: 'L' },
  { id: 'other', label: 'Sonstiges', choose: 'Lüfter, Peripherie … hinzufügen', size: 'M' },
];

export function categoryById(id) {
  return CATEGORIES.find((c) => c.id === id) ?? CATEGORIES.at(-1);
}

export function shippingEstimate(categoryId) {
  return SHIPPING_ESTIMATE[categoryById(categoryId).size];
}

// Kleinanzeigen's own "Art" field under PC-Zubehör & Software.
const ART_RULES = [
  ['gpu', /grafikkarte/],
  ['cpu', /prozessor|cpu/],
  ['mainboard', /mainboard/],
  ['ram', /^speicher$|arbeitsspeicher/],
  ['storage', /festplatte|laufwerk/],
  ['case', /gehäuse/],
  ['monitor', /monitor/],
  ['psu', /netzteil/],
];

// Title keywords, checked in order.
const KEYWORD_RULES = [
  ['os', /\bwindows\s?(1[01]|7|8)\b|\blizenz|betriebssystem|product key/],
  ['gpu', /grafikkarte|geforce|radeon/],
  ['monitor', /monitor|bildschirm|\b\d{2}\s?zoll\b|\b(144|165|170|240|360)\s?hz\b/],
  ['cooler', /kühler|cooler|\baio\b|wasserkühlung|noctua|dark rock|liquid freezer/],
  ['cpu', /\bryzen\b|prozessor|\bcpu\b|threadripper|xeon/],
  ['storage', /\bssd\b|\bhdd\b|nvme|festplatte/],
  ['mainboard', /mainboard|motherboard|\b[abhxzq][1-9]\d0[a-z]?\b|\blga\s?1[27]\d{2}\b/],
  ['ram', /\bddr[345]\b|arbeitsspeicher|\bram\b|\bdimm\b/],
  ['storage', /\bm 2\b|\b\d+\s?tb\b/],
  ['psu', /netzteil|\bpsu\b|\b\d{3,4}\s?w(att)?\b/],
  ['case', /gehäuse|\bcase\b|\btower\b/],
];

export function classify(title, art) {
  const t = normalize(title);
  const a = normalize(art);
  const keyword = KEYWORD_RULES.find(([, re]) => re.test(t))?.[0];
  const fromArt = a ? ART_RULES.find(([, re]) => re.test(a))?.[0] : undefined;
  if (fromArt === 'cpu' && keyword === 'cooler') return 'cooler';
  if (fromArt) return fromArt;
  const model = extractModel(title);
  if (model) return model.kind;
  return keyword ?? 'other';
}
