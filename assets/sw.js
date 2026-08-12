const CACHE_NAME = "naengjango-hankki-v1";
const PRECACHE_URLS = ["/logo.svg", "/icon.svg", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 정적 자산(로고/아이콘/매니페스트)만 캐시 우선으로 서빙한다.
// 그 외 요청(API 호출, 실시간 상태 연결)은 항상 네트워크로 그대로 보낸다 -
// 이 앱은 실시간 서버 상태(Reflex 이벤트, FastAPI 호출)에 의존하므로 오프라인 완전
// 지원은 하지 않고, "홈 화면 설치가 가능한 앱"이라는 PWA 최소 요건만 충족한다.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (PRECACHE_URLS.includes(url.pathname)) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
  }
});
