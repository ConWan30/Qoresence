// Qoresence Glass service worker — local-first shell.
// Caches the static shell; always goes network-first for live data + video.
const SHELL = [
  '/mobile.html',
  '/manifest.webmanifest',
  '/icons/glass-192.png',
  '/icons/glass-512.png'
];
const CACHE = 'qoresence-glass-v1';

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  // Never cache live video, still JPEG, or situation API — always network.
  if (
    url.pathname.startsWith('/video') ||
    url.pathname === '/live.jpg' ||
    url.pathname.startsWith('/api/')
  ) {
    return; // let the browser handle it
  }
  // Static shell: stale-while-revalidate.
  if (req.method === 'GET') {
    e.respondWith(
      caches.open(CACHE).then(async (c) => {
        const cached = await c.match(req);
        const fetchPromise = fetch(req).then((resp) => {
          if (resp && resp.status === 200) c.put(req, resp.clone());
          return resp;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    );
  }
});
