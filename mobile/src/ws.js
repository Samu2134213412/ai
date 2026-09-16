/* WebSocket client with automatic reconnection and lossless catch-up.
 *
 * Two things matter here:
 *   1. The task keeps running on the PC whether or not this socket is open, so
 *      dropping the connection is never destructive.
 *   2. Every event has a monotonic `seq`, so on reconnect we ask the server to
 *      replay from the last seq we saw. Nothing that happened while the phone
 *      was asleep, backgrounded or on a different network is lost. */

import NetInfo from '@react-native-community/netinfo';

import { credentials, baseUrl, forgetBase } from './api';

const BACKOFF_MS = [500, 1000, 2000, 4000, 8000, 15000];
const HEARTBEAT_MS = 25000;

export class SessionStream {
  /**
   * @param {string|null} sessionId  session to follow, or null for all sessions
   * @param {object} handlers  { onEvent, onStatus, onReplayComplete }
   */
  constructor(sessionId, handlers = {}) {
    this.sessionId = sessionId;
    this.handlers = handlers;
    this.lastSeq = 0;
    this.socket = null;
    this.attempt = 0;
    this.closed = false;
    this.heartbeat = null;
    this.reconnectTimer = null;
    this.netUnsubscribe = null;
    this.state = 'connecting';
  }

  setStatus(state, detail) {
    this.state = state;
    this.handlers.onStatus?.(state, detail);
  }

  async start(fromSeq = 0) {
    this.lastSeq = fromSeq;
    this.closed = false;
    // A Wi-Fi <-> mobile-data switch invalidates the socket silently on Android,
    // so react to the transition rather than waiting for a timeout.
    this.netUnsubscribe = NetInfo.addEventListener((netState) => {
      if (netState.isConnected && this.state !== 'open') {
        forgetBase();
        this.attempt = 0;
        this.connect();
      } else if (!netState.isConnected) {
        this.setStatus('offline', 'This phone has no network connection.');
      }
    });
    this.connect();
  }

  async connect() {
    if (this.closed) return;
    clearTimeout(this.reconnectTimer);
    this.setStatus(this.lastSeq ? 'reconnecting' : 'connecting');

    let url;
    try {
      const token = await credentials.load();
      if (!token) { this.setStatus('unpaired'); return; }
      const base = await baseUrl();
      const wsBase = base.replace(/^http/, 'ws');
      const params = new URLSearchParams({ token, after: String(this.lastSeq) });
      if (this.sessionId) params.set('session', this.sessionId);
      url = `${wsBase}/ws?${params.toString()}`;
    } catch (err) {
      this.setStatus('unreachable', err.message);
      this.scheduleReconnect();
      return;
    }

    let socket;
    try {
      socket = new WebSocket(url);
    } catch (err) {
      this.setStatus('unreachable', String(err));
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      this.attempt = 0;
      this.setStatus('open');
      clearInterval(this.heartbeat);
      this.heartbeat = setInterval(() => this.send({ action: 'ping' }), HEARTBEAT_MS);
    };

    socket.onmessage = (raw) => {
      let message;
      try { message = JSON.parse(raw.data); } catch { return; }
      switch (message.type) {
        case 'connected':
          this.setStatus('open');
          break;
        case 'event':
          this.lastSeq = Math.max(this.lastSeq, message.seq);
          this.handlers.onEvent?.(message);
          break;
        case 'replay_complete':
          this.lastSeq = Math.max(this.lastSeq, message.last_seq || 0);
          this.handlers.onReplayComplete?.(this.lastSeq);
          break;
        case 'error':
          if (message.code === 'unauthorized') {
            this.closed = true;
            this.setStatus('unpaired', message.message);
          } else {
            this.handlers.onStatus?.(this.state, message.message);
          }
          break;
        default:
          break;  // pong and anything we do not know about yet
      }
    };

    socket.onerror = () => { /* onclose always follows; handle it there */ };

    socket.onclose = () => {
      clearInterval(this.heartbeat);
      if (this.closed) return;
      forgetBase();
      this.setStatus('reconnecting');
      this.scheduleReconnect();
    };
  }

  scheduleReconnect() {
    if (this.closed) return;
    const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)];
    this.attempt += 1;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  send(payload) {
    if (this.socket && this.socket.readyState === 1) {
      this.socket.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }

  stop() {
    this.closed = true;
    clearTimeout(this.reconnectTimer);
    clearInterval(this.heartbeat);
    this.netUnsubscribe?.();
    try { this.socket?.close(); } catch { /* already gone */ }
    this.socket = null;
  }
}
