// Generierte Produktbilder als SVG – keine externen Bilder nötig.

const BRAND_COLORS = {
  AMD: "#e2382b", Intel: "#0a6cd6", NVIDIA: "#76b900", ASUS: "#5b6ee1", MSI: "#d4202a",
  Gigabyte: "#f08c00", Corsair: "#f5c400", "G.Skill": "#c0392b", Kingston: "#d4202a",
  Crucial: "#2a7ab8", Samsung: "#1428a0", WD: "#7d3fc8", Seagate: "#3fae49",
  DeepCool: "#00a3e0", Thermalright: "#888", Noctua: "#8b5a3c", Arctic: "#0083c3",
  "be quiet!": "#f39200", Seasonic: "#1a1a1a", Fractal: "#6b6b6b", "Lian Li": "#444",
  "Cooler Master": "#7b2ff7",
};

export const brandColor = (brand) => BRAND_COLORS[brand] || "#6c7a89";

const SHAPES = {
  cpu: (c) => `
    <rect x="18" y="18" width="64" height="64" rx="4" fill="#2b2f36"/>
    <rect x="26" y="26" width="48" height="48" rx="3" fill="#c9ccd1"/>
    <rect x="34" y="34" width="32" height="32" rx="2" fill="${c}"/>
    ${pins(18, 82)}`,
  mobo: (c) => `
    <rect x="10" y="10" width="80" height="80" rx="3" fill="#1f3b2d"/>
    <rect x="38" y="18" width="22" height="22" fill="#9aa0a6"/>
    <rect x="66" y="16" width="5" height="34" fill="#444"/><rect x="74" y="16" width="5" height="34" fill="#444"/>
    <rect x="16" y="52" width="60" height="5" fill="${c}"/><rect x="16" y="66" width="60" height="5" fill="#555"/>
    <rect x="14" y="16" width="16" height="28" fill="#333"/>`,
  ram: (c) => `
    <rect x="8" y="34" width="84" height="30" rx="2" fill="${c}"/>
    ${[0, 1, 2, 3, 4, 5].map((i) => `<rect x="${14 + i * 12}" y="40" width="9" height="12" fill="#222"/>`).join("")}
    <rect x="8" y="64" width="84" height="5" fill="#d4af37"/>`,
  gpu: (c) => `
    <rect x="6" y="28" width="88" height="40" rx="5" fill="#2b2f36"/>
    <circle cx="30" cy="48" r="15" fill="#15171a" stroke="${c}" stroke-width="2"/>
    <circle cx="70" cy="48" r="15" fill="#15171a" stroke="${c}" stroke-width="2"/>
    <circle cx="30" cy="48" r="4" fill="${c}"/><circle cx="70" cy="48" r="4" fill="${c}"/>
    <rect x="10" y="68" width="50" height="5" fill="#d4af37"/>`,
  storage: (c) => `
    <rect x="10" y="38" width="80" height="24" rx="2" fill="#1d1f24"/>
    <rect x="18" y="42" width="22" height="16" fill="${c}"/><rect x="46" y="42" width="16" height="16" fill="#555"/>
    <rect x="66" y="42" width="16" height="16" fill="#555"/><rect x="86" y="44" width="4" height="12" fill="#d4af37"/>`,
  cooler: (c) => `
    <rect x="22" y="14" width="56" height="62" rx="3" fill="#b8bcc2"/>
    ${[0, 1, 2, 3, 4, 5, 6].map((i) => `<rect x="24" y="${18 + i * 8}" width="52" height="3" fill="#8a8f96"/>`).join("")}
    <circle cx="50" cy="45" r="20" fill="#2b2f36" stroke="${c}" stroke-width="2"/>
    <rect x="34" y="78" width="32" height="8" fill="#555"/>`,
  psu: (c) => `
    <rect x="12" y="22" width="76" height="56" rx="4" fill="#2b2f36"/>
    <circle cx="50" cy="50" r="22" fill="#15171a"/>
    ${[0, 1, 2, 3].map((i) => `<circle cx="50" cy="50" r="${6 + i * 5}" fill="none" stroke="#444" stroke-width="1.5"/>`).join("")}
    <rect x="12" y="22" width="76" height="6" fill="${c}"/>`,
  case: (c) => `
    <rect x="22" y="8" width="56" height="84" rx="4" fill="#2b2f36"/>
    <rect x="28" y="14" width="44" height="64" rx="2" fill="#3c4250" opacity=".9"/>
    <circle cx="50" cy="30" r="9" fill="none" stroke="${c}" stroke-width="2"/>
    <circle cx="50" cy="56" r="9" fill="none" stroke="${c}" stroke-width="2"/>
    <rect x="28" y="82" width="44" height="4" fill="${c}"/>`,
};

function pins(from, to) {
  let s = "";
  for (let x = from + 6; x < to; x += 8) s += `<rect x="${x}" y="13" width="3" height="5" fill="#d4af37"/><rect x="${x}" y="82" width="3" height="5" fill="#d4af37"/>`;
  return s;
}

export function partSvg(part) {
  const shape = SHAPES[part.cat] || SHAPES.storage;
  return `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${shape(brandColor(part.brand))}</svg>`;
}
