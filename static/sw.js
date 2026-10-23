/* LHM Ads AI PWA: shell assets only, NEVER cache credentials or Ads data. */
'use strict';
const VERSION = 'lhm-pwa-v1-20261023';
const OFFLINE_URL = '/static/pwa-offline.html';
const SHELL = [
  OFFLINE_URL,
  '/static/pwa-offline.css',
  '/static/pwa-mobile.css',
  '/static/pwa-install.js',
  '/static/pwa-offline.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(VERSION).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('lhm-pwa-') && key !== VERSION).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // All authenticated routes including /studio, /api/* and OAuth are network-only.
  // An offline navigation displays an honest offline page, never stale Ads numbers.
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(async () => (await caches.match(OFFLINE_URL)) || Response.error()));
    return;
  }
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/mcp') || url.pathname.startsWith('/oauth')
      || url.pathname === '/sw.js' || url.pathname === '/manifest.webmanifest') return;
  // Only public code, styles, fonts and icons may be cached; no HTML or user reports.
  if (!url.pathname.startsWith('/static/') ||
      !/\.(?:js|css|png|svg|webp|woff2?)$/i.test(url.pathname)) return;
  event.respondWith(fetch(req).then(response => {
    if (response.ok && response.type === 'basic') {
      const copy = response.clone();
      event.waitUntil(caches.open(VERSION).then(cache => cache.put(req, copy)));
    }
    return response;
  }).catch(async () => (await caches.match(req)) || Response.error()));
});
