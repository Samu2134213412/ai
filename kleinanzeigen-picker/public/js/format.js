const EUR = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' });

export function eur(n) {
  return n == null || !Number.isFinite(n) ? '—' : EUR.format(n);
}

export function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// "1.234,50 €" / "1.200" / "1234.5" / "" -> number | null (empty) | NaN (garbage)
export function parseNumberInput(value) {
  const s = String(value ?? '').replace(/€|\s/g, '');
  if (!s) return null;
  const thousandsOnly = /^\d{1,3}(\.\d{3})+$/.test(s);
  const normalized = s.includes(',') || thousandsOnly ? s.replace(/\./g, '').replace(',', '.') : s;
  const n = Number(normalized);
  return Number.isFinite(n) && n >= 0 ? n : NaN;
}

// 249.9 -> "249,9" for input fields; parseNumberInput reads it back.
export function numberForInput(n) {
  return n == null || !Number.isFinite(n) ? '' : String(n).replace('.', ',');
}

// "26.10.2026" -> "2026-10-26"
export function germanDateToIso(text) {
  const m = String(text ?? '').match(/(\d{1,2})\.(\d{1,2})\.(\d{4})/);
  if (!m) return null;
  return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
}
