const CACHE_NAME = 'ttrpg-gemini-v21';
const PRECACHE_ASSETS = [
  '/',
  '/static/css/style.css?v=16',
  '/static/js/app.js?v=20',
  '/static/manifest.json',
  '/static/icons/icon.svg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-maskable-192.png',
  '/static/icons/icon-maskable-512.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon.png',
  'https://cdn.tailwindcss.com',
  'https://cdn.jsdelivr.net/npm/alpinejs@3.14.3/dist/cdn.min.js'
];

// Install Event: pre-cache critical app shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Pre-caching offline app shell');
      // Use Promise.allSettled so external CDN failures don't block install
      return Promise.allSettled(
        PRECACHE_ASSETS.map((url) =>
          cache.add(url).catch((err) => console.warn(`[SW] Failed to cache: ${url}`, err))
        )
      );
    }).then(() => self.skipWaiting())
  );
});

// Activate Event: clean up old caches & take immediate control
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (name !== CACHE_NAME) {
            console.log('[SW] Removing old cache:', name);
            return caches.delete(name);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Systemowe powiadomienia, także gdy karta lub PWA są zamknięte.
self.addEventListener('push', (event) => {
  event.waitUntil((async () => {
    const visibleClients = await self.clients.matchAll({
      type: 'window',
      includeUncontrolled: true
    });
    if (visibleClients.some(client => client.visibilityState === 'visible')) return;

    let payload = {};
    try {
      payload = event.data ? event.data.json() : {};
    } catch (error) {
      payload = { body: event.data?.text() || 'W grze wydarzyło się coś nowego.' };
    }

    const title = payload.title || 'TTRPG Gemini Master';
    await self.registration.showNotification(title, {
      body: payload.body || 'W grze wydarzyło się coś nowego.',
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/icon-192.png',
      tag: payload.tag || 'ttrpg-update',
      renotify: true,
      data: { url: payload.url || '/' }
    });
  })());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    let targetUrl = new URL(event.notification.data?.url || '/', self.location.origin);
    if (targetUrl.origin !== self.location.origin) {
      targetUrl = new URL('/', self.location.origin);
    }

    const windowClients = await self.clients.matchAll({
      type: 'window',
      includeUncontrolled: true
    });
    for (const client of windowClients) {
      if ('navigate' in client) await client.navigate(targetUrl.href);
      return client.focus();
    }
    return self.clients.openWindow(targetUrl.href);
  })());
});

// Fetch Event: intelligent caching strategy
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 1. Skip non-GET requests, API endpoints, uploads, and WebSocket upgrades
  if (
    event.request.method !== 'GET' ||
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/ws/') ||
    url.pathname.startsWith('/uploads/')
  ) {
    return;
  }

  // 2. HTML Navigation requests: Network-first, fallback to cached '/'
  if (event.request.mode === 'navigate' || event.request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(event.request);
          if (cached) return cached;
          return caches.match('/');
        })
    );
    return;
  }

  // 3. CSS i JS: Network-first, żeby szablon nigdy nie działał ze starą logiką
  if (
    url.origin === self.location.origin &&
    (url.pathname.startsWith('/static/css/') || url.pathname.startsWith('/static/js/'))
  ) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // 4. Pozostałe statyczne zasoby: Stale-While-Revalidate
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
          }
          return networkResponse;
        })
        .catch(() => {
          // Silent catch for network failure when offline
          return cachedResponse;
        });

      return cachedResponse || fetchPromise;
    })
  );
});
