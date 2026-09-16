/* HTTP client with multi-address failover.
 *
 * The phone may sit on the home Wi-Fi (LAN address) or anywhere else (Tailscale
 * address). Rather than making the user choose, we keep every address the QR
 * code carried and probe them, remembering whichever answered last. */

import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

const TOKEN_KEY = 'codepilot.device_token';
const ADDRESSES_KEY = 'codepilot.addresses';
const PREFERRED_KEY = 'codepilot.preferred_address';

const PROBE_TIMEOUT = 3500;
const REQUEST_TIMEOUT = 30000;

export class ApiError extends Error {
  constructor(message, { status = 0, kind = 'error' } = {}) {
    super(message);
    this.status = status;
    this.kind = kind;
  }
}

async function fetchWithTimeout(url, options = {}, timeout = REQUEST_TIMEOUT) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export const credentials = {
  async save(token) {
    try {
      await SecureStore.setItemAsync(TOKEN_KEY, token, {
        keychainAccessible: SecureStore.WHEN_UNLOCKED,
      });
    } catch {
      // SecureStore is unavailable in some Expo Go / web contexts. Falling back
      // keeps the app usable, and the token is still scoped to this app.
      await AsyncStorage.setItem(TOKEN_KEY, token);
    }
  },
  async load() {
    try {
      const value = await SecureStore.getItemAsync(TOKEN_KEY);
      if (value) return value;
    } catch { /* fall through */ }
    return AsyncStorage.getItem(TOKEN_KEY);
  },
  async clear() {
    try { await SecureStore.deleteItemAsync(TOKEN_KEY); } catch { /* ignore */ }
    await AsyncStorage.multiRemove([TOKEN_KEY, ADDRESSES_KEY, PREFERRED_KEY]);
  },
};

export const addresses = {
  async save(list) {
    await AsyncStorage.setItem(ADDRESSES_KEY, JSON.stringify(list));
  },
  async load() {
    const raw = await AsyncStorage.getItem(ADDRESSES_KEY);
    try { return raw ? JSON.parse(raw) : []; } catch { return []; }
  },
  async preferred() { return AsyncStorage.getItem(PREFERRED_KEY); },
  async setPreferred(url) { await AsyncStorage.setItem(PREFERRED_KEY, url); },
};

/** Probe one address. Resolves to the url on success, rejects otherwise. */
export async function probe(url) {
  const res = await fetchWithTimeout(`${url}/api/health`, {}, PROBE_TIMEOUT);
  if (!res.ok) throw new ApiError(`HTTP ${res.status}`, { status: res.status });
  const body = await res.json();
  if (body.service !== 'codepilot-remote') {
    throw new ApiError('that address is not a CodePilot server');
  }
  return url;
}

/** Find a working address: the remembered one first, then everything else. */
export async function resolveAddress() {
  const all = await addresses.load();
  if (!all.length) throw new ApiError('no server addresses stored — pair again', { kind: 'unpaired' });
  const preferred = await addresses.preferred();
  const ordered = preferred ? [preferred, ...all.filter((a) => a !== preferred)] : all;

  const failures = [];
  for (const url of ordered) {
    try {
      await probe(url);
      await addresses.setPreferred(url);
      return url;
    } catch (err) {
      failures.push(`${url}: ${err.message}`);
    }
  }
  throw new ApiError(
    `Your PC is not reachable on any known address.\n\n${failures.join('\n')}\n\n` +
    'On the home Wi-Fi the LAN address should work. Away from home, make sure ' +
    'Tailscale is connected on both the phone and the PC.',
    { kind: 'unreachable' },
  );
}

let cachedBase = null;
export function currentBase() { return cachedBase; }
export function forgetBase() { cachedBase = null; }

export async function baseUrl() {
  if (cachedBase) return cachedBase;
  cachedBase = await resolveAddress();
  return cachedBase;
}

export async function request(path, { method = 'GET', body, retryOnNetworkError = true } = {}) {
  const token = await credentials.load();
  if (!token) throw new ApiError('this phone is not paired', { kind: 'unpaired' });
  const base = await baseUrl();

  let res;
  try {
    res = await fetchWithTimeout(`${base}${path}`, {
      method,
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${token}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    forgetBase();
    if (retryOnNetworkError) {
      // The network may have flipped between Wi-Fi and mobile data; re-resolve once.
      return request(path, { method, body, retryOnNetworkError: false });
    }
    throw new ApiError(
      err.name === 'AbortError'
        ? 'The PC did not answer in time. It may be busy or asleep.'
        : 'Lost the connection to your PC.',
      { kind: 'unreachable' },
    );
  }

  const text = await res.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = { detail: text }; }

  if (res.status === 401) {
    throw new ApiError('This phone is no longer authorised. Pair it again from the PC dashboard.',
      { status: 401, kind: 'unpaired' });
  }
  if (res.status === 403) {
    throw new ApiError((payload && payload.detail) || 'Not allowed from a phone.',
      { status: 403, kind: 'forbidden' });
  }
  if (!res.ok) {
    throw new ApiError((payload && payload.detail) || `Request failed (HTTP ${res.status})`,
      { status: res.status });
  }
  return payload;
}

/* ------------------------------------------------------------------ pairing */
export async function pair(scanned, deviceName) {
  const list = Array.isArray(scanned.addresses) && scanned.addresses.length
    ? scanned.addresses
    : [scanned.address];
  let lastError = null;
  for (const url of list) {
    try {
      await probe(url);
      const res = await fetchWithTimeout(`${url}/api/pair`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token: scanned.token, device_name: deviceName }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new ApiError(body.detail || `Pairing failed (HTTP ${res.status})`,
          { status: res.status });
      }
      await credentials.save(body.device_token);
      await addresses.save(list);
      await addresses.setPreferred(url);
      forgetBase();
      return body;
    } catch (err) {
      lastError = err;
      // A consumed one-time token cannot be retried against another address.
      if (err.status === 401) break;
    }
  }
  throw lastError || new ApiError('Pairing failed');
}

/* ------------------------------------------------------------- API surface */
export const api = {
  status: () => request('/api/status'),
  models: () => request('/api/models'),
  projects: () => request('/api/projects'),
  projectGit: (id) => request(`/api/projects/${id}/git`),
  projectChanges: (id) => request(`/api/projects/${id}/changes`),
  fileDiff: (id, path, base) =>
    request(`/api/projects/${id}/diff?path=${encodeURIComponent(path)}` +
            (base ? `&base=${encodeURIComponent(base)}` : '')),
  sessions: (projectId) =>
    request(`/api/sessions${projectId ? `?project_id=${projectId}` : ''}`),
  session: (id) => request(`/api/sessions/${id}`),
  sessionEvents: (id, after = 0) => request(`/api/sessions/${id}/events?after=${after}`),
  sessionChanges: (id) => request(`/api/sessions/${id}/changes`),
  createSession: (payload) => request('/api/sessions', { method: 'POST', body: payload }),
  stopSession: (id) => request(`/api/sessions/${id}/stop`, { method: 'POST' }),
  sendMessage: (id, text) => request(`/api/sessions/${id}/message`, { method: 'POST', body: { text } }),
  continueSession: (id, text) =>
    request(`/api/sessions/${id}/continue`, { method: 'POST', body: { text } }),
  approvals: (sessionId) =>
    request(`/api/approvals${sessionId ? `?session_id=${sessionId}` : ''}`),
  decideApproval: (id, approve, reason) =>
    request(`/api/approvals/${id}/decide`, { method: 'POST', body: { approve, reason } }),
};
