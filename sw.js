// Service worker minimal de Nostradamus : il rend l'appli « installable » (plein écran) sans rien mettre en cache.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});   // présent pour que Chrome propose « Installer l'application »
