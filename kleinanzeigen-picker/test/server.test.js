import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import http from 'node:http';
import { createServer } from '../lib/app.js';

const fixture = (name) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8');
const LISTING = 'https://www.kleinanzeigen.de/s-anzeige/msi-rtx-3080-gaming-x-trio/2912345678-225-3331';
const requested = [];

function fakeFetch(url) {
  requested.push(url);
  const html = (body, status = 200, headers = {}) => new Response(body, { status, headers });
  if (url === LISTING) return Promise.resolve(html(fixture('listing.html')));
  if (url.endsWith('/s-anzeige/old/2900000000-225-1')) return Promise.resolve(html('', 301, { location: '/s-pc-zubehoer-software/c225' }));
  if (url.endsWith('/s-anzeige/evil/2900000001-225-1')) return Promise.resolve(html('', 302, { location: 'https://evil.example/' }));
  if (url.endsWith('/s-anzeige/blocked/2900000002-225-1')) return Promise.resolve(html('nope', 403));
  if (url.includes('/s-pc-zubehoer-software/rtx-3080/k0c225')) return Promise.resolve(html(fixture('search.html')));
  if (url.includes('/s-pc-zubehoer-software/c225')) return Promise.resolve(html('<html>Kategorie</html>'));
  return Promise.resolve(html('not found', 404));
}

let server;
let base;
before(async () => {
  server = createServer({ fetchImpl: fakeFetch, gapMs: 0 });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  base = `http://localhost:${server.address().port}`;
});
after(() => server.close());

const get = async (path) => {
  const res = await fetch(base + path);
  return { status: res.status, body: res.headers.get('content-type')?.includes('json') ? await res.json() : await res.text() };
};

// fetch() normalises paths and won't send a custom Host header; raw http does.
const rawStatus = (path, host) => new Promise((resolve, reject) => {
  const req = http.request({ port: server.address().port, host: '127.0.0.1', path, headers: { Host: host ?? 'localhost' } }, (res) => {
    res.resume();
    resolve(res.statusCode);
  });
  req.on('error', reject).end();
});

test('GET /api/listing returns the parsed listing', async () => {
  const { status, body } = await get(`/api/listing?url=${encodeURIComponent(`${LISTING}?utm=1`)}`);
  assert.equal(status, 200);
  assert.equal(body.listing.price, 420);
  assert.equal(body.listing.shipping.cost, 6.99);
});

test('GET /api/listing rejects foreign links without fetching them', async () => {
  const before = requested.length;
  const { status, body } = await get(`/api/listing?url=${encodeURIComponent('https://evil.example/s-anzeige/x/1')}`);
  assert.equal(status, 400);
  assert.match(body.error, /Kein Kleinanzeigen/);
  assert.equal(requested.length, before);
});

test('deleted listings, foreign redirects and bot blocks become clear errors', async () => {
  const q = (slug) => `/api/listing?url=${encodeURIComponent(`https://www.kleinanzeigen.de/s-anzeige/${slug}`)}`;
  let r = await get(q('old/2900000000-225-1'));
  assert.equal(r.status, 404);
  assert.match(r.body.error, /nicht mehr verfügbar/);
  r = await get(q('evil/2900000001-225-1'));
  assert.equal(r.status, 502);
  assert.ok(!requested.some((u) => u.startsWith('https://evil.example')));
  r = await get(q('blocked/2900000002-225-1'));
  assert.equal(r.status, 503);
  assert.match(r.body.error, /Bot-Schutz/);
});

test('GET /api/market returns stats over comparable listings only', async () => {
  const { status, body } = await get('/api/market?q=rtx%203080&cat=225&exclude=2912345678');
  assert.equal(status, 200);
  assert.equal(body.found, 11);
  // 400, 450, 430, 470 kept; Ti, Suche, defekt, VB-only, the ad itself, 1 € and 1.050 € dropped
  assert.equal(body.stats.count, 4);
  assert.equal(body.stats.median, 440);
  assert.equal(body.searchUrl, 'https://www.kleinanzeigen.de/s-pc-zubehoer-software/rtx-3080/k0c225');
});

test('static files are served, traversal and foreign Host headers are not', async () => {
  const index = await get('/');
  assert.equal(index.status, 200);
  assert.match(index.body, /Anzeigen-Picker/);
  assert.equal((await get('/js/app.js')).status, 200);
  assert.equal(await rawStatus('/../server.js'), 404, 'URL parser already drops the ..');
  assert.equal(await rawStatus('/..%2fserver.js'), 403);
  assert.equal(await rawStatus('/', 'attacker.example'), 403);
  assert.equal(await rawStatus('/', '127.0.0.1:3000'), 200);
});
