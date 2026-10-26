import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseListing } from '../lib/parse.js';
import { assessRisk } from '../public/js/risk.js';

const now = Date.parse('2026-10-26T12:00:00');
const load = (name) => parseListing(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8'), { now });

test('a normal listing at market price is low risk', () => {
  const listing = load('listing.html');
  const r = assessRisk({ listing, price: listing.price, market: 440, marketSource: 'search', marketCount: 6, now });
  assert.equal(r.level, 'low');
  assert.equal(r.score, 0);
  // "kein Mining" and "nicht defekt" are negations, not warnings
  assert.ok(!r.reasons.some((x) => x.severity === 'warn'), JSON.stringify(r.reasons));
});

test('a typical fake offer is high risk with the reasons spelled out', () => {
  const listing = load('listing-scam.html');
  const r = assessRisk({ listing, price: listing.price, market: 1600, marketSource: 'search', marketCount: 12, now });
  assert.equal(r.level, 'high');
  assert.equal(r.score, 100);
  const text = r.reasons.map((x) => x.text).join('\n');
  for (const expected of ['unter Marktpreis', 'erst 6 Tage alt', 'PayPal Freunde', 'außerhalb von Kleinanzeigen', 'Ausland', 'Nur Versand']) {
    assert.ok(text.includes(expected), `missing "${expected}" in:\n${text}`);
  }
});

test('cheap because defective is a condition warning, not a scam signal', () => {
  const listing = {
    title: 'RTX 3080 defekt für Bastler', description: 'Zeigt Artefakte, sonst ok. Abholung oder Versand.',
    images: 4, seller: { activeSince: '2015-01-01' }, shipping: {},
  };
  const r = assessRisk({ listing, price: 120, market: 440, marketSource: 'search', marketCount: 10, now });
  assert.equal(r.level, 'low');
  assert.ok(r.reasons.some((x) => x.severity === 'warn' && /Defekt/.test(x.text)));
});

test('missing market price is reported, not guessed', () => {
  const listing = { title: 'Exotisches Teil', description: 'x'.repeat(100), images: 3, seller: {}, shipping: {} };
  const r = assessRisk({ listing, price: 50, market: null, now });
  assert.ok(r.reasons.some((x) => /Kein Marktpreis/.test(x.text)));
  assert.equal(r.ratio, null);
});

test('manual entries are only checked against the price', () => {
  const r = assessRisk({ listing: { manual: true, title: '', shipping: {}, seller: {} }, price: 100, market: 400, marketSource: 'manual', now });
  assert.equal(r.level, 'mid');
  assert.equal(r.reasons.length, 1);
});
