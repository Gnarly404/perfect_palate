/* Perfect Palate service worker. Served from /sw.js so its scope is the whole site.
 * __VERSION__ and __PRECACHE__ are filled in by the server so a deploy replaces old caches.
 *
 *  - app shell (our JS/CSS/icons, offline page): cached at install
 *  - /recipes/ pages (all recipes live inside that HTML): network first, 4 s patience, then the saved copy
 *  - recipe photos: cache first, newest 150 kept
 *  - fonts / icon font from their CDNs: cache first
 *  - everything else (sign in, reviews, profile, forms): straight to the network, never cached
 */
const VERSION = '__VERSION__';
const PRECACHE = __PRECACHE__;
const SHELL = 'pp-shell-' + VERSION;
const PAGES = 'pp-pages-' + VERSION;
const IMAGES = 'pp-images-v1';
const EXTERNAL = 'pp-external-v1';
const MAX_IMAGES = 150;
const PATIENCE_MS = 4000;
const EXTERNAL_HOSTS = ['cdnjs.cloudflare.com', 'fonts.googleapis.com', 'fonts.gstatic.com'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL).then(c => Promise.all(
    PRECACHE.map(u => c.add(new Request(u, { cache: 'reload' })).catch(() => {}))
  )));
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL, PAGES, IMAGES, EXTERNAL]);
    for (const k of await caches.keys()) if (k.startsWith('pp-') && !keep.has(k)) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener('message', event => {
  const d = event.data || {};
  if (d.type === 'skip-waiting') self.skipWaiting();
  else if (d.type === 'clear-user') event.waitUntil(caches.delete(PAGES));
  else if (d.type === 'prefetch' && Array.isArray(d.urls)) {
    event.waitUntil((async () => {
      const cache = await caches.open(PAGES);
      let fresh = false;
      for (const u of d.urls) {
        if (!/^\/recipes\//.test(u)) continue;
        try {
          const had = await cache.match(u);
          const res = await fetch(u, { credentials: 'same-origin' });
          if (res.ok && !res.redirected) { await cache.put(u, res.clone()); if (!had) fresh = true; }
        } catch (e) { /* offline: try next time */ }
      }
      const all = await self.clients.matchAll();
      all.forEach(c => c.postMessage({ type: 'prefetched', version: VERSION, fresh }));
    })());
  }
});

const isCacheablePage = url => /^\/recipes\/(?:$|tips\/?$)/.test(url.pathname);
const isPermalink = url => /^\/recipes\/recipe\/\d+\/?$/.test(url.pathname);

async function trim(cacheName, max) {
  const cache = await caches.open(cacheName), keys = await cache.keys();
  for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
}

async function offlineFallback(url) {
  const pages = await caches.open(PAGES);
  // a recipe link that was never opened online still opens: the recipe book page carries every recipe
  if (/^\/recipes\/recipe\/\d+/.test(url.pathname)) { const book = await pages.match('/recipes/'); if (book) return book; }
  const shell = await caches.open(SHELL);
  return (await shell.match('/offline')) || new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
}

async function pageRequest(request, url) {
  const pages = await caches.open(PAGES);
  const key = url.origin + url.pathname;
  // a recipe permalink is the same recipe book with one recipe opened, so the saved book stands in for it
  const cached = await pages.match(isPermalink(url) ? url.origin + '/recipes/' : key);
  const network = fetch(request).then(res => {
    if (res.ok && !res.redirected && isCacheablePage(url)) pages.put(key, res.clone());
    return res;
  });
  if (!cached) return network.catch(() => offlineFallback(url));
  return Promise.race([network, new Promise(r => setTimeout(() => r(cached), PATIENCE_MS))]).catch(() => cached);
}

async function cacheFirst(request, cacheName, max) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok || res.type === 'opaque') { cache.put(request, res.clone()); if (max) trim(cacheName, max); }
  return res;
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) {
    if (EXTERNAL_HOSTS.includes(url.hostname)) event.respondWith(cacheFirst(request, EXTERNAL).catch(() => Response.error()));
    return;
  }
  if (url.pathname === '/sw.js') return;
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.open(SHELL).then(async c => (await c.match(request)) || cacheFirst(request, SHELL)));
    return;
  }
  if (url.pathname.startsWith('/recipes/image/')) { event.respondWith(cacheFirst(request, IMAGES, MAX_IMAGES).catch(() => Response.error())); return; }
  if (request.mode === 'navigate') {
    if (isCacheablePage(url) || isPermalink(url)) event.respondWith(pageRequest(request, url));
    else event.respondWith(fetch(request).catch(() => offlineFallback(url)));
  }
});
