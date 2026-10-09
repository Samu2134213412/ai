import { CATEGORIES, PARTS, partById, specLine } from "./parts.js";
import { checkBuild, fitsBuild, powerDraw, recommendedPsu } from "./check.js";
import { partSvg } from "./icons.js";
import { PcScene } from "./scene3d.js";
import { fileToBase64, recognizeParts, toCustomPart } from "./recognize.js";

const $ = (sel) => document.querySelector(sel);
const eur = (n) => n.toLocaleString("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const STORE_KEY = "pc-builder.build";
const KEY_KEY = "pc-builder.apiKey";

const state = {
  build: { cpu: null, mobo: null, ram: null, gpu: null, cooler: null, psu: null, case: null, storage: [] },
  customParts: [], // per Foto erkannte Teile ohne Katalogeintrag
  tab: "cpu",
  query: "",
  onlyFitting: false,
};

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
  const q = state.query.trim().toLowerCase();
  const items = allParts()
    .filter((p) => p.cat === state.tab)
    .filter((p) => !q || `${p.brand} ${p.name}`.toLowerCase().includes(q))
    .map((p) => ({ p, fits: fitsBuild(p, state.build) }))
    .filter(({ fits }) => fits || !state.onlyFitting);

  $("#catalog").innerHTML = items.length
    ? items
        .map(({ p, fits }) => {
          const inBuild = p.cat === "storage" ? state.build.storage.includes(p) : state.build[p.cat]?.id === p.id;
          return `
      <article class="card ${fits ? "" : "conflict"} ${inBuild ? "selected" : ""}" draggable="true" data-id="${p.id}" title="${fits ? "In den PC ziehen oder klicken" : "Passt nicht zum aktuellen Build"}">
        <div class="thumb">${partSvg(p)}</div>
        <div class="info">
          <div class="name"><span class="brand">${esc(p.brand)}</span> ${esc(p.name)}</div>
          <div class="specs">${esc(specLine(p))}${p.custom ? " · per Foto erkannt" : ""}</div>
        </div>
        <div class="price">${eur(p.price)}</div>
        ${fits ? "" : `<span class="badge-warn" aria-label="Konflikt">!</span>`}
      </article>`;
        })
        .join("")
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
        </div>
        <div class="price">${eur(p.price)}</div>
        <button class="icon-btn" data-remove="${c.id}" data-index="${i}" aria-label="${esc(p.name)} entfernen">×</button>
      </li>`),
    );
  }
  $("#build-list").innerHTML = rows.join("");
}

function renderSummary() {
  const b = state.build;
  const all = [b.cpu, b.mobo, b.ram, b.gpu, b.cooler, b.psu, b.case, ...b.storage].filter(Boolean);
  const total = all.reduce((s, p) => s + p.price, 0);
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
      render();
    }
  });
  $("#search").addEventListener("input", (e) => {
    state.query = e.target.value;
    renderCatalog();
  });
  $("#only-fitting").addEventListener("change", (e) => {
    state.onlyFitting = e.target.checked;
    renderCatalog();
  });

  $("#catalog").addEventListener("click", (e) => {
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
    const rm = e.target.closest("[data-remove]");
    if (rm) return removePart(rm.dataset.remove, Number(rm.dataset.index));
    const pick = e.target.closest("[data-pick]");
    if (pick) {
      state.tab = pick.dataset.pick;
      render();
      $("#catalog").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

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
      results = found.map((r) => ({ r, part: (r.catalogId && partById(r.catalogId)) || toCustomPart(r) }));
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

load();
bindEvents();
render();
try {
  scene = new PcScene($("#viewport"));
  scene.update(state.build);
} catch (err) {
  $("#viewport").innerHTML = `<p class="empty">3D-Ansicht nicht verfügbar (WebGL fehlt): ${esc(err.message)}</p>`;
}
