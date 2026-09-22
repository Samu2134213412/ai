// Jarvis Core — App-Shell-Cache für die Installation auf dem Startbildschirm.
//
// Absichtlich sehr klein und vorsichtig: gecacht wird ausschließlich die
// statische Hülle (HTML/Manifest/Icons). Alles andere — insbesondere jeder
// /api/*-Aufruf und die WebSocket-Verbindung zum Jarvis-Server — läuft
// unangetastet direkt durchs Netzwerk. Ein Cache darf niemals eine echte
// Werkzeug- oder Statusabfrage durch alte Daten ersetzen; das würde die
// Grundregel des Projekts (kein Erfolg ohne echtes Tool-Result) auf der
// Oberfläche unterlaufen.
// v2: die alte Prüfung erkannte "trifft das die App-Huelle?" ueber
// pathname.endsWith(shellEintrag.replace("./","")) -- fuer den Eintrag
// "./" wird daraus ein LEERER String, und jeder Pfad endet auf "".
// isShellPath war dadurch fuer JEDEN Pfad wahr, also auch fuer /api/*:
// jede Werkzeug-/Statusabfrage wurde gecacht und beim naechsten Aufruf mit
// derselben URL (z. B. nach einem Favorit-Umschalten in der Kommando-
// Palette) als veralteter Stand zurueckgegeben -- genau das, was der
// Kommentar unten als "darf niemals passieren" beschreibt. Die
// Cache-Version steigt mit, damit ein schon installierter Service Worker
// seinen alten, moeglicherweise verunreinigten Cache verwirft statt ihn
// weiterzuverwenden.
const CACHE = "jarvis-shell-v2";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-512-maskable.png",
  "./icons/apple-touch-icon.png",
  "./icons/favicon-32.png",
];
// Exakte Pfade statt eines Suffix-Vergleichs -- siehe Begruendung oben.
const SHELL_PATHS = new Set(
  SHELL.filter((s) => s !== "./").map((s) => s.replace(/^\./, ""))
);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // Nur die Hülle bedienen — niemals /api/*, niemals sonst etwas Dynamisches.
  // Exakter Pfadvergleich, kein Suffix-Test (siehe Begründung bei SHELL_PATHS).
  const isShellPath = url.pathname === "/" || SHELL_PATHS.has(url.pathname);
  if (!isShellPath) return;

  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
          }
          return res;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
