/* Fokus-Sitzung, wie sie die Browser-Erweiterung abfragt (GET /api/focus).
   Die Oberfläche ist die Quelle der Wahrheit und meldet ihren Stand per IPC;
   Befehle der Erweiterung/des Trays gehen als „Kommandos“ zurück an die Oberfläche. */
const DEFAULT_BLOCKLIST = ["youtube.com", "youtu.be", "instagram.com", "tiktok.com", "netflix.com",
  "twitch.tv", "x.com", "twitter.com", "facebook.com", "reddit.com", "snapchat.com"];

class FocusState {
  constructor(clock = () => Date.now() / 1000) {
    this.clock = clock;
    this.endsAt = 0; this.minutes = 0; this.blocklist = [...DEFAULT_BLOCKLIST];
  }
  info() {
    const remaining = Math.max(0, Math.floor(this.endsAt - this.clock()));
    return { active: remaining > 0, remaining, ends_at: this.endsAt, minutes: this.minutes,
             blocklist: [...this.blocklist] };
  }
  start(minutes) {
    const m = Math.max(1, Math.min(240, parseInt(minutes, 10) || 25));
    this.endsAt = this.clock() + m * 60; this.minutes = m;
  }
  stop() { this.endsAt = 0; this.minutes = 0; }
  /* Stand der Oberfläche übernehmen (validiert, da von außen kommend). */
  update(s) {
    if (!s || typeof s !== "object") return;
    if (Number.isFinite(s.ends_at)) this.endsAt = Math.max(0, s.ends_at);
    if (Number.isFinite(s.minutes)) this.minutes = Math.max(0, Math.min(240, s.minutes));
    if (Array.isArray(s.blocklist)) {
      this.blocklist = s.blocklist.filter((d) => typeof d === "string" && /^[a-z0-9.-]+\.[a-z]{2,}$/.test(d)).slice(0, 200);
    }
  }
}
module.exports = { FocusState, DEFAULT_BLOCKLIST };
