import { eur } from './format.js';

const DAY = 86_400_000;

const PATTERNS = {
  fakeEscrow: /treuhand|zahlungs-?link|kleinanzeigen[\s-]?(zahlung|link)|dhl[\s-]?(treuhand|zahlung)/i,
  badPayment: /western\s?union|moneygram|paysafe|gutschein|amazon[\s-]?karte|bitcoin|krypto|crypto|freunde\s*(und|&|u\.?)\s*familie|friends\s*(and|&)\s*family|paypal\s*(f\s?&\s?f|ff\b|freunde)/i,
  prepay: /vorkasse|nur\s+(per\s+)?(überweisung|ueberweisung)/i,
  offPlatform: /whats\s?app|telegram|threema|\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b|(?:\+49|0049|\b01[5-7]\d)[\d\s/-]{6,}|(?:per|über|via)\s+(?:e-?)?mail\s+(?:kontakt|melden|schreiben)/i,
  abroad: /im ausland|aus dem ausland|auf montage|geschäftsreise|beruflich (unterwegs|im)|nicht vor ort|spedition/i,
  shipOnly: /nur versand|keine abholung|kein abholen|abholung (ist )?nicht möglich|nur verschickt/i,
  urgency: /muss (schnell|heute|dringend) weg|schnell weg|nur heute/i,
  defect: /defekt|bastler|ohne funktion|ungetestet|nicht getestet|artefakte|kein bild|startet nicht|wasserschaden|beschädigt|kaputt/i,
  mining: /mining|gemined|\bminer\b/i,
  wanted: /^\s*(suche|ich suche|gesucht)\b/i,
  strongBadge: /top zufriedenheit|besonders zufrieden/i,
  badge: /freundlich|zuverlässig/i,
};

// Matches that aren't directly negated: "kein PayPal Freunde", "nicht defekt",
// "bitte kein Kontakt über WhatsApp" don't count.
function mentions(text, re) {
  const g = new RegExp(re.source, re.flags.replace('g', '') + 'g');
  for (const m of text.matchAll(g)) {
    const before = text.slice(Math.max(0, m.index - 30), m.index).toLowerCase();
    if (!/\b(kein\w*|nicht|ohne|nie|niemals)\s+(\S+\s+){0,2}$/.test(before)) return true;
  }
  return false;
}

function severityFor(points) {
  if (points >= 20) return 'high';
  if (points >= 8) return 'mid';
  if (points > 0) return 'low';
  return points < 0 ? 'good' : 'info';
}

function daysSince(isoDate, now) {
  if (!isoDate) return null;
  const t = Date.parse(`${isoDate}T00:00:00`);
  return Number.isFinite(t) ? Math.max(0, Math.floor((now - t) / DAY)) : null;
}

/**
 * Scores how likely a listing is a scam (0–100) and explains why.
 * price/market are the effective values after user overrides.
 * Condition problems (defekt, Mining) are reported as 'warn' without points:
 * they're a reason to look closer, not a sign of fraud.
 */
export function assessRisk({ listing = {}, price = null, market = null, marketSource = null, marketCount = null, now = Date.now() }) {
  const reasons = [];
  const add = (points, text, severity = severityFor(points)) => reasons.push({ points, text, severity });
  const text = `${listing.title ?? ''}\n${listing.description ?? ''}`;
  const hasText = !listing.manual && Boolean(listing.description || listing.title);
  const defect = hasText && (mentions(text, PATTERNS.defect) || /defekt/i.test(listing.details?.Zustand ?? ''));

  if (listing.status === 'deleted') add(0, 'Anzeige ist nicht mehr verfügbar (gelöscht oder verkauft).', 'warn');
  if (listing.status === 'reserved') add(0, 'Anzeige ist als reserviert markiert.', 'warn');
  if (PATTERNS.wanted.test(listing.title ?? '')) add(0, 'Das ist ein Gesuch, kein Angebot.', 'warn');

  // Price against the market
  let ratio = null;
  if (listing.priceType === 'free' && market >= 50) {
    add(30, `„Zu verschenken" bei Ware im Wert von ca. ${eur(market)} – sehr ungewöhnlich.`);
  } else if (price != null && price <= 5 && market >= 50) {
    add(10, `Lockpreis (${eur(price)}) – echter Preis unklar, vorher nachfragen.`);
  } else if (price != null && market > 0) {
    ratio = price / market;
    const below = Math.round((1 - ratio) * 100);
    if (defect && ratio < 0.75) add(0, `Preis ${below} % unter Marktpreis – passt zum angegebenen Defekt/Bastlerzustand.`);
    else if (ratio < 0.4) add(45, `Preis ${below} % unter Marktpreis – extrem günstig, klassisches Scam-Signal.`);
    else if (ratio < 0.6) add(28, `Preis ${below} % unter Marktpreis – auffällig günstig.`);
    else if (ratio < 0.75) add(12, `Preis ${below} % unter Marktpreis – günstig, genau prüfen.`);
    else if (ratio > 1.3) add(0, `Preis ${Math.round((ratio - 1) * 100)} % über Marktpreis – verhandeln oder weitersuchen.`);
    else add(0, 'Preis im üblichen Marktrahmen.', 'good');
    if (marketSource === 'search' && marketCount != null && marketCount < 5) {
      add(0, `Marktpreis basiert auf nur ${marketCount} Vergleichsangebot${marketCount === 1 ? '' : 'en'} – mit Vorsicht genießen.`);
    }
  } else if (price != null) {
    add(0, 'Kein Marktpreis verfügbar – Preis nicht prüfbar. Trag ihn bei Bedarf manuell ein.');
  }

  // Seller
  const seller = listing.seller ?? {};
  const accountDays = daysSince(seller.activeSince, now);
  if (accountDays != null) {
    if (accountDays < 30) add(25, `Verkäuferkonto erst ${accountDays} Tag${accountDays === 1 ? '' : 'e'} alt.`);
    else if (accountDays < 180) add(12, `Verkäuferkonto erst ${Math.max(1, Math.round(accountDays / 30))} Monate alt.`);
    else if (accountDays >= 3 * 365) add(-8, `Verkäuferkonto seit ${Math.floor(accountDays / 365)} Jahren aktiv.`);
    else add(0, `Verkäuferkonto seit ${Math.floor(accountDays / 30)} Monaten aktiv.`);
  } else if (!listing.manual) {
    add(0, 'Kontoalter des Verkäufers unbekannt.');
  }
  const badges = (seller.badges ?? []).join(' ');
  if (PATTERNS.strongBadge.test(badges)) add(-10, `Gute Bewertungen: ${seller.badges.join(', ')}.`);
  else if (PATTERNS.badge.test(badges)) add(-5, `Bewertungen: ${seller.badges.join(', ')}.`);
  if (seller.type === 'commercial') add(0, 'Gewerblicher Anbieter – Gewährleistung und Widerrufsrecht gelten.');

  // Listing content
  if (!listing.manual) {
    if (listing.images === 0) add(15, 'Keine Fotos.');
    else if (listing.images === 1) add(6, 'Nur ein Foto.');
    const descLen = (listing.description ?? '').trim().length;
    if (descLen < 30) add(10, 'Kaum Beschreibung.');
    else if (descLen < 80) add(4, 'Sehr kurze Beschreibung.');
  }

  if (hasText) {
    if (mentions(text, PATTERNS.fakeEscrow)) add(25, 'Erwähnt Treuhand/Zahlungslink – bekannte Betrugsmasche, Kleinanzeigen verschickt keine Zahlungslinks.');
    if (mentions(text, PATTERNS.badPayment)) add(25, 'Unsichere Zahlungsart (PayPal Freunde, Gutschein, Western Union …) – kein Käuferschutz.');
    else if (mentions(text, PATTERNS.prepay)) add(10, 'Nur Vorkasse/Überweisung – kein Käuferschutz.');
    if (mentions(text, PATTERNS.offPlatform)) add(15, 'Will Kontakt außerhalb von Kleinanzeigen (WhatsApp/E-Mail/Telefon).');
    const abroad = mentions(text, PATTERNS.abroad);
    if (abroad) add(15, 'Verkäufer angeblich im Ausland/unterwegs – typisches Scam-Muster.');
    const shipOnly = PATTERNS.shipOnly.test(text);
    if (shipOnly) add(6, 'Nur Versand, keine Abholung.');
    if (mentions(text, PATTERNS.urgency)) add(4, 'Zeitdruck („muss schnell weg").');
    if (!defect && ratio != null && ratio < 0.6 && (shipOnly || abroad)) {
      add(10, 'Sehr günstig + nur Versand: klassische Kombination bei Fake-Anzeigen.');
    }
    const postedDays = daysSince(listing.postedAt, now);
    if (!defect && ratio != null && ratio < 0.6 && postedDays != null && postedDays <= 1) {
      add(5, 'Gerade erst eingestellt und sehr günstig.');
    }
    if (defect) add(0, 'Hinweis auf Defekt, Bastlerware oder ungetestet – Zustandsrisiko.', 'warn');
    if (mentions(text, PATTERNS.mining)) add(0, 'Mining-Hinweis – stärkerer Verschleiß möglich.', 'warn');
  }

  if (listing.shipping?.pickupOnly) add(-5, 'Nur Abholung – Ware vor Ort prüfen und bar zahlen senkt das Risiko.');
  if (listing.buyNow) add(0, '„Direkt kaufen"/„Sicher bezahlen" verfügbar – nutze das für Käuferschutz.', 'good');

  const score = Math.max(0, Math.min(100, reasons.reduce((sum, r) => sum + r.points, 0)));
  const level = score >= 50 ? 'high' : score >= 25 ? 'mid' : 'low';
  const order = { high: 0, warn: 1, mid: 2, low: 3, info: 4, good: 5 };
  reasons.sort((a, b) => order[a.severity] - order[b.severity] || b.points - a.points);
  return { score, level, ratio, reasons };
}

export const LEVEL_LABEL = { low: 'Niedrig', mid: 'Mittel', high: 'Hoch' };
