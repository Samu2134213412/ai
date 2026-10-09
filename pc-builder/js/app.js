import { CATEGORIES, PARTS, loadImportedParts, partById, specLine } from "./parts.js";
import { checkBuild, fitsBuild, powerDraw, recommendedPsu } from "./check.js";
import { partSvg } from "./icons.js";
import { PcScene } from "./scene3d.js";
import { deleteModel, isGlb, loadAllModels, loadManifest, saveModel } from "./models.js";
import { fetchPrices, isFresh, readPriceCache } from "./prices.js";
import { fileToBase64, matchCatalog, recognizeParts, toCustomPart } from "./recognize.js";

const $ = (sel) => document.querySelector(sel);
const PAGE = 60;
const eur = (n) => n == null ? "–" : n.toLocaleString("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const STORE_KEY = "pc-builder.build";
const KEY_KEY = "pc-builder.apiKey";

const state = {
  build: { cpu: null, mobo: null, ram: null, gpu: null, cooler: null, psu: null, case: null, storage: [] },
  customParts: [], // per Foto erkannte Teile ohne Katalogeintrag
  tab: "cpu",
  query: "",
  onlyFitting: false,
  sort: "priced",
  limit: PAGE,
};

// Live-Preis aus dem Cache, sonst Katalogpreis.
let priceCache = readPriceCache();
const livePrice = (p) => priceCache[p.id];
const priceOf = (p) => livePrice(p)?.price ?? p.price;

const allParts = () => [...PARTS, ...state.customParts];
const findPart = (id) => partById(id) || state.customParts.find((p) => p.id === id);

let scene;

// ---------- Build ändern ----------

function addPart(part) {
  if (part.cat === "storage") state.build.storage.push(part);
  else state.build[part.cat] = part;
  if (part.custom && !state.customParts.some((p) => p.id === part.id)) state.customParts.push(part);
  changed();
}

function removePart(cat, index) {
  if (cat === "storage") state.build.storage.splice(index, 1);
  else state.build[cat] = null;
  changed();
}

function changed() {
  save();
  render();
  scene?.update(state.build);
}

function save() {
  const b = state.build;
  const ids = { ...Object.fromEntries(Object.entries(b).map(([k, v]) => [k, Array.isArray(v) ? v.map((p) => p.id) : v?.id ?? null])) };
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({ ids, customParts: state.customParts }));
  } catch {}
}

function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE_KEY));
    if (!raw) return;
    state.customParts = raw.customParts || [];
    for (const [k, v] of Object.entries(raw.ids)) {
      if (k === "storage") state.build.storage = v.map(findPart).filter(Boolean);
      else state.build[k] = v ? findPart(v) ?? null : null;
    }
  } catch {}
}

// ---------- Rendering ----------

function render() {
  renderTabs();
  renderCatalog();
  renderBuild();
  renderSummary();
}

function renderTabs() {
  $("#tabs").innerHTML = CATEGORIES.map(
    (c) => `<button role="tab" class="tab ${c.id === state.tab ? "active" : ""}" data-tab="${c.id}" aria-selected="${c.id === state.tab}">${c.label}</button>`,
  ).join("");
}

function renderCatalog() {
  const words = state.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  let items = allParts().filter((p) => p.cat === state.tab);
  if (words.length) items = items.filter((p) => {
    const hay = `${p.brand} ${p.name} ${specLine(p)}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
  const hasPrice = (p) => priceOf(p) != null;
  if (state.sort === "price-asc") items = items.filter(hasPrice).sort((a, b) => priceOf(a) - priceOf(b));
  if (state.sort === "price-desc") items = items.filter(hasPrice).sort((a, b) => priceOf(b) - priceOf(a));
  if (state.sort === "priced") items = items.filter((p) => hasPrice(p) || p.isNew);
  if (state.onlyFitting) items = items.filter((p) => fitsBuild(p, state.build));
  const total = items.length;
  const shown = items.slice(0, state.limit).map((p) => ({ p, fits: state.onlyFitting || fitsBuild(p, state.build) }));

  $("#catalog-count").textContent = `${total.toLocaleString("de-DE")} Teile`;
  $("#catalog").innerHTML = shown.length
    ? shown
        .map(({ p, fits }) => {
          const inBuild = p.cat === "storage" ? state.build.storage.includes(p) : state.build[p.cat]?.id === p.id;
          return `
      <article class="card ${fits ? "" : "conflict"} ${inBuild ? "selected" : ""}" draggable="true" data-id="${p.id}" title="${fits ? "In den PC ziehen oder klicken" : "Passt nicht zum aktuellen Build"}">
        <div class="thumb">${partSvg(p)}</div>
        <div class="info">
          <div class="name"><span class="brand">${esc(p.brand)}</span> ${esc(p.name)}</div>
          <div class="specs">${p.isNew ? `<span class="tag-new">Neu</span> ` : ""}${esc(specLine(p))}${p.custom ? " · per Foto erkannt" : ""}</div>
        </div>
        <div class="price">${eur(priceOf(p))}${livePrice(p)?.price != null ? `<span class="live" title="Live-Preis">live</span>` : ""}</div>
        ${fits ? "" : `<span class="badge-warn" aria-label="Konflikt">!</span>`}
      </article>`;
        })
        .join("") +
      (total > shown.length ? `<button class="ghost more" id="more">Mehr anzeigen (${(total - shown.length).toLocaleString("de-DE")} weitere)</button>` : "")
    : `<p class="empty">Keine Teile gefunden.</p>`;
}

function renderBuild() {
  const rows = [];
  for (const c of CATEGORIES) {
    const parts = c.id === "storage" ? state.build.storage : state.build[c.id] ? [state.build[c.id]] : [];
    if (!parts.length) {
      rows.push(`<li class="slot empty-slot" data-cat="${c.id}"><span class="slot-label">${c.label}</span><button class="link" data-pick="${c.id}">auswählen</button></li>`);
    }
    parts.forEach((p, i) =>
      rows.push(`
      <li class="slot" data-cat="${c.id}">
        <div class="thumb small">${partSvg(p)}</div>
        <div class="info">
          <span class="slot-label">${c.label}</span>
          <div class="name">${esc(p.brand)} ${esc(p.name)}</div>
          ${priceNote(p)}
          ${modelControls(p)}
        </div>
        <div class="price">${eur(priceOf(p))}</div>
        <button class="icon-btn" data-remove="${c.id}" data-index="${i}" aria-label="${esc(p.name)} entfernen">×</button>
      </li>`),
    );
  }
  $("#build-list").innerHTML = rows.join("");
}

// Eigene 3D-Modelle je Teil: { partId: { buffer, name, rotation } }
let customModels = {};

function modelControls(p) {
  const m = customModels[p.id];
  if (!m) return `<div class="model-ctl"><button class="link small-link" data-model="${esc(p.id)}">3D-Modell laden</button></div>`;
  return `<div class="model-ctl">3D: ${esc(m.name)} · <button class="link small-link" data-rotate="${esc(p.id)}">drehen</button> · <button class="link small-link" data-unmodel="${esc(p.id)}">entfernen</button></div>`;
}

function pickModelFile(partId) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".glb,model/gltf-binary";
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    const buffer = await file.arrayBuffer();
    if (!isGlb(buffer)) return alert("Bitte eine .glb-Datei wählen (glTF binär). Andere Formate vorher z. B. in Blender als .glb exportieren.");
    customModels[partId] = { buffer, name: file.name, rotation: 0 };
    try {
      await saveModel(partId, customModels[partId]);
    } catch {}
    scene?.setCustomModel(partId, buffer);
    renderBuild();
  };
  input.click();
}

function priceNote(p) {
  const lp = livePrice(p);
  if (!lp) return `<div class="price-note">Katalogpreis</div>`;
  const age = isFresh(lp) ? "" : " (älter als 1 Tag)";
  if (lp.price == null) return `<div class="price-note">Kein aktuelles Angebot gefunden${age}</div>`;
  const shop = lp.url ? `<a href="${esc(lp.url)}" target="_blank" rel="noopener noreferrer">${esc(lp.shop || "Angebot")}</a>` : esc(lp.shop || "");
  return `<div class="price-note live-note">Live: ${shop}${lp.note ? ` · ${esc(lp.note)}` : ""}${age}</div>`;
}

function renderSummary() {
  const b = state.build;
  const all = [b.cpu, b.mobo, b.ram, b.gpu, b.cooler, b.psu, b.case, ...b.storage].filter(Boolean);
  const total = all.reduce((s, p) => s + (priceOf(p) ?? 0), 0);
  const missing = all.filter((p) => priceOf(p) == null).length;
  $("#price-hint").textContent = missing ? `${missing} Teil${missing > 1 ? "e" : ""} ohne Preis` : "";
  const { total: watt, parts } = powerDraw(b);
  const rec = recommendedPsu(watt);
  const psuW = b.psu?.watt;

  $("#total-price").textContent = eur(total);
  $("#total-watt").textContent = `${watt} W`;
  $("#psu-rec").textContent = `${rec} W`;

  const pct = psuW ? Math.min(100, (watt / psuW) * 100) : 0;
  const bar = $("#power-bar");
  bar.style.setProperty("--pct", `${pct}%`);
  bar.dataset.level = !psuW ? "none" : watt > psuW ? "error" : psuW < rec ? "warn" : "ok";
  $("#power-text").textContent = psuW ? `${watt} W von ${psuW} W (${Math.round((watt / psuW) * 100)} %)` : `${watt} W – kein Netzteil gewählt`;
  $("#power-detail").innerHTML = parts.map((p) => `<li><span>${esc(p.label)}</span><span>${p.watt} W</span></li>`).join("");

  const checks = checkBuild(b);
  const errors = checks.filter((c) => c.level === "error").length;
  $("#status").textContent = !all.length ? "Leer" : errors ? `${errors} Problem${errors > 1 ? "e" : ""}` : "Kompatibel";
  $("#status").dataset.level = !all.length ? "none" : errors ? "error" : "ok";
  $("#checks").innerHTML = checks.length
    ? checks.map((c) => `<li class="check ${c.level}"><span class="dot" aria-hidden="true"></span>${esc(c.text)}</li>`).join("")
    : `<li class="check none">Wähle Teile aus, um die Kompatibilität zu prüfen.</li>`;
}

// ---------- Interaktion ----------

function bindEvents() {
  $("#tabs").addEventListener("click", (e) => {
    const t = e.target.closest("[data-tab]");
    if (t) {
      state.tab = t.dataset.tab;
      state.limit = PAGE;
      state.query = $("#search").value = "";
      render();
    }
  });
  $("#search").addEventListener("input", (e) => {
    state.query = e.target.value;
    state.limit = PAGE;
    renderCatalog();
  });
  $("#only-fitting").addEventListener("change", (e) => {
    state.onlyFitting = e.target.checked;
    renderCatalog();
  });

  $("#sort").addEventListener("change", (e) => {
    state.sort = e.target.value;
    state.limit = PAGE;
    renderCatalog();
  });

  $("#catalog").addEventListener("click", (e) => {
    if (e.target.id === "more") {
      state.limit += PAGE * 2;
      return renderCatalog();
    }
    const card = e.target.closest(".card");
    if (card) addPart(findPart(card.dataset.id));
  });
  $("#catalog").addEventListener("dragstart", (e) => {
    const card = e.target.closest(".card");
    if (!card) return;
    e.dataTransfer.setData("text/plain", card.dataset.id);
    e.dataTransfer.effectAllowed = "copy";
    document.body.classList.add("dragging");
  });
  document.addEventListener("dragend", () => document.body.classList.remove("dragging"));

  for (const zone of [$("#viewport"), $("#build-panel")]) {
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("drop-hover");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drop-hover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("drop-hover");
      document.body.classList.remove("dragging");
      const part = findPart(e.dataTransfer.getData("text/plain"));
      if (part) addPart(part);
    });
  }

  $("#build-list").addEventListener("click", (e) => {
    const t = e.target.closest("[data-model],[data-rotate],[data-unmodel]");
    if (t?.dataset.model) return pickModelFile(t.dataset.model);
    if (t?.dataset.rotate) {
      const m = customModels[t.dataset.rotate];
      m.rotation = (m.rotation + 1) % 4;
      saveModel(t.dataset.rotate, m).catch(() => {});
      return scene?.setRotation(t.dataset.rotate, m.rotation);
    }
    if (t?.dataset.unmodel) {
      delete customModels[t.dataset.unmodel];
      deleteModel(t.dataset.unmodel).catch(() => {});
      scene?.setCustomModel(t.dataset.unmodel, null);
      return renderBuild();
    }
    const rm = e.target.closest("[data-remove]");
    if (rm) return removePart(rm.dataset.remove, Number(rm.dataset.index));
    const pick = e.target.closest("[data-pick]");
    if (pick) {
      state.tab = pick.dataset.pick;
      state.limit = PAGE;
      render();
      $("#catalog").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  $("#fetch-prices").addEventListener("click", updatePrices);

  $("#reset").addEventListener("click", () => {
    if (!confirm("Build wirklich leeren?")) return;
    state.build = { cpu: null, mobo: null, ram: null, gpu: null, cooler: null, psu: null, case: null, storage: [] };
    changed();
  });

  $("#screenshot").addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = scene.snapshot();
    a.download = "mein-pc.png";
    a.click();
  });

  bindPhoto();
}

// ---------- Live-Preise ----------

async function updatePrices() {
  const b = state.build;
  const parts = [b.cpu, b.mobo, b.ram, b.gpu, b.cooler, b.psu, b.case, ...b.storage].filter(Boolean);
  const status = $("#price-status");
  if (!parts.length) return void (status.textContent = "Erst Teile auswählen.");
  let key = readKey();
  if (!key) {
    key = (prompt("Anthropic-API-Schlüssel für die Preissuche (wird nur in diesem Browser gespeichert):") || "").trim();
    if (!key) return;
    try {
      localStorage.setItem(KEY_KEY, key);
    } catch {}
  }
  const btn = $("#fetch-prices");
  btn.disabled = true;
  status.textContent = `Suche Preise für ${parts.length} Teile …`;
  try {
    priceCache = await fetchPrices(key, parts, (round) => {
      if (round) status.textContent = `Suche läuft weiter (Runde ${round + 1}) …`;
    });
    const found = parts.filter((p) => priceCache[p.id]?.price != null).length;
    status.textContent = `${found} von ${parts.length} Preisen aktualisiert · ${new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`;
    render();
  } catch (err) {
    status.textContent = `Fehler: ${err.message || err}`;
  } finally {
    btn.disabled = false;
  }
}

// ---------- Foto-Erkennung ----------

function bindPhoto() {
  const dlg = $("#photo-dialog");
  let results = [];

  $("#open-photo").addEventListener("click", () => {
    $("#api-key").value = readKey();
    $("#photo-results").innerHTML = "";
    $("#photo-preview").hidden = true;
    $("#photo-error").textContent = "";
    $("#apply-photo").disabled = true;
    dlg.showModal();
  });
  $("#close-photo").addEventListener("click", () => dlg.close());

  $("#photo-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const key = $("#api-key").value.trim();
    if (!key) return void ($("#photo-error").textContent = "Bitte zuerst einen Anthropic-API-Schlüssel eintragen.");
    try {
      localStorage.setItem(KEY_KEY, key);
    } catch {}

    $("#photo-error").textContent = "";
    $("#photo-results").innerHTML = `<li class="loading">Teile werden erkannt …</li>`;
    $("#apply-photo").disabled = true;
    try {
      const { data, preview } = await fileToBase64(file);
      $("#photo-preview").src = preview;
      $("#photo-preview").hidden = false;
      const found = await recognizeParts(key, data);
      results = found.map((r) => ({ r, part: (r.catalogId && partById(r.catalogId)) || matchCatalog(r, allParts()) || toCustomPart(r) }));
      renderResults(results);
    } catch (err) {
      $("#photo-results").innerHTML = "";
      $("#photo-error").textContent = `Fehler: ${err.message || err}`;
    }
  });

  $("#apply-photo").addEventListener("click", () => {
    $("#photo-results")
      .querySelectorAll("input:checked")
      .forEach((cb) => addPart(results[Number(cb.value)].part));
    dlg.close();
  });
}

function renderResults(results) {
  $("#photo-results").innerHTML = results.length
    ? results
        .map(
          ({ r, part }, i) => `
      <li class="result">
        <label>
          <input type="checkbox" value="${i}" ${r.confidence === "niedrig" ? "" : "checked"}>
          <div class="thumb small">${partSvg(part)}</div>
          <div class="info">
            <div class="name">${esc(part.brand)} ${esc(part.name)}</div>
            <div class="specs">${part.custom ? "Nicht im Katalog – Daten geschätzt" : "Im Katalog gefunden"} · Sicherheit: ${esc(r.confidence)}</div>
            <div class="evidence">${esc(r.evidence)}</div>
          </div>
          <div class="price">${eur(part.price)}</div>
        </label>
      </li>`,
        )
        .join("")
    : `<li class="empty">Auf dem Foto wurden keine PC-Teile erkannt.</li>`;
  $("#apply-photo").disabled = !results.length;
}

function readKey() {
  try {
    return localStorage.getItem(KEY_KEY) || "";
  } catch {
    return "";
  }
}

// ---------- Start ----------

const imported = await loadImportedParts();
$("#catalog-source").textContent = imported ? "Katalog: PCPartPicker-Daten (Preise aus USD umgerechnet)" : "Katalog: Beispielteile – für alle Teile tools/import-pcpp.mjs ausführen";
load();
bindEvents();
render();
try {
  scene = new PcScene($("#viewport"));
  customModels = await loadAllModels();
  for (const [id, m] of Object.entries(customModels)) {
    scene.customModels.set(id, m.buffer);
    if (m.rotation) scene.rotations.set(id, m.rotation);
  }
  scene.manifest = await loadManifest();
  scene.update(state.build);
  renderBuild();
} catch (err) {
  $("#viewport").innerHTML = `<p class="empty">3D-Ansicht nicht verfügbar (WebGL fehlt): ${esc(err.message)}</p>`;
}
