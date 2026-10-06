/* Beobachtet, ob ein Programm läuft (z. B. GoodNotes): erkennt „geöffnet“ sofort, „geschlossen“ erst nach
   mehreren Fehlsichtungen (Fenstertitel können kurz verschwinden). Nur Lesen von Fenster-/Prozessnamen. */
const GOODNOTES = /goodnotes/i;

function createWatcher({ pattern = GOODNOTES, getNames, onOpen, onClose, misses = 2 }) {
  let open = false, missed = 0;
  return {
    get open() { return open; },
    /* Ein Beobachtungsschritt (von außen im Takt aufgerufen). Liefert, ob das Programm gerade als offen gilt. */
    async tick() {
      let names = [];
      try { names = await getNames(); } catch (e) { return open; }       // Quelle ausgefallen → Zustand beibehalten
      const seen = names.some((n) => pattern.test(String(n)));
      if (seen) {
        missed = 0;
        if (!open) { open = true; await onOpen(); }
      } else if (open && ++missed >= misses) {
        open = false; missed = 0; await onClose();
      }
      return open;
    },
  };
}

/* Automatik: Solange das Programm offen ist, läuft ein Fokus (und die Leiste ist sichtbar). Greift nie in
   Sitzungen ein, die der Lernende selbst gestartet hat, und respektiert ein manuelles Beenden. */
function createAuto({ getConfig, focus, overlay, notify, now = () => Date.now() / 1000 }) {
  let focusOn = false, startedAt = 0, overlayShown = false, extendAt = 0;
  return {
    get focusOn() { return focusOn; },
    async onOpen() {
      const c = getConfig();
      if (c.autoOverlay && overlay.show()) overlayShown = true;
      if (c.autoFocus) {
        const f = await focus.info();
        if (!f.active) {                                    // eigene Sitzung des Lernenden bleibt unangetastet
          await focus.start(c.autoMinutes);
          focusOn = true; startedAt = now(); extendAt = now() + (c.autoMinutes - 10) * 60;
          notify("GoodNotes ist offen – Fokus läuft 🎯", "Ablenkungen werden ferngehalten, bis du GoodNotes schließt.");
        }
      }
    },
    async onClose() {
      if (focusOn) { await focus.stop(); focusOn = false; notify("GoodNotes geschlossen", "Fokus beendet. Gut gelernt! 🎉"); }
      if (overlayShown) { overlay.hide(); overlayShown = false; }
    },
    /* Während GoodNotes offen ist: Sitzung verlängern; hat der Lernende sie beendet, nicht wieder starten. */
    async keepAlive() {
      if (!focusOn) return;
      const f = await focus.info();
      if (!f.active && now() - startedAt > 15) { focusOn = false; return; }      // vom Lernenden beendet → Ruhe
      if (now() >= extendAt) { const c = getConfig(); await focus.start(c.autoMinutes); extendAt = now() + (c.autoMinutes - 10) * 60; }
    },
  };
}
module.exports = { createWatcher, createAuto, GOODNOTES };
