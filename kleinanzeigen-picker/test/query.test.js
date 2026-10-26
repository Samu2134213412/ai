import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildQuery, extractModel, matchesComparable } from '../public/js/query.js';
import { classify } from '../public/js/categories.js';
import { buildSearchUrl, extractListingUrl } from '../public/js/urls.js';
import { parseNumberInput } from '../public/js/format.js';

test('extractModel canonicalises GPU and CPU names', () => {
  const key = (t) => extractModel(t)?.key ?? null;
  assert.equal(key('MSI GeForce RTX 3080 Gaming X Trio'), 'rtx 3080');
  assert.equal(key('RTX3080Ti Founders'), 'rtx 3080 ti');
  assert.equal(key('Asus RTX 4070 Ti Super OC'), 'rtx 4070 ti super');
  assert.equal(key('Geforce 1080 Ti'), 'gtx 1080 ti');
  assert.equal(key('Sapphire Radeon RX 7900 XTX Nitro+'), 'rx 7900 xtx');
  assert.equal(key('Intel Arc A770 16GB'), 'arc a770');
  assert.equal(key('AMD Ryzen 7 5800X3D'), 'ryzen 5800x3d');
  assert.equal(key('Ryzen 5 5600'), 'ryzen 5600');
  assert.equal(key('Intel Core i7-13700K'), 'i7 13700k');
  assert.equal(key('Core Ultra 7 265K'), 'ultra 7 265k');
  assert.equal(key('Ryzen 7 7840HS Laptop'), null);
  assert.equal(key('Corsair Vengeance 32GB DDR5'), null);
});

test('buildQuery falls back to the meaningful title words', () => {
  assert.equal(buildQuery('Verkaufe Samsung 990 Pro 2TB NVMe SSD wie neu'), 'samsung 990 pro 2tb nvme');
  assert.equal(buildQuery('MSI GeForce RTX 3080 Gaming X Trio 10GB'), 'rtx 3080');
});

test('matchesComparable keeps the same product only', () => {
  assert.ok(matchesComparable('Gigabyte RTX3080 Eagle', 'rtx 3080'));
  assert.ok(!matchesComparable('RTX 3080 Ti Founders Edition', 'rtx 3080'));
  assert.ok(!matchesComparable('Suche RTX 3080', 'rtx 3080'));
  assert.ok(!matchesComparable('RTX 3080 defekt', 'rtx 3080'));
  assert.ok(matchesComparable('RTX 3080 defekt', 'rtx 3080', { allowDefect: true }));
  assert.ok(!matchesComparable('Gaming PC mit RTX 3080', 'rtx 3080'));
  assert.ok(matchesComparable('Samsung 990 Pro 2 TB', 'samsung 990 pro 2tb'));
  assert.ok(!matchesComparable('Samsung 980 Pro 1TB', 'samsung 990 pro 2tb'));
});

test('classify sorts listings into components', () => {
  assert.equal(classify('MSI RTX 3080', 'Grafikkarten'), 'gpu');
  assert.equal(classify('Noctua NH-D15 CPU Kühler', 'Prozessoren / CPUs'), 'cooler');
  assert.equal(classify('AMD Ryzen 7 5800X'), 'cpu');
  assert.equal(classify('MSI MAG B650 Tomahawk WiFi'), 'mainboard');
  assert.equal(classify('Corsair Vengeance 32GB DDR5 6000'), 'ram');
  assert.equal(classify('Kingston A400 SSD 480GB'), 'storage');
  assert.equal(classify('be quiet! Pure Power 12 M 750W'), 'psu');
  assert.equal(classify('Fractal Design North Gehäuse'), 'case');
  assert.equal(classify('LG 27GP850 27 Zoll 165Hz'), 'monitor');
  assert.equal(classify('Windows 11 Pro Lizenz'), 'os');
  assert.equal(classify('Logitech G Pro Maus'), 'other');
});

test('extractListingUrl only accepts Kleinanzeigen ad links', () => {
  const canonical = 'https://www.kleinanzeigen.de/s-anzeige/rtx-3080/2912345678-225-3331';
  assert.equal(extractListingUrl('https://www.kleinanzeigen.de/s-anzeige/rtx-3080/2912345678-225-3331?utm_source=x'), canonical);
  assert.equal(extractListingUrl('Schau mal: kleinanzeigen.de/s-anzeige/rtx-3080/2912345678-225-3331 !'), canonical);
  assert.equal(extractListingUrl('https://www.ebay-kleinanzeigen.de/s-anzeige/rtx-3080/2912345678-225-3331/'), canonical);
  assert.equal(extractListingUrl('https://www.kleinanzeigen.de/s-grafikkarten/k0'), null);
  assert.equal(extractListingUrl('https://evil.example/s-anzeige/x/1'), null);
  assert.equal(extractListingUrl(''), null);
});

test('buildSearchUrl uses the PC category when known', () => {
  assert.equal(buildSearchUrl('rtx 3080', '225'), 'https://www.kleinanzeigen.de/s-pc-zubehoer-software/rtx-3080/k0c225');
  assert.equal(buildSearchUrl('Gehäuse weiß', null), 'https://www.kleinanzeigen.de/s-geh%C3%A4use-wei%C3%9F/k0');
});

test('parseNumberInput reads German numbers', () => {
  assert.equal(parseNumberInput('249,90 €'), 249.9);
  assert.equal(parseNumberInput('1.200'), 1200);
  assert.equal(parseNumberInput('1.234,5'), 1234.5);
  assert.equal(parseNumberInput('12.5'), 12.5);
  assert.equal(parseNumberInput(''), null);
  assert.ok(Number.isNaN(parseNumberInput('abc')));
});
