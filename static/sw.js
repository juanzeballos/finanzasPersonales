// Service worker mínimo: alcanza para que la app sea "instalable" (PWA).
// El cache offline lo dejamos para más adelante (etapa 2).

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {
  // Pasa las requests a la red tal cual (sin cache por ahora).
});
