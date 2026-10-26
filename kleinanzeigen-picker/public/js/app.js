import { CATEGORIES, categoryById, classify, shippingEstimate } from './categories.js';
import { buildQuery } from './query.js';
import { assessRisk, LEVEL_LABEL } from './risk.js';
import { eur, escapeHtml as h, numberForInput as num, parseNumberInput } from './format.js';
import { extractListingUrl, isAllowedImage } from './urls.js';

const STORAGE_KEY = 'anzeigen-picker:v1';
const $ = (sel) => document.querySelector(sel);

const state = load();
const ui = { expanded: new Set(), adding: null, focusAdd: false };

// ---------- persistence ----------

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');
    if (saved && Array.isArray(saved.items)) return sanitizeState(saved);
  } catch {
    // Storage blocked or corrupt – start empty.
  }
  return { name: 'Meine PC-Liste', items: [] };
}

function sanitizeState(raw) {
  const items = raw.items
    .filter((i) => i && typeof i === 'object' && typeof i.url === 'string')
    .map((i) => ({
      id: String(i.id ?? uid()),
      url: i.url,
      category: categoryById(i.category).id,
      autoCategory: false,
      status: i.status === 'ok' && i.listing ? 'ok' : 'error',
      error: i.status === 'ok' ? null : (i.error ?? 'Abruf unterbrochen – erneut versuchen.'),
      listing: i.listing ?? null,
      market: i.market?.status === 'ok' ? i.market : null,
      overrides: i.overrides && typeof i.overrides === 'object' ? i.overrides : {},
    }));
  return { name: String(raw.name ?? 'Meine PC-Liste').slice(0, 80), items };
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Not fatal: the list just won't survive a reload.
  }
}

function uid() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ---------- API ----------

async function api(path) {
  let res;
  try {
    res = await fetch(path);
  } catch {
    throw new Error('Server nicht erreichbar – läuft start.bat / npm start noch?');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error ?? `Fehler ${res.status}`);
  return data;
}

const alive = (item) => state.items.includes(item);

async function loadListing(item) {
  item.status = 'loading';
  item.error = null;
  render();
  try {
    const { listing } = await api(`/api/listing?url=${encodeURIComponent(item.url)}`);
    if (!alive(item)) return;
    item.listing = listing;
    item.url = listing.url ?? item.url;
    item.status = 'ok';
    if (item.autoCategory) {
      item.category = classify(listing.title, listing.details?.Art);
      item.autoCategory = false;
      toast(`Einsortiert als ${categoryById(item.category).label}.`);
    }
  } catch (err) {
    if (!alive(item)) return;
    item.status = 'error';
    item.error = err.message;
  }
  save();
  render();
  if (item.status === 'ok') loadMarket(item);
}

async function loadMarket(item) {
  const listing = item.listing;
  const query = item.overrides.query || (listing?.title ? buildQuery(listing.title) : '');
  if (!query) return;
  item.market = { status: 'loading', query };
  render();
  const params = new URLSearchParams({ q: query });
  if (listing.categoryId) params.set('cat', listing.categoryId);
  if (listing.adId) params.set('exclude', listing.adId);
  if (/defekt|bastler/i.test(`${listing.title} ${listing.details?.Zustand ?? ''}`)) params.set('defect', '1');
  try {
    const data = await api(`/api/market?${params}`);
    if (!alive(item)) return;
    item.market = { status: 'ok', ...data };
  } catch (err) {
    if (!alive(item)) return;
    item.market = { status: 'error', query, error: err.message };
  }
  save();
  render();
}

function addListing(input, category = null) {
  const url = extractListingUrl(input);
  if (!url) {
    toast('Kein Kleinanzeigen-Anzeigenlink erkannt (…kleinanzeigen.de/s-anzeige/…).', true);
    return false;
  }
  if (state.items.some((i) => i.url === url)) {
    toast('Diese Anzeige ist schon in der Liste.', true);
    return false;
  }
  const item = {
    id: uid(), url, category: category ?? 'other', autoCategory: !category,
    status: 'loading', error: null, listing: null, market: null, overrides: {},
  };
  state.items.push(item);
  ui.adding = null;
  save();
  loadListing(item);
  return true;
}

// ---------- derived values ----------

function compute(item) {
  const L = item.listing ?? {};
  const o = item.overrides;
  const price = o.price ?? L.price ?? null;
  const pickup = o.pickup ?? Boolean(L.shipping?.pickupOnly);
  let shipping;
  let shippingSource;
  if (pickup) [shipping, shippingSource] = [0, 'Abholung'];
  else if (o.shipping != null) [shipping, shippingSource] = [o.shipping, 'manuell'];
  else if (L.shipping?.cost != null) [shipping, shippingSource] = [L.shipping.cost, 'laut Anzeige'];
  else [shipping, shippingSource] = [shippingEstimate(item.category), 'geschätzt'];

  const auto = item.market?.status === 'ok' ? item.market.stats?.median ?? null : null;
  const market = o.marketPrice ?? auto;
  const marketSource = o.marketPrice != null ? 'manual' : auto != null ? 'search' : null;
  const risk = item.listing
    ? assessRisk({
      listing: L, price, market, marketSource, marketCount: item.market?.stats?.count ?? null,
    })
    : null;
  return {
    title: o.title || L.title || 'Ohne Titel',
    price, pickup, shipping, shippingSource,
    total: price == null ? null : price + shipping,
    market, marketSource, risk,
  };
}

// ---------- rendering ----------

// Rows are rebuilt on every change, so keep whatever the user is typing
// when a background load finishes mid-edit.
function captureFocus() {
  const el = document.activeElement;
  if (!el || !$('#parts-body').contains(el)) return null;
  const form = el.form;
  let selector = null;
  if (el.dataset.field) selector = `[data-field="${el.dataset.field}"][data-id="${el.dataset.id}"]`;
  else if (form?.classList.contains('market-form')) selector = `.market-form[data-id="${form.dataset.id}"] input[name="q"]`;
  else if (form?.classList.contains('inline-add')) selector = `.inline-add[data-cat="${form.dataset.cat}"] input[name="url"]`;
  if (!selector) return null;
  return { selector, value: el.value, start: el.selectionStart, end: el.selectionEnd, keepValue: el.tagName === 'INPUT' && el.type !== 'checkbox' };
}

function restoreFocus(saved) {
  const el = saved && $('#parts-body').querySelector(saved.selector);
  if (!el) return;
  if (saved.keepValue) el.value = saved.value;
  el.focus();
  try {
    el.setSelectionRange(saved.start, saved.end);
  } catch {
    // Not a text input.
  }
}

function render() {
  const focused = captureFocus();
  const nameInput = $('#list-name');
  if (document.activeElement !== nameInput) nameInput.value = state.name;
  const rows = [];
  for (const cat of CATEGORIES) {
    const items = state.items.filter((i) => i.category === cat.id);
    if (!items.length) {
      rows.push(renderEmpty(cat));
      continue;
    }
    items.forEach((item, idx) => {
      rows.push(renderItem(item, cat, idx === 0));
      if (ui.expanded.has(item.id)) rows.push(renderDetails(item));
    });
    if (ui.adding === cat.id) rows.push(`<tr class="add-row"><th></th><td colspan="8">${addForm(cat)}</td></tr>`);
  }
  $('#parts-body').innerHTML = rows.join('');
  renderSummary();
  if (ui.focusAdd) {
    ui.focusAdd = false;
    $('#parts-body').querySelector('.inline-add input')?.focus();
  } else {
    restoreFocus(focused);
  }
}

function catCell(cat, withMore) {
  const more = withMore ? `<button type="button" class="link small" data-act="add-more" data-cat="${cat.id}">+ weitere</button>` : '';
  return `<th class="c-cat" scope="row"><span class="cat-label">${h(cat.label)}</span>${more}</th>`;
}

function addForm(cat) {
  return `<form class="inline-add" data-cat="${cat.id}" autocomplete="off">
    <input type="text" name="url" placeholder="Kleinanzeigen-Link für ${h(cat.label)} einfügen" aria-label="Kleinanzeigen-Link">
    <button type="submit" class="primary">OK</button>
    <button type="button" class="ghost" data-act="cancel-add">Abbrechen</button>
  </form>`;
}

function renderEmpty(cat) {
  const content = ui.adding === cat.id
    ? addForm(cat)
    : `<button type="button" class="choose" data-act="choose" data-cat="${cat.id}">+ ${h(cat.choose)}</button>`;
  return `<tr class="cat-row">${catCell(cat, false)}<td colspan="8">${content}</td></tr>`;
}

function renderItem(item, cat, first) {
  const head = catCell(cat, first);
  const remove = `<td class="c-x"><button type="button" class="icon-btn" data-act="remove" data-id="${item.id}" title="Entfernen" aria-label="Entfernen">×</button></td>`;

  if (item.status === 'loading') {
    return `<tr class="item-row loading">${head}<td colspan="7"><span class="spinner"></span> Lade Anzeige …
      <span class="muted small">${h(shortUrl(item.url))}</span></td>${remove}</tr>`;
  }
  if (item.status === 'error' && !item.listing) {
    return `<tr class="item-row error">${head}<td colspan="7">
      <div class="err">⚠ ${h(item.error)}</div>
      <div class="muted small">${h(shortUrl(item.url))}</div>
      <div class="btn-row">
        <button type="button" class="ghost" data-act="retry" data-id="${item.id}">Erneut versuchen</button>
        <button type="button" class="ghost" data-act="manual" data-id="${item.id}">Manuell eintragen</button>
        <a class="ghost" href="${h(item.url)}" target="_blank" rel="noopener noreferrer">Anzeige öffnen ↗</a>
      </div></td>${remove}</tr>`;
  }

  const L = item.listing;
  const c = compute(item);
  const thumb = isAllowedImage(L.image)
    ? `<img class="thumb" src="${h(L.image)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
    : '<span class="thumb thumb-empty" aria-hidden="true"></span>';
  const meta = [
    L.location && `📍 ${h(L.location)}`,
    L.seller?.activeSince && `Konto seit ${h(L.seller.activeSince.slice(0, 4))}`,
    L.seller?.type && (L.seller.type === 'commercial' ? 'gewerblich' : 'privat'),
    L.details?.Zustand && `Zustand: ${h(L.details.Zustand)}`,
  ].filter(Boolean).join(' · ');
  const flags = [
    L.status === 'reserved' && '<span class="flag warn">Reserviert</span>',
    L.status === 'deleted' && '<span class="flag bad">Nicht mehr verfügbar</span>',
    L.manual && '<span class="flag">Manuell</span>',
    item.status === 'error' && `<span class="flag warn" title="${h(item.error)}">Aktualisierung fehlgeschlagen</span>`,
  ].filter(Boolean).join(' ');

  const priceCell = c.price == null
    ? '<span class="muted">—</span>'
    : `${eur(c.price)}${L.priceType === 'vb' && item.overrides.price == null ? ' <span class="tag">VB</span>' : ''}`;
  const shippingCell = `${eur(c.shipping)}<span class="sub">${h(c.shippingSource)}</span>`;
  const marketCell = renderMarketCell(item, c);
  const risk = c.risk;
  const riskCell = `<button type="button" class="risk-badge ${risk.level}" data-act="toggle" data-id="${item.id}"
      aria-expanded="${ui.expanded.has(item.id)}" title="Details anzeigen">${LEVEL_LABEL[risk.level]} · ${risk.score}</button>`;
  const where = L.manual ? '<span class="muted">—</span>'
    : `<a class="where" href="${h(item.url)}" target="_blank" rel="noopener noreferrer">Kleinanzeigen ↗</a>`;

  return `<tr class="item-row risk-${risk.level}${ui.expanded.has(item.id) ? ' open' : ''}">
    ${head}
    <td class="c-sel" data-label="Auswahl"><div class="sel">${thumb}<div class="sel-text">
      <button type="button" class="title-btn" data-act="toggle" data-id="${item.id}">${h(c.title)}</button> ${flags}
      <div class="meta">${meta}</div></div></div></td>
    <td class="num" data-label="Preis"><span>${priceCell}</span></td>
    <td class="num" data-label="Versand"><span>${shippingCell}</span></td>
    <td class="num strong" data-label="Gesamt"><span>${eur(c.total)}</span></td>
    <td class="num" data-label="Marktpreis"><span>${marketCell}</span></td>
    <td data-label="Risiko">${riskCell}</td>
    <td data-label="Wo">${where}</td>
    ${remove}
  </tr>`;
}

function renderMarketCell(item, c) {
  if (item.market?.status === 'loading' && item.overrides.marketPrice == null) return '<span class="spinner"></span>';
  if (c.market == null) return '<span class="muted">—</span>';
  let diff = '';
  if (c.price != null && c.market > 0) {
    const pct = Math.round((c.price / c.market - 1) * 100);
    const cls = pct <= -40 ? 'bad' : pct <= -25 ? 'warn' : pct >= 30 ? 'muted' : 'okc';
    diff = `<span class="sub ${cls}">${pct > 0 ? '+' : ''}${pct} %</span>`;
  }
  return `${eur(c.market)}${diff || `<span class="sub">${c.marketSource === 'manual' ? 'manuell' : 'Median'}</span>`}`;
}

const SEVERITY_ICON = { high: '●', mid: '●', low: '●', warn: '▲', info: 'ℹ', good: '✓' };

function renderDetails(item) {
  const L = item.listing;
  if (!L) return '';
  const c = compute(item);
  const o = item.overrides;
  const m = item.market;

  const reasons = c.risk.reasons.map((r) => `<li class="sev-${r.severity}"><span class="dot">${SEVERITY_ICON[r.severity]}</span>
    <span>${h(r.text)}</span>${r.points ? `<span class="pts">${r.points > 0 ? '+' : ''}${r.points}</span>` : ''}</li>`).join('');
  const tips = c.risk.level === 'low' ? '' : `<div class="tips"><b>So schützt du dich:</b> nur über Kleinanzeigen schreiben,
    „Sicher bezahlen“ oder PayPal Waren &amp; Dienstleistungen nutzen, nie „Freunde &amp; Familie“, keine Zahlungslinks anklicken,
    bei Abholung vor Ort testen.</div>`;

  const catOptions = CATEGORIES.map((cat) => `<option value="${cat.id}"${cat.id === item.category ? ' selected' : ''}>${h(cat.label)}</option>`).join('');

  let market = '';
  if (m?.status === 'loading') market = '<p><span class="spinner"></span> Suche Vergleichsangebote …</p>';
  else if (m?.status === 'error') market = `<p class="err">⚠ ${h(m.error)}</p>`;
  else if (m?.status === 'ok' && m.stats) {
    market = `<p>Median <b>${eur(m.stats.median)}</b> aus ${m.stats.count} Angeboten
      <span class="muted">(Mittelfeld ${eur(m.stats.p25)} – ${eur(m.stats.p75)})</span></p>
      <ul class="samples">${m.samples.map((s) => `<li><a href="${h(s.url)}" target="_blank" rel="noopener noreferrer">${h(s.title)}</a>
        <span>${eur(s.price)}${s.priceType === 'vb' ? ' VB' : ''}</span></li>`).join('')}</ul>`;
  } else if (m?.status === 'ok') {
    market = `<p class="muted">Keine passenden Vergleichsangebote gefunden (${m.found} Treffer insgesamt). Suchbegriff anpassen oder Marktpreis manuell eintragen.</p>`;
  }
  const searchLink = m?.searchUrl ? `<a href="${h(m.searchUrl)}" target="_blank" rel="noopener noreferrer">Suche auf Kleinanzeigen öffnen ↗</a>` : '';

  const seller = L.seller ?? {};
  const sellerLine = [
    seller.name && h(seller.name),
    seller.type && (seller.type === 'commercial' ? 'Gewerblich' : 'Privat'),
    seller.activeSince && `aktiv seit ${h(seller.activeSince.split('-').reverse().join('.'))}`,
    seller.badges?.length && h(seller.badges.join(', ')),
  ].filter(Boolean).join(' · ');
  const desc = (L.description ?? '').trim();

  return `<tr class="detail-row"><td colspan="9"><div class="details">
    <section class="d-risk">
      <h4>Risiko-Check <span class="risk-badge ${c.risk.level}">${LEVEL_LABEL[c.risk.level]} · ${c.risk.score}/100</span></h4>
      <ul class="reasons">${reasons || '<li class="sev-info"><span class="dot">ℹ</span><span>Keine Auffälligkeiten.</span></li>'}</ul>
      ${tips}
    </section>
    <section class="d-edit">
      <h4>Werte anpassen</h4>
      <label>Titel <input data-field="title" data-id="${item.id}" value="${h(o.title ?? '')}" placeholder="${h(L.title ?? '')}"></label>
      <div class="two">
        <label>Preis (€) <input data-field="price" data-id="${item.id}" inputmode="decimal" value="${num(o.price)}" placeholder="${L.price != null ? num(L.price) : 'fehlt'}"></label>
        <label>Versand (€) <input data-field="shipping" data-id="${item.id}" inputmode="decimal" value="${num(o.shipping)}"
          placeholder="${num(L.shipping?.cost ?? shippingEstimate(item.category))}"${c.pickup ? ' disabled' : ''}></label>
      </div>
      <label class="check"><input type="checkbox" data-field="pickup" data-id="${item.id}"${c.pickup ? ' checked' : ''}> Abholung (kein Versand)</label>
      <div class="two">
        <label>Marktpreis (€) <input data-field="marketPrice" data-id="${item.id}" inputmode="decimal" value="${num(o.marketPrice)}"
          placeholder="${m?.stats?.median != null ? num(m.stats.median) : 'z. B. von Geizhals'}"></label>
        <label>Komponente <select data-field="category" data-id="${item.id}">${catOptions}</select></label>
      </div>
      <p class="muted small">Versand laut Anzeige: ${h(L.shipping?.text || 'keine Angabe')}</p>
      <div class="btn-row">
        ${L.manual ? '' : `<button type="button" class="ghost" data-act="refresh" data-id="${item.id}">Neu laden</button>`}
        <button type="button" class="ghost danger" data-act="remove" data-id="${item.id}">Entfernen</button>
      </div>
    </section>
    <section class="d-market">
      <h4>Marktvergleich</h4>
      ${L.manual ? '<p class="muted">Bei manuellen Einträgen Marktpreis links eintragen.</p>' : `
      <form class="market-form" data-id="${item.id}" autocomplete="off">
        <input name="q" value="${h(m?.query ?? o.query ?? buildQuery(L.title ?? ''))}" aria-label="Suchbegriff für Vergleich">
        <button type="submit" class="primary">Suchen</button>
      </form>
      ${market}${searchLink}`}
    </section>
    <section class="d-desc">
      <h4>Anzeige</h4>
      ${sellerLine ? `<p class="small">${sellerLine}</p>` : ''}
      ${L.postedAt ? `<p class="small muted">Eingestellt am ${h(L.postedAt.split('-').reverse().join('.'))} · ${L.images ?? 0} Foto(s)</p>` : ''}
      ${desc ? `<p class="desc">${h(desc.length > 700 ? `${desc.slice(0, 700)} …` : desc)}</p>` : ''}
    </section>
  </div></td></tr>`;
}

function renderSummary() {
  const entries = state.items.filter((i) => i.listing).map((i) => ({ item: i, c: compute(i) }));
  const priced = entries.filter((e) => e.c.price != null);
  const base = priced.reduce((s, e) => s + e.c.price, 0);
  const ship = priced.reduce((s, e) => s + e.c.shipping, 0);
  const high = entries.filter((e) => e.c.risk.level === 'high').length;
  const mid = entries.filter((e) => e.c.risk.level === 'mid').length;
  const loading = state.items.filter((i) => i.status === 'loading').length;
  const errors = state.items.filter((i) => i.status === 'error' && !i.listing).length;

  const status = $('#risk-status');
  let cls = 'ok';
  let text;
  if (!state.items.length) text = '<b>Risiko-Check:</b> Füge Kleinanzeigen-Links hinzu.';
  else if (high) {
    cls = 'bad';
    text = `<b>Achtung:</b> ${high} Anzeige${high > 1 ? 'n' : ''} mit hohem Scam-Risiko${mid ? `, ${mid} auffällig` : ''}.`;
  } else if (mid) {
    cls = 'warn';
    text = `<b>Risiko-Check:</b> ${mid} Anzeige${mid > 1 ? 'n' : ''} auffällig – Details prüfen.`;
  } else text = '<b>Risiko-Check:</b> Keine Auffälligkeiten gefunden.';
  if (loading) text += ` <span class="small">(${loading} wird geladen …)</span>`;
  if (errors) text += ` <span class="small">(${errors} Fehler)</span>`;
  status.className = `risk-status ${cls}`;
  status.innerHTML = `<span class="status-icon">${cls === 'ok' ? '✓' : '⚠'}</span> ${text}`;

  $('#total-status').innerHTML = `Gesamt: <b>${eur(base + ship)}</b>`;
  $('#parts-foot').innerHTML = priced.length ? `<tr>
      <th colspan="2" class="foot-label">Summe (${priced.length} Teil${priced.length > 1 ? 'e' : ''})</th>
      <td class="num" data-label="Preis">${eur(base)}</td>
      <td class="num" data-label="Versand">${eur(ship)}</td>
      <td class="num strong" data-label="Gesamt">${eur(base + ship)}</td>
      <td colspan="4"></td>
    </tr>` : '';
}

function shortUrl(url) {
  return String(url).replace(/^https:\/\/www\./, '').slice(0, 90);
}

// ---------- text export ----------

function listAsText() {
  const lines = [state.name, '='.repeat(Math.min(60, state.name.length || 10))];
  let base = 0;
  let ship = 0;
  for (const cat of CATEGORIES) {
    for (const item of state.items.filter((i) => i.category === cat.id && i.listing)) {
      const c = compute(item);
      if (c.price != null) {
        base += c.price;
        ship += c.shipping;
      }
      const shipText = c.pickup ? 'Abholung' : `+ ${eur(c.shipping)} Versand`;
      lines.push(`${cat.label}: ${c.title} – ${eur(c.price)} ${shipText} (Risiko: ${LEVEL_LABEL[c.risk.level]})`);
      if (!item.listing.manual) lines.push(`  ${item.url}`);
    }
  }
  lines.push('', `Summe: ${eur(base)} + ${eur(ship)} Versand = ${eur(base + ship)}`);
  return lines.join('\n');
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = Object.assign(document.createElement('textarea'), { value: text });
    document.body.append(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }
}

// ---------- events ----------

let toastTimer;
function toast(message, isError = false) {
  const el = $('#toast');
  el.textContent = message;
  el.className = `toast${isError ? ' error' : ''}`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

const byId = (id) => state.items.find((i) => i.id === id);

const actions = {
  choose(el) { Object.assign(ui, { adding: el.dataset.cat, focusAdd: true }); render(); },
  'add-more'(el) { Object.assign(ui, { adding: el.dataset.cat, focusAdd: true }); render(); },
  'cancel-add'() { ui.adding = null; render(); },
  toggle(el) {
    const id = el.dataset.id;
    if (ui.expanded.has(id)) ui.expanded.delete(id);
    else ui.expanded.add(id);
    render();
  },
  remove(el) {
    state.items = state.items.filter((i) => i.id !== el.dataset.id);
    ui.expanded.delete(el.dataset.id);
    save();
    render();
  },
  retry(el) { const item = byId(el.dataset.id); if (item) loadListing(item); },
  refresh(el) { const item = byId(el.dataset.id); if (item) loadListing(item); },
  manual(el) {
    const item = byId(el.dataset.id);
    if (!item) return;
    item.listing = { manual: true, url: item.url, title: '', price: null, priceType: 'fixed', shipping: {}, seller: {} };
    item.overrides.title ||= 'Manuelle Eingabe';
    item.status = 'ok';
    item.error = null;
    ui.expanded.add(item.id);
    save();
    render();
  },
  'copy-text'() { copyText(listAsText()).then(() => toast('Liste als Text kopiert.')); },
  export() {
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob),
      download: `${state.name.replace(/[^\p{L}\p{N}-]+/gu, '_') || 'liste'}.json`,
    });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  },
  import() { $('#file-import').click(); },
  clear() {
    if (!state.items.length || !confirm('Ganze Liste leeren?')) return;
    state.items = [];
    ui.expanded.clear();
    save();
    render();
  },
};

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el || !actions[el.dataset.act]) return;
  e.preventDefault();
  actions[el.dataset.act](el);
});

document.addEventListener('submit', (e) => {
  const form = e.target;
  e.preventDefault();
  if (form.id === 'quick-add') {
    if (addListing($('#quick-url').value)) $('#quick-url').value = '';
  } else if (form.classList.contains('inline-add')) {
    addListing(form.elements.url.value, form.dataset.cat);
  } else if (form.classList.contains('market-form')) {
    const item = byId(form.dataset.id);
    if (!item) return;
    item.overrides.query = form.elements.q.value.trim() || undefined;
    loadMarket(item);
  }
});

$('#parts-body').addEventListener('change', (e) => {
  const el = e.target;
  const item = byId(el.dataset.id);
  if (!item || !el.dataset.field) return;
  const field = el.dataset.field;
  if (field === 'category') item.category = el.value;
  else if (field === 'pickup') item.overrides.pickup = el.checked;
  else if (field === 'title') item.overrides.title = el.value.trim() || undefined;
  else {
    const n = parseNumberInput(el.value);
    if (Number.isNaN(n)) {
      toast('Bitte eine Zahl eingeben, z. B. 249,90.', true);
      return;
    }
    item.overrides[field] = n ?? undefined;
  }
  save();
  render();
});

// Thumbnails come from Kleinanzeigen's CDN; show the placeholder when one fails.
document.addEventListener('error', (e) => {
  if (e.target instanceof HTMLImageElement && e.target.classList.contains('thumb')) {
    e.target.replaceWith(Object.assign(document.createElement('span'), { className: 'thumb thumb-empty' }));
  }
}, true);

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && ui.adding) {
    ui.adding = null;
    render();
  }
});

$('#list-name').addEventListener('input', (e) => {
  state.name = e.target.value;
  save();
});

$('#file-import').addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  e.target.value = '';
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (!Array.isArray(data?.items)) throw new Error('format');
    Object.assign(state, sanitizeState(data));
    ui.expanded.clear();
    save();
    render();
    toast(`${state.items.length} Einträge importiert.`);
  } catch {
    toast('Datei ist keine gültige Anzeigen-Picker-Liste.', true);
  }
});

render();
