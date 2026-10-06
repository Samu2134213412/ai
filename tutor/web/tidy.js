/* „Seite aufräumen“: gelesene Seite → gegliederte, saubere Seite (Vorschau, bearbeiten, per Zuruf ändern,
   als PDF/PNG exportieren oder ans Teilen-Menü geben, z. B. zum Import in GoodNotes).
   Wird vom Hauptfenster und von der GoodNotes-Leiste benutzt; baut seinen Dialog selbst. */
(function (root) {
"use strict";
const Notes = root.TutorNotes;
let cfg = { api: null, say: () => {}, onOpen: () => {}, onClose: () => {} };
let dlg = null, el = {}, markup = "", pages = [], timer = 0;

function build() {
  if (dlg) return;
  dlg = document.createElement("dialog"); dlg.id = "tidyDlg"; dlg.className = "wide";
  dlg.innerHTML = `<form method="dialog">
    <h3>🧹 Aufgeräumte Seite</h3>
    <div id="tidyStatus" class="hint"></div>
    <div class="tidyGrid">
      <div class="tidyEdit">
        <textarea id="tidyText" rows="16" spellcheck="false" aria-label="Seite bearbeiten"></textarea>
        <div class="row2"><input id="tidyWish" placeholder="Wunsch, z. B. „mach das als Liste“" maxlength="300"><button type="button" id="tidyApply">Ändern</button></div>
        <label class="hint">Stil <select id="tidyStyle"><option value="clean">Sauber</option><option value="hand">Heft (Handschrift-Optik)</option></select></label>
      </div>
      <div class="tidyPreview"><div id="tidyPages"></div></div>
    </div>
    <p class="hint">Der Tutor hat nur geordnet – nichts gelöst oder korrigiert. <b>[?]</b> = unsicher gelesen, bitte prüfen. Format: <code># Titel</code> <code>## Abschnitt</code> <code>- Punkt</code> <code>1. Schritt</code> <code>$ Rechnung</code> <code>[ ] To-do</code> <code>&gt; Merksatz</code>.
    In GoodNotes: <i>Importieren → PDF</i> (oder über „Teilen“ direkt an GoodNotes senden).</p>
    <div class="actions"><button value="cancel">Schließen</button><button type="button" id="tidyPng">⬇︎ PNG</button><button type="button" id="tidyShare">Teilen …</button><button type="button" id="tidyPdf" class="go">⬇︎ PDF</button></div>
  </form>`;
  document.body.appendChild(dlg);
  for (const id of ["tidyStatus", "tidyText", "tidyWish", "tidyApply", "tidyStyle", "tidyPages", "tidyPng", "tidyShare", "tidyPdf"]) el[id] = dlg.querySelector("#" + id);
  el.tidyText.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(preview, 300); });
  el.tidyStyle.addEventListener("change", preview);
  el.tidyApply.addEventListener("click", applyWish);
  el.tidyWish.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); applyWish(); } });
  el.tidyPdf.addEventListener("click", () => exportFile("pdf"));
  el.tidyPng.addEventListener("click", () => exportFile("png"));
  el.tidyShare.addEventListener("click", () => exportFile("share"));
  dlg.addEventListener("close", () => cfg.onClose());
}

function preview() {
  markup = el.tidyText.value;
  pages = Notes.render(Notes.parse(markup), el.tidyStyle.value);
  el.tidyPages.replaceChildren(...pages.map((cv, i) => {
    const wrap = document.createElement("div"); wrap.className = "tidyPage";
    const img = new Image(); img.src = cv.toDataURL("image/jpeg", 0.8); img.alt = `Seite ${i + 1}`; wrap.appendChild(img);
    return wrap;
  }));
  el.tidyStatus.textContent = `${pages.length} Seite${pages.length === 1 ? "" : "n"} (A4)`;
}

async function request(body) {
  el.tidyStatus.textContent = "Räume auf …";
  [el.tidyApply, el.tidyPdf, el.tidyPng, el.tidyShare].forEach((b) => (b.disabled = true));
  try {
    const r = await cfg.api("/api/tidy", body);
    el.tidyText.value = r.markup; preview();
  } catch (e) { el.tidyStatus.textContent = "⚠ " + e.message; }
  finally { [el.tidyApply, el.tidyPdf, el.tidyPng, el.tidyShare].forEach((b) => (b.disabled = false)); }
}
const applyWish = async () => {
  const wish = el.tidyWish.value.trim(); if (!wish) return;
  await request({ markup: el.tidyText.value, instruction: wish }); el.tidyWish.value = "";
};

async function exportFile(kind) {
  if (!pages.length) return;
  const stamp = new Date().toISOString().slice(0, 10);
  let files;
  if (kind === "png") {
    files = await Promise.all(pages.map(async (cv, i) => new File([await new Promise((r) => cv.toBlob(r, "image/png"))], `seite-${stamp}${pages.length > 1 ? "-" + (i + 1) : ""}.png`, { type: "image/png" })));
  } else {
    files = [new File([await Notes.toPdf(pages)], `aufgeraeumt-${stamp}.pdf`, { type: "application/pdf" })];
  }
  if (kind === "share") {
    try { if (navigator.canShare && navigator.canShare({ files })) { await navigator.share({ files, title: "Aufgeräumte Seite" }); return; } }
    catch (e) { if (e.name === "AbortError") return; }
  }
  for (const f of files) {
    const a = document.createElement("a"); a.href = URL.createObjectURL(f); a.download = f.name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }
  cfg.say(kind === "share" ? "Teilen geht hier nicht – ich hab die Datei gespeichert." : "Gespeichert. In GoodNotes: Importieren → PDF.");
}

/* Dialog öffnen und die zuletzt gelesene Seite aufräumen. */
async function open() {
  build(); cfg.onOpen();
  el.tidyText.value = ""; el.tidyPages.replaceChildren();
  dlg.showModal();
  await request({});
}

root.TutorTidy = { init(c) { cfg = { ...cfg, ...c }; }, open };
})(typeof self !== "undefined" ? self : globalThis);
