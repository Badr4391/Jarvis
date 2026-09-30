/* Service Worker: haelt die Huelle offline bereit und zeigt die letzten
   bekannten Daten, wenn der Rechner zu Hause gerade nicht erreichbar ist. */

const SHELL = "jarvis-shell-v1";
const DATA = "jarvis-data-v1";
const SHELL_FILES = [
  "/", "/app.css", "/app.js", "/icon.svg",
  "/icon-192.png", "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL)
      .then((cache) => cache.addAll(SHELL_FILES))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== SHELL && k !== DATA).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname === "/api/stream") return;          // SSE nie abfangen

  // Daten: erst Netz, bei Ausfall der letzte bekannte Stand.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(DATA).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request).then((hit) => hit || new Response(
          JSON.stringify({ error: "offline", offline: true }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        )))
    );
    return;
  }

  // Huelle: erst Cache, dann Netz.
  event.respondWith(
    caches.match(request).then((hit) => hit || fetch(request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(SHELL).then((cache) => cache.put(request, copy));
      }
      return response;
    }))
  );
});

/* Meldungen, die der Server ueber die offene Seite schickt. */
self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "notify" && self.registration.showNotification) {
    self.registration.showNotification(data.title || "Jarvis", {
      body: data.body || "",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      tag: data.tag || "jarvis",
      renotify: true,
    });
  }
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow("/"));
});
