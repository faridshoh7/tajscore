/* Сервис-воркер Tajscore: приложение на телефоне, работа без сети и push.

   Отдаётся с корня сайта (/sw.js, см. app/routers/pages.py), иначе он не
   управлял бы страницами. Меняете логику — поднимите VERSION: старый кэш
   будет удалён при следующем открытии сайта. */
const VERSION = "ts-v1";
const STATIC_CACHE = VERSION + "-static";
const PAGES_CACHE = VERSION + "-pages";
const API_CACHE = VERSION + "-api";
const OFFLINE_URL = "/offline";

const PRECACHE = [
  OFFLINE_URL,
  "/static/img/logo-96.png",
  "/static/img/icon-192.png",
  "/manifest.webmanifest",
];

// Эти ответы нельзя ни кэшировать, ни подменять старыми: вход, личные данные
const NEVER_CACHE = ["/api/auth", "/api/favorites", "/api/notify", "/api/push", "/adminpanel"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(STATIC_CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => !k.startsWith(VERSION)).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

async function trim(cacheName, max) {
  const c = await caches.open(cacheName);
  const keys = await c.keys();
  for (let i = 0; i < keys.length - max; i++) await c.delete(keys[i]);
}

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;           // эмблемы с api-sports и шрифты — браузеру
  if (NEVER_CACHE.some(p => url.pathname.startsWith(p))) return;

  // Статика версионируется (?v=…) — смело берём из кэша
  if (url.pathname.startsWith("/static/")) {
    event.respondWith((async () => {
      const cache = await caches.open(STATIC_CACHE);
      const hit = await cache.match(req);
      if (hit) return hit;
      const res = await fetch(req);
      if (res.ok) { cache.put(req, res.clone()); trim(STATIC_CACHE, 300); }
      return res;
    })());
    return;
  }

  // Данные: всегда свежие из сети; без сети — последнее, что видели
  if (url.pathname.startsWith("/api/")) {
    event.respondWith((async () => {
      try {
        const res = await fetch(req);
        if (res.ok) {
          const cache = await caches.open(API_CACHE);
          cache.put(req, res.clone());
          trim(API_CACHE, 80);
        }
        return res;
      } catch (e) {
        const hit = await caches.match(req);
        if (hit) return hit;
        throw e;
      }
    })());
    return;
  }

  // Страницы: сеть, затем кэш, затем заглушка «нет связи»
  if (req.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const res = await fetch(req);
        if (res.ok) {
          const cache = await caches.open(PAGES_CACHE);
          cache.put(req, res.clone());
          trim(PAGES_CACHE, 30);
        }
        return res;
      } catch (e) {
        return (await caches.match(req)) || (await caches.match(OFFLINE_URL));
      }
    })());
  }
});

/* ------------------------------------------------------------------ push */
self.addEventListener("push", event => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch (e) { d = { title: "Tajscore", body: event.data && event.data.text() }; }
  const title = d.title || "Tajscore";
  event.waitUntil(self.registration.showNotification(title, {
    body: d.body || "",
    icon: d.icon || "/static/img/icon-192.png",
    badge: d.badge || "/static/img/icon-192.png",
    tag: d.tag || undefined,
    // новый гол по тому же матчу заменяет прежнее уведомление, но снова звенит
    renotify: !!d.tag,
    silent: !!d.silent,
    data: { url: d.url || "/" },
    vibrate: d.silent ? undefined : [120, 60, 120],
  }));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil((async () => {
    const path = new URL(target, location.origin).pathname;
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) {
      if (new URL(w.url).pathname === path && "focus" in w) return w.focus();
    }
    for (const w of wins) {
      if ("navigate" in w) { await w.navigate(target); return w.focus(); }
    }
    return self.clients.openWindow(target);
  })());
});

/* Браузер сам обновил подписку (так бывает раз в несколько месяцев) —
   сообщаем серверу новую, иначе уведомления молча перестали бы приходить. */
self.addEventListener("pushsubscriptionchange", event => {
  event.waitUntil((async () => {
    try {
      const r = await fetch("/api/push/key");
      const { key } = await r.json();
      const pad = "=".repeat((4 - key.length % 4) % 4);
      const raw = atob((key + pad).replace(/-/g, "+").replace(/_/g, "/"));
      const sub = await self.registration.pushManager.subscribe({
        userVisibleOnly: true, applicationServerKey: Uint8Array.from(raw, c => c.charCodeAt(0)) });
      await fetch("/api/push/subscribe", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscription: sub.toJSON() }) });
    } catch (e) { /* человек снова включит push в настройках */ }
  })());
});
