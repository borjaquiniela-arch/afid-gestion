self.addEventListener("install", (event) => {
  event.waitUntil(caches.open("afid-v1").then((cache) => cache.addAll([
    "/",
    "/static/style.css?v=6",
    "/static/app.js?v=6",
    "/static/logo-sidebar.png?v=3",
    "/static/icon-192.png"
  ]).catch(() => undefined)));
  self.skipWaiting();
});
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/")) return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
