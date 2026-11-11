// Service worker för Värdskärm: gör att den publicerade appen startar utan nät.
// Appen själv hämtas alltid från nätet först (så att nya versioner slår igenom direkt)
// och från cachen bara när nätet saknas. Biblioteken från CDN har versionsnummer i
// adressen och ändras aldrig, så de tas från cachen direkt.
const CACHE = 'vardskarm-v1';
const CDN = 'https://cdn.jsdelivr.net/';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['./', 'index.html']).catch(() => {})).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET') return;
  if (url.href.startsWith(CDN)) {                       // bibliotek: cache först
    e.respondWith(caches.open(CACHE).then(async c => {
      const hit = await c.match(req, { ignoreVary: true });
      if (hit) return hit;
      const res = await fetch(req);
      if (res.ok || res.type === 'opaque') c.put(req, res.clone());
      return res;
    }));
    return;
  }
  if (url.origin !== location.origin) return;           // t.ex. ntfy.sh: rör inte
  e.respondWith((async () => {                          // appen: nät först, cache som reserv
    const c = await caches.open(CACHE);
    try {
      const res = await fetch(req, { cache: 'no-cache' });
      if (res.ok) c.put(req, res.clone());
      return res;
    } catch (err) {
      const hit = await c.match(req, { ignoreSearch: true }) || await c.match('index.html');
      if (hit) return hit;
      throw err;
    }
  })());
});
