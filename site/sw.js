// Network-first for the digest so it is always fresh; cached copy only when offline.
const CACHE = "regarding-maine-v1";
self.addEventListener("install", e => e.waitUntil(
  caches.open(CACHE).then(c => c.addAll(["./", "manifest.webmanifest", "icon-192.png"]))));
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.endsWith(".mp3") || url.origin !== location.origin) return;
  e.respondWith(fetch(e.request).then(r => {
    const copy = r.clone();
    caches.open(CACHE).then(c => c.put(e.request, copy));
    return r;
  }).catch(() => caches.match(e.request)));
});
