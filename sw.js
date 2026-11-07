// Ruta fresca: guarda la web y sus datos para abrirla rápido y sin conexión.
// Páginas: primero la red (para recibir cambios) y, sin conexión, la copia guardada.
// Datos, iconos y Leaflet: primero la copia guardada. Cada versión de la web cambia VERSION y borra las copias antiguas.
const VERSION = "rf-8048d7070702";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin && url.hostname !== "cdn.jsdelivr.net") return;
  const page = req.mode === "navigate" || url.pathname.endsWith(".html") || url.pathname.endsWith("/");
  e.respondWith(caches.open(VERSION).then(async cache => {
    if (page) {
      try { const r = await fetch(req); if (r.ok) cache.put(req, r.clone()); return r; }
      catch (err) { const hit = await cache.match(req, {ignoreSearch: true}); if (hit) return hit; throw err; }
    }
    const hit = await cache.match(req);
    if (hit) return hit;
    const r = await fetch(req);
    if (r.ok) cache.put(req, r.clone());
    return r;
  }));
});
