const CACHE_PREFIX = "famiverse-shell-";
const CACHE_NAME = `${CACHE_PREFIX}v1`;
const SHELL_URLS = [
  "/offline/",
  "/static/css/app.css",
  "/static/pwa/icon-192.png",
  "/static/pwa/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const requestUrl = new URL(request.url);

  if (request.method !== "GET" || requestUrl.origin !== self.location.origin) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (requestUrl.pathname === "/offline/" && response.ok) {
            event.waitUntil(
              caches.open(CACHE_NAME)
                .then((cache) => cache.put("/offline/", response.clone()))
            );
          }
          return response;
        })
        .catch(() => caches.match("/offline/"))
    );
    return;
  }

  if (requestUrl.pathname.startsWith("/static/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            event.waitUntil(
              caches.open(CACHE_NAME)
                .then((cache) => cache.put(request, response.clone()))
            );
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
  }
});
