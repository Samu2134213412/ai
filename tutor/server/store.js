/* Dateibasierter Speicher: Nutzerliste und je Nutzer eine JSON-Datei (atomar geschrieben). */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { return fallback; }
}
function writeJson(file, data, mode) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file + ".tmp", JSON.stringify(data, null, 2), mode ? { mode } : undefined);
  fs.renameSync(file + ".tmp", file);
}

/* Schnittstelle, die backend-local.js erwartet: async get(key) / set(key, value). */
function fileStorage(file) {
  const data = readJson(file, {});
  return {
    async get(key) { return data[key] === undefined ? null : JSON.parse(JSON.stringify(data[key])); },
    async set(key, value) { data[key] = JSON.parse(JSON.stringify(value)); writeJson(file, data); },
  };
}

const sha = (s) => crypto.createHash("sha256").update(s).digest("hex");
const same = (a, b) => a.length === b.length && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));

/* Nutzer: id → { name, hashes (SHA-256 der Geräte-Tokens), owner }. Eine Person kann mehrere Geräte haben;
   Tokens werden nie im Klartext gespeichert. */
function usersDb(file) {
  const db = readJson(file, { users: {} });
  const save = () => writeJson(file, db, 0o600);
  return {
    list: () => Object.entries(db.users).map(([id, u]) => ({ id, name: u.name, owner: !!u.owner, devices: u.hashes.length })),
    find(token) {                                    // Token → Nutzer-ID oder null
      if (!token) return null;
      const h = sha(token);
      for (const [id, u] of Object.entries(db.users)) if (u.hashes.some((x) => same(x, h))) return id;
      return null;
    },
    /* Neues Gerät: legt die Person an (oder ergänzt ein Gerät) und liefert { id, token }. */
    add(name, { owner = false, id } = {}) {
      id = id || crypto.randomBytes(5).toString("hex");
      const token = crypto.randomBytes(24).toString("base64url");
      const prev = db.users[id] || { name: String(name || "Lernende:r").slice(0, 40), hashes: [], owner: false };
      prev.hashes = [...prev.hashes, sha(token)].slice(-10);          // höchstens 10 Geräte pro Person
      prev.owner = prev.owner || owner;
      db.users[id] = prev;
      save();
      return { id, token };
    },
    owner: () => { const e = Object.entries(db.users).find(([, u]) => u.owner); return e ? e[0] : null; },
  };
}
module.exports = { fileStorage, usersDb, readJson, writeJson, sha };
