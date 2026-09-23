const CACHE_NAME = 'ttrpg-gemini-v53';
const PRECACHE_ASSETS = [
  '/',
  '/static/css/style.css?v=31',
  '/static/css/modules/tokens.css?v=21',
  '/static/css/modules/base.css?v=21',
  '/static/css/modules/components.css?v=21',
  '/static/css/modules/inventory.css?v=24',
  '/static/css/modules/market.css?v=2',
  '/static/css/modules/map.css?v=22',
  '/static/css/modules/lore.css?v=21',
  '/static/css/modules/feedback.css?v=21',
  '/static/css/modules/responsive.css?v=21',
  '/static/css/modules/theme.css?v=24',
  '/static/css/modules/theme-art.css?v=5',
  '/static/js/theme-bootstrap.js?v=33',
  '/static/js/modules/core.js?v=39',
  '/static/js/modules/pwa-notifications.js?v=32',
  '/static/js/modules/auth-admin.js?v=37',
  '/static/js/modules/session-character.js?v=38',
  '/static/js/modules/story-map-proxy.js?v=36',
  '/static/js/modules/realtime-chat.js?v=37',
  '/static/js/modules/campaign-actions.js?v=34',
  '/static/js/modules/equipment-images.js?v=32',
  '/static/js/modules/market.js?v=2',
  '/static/js/modules/local-components.js?v=31',
  '/static/js/app.js?v=34',
  '/manifest.json?v=2',
  '/static/icons/icon.svg?v=2',
  '/static/icons/d20.svg',
  '/static/icons/icon-192.png?v=2',
  '/static/icons/icon-512.png?v=2',
  '/static/icons/icon-maskable-192.png?v=2',
  '/static/icons/icon-maskable-512.png?v=2',
  '/static/icons/apple-touch-icon.png?v=2',
  '/static/icons/favicon.png?v=2',
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

    const title = payload.title || 'Przygoda RPG';
    await self.registration.showNotification(title, {
      body: payload.body || 'W grze wydarzyło się coś nowego.',
      icon: '/static/icons/icon-192.png?v=2',
      badge: '/static/icons/icon-192.png?v=2',
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
