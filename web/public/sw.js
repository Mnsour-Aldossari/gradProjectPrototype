// Service worker for the installable field view.
// Network first: online users always get the current app; if the network drops, the last
// loaded app shell still opens. Live data (/api, /ws) and dev-server files are never cached.
const CACHE = 'uav-field-shell-v1'
const SHELL = ['/field', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png']
const BYPASS = ['/api/', '/ws/', '/@', '/src/', '/node_modules/']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .catch(() => undefined),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (BYPASS.some((prefix) => url.pathname.startsWith(prefix))) return

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) event.waitUntil(keepCopy(request, response.clone()))
        return response
      })
      .catch(async () => {
        const cached = await caches.match(request)
        if (cached) return cached
        if (request.mode === 'navigate') {
          const shell = await caches.match('/field')
          if (shell) return shell
        }
        return Response.error()
      }),
  )
})

// Keeps a copy of a good network answer for offline use. A full or blocked cache only loses that copy: the answer
// itself has already been served.
async function keepCopy(request, response) {
  try {
    const cache = await caches.open(CACHE)
    await cache.put(request, response)
  } catch {
    // no offline copy this time; the next successful load tries again
  }
}
