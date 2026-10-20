// Build ID is stamped into this file by the `sw-build-id` plugin in vite.config.ts (dist/sw.js only).
// A new build => new cache name => the old caches are deleted on activate.
const BUILD_ID = '__BUILD_ID__';
const CACHE_NAME = `lockin-weave-${BUILD_ID}`;
const SHELL_URL = '/index.html';
const PRECACHE = ['/manifest.json', '/favicon.svg']; // NOT the shell: the shell is always fetched fresh when online

const isHtml = (res) => (res.headers.get('content-type') || '').includes('text/html');

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE))
      .catch(() => {}) // a missing icon must never block the update
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

// Page loads: network first, so a deploy shows up on the very next open. Cache is only the offline fallback.
async function shell(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const res = await fetch(request);
    if (res.ok && isHtml(res)) await cache.put(SHELL_URL, res.clone());
    return res;
  } catch (_) {
    return (await cache.match(SHELL_URL)) || Response.error();
  }
}

// /assets/* are content-hashed (immutable): cache first. Never cache an HTML reply under an asset URL
// (a host with an SPA fallback answers a missing .js with index.html and 200, which would poison the cache).
async function hashedAsset(request) {
  const cache = await caches.open(CACHE_NAME);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok && !isHtml(res)) await cache.put(request, res.clone());
  return res;
}

// Everything else same-origin (manifest, icon): serve cached, refresh in the background.
function staleWhileRevalidate(event) {
  const request = event.request;
  const refresh = caches.open(CACHE_NAME).then(async (cache) => {
    const res = await fetch(request);
    if (res.ok && !isHtml(res)) await cache.put(request, res.clone());
    return res;
  });
  event.waitUntil(refresh.catch(() => {}));
  return caches.match(request).then((hit) => hit || refresh.catch(() => Response.error()));
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  // Same-origin GETs only. The API lives on another origin: personal data must always be fresh and never sit in Cache Storage.
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname === '/sw.js') return;

  if (request.mode === 'navigate') {
    event.respondWith(shell(request));
  } else if (url.pathname.startsWith('/assets/')) {
    event.respondWith(hashedAsset(request));
  } else {
    event.respondWith(staleWhileRevalidate(event));
  }
});

// ---------------------------------------------------------------- web push (task reminders & nudges)
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    data = {};
  }
  const title = typeof data.title === 'string' && data.title ? data.title : "Lock'in";
  const url = typeof data.url === 'string' && data.url.startsWith('/') ? data.url : '/';
  const options = {
    body: typeof data.body === 'string' ? data.body : '',
    icon: '/favicon.svg',
    data: { url },
  };
  if (typeof data.tag === 'string' && data.tag) {
    options.tag = data.tag; // same tag replaces the earlier notification instead of stacking
    options.renotify = true;
  }
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ('focus' in client) {
          return client.focus().then((focused) => (focused && 'navigate' in focused ? focused.navigate(url) : focused));
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
