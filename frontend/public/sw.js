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

// ---------------------------------------------------------------- web push (reminders, nudges, companion)
// A push may carry up to two action buttons plus ONE signed, single-use, short-lived `token`. A button tap POSTs the
// token straight to the API (no session needed), so the loop closes from the lock screen without opening the app.
// iOS web push shows no buttons: there the body tap deep-links into the app (/?a=checkin ...), which finishes the job.
const ICON = '/favicon.svg';
// Buttons that finish by opening the app on the thing itself (morning "Start"): the tap is recorded first, then we go.
const OPEN_AFTER = new Set(['start']);

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    data = {};
  }
  const title = typeof data.title === 'string' && data.title ? data.title : "Lock'in";
  const url = typeof data.url === 'string' && data.url.startsWith('/') ? data.url : '/';
  const tag = typeof data.tag === 'string' && data.tag ? data.tag : '';
  const token = typeof data.token === 'string' && data.token ? data.token : '';
  const api = typeof data.api === 'string' && /^https:\/\//.test(data.api) ? data.api : '';
  const options = {
    body: typeof data.body === 'string' ? data.body : '',
    icon: ICON,
    data: { url, token, api, tag },
  };
  if (tag) {
    options.tag = tag; // same tag replaces the earlier notification instead of stacking
    options.renotify = true;
  }
  if (token && Array.isArray(data.actions)) {
    options.actions = data.actions
      .filter((a) => a && typeof a.action === 'string' && typeof a.title === 'string')
      .slice(0, 2)
      .map((a) => ({ action: a.action, title: a.title.slice(0, 24) }));
  }
  event.waitUntil(self.registration.showNotification(title, options));
});

async function postAction(d, action) {
  const base = (d.api || self.location.origin).replace(/\/$/, '');
  return fetch(`${base}/actions/${encodeURIComponent(d.token)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
    credentials: 'omit',
  });
}

// Replace the notification with a one-line result, then take it away again. Never leaves clutter behind.
async function flash(message, tag) {
  const t = tag || 'lockin-result';
  await self.registration.showNotification(message, { tag: t, silent: true, icon: ICON, data: { url: '/' } });
  await new Promise((resolve) => setTimeout(resolve, 3500));
  const open = await self.registration.getNotifications({ tag: t });
  open.forEach((n) => n.close());
}

function openApp(url) {
  return self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
    for (const client of windows) {
      if ('focus' in client) {
        return client.focus().then((focused) => (focused && 'navigate' in focused ? focused.navigate(url) : focused));
      }
    }
    return self.clients.openWindow(url);
  });
}

async function runButton(d, action) {
  try {
    const res = await postAction(d, action);
    if (res.ok) {
      const body = await res.json().catch(() => ({}));
      if (body && body.status !== 'failed') return OPEN_AFTER.has(action) ? openApp(d.url || '/') : flash(body.message || 'Done', d.tag);
    }
    // 401 / 410 (expired) / 429 / a failed action: don't pretend it worked. Hand over to the app.
  } catch (_) {
    // offline: the server never saw it, so nothing was consumed. Open the app instead.
  }
  return openApp(d.url || '/');
}

self.addEventListener('notificationclick', (event) => {
  const n = event.notification;
  const d = n.data || {};
  n.close();
  if (event.action && d.token) {
    event.waitUntil(runButton(d, event.action));
    return;
  }
  // Body tap: open the deep link and (best effort) tell the server it was seen, which keeps the anti-nag backoff honest.
  const seen = d.token ? postAction(d, 'open').catch(() => {}) : Promise.resolve();
  event.waitUntil(Promise.all([openApp(d.url || '/'), seen]));
});
