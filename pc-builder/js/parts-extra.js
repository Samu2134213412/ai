// Teile, die nach dem Stand des PCPartPicker-Datensatzes (Juli 2025) erschienen
// sind, plus genaue Gehäusemaße für beliebte Gehäuse. Recherchiert im Oktober 2026.
// Preise: US-Einführungspreis grob in EUR umgerechnet, null = unbekannt
// (über „Aktuelle Preise abrufen“ nachladen).
//
// Quellen:
//   Ryzen 7 9850X3D: tomshardware.com/pc-components/cpus/amd-ryzen-7-9850x3d-review, windowscentral.com (Start 29.01.2026, $499)
//   Ryzen 9 9950X3D2: tomshardware.com (…amd-reveals-usd899-price-tag-for-ryzen-9-9950x3d2…), videocardz.com (Start 22.04.2026, 200 W)
//   Core Ultra 200S Plus: hothardware.com/reviews/intel-core-ultra-plus-arrow-lake-refresh-review, videocardz.com ($299/$199, 26.03.2026)
//   Ryzen 9700F/9500F: en.wikipedia.org/wiki/Template:AMD_Ryzen_9000_Series
//   RX 9050: videocardz.com/newz/amd-radeon-rx-9050-launches-at-279…, 91mobiles.com (92 W, 8 GB)
//   RX 9060: techpowerup.com/339587, techspot.com/review/3060-amd-radeon-9060 (132 W, nur Fertig-PCs)
//   Arc Pro B70: pcpowerup.co.uk (32 GB, 350 W, $949.99)
//   Samsung 9100 Pro: samsung.com, thepcenthusiast.com/best-nvme-gen5-m-2-ssd
//   Gehäusemaße: newegg.com/insider/best-pc-cases-airflow-2026, maxmybuild.com, verdictbits.com/reviews/best-pc-cases-2026

const usd = (n) => Math.round(n * 0.86);

export const EXTRA_PARTS = [
  // --- CPU ---
  { id: "x-cpu-r7-9850x3d", cat: "cpu", brand: "AMD", name: "Ryzen 7 9850X3D", price: usd(499), socket: "AM5", tdp: 120, cores: 8, igpu: true, isNew: true },
  { id: "x-cpu-r9-9950x3d2", cat: "cpu", brand: "AMD", name: "Ryzen 9 9950X3D2 Dual Edition", price: usd(899), socket: "AM5", tdp: 200, cores: 16, igpu: true, isNew: true },
  { id: "x-cpu-r7-9700f", cat: "cpu", brand: "AMD", name: "Ryzen 7 9700F", price: null, socket: "AM5", tdp: 65, cores: 8, igpu: false, isNew: true },
  { id: "x-cpu-r5-9500f", cat: "cpu", brand: "AMD", name: "Ryzen 5 9500F", price: null, socket: "AM5", tdp: 65, cores: 6, igpu: false, isNew: true },
  { id: "x-cpu-u7-270kp", cat: "cpu", brand: "Intel", name: "Core Ultra 7 270K Plus", price: usd(299), socket: "LGA1851", tdp: 125, cores: 24, igpu: true, isNew: true },
  { id: "x-cpu-u5-250kp", cat: "cpu", brand: "Intel", name: "Core Ultra 5 250K Plus", price: usd(199), socket: "LGA1851", tdp: 125, cores: 18, igpu: true, isNew: true },
  { id: "x-cpu-u5-250kfp", cat: "cpu", brand: "Intel", name: "Core Ultra 5 250KF Plus", price: null, socket: "LGA1851", tdp: 125, cores: 18, igpu: false, isNew: true },

  // --- GPU ---
  { id: "x-gpu-rx9050", cat: "gpu", brand: "AMD", name: "Radeon RX 9050 8 GB", price: usd(279), tdp: 92, lengthMm: 230, vramGB: 8, isNew: true },
  { id: "x-gpu-rx9060", cat: "gpu", brand: "AMD", name: "Radeon RX 9060 8 GB (nur Fertig-PCs)", price: null, tdp: 132, lengthMm: 240, vramGB: 8, isNew: true },
  { id: "x-gpu-arc-pro-b70", cat: "gpu", brand: "Intel", name: "Arc Pro B70 32 GB", price: usd(950), tdp: 350, lengthMm: 290, vramGB: 32, isNew: true },

  // --- Speicher ---
  { id: "x-ssd-9100pro-1tb", cat: "storage", brand: "Samsung", name: "9100 Pro 1 TB (PCIe 5.0)", price: usd(250), kind: "m2", sizeGB: 1000, watt: 8, isNew: true },
  { id: "x-ssd-9100pro-2tb", cat: "storage", brand: "Samsung", name: "9100 Pro 2 TB (PCIe 5.0)", price: usd(400), kind: "m2", sizeGB: 2000, watt: 8, isNew: true },
  { id: "x-ssd-9100pro-4tb", cat: "storage", brand: "Samsung", name: "9100 Pro 4 TB (PCIe 5.0)", price: null, kind: "m2", sizeGB: 4000, watt: 9, isNew: true },
  { id: "x-ssd-9100pro-8tb", cat: "storage", brand: "Samsung", name: "9100 Pro 8 TB (PCIe 5.0)", price: null, kind: "m2", sizeGB: 8000, watt: 9, isNew: true },

  // --- Gehäuse ---
  { id: "x-case-summit", cat: "case", brand: "Fractal", name: "Design Summit", price: null, formFactors: ["ATX", "mATX", "ITX"], maxGpuMm: 425, maxCoolerMm: 173, isNew: true },
];

// Genaue Maße für Gehäuse aus dem PCPartPicker-Datensatz, der nur den Typ kennt.
// Schlüssel: Anfang des vollen Namens (Hersteller + Modell), ohne Groß-/Kleinschreibung.
export const CASE_SPECS = {
  "phanteks xt pro ultra": { maxGpuMm: 520, maxCoolerMm: 185 },
  "phanteks eclipse g500a": { maxGpuMm: 435, maxCoolerMm: 185 },
  "nzxt h7 flow": { maxGpuMm: 410, maxCoolerMm: 185 },
  "corsair frame 4000d": { maxGpuMm: 405, maxCoolerMm: 170 },
  "montech air 903 max": { maxGpuMm: 400, maxCoolerMm: 180 },
  "lian li lancool 207": { maxGpuMm: 375, maxCoolerMm: 173 },
  "silverstone fara 515xr": { maxGpuMm: 350, maxCoolerMm: 165 },
  "fractal design terra": { maxGpuMm: 233, maxCoolerMm: 77, formFactors: ["ITX"] },
  "fractal design north": { maxGpuMm: 355, maxCoolerMm: 170 },
  "corsair 4000d airflow": { maxGpuMm: 360, maxCoolerMm: 170 },
  "lian li o11 dynamic evo": { maxGpuMm: 420, maxCoolerMm: 167 },
  "lian li a3-matx": { maxGpuMm: 415, maxCoolerMm: 165 },
  "cooler master masterbox nr200p": { maxGpuMm: 336, maxCoolerMm: 155, formFactors: ["ITX"] },
};

export function applyCaseSpecs(part) {
  if (part.cat !== "case") return part;
  const full = `${part.brand} ${part.name}`.toLowerCase();
  const key = Object.keys(CASE_SPECS).find((k) => full.startsWith(k));
  return key ? { ...part, ...CASE_SPECS[key], estimated: false } : part;
}
