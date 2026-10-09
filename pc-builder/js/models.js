// Eigene 3D-Modelle (.glb) pro Teil, gespeichert in IndexedDB dieses Browsers.

const DB = "pc-builder";
const STORE = "models";

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run(mode, fn) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const req = fn(tx.objectStore(STORE));
    tx.oncomplete = () => resolve(req?.result);
    tx.onerror = () => reject(tx.error);
  });
}

// { partId: { buffer, name, rotation } }
export async function loadAllModels() {
  try {
    const out = {};
    await run("readonly", (s) => {
      const req = s.openCursor();
      req.onsuccess = () => {
        const c = req.result;
        if (!c) return;
        out[c.key] = c.value;
        c.continue();
      };
      return req;
    });
    return out;
  } catch {
    return {};
  }
}

export const saveModel = (partId, value) => run("readwrite", (s) => s.put(value, partId));
export const deleteModel = (partId) => run("readwrite", (s) => s.delete(partId));

// Optionale Zuordnung models/manifest.json: [{ "cat": "gpu", "match": "RTX 5090", "file": "rtx5090.glb" }]
export async function loadManifest() {
  try {
    const res = await fetch("models/manifest.json");
    return res.ok ? await res.json() : [];
  } catch {
    return [];
  }
}

// Prüft die GLB-Signatur, damit keine falsche Datei gespeichert wird.
export function isGlb(buffer) {
  return buffer.byteLength > 12 && new TextDecoder().decode(new Uint8Array(buffer, 0, 4)) === "glTF";
}
