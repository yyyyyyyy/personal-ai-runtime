// Personal AI Runtime – Service Worker
// Cache-first for static assets, network-first for API calls.
//
// Cache versioning: bump CACHE_VERSION on each deployment to invalidate old caches.
// Old-version caches are automatically purged during the activate event.

const CACHE_VERSION = "paios-v1";
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const RUNTIME_CACHE = `runtime-${CACHE_VERSION}`;

// Cap the static cache to avoid unbounded growth from old hashed assets
const MAX_STATIC_CACHE_ENTRIES = 80;

// Core shell to pre-cache on install
const PRECACHE_URLS = ["/", "/manifest.json"];

// ── Install ──────────────────────────────────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting(); // activate immediately
});

// ── Activate – clean old caches ──────────────────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== RUNTIME_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim(); // take control of open pages
});

// ── Fetch ────────────────────────────────────────────────────────────────────
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== "GET") return;

  // API / WebSocket → network-first (never cache API responses)
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws")) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Static assets (JS/CSS/images/fonts) → cache-first
  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML pages / fallback → network-first with cache fallback
  event.respondWith(networkFirst(request));
});

// ── Strategies ───────────────────────────────────────────────────────────────

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
      // Enforce cache size limit to prevent unbounded growth
      evictStaticCache(cache);
    }
    return response;
  } catch {
    return offlineFallback(request);
  }
}

async function evictStaticCache(cache) {
  const keys = await cache.keys();
  if (keys.length <= MAX_STATIC_CACHE_ENTRIES) return;
  // Remove oldest entries (first in list) until under limit
  const toRemove = keys.slice(0, keys.length - MAX_STATIC_CACHE_ENTRIES);
  await Promise.all(toRemove.map((req) => cache.delete(req)));
}

async function networkFirst(request) {
  try {
    const networkRes = await fetch(request);
    if (networkRes.ok) {
      const cache = await caches.open(RUNTIME_CACHE);
      cache.put(request, networkRes.clone());
    }
    return networkRes;
  } catch {
    const cached = await caches.match(request);
    return cached || offlineFallback(request);
  }
}

function offlineFallback(request) {
  // For navigation requests, return the cached root page
  if (request.mode === "navigate") {
    return caches.match("/") || new Response("Offline", { status: 503 });
  }
  return new Response("", { status: 404 });
}

function isStaticAsset(pathname) {
  return /\.(js|css|png|jpg|jpeg|svg|ico|woff2?|ttf|eot)(\?.*)?$/.test(pathname);
}
