import { ALLOWED_HOSTS } from '../public/js/urls.js';

export class FetchError extends Error {
  constructor(message, code, status = null) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
  Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'de-DE,de;q=0.9,en;q=0.6',
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// One client per server: requests run one at a time with a gap in between,
// so pasting ten links doesn't look like a bot hammering the site.
export function createKleinanzeigenClient({ fetchImpl = globalThis.fetch, gapMs = 900, ttlMs = 10 * 60_000, maxEntries = 300 } = {}) {
  const cache = new Map();
  let queue = Promise.resolve();
  let last = 0;

  function schedule(task) {
    const run = queue.then(async () => {
      const wait = last + gapMs - Date.now();
      if (wait > 0) await sleep(wait);
      try {
        return await task();
      } finally {
        last = Date.now();
      }
    });
    queue = run.catch(() => {});
    return run;
  }

  async function fetchFollow(url) {
    let current = url;
    for (let hop = 0; hop < 5; hop++) {
      let res;
      try {
        res = await fetchImpl(current, { headers: HEADERS, redirect: 'manual', signal: AbortSignal.timeout(15_000) });
      } catch (err) {
        const why = err?.name === 'TimeoutError' ? 'Zeitüberschreitung' : (err?.cause?.code ?? err?.message ?? 'Netzwerkfehler');
        throw new FetchError(`Kleinanzeigen nicht erreichbar (${why}).`, 'network');
      }
      const location = res.headers.get('location');
      if (res.status >= 300 && res.status < 400 && location) {
        const next = new URL(location, current);
        if (next.protocol !== 'https:' || !ALLOWED_HOSTS.has(next.hostname.toLowerCase())) {
          throw new FetchError('Kleinanzeigen leitet auf eine fremde Seite weiter.', 'redirect');
        }
        current = next.href;
        continue;
      }
      if (res.status === 404 || res.status === 410) return { status: res.status, url: current, html: '' };
      if (res.status === 403 || res.status === 429) {
        throw new FetchError('Kleinanzeigen blockiert gerade automatische Abrufe (Bot-Schutz). Kurz warten und erneut versuchen oder Werte manuell eintragen.', 'blocked', res.status);
      }
      if (!res.ok) throw new FetchError(`Kleinanzeigen antwortet mit HTTP ${res.status}.`, 'http', res.status);
      return { status: res.status, url: current, html: await res.text() };
    }
    throw new FetchError('Zu viele Weiterleitungen.', 'redirect');
  }

  return {
    async get(url) {
      const hit = cache.get(url);
      if (hit && Date.now() - hit.time < ttlMs) return hit.value;
      const value = await schedule(() => fetchFollow(url));
      cache.set(url, { time: Date.now(), value });
      if (cache.size > maxEntries) cache.delete(cache.keys().next().value);
      return value;
    },
  };
}
