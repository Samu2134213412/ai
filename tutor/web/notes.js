/* Aufgeräumte Seite: Notiz-Format lesen, als saubere A4-Seite zeichnen, als PDF verpacken.
   Gemeinsam für Hauptfenster und GoodNotes-Leiste; parse() und buildPdf() laufen auch in Node (Tests). */
(function (root) {
"use strict";

/* Format (Markdown-Auszug), wie es das Sprachmodell liefert und der Lernende bearbeiten kann:
   # Titel · ## Abschnitt · - Punkt · 1. Schritt · $ Formel/Rechenzeile · [ ] To-do · > Hinweis · sonst Text */
function parse(markup) {
  const blocks = [];
  for (let raw of String(markup || "").replace(/```[a-z]*\n?/gi, "").split(/\r?\n/)) {
    const line = raw.replace(/\*\*|__|`/g, "").trimEnd();
    if (!line.trim()) { if (blocks.length && blocks[blocks.length - 1].t !== "gap") blocks.push({ t: "gap" }); continue; }
    let m;
    if ((m = /^\s*##+\s+(.*)$/.exec(line))) blocks.push({ t: "h2", text: m[1] });
    else if ((m = /^\s*#\s+(.*)$/.exec(line))) blocks.push({ t: "h1", text: m[1] });
    else if ((m = /^\s*\[( |x|X)\]\s+(.*)$/.exec(line))) blocks.push({ t: "todo", done: m[1] !== " ", text: m[2] });
    else if ((m = /^\s*[-*•]\s+(.*)$/.exec(line))) blocks.push({ t: "li", text: m[1] });
    else if ((m = /^\s*(\d+)[.)]\s+(.*)$/.exec(line))) blocks.push({ t: "ol", n: +m[1], text: m[2] });
    else if ((m = /^\s*\$\s+(.*)$/.exec(line))) blocks.push({ t: "formula", text: m[1].replace(/^\$+|\$+$/g, "").trim() });
    else if ((m = /^\s*>\s?(.*)$/.exec(line))) blocks.push({ t: "note", text: m[1] });
    else blocks.push({ t: "p", text: line.trim() });
  }
  while (blocks.length && blocks[blocks.length - 1].t === "gap") blocks.pop();
  return blocks;
}

const PAGE = { w: 1240, h: 1754 };                       // A4 mit 150 dpi
const STYLES = {
  clean: { bg: "#ffffff", ink: "#1f2430", accent: "#e8590c", muted: "#6b7280", box: "#f6f1ea", line: null,
    font: '"Segoe UI","Helvetica Neue",Arial,sans-serif', math: '"Cambria Math","Times New Roman",serif', size: 32, grid: 0 },
  hand: { bg: "#fffdf6", ink: "#1c3d8f", accent: "#c92a2a", muted: "#5b6b9b", box: "#eef2ff", line: "#bcd0f0",
    font: '"Bradley Hand","Noteworthy","Marker Felt","Segoe Print","Comic Sans MS",cursive', math: '"Bradley Hand","Segoe Print","Comic Sans MS",cursive', size: 36, grid: 58 },
};

function wrap(ctx, text, maxW) {
  const lines = []; let cur = "";
  for (const word of String(text).split(/\s+/)) {
    if (!word) continue;
    const t = cur ? cur + " " + word : word;
    if (ctx.measureText(t).width > maxW && cur) { lines.push(cur); cur = word; } else cur = t;
  }
  if (cur) lines.push(cur);
  return lines.length ? lines : [""];
}

/* Zeichnet die Blöcke auf eine oder mehrere A4-Seiten und liefert die Canvas-Elemente. */
function render(blocks, style) {
  const S = STYLES[style] || STYLES.clean, M = 110, W = PAGE.w - 2 * M, pages = [];
  let cv, ctx, y;
  const newPage = () => {
    cv = document.createElement("canvas"); cv.width = PAGE.w; cv.height = PAGE.h; ctx = cv.getContext("2d");
    ctx.fillStyle = S.bg; ctx.fillRect(0, 0, PAGE.w, PAGE.h);
    if (S.line) { ctx.strokeStyle = S.line; ctx.lineWidth = 2; for (let ly = M + S.grid; ly < PAGE.h - 60; ly += S.grid) { ctx.beginPath(); ctx.moveTo(60, ly); ctx.lineTo(PAGE.w - 60, ly); ctx.stroke(); }
      ctx.strokeStyle = "#f2b8b8"; ctx.beginPath(); ctx.moveTo(M - 30, 0); ctx.lineTo(M - 30, PAGE.h); ctx.stroke(); }
    ctx.textBaseline = "alphabetic"; pages.push(cv); y = M;
  };
  const lineH = (size) => (S.grid ? S.grid : Math.round(size * 1.45));
  const snap = (v) => (S.grid ? Math.ceil((v - M) / S.grid) * S.grid + M : v);
  const room = (h) => { if (y + h > PAGE.h - M) newPage(); };
  newPage();

  function text(str, x, size, opts = {}) {
    ctx.font = `${opts.weight || ""} ${opts.italic ? "italic " : ""}${size}px ${opts.font || S.font}`.trim();
    const lh = lineH(size), lines = wrap(ctx, str, W - (x - M));
    for (const ln of lines) {
      room(lh); y = snap(y);
      ctx.fillStyle = opts.color || S.ink; ctx.fillText(ln, x, y + (S.grid ? -10 : size));
      y += lh;
    }
    return lines.length;
  }
  for (const b of blocks) {
    switch (b.t) {
      case "gap": y += S.grid ? S.grid / 2 : 14; break;
      case "h1": {
        if (y > M) y += 10;
        text(b.text, M, S.size + 22, { weight: "bold", color: S.ink });
        ctx.fillStyle = S.accent; ctx.fillRect(M, y - (S.grid ? 14 : 8), 220, 7); y += S.grid ? 22 : 26; break;
      }
      case "h2": y += S.grid ? 8 : 18; text(b.text, M, S.size + 6, { weight: "bold", color: S.accent }); y += 4; break;
      case "p": text(b.text, M, S.size); break;
      case "li": { const y0 = y; const n = text(b.text, M + 48, S.size); ctx.fillStyle = S.accent; ctx.beginPath(); ctx.arc(M + 18, snap(y0) + (S.grid ? -S.size * 0.35 - 10 : S.size * 0.62), 7, 0, 7); ctx.fill(); void n; break; }
      case "ol": { const y0 = y; text(b.text, M + 64, S.size); const keep = y; y = y0; ctx.font = `bold ${S.size}px ${S.font}`; ctx.fillStyle = S.accent; room(lineH(S.size)); ctx.fillText(b.n + ".", M + 6, snap(y) + (S.grid ? -10 : S.size)); y = keep; break; }
      case "formula": {
        ctx.font = `italic ${S.size + 4}px ${S.math}`;
        const lines = wrap(ctx, b.text, W - 70), lh = lineH(S.size + 4), h = lines.length * lh + (S.grid ? 0 : 26);
        room(h + 8); y = snap(y) + (S.grid ? 0 : 6);
        if (!S.grid) { ctx.fillStyle = S.box; ctx.fillRect(M + 24, y - 6, W - 24, h); }
        ctx.fillStyle = S.ink; ctx.font = `italic ${S.size + 4}px ${S.math}`;
        lines.forEach((ln, i) => ctx.fillText(ln, M + 48, y + (S.grid ? -10 : S.size + 6) + i * lh));
        y += h + (S.grid ? 0 : 14); break;
      }
      case "todo": {
        const y0 = snap(y); room(lineH(S.size)); ctx.strokeStyle = S.ink; ctx.lineWidth = 3; ctx.strokeRect(M + 6, y0 + (S.grid ? -S.size : 4), S.size - 6, S.size - 6);
        if (b.done) { ctx.beginPath(); ctx.moveTo(M + 12, y0 + (S.grid ? -S.size / 2 : S.size / 2)); ctx.lineTo(M + 22, y0 + (S.grid ? -10 : S.size - 8)); ctx.lineTo(M + S.size, y0 + (S.grid ? -S.size - 4 : -2)); ctx.stroke(); }
        text(b.text, M + 58, S.size, { color: b.done ? S.muted : S.ink }); break;
      }
      case "note": {
        const y0 = y; text(b.text, M + 40, S.size - 2, { italic: true, color: S.muted });
        ctx.fillStyle = S.accent; ctx.fillRect(M + 8, snap(y0) - (S.grid ? S.size : 0) + 4, 6, Math.max(30, y - y0 - 8)); break;
      }
      default: break;
    }
  }
  return pages;
}

/* PDF ohne Bibliothek: je Seite ein JPEG über die ganze A4-Seite. pages: [{ jpeg: Uint8Array, width, height }] */
function buildPdf(pages) {
  const enc = new TextEncoder(), parts = [], offsets = [];
  let size = 0;
  const push = (x) => { const b = typeof x === "string" ? enc.encode(x) : x; parts.push(b); size += b.length; };
  const obj = (n, body) => { offsets[n] = size; push(`${n} 0 obj\n`); body(); push("\nendobj\n"); };
  push("%PDF-1.4\n%âãÏÓ\n");
  const count = pages.length, firstPage = 3;               // 1 Katalog, 2 Seitenbaum, danach je Seite 3 Objekte
  obj(1, () => push("<< /Type /Catalog /Pages 2 0 R >>"));
  obj(2, () => push(`<< /Type /Pages /Count ${count} /Kids [${pages.map((_, i) => `${firstPage + i * 3} 0 R`).join(" ")}] >>`));
  pages.forEach((p, i) => {
    const pg = firstPage + i * 3, img = pg + 1, con = pg + 2, W = 595, H = 842;
    obj(pg, () => push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${W} ${H}] /Resources << /XObject << /Im0 ${img} 0 R >> >> /Contents ${con} 0 R >>`));
    obj(img, () => { push(`<< /Type /XObject /Subtype /Image /Width ${p.width} /Height ${p.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${p.jpeg.length} >>\nstream\n`); push(p.jpeg); push("\nendstream"); });
    const content = `q ${W} 0 0 ${H} 0 0 cm /Im0 Do Q`;
    obj(con, () => push(`<< /Length ${content.length} >>\nstream\n${content}\nendstream`));
  });
  const total = firstPage + count * 3, xref = size;
  push(`xref\n0 ${total}\n0000000000 65535 f \n`);
  for (let n = 1; n < total; n++) push(String(offsets[n]).padStart(10, "0") + " 00000 n \n");
  push(`trailer\n<< /Size ${total} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  const out = new Uint8Array(size); let pos = 0;
  for (const b of parts) { out.set(b, pos); pos += b.length; }
  return out;
}

/* Canvas-Seiten → PDF-Bytes (Browser). */
async function toPdf(canvases) {
  const pages = [];
  for (const cv of canvases) {
    const blob = await new Promise((r) => cv.toBlob(r, "image/jpeg", 0.92));
    pages.push({ jpeg: new Uint8Array(await blob.arrayBuffer()), width: cv.width, height: cv.height });
  }
  return buildPdf(pages);
}

const api = { parse, render, buildPdf, toPdf, STYLES, PAGE };
if (typeof module !== "undefined" && module.exports) module.exports = api;
root.TutorNotes = api;
})(typeof self !== "undefined" ? self : globalThis);
