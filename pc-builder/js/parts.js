// Teile-Katalog. Preise sind Richtwerte in EUR (Stand Herbst 2026) und dienen
// nur zur Orientierung – für echte Preise eine Preis-API anbinden.
//
// Felder je Kategorie:
//   cpu:     socket, tdp, cores, igpu
//   mobo:    socket, memType, formFactor, m2Slots, ramSlots
//   ram:     memType, sizeGB, sticks, watt
//   gpu:     tdp, lengthMm, vramGB
//   storage: kind ("m2" | "sata"), sizeGB, watt
//   psu:     watt (Nennleistung), efficiency
//   case:    formFactors (unterstützt), maxGpuMm, maxCoolerMm
//   cooler:  sockets, maxTdp, heightMm (0 = AIO), watt

export const CATEGORIES = [
  { id: "cpu", label: "Prozessor", multi: false },
  { id: "mobo", label: "Mainboard", multi: false },
  { id: "ram", label: "Arbeitsspeicher", multi: false },
  { id: "gpu", label: "Grafikkarte", multi: false },
  { id: "storage", label: "Speicher", multi: true },
  { id: "cooler", label: "CPU-Kühler", multi: false },
  { id: "psu", label: "Netzteil", multi: false },
  { id: "case", label: "Gehäuse", multi: false },
];

export const PARTS = [
  // --- CPU ---
  { id: "cpu-r5-9600x", cat: "cpu", brand: "AMD", name: "Ryzen 5 9600X", price: 209, socket: "AM5", tdp: 65, cores: 6, igpu: true },
  { id: "cpu-r7-9700x", cat: "cpu", brand: "AMD", name: "Ryzen 7 9700X", price: 299, socket: "AM5", tdp: 65, cores: 8, igpu: true },
  { id: "cpu-r7-9800x3d", cat: "cpu", brand: "AMD", name: "Ryzen 7 9800X3D", price: 469, socket: "AM5", tdp: 120, cores: 8, igpu: true },
  { id: "cpu-r9-9950x", cat: "cpu", brand: "AMD", name: "Ryzen 9 9950X", price: 559, socket: "AM5", tdp: 170, cores: 16, igpu: true },
  { id: "cpu-r5-5600", cat: "cpu", brand: "AMD", name: "Ryzen 5 5600", price: 89, socket: "AM4", tdp: 65, cores: 6, igpu: false },
  { id: "cpu-r7-5800x3d", cat: "cpu", brand: "AMD", name: "Ryzen 7 5800X3D", price: 279, socket: "AM4", tdp: 105, cores: 8, igpu: false },
  { id: "cpu-u5-245k", cat: "cpu", brand: "Intel", name: "Core Ultra 5 245K", price: 249, socket: "LGA1851", tdp: 125, cores: 14, igpu: true },
  { id: "cpu-u7-265k", cat: "cpu", brand: "Intel", name: "Core Ultra 7 265K", price: 329, socket: "LGA1851", tdp: 125, cores: 20, igpu: true },
  { id: "cpu-u9-285k", cat: "cpu", brand: "Intel", name: "Core Ultra 9 285K", price: 549, socket: "LGA1851", tdp: 125, cores: 24, igpu: true },
  { id: "cpu-i5-14600k", cat: "cpu", brand: "Intel", name: "Core i5-14600K", price: 219, socket: "LGA1700", tdp: 125, cores: 14, igpu: true },
  { id: "cpu-i7-14700k", cat: "cpu", brand: "Intel", name: "Core i7-14700K", price: 339, socket: "LGA1700", tdp: 125, cores: 20, igpu: true },

  // --- Mainboard ---
  { id: "mobo-b650-plus", cat: "mobo", brand: "ASUS", name: "TUF Gaming B650-Plus WiFi", price: 179, socket: "AM5", memType: "DDR5", formFactor: "ATX", m2Slots: 3, ramSlots: 4 },
  { id: "mobo-b650m-mortar", cat: "mobo", brand: "MSI", name: "MAG B650M Mortar WiFi", price: 169, socket: "AM5", memType: "DDR5", formFactor: "mATX", m2Slots: 2, ramSlots: 4 },
  { id: "mobo-x870e-hero", cat: "mobo", brand: "ASUS", name: "ROG Crosshair X870E Hero", price: 629, socket: "AM5", memType: "DDR5", formFactor: "ATX", m2Slots: 5, ramSlots: 4 },
  { id: "mobo-b650i", cat: "mobo", brand: "Gigabyte", name: "B650I Aorus Ultra", price: 249, socket: "AM5", memType: "DDR5", formFactor: "ITX", m2Slots: 3, ramSlots: 2 },
  { id: "mobo-b550-tomahawk", cat: "mobo", brand: "MSI", name: "MAG B550 Tomahawk", price: 139, socket: "AM4", memType: "DDR4", formFactor: "ATX", m2Slots: 2, ramSlots: 4 },
  { id: "mobo-z890-a", cat: "mobo", brand: "MSI", name: "PRO Z890-A WiFi", price: 239, socket: "LGA1851", memType: "DDR5", formFactor: "ATX", m2Slots: 4, ramSlots: 4 },
  { id: "mobo-b860m", cat: "mobo", brand: "Gigabyte", name: "B860M Gaming X", price: 139, socket: "LGA1851", memType: "DDR5", formFactor: "mATX", m2Slots: 2, ramSlots: 4 },
  { id: "mobo-z790-d4", cat: "mobo", brand: "ASUS", name: "Prime Z790-P D4", price: 169, socket: "LGA1700", memType: "DDR4", formFactor: "ATX", m2Slots: 3, ramSlots: 4 },
  { id: "mobo-b760m-ddr5", cat: "mobo", brand: "MSI", name: "PRO B760M-A WiFi", price: 129, socket: "LGA1700", memType: "DDR5", formFactor: "mATX", m2Slots: 2, ramSlots: 4 },

  // --- RAM ---
  { id: "ram-ddr5-32-6000", cat: "ram", brand: "Corsair", name: "Vengeance 32 GB (2x16) DDR5-6000 CL30", price: 109, memType: "DDR5", sizeGB: 32, sticks: 2, watt: 10 },
  { id: "ram-ddr5-64-6000", cat: "ram", brand: "G.Skill", name: "Trident Z5 64 GB (2x32) DDR5-6000 CL30", price: 209, memType: "DDR5", sizeGB: 64, sticks: 2, watt: 12 },
  { id: "ram-ddr5-96-6400", cat: "ram", brand: "Kingston", name: "Fury Beast 96 GB (2x48) DDR5-6400", price: 299, memType: "DDR5", sizeGB: 96, sticks: 2, watt: 14 },
  { id: "ram-ddr4-16-3200", cat: "ram", brand: "Crucial", name: "Pro 16 GB (2x8) DDR4-3200", price: 39, memType: "DDR4", sizeGB: 16, sticks: 2, watt: 6 },
  { id: "ram-ddr4-32-3600", cat: "ram", brand: "G.Skill", name: "Ripjaws V 32 GB (2x16) DDR4-3600 CL16", price: 69, memType: "DDR4", sizeGB: 32, sticks: 2, watt: 8 },

  // --- GPU ---
  { id: "gpu-rtx5060", cat: "gpu", brand: "NVIDIA", name: "GeForce RTX 5060 8 GB", price: 299, tdp: 145, lengthMm: 240, vramGB: 8 },
  { id: "gpu-rtx5070", cat: "gpu", brand: "NVIDIA", name: "GeForce RTX 5070 12 GB", price: 549, tdp: 250, lengthMm: 300, vramGB: 12 },
  { id: "gpu-rtx5070ti", cat: "gpu", brand: "NVIDIA", name: "GeForce RTX 5070 Ti 16 GB", price: 799, tdp: 300, lengthMm: 320, vramGB: 16 },
  { id: "gpu-rtx5080", cat: "gpu", brand: "NVIDIA", name: "GeForce RTX 5080 16 GB", price: 1099, tdp: 360, lengthMm: 330, vramGB: 16 },
  { id: "gpu-rtx5090", cat: "gpu", brand: "NVIDIA", name: "GeForce RTX 5090 32 GB", price: 2299, tdp: 575, lengthMm: 340, vramGB: 32 },
  { id: "gpu-rx9060xt", cat: "gpu", brand: "AMD", name: "Radeon RX 9060 XT 16 GB", price: 369, tdp: 160, lengthMm: 270, vramGB: 16 },
  { id: "gpu-rx9070", cat: "gpu", brand: "AMD", name: "Radeon RX 9070 16 GB", price: 589, tdp: 220, lengthMm: 300, vramGB: 16 },
  { id: "gpu-rx9070xt", cat: "gpu", brand: "AMD", name: "Radeon RX 9070 XT 16 GB", price: 669, tdp: 304, lengthMm: 330, vramGB: 16 },
  { id: "gpu-arc-b580", cat: "gpu", brand: "Intel", name: "Arc B580 12 GB", price: 269, tdp: 190, lengthMm: 272, vramGB: 12 },

  // --- Speicher ---
  { id: "ssd-990pro-2tb", cat: "storage", brand: "Samsung", name: "990 Pro 2 TB NVMe", price: 159, kind: "m2", sizeGB: 2000, watt: 7 },
  { id: "ssd-sn850x-1tb", cat: "storage", brand: "WD", name: "Black SN850X 1 TB NVMe", price: 79, kind: "m2", sizeGB: 1000, watt: 6 },
  { id: "ssd-kc3000-4tb", cat: "storage", brand: "Kingston", name: "KC3000 4 TB NVMe", price: 279, kind: "m2", sizeGB: 4000, watt: 8 },
  { id: "ssd-870evo-1tb", cat: "storage", brand: "Samsung", name: "870 EVO 1 TB SATA", price: 79, kind: "sata", sizeGB: 1000, watt: 4 },
  { id: "hdd-barracuda-4tb", cat: "storage", brand: "Seagate", name: "BarraCuda 4 TB HDD", price: 89, kind: "sata", sizeGB: 4000, watt: 8 },

  // --- Kühler ---
  { id: "cool-ak400", cat: "cooler", brand: "DeepCool", name: "AK400", price: 29, sockets: ["AM4", "AM5", "LGA1700", "LGA1851"], maxTdp: 180, heightMm: 155, watt: 3 },
  { id: "cool-pa120", cat: "cooler", brand: "Thermalright", name: "Peerless Assassin 120 SE", price: 39, sockets: ["AM4", "AM5", "LGA1700", "LGA1851"], maxTdp: 245, heightMm: 157, watt: 4 },
  { id: "cool-nhd15", cat: "cooler", brand: "Noctua", name: "NH-D15 G2", price: 149, sockets: ["AM4", "AM5", "LGA1700", "LGA1851"], maxTdp: 280, heightMm: 168, watt: 4 },
  { id: "cool-arctic-360", cat: "cooler", brand: "Arctic", name: "Liquid Freezer III 360 (AIO)", price: 99, sockets: ["AM4", "AM5", "LGA1700", "LGA1851"], maxTdp: 320, heightMm: 0, watt: 12 },
  { id: "cool-l9a", cat: "cooler", brand: "Noctua", name: "NH-L9a-AM5 (Low Profile)", price: 49, sockets: ["AM5"], maxTdp: 95, heightMm: 37, watt: 2 },

  // --- Netzteil ---
  { id: "psu-550", cat: "psu", brand: "be quiet!", name: "Pure Power 12 550 W", price: 69, watt: 550, efficiency: "80+ Gold" },
  { id: "psu-650", cat: "psu", brand: "Corsair", name: "RM650e 650 W", price: 89, watt: 650, efficiency: "80+ Gold" },
  { id: "psu-750", cat: "psu", brand: "Corsair", name: "RM750e 750 W", price: 99, watt: 750, efficiency: "80+ Gold" },
  { id: "psu-850", cat: "psu", brand: "be quiet!", name: "Pure Power 12 M 850 W", price: 119, watt: 850, efficiency: "80+ Gold" },
  { id: "psu-1000", cat: "psu", brand: "Seasonic", name: "Focus GX-1000 1000 W", price: 169, watt: 1000, efficiency: "80+ Gold" },
  { id: "psu-1200", cat: "psu", brand: "Corsair", name: "HX1200i 1200 W", price: 259, watt: 1200, efficiency: "80+ Platinum" },

  // --- Gehäuse ---
  { id: "case-north", cat: "case", brand: "Fractal", name: "North", price: 139, formFactors: ["ATX", "mATX", "ITX"], maxGpuMm: 355, maxCoolerMm: 170 },
  { id: "case-o11", cat: "case", brand: "Lian Li", name: "O11 Dynamic EVO", price: 159, formFactors: ["ATX", "mATX", "ITX"], maxGpuMm: 420, maxCoolerMm: 167 },
  { id: "case-4000d", cat: "case", brand: "Corsair", name: "4000D Airflow", price: 99, formFactors: ["ATX", "mATX", "ITX"], maxGpuMm: 360, maxCoolerMm: 170 },
  { id: "case-a3", cat: "case", brand: "Lian Li", name: "A3-mATX", price: 79, formFactors: ["mATX", "ITX"], maxGpuMm: 415, maxCoolerMm: 165 },
  { id: "case-nr200p", cat: "case", brand: "Cooler Master", name: "NR200P V2 (ITX)", price: 109, formFactors: ["ITX"], maxGpuMm: 336, maxCoolerMm: 155 },
];

export const partById = (id) => PARTS.find((p) => p.id === id);

// Kurze Spezifikationszeile für Karten und Listen.
export function specLine(p) {
  switch (p.cat) {
    case "cpu": return `${p.socket} · ${p.cores} Kerne · ${p.tdp} W`;
    case "mobo": return `${p.socket} · ${p.memType} · ${p.formFactor}`;
    case "ram": return `${p.memType} · ${p.sizeGB} GB`;
    case "gpu": return `${p.vramGB} GB · ${p.tdp} W · ${p.lengthMm} mm`;
    case "storage": return `${p.kind === "m2" ? "M.2 NVMe" : "SATA"} · ${p.sizeGB >= 1000 ? p.sizeGB / 1000 + " TB" : p.sizeGB + " GB"}`;
    case "cooler": return `bis ${p.maxTdp} W · ${p.heightMm ? p.heightMm + " mm" : "AIO"}`;
    case "psu": return `${p.watt} W · ${p.efficiency}`;
    case "case": return `${p.formFactors.join("/")} · GPU ≤ ${p.maxGpuMm} mm`;
    default: return "";
  }
}
