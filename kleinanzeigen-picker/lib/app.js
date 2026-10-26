import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createKleinanzeigenClient, FetchError } from './fetcher.js';
import { parseListing, parseSearch, ParseError } from './parse.js';
import { priceStats } from './market.js';
import { buildSearchUrl, extractListingUrl } from '../public/js/urls.js';
import { matchesComparable } from '../public/js/query.js';

const PUBLIC_DIR = fileURLToPath(new URL('../public/', import.meta.url));

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.json': 'application/json; charset=utf-8',
};

const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' data: https://img.kleinanzeigen.de https://i.ebayimg.com; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'",
};

const LOCAL_HOSTNAMES = new Set(['localhost', '127.0.0.1', '[::1]']);

function sendJson(res, status, body) {
  res.writeHead(status, { ...SECURITY_HEADERS, 'Content-Type': TYPES['.json'], 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(body));
}

function errorStatus(err) {
  if (err instanceof ParseError) return err.code === 'gone' ? 404 : 502;
  if (err instanceof FetchError) return err.code === 'blocked' ? 503 : 502;
  return 500;
}

export function createServer({ fetchImpl = globalThis.fetch, gapMs, allowAnyHost = false } = {}) {
  const client = createKleinanzeigenClient({ fetchImpl, gapMs });

  async function listing(params) {
    const target = extractListingUrl(params.get('url'));
    if (!target) {
      return [400, { error: 'Kein Kleinanzeigen-Anzeigenlink erkannt (…kleinanzeigen.de/s-anzeige/…).' }];
    }
    const page = await client.get(target);
    if (!page.html || !new URL(page.url).pathname.startsWith('/s-anzeige/')) {
      return [404, { error: 'Anzeige ist nicht mehr verfügbar (gelöscht oder verkauft).' }];
    }
    return [200, { listing: parseListing(page.html, { url: page.url }) }];
  }

  async function market(params) {
    const query = (params.get('q') ?? '').trim().slice(0, 100);
    if (!query) return [400, { error: 'Suchbegriff fehlt.' }];
    const cat = /^\d{1,5}$/.test(params.get('cat') ?? '') ? params.get('cat') : null;
    const exclude = params.get('exclude');
    const allowDefect = params.get('defect') === '1';
    const searchUrl = buildSearchUrl(query, cat);
    const page = await client.get(searchUrl);
    const found = parseSearch(page.html);
    const comparable = found.filter((r) => r.adId !== exclude && r.price > 0
      && matchesComparable(r.title, query, { allowDefect }));
    const stats = priceStats(comparable.map((r) => r.price));
    return [200, {
      query,
      searchUrl,
      found: found.length,
      stats,
      samples: comparable.slice(0, 8).map(({ title, price, priceType, url }) => ({ title, price, priceType, url })),
    }];
  }

  async function serveStatic(pathname, res, method) {
    let path;
    try {
      path = decodeURIComponent(pathname);
    } catch {
      res.writeHead(400).end();
      return;
    }
    const file = resolve(PUBLIC_DIR, `.${path === '/' ? '/index.html' : path}`);
    if (!file.startsWith(PUBLIC_DIR)) {
      res.writeHead(403).end();
      return;
    }
    try {
      const body = await readFile(file);
      res.writeHead(200, {
        ...SECURITY_HEADERS,
        'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream',
        'Cache-Control': 'no-cache',
      });
      res.end(method === 'HEAD' ? undefined : body);
    } catch {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Nicht gefunden');
    }
  }

  return http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    // Blocks DNS-rebinding: only pages served from localhost may use the API.
    const hostname = (req.headers.host ?? '').replace(/:\d+$/, '').toLowerCase();
    if (!allowAnyHost && !LOCAL_HOSTNAMES.has(hostname)) {
      res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Nur über localhost erreichbar.');
      return;
    }
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.writeHead(405, { Allow: 'GET, HEAD' }).end();
      return;
    }
    const routes = { '/api/listing': listing, '/api/market': market };
    if (routes[url.pathname]) {
      try {
        const [status, body] = await routes[url.pathname](url.searchParams);
        sendJson(res, status, body);
      } catch (err) {
        if (!(err instanceof FetchError || err instanceof ParseError)) console.error(err);
        sendJson(res, errorStatus(err), { error: err instanceof FetchError || err instanceof ParseError ? err.message : 'Interner Fehler.' });
      }
      return;
    }
    if (url.pathname.startsWith('/api/')) {
      sendJson(res, 404, { error: 'Unbekannter Endpunkt.' });
      return;
    }
    await serveStatic(url.pathname, res, req.method);
  });
}
