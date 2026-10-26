// Shared by browser and server: turns a listing title into a market search
// query and decides whether another listing is the same product.

const STOPWORDS = new Set((
  'verkaufe verkauf verkaufen biete top zustand neu neuwertig neuwertige wie ovp mit ohne und oder ' +
  'inkl inklusive rechnung garantie gebraucht gebrauchte sehr gut guter gute original ' +
  'originalverpackung versand versandkostenfrei abholung nur für fur der die das den dem ein eine ' +
  'einer im in vb preis festpreis tausch tausche kaum genutzt benutzt funktioniert einwandfrei voll ' +
  'funktionsfähig super zu von bei auf als bitte lesen'
).split(' '));

export function normalize(text) {
  return String(text ?? '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

const geforcePrefix = (num) => (Number(num) >= 2000 ? 'rtx' : 'gtx');

// Recognises GPU/CPU model names, which carry most of a part's price.
// key is canonical, so "RTX3080Ti" and "rtx 3080 ti" compare equal.
export function extractModel(text) {
  const t = ` ${normalize(text)} `;
  let m;
  if ((m = t.match(/\b(rtx|gtx)\s?(\d{3,4})(?:\s?(ti))?(?:\s?(super))?\b/))) {
    return { kind: 'gpu', key: [m[1], m[2], m[3], m[4]].filter(Boolean).join(' ') };
  }
  if ((m = t.match(/\bgeforce\s(\d{4})(?:\s?(ti))?(?:\s?(super))?\b/))) {
    return { kind: 'gpu', key: [geforcePrefix(m[1]), m[1], m[2], m[3]].filter(Boolean).join(' ') };
  }
  if ((m = t.match(/\b(?:rx|radeon(?:\s?rx)?)\s?(\d{3,4})(?:\s?(xtx|xt|gre))?\b/))) {
    return { kind: 'gpu', key: ['rx', m[1], m[2]].filter(Boolean).join(' ') };
  }
  if ((m = t.match(/\barc\s?([ab]\d{3})\b/))) {
    return { kind: 'gpu', key: `arc ${m[1]}` };
  }
  if ((m = t.match(/\bryzen\s?(?:[3579]\s?)?(\d{4})\s?(x3d|xt|x|ge|g|f)?\b/))) {
    return { kind: 'cpu', key: `ryzen ${m[1]}${m[2] ?? ''}` };
  }
  if ((m = t.match(/\bamd\s(\d{4})(x3d|xt|x|g)\b/))) {
    return { kind: 'cpu', key: `ryzen ${m[1]}${m[2]}` };
  }
  if ((m = t.match(/\bultra\s?([579])\s?(\d{3})(kf|k|f|t)?\b/))) {
    return { kind: 'cpu', key: `ultra ${m[1]} ${m[2]}${m[3] ?? ''}` };
  }
  if ((m = t.match(/\b(?:core\s?)?i([3579])\s?(\d{4,5})(ks|kf|k|f|t)?\b/))) {
    return { kind: 'cpu', key: `i${m[1]} ${m[2]}${m[3] ?? ''}` };
  }
  return null;
}

export function buildQuery(title) {
  const model = extractModel(title);
  if (model) return model.key;
  const words = [];
  for (const w of normalize(title).split(' ')) {
    if (w.length < 2 || STOPWORDS.has(w) || words.includes(w)) continue;
    words.push(w);
    if (words.length === 5) break;
  }
  return words.join(' ');
}

// Words that mark a search hit as a different kind of offer. A hit is only
// dropped for one of these if the query itself doesn't contain it.
const OFF_TOPIC = [
  /\b(suche|tausche|gesucht)\b/,
  /\b(defekt\w*|bastler|kaputt|ohne funktion)\b/,
  /\b(nur|leere?)\s(ovp|karton|verpackung)\b|\bovp leer\b|\bleerkarton\b/,
  /\b(backplate|halterung|wasserblock|waterblock|stützwinkel)\b/,
  /\b(gaming pc|komplett pc|pc system|rechner|laptop|notebook)\b/,
];

export function matchesComparable(title, query, { allowDefect = false } = {}) {
  const t = normalize(title);
  const q = normalize(query);
  for (const re of OFF_TOPIC) {
    if (allowDefect && re === OFF_TOPIC[1]) continue;
    if (re.test(t) && !re.test(q)) return false;
  }
  const model = extractModel(q);
  if (model) return extractModel(t)?.key === model.key;
  const compact = t.replace(/\s/g, '');
  return q.split(' ').filter((w) => /\d/.test(w)).every((w) => compact.includes(w));
}
