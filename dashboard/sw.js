/* BMTC Future Transit Planner - service worker (v3).
 * The shell (page, scripts, styles, icons) is fetched from the network first and then stored, so a new deployment
 * is used at once, and the app still opens offline with the last copy this device saw.
 * Some public timetable answers are also kept, so a timetable opened once can be read offline. Each kept answer is
 * stamped with the time it was saved, and an offline answer is marked as a saved copy.
 * Answers that depend on the time of day, on journey planning, on nearby search, on scenarios, on saved routes or
 * preferences, and every admin answer, are never kept. A search with typed words (a non-empty q, for a route or stop
 * name) is never kept either. Requests to other origins (map tiles) are left alone.
 */
var CACHE = "bmtc-planner-shell-v3";
var SHELL_PREFIX = "bmtc-planner-shell-";
var TIMETABLE_CACHE = "bmtc-planner-timetable-v1";
var TIMETABLE_PREFIX = "bmtc-planner-timetable-";
var TIMETABLE_LIMIT = 120;
// Public answers that depend only on the timetable data, never on the time of day or on the device.
var SAVED_API = /^\/api\/(routes|routes\/[^\/]+|routes\/[^\/]+\/timetable|stops|data-sources)$/;
var SHELL = [
  "/",
  "/index.html",
  "/app.js",
  "/i18n.js",
  "/styles.css",
  "/manifest.webmanifest",
  "/vendor/leaflet/leaflet.js",
  "/vendor/leaflet/leaflet.css",
  "/icons/icon-192.png",
  "/icons/icon-512.png"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      // Each file is stored on its own, so one missing file cannot stop the worker from installing.
      return Promise.all(
        SHELL.map(function (url) {
          return fetch(url, { cache: "reload" })
            .then(function (response) {
              return response.ok ? cache.put(url, response) : null;
            })
            .catch(function () {
              return null;
            });
        })
      );
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(
        names
          .filter(function (name) {
            return (name.indexOf(SHELL_PREFIX) === 0 && name !== CACHE) ||
              (name.indexOf(TIMETABLE_PREFIX) === 0 && name !== TIMETABLE_CACHE);
          })
          .map(function (name) {
            return caches.delete(name);
          })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") return;
  var url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf("/api/") === 0) {
    if (SAVED_API.test(url.pathname)) event.respondWith(savedAnswer(event));
    return;
  }
  event.respondWith(shellAnswer(request));
});

function shellAnswer(request) {
  return fetch(request)
    .then(function (response) {
      if (response && response.ok && response.type === "basic") {
        var copy = response.clone();
        caches.open(CACHE).then(function (cache) {
          cache.put(request, copy);
        });
      }
      return response;
    })
    .catch(function () {
      return caches.match(request).then(function (cached) {
        if (cached) return cached;
        if (request.mode === "navigate") return caches.match("/index.html");
        return Response.error();
      });
    });
}

// The server answer goes to the page unchanged. A copy is kept for offline reading, and if the server cannot be
// reached the kept copy is returned with a header that tells the page it is a saved copy.
function savedAnswer(event) {
  var request = event.request;
  // A search with typed words (a non-empty q parameter) is never kept: its copy would record the words searched for.
  // The route and stop lists send q with an empty value when nothing is typed, and those lists are kept.
  var keep = !new URL(request.url).searchParams.get("q");
  return fetch(request)
    .then(function (response) {
      if (keep && response && response.ok) event.waitUntil(keepCopy(request, response.clone()));
      return response;
    })
    .catch(function () {
      return caches.open(TIMETABLE_CACHE)
        .then(function (cache) {
          return cache.match(request);
        })
        .then(function (saved) {
          if (!saved) return Response.error();
          return withHeaders(saved, { "X-Served-From-Cache": "1" });
        });
    });
}

function keepCopy(request, response) {
  return response.blob().then(function (body) {
    var headers = new Headers(response.headers);
    headers.delete("Content-Encoding");
    headers.delete("Content-Length");
    headers.set("X-Saved-At", new Date().toISOString());
    var stored = new Response(body, { status: response.status, statusText: response.statusText, headers: headers });
    return caches.open(TIMETABLE_CACHE).then(function (cache) {
      return cache.put(request, stored).then(function () {
        return trimCache(cache);
      });
    });
  }).catch(function () {
    return null;
  });
}

// Drops the oldest kept answers once there are more than the limit.
function trimCache(cache) {
  return cache.keys().then(function (keys) {
    var extra = keys.length - TIMETABLE_LIMIT;
    if (extra <= 0) return null;
    return Promise.all(keys.slice(0, extra).map(function (key) {
      return cache.delete(key);
    }));
  });
}

function withHeaders(response, extra) {
  return response.blob().then(function (body) {
    var headers = new Headers(response.headers);
    Object.keys(extra).forEach(function (name) {
      headers.set(name, extra[name]);
    });
    return new Response(body, { status: response.status, statusText: response.statusText, headers: headers });
  });
}
