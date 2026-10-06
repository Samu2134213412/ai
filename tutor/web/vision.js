/* Bild-Aufbereitung für das Lesen von (schlechter) Handschrift – gemeinsam für Hauptfenster und Leiste.
   Graustufen + automatischer Kontrast, dunkle Seiten invertieren, Ausschnitte hochskalieren,
   große Flächen in überlappende Bänder teilen (größere Schrift = bessere Lesung). */
(function (root) {
"use strict";

function enhance(cv) {
  const c = cv.getContext("2d"), img = c.getImageData(0, 0, cv.width, cv.height), d = img.data;
  const hist = new Uint32Array(256);
  for (let i = 0; i < d.length; i += 4) {
    const y = (d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114) | 0;
    d[i] = y; hist[y]++;
  }
  const n = d.length / 4;
  let acc = 0, lo = 0, hi = 255, mean = 0;
  for (let v = 0; v < 256; v++) mean += v * hist[v];
  mean /= n;
  for (let v = 0; v < 256; v++) { acc += hist[v]; if (acc >= n * 0.02) { lo = v; break; } }
  acc = 0;
  for (let v = 255; v >= 0; v--) { acc += hist[v]; if (acc >= n * 0.02) { hi = v; break; } }
  const span = Math.max(40, hi - lo), invert = mean < 110;
  for (let i = 0; i < d.length; i += 4) {
    let y = Math.max(0, Math.min(255, ((d[i] - lo) / span) * 255));
    if (invert) y = 255 - y;
    d[i] = d[i + 1] = d[i + 2] = y; d[i + 3] = 255;
  }
  c.putImageData(img, 0, 0);
  return cv;
}

/* Schneidet (x, y, w, h) aus den übereinanderliegenden Ebenen, skaliert und bereitet auf. */
function crop(layers, x, y, w, h, minEdge, maxEdge) {
  const k = Math.min(maxEdge / Math.max(w, h), Math.max(1, minEdge / Math.max(w, h)));
  const cv = document.createElement("canvas");
  cv.width = Math.round(w * k); cv.height = Math.round(h * k);
  const c = cv.getContext("2d");
  c.fillStyle = "#fff"; c.fillRect(0, 0, cv.width, cv.height);
  c.imageSmoothingQuality = "high";
  for (const layer of layers) c.drawImage(layer, x, y, w, h, 0, 0, cv.width, cv.height);
  return enhance(cv);
}

/* Aufteilung: hohe Flächen in 2–3 Bänder übereinander, sehr breite in 2 Spalten, sonst ein Stück. */
function bands(W, H) {
  const r = H / W;
  if (r > 1.25) {
    const n = r > 2 ? 3 : 2, th = Math.round(H / n * 1.18);
    return Array.from({ length: n }, (_, i) => ({ x: 0, y: Math.min(H - th, Math.round((H - th) * i / (n - 1))), w: W, h: th }));
  }
  if (r < 0.67) {
    const tw = Math.round(W * 0.6);
    return [{ x: 0, y: 0, w: tw, h: H }, { x: W - tw, y: 0, w: tw, h: H }];
  }
  return [{ x: 0, y: 0, w: W, h: H }];
}

const tiles = (layers, W, H) => bands(W, H).map((r) => crop(layers, r.x, r.y, r.w, r.h, 1400, 1800).toDataURL("image/jpeg", 0.9));
const snapshot = (layers, rect, maxEdge = 900) => crop(layers, rect.x, rect.y, rect.w, rect.h, 700, maxEdge).toDataURL("image/jpeg", 0.9);

const api = { enhance, crop, bands, tiles, snapshot };
if (typeof module !== "undefined" && module.exports) module.exports = api;
root.TutorVision = api;
})(typeof self !== "undefined" ? self : globalThis);
