import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseListing, parsePrice, parseSearch, ParseError } from '../lib/parse.js';
import { priceStats } from '../lib/market.js';

const fixture = (name) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8');
const URL_OK = 'https://www.kleinanzeigen.de/s-anzeige/msi-rtx-3080-gaming-x-trio/2912345678-225-3331';

test('parsePrice handles German formats', () => {
  assert.deepEqual(parsePrice('420 € VB'), { price: 420, priceType: 'vb' });
  assert.deepEqual(parsePrice('1.250 €'), { price: 1250, priceType: 'fixed' });
  assert.deepEqual(parsePrice('19,90 €'), { price: 19.9, priceType: 'fixed' });
  assert.deepEqual(parsePrice('VB'), { price: null, priceType: 'vb' });
  assert.deepEqual(parsePrice('Zu verschenken'), { price: 0, priceType: 'free' });
  assert.deepEqual(parsePrice(''), { price: null, priceType: 'unknown' });
});

test('parseListing reads a normal listing', () => {
  const l = parseListing(fixture('listing.html'), { url: URL_OK, now: Date.parse('2026-10-26T12:00:00') });
  assert.equal(l.title, 'MSI GeForce RTX 3080 Gaming X Trio 10GB – Top Zustand');
  assert.equal(l.price, 420);
  assert.equal(l.priceType, 'vb');
  assert.deepEqual(l.shipping, { available: true, pickupOnly: false, cost: 6.99, text: 'Versand ab 6,99 €' });
  assert.equal(l.location, '10115 Berlin - Mitte');
  assert.equal(l.zip, '10115');
  assert.equal(l.postedAt, '2026-10-24');
  assert.equal(l.adId, '2912345678');
  assert.equal(l.categoryId, '225');
  assert.equal(l.images, 3);
  assert.match(l.image, /^https:\/\/img\.kleinanzeigen\.de\//);
  assert.equal(l.details.Art, 'Grafikkarten');
  assert.equal(l.details.Zustand, 'Sehr gut');
  assert.match(l.description, /^Verkaufe meine RTX 3080, lief nur zum Zocken, kein Mining\.\nRechnung vorhanden/);
  assert.deepEqual(l.seller, {
    name: 'Jonas', type: 'private', activeSince: '2016-05-12',
    badges: ['TOP Zufriedenheit', 'Freundlich', 'Zuverlässig'], adsOnline: 14, userId: '55512345',
  });
  assert.deepEqual(l.breadcrumbs, ['PC-Zubehör & Software', 'Grafikkarten']);
  assert.equal(l.status, 'active');
});

test('parseListing reads relative dates and reserved titles', () => {
  const now = Date.parse('2026-10-26T12:00:00');
  const scam = parseListing(fixture('listing-scam.html'), { url: 'https://www.kleinanzeigen.de/s-anzeige/x/2999999999-225-1', now });
  assert.equal(scam.postedAt, '2026-10-26');
  assert.equal(scam.images, 1);
  assert.equal(scam.seller.activeSince, '2026-10-20');
  assert.deepEqual(scam.seller.badges, []);

  const reserved = parseListing('<h1 id="viewad-title"><span class="pvap-reserved-title">Reserviert • </span>Ryzen 7 5800X</h1><h2 id="viewad-price">150 €</h2>');
  assert.equal(reserved.status, 'reserved');
  assert.equal(reserved.title, 'Ryzen 7 5800X');
});

test('parseListing detects pickup-only and falls back to meta tags', () => {
  const html = `<meta property="og:title" content="be quiet! Pure Base 500 | kleinanzeigen.de">
    <meta itemprop="price" content="45.00">
    <li class="addetailslist--detail">Versand<span class="addetailslist--detail--value">Nur Abholung</span></li>`;
  const l = parseListing(html);
  assert.equal(l.title, 'be quiet! Pure Base 500');
  assert.equal(l.price, 45);
  assert.equal(l.priceType, 'fixed');
  assert.equal(l.shipping.pickupOnly, true);
});

test('parseListing recognises bot-protection pages', () => {
  assert.throws(() => parseListing('<html><body>Bitte bestätige das Captcha</body></html>'),
    (err) => err instanceof ParseError && err.code === 'blocked');
});

test('parseSearch reads result cards', () => {
  const results = parseSearch(fixture('search.html'));
  assert.equal(results.length, 11);
  assert.deepEqual(results[0], {
    adId: '2900000001', title: 'ASUS TUF RTX 3080 10GB', price: 400, priceType: 'vb',
    url: 'https://www.kleinanzeigen.de/s-anzeige/rtx-3080-asus-tuf/2900000001-225-100',
    shipping: 'Versand möglich', location: '10115 Berlin',
  });
  assert.equal(results[2].price, 430, 'takes the current price, not the struck-through one');
  assert.equal(results[7].price, null);
  assert.equal(results[10].price, 1050);
});

test('priceStats trims outliers before taking the median', () => {
  const s = priceStats([1, 400, 430, 450, 470, 1050]);
  assert.equal(s.count, 4);
  assert.equal(s.excluded, 2);
  assert.equal(s.median, 440);
  assert.equal(priceStats([]), null);
});
