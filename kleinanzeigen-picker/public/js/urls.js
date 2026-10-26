// Shared by browser and server. The server only ever fetches URLs built here,
// so a pasted link can never make it request anything but kleinanzeigen.de.

export const BASE_URL = 'https://www.kleinanzeigen.de';

export const ALLOWED_HOSTS = new Set([
  'kleinanzeigen.de', 'www.kleinanzeigen.de', 'm.kleinanzeigen.de',
  'ebay-kleinanzeigen.de', 'www.ebay-kleinanzeigen.de', 'm.ebay-kleinanzeigen.de',
]);

// Accepts a bare link, a link without https://, or the share text the app
// produces ("Schau mal: https://www.kleinanzeigen.de/s-anzeige/..."). Returns
// the canonical listing URL or null.
export function extractListingUrl(input) {
  const m = String(input ?? '').match(/(?:https?:\/\/)?(?:[a-z0-9-]+\.)*(?:ebay-)?kleinanzeigen\.de\/s-anzeige\/[^\s"'<>]+/i);
  if (!m) return null;
  let u;
  try {
    u = new URL(/^https?:\/\//i.test(m[0]) ? m[0] : `https://${m[0]}`);
  } catch {
    return null;
  }
  if (!ALLOWED_HOSTS.has(u.hostname.toLowerCase())) return null;
  const path = u.pathname.replace(/\/+$/, '');
  if (!/^\/s-anzeige\/[^/]+/.test(path)) return null;
  return BASE_URL + path;
}

export function adIdFromUrl(url) {
  return String(url ?? '').match(/\/(\d{5,})-\d+-\d+\/?$/)?.[1] ?? null;
}

export function categoryIdFromUrl(url) {
  return String(url ?? '').match(/\/\d{5,}-(\d+)-\d+\/?$/)?.[1] ?? null;
}

const CATEGORY_SLUGS = { 225: 'pc-zubehoer-software' };

export function buildSearchUrl(query, categoryId) {
  const words = String(query ?? '').toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean).slice(0, 8);
  const slug = words.map(encodeURIComponent).join('-');
  const catSlug = CATEGORY_SLUGS[categoryId];
  return catSlug ? `${BASE_URL}/s-${catSlug}/${slug}/k0c${categoryId}` : `${BASE_URL}/s-${slug}/k0`;
}

export function isAllowedImage(url) {
  return /^https:\/\/(img\.kleinanzeigen\.de|i\.ebayimg\.com)\//i.test(String(url ?? ''));
}
