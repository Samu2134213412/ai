// Reads Kleinanzeigen HTML without a DOM library. Every field has a fallback
// (ids -> classes -> meta tags -> plain text), because the markup changes
// now and then and a half-filled listing is more useful than an error.

import { BASE_URL, adIdFromUrl, categoryIdFromUrl, isAllowedImage } from '../public/js/urls.js';
import { germanDateToIso } from '../public/js/format.js';

export class ParseError extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
  }
}

const NAMED = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', euro: '€', auml: 'ä', ouml: 'ö',
  uuml: 'ü', Auml: 'Ä', Ouml: 'Ö', Uuml: 'Ü', szlig: 'ß', bull: '•', middot: '·', ndash: '–',
  mdash: '—', hellip: '…', bdquo: '„', ldquo: '“', rdquo: '”', lsquo: '‘', rsquo: '’', shy: '',
};

export function decodeEntities(s) {
  return String(s).replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
    if (e[0] === '#') {
      const code = e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return code > 0 && code < 0x110000 ? String.fromCodePoint(code) : m;
    }
    return Object.hasOwn(NAMED, e) ? NAMED[e] : m;
  });
}

export function htmlToText(html) {
  if (!html) return '';
  return decodeEntities(String(html)
    .replace(/<(script|style|noscript)\b[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|h\d)>/gi, '\n')
    .replace(/<[^>]+>/g, ' '))
    .replace(/[ \t\r\f\v ]+/g, ' ')
    .replace(/ ?\n ?/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

const oneLine = (html) => htmlToText(html).replace(/\s+/g, ' ').trim();

function innerById(html, id) {
  const re = new RegExp(`<([a-z][a-z0-9]*)\\b[^>]*\\sid=["']${id}["'][^>]*>([\\s\\S]*?)<\\/\\1\\s*>`, 'i');
  return html.match(re)?.[2] ?? null;
}

function classRegex(cls, flags) {
  return new RegExp(`<([a-z][a-z0-9]*)\\b[^>]*\\sclass=["'](?:[^"']*\\s)?${cls}(?:\\s[^"']*)?["'][^>]*>([\\s\\S]*?)<\\/\\1\\s*>`, flags);
}

function innerByClass(html, cls) {
  return html.match(classRegex(cls, 'i'))?.[2] ?? null;
}

function allByClass(html, cls) {
  return [...html.matchAll(classRegex(cls, 'gi'))].map((m) => m[2]);
}

function parseAttrs(tag) {
  const out = {};
  for (const m of tag.matchAll(/([a-z_:][-\w:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/gi)) {
    out[m[1].toLowerCase()] = decodeEntities(m[2] ?? m[3]);
  }
  return out;
}

function collectMeta(html) {
  const meta = new Map();
  for (const m of html.matchAll(/<meta\b[^>]*>/gi)) {
    const a = parseAttrs(m[0]);
    const key = a.property ?? a.name ?? a.itemprop;
    if (key && a.content != null && !meta.has(key)) meta.set(key, a.content.trim());
  }
  return meta;
}

// "1.234,56 €" -> 1234.56
export function parseEuro(text) {
  const m = String(text ?? '').match(/(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?\s*(?:€|EUR)/i);
  if (!m) return null;
  return Number(m[1].replace(/\./g, '')) + (m[2] ? Number(m[2].padEnd(2, '0')) / 100 : 0);
}

export function parsePrice(text) {
  const t = String(text ?? '').replace(/\s+/g, ' ').trim();
  if (/zu verschenken/i.test(t)) return { price: 0, priceType: 'free' };
  const price = parseEuro(t);
  const vb = /\bVB\b/i.test(t);
  if (price == null) return { price: null, priceType: vb ? 'vb' : 'unknown' };
  return { price, priceType: vb ? 'vb' : 'fixed' };
}

function parseMetaNumber(value) {
  if (value == null || value === '') return null;
  const s = String(value).trim();
  const n = Number(s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : s);
  return Number.isFinite(n) ? n : null;
}

function parseDetails(html) {
  const out = {};
  const re = /<li\b[^>]*class=["'](?:[^"']*\s)?addetailslist--detail(?:\s[^"']*)?["'][^>]*>([\s\S]*?)<\/li>/gi;
  for (const m of html.matchAll(re)) {
    const value = innerByClass(m[1], 'addetailslist--detail--value');
    const label = oneLine(m[1].split(/<span\b/i)[0]);
    if (label && value != null) out[label] = oneLine(value);
  }
  return out;
}

const FREE_SHIPPING = /versandkostenfrei|kostenlose[rn]? versand|versand kostenlos|gratis versand|inkl\.? versand/i;

function parseShipping(region, details, title) {
  const box = oneLine(innerByClass(region, 'boxedarticle--details--shipping') ?? '');
  const text = box || oneLine(region);
  const versand = details.Versand ?? '';
  const m = text.match(/Versand\s*(?:ab|für|:)?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*€/i);
  if (m) return { available: true, pickupOnly: false, cost: parseEuro(`${m[1]} €`), text: m[0].trim() };
  if (/nur abholung/i.test(versand) || /nur abholung/i.test(box)) {
    return { available: false, pickupOnly: true, cost: null, text: 'Nur Abholung' };
  }
  if (/versand möglich/i.test(versand) || /versand möglich/i.test(text)) {
    return FREE_SHIPPING.test(title)
      ? { available: true, pickupOnly: false, cost: 0, text: 'Versand inklusive (laut Titel)' }
      : { available: true, pickupOnly: false, cost: null, text: 'Versand möglich' };
  }
  if (/nur abholung/i.test(text)) return { available: false, pickupOnly: true, cost: null, text: 'Nur Abholung' };
  return { available: null, pickupOnly: false, cost: null, text: '' };
}

function parsePostedAt(html, region, now) {
  const extra = innerById(html, 'viewad-extra-info');
  const text = oneLine(extra ?? region);
  const iso = germanDateToIso(text);
  if (iso) return iso;
  const day = new Date(now);
  if (/\bgestern\b/i.test(text)) day.setDate(day.getDate() - 1);
  else if (!/\bheute\b/i.test(text)) return null;
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
}

function countImages(html, endIdx) {
  const scope = endIdx > 0 ? html.slice(0, endIdx) : html;
  const ids = new Set();
  for (const m of scope.matchAll(/prod-ads\/images\/([0-9a-z/_-]{8,})/gi)) ids.add(m[1].toLowerCase());
  for (const m of scope.matchAll(/i\.ebayimg\.com\/[^"'\s]*?\/z\/([\w~-]{8,})\//gi)) ids.add(m[1]);
  return ids.size;
}

const BADGES = [
  ['TOP Zufriedenheit', /TOP\s+Zufriedenheit/i],
  ['Besonders zufrieden', /Besonders\s+zufrieden/i],
  ['Sehr freundlich', /Sehr\s+freundlich\b/i],
  ['Freundlich', /(?<!Sehr\s)\bFreundlich\b/],
  ['Sehr zuverlässig', /Sehr\s+zuverlässig/i],
  ['Zuverlässig', /(?<!Sehr\s)\bZuverlässig\b/],
];

function parseSeller(html, pageText) {
  const name = oneLine(innerByClass(html, 'userprofile-vip') ?? '') || null;
  const type = /Gewerblicher\s+(Nutzer|Anbieter|Händler)/i.test(pageText) ? 'commercial'
    : /Privater\s+(Nutzer|Anbieter)/i.test(pageText) ? 'private' : null;
  const anchor = pageText.search(/Aktiv seit|Privater Nutzer|Gewerblicher (Nutzer|Anbieter)/i);
  const area = anchor >= 0 ? pageText.slice(Math.max(0, anchor - 1500), anchor + 1500) : '';
  return {
    name,
    type,
    activeSince: germanDateToIso(pageText.match(/Aktiv seit\s*(\d{1,2}\.\d{1,2}\.\d{4})/i)?.[1]),
    badges: BADGES.filter(([, re]) => re.test(area)).map(([label]) => label),
    adsOnline: Number(area.match(/(\d+)\s+Anzeigen?\s+online/i)?.[1]) || null,
    userId: html.match(/[?&]userId=(\d+)/)?.[1] ?? null,
  };
}

export function parseListing(html, { url = null, now = Date.now() } = {}) {
  html = String(html ?? '');
  const meta = collectMeta(html);
  const rawTitle = innerById(html, 'viewad-title');
  let title = rawTitle != null
    ? oneLine(rawTitle)
    : (meta.get('og:title') ?? '').replace(/\s*[|]\s*kleinanzeigen.*$/i, '').trim();

  if (!title) {
    if (/captcha|access denied|zugriff verweigert|ungewöhnlich viele anfragen|too many requests/i.test(html)) {
      throw new ParseError('Kleinanzeigen zeigt eine Bot-Schutz-Seite. Kurz warten und erneut versuchen oder Werte manuell eintragen.', 'blocked');
    }
    if (/nicht mehr verfügbar|wurde gelöscht|existiert nicht/i.test(html)) {
      throw new ParseError('Anzeige ist nicht mehr verfügbar.', 'gone');
    }
    throw new ParseError('Seite konnte nicht als Anzeige gelesen werden.', 'unparsable');
  }

  let status = 'active';
  const prefix = title.match(/^(Reserviert|Gelöscht|Verkauft)\s*[•·|-]\s*/i);
  if (prefix) {
    status = /reserviert/i.test(prefix[1]) ? 'reserved' : 'deleted';
    title = title.slice(prefix[0].length).trim();
  }

  const titleIdx = Math.max(0, html.search(/\sid=["']viewad-title["']/i));
  const descIdx = html.search(/\sid=["']viewad-description/i);
  const region = html.slice(titleIdx, descIdx > titleIdx ? descIdx : titleIdx + 20000);
  const regionText = oneLine(region);
  if (status === 'active' && /nicht mehr verfügbar|wurde (bereits )?gelöscht|bereits verkauft/i.test(regionText)) {
    status = 'deleted';
  }

  const priceText = oneLine(innerById(html, 'viewad-price') ?? innerByClass(html, 'boxedarticle--price') ?? '');
  const { price: textPrice, priceType } = parsePrice(priceText);
  const metaPrice = parseMetaNumber(meta.get('price') ?? meta.get('product:price:amount'));
  const price = textPrice ?? (metaPrice > 0 ? metaPrice : null);

  const details = parseDetails(html);
  const locationText = oneLine(innerById(html, 'viewad-locality') ?? '') || meta.get('addressLocality') || null;
  const description = htmlToText(innerById(html, 'viewad-description-text') ?? '')
    || meta.get('og:description') || meta.get('description') || '';
  const image = meta.get('og:image');
  const pageText = oneLine(html);
  const finalUrl = url ?? (meta.get('og:url') || null);

  return {
    url: finalUrl,
    adId: adIdFromUrl(finalUrl) ?? regionText.match(/Anzeigen-?ID:?\s*(\d{6,})/i)?.[1] ?? null,
    categoryId: categoryIdFromUrl(finalUrl),
    title,
    status,
    price,
    priceType: priceType === 'unknown' && price != null ? 'fixed' : priceType,
    priceText,
    shipping: parseShipping(region, details, title),
    location: locationText,
    zip: locationText?.match(/\b\d{5}\b/)?.[0] ?? null,
    postedAt: parsePostedAt(html, region, now),
    description: description.slice(0, 5000),
    images: countImages(html, descIdx) || (image ? 1 : 0),
    image: isAllowedImage(image) ? image : null,
    seller: parseSeller(html, pageText),
    details,
    breadcrumbs: allByClass(html, 'breadcrump-link').map(oneLine).filter(Boolean),
    buyNow: /Direkt kaufen|Sicher bezahlen/i.test(regionText),
  };
}

export function parseSearch(html) {
  const out = [];
  for (const m of String(html ?? '').matchAll(/<article\b([^>]*)>([\s\S]*?)<\/article>/gi)) {
    const attrs = parseAttrs(m[1]);
    if (!/(^|\s)aditem(\s|$)/.test(attrs.class ?? '')) continue;
    const body = m[2];
    const href = attrs['data-href'] || body.match(/href=["'](\/s-anzeige\/[^"']+)["']/i)?.[1] || null;
    const titleHtml = innerByClass(body, 'ellipsis') ?? body.match(/<h2\b[^>]*>([\s\S]*?)<\/h2>/i)?.[1] ?? '';
    const priceText = oneLine(innerByClass(body, 'aditem-main--middle--price-shipping--price') ?? '')
      || (oneLine(body).match(/\d[\d.]*(?:,\d{1,2})?\s*€(?:\s*VB)?/)?.[0] ?? '');
    out.push({
      adId: attrs['data-adid'] || adIdFromUrl(href),
      title: oneLine(titleHtml),
      ...parsePrice(priceText),
      url: href ? BASE_URL + href : null,
      shipping: oneLine(innerByClass(body, 'aditem-main--middle--price-shipping--shipping') ?? '') || null,
      location: oneLine(innerByClass(body, 'aditem-main--top--left') ?? '') || null,
    });
  }
  return out;
}
