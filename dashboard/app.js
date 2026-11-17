/* BMTC Future Transit Planner - web dashboard (v3).
 * No inline scripts or handlers (the CSP forbids them) and no code from a CDN.
 * "Now" and "today" come from the server clock in the feed's time zone, never from this device alone.
 * Official, unverified and estimated data are always shown in separate, labelled places.
 * Syntax is kept to ES2017 (no optional chaining, no object spread, no nullish operator).
 */
(function () {
  "use strict";

  var PLANNING_YEARS = [2027, 2028, 2029, 2030];
  var DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
  var FALLBACK_LANG = "en";
  var MAX_TRIPS_SHOWN = 200;
  var MAX_SCENARIO_STOPS = 30;
  var REQUEST_TIMEOUT_MS = 15000;
  var DOWNLOAD_TIMEOUT_MS = 60000;
  var CLOCK_TIMEOUT_MS = 8000;
  var CLOCK_TICK_MS = 30000;
  var CLOCK_RESYNC_MS = 10 * 60 * 1000;
  var IMPORT_TIMEOUT_MS = 5 * 60 * 1000;
  var BACKUP_TIMEOUT_MS = 2 * 60 * 1000;
  var PREFIX = "bmtc.";
  var CSS_FOR = { OFFICIAL_VERIFIED: "official", UNVERIFIED_FEED: "unverified", ESTIMATED_SCENARIO: "scenario" };

  // storage-begin
  // Browser storage can be blocked (private windows, embedded frames). Reads then return null and writes are skipped.
  var storage = (function () {
    function store() {
      try {
        return window.localStorage || null;
      } catch (_) {
        return null;
      }
    }
    return {
      get: function (key) {
        var area = store();
        try {
          return area ? area.getItem(key) : null;
        } catch (_) {
          return null;
        }
      },
      set: function (key, value) {
        var area = store();
        try {
          if (area) area.setItem(key, value);
        } catch (_) {
          /* full or blocked: the app keeps working without saving */
        }
      },
    };
  })();
  // storage-end

  var state = {
    lang: FALLBACK_LANG,
    year: 2027,
    classification: "OFFICIAL_VERIFIED",
    adminKey: "",
    clock: null,
    clockFailed: false,
    clockOffsetMs: 0,
    clockSyncedAt: 0,
    lastServiceDate: null,
    viewToken: 0,
    searchToken: 0,
    yearToken: 0,
    timetableToken: 0,
    map: null,
    markers: null,
    scenarioEditId: null,
    scenarioStops: [],
    route: null,
    features: null,
    services: null,
    version: "",
    theme: "system",
    lowData: false,
    largeText: false,
    autoNearby: false,
    pendingQuery: "",
  };

  var startedAt = Date.now();

  var el = {
    view: document.getElementById("view"),
    yearStatus: document.getElementById("yearStatus"),
    yearSelect: document.getElementById("yearSelect"),
    langSelect: document.getElementById("langSelect"),
    clock: document.getElementById("serviceClock"),
    offline: document.getElementById("offlineBanner"),
    saved: document.getElementById("savedBanner"),
    savedText: document.getElementById("savedText"),
    sidebar: document.getElementById("sidebar"),
    navToggle: document.getElementById("navToggle"),
    toast: document.getElementById("toast"),
  };

  var catalogue = window.BMTC_I18N || { languages: [{ code: FALLBACK_LANG, name: "English" }], messages: {} };

  // ---------------------------------------------------------------- text and language
  function esc(value) {
    return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function isLanguage(code) {
    return catalogue.languages.some(function (item) {
      return item.code === code;
    });
  }

  function lookup(key) {
    var table = catalogue.messages[state.lang] || {};
    var base = catalogue.messages[FALLBACK_LANG] || {};
    if (Object.prototype.hasOwnProperty.call(table, key)) return table[key];
    if (Object.prototype.hasOwnProperty.call(base, key)) return base[key];
    return null;
  }

  function hasMessage(key) {
    return lookup(key) !== null;
  }

  // Returns plain text. Callers must pass it through esc() before it goes into HTML.
  function t(key, values) {
    var text = lookup(key);
    if (text === null) return key;
    if (!values) return text;
    return text.replace(/\{(\w+)\}/g, function (match, name) {
      return Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match;
    });
  }

  function localeTag() {
    return state.lang === FALLBACK_LANG ? "en-IN" : state.lang;
  }

  function pickInitialLanguage() {
    var saved = storage.get(PREFIX + "lang");
    if (saved && isLanguage(saved)) return saved;
    var wanted = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || FALLBACK_LANG];
    for (var i = 0; i < wanted.length; i += 1) {
      var code = String(wanted[i] || "").toLowerCase().split("-")[0];
      if (isLanguage(code)) return code;
    }
    return FALLBACK_LANG;
  }

  // ---------------------------------------------------------------- time (service zone, server clock)
  function zoneName() {
    if (state.clock && state.clock.service_timezone) return state.clock.service_timezone;
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch (_) {
      return "UTC";
    }
  }

  function formatter(options) {
    try {
      return new Intl.DateTimeFormat(localeTag(), Object.assign({ timeZone: zoneName() }, options));
    } catch (_) {
      return new Intl.DateTimeFormat(localeTag(), options);
    }
  }

  // Calendar parts of an instant in the service zone (always Latin digits, 24-hour clock).
  function partsAt(ms) {
    var options = { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" };
    var fmt;
    try {
      fmt = new Intl.DateTimeFormat("en-US", Object.assign({ timeZone: zoneName() }, options));
    } catch (_) {
      fmt = new Intl.DateTimeFormat("en-US", options);
    }
    var out = {};
    fmt.formatToParts(new Date(ms)).forEach(function (part) {
      out[part.type] = part.value;
    });
    return out;
  }

  function dateKeyAt(ms) {
    var p = partsAt(ms);
    return p.year + "-" + p.month + "-" + p.day;
  }

  // The server's time plus the offset measured when the clock was last read. Falls back to this device's time.
  function serverNowMs() {
    return Date.now() + (state.clock ? state.clockOffsetMs : 0);
  }

  function todayKey() {
    return dateKeyAt(serverNowMs());
  }

  function isIsoDate(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ""));
  }

  function addDays(isoDate, days) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
    if (!m) return isoDate;
    return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + days)).toISOString().slice(0, 10);
  }

  function formatCalendarDate(isoDate) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(isoDate || ""));
    if (!m) return t("common.na");
    var date = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
    return new Intl.DateTimeFormat(localeTag(), { timeZone: "UTC", weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(date);
  }

  // A YYYY, YYYY-MM or YYYY-MM-DD value, shown only as precisely as it was announced.
  function formatPartialDate(value) {
    var text = String(value || "");
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return formatCalendarDate(text);
    var m = /^(\d{4})-(\d{2})$/.exec(text);
    if (m) {
      var month = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, 1));
      return new Intl.DateTimeFormat(localeTag(), { timeZone: "UTC", month: "long", year: "numeric" }).format(month);
    }
    return /^\d{4}$/.test(text) ? text : t("common.na");
  }

  // A clock time (for example 08:12) in the service zone, from an ISO string that carries its own offset.
  function formatClockTime(iso) {
    var ms = Date.parse(iso);
    if (isNaN(ms)) return t("common.na");
    return formatter({ hour: "2-digit", minute: "2-digit" }).format(new Date(ms));
  }

  function dayLabel(iso, today) {
    var ms = Date.parse(iso);
    if (isNaN(ms) || !today) return t("common.na");
    var key = dateKeyAt(ms);
    if (key === today) return t("time.today");
    if (key === addDays(today, 1)) return t("time.tomorrow");
    return formatCalendarDate(key);
  }

  // Scheduled GTFS times such as 08:12:00 or 25:10:00 (past midnight) as seconds from the service day's start.
  function gtfsSeconds(value) {
    var m = /^(\d+):(\d{2}):(\d{2})$/.exec(String(value || ""));
    return m ? Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) : null;
  }

  function nowSecondsInZone() {
    var p = partsAt(serverNowMs());
    return Number(p.hour) * 3600 + Number(p.minute) * 60 + Number(p.second);
  }

  function fmtNum(value) {
    if (value === null || value === undefined || value === "" || !isFinite(Number(value))) return t("common.na");
    return new Intl.NumberFormat(localeTag()).format(Number(value));
  }

  function quantity(value, unitKey) {
    if (value === null || value === undefined || value === "") return esc(t("common.na"));
    return esc(t(unitKey, { n: fmtNum(value) }));
  }

  function naOr(value) {
    return value === null || value === undefined || value === "" ? esc(t("common.na")) : esc(value);
  }

  function classLabel(code) {
    return CSS_FOR[code] ? t("cls." + code) : String(code || "");
  }

  function badge(classification) {
    var css = CSS_FOR[classification] || "neutral";
    return '<span class="badge ' + css + '">' + esc(classLabel(classification)) + "</span>";
  }

  // Only http and https links are rendered as links. Anything else (javascript:, data:) is shown as text.
  function safeHref(url) {
    if (!url) return null;
    try {
      var parsed = new URL(String(url), window.location.href);
      return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
    } catch (_) {
      return null;
    }
  }

  // ---------------------------------------------------------------- network
  // Also kept in memory, so one page session keeps one device key even where browser storage is blocked.
  var memoryClientKey = "";
  function clientKey() {
    var key = storage.get(PREFIX + "clientKey") || memoryClientKey;
    if (!key || key.length < 16) {
      if (!window.crypto || !window.crypto.getRandomValues) {
        throw new Error(t("msg.unexpected"));
      }
      var bytes = new Uint8Array(24);
      window.crypto.getRandomValues(bytes);
      key = btoa(String.fromCharCode.apply(null, Array.prototype.slice.call(bytes)))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      storage.set(PREFIX + "clientKey", key);
    }
    memoryClientKey = key;
    return key;
  }

  function startTimer(ms) {
    var controller = typeof AbortController === "function" ? new AbortController() : null;
    var timer = setTimeout(function () {
      if (controller) controller.abort();
    }, ms);
    return {
      signal: controller ? controller.signal : undefined,
      stop: function () {
        clearTimeout(timer);
      },
    };
  }

  async function send(url, init, signal) {
    var options = Object.assign({ cache: "no-store", credentials: "same-origin" }, init);
    if (signal) options.signal = signal;
    try {
      return await fetch(url, options);
    } catch (err) {
      throw new Error(err && err.name === "AbortError" ? t("msg.timeout") : t("msg.network"));
    }
  }

  async function readJson(response) {
    try {
      return await response.json();
    } catch (err) {
      if (err && err.name === "AbortError") throw new Error(t("msg.timeout"));
      return null;
    }
  }

  function messageFrom(data, status) {
    var detail = data && data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map(function (item) {
          var where = item.loc && item.loc.length > 1 ? item.loc.slice(1).join(".") + ": " : "";
          return where + (item.msg || "");
        })
        .join("; ");
    }
    if (detail && typeof detail === "object") {
      if (detail.message) return detail.message;
      if (Array.isArray(detail.errors) && detail.errors.length) return detail.errors.join("; ");
    }
    return t("msg.failed", { status: status });
  }

  function httpError(response, data) {
    var error = new Error(messageFrom(data, response.status));
    error.status = response.status;
    error.data = data;
    if (response.status === 429) error.message = t("msg.rate_limited");
    return error;
  }

  async function api(path, options) {
    var opts = options || {};
    var headers = { Accept: "application/json", "X-Client-Key": clientKey() };
    var body;
    if (opts.admin) {
      if (!state.adminKey) throw new Error(t("admin.key_needed"));
      headers["X-Admin-Key"] = state.adminKey;
    }
    if (opts.form) {
      body = opts.form;
    } else if (opts.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.json);
    }
    var timer = startTimer(opts.timeout || REQUEST_TIMEOUT_MS);
    try {
      var response = await send(path, { method: opts.method || "GET", headers: headers, body: body }, timer.signal);
      noteSource(response);
      if (response.status === 204) return null;
      var data = await readJson(response);
      if (!response.ok) {
        if (response.status === 401 && opts.admin) {
          state.adminKey = "";
          var rejected = httpError(response, data);
          rejected.message = t("admin.key_rejected");
          throw rejected;
        }
        throw httpError(response, data);
      }
      return data;
    } finally {
      timer.stop();
    }
  }

  async function download(path, fallbackName) {
    var timer = startTimer(DOWNLOAD_TIMEOUT_MS);
    try {
      var response = await send(path, { headers: { "X-Client-Key": clientKey() } }, timer.signal);
      if (!response.ok) throw httpError(response, await readJson(response));
      var blob = await response.blob();
      var match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "");
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = match ? match[1] : fallbackName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(function () {
        URL.revokeObjectURL(url);
      }, 1500);
    } catch (err) {
      if (err && err.name === "AbortError") throw new Error(t("msg.timeout"));
      throw err;
    } finally {
      timer.stop();
    }
  }

  // ---------------------------------------------------------------- server clock
  function renderClockBar() {
    if (!el.clock) return;
    if (state.clockFailed) {
      el.clock.textContent = t("clock.unavailable");
      return;
    }
    if (!state.clock) {
      el.clock.textContent = t("clock.loading");
      return;
    }
    var ms = serverNowMs();
    el.clock.textContent = t("clock.line", {
      date: formatter({ weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date(ms)),
      time: formatter({ hour: "2-digit", minute: "2-digit" }).format(new Date(ms)),
      zone: zoneName(),
    });
  }

  async function loadClock() {
    var sent = Date.now();
    try {
      var data = await api("/api/clock", { timeout: CLOCK_TIMEOUT_MS });
      var received = Date.now();
      var serverMs = Date.parse(data.now_utc);
      if (!isNaN(serverMs)) state.clockOffsetMs = serverMs - Math.round((sent + received) / 2);
      state.clock = data;
      state.clockFailed = false;
      state.clockSyncedAt = received;
    } catch (err) {
      state.clockFailed = true;
    }
    renderClockBar();
    return !state.clockFailed;
  }

  // Runs every 30 seconds: keeps the clock bar current, re-reads the server clock now and then,
  // and redraws the views when the service date has moved on (so "today" is never stale).
  function tick() {
    renderClockBar();
    var stale = state.clockFailed || Date.now() - state.clockSyncedAt > CLOCK_RESYNC_MS;
    var reading = stale ? loadClock() : Promise.resolve(true);
    reading.then(function () {
      if (state.renderedDate && todayKey() !== state.renderedDate) {
        toast(t("clock.date_changed"));
        render();
      }
    });
  }

  // ---------------------------------------------------------------- language, menu, toast
  function directionOf(code) {
    var item = catalogue.languages.filter(function (language) {
      return language.code === code;
    })[0];
    return item && item.dir === "rtl" ? "rtl" : "ltr";
  }

  function applyStaticText() {
    document.querySelectorAll("[data-i18n]").forEach(function (node) {
      node.textContent = t(node.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (node) {
      node.setAttribute("aria-label", t(node.getAttribute("data-i18n-aria")));
    });
  }

  function populateLanguages() {
    el.langSelect.textContent = "";
    catalogue.languages.forEach(function (item) {
      var option = document.createElement("option");
      option.value = item.code;
      option.textContent = item.name;
      el.langSelect.appendChild(option);
    });
  }

  function setLanguage(code) {
    if (!isLanguage(code)) return;
    state.lang = code;
    storage.set(PREFIX + "lang", code);
    document.documentElement.lang = code;
    document.documentElement.dir = directionOf(code);
    document.title = t("app.brand");
    el.langSelect.value = code;
    applyStaticText();
    syncMenuLabel();
    renderClockBar();
  }

  function syncMenuLabel() {
    var open = el.sidebar.classList.contains("open");
    el.navToggle.setAttribute("aria-label", t(open ? "menu.close" : "menu.open"));
  }

  function setMenu(open) {
    el.sidebar.classList.toggle("open", open);
    el.navToggle.setAttribute("aria-expanded", String(open));
    syncMenuLabel();
  }

  var toastTimer = null;
  function toast(message) {
    el.toast.textContent = message;
    el.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.toast.hidden = true;
    }, 4500);
  }

  // An answer kept for offline reading is marked by the service worker. The notice shows when it was saved,
  // and hides again as soon as an answer comes straight from the server.
  function noteSource(response) {
    if (response.headers.get("X-Served-From-Cache") !== "1") {
      el.saved.hidden = true;
      return;
    }
    var when = new Date(response.headers.get("X-Saved-At") || "");
    var text = isNaN(when.getTime())
      ? t("common.na")
      : new Intl.DateTimeFormat(localeTag(), { dateStyle: "medium", timeStyle: "short" }).format(when);
    el.savedText.textContent = t("offline.saved", { time: text });
    el.saved.hidden = false;
  }

  function syncOnlineState() {
    el.offline.hidden = navigator.onLine !== false;
  }

  // ---------------------------------------------------------------- render cycle
  // Every render gets a token. A slow answer that arrives after the user has moved on is ignored,
  // so it can never overwrite the page the user is looking at.
  function isCurrent(panel, token) {
    return token === state.viewToken && !!panel && panel.isConnected;
  }

  function loadingCard(text) {
    return '<section class="card" aria-busy="true"><p class="muted">' + esc(text || t("common.loading")) + "</p></section>";
  }

  function loadingInline(text) {
    return '<p class="muted" aria-busy="true">' + esc(text || t("common.loading")) + "</p>";
  }

  function panelError(err, action) {
    return '<div class="banner error" role="alert"><strong>' + esc(t("common.error")) + "</strong>" + esc(err.message || t("msg.unexpected")) +
      '<div style="margin-top:8px"><button type="button" class="secondary" data-action="' + esc(action) + '">' + esc(t("common.retry")) + "</button></div></div>";
  }

  function setView(html) {
    el.view.innerHTML = html;
  }

  // A search typed on the home screen is handed to the Routes or Stops page, which shows it in its own search box.
  function takePendingQuery(formId) {
    var query = state.pendingQuery || "";
    state.pendingQuery = "";
    var form = document.getElementById(formId);
    if (query && form && form.elements.q) form.elements.q.value = query;
    return query;
  }

  function routeParts() {
    return location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  }

  async function render() {
    state.viewToken += 1;
    var token = state.viewToken;
    state.renderedDate = todayKey();
    destroyMap();
    var parts = routeParts();
    var name = parts[0] && Object.prototype.hasOwnProperty.call(ROUTES, parts[0]) ? parts[0] : "home";
    var isSection = NEW_SECTIONS.indexOf(name) !== -1;
    document.body.setAttribute("data-view", isSection ? name : "tools");
    document.querySelectorAll("[data-nav]").forEach(function (link) {
      if (link.getAttribute("href") === "#/" + name) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    setMenu(false);
    if (isSection && name !== "nearby") {
      state.yearToken += 1;
      el.yearStatus.innerHTML = "";
      el.yearStatus.hidden = true;
    } else {
      el.yearStatus.hidden = false;
      renderYearStatus();
    }
    try {
      await ROUTES[name](parts.slice(1), token);
    } catch (err) {
      if (token === state.viewToken) setView(panelError(err, "rerender"));
    }
    hideSplash();
  }

  // Fills one panel with the result of job(). Stale answers are dropped; errors stay inside the panel.
  async function fillPanel(panel, token, job, searchSeq) {
    if (!panel) return;
    panel.innerHTML = loadingInline();
    try {
      var html = await job();
      var stale = searchSeq !== undefined && searchSeq !== state.searchToken;
      if (!stale && isCurrent(panel, token)) panel.innerHTML = html;
    } catch (err) {
      var stillWanted = searchSeq === undefined || searchSeq === state.searchToken;
      if (stillWanted && isCurrent(panel, token)) panel.innerHTML = panelError(err, "rerender");
    }
  }

  async function renderYearStatus() {
    var seq = ++state.yearToken;
    try {
      var data = await api("/api/years/" + encodeURIComponent(state.year) + "/status");
      if (seq !== state.yearToken) return;
      // A heading names data only when that data exists; otherwise it says plainly that none is available.
      var officialTitle = data.official.imports ? t("year.official_title", { year: state.year }) : t("year.official_none");
      var unverifiedTitle = data.unverified.imports ? t("year.unverified_title", { year: state.year }) : t("year.unverified_none");
      el.yearStatus.innerHTML =
        '<div class="banner official"><strong>' + badge("OFFICIAL_VERIFIED") + " " + esc(officialTitle) + "</strong>" + esc(data.official.message) + "</div>" +
        '<div class="banner unverified"><strong>' + badge("UNVERIFIED_FEED") + " " + esc(unverifiedTitle) + "</strong>" + esc(data.unverified.message) + "</div>" +
        '<div class="banner scenario"><strong>' + badge("ESTIMATED_SCENARIO") + "</strong>" + esc(t("scn.notice")) + "</div>";
    } catch (err) {
      if (seq === state.yearToken) el.yearStatus.innerHTML = '<div class="banner error" role="alert">' + esc(err.message) + "</div>";
    }
  }

  function segmentedClassification() {
    function option(code) {
      var pressed = state.classification === code ? "true" : "false";
      return '<button type="button" data-action="cls" data-cls="' + code + '" aria-pressed="' + pressed + '">' + esc(classLabel(code)) + "</button>";
    }
    return '<div class="seg" role="group" aria-label="' + esc(t("cls.label")) + '">' + option("OFFICIAL_VERIFIED") + option("UNVERIFIED_FEED") + "</div>";
  }

  // ---------------------------------------------------------------- maps (guarded: the map is optional)
  function destroyMap() {
    if (state.map) state.map.remove();
    state.map = null;
    state.markers = null;
  }

  function makeMap(elementId) {
    destroyMap();
    var element = document.getElementById(elementId);
    if (!element) return null;
    if (typeof window.L === "undefined") {
      element.innerHTML = '<div class="map-message">' + esc(t("msg.map_unavailable")) + "</div>";
      return null;
    }
    var L = window.L;
    var map = L.map(element, { scrollWheelZoom: false }).setView([20, 0], 2);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
    }).addTo(map);
    // Credits never replace the app: the map data credit opens in a new tab, and the library is named without a link
    // (Leaflet's own default links away in the same tab, which in the installed app would leave the app).
    if (map.attributionControl) map.attributionControl.setPrefix("Leaflet");
    state.map = map;
    state.markers = L.layerGroup().addTo(map);
    return map;
  }

  function validCoord(lat, lon) {
    return typeof lat === "number" && typeof lon === "number" && isFinite(lat) && isFinite(lon);
  }

  function messageFor(code, fallback) {
    var key = "msgcode." + code;
    if (code && hasMessage(key)) return t(key);
    return fallback || t("msg.unexpected");
  }

  function dayName(code) {
    return hasMessage("day." + code) ? t("day." + code) : String(code || "");
  }

  // The planning date is "today" in the service zone when that year is being planned, else 1 January.
  function defaultDate() {
    var today = todayKey();
    return Number(today.slice(0, 4)) === state.year ? today : state.year + "-01-01";
  }

  // ---------------------------------------------------------------- routes and timetables
  function routeItem(r) {
    return '<li><div><div class="title">' + esc(r.short_name || r.gtfs_route_id) + '</div><div class="muted">' + esc(r.long_name || "") + "</div></div>" +
      '<div class="row-actions">' + badge(r.classification) +
      '<a class="button secondary" href="#/routes/' + esc(encodeURIComponent(r.id)) + '">' + esc(t("common.open")) + "</a></div></li>";
  }

  function routeListHtml(data) {
    if (data.results.length) return '<ul class="list">' + data.results.map(routeItem).join("") + "</ul>";
    var noCoverage = data.coverage && data.coverage.status === "NONE";
    var text = noCoverage
      ? messageFor(data.classification === "OFFICIAL_VERIFIED" ? "NO_OFFICIAL_DATA" : "NO_UNVERIFIED_DATA")
      : t("routes.no_match");
    return '<div class="empty">' + esc(text) + "</div>";
  }

  async function loadRouteResults(query, panel, token) {
    var seq = ++state.searchToken;
    await fillPanel(panel, token, async function () {
      var params = new URLSearchParams({ classification: state.classification, year: String(state.year), q: query, limit: "100" });
      var data = await api("/api/routes?" + params.toString());
      return routeListHtml(data) + (data.results.length ? "" : await otherClassificationHint("/api/routes", query));
    }, seq);
  }

  // When nothing matches in the chosen classification, say whether the other one has matches. The two are never
  // mixed: the user decides to switch, and the search is repeated there.
  async function otherClassificationHint(path, query) {
    var other = state.classification === "OFFICIAL_VERIFIED" ? "UNVERIFIED_FEED" : "OFFICIAL_VERIFIED";
    try {
      var params = new URLSearchParams({ classification: other, year: String(state.year), q: query, limit: "1" });
      var data = await api(path + "?" + params.toString());
      if (!data.results.length) return "";
    } catch (_) {
      return "";
    }
    return '<div class="notice"><p>' + esc(t("search.other_found", { cls: classLabel(state.classification), other: classLabel(other) })) + "</p>" +
      '<button type="button" class="secondary" data-action="cls-search" data-cls="' + esc(other) + '" data-q="' + esc(query) + '">' +
      esc(t("search.show_other", { other: classLabel(other) })) + "</button></div>";
  }

  async function loadSaved(panel, token) {
    await fillPanel(panel, token, async function () {
      var data = await api("/api/saved-routes");
      if (!data.saved.length) return '<div class="empty">' + esc(t("routes.saved_none")) + "</div>";
      return '<ul class="list">' + data.saved.map(function (s) {
        return '<li><div><div class="title">' + esc(s.label) + '</div><div class="muted">' + esc(s.gtfs_route_id) + "</div></div>" +
          '<div class="row-actions">' + badge(s.classification) +
          '<button type="button" class="secondary" data-action="open-saved" data-gtfs="' + esc(s.gtfs_route_id) + '" data-cls="' + esc(s.classification) + '">' + esc(t("common.open")) + "</button>" +
          '<button type="button" class="danger" data-action="del-saved" data-id="' + esc(s.id) + '">' + esc(t("common.remove")) + "</button></div></li>";
      }).join("") + "</ul>";
    });
  }

  async function renderRoutes(args, token) {
    if (args[0]) return renderRouteDetail(args[0], token);
    setView(
      '<section class="card"><h2>' + esc(t("routes.title")) + "</h2>" +
      '<p class="muted">' + esc(t("routes.intro", { year: state.year, cls: classLabel(state.classification) })) + "</p>" +
      segmentedClassification() +
      '<form id="routeSearch" class="toolbar" role="search" style="margin-top:12px">' +
      '<label class="field" style="flex:1 1 240px">' + esc(t("routes.search_label")) +
      '<input name="q" type="search" maxlength="80" autocomplete="off" placeholder="' + esc(t("routes.search_placeholder")) + '"></label>' +
      '<button type="submit">' + esc(t("common.search")) + "</button></form>" +
      '<div id="routeResults" style="margin-top:12px"></div></section>' +
      '<section class="card"><h2>' + esc(t("routes.saved_title")) + '</h2><div id="savedRoutes"></div></section>'
    );
    var routeQuery = takePendingQuery("routeSearch");
    await Promise.all([
      loadRouteResults(routeQuery, document.getElementById("routeResults"), token),
      loadSaved(document.getElementById("savedRoutes"), token),
    ]);
  }

  function directionHtml(direction) {
    var heading = direction.direction_id === null || direction.direction_id === undefined
      ? t("route.single_direction")
      : t("route.direction", { n: direction.direction_id });
    if (direction.headsign) heading += " " + t("route.towards", { headsign: direction.headsign });
    var rows = (direction.stops || []).map(function (s) {
      var stopName = s.stop_id !== null && s.stop_id !== undefined
        ? '<a href="#/stops/' + esc(encodeURIComponent(s.stop_id)) + '">' + esc(s.name) + "</a>" : esc(s.name);
      return '<tr><td class="num">' + esc(s.sequence) + "</td><td>" + stopName + "</td><td>" + esc(s.arrival || "") + "</td><td>" + esc(s.departure || "") + "</td></tr>";
    }).join("");
    return "<h3>" + esc(heading) + '</h3><div class="table-wrap" tabindex="0" role="region" aria-label="' + esc(t("common.table_scroll", { name: heading })) + '"><table><thead><tr>' +
      '<th class="num">' + esc(t("route.col_seq")) + "</th><th>" + esc(t("route.col_stop")) + "</th><th>" + esc(t("route.col_arrival")) + "</th><th>" + esc(t("route.col_departure")) + "</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  async function renderRouteDetail(routeId, token) {
    setView(loadingCard(t("route.loading")));
    var detail;
    try {
      detail = await api("/api/routes/" + encodeURIComponent(routeId));
    } catch (err) {
      if (token === state.viewToken) {
        var text = err.status === 404 ? t("route.cannot_open") : err.message;
        setView('<section class="card"><p><a href="#/routes">&larr; ' + esc(t("route.back")) + '</a></p><div class="banner error" role="alert">' + esc(text) + "</div></section>");
      }
      return;
    }
    if (token !== state.viewToken) return;
    state.route = detail;
    var title = (detail.short_name || detail.gtfs_route_id) + (detail.long_name ? " - " + detail.long_name : "");
    var directions = detail.directions && detail.directions.length
      ? detail.directions.map(directionHtml).join("")
      : '<div class="empty">' + esc(t("route.no_stops")) + "</div>";
    var days = (detail.operating_days || []).map(dayName).join(", ") || t("common.not_stated");
    setView(
      '<section class="card"><p><a href="#/routes">&larr; ' + esc(t("route.back")) + "</a></p>" +
      "<h2>" + esc(title) + "</h2><p>" + badge(detail.classification) + "</p>" +
      '<p class="muted">' + esc(t("route.operating_days", { days: days })) + "</p>" +
      '<p class="muted">' + esc(detail.geometry_note || "") + "</p>" +
      '<div id="routeMap" class="map" role="region" aria-label="' + esc(t("route.map_label")) + '"></div>' +
      '<div class="toolbar"><label class="field">' + esc(t("route.timetable_date")) +
      '<input type="date" id="ttDate" value="' + esc(defaultDate()) + '"></label>' +
      '<button type="button" data-action="tt-load" data-id="' + esc(detail.id) + '">' + esc(t("route.show_timetable")) + "</button>" +
      '<button type="button" class="secondary" data-action="tt-csv" data-id="' + esc(detail.id) + '">' + esc(t("common.download_csv")) + "</button>" +
      '<button type="button" class="secondary" data-action="save-route" data-gtfs="' + esc(detail.gtfs_route_id) + '" data-cls="' + esc(detail.classification) + '" data-label="' + esc(title) + '">' + esc(t("route.save")) + "</button></div>" +
      '<div id="timetable" style="margin-top:12px"></div></section>' +
      '<section class="card"><h2>' + esc(t("route.stops_title")) + "</h2>" + directions + "</section>"
    );
    drawRouteMap(detail);
    await loadTimetable(detail.id, token);
  }

  function drawRouteMap(detail) {
    var map = makeMap("routeMap");
    if (!map) return;
    var L = window.L;
    var bounds = [];
    (detail.shapes || []).forEach(function (shape) {
      if (shape.points && shape.points.length > 1) {
        L.polyline(shape.points, { color: "#0b5cad", weight: 4, opacity: 0.8 }).addTo(state.markers);
        shape.points.forEach(function (p) {
          bounds.push(p);
        });
      }
    });
    (detail.directions || []).forEach(function (direction, index) {
      (direction.stops || []).forEach(function (stop) {
        if (!validCoord(stop.lat, stop.lon)) return;
        var point = [stop.lat, stop.lon];
        bounds.push(point);
        L.circleMarker(point, { radius: index === 0 ? 5 : 4, color: index === 0 ? "#1b7f4c" : "#9a5b00", fillOpacity: 0.9 })
          .bindTooltip(esc(stop.name))
          .addTo(state.markers);
      });
    });
    // No animation: an animated zoom finishes on a timer, which could run after the visitor has left this page.
    if (bounds.length) map.fitBounds(L.latLngBounds(bounds), { padding: [18, 18], animate: false });
  }

  async function loadTimetable(routeId, token) {
    var box = document.getElementById("timetable");
    var input = document.getElementById("ttDate");
    if (!box || !input) return;
    var date = input.value;
    if (!isIsoDate(date)) {
      box.innerHTML = '<div class="banner error" role="alert">' + esc(t("common.bad_date")) + "</div>";
      return;
    }
    var seq = ++state.timetableToken;
    box.innerHTML = loadingInline(t("timetable.loading"));
    try {
      var data = await api("/api/routes/" + encodeURIComponent(routeId) + "/timetable?date=" + encodeURIComponent(date));
      if (token !== state.viewToken || seq !== state.timetableToken || !box.isConnected) return;
      box.innerHTML = timetableHtml(data, date);
    } catch (err) {
      if (token === state.viewToken && seq === state.timetableToken && box.isConnected) box.innerHTML = panelError(err, "rerender");
    }
  }

  function timetableHtml(data, date) {
    if (!data.covered || !data.trips || !data.trips.length) {
      var tone = data.classification === "OFFICIAL_VERIFIED" ? "official" : "unverified";
      var text = data.message_code ? messageFor(data.message_code, data.message) : data.message || t("timetable.none");
      return '<div class="banner ' + tone + '">' + esc(text) + "</div>";
    }
    var isToday = date === todayKey();
    var nowSecs = isToday ? nowSecondsInZone() : null;
    var afterMidnight = data.trips.some(function (trip) {
      var secs = gtfsSeconds(trip.first_departure);
      return secs !== null && secs >= 86400;
    });
    var markedNext = false;
    var rows = data.trips.slice(0, MAX_TRIPS_SHOWN).map(function (trip) {
      var secs = gtfsSeconds(trip.first_departure);
      var upcoming = nowSecs !== null && secs !== null && secs >= nowSecs;
      var mark = "";
      if (upcoming && !markedNext) {
        markedNext = true;
        mark = ' <span class="badge">' + esc(t("timetable.next")) + "</span>";
      }
      return "<tr" + (upcoming ? ' class="next"' : "") + "><td>" + esc(trip.trip_id) + mark + "</td><td>" + esc(trip.headsign || "") +
        "</td><td>" + esc(trip.first_departure || "") + "</td><td>" + esc(trip.last_arrival || "") +
        '</td><td class="num">' + esc(trip.stops ? trip.stops.length : 0) + "</td></tr>";
    }).join("");
    var summary = t("timetable.summary", {
      date: formatCalendarDate(date),
      count: fmtNum(data.trips.length),
      first: data.first_departure || t("common.na"),
      last: data.last_arrival || t("common.na"),
    });
    return '<p class="muted">' + esc(summary) + "</p>" +
      (isToday ? '<p class="muted">' + esc(t("timetable.hint_today", { zone: zoneName() })) + "</p>" : "") +
      (afterMidnight ? '<p class="muted">' + esc(t("timetable.after_midnight")) + "</p>" : "") +
      (data.trips.length > MAX_TRIPS_SHOWN ? '<p class="muted">' + esc(t("timetable.truncated", { max: MAX_TRIPS_SHOWN })) + "</p>" : "") +
      '<div class="table-wrap" tabindex="0" role="region" aria-label="' + esc(t("common.table_scroll", { name: t("table.timetable") })) + '"><table><thead><tr><th>' + esc(t("timetable.col_trip")) + "</th><th>" + esc(t("timetable.col_towards")) +
      "</th><th>" + esc(t("timetable.col_first")) + "</th><th>" + esc(t("timetable.col_last")) + '</th><th class="num">' + esc(t("timetable.col_stops")) +
      "</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  // ---------------------------------------------------------------- stops
  function stopItem(stop, distanceM) {
    var coords = validCoord(stop.lat, stop.lon) ? stop.lat.toFixed(5) + ", " + stop.lon.toFixed(5) : t("stops.no_coords");
    var away = typeof distanceM === "number" ? " - " + t("stops.away", { distance: t("unit.m", { n: fmtNum(Math.round(distanceM)) }) }) : "";
    return '<li><div><div class="title">' + esc(stop.name) + '</div><div class="muted">' + esc(coords + away) + "</div></div>" +
      '<div class="row-actions">' + badge(stop.classification) +
      '<a class="button secondary" href="#/stops/' + esc(encodeURIComponent(stop.id)) + '">' + esc(t("stops.departures")) + "</a></div></li>";
  }

  function stopListHtml(stops, withDistance) {
    if (!stops.length) return '<div class="empty">' + esc(t("stops.none")) + "</div>";
    return '<ul class="list">' + stops.map(function (s) {
      return stopItem(s, withDistance ? s.distance_m : undefined);
    }).join("") + "</ul>";
  }

  async function loadStops(query, token) {
    var seq = ++state.searchToken;
    await fillPanel(document.getElementById("stopResults"), token, async function () {
      var params = new URLSearchParams({ classification: state.classification, year: String(state.year), q: query, limit: "100" });
      var data = await api("/api/stops?" + params.toString());
      if (seq === state.searchToken && token === state.viewToken) plotStops(data.results, null);
      return stopListHtml(data.results, false) + (data.results.length ? "" : await otherClassificationHint("/api/stops", query));
    }, seq);
  }

  async function renderStops(args, token) {
    if (args[0]) return renderStopDetail(args[0], token);
    setView(
      '<section class="card"><h2>' + esc(t("stops.title")) + "</h2>" +
      '<p class="muted">' + esc(t("stops.intro")) + "</p>" +
      segmentedClassification() +
      '<form id="stopSearch" class="toolbar" role="search" style="margin-top:12px">' +
      '<label class="field" style="flex:1 1 240px">' + esc(t("stops.search_label")) +
      '<input name="q" type="search" maxlength="80" autocomplete="off" placeholder="' + esc(t("stops.search_placeholder")) + '"></label>' +
      '<button type="submit">' + esc(t("common.search")) + "</button>" +
      '<button type="button" class="secondary" data-action="nearby-me">' + esc(t("stops.nearby")) + "</button></form>" +
      '<div id="stopMap" class="map" role="region" aria-label="' + esc(t("stops.map_label")) + '"></div>' +
      '<div id="stopResults"></div></section>'
    );
    makeMap("stopMap");
    await loadStops(takePendingQuery("stopSearch"), token);
  }

  function plotStops(stops, here) {
    if (!state.map || !state.markers) return;
    var L = window.L;
    state.markers.clearLayers();
    var bounds = [];
    stops.forEach(function (stop) {
      if (!validCoord(stop.lat, stop.lon)) return;
      var point = [stop.lat, stop.lon];
      bounds.push(point);
      L.circleMarker(point, { radius: 5, color: "#0b5cad", fillOpacity: 0.85 }).bindTooltip(esc(stop.name)).addTo(state.markers);
    });
    if (here && validCoord(here.lat, here.lon)) {
      bounds.push([here.lat, here.lon]);
      L.circleMarker([here.lat, here.lon], { radius: 7, color: "#b3261e", fillOpacity: 0.9 })
        .bindTooltip(esc(t("stops.you_are_here")))
        .addTo(state.markers);
    }
    // No animation, for the same reason as in drawRouteMap.
    if (bounds.length) state.map.fitBounds(L.latLngBounds(bounds), { padding: [24, 24], maxZoom: 16, animate: false });
  }

  function nearbyStops() {
    var token = state.viewToken;
    if (!window.isSecureContext) {
      toast(t("msg.location_secure"));
      return;
    }
    if (!navigator.geolocation) {
      toast(t("stops.geo_unsupported"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (position) {
        findNearby(position.coords.latitude, position.coords.longitude, token);
      },
      function (error) {
        toast(error && error.code === 1 ? t("stops.geo_denied") : t("stops.geo_failed"));
      },
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 }
    );
  }

  async function findNearby(lat, lon, token) {
    var seq = ++state.searchToken;
    await fillPanel(document.getElementById("stopResults"), token, async function () {
      var params = new URLSearchParams({ lat: String(lat), lon: String(lon), radius_m: "800", classification: state.classification, limit: "50" });
      var data = await api("/api/stops/nearby?" + params.toString());
      if (seq === state.searchToken && token === state.viewToken) plotStops(data.results, { lat: lat, lon: lon });
      return '<p class="muted">' + esc(t("stops.within", { m: 800 })) + "</p>" + stopListHtml(data.results, true);
    }, seq);
  }

  async function renderStopDetail(stopId, token) {
    setView(loadingCard(t("stop.loading")));
    var data;
    try {
      data = await api("/api/stops/" + encodeURIComponent(stopId) + "/departures?classification=" + encodeURIComponent(state.classification) + "&limit=40");
    } catch (err) {
      if (token === state.viewToken) {
        var text = err.status === 404 ? t("stop.cannot_open") : err.message;
        setView('<section class="card"><p><a href="#/stops">&larr; ' + esc(t("stop.back")) + '</a></p><div class="banner error" role="alert">' + esc(text) + "</div></section>");
      }
      return;
    }
    if (token !== state.viewToken) return;
    var today = todayKey();
    var rows = data.departures.map(function (d) {
      var minutes = d.minutes_from_now === null || d.minutes_from_now === undefined
        ? ""
        : d.minutes_from_now === 0 ? t("time.now") : t("stop.in_minutes", { n: fmtNum(d.minutes_from_now) });
      var routeCell = esc(d.route_number || "") + (d.route_name ? '<div class="muted">' + esc(d.route_name) + "</div>" : "");
      return "<tr><td>" + esc(formatClockTime(d.departure_local)) + "</td><td>" + routeCell + "</td><td>" + esc(d.headsign || "") +
        "</td><td>" + esc(dayLabel(d.departure_local, today)) + "</td><td>" + esc(minutes) + "</td></tr>";
    }).join("");
    var body = data.departures.length
      ? '<div class="table-wrap" tabindex="0" role="region" aria-label="' + esc(t("common.table_scroll", { name: t("table.departures") })) + '" style="margin-top:12px"><table><thead><tr><th>' + esc(t("stop.col_time")) + "</th><th>" + esc(t("stop.col_route")) +
        "</th><th>" + esc(t("stop.col_towards")) + "</th><th>" + esc(t("stop.col_day")) + "</th><th>" + esc(t("journey.col_wait")) +
        "</th></tr></thead><tbody>" + rows + "</tbody></table></div>"
      : '<div class="empty" style="margin-top:12px">' + esc(messageFor(data.message_code, data.message)) + "</div>";
    setView(
      '<section class="card"><p><a href="#/stops">&larr; ' + esc(t("stop.back")) + "</a></p>" +
      "<h2>" + esc(t("stop.title", { name: data.stop.name })) + "</h2><p>" + badge(data.stop.classification) + "</p>" +
      '<p class="muted">' + esc(t("stop.intro", { zone: data.service_timezone })) + "</p>" +
      '<div class="toolbar"><button type="button" class="secondary" data-action="rerender">' + esc(t("common.refresh")) + "</button></div>" +
      body +
      '<p class="muted" style="margin-top:12px">' + esc(t("clock.scheduled_only")) + "</p></section>" +
      stopExtrasHtml(data.stop)
    );
    await fillPanel(document.getElementById("stopRoutes"), token, async function () {
      var routes = await api("/api/stops/" + encodeURIComponent(stopId) + "/routes?classification=" + encodeURIComponent(state.classification));
      if (!routes.routes.length) return '<div class="empty">' + esc(t("stop.routes_none")) + "</div>";
      return '<ul class="list">' + routes.routes.map(function (r) {
        var towards = r.towards.length ? '<div class="muted">' + esc(t("stop.towards_list", { places: r.towards.join(", ") })) + "</div>" : "";
        return '<li><div><div class="title"><span class="mode-tag">' + esc(t("mode." + modeOfType(r.route_type))) + "</span> " + esc(r.route_number || "") +
          (r.route_name ? " - " + esc(r.route_name) : "") + "</div>" + towards + "</div>" +
          '<div class="row-actions"><a class="button secondary" href="#/routes/' + esc(encodeURIComponent(r.id)) + '">' + esc(t("common.open")) + "</a></div></li>";
      }).join("") + "</ul>";
    });
  }

  var MODES = ["bus", "metro", "rail", "tram", "other"];
  function modeOfType(routeType) {
    var type = Number(routeType);
    if ([1, 400, 401, 402, 403, 404, 405].indexOf(type) !== -1) return "metro";
    if ([2, 100, 101, 102, 103, 106, 109].indexOf(type) !== -1) return "rail";
    if ([0, 900, 901, 902].indexOf(type) !== -1) return "tram";
    if (type === 3 || (type >= 700 && type <= 799)) return "bus";
    return "other";
  }

  function walkingDirectionsUrl(stop) {
    if (!validCoord(stop.lat, stop.lon)) return null;
    return "https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot&route=%3B" + stop.lat.toFixed(6) + "%2C" + stop.lon.toFixed(6);
  }

  function stopExtrasHtml(stop) {
    var saved = favouriteStops().some(function (f) {
      return f.gtfs === stop.gtfs_stop_id && f.cls === stop.classification;
    });
    var walk = walkingDirectionsUrl(stop);
    return '<section class="card"><h2>' + esc(t("stop.routes_title")) + '</h2><div id="stopRoutes"></div></section>' +
      '<section class="card"><div class="toolbar">' +
      (walk ? '<a class="button-link secondary" href="' + esc(walk) + '" target="_blank" rel="noopener noreferrer">' + esc(t("stop.walk")) + "</a>" : "") +
      (saved
        ? '<button type="button" class="secondary" data-action="unfav-stop" data-gtfs="' + esc(stop.gtfs_stop_id) + '" data-cls="' + esc(stop.classification) + '">' + esc(t("stop.unsave")) + "</button>"
        : '<button type="button" data-action="fav-stop" data-gtfs="' + esc(stop.gtfs_stop_id) + '" data-cls="' + esc(stop.classification) + '" data-name="' + esc(stop.name) + '">' + esc(t("stop.save")) + "</button>") +
      "</div>" + (walk ? '<p class="muted small">' + esc(t("stop.walk_note")) + "</p>" : "") + "</section>";
  }

  // ---------------------------------------------------------------- device-only lists: favourite stops, recent searches
  // Kept in this browser only (never sent to the server), so they work offline and need no account.
  function readList(key) {
    try {
      var value = JSON.parse(storage.get(PREFIX + key) || "[]");
      return Array.isArray(value) ? value : [];
    } catch (_) {
      return [];
    }
  }

  function favouriteStops() {
    return readList("favStops").filter(function (f) {
      return f && typeof f.gtfs === "string" && (f.cls === "OFFICIAL_VERIFIED" || f.cls === "UNVERIFIED_FEED");
    });
  }

  function setFavouriteStop(node, on) {
    var gtfs = node.getAttribute("data-gtfs");
    var cls = node.getAttribute("data-cls");
    var list = favouriteStops().filter(function (f) {
      return !(f.gtfs === gtfs && f.cls === cls);
    });
    if (on) list.unshift({ gtfs: gtfs, cls: cls, name: String(node.getAttribute("data-name") || gtfs).slice(0, 200) });
    storage.set(PREFIX + "favStops", JSON.stringify(list.slice(0, 50)));
    toast(t(on ? "stop.saved" : "stop.unsaved"));
    render();
  }

  // A saved stop is found again by its GTFS id, because internal ids change when a feed is re-imported.
  async function openFavouriteStop(node) {
    var gtfs = node.getAttribute("data-gtfs");
    var cls = node.getAttribute("data-cls");
    var data;
    try {
      data = await api("/api/stops?" + new URLSearchParams({ classification: cls, q: gtfs, limit: "100" }).toString());
    } catch (err) {
      fail(err);
      return;
    }
    var match = data.results.filter(function (stop) {
      return stop.gtfs_stop_id === gtfs;
    })[0];
    if (!match) {
      toast(t("fav.stop_gone"));
      return;
    }
    state.classification = cls;
    storage.set(PREFIX + "classification", cls);
    location.hash = "#/stops/" + encodeURIComponent(match.id);
  }

  function recentSearches() {
    return readList("recent").filter(function (r) {
      return r && (r.kind === "routes" || r.kind === "stops") && typeof r.q === "string" && r.q;
    });
  }

  function addRecent(kind, query) {
    if (!query) return;
    var list = recentSearches().filter(function (r) {
      return !(r.kind === kind && r.q.toLowerCase() === query.toLowerCase());
    });
    list.unshift({ kind: kind, q: query.slice(0, 80) });
    storage.set(PREFIX + "recent", JSON.stringify(list.slice(0, 8)));
  }

  function recentHtml() {
    var list = recentSearches();
    if (!list.length) return "";
    return '<div class="recent"><span class="recent-title">' + esc(t("recent.title")) + "</span>" + list.map(function (r) {
      return '<button type="button" class="chip-button" data-action="recent" data-kind="' + esc(r.kind) + '" data-q="' + esc(r.q) + '">' + esc(r.q) + "</button>";
    }).join("") + '<button type="button" class="link-button" data-action="recent-clear">' + esc(t("recent.clear")) + "</button></div>";
  }

  // ---------------------------------------------------------------- direct journeys
  // Leave-now is the default: it uses the server's current time in the service zone.
  // The planner: up to two changes, from /api/plan. Every time is scheduled; live positions are never shown.
  var LABEL_KEYS = {
    EARLIEST_ARRIVAL: "journey.label_earliest_arrival",
    FEWEST_CHANGES: "journey.label_fewest_changes",
    BUS_AND_METRO: "journey.label_bus_metro"
  };

  function renderJourney(args, token) {
    setView(
      '<section class="card"><h2>' + esc(t("journey.title")) + "</h2>" +
      '<p class="muted">' + esc(t("journey.intro")) + "</p>" +
      segmentedClassification() +
      '<form id="journeyForm" style="margin-top:12px">' +
      '<div class="form-grid">' +
      '<label class="field">' + esc(t("journey.from")) + '<input name="origin" required minlength="2" maxlength="80" autocomplete="off"></label>' +
      '<label class="field">' + esc(t("journey.to")) + '<input name="destination" required minlength="2" maxlength="80" autocomplete="off"></label>' +
      "</div>" +
      '<fieldset style="margin-top:12px"><legend>' + esc(t("journey.when")) + "</legend>" +
      '<div class="checks">' +
      '<label><input type="radio" name="when" value="now" checked> ' + esc(t("journey.now")) + "</label>" +
      '<label><input type="radio" name="when" value="date"> ' + esc(t("journey.on_date")) + "</label>" +
      "</div>" +
      '<label class="field" style="margin-top:8px">' + esc(t("journey.date")) +
      '<input name="date" type="date" value="' + esc(defaultDate()) + '" disabled></label>' +
      "</fieldset>" +
      '<fieldset style="margin-top:12px"><legend>' + esc(t("journey.changes_legend")) + "</legend>" +
      '<div class="checks">' +
      '<label><input type="radio" name="changes" value="0"> ' + esc(t("journey.changes_0")) + "</label>" +
      '<label><input type="radio" name="changes" value="1"> ' + esc(t("journey.changes_1")) + "</label>" +
      '<label><input type="radio" name="changes" value="2" checked> ' + esc(t("journey.changes_2")) + "</label>" +
      "</div></fieldset>" +
      '<fieldset style="margin-top:12px"><legend>' + esc(t("journey.modes_legend")) + "</legend>" +
      '<div class="checks">' +
      '<label><input type="radio" name="modes" value="all" checked> ' + esc(t("journey.modes_all")) + "</label>" +
      '<label><input type="radio" name="modes" value="bus"> ' + esc(t("journey.modes_bus")) + "</label>" +
      '<label><input type="radio" name="modes" value="metro"> ' + esc(t("journey.modes_metro")) + "</label>" +
      "</div></fieldset>" +
      '<div class="toolbar"><button type="submit">' + esc(t("journey.submit")) + "</button></div>" +
      "</form>" +
      '<div id="journeyResults" style="margin-top:12px" aria-live="polite"></div></section>'
    );
    var pending = state.pendingJourney;
    state.pendingJourney = null;
    var form = document.getElementById("journeyForm");
    if (pending && form) {
      form.elements.origin.value = pending.from;
      form.elements.destination.value = pending.to;
      var mode = form.querySelector('input[name="modes"][value="' + (JOURNEY_MODES.indexOf(pending.modes) !== -1 ? pending.modes : "all") + '"]');
      if (mode) mode.checked = true;
      submitJourney(form, token);
    }
  }

  async function submitJourney(form, token) {
    var box = document.getElementById("journeyResults");
    if (!box) return;
    var origin = String(form.elements.origin.value || "").trim();
    var destination = String(form.elements.destination.value || "").trim();
    var when = form.elements.when.value;
    if (origin.length < 2 || destination.length < 2) {
      box.innerHTML = '<div class="banner error" role="alert">' + esc(messageFor("NEED_BOTH_STOPS")) + "</div>";
      return;
    }
    var params = {
      origin: origin,
      destination: destination,
      classification: state.classification,
      max_changes: String(form.elements.changes.value || "2"),
      modes: ["all", "bus", "metro"].indexOf(form.elements.modes.value) !== -1 ? form.elements.modes.value : "all"
    };
    if (when === "date") {
      if (!isIsoDate(form.elements.date.value)) {
        box.innerHTML = '<div class="banner error" role="alert">' + esc(t("common.bad_date")) + "</div>";
        return;
      }
      params.date = form.elements.date.value;
    }
    var seq = ++state.searchToken;
    box.innerHTML = loadingInline(t("journey.searching"));
    try {
      var data = await api("/api/plan?" + new URLSearchParams(params).toString());
      if (seq !== state.searchToken || token !== state.viewToken || !box.isConnected) return;
      box.innerHTML = journeyHtml(data);
    } catch (err) {
      if (seq === state.searchToken && token === state.viewToken && box.isConnected) box.innerHTML = panelError(err, "rerender");
    }
  }

  function journeyHtml(data) {
    var zone = data.service_timezone || zoneName();
    var assumptions = data.assumptions || {};
    var note = data.mode === "date"
      ? t("journey.date_note", { date: formatCalendarDate(data.date), zone: zone })
      : t("journey.now_note", { zone: zone, hours: fmtNum((assumptions.now_window_minutes || 180) / 60) });
    var html = '<p class="notice" role="note">' + esc(t("journey.realtime_note")) + "</p>" +
      '<p class="muted">' + esc(note) + "</p>";
    if (data.match_note) html += '<p class="muted">' + esc(t("journey.match_limited")) + "</p>";
    if (!data.options || !data.options.length) {
      var text = data.message_code ? messageFor(data.message_code, data.message) : (data.message || t("journey.none"));
      return html + '<div class="empty" role="status">' + esc(text) + "</div>";
    }
    html += '<ol class="options" aria-label="' + esc(t("journey.options_label")) + '">' +
      data.options.map(function (option, index) { return optionHtml(option, index + 1); }).join("") + "</ol>";
    html += saveJourneyButton(data);
    html += sourcesHtml(data);
    html += '<p class="muted small">' + esc(t("journey.assumptions", {
      speed: fmtNum(assumptions.walk_speed_kmph),
      minutes: fmtNum(assumptions.min_change_minutes),
      metres: fmtNum(assumptions.max_walk_m)
    })) + "</p>";
    return html;
  }

  // ---------------------------------------------------------------- saved journeys (on this device only)
  var JOURNEY_MODES = ["all", "bus", "metro"];
  var JOURNEY_MODE_KEYS = { all: "journey.modes_all", bus: "journey.modes_bus", metro: "journey.modes_metro" };

  function savedJourneys() {
    return readList("favJourneys").filter(function (j) {
      return j && typeof j.from === "string" && j.from && typeof j.to === "string" && j.to &&
        JOURNEY_MODES.indexOf(j.modes) !== -1 && (j.cls === "OFFICIAL_VERIFIED" || j.cls === "UNVERIFIED_FEED");
    });
  }

  function sameJourney(a, b) {
    return a.from.toLowerCase() === b.from.toLowerCase() && a.to.toLowerCase() === b.to.toLowerCase() &&
      a.modes === b.modes && a.cls === b.cls;
  }

  function saveJourneyButton(data) {
    var journey = { from: String(data.origin_query || ""), to: String(data.destination_query || ""), modes: data.travel_modes || "all", cls: data.classification };
    var saved = savedJourneys().some(function (j) { return sameJourney(j, journey); });
    return '<div class="toolbar"><button type="button" class="secondary" data-action="save-journey"' +
      ' data-from="' + esc(journey.from) + '" data-to="' + esc(journey.to) + '" data-modes="' + esc(journey.modes) + '" data-cls="' + esc(journey.cls) + '"' +
      (saved ? " disabled" : "") + ">" + esc(t(saved ? "journey.saved" : "journey.save")) + "</button></div>";
  }

  function journeyFromNode(node) {
    return {
      from: String(node.getAttribute("data-from") || "").trim().slice(0, 80),
      to: String(node.getAttribute("data-to") || "").trim().slice(0, 80),
      modes: node.getAttribute("data-modes") || "all",
      cls: node.getAttribute("data-cls") || ""
    };
  }

  function setSavedJourney(node, on) {
    var journey = journeyFromNode(node);
    if (journey.from.length < 2 || journey.to.length < 2 || JOURNEY_MODES.indexOf(journey.modes) === -1 ||
        (journey.cls !== "OFFICIAL_VERIFIED" && journey.cls !== "UNVERIFIED_FEED")) return;
    var list = savedJourneys().filter(function (j) { return !sameJourney(j, journey); });
    if (on) list.unshift(journey);
    storage.set(PREFIX + "favJourneys", JSON.stringify(list.slice(0, 20)));
    toast(t(on ? "journey.saved" : "journey.unsaved"));
    if (on) {
      node.disabled = true;
      node.textContent = t("journey.saved");
    } else {
      render();
    }
  }

  function planSavedJourney(node) {
    var journey = journeyFromNode(node);
    state.pendingJourney = journey;
    if (journey.cls === "OFFICIAL_VERIFIED" || journey.cls === "UNVERIFIED_FEED") {
      state.classification = journey.cls;
      storage.set(PREFIX + "classification", journey.cls);
    }
    if (location.hash === "#/journey") render();
    else location.hash = "#/journey";
  }

  function savedJourneysHtml() {
    var list = savedJourneys();
    if (!list.length) return '<div class="empty">' + esc(t("fav.journeys_none")) + "</div>";
    return '<ul class="list">' + list.map(function (j) {
      var attrs = ' data-from="' + esc(j.from) + '" data-to="' + esc(j.to) + '" data-modes="' + esc(j.modes) + '" data-cls="' + esc(j.cls) + '"';
      return '<li><div><div class="title">' + esc(t("fav.journey_name", { from: j.from, to: j.to })) + "</div>" +
        '<div class="muted">' + esc(t(JOURNEY_MODE_KEYS[j.modes])) + "</div></div>" +
        '<div class="row-actions">' + badge(j.cls) +
        '<button type="button" class="secondary" data-action="plan-fav-journey"' + attrs + ">" + esc(t("fav.plan_again")) + "</button>" +
        '<button type="button" class="danger" data-action="unfav-journey"' + attrs + ">" + esc(t("common.remove")) + "</button></div></li>";
    }).join("") + "</ul>";
  }

  function optionHtml(option, number) {
    var labels = (option.labels || []).map(function (label) {
      var key = LABEL_KEYS[label];
      return key ? '<span class="badge neutral">' + esc(t(key)) + "</span> " : "";
    }).join("");
    var changes = option.changes === 0 ? t("journey.changes_none")
      : option.changes === 1 ? t("journey.changes_one")
      : t("journey.changes_many", { n: fmtNum(option.changes) });
    var wait = option.wait_minutes > 0
      ? "<li>" + esc(t("journey.wait", { n: fmtNum(option.wait_minutes) })) + "</li>" : "";
    return '<li class="option">' +
      '<h3 class="option-title">' + esc(t("journey.option", { n: fmtNum(number) })) + " " + labels + "</h3>" +
      '<p class="option-summary">' + esc(t("journey.summary", {
        dep: formatClockTime(option.departs_at),
        arr: formatClockTime(option.arrives_at),
        minutes: fmtNum(option.duration_minutes)
      })) + " · " + esc(changes) + "</p>" +
      '<ul class="option-meta">' + wait + "<li>" + esc(fareText(option.fare, option.legs)) + "</li></ul>" +
      '<ol class="legs" aria-label="' + esc(t("journey.legs_label")) + '">' +
      (option.legs || []).map(legHtml).join("") + "</ol></li>";
  }

  // Fares come only from unrestricted fare rules in the feed. A journey with changes is never given one total.
  function fareText(fare, legs) {
    var rides = (legs || []).filter(function (leg) { return leg.type === "ride"; });
    if (!fare) return t("journey.fare_not_in_feed");
    if (fare.code === "IN_FEED" && fare.total) {
      var paid = rides.length && rides[0].fares.length ? payText(rides[0].fares[0].payment) : "";
      return t("journey.fare_in_feed", { price: fare.total.price, currency: fare.total.currency }) + (paid ? " " + paid : "");
    }
    if (fare.code === "SEVERAL_IN_FEED") {
      var list = rides.length ? rides[0].fares.map(function (item) { return item.price + " " + item.currency; }).join(", ") : "";
      return t("journey.fare_several", { list: list });
    }
    if (fare.code === "CHANGES_NOT_PRICED") return t("journey.fare_changes");
    return t("journey.fare_not_in_feed");
  }

  function payText(payment) {
    return payment === "ON_BOARD" ? t("journey.pay_on_board") : t("journey.pay_before_boarding");
  }

  function legHtml(leg) {
    if (leg.type === "walk") {
      return '<li class="leg walk"><span class="leg-title">' +
        esc(t("journey.leg_walk", { to: leg.to.name, metres: fmtNum(leg.distance_m) })) + "</span> " +
        '<span class="muted">' + esc(t("journey.leg_walk_time", { minutes: fmtNum(leg.duration_minutes) })) + "</span></li>";
    }
    var towards = leg.headsign ? ' <span class="muted">' + esc(t("journey.leg_towards", { headsign: leg.headsign })) + "</span>" : "";
    var mode = MODES.indexOf(leg.mode) !== -1 ? leg.mode : "other";
    return '<li class="leg ride mode-' + mode + '"><span class="mode-tag">' + esc(t("mode." + mode)) + "</span> " + '<span class="leg-title">' +
      esc(t("journey.leg_ride", { route: leg.route_number || "", from: leg.from.name, to: leg.to.name })) + "</span>" + towards + "<br>" +
      '<span class="muted">' + esc(t("journey.leg_times", {
        dep: formatClockTime(leg.departs_at),
        arr: formatClockTime(leg.arrives_at),
        minutes: fmtNum(leg.duration_minutes)
      })) + "</span> " + badge(leg.source.classification) +
      ' <span class="muted">' + esc(leg.source.name) + "</span></li>";
  }

  function sourcesHtml(data) {
    if (!data.sources || !data.sources.length) return "";
    return '<h3 class="sources-title">' + esc(t("journey.sources_title")) + "</h3>" +
      '<ul class="plain">' + data.sources.map(function (source) {
        return "<li>" + badge(data.classification) + " " + esc(source.name) +
          (source.publisher ? ' <span class="muted">' + esc(source.publisher) + "</span>" : "") + "</li>";
      }).join("") + "</ul>";
  }

  // ---------------------------------------------------------------- future scenarios (estimates only)
  async function renderScenarios(args, token) {
    state.scenarioEditId = null;
    state.scenarioStops = [];
    var yearOptions = PLANNING_YEARS.map(function (y) {
      return '<option value="' + y + '">' + y + "</option>";
    }).join("");
    setView(
      '<section class="card"><div class="banner scenario"><strong>' + badge("ESTIMATED_SCENARIO") + " " + esc(t("scn.permanent")) + "</strong>" +
      esc(t("scn.notice")) + "</div>" +
      '<p class="muted" style="margin-top:10px">' + esc(t("scn.device_note")) + "</p>" +
      '<div class="toolbar"><label class="field">' + esc(t("scn.year_filter")) +
      '<select id="scnYearFilter"><option value="">' + esc(t("scn.all_years")) + "</option>" + yearOptions + "</select></label>" +
      '<button type="button" data-action="scn-new">' + esc(t("scn.new")) + "</button>" +
      '<button type="button" class="secondary" data-action="scn-csv">' + esc(t("scn.export_csv")) + "</button></div></section>" +
      '<section id="scnForm" class="card" hidden></section>' +
      '<section class="card"><h2>' + esc(t("scn.list_title")) + '</h2><div id="scnList"></div></section>'
    );
    await loadScenarioList(document.getElementById("scnList"), token);
  }

  function scenarioItem(s) {
    var e = s.estimate || {};
    var days = (s.operating_days || []).map(dayName).join(" ");
    var departures = e.departures_per_day === null || e.departures_per_day === undefined ? t("common.na") : fmtNum(e.departures_per_day);
    var distance = e.estimated_distance_km === null || e.estimated_distance_km === undefined ? t("common.na") : t("unit.km", { n: fmtNum(e.estimated_distance_km) });
    var minutes = e.estimated_journey_minutes === null || e.estimated_journey_minutes === undefined ? t("common.na") : t("unit.min", { n: fmtNum(e.estimated_journey_minutes) });
    return '<li><div><div class="title">' + esc(s.name) + "</div>" +
      '<div class="muted">' + esc(t("scn.meta", { year: s.year, code: s.route_code })) + "</div>" +
      '<div class="muted">' + esc(t("scn.trip", {
        origin: s.origin.name, destination: s.destination.name, first: s.first_departure,
        last: s.last_departure, frequency: s.frequency_minutes, days: days,
      })) + "</div>" +
      '<div class="muted">' + esc(t("scn.estimate", { departures: departures, distance: distance, minutes: minutes })) + "</div></div>" +
      '<div class="row-actions">' + badge("ESTIMATED_SCENARIO") +
      '<button type="button" class="secondary" data-action="scn-edit" data-id="' + esc(s.id) + '">' + esc(t("common.edit")) + "</button>" +
      '<button type="button" class="secondary" data-action="scn-pdf" data-id="' + esc(s.id) + '">' + esc(t("common.pdf")) + "</button>" +
      '<button type="button" class="danger" data-action="scn-del" data-id="' + esc(s.id) + '">' + esc(t("common.delete")) + "</button></div></li>";
  }

  async function loadScenarioList(panel, token) {
    var filter = document.getElementById("scnYearFilter");
    var year = filter ? filter.value : "";
    await fillPanel(panel, token, async function () {
      var data = await api("/api/scenarios" + (year ? "?year=" + encodeURIComponent(year) : ""));
      if (!data.scenarios.length) return '<div class="empty">' + esc(t("scn.none")) + "</div>";
      return '<ul class="list">' + data.scenarios.map(scenarioItem).join("") + "</ul>";
    });
  }

  function scenarioFormHtml(s) {
    var v = s || {};
    var origin = v.origin || {};
    var destination = v.destination || {};
    var days = v.operating_days || ["MON", "TUE", "WED", "THU", "FRI"];
    var yearOptions = PLANNING_YEARS.map(function (y) {
      var selected = Number(v.year || state.year) === y ? " selected" : "";
      return '<option value="' + y + '"' + selected + ">" + y + "</option>";
    }).join("");
    var dayBoxes = DAYS.map(function (d) {
      var checked = days.indexOf(d) !== -1 ? " checked" : "";
      return '<label><input type="checkbox" name="days" value="' + d + '"' + checked + "> " + esc(dayName(d)) + "</label>";
    }).join("");
    function coord(value) {
      return value === null || value === undefined ? "" : String(value);
    }
    return "<h2>" + esc(t(s ? "scn.form_edit" : "scn.form_new")) + "</h2>" +
      '<p class="muted">' + esc(t("scn.form_help")) + "</p>" +
      '<form id="scenarioForm">' +
      '<div class="form-grid">' +
      '<label class="field">' + esc(t("scn.name")) + '<input name="name" maxlength="120" required value="' + esc(v.name || "") + '"></label>' +
      '<label class="field">' + esc(t("scn.year")) + '<select name="year">' + yearOptions + "</select></label>" +
      '<label class="field">' + esc(t("scn.route_code")) + '<input name="route_code" maxlength="20" required pattern="[A-Za-z0-9][A-Za-z0-9\\-_ ]*" value="' + esc(v.route_code || "") +
      '" placeholder="' + esc(t("scn.route_code_hint")) + '"></label>' +
      '<label class="field">' + esc(t("scn.frequency")) + '<input name="frequency_minutes" type="number" min="1" max="240" required value="' + esc(v.frequency_minutes || 15) + '"></label>' +
      '<label class="field">' + esc(t("scn.first")) + '<input name="first_departure" type="time" required value="' + esc(v.first_departure || "06:00") + '"></label>' +
      '<label class="field">' + esc(t("scn.last")) + '<input name="last_departure" type="time" required value="' + esc(v.last_departure || "22:00") + '"></label>' +
      "</div>" +
      "<fieldset><legend>" + esc(t("scn.od")) + "</legend>" +
      '<div class="form-grid">' +
      '<label class="field">' + esc(t("scn.origin_name")) + '<input name="origin_name" maxlength="200" required value="' + esc(origin.name || "") + '"></label>' +
      '<label class="field">' + esc(t("scn.origin_lat")) + '<input name="origin_lat" type="number" step="any" min="-90" max="90" value="' + esc(coord(origin.lat)) + '"></label>' +
      '<label class="field">' + esc(t("scn.origin_lon")) + '<input name="origin_lon" type="number" step="any" min="-180" max="180" value="' + esc(coord(origin.lon)) + '"></label>' +
      '<label class="field">' + esc(t("scn.dest_name")) + '<input name="destination_name" maxlength="200" required value="' + esc(destination.name || "") + '"></label>' +
      '<label class="field">' + esc(t("scn.dest_lat")) + '<input name="destination_lat" type="number" step="any" min="-90" max="90" value="' + esc(coord(destination.lat)) + '"></label>' +
      '<label class="field">' + esc(t("scn.dest_lon")) + '<input name="destination_lon" type="number" step="any" min="-180" max="180" value="' + esc(coord(destination.lon)) + '"></label>' +
      "</div></fieldset>" +
      "<fieldset><legend>" + esc(t("scn.days")) + '</legend><div class="checks">' + dayBoxes + "</div></fieldset>" +
      "<h3>" + esc(t("scn.stops_title", { max: MAX_SCENARIO_STOPS })) + "</h3>" +
      '<div id="scnStops"></div>' +
      '<div class="toolbar"><button type="button" class="secondary" data-action="scn-add-stop">' + esc(t("scn.add_stop")) + "</button></div>" +
      '<label class="field" style="margin-top:12px">' + esc(t("scn.notes")) + '<textarea name="description" maxlength="1000">' + esc(v.description || "") + "</textarea></label>" +
      '<div class="toolbar" style="margin-top:14px"><button type="submit">' + esc(t(s ? "scn.save_changes" : "scn.create")) + "</button>" +
      '<button type="button" class="secondary" data-action="scn-cancel">' + esc(t("common.cancel")) + "</button></div>" +
      '<div id="scnError" class="banner error" role="alert" hidden></div>' +
      "</form>";
  }

  function renderScenarioStops() {
    var box = document.getElementById("scnStops");
    if (!box) return;
    if (!state.scenarioStops.length) {
      box.innerHTML = '<p class="muted">' + esc(t("scn.stops_none")) + "</p>";
      return;
    }
    box.innerHTML = '<div class="form-grid">' + state.scenarioStops.map(function (stop, i) {
      var lat = stop.lat === null || stop.lat === undefined ? "" : String(stop.lat);
      var lon = stop.lon === null || stop.lon === undefined ? "" : String(stop.lon);
      return '<div class="card" style="margin:0">' +
        '<label class="field">' + esc(t("scn.stop_name", { n: i + 1 })) + '<input data-stop="' + i + '" data-field="name" maxlength="200" value="' + esc(stop.name || "") + '"></label>' +
        '<div class="form-grid" style="margin-top:8px">' +
        '<label class="field">' + esc(t("scn.lat")) + '<input data-stop="' + i + '" data-field="lat" type="number" step="any" min="-90" max="90" value="' + esc(lat) + '"></label>' +
        '<label class="field">' + esc(t("scn.lon")) + '<input data-stop="' + i + '" data-field="lon" type="number" step="any" min="-180" max="180" value="' + esc(lon) + '"></label>' +
        "</div>" +
        '<button type="button" class="danger" data-action="scn-remove-stop" data-index="' + i + '" style="margin-top:8px">' + esc(t("scn.remove_stop")) + "</button></div>";
    }).join("") + "</div>";
  }

  // Copies what the user has typed in the stop inputs back into state before the list changes.
  function syncStopsFromDom() {
    var inputs = document.querySelectorAll("#scnStops [data-stop]");
    if (!inputs.length) return;
    var stops = state.scenarioStops.map(function (stop) {
      return Object.assign({}, stop);
    });
    inputs.forEach(function (input) {
      var index = Number(input.getAttribute("data-stop"));
      var field = input.getAttribute("data-field");
      if (!stops[index]) return;
      var raw = input.value.trim();
      if (field === "name") stops[index].name = raw;
      else stops[index][field] = raw === "" ? null : Number(raw);
    });
    state.scenarioStops = stops;
  }

  async function openScenarioForm(id, token) {
    var box = document.getElementById("scnForm");
    if (!box) return;
    var scenario = null;
    if (id) {
      try {
        scenario = await api("/api/scenarios/" + encodeURIComponent(id));
      } catch (err) {
        toast(err.message);
        return;
      }
      if (token !== state.viewToken) return;
    }
    state.scenarioEditId = id || null;
    state.scenarioStops = scenario
      ? scenario.stops.map(function (s) {
        return { name: s.name, lat: s.lat, lon: s.lon };
      })
      : [];
    box.innerHTML = scenarioFormHtml(scenario);
    box.hidden = false;
    renderScenarioStops();
    var calmer = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    box.scrollIntoView({ behavior: calmer ? "auto" : "smooth", block: "start" });
  }

  function readScenarioForm(form) {
    syncStopsFromDom();
    var f = new FormData(form);
    var number = function (key) {
      var raw = String(f.get(key) || "").trim();
      return raw === "" ? null : Number(raw);
    };
    return {
      name: String(f.get("name") || "").trim(),
      year: Number(f.get("year")),
      route_code: String(f.get("route_code") || "").trim(),
      description: String(f.get("description") || "").trim() || null,
      origin_name: String(f.get("origin_name") || "").trim(),
      origin_lat: number("origin_lat"),
      origin_lon: number("origin_lon"),
      destination_name: String(f.get("destination_name") || "").trim(),
      destination_lat: number("destination_lat"),
      destination_lon: number("destination_lon"),
      first_departure: String(f.get("first_departure") || ""),
      last_departure: String(f.get("last_departure") || ""),
      frequency_minutes: Number(f.get("frequency_minutes")),
      operating_days: f.getAll("days"),
      stops: state.scenarioStops
        .filter(function (stop) {
          return stop.name && String(stop.name).trim();
        })
        .map(function (stop) {
          return {
            name: String(stop.name).trim(),
            lat: stop.lat === undefined ? null : stop.lat,
            lon: stop.lon === undefined ? null : stop.lon,
          };
        }),
    };
  }

  function isBlankValue(value) {
    return value === null || value === undefined || value === "";
  }

  // The rules the server also enforces are checked here first, so the message is in the person's language.
  function scenarioProblem(body) {
    if (body.first_departure && body.last_departure && body.last_departure < body.first_departure) return "scn.err_times";
    if (!body.operating_days.length) return "scn.err_days";
    if (isBlankValue(body.origin_lat) !== isBlankValue(body.origin_lon)) return "scn.err_pair";
    if (isBlankValue(body.destination_lat) !== isBlankValue(body.destination_lon)) return "scn.err_pair";
    for (var i = 0; i < state.scenarioStops.length; i += 1) {
      var stop = state.scenarioStops[i];
      var named = !!(stop.name && String(stop.name).trim());
      var latGiven = !isBlankValue(stop.lat);
      var lonGiven = !isBlankValue(stop.lon);
      if (!named && !latGiven && !lonGiven) continue;
      if (!named) return "scn.err_stop_name";
      if (latGiven !== lonGiven) return "scn.err_pair";
    }
    return null;
  }

  async function submitScenario(form, token) {
    var errorBox = document.getElementById("scnError");
    if (!errorBox) return;
    errorBox.hidden = true;
    var body = readScenarioForm(form);
    var problem = scenarioProblem(body);
    if (problem) {
      errorBox.textContent = t(problem);
      errorBox.hidden = false;
      return;
    }
    busy(form, true);
    try {
      var result = state.scenarioEditId
        ? await api("/api/scenarios/" + encodeURIComponent(state.scenarioEditId), { method: "PUT", json: body })
        : await api("/api/scenarios", { method: "POST", json: body });
      if (token !== state.viewToken) return;
      closeScenarioForm();
      toast(result.warnings && result.warnings.length ? t("scn.saved") + " " + result.warnings.join(" ") : t("scn.saved"));
      await loadScenarioList(document.getElementById("scnList"), token);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
    } finally {
      busy(form, false);
    }
  }

  // ---------------------------------------------------------------- compare
  // Values from the estimate: text is formatted with the locale; a missing value is shown as n/a.
  function estimateText(value, unitKey) {
    if (value === null || value === undefined) return esc(t("common.na"));
    return esc(unitKey ? t(unitKey, { n: fmtNum(value) }) : fmtNum(value));
  }

  async function renderCompare(args, token) {
    setView(
      '<section class="card"><div class="banner scenario"><strong>' + badge("ESTIMATED_SCENARIO") + "</strong>" + esc(t("scn.notice")) + "</div>" +
      '<h2 style="margin-top:12px">' + esc(t("cmp.title")) + "</h2>" +
      '<div class="toolbar">' +
      '<label class="field">' + esc(t("cmp.a")) + '<select id="cmpA"></select></label>' +
      '<label class="field">' + esc(t("cmp.b")) + '<select id="cmpB"></select></label>' +
      '<button type="button" data-action="cmp-run">' + esc(t("cmp.run")) + "</button>" +
      '<button type="button" class="secondary" data-action="cmp-pdf">' + esc(t("cmp.pdf")) + "</button></div>" +
      '<div id="cmpResult" style="margin-top:12px"></div></section>' +
      '<section class="card"><h2>' + esc(t("cmp.years_title")) + '</h2><div id="yearsCompare"></div></section>'
    );
    await Promise.all([
      loadScenarioOptions(token),
      loadYearsCompare(document.getElementById("yearsCompare"), token),
    ]);
  }

  async function loadScenarioOptions(token) {
    var result = document.getElementById("cmpResult");
    try {
      var data = await api("/api/scenarios");
      var a = document.getElementById("cmpA");
      var b = document.getElementById("cmpB");
      if (token !== state.viewToken || !a || !b) return;
      var options = data.scenarios.map(function (s) {
        return '<option value="' + esc(s.id) + '">' + esc(s.name) + " (" + esc(s.year) + ")</option>";
      }).join("");
      a.innerHTML = options;
      b.innerHTML = options;
      if (data.scenarios.length < 2) result.innerHTML = '<div class="empty">' + esc(t("cmp.need_two")) + "</div>";
    } catch (err) {
      if (token === state.viewToken && result) result.innerHTML = panelError(err, "rerender");
    }
  }

  async function loadYearsCompare(panel, token) {
    await fillPanel(panel, token, async function () {
      var data = await api("/api/years/compare");
      function cell(cov) {
        return badge(cov.classification) + '<div class="muted">' + esc(cov.message) + "</div>";
      }
      var rows = data.years.map(function (y) {
        return "<tr><td><strong>" + esc(y.year) + "</strong></td><td>" + cell(y.official) + "</td><td>" + cell(y.unverified) +
          '</td><td class="num">' + esc(fmtNum(y.your_scenarios)) + "</td></tr>";
      }).join("");
      return '<div class="table-wrap" tabindex="0" role="region" aria-label="' + esc(t("common.table_scroll", { name: t("table.years") })) + '"><table><thead><tr><th>' + esc(t("cmp.col_year")) + "</th><th>" + esc(t("cmp.col_official")) +
        "</th><th>" + esc(t("cmp.col_unverified")) + '</th><th class="num">' + esc(t("cmp.col_yours")) + "</th></tr></thead><tbody>" +
        rows + "</tbody></table></div>";
    });
  }

  async function runComparison(token) {
    var a = document.getElementById("cmpA");
    var b = document.getElementById("cmpB");
    var result = document.getElementById("cmpResult");
    if (!a || !b || !result) return;
    if (!a.value || !b.value) {
      toast(t("cmp.choose_two"));
      return;
    }
    result.innerHTML = loadingInline();
    try {
      var data = await api("/api/scenarios/compare?a=" + encodeURIComponent(a.value) + "&b=" + encodeURIComponent(b.value));
      if (token !== state.viewToken) return;
      var row = function (label, key, unitKey) {
        return "<tr><td>" + esc(label) + '</td><td class="num">' + estimateText(data.a.estimate[key], unitKey) +
          '</td><td class="num">' + estimateText(data.b.estimate[key], unitKey) +
          '</td><td class="num">' + estimateText(data.difference_b_minus_a[key], unitKey) + "</td></tr>";
      };
      result.innerHTML = '<div class="table-wrap" tabindex="0" role="region" aria-label="' + esc(t("common.table_scroll", { name: t("table.comparison") })) + '"><table><thead><tr><th>' + esc(t("cmp.col_estimate")) + '</th><th class="num">' +
        esc(data.a.scenario.name) + '</th><th class="num">' + esc(data.b.scenario.name) + '</th><th class="num">' + esc(t("cmp.col_diff")) +
        "</th></tr></thead><tbody>" +
        row(t("cmp.row_distance"), "estimated_distance_km", "unit.km") +
        row(t("cmp.row_time"), "estimated_journey_minutes", "unit.min") +
        row(t("cmp.row_day"), "departures_per_day", null) +
        row(t("cmp.row_week"), "departures_per_week", null) +
        "</tbody></table></div>" +
        '<p class="muted">' + esc(t("scn.notice")) + "</p>";
    } catch (err) {
      if (token === state.viewToken) result.innerHTML = panelError(err, "rerender");
    }
  }

  async function comparisonPdf() {
    var a = document.getElementById("cmpA");
    var b = document.getElementById("cmpB");
    if (!a || !b || !a.value || !b.value) {
      toast(t("cmp.choose_two"));
      return;
    }
    await download("/api/scenarios/compare.pdf?a=" + encodeURIComponent(a.value) + "&b=" + encodeURIComponent(b.value), "estimated_scenario_comparison.pdf");
  }

  // ---------------------------------------------------------------- data sources (public)
  function sourceItem(s) {
    var href = safeHref(s.source_url);
    var link = href
      ? '<a href="' + esc(href) + '" rel="noopener noreferrer" target="_blank">' + esc(s.source_url) + "</a>"
      : esc(t("src.no_link"));
    var status = s.verified
      ? (s.verified_at ? t("src.verified_on", { date: String(s.verified_at).slice(0, 10) }) : t("admin.verified") + ".")
      : t("src.not_verified");
    return '<li><div><div class="title">' + esc(s.name) + "</div>" +
      '<div class="muted">' + esc(t("src.publisher")) + ": " + esc(s.publisher) + " - " + esc(t("src.licence")) + ": " + esc(s.license) +
      " - " + esc(t("src.kind")) + ": " + esc(s.kind) + "</div>" +
      '<div class="muted">' + link + "</div>" +
      '<div class="muted">' + esc(status) + " " + esc(t("src.imports", { count: fmtNum(s.completed_imports) })) + "</div></div>" +
      '<div class="row-actions">' + badge(s.classification) + "</div></li>";
  }

  async function renderSources(args, token) {
    setView(
      '<section class="card"><h2>' + esc(t("src.title")) + "</h2>" +
      '<dl class="kv">' +
      "<dt>" + badge("OFFICIAL_VERIFIED") + "</dt><dd>" + esc(t("cls.explain.OFFICIAL_VERIFIED")) + "</dd>" +
      "<dt>" + badge("UNVERIFIED_FEED") + "</dt><dd>" + esc(t("cls.explain.UNVERIFIED_FEED")) + "</dd>" +
      "<dt>" + badge("ESTIMATED_SCENARIO") + "</dt><dd>" + esc(t("cls.explain.ESTIMATED_SCENARIO")) + "</dd>" +
      "</dl>" +
      "<h3>" + esc(t("src.in_use")) + "</h3>" +
      '<div id="sourceList"></div></section>' +
      '<section class="card"><h2>' + esc(t("src.not_used_title")) + "</h2>" +
      '<p class="muted">' + esc(t("src.not_used")) + "</p></section>"
    );
    await fillPanel(document.getElementById("sourceList"), token, async function () {
      var data = await api("/api/data-sources");
      if (!data.sources.length) return '<div class="empty">' + esc(t("src.none")) + "</div>";
      return '<ul class="list">' + data.sources.map(sourceItem).join("") + "</ul>";
    });
  }

  // ---------------------------------------------------------------- administration
  // The admin key lives only in this page's memory: it is never written to browser storage.
  async function renderAdmin(args, token) {
    var meta;
    try {
      meta = await api("/api/meta");
    } catch (err) {
      if (token === state.viewToken) setView(panelError(err, "rerender"));
      return;
    }
    if (token !== state.viewToken) return;
    if (!meta.admin_enabled) {
      setView('<section class="card"><h2>' + esc(t("admin.title")) + '</h2><div class="banner error" role="alert">' + esc(t("admin.disabled")) + "</div></section>");
      return;
    }
    setView(
      '<section class="card"><h2>' + esc(t("admin.sign_in")) + "</h2>" +
      '<p class="muted">' + esc(t("admin.key_note")) + "</p>" +
      '<form id="adminKeyForm" class="toolbar" autocomplete="off">' +
      '<label class="field" style="flex:1 1 260px">' + esc(t("admin.key_label")) +
      '<input name="key" type="password" autocomplete="new-password" spellcheck="false"></label>' +
      '<button type="submit">' + esc(t("admin.key_save")) + "</button>" +
      '<button type="button" class="secondary" data-action="admin-key-clear">' + esc(t("admin.key_forget")) + "</button></form></section>" +
      '<div id="adminBody"></div>'
    );
    if (state.adminKey) {
      await loadAdmin(token);
    } else {
      document.getElementById("adminBody").innerHTML = '<div class="empty">' + esc(t("admin.key_needed")) + "</div>";
    }
  }

  async function loadAdmin(token) {
    var body = document.getElementById("adminBody");
    if (!body) return;
    body.innerHTML =
      '<div id="adminNotice" role="alert"></div>' +
      '<section class="card"><h2>' + esc(t("admin.sources")) + '</h2><div id="adminSources">' + loadingInline() + "</div>" +
      '<form id="sourceDecisionForm" class="form-grid" hidden aria-labelledby="decisionQuestion">' +
      '<label class="field"><span id="decisionQuestion"></span><input name="note" required maxlength="500" autocomplete="off"></label>' +
      '<input type="hidden" name="source_id"><input type="hidden" name="verified">' +
      '<div class="row-actions" style="align-self:end"><button type="submit" id="decisionSubmit"></button>' +
      '<button type="button" class="secondary" data-action="decision-cancel">' + esc(t("common.cancel")) + "</button></div></form>" +
      "<h3>" + esc(t("admin.add_source")) + "</h3>" +
      '<form id="sourceForm" class="form-grid">' +
      '<label class="field">' + esc(t("admin.src_name")) + '<input name="name" required maxlength="200"></label>' +
      '<label class="field">' + esc(t("admin.src_publisher")) + '<input name="publisher" required maxlength="200"></label>' +
      '<label class="field">' + esc(t("admin.src_url")) + '<input name="source_url" type="url" maxlength="500" pattern="https?://\\S+" placeholder="https://"></label>' +
      '<label class="field">' + esc(t("admin.src_license")) + '<input name="license" maxlength="200" placeholder="' + esc(t("common.not_specified")) + '"></label>' +
      '<label class="field">' + esc(t("admin.src_kind")) + '<select name="kind">' +
      '<option value="OFFICIAL">OFFICIAL</option><option value="COMMUNITY">COMMUNITY</option>' +
      '<option value="SYNTHETIC_DEMO">SYNTHETIC_DEMO</option><option value="UNKNOWN" selected>UNKNOWN</option></select></label>' +
      '<div style="align-self:end"><button type="submit">' + esc(t("admin.src_add")) + "</button></div></form></section>" +
      '<section class="card"><h2>' + esc(t("admin.upcoming_title")) + "</h2>" +
      '<p class="muted">' + esc(t("admin.upcoming_help")) + "</p>" +
      '<form id="upcomingForm" class="form-grid">' +
      '<label class="field">' + esc(t("admin.upcoming_entry")) + '<select name="entry" id="upcomingEntry"></select></label>' +
      '<label class="field">' + esc(t("admin.upcoming_id")) + '<input name="entry_id" maxlength="60" pattern="[a-z0-9_]{2,60}" autocomplete="off"></label>' +
      '<label class="field">' + esc(t("admin.upcoming_name")) + '<input name="name" required minlength="3" maxlength="200"></label>' +
      '<label class="field">' + esc(t("admin.upcoming_type")) + '<select name="transport_type" id="upcomingType"></select></label>' +
      '<label class="field">' + esc(t("admin.upcoming_location")) + '<input name="location" maxlength="300"></label>' +
      '<label class="field">' + esc(t("admin.upcoming_text")) + '<textarea name="announcement" rows="2" maxlength="2000"></textarea></label>' +
      '<label class="field">' + esc(t("admin.upcoming_status")) + '<select name="status" id="upcomingStatus"></select></label>' +
      '<label class="field">' + esc(t("admin.upcoming_kind")) + '<select name="source_kind" id="upcomingKind"></select></label>' +
      '<label class="field">' + esc(t("admin.upcoming_announced")) + '<input name="announced_on" maxlength="10" pattern="\\d{4}(-\\d{2}(-\\d{2})?)?" autocomplete="off"></label>' +
      '<label class="field">' + esc(t("admin.upcoming_expected")) + '<input name="expected_start" maxlength="10" pattern="\\d{4}(-\\d{2}(-\\d{2})?)?" autocomplete="off"></label>' +
      '<label class="field">' + esc(t("admin.upcoming_opened")) + '<input name="opened_on" type="date"></label>' +
      '<label class="field">' + esc(t("admin.upcoming_sources")) + '<textarea name="sources" rows="3" required maxlength="3000"></textarea></label>' +
      '<label class="field">' + esc(t("admin.upcoming_verified")) + '<input name="verified_on" type="date" required></label>' +
      '<label class="field">' + esc(t("admin.upcoming_note")) + '<input name="note" maxlength="300"></label>' +
      '<label class="field">' + esc(t("admin.upcoming_reason")) + '<input name="reason" required minlength="3" maxlength="500" autocomplete="off"></label>' +
      '<div class="align-end"><button type="submit">' + esc(t("admin.upcoming_save")) + "</button></div></form></section>" +
      '<section class="card"><h2>' + esc(t("admin.upload_title")) + "</h2>" +
      '<p class="muted">' + esc(t("admin.upload_help")) + "</p>" +
      '<form id="uploadForm" class="form-grid">' +
      '<label class="field">' + esc(t("admin.upload_source")) + '<select name="data_source_id" id="uploadSource" required></select></label>' +
      '<label class="field">' + esc(t("admin.upload_file")) + '<input name="file" type="file" accept=".zip,application/zip" required></label>' +
      '<div style="align-self:end"><button type="submit">' + esc(t("admin.upload_submit")) + "</button></div></form>" +
      '<div id="uploadResult" style="margin-top:12px"></div></section>' +
      '<section class="card"><h2>' + esc(t("admin.imports")) + '</h2><div id="adminImports">' + loadingInline() + "</div></section>" +
      '<section class="card"><h2>' + esc(t("admin.db_title")) + '</h2><div id="adminStats">' + loadingInline() + "</div>" +
      '<div class="toolbar" style="margin-top:8px"><button type="button" class="secondary" data-action="backup">' + esc(t("admin.backup")) + "</button></div></section>" +
      '<section class="card"><h2>' + esc(t("admin.audit")) + '</h2><div id="adminAudit">' + loadingInline() + "</div></section>";

    try {
      await refreshAdminData(token);
    } catch (err) {
      adminFailure(err, token);
    }
  }

  // ---------------------------------------------------------------- administration: rendering
  var STATUS_KEYS = { COMPLETED: "admin.status_completed", REJECTED: "admin.status_rejected" };
  var STAT_KEYS = [
    ["data_sources", "admin.stat_sources"],
    ["imports_completed", "admin.stat_imports_ok"],
    ["imports_rejected", "admin.stat_imports_rejected"],
    ["routes", "admin.stat_routes"],
    ["stops", "admin.stat_stops"],
    ["trips", "admin.stat_trips"],
    ["stop_times", "admin.stat_stop_times"],
    ["shape_points", "admin.stat_shapes"],
    ["scenarios", "admin.stat_scenarios"],
    ["audit_entries", "admin.stat_audit"],
  ];

  // The database keeps times without a time zone. Those are UTC, so they are read as UTC here.
  function parseUtc(value) {
    var text = String(value || "").replace(/(\.\d{3})\d+/, "$1");
    if (!text) return NaN;
    if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(text)) text += "Z";
    return Date.parse(text);
  }

  function utcText(value) {
    var ms = parseUtc(value);
    if (isNaN(ms)) return t("common.na");
    return new Intl.DateTimeFormat(localeTag(), {
      timeZone: "UTC",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZoneName: "short",
    }).format(new Date(ms));
  }

  function statusText(status) {
    return Object.prototype.hasOwnProperty.call(STATUS_KEYS, status) ? t(STATUS_KEYS[status]) : String(status || "");
  }

  function listHtml(items) {
    if (!items || !items.length) return "";
    return "<ul>" + items.map(function (item) {
      return "<li>" + esc(item) + "</li>";
    }).join("") + "</ul>";
  }

  function adminSourceRow(s) {
    var canVerify = s.kind === "OFFICIAL";
    var status = s.verified
      ? esc(t("admin.verified")) +
        (s.verified_at ? '<div class="muted">' + esc(t("src.verified_on", { date: String(s.verified_at).slice(0, 10) })) + "</div>" : "") +
        (s.admin_note ? '<div class="muted">' + esc(s.admin_note) + "</div>" : "")
      : esc(t("admin.not_verified"));
    var action = s.verified
      ? '<button type="button" class="secondary" data-action="src-revoke" data-id="' + esc(s.id) + '">' + esc(t("admin.revoke")) + "</button>"
      : '<button type="button" data-action="src-verify" data-id="' + esc(s.id) + '"' + (canVerify ? "" : " disabled") + ">" +
        esc(t("admin.verify")) + "</button>";
    var hint = !s.verified && !canVerify ? '<div class="muted">' + esc(t("admin.verify_official_only")) + "</div>" : "";
    return "<tr><td>" + esc(s.id) + "</td><td><strong>" + esc(s.name) + '</strong><div class="muted">' + esc(s.publisher) +
      "</div></td><td>" + esc(s.kind) + "</td><td>" + badge(s.classification) + "</td><td>" + status +
      '<div class="row-actions">' + action + "</div>" + hint + "</td></tr>";
  }

  function renderAdminSources(sources) {
    var box = document.getElementById("adminSources");
    if (box) {
      box.innerHTML = sources.length
        ? '<div class="table-wrap" tabindex="0" role="region" aria-label="' + esc(t("common.table_scroll", { name: t("table.sources") })) + '"><table><thead><tr><th>' + esc(t("admin.col_id")) + "</th><th>" + esc(t("admin.col_name")) +
          "</th><th>" + esc(t("admin.col_kind")) + "</th><th>" + esc(t("admin.col_class")) + "</th><th>" + esc(t("admin.col_status")) +
          "</th></tr></thead><tbody>" + sources.map(adminSourceRow).join("") + "</tbody></table></div>"
        : '<div class="empty">' + esc(t("admin.sources_none")) + "</div>";
    }
    var select = document.getElementById("uploadSource");
    if (select) {
      select.innerHTML = sources.map(function (s) {
        return '<option value="' + esc(s.id) + '">' + esc(s.name + " (" + s.kind + ")") + "</option>";
      }).join("");
      select.disabled = !sources.length;
    }
    var submit = document.querySelector('#uploadForm button[type="submit"]');
    if (submit) submit.disabled = !sources.length;
  }

  function renderAdminImports(imports) {
    var box = document.getElementById("adminImports");
    if (!box) return;
    if (!imports.length) {
      box.innerHTML = '<div class="empty">' + esc(t("admin.imports_none")) + "</div>";
      return;
    }
    var rows = imports.map(function (imp) {
      var counts = t("admin.import_counts", {
        routes: fmtNum(imp.routes),
        stops: fmtNum(imp.stops),
        trips: fmtNum(imp.trips),
        stop_times: fmtNum(imp.stop_times),
        start: formatCalendarDate(imp.feed_start_date),
        end: formatCalendarDate(imp.feed_end_date),
      });
      var problems = t("admin.import_problems", { errors: fmtNum(imp.errors.length), warnings: fmtNum(imp.warnings.length) });
      var details = imp.errors.length || imp.warnings.length
        ? "<details><summary>" + esc(problems) + "</summary>" + listHtml(imp.errors.concat(imp.warnings)) + "</details>"
        : esc(problems);
      return "<tr><td>" + esc(imp.id) + "</td><td><strong>" + esc(imp.filename) + '</strong><div class="muted">' + esc(counts) +
        "</div></td><td>" + badge(imp.classification) + "</td><td>" + esc(statusText(imp.status)) + "<div>" + details + "</div></td><td>" +
        '<button type="button" class="danger" data-action="import-delete" data-id="' + esc(imp.id) + '" aria-label="' +
        esc(t("admin.import_delete", { id: imp.id })) + '">' + esc(t("common.delete")) + "</button></td></tr>";
    }).join("");
    box.innerHTML = '<div class="table-wrap" tabindex="0" role="region" aria-label="' + esc(t("common.table_scroll", { name: t("table.imports") })) + '"><table><thead><tr><th>' + esc(t("admin.col_id")) + "</th><th>" + esc(t("admin.upload_file")) +
      "</th><th>" + esc(t("admin.col_class")) + "</th><th>" + esc(t("admin.col_status")) + '</th><th><span class="sr-only">' +
      esc(t("common.delete")) + "</span></th></tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  function renderAdminStats(stats) {
    var box = document.getElementById("adminStats");
    if (!box) return;
    var counts = stats.counts || {};
    var perClass = stats.active_imports_by_classification || {};
    box.innerHTML = '<dl class="kv">' +
      STAT_KEYS.map(function (pair) {
        return "<dt>" + esc(t(pair[1])) + "</dt><dd>" + esc(fmtNum(counts[pair[0]] || 0)) + "</dd>";
      }).join("") +
      "</dl>" +
      '<p class="muted">' + esc(t("admin.active_imports", {
        official: fmtNum(perClass.OFFICIAL_VERIFIED || 0),
        unverified: fmtNum(perClass.UNVERIFIED_FEED || 0),
      })) + "</p>" +
      '<p class="muted">' + esc(t("admin.database", { name: stats.database || t("common.na") })) + "</p>";
  }

  function renderAdminAudit(entries) {
    var box = document.getElementById("adminAudit");
    if (!box) return;
    if (!entries.length) {
      box.innerHTML = '<div class="empty">' + esc(t("admin.audit_none")) + "</div>";
      return;
    }
    var rows = entries.map(function (entry) {
      var detail = entry.detail === null || entry.detail === undefined ? "" : JSON.stringify(entry.detail);
      if (detail.length > 240) detail = detail.slice(0, 237) + "...";
      var entity = entry.entity + (entry.entity_id === null || entry.entity_id === undefined ? "" : " " + entry.entity_id);
      return "<tr><td>" + esc(utcText(entry.time)) + "</td><td>" + esc(entry.actor) + "</td><td>" + esc(entry.action) +
        "</td><td>" + esc(entity) + '</td><td class="muted">' + esc(detail) + "</td></tr>";
    }).join("");
    box.innerHTML = '<div class="table-wrap" tabindex="0" role="region" aria-label="' + esc(t("common.table_scroll", { name: t("table.audit") })) + '"><table><thead><tr><th>' + esc(t("admin.audit_time")) + "</th><th>" + esc(t("admin.audit_actor")) +
      "</th><th>" + esc(t("admin.audit_action")) + "</th><th>" + esc(t("admin.audit_entity")) + "</th><th>" + esc(t("admin.audit_detail")) +
      "</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  function importSummaryHtml(summary) {
    var counts = t("admin.import_counts", {
      routes: fmtNum(summary.routes),
      stops: fmtNum(summary.stops),
      trips: fmtNum(summary.trips),
      stop_times: fmtNum(summary.stop_times),
      start: formatCalendarDate(summary.feed_start_date),
      end: formatCalendarDate(summary.feed_end_date),
    });
    var problems = t("admin.import_problems", { errors: fmtNum(summary.errors.length), warnings: fmtNum(summary.warnings.length) });
    var fares = t("admin.import_fares", { fares: fmtNum(summary.fares) });
    var outcome = summary.status === "COMPLETED" ? "" : t("admin.import_nothing_stored");
    var warningNote = summary.warnings.length ? t("admin.import_warnings_note") : "";
    return "<p>" + badge(summary.classification) + " " + esc(statusText(summary.status)) + "</p>" +
      (outcome ? "<p><strong>" + esc(outcome) + "</strong></p>" : "") +
      '<p class="muted">' + esc(counts) + "</p>" +
      '<p class="muted">' + esc(fares) + "</p>" +
      '<p class="muted">' + esc(problems) + "</p>" +
      (warningNote ? '<p class="muted">' + esc(warningNote) + "</p>" : "") +
      listHtml(summary.errors) + listHtml(summary.warnings);
  }

  function setAdminNotice(html) {
    var notice = document.getElementById("adminNotice");
    if (notice) notice.innerHTML = html || "";
  }

  // A refused admin key signs the page out. Any other failure is shown on the admin page.
  function adminFailure(err, token) {
    if (err && err.status === 401) {
      state.adminKey = "";
      if (token === state.viewToken) {
        toast(t("admin.key_rejected"));
        render();
      }
      return;
    }
    if (token === state.viewToken) {
      setAdminNotice('<div class="banner error" role="alert">' + esc(err && err.message ? err.message : t("msg.unexpected")) + "</div>");
    }
  }

  async function refreshAdminData(token) {
    var results = await Promise.all([
      api("/api/admin/data-sources", { admin: true }),
      api("/api/admin/imports", { admin: true }),
      api("/api/admin/stats", { admin: true }),
      api("/api/admin/audit-logs?limit=50", { admin: true }),
      api("/api/upcoming"),
    ]);
    if (token !== state.viewToken || !document.getElementById("adminBody")) return;
    setAdminNotice("");
    renderAdminSources(results[0].sources);
    renderAdminImports(results[1].imports);
    renderAdminStats(results[2]);
    renderAdminAudit(results[3].entries);
    renderAdminUpcoming(results[4]);
  }

  // ---------------------------------------------------------------- administration: upcoming transport
  function optionList(values, prefix, selected) {
    return values.map(function (v) {
      return '<option value="' + esc(v) + '"' + (v === selected ? " selected" : "") + ">" + esc(t(prefix + v)) + "</option>";
    }).join("");
  }

  function renderAdminUpcoming(data) {
    var form = document.getElementById("upcomingForm");
    if (!form) return;
    state.adminUpcoming = data;
    var current = form.elements.entry.value;
    form.elements.entry.innerHTML = '<option value="">' + esc(t("admin.upcoming_new")) + "</option>" +
      data.projects.map(function (p) {
        return '<option value="' + esc(p.id) + '"' + (p.id === current ? " selected" : "") + ">" + esc(p.name) + "</option>";
      }).join("");
    fillUpcomingForm(form);
  }

  function fillUpcomingForm(form) {
    var data = state.adminUpcoming;
    if (!data) return;
    var key = form.elements.entry.value;
    var p = data.projects.filter(function (x) { return x.id === key; })[0] || {};
    form.elements.transport_type.innerHTML = optionList(data.transport_types, "upcoming.type.", p.transport_type);
    form.elements.status.innerHTML = optionList(data.statuses, "upcoming.status.", p.status || "ANNOUNCED");
    form.elements.source_kind.innerHTML = optionList(data.source_kinds, "upcoming.kind.", p.source_kind || "OFFICIAL");
    // The field is "entry_id", not "id": a control named "id" would hide form.id, which the submit handler reads.
    form.elements.entry_id.value = p.id || "";
    form.elements.entry_id.disabled = Boolean(p.id);
    ["name", "location", "announcement", "announced_on", "expected_start", "opened_on", "verified_on", "note"].forEach(function (f) {
      form.elements[f].value = p[f] || "";
    });
    form.elements.sources.value = (p.sources || []).map(function (s) { return s.title + " | " + s.url; }).join("\n");
    form.elements.reason.value = "";
  }

  // Each line is "Title | full https address". Returns null when a line does not follow that form.
  function parseSources(text) {
    var sources = [];
    var lines = String(text || "").split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
    for (var i = 0; i < lines.length; i++) {
      var cut = lines[i].lastIndexOf("|");
      var title = cut > 0 ? lines[i].slice(0, cut).trim() : "";
      var url = cut > 0 ? lines[i].slice(cut + 1).trim() : "";
      if (!title || !/^https:\/\/\S+$/.test(url)) return null;
      sources.push({ title: title, url: url });
    }
    return sources.length ? sources : null;
  }

  async function submitUpcoming(form, token) {
    var sources = parseSources(form.elements.sources.value);
    if (!sources) {
      toast(t("admin.upcoming_bad_sources"));
      return;
    }
    var body = { sources: sources, reason: String(form.elements.reason.value || "").trim() };
    ["name", "transport_type", "location", "announcement", "status", "source_kind", "verified_on", "note"].forEach(function (f) {
      body[f] = String(form.elements[f].value || "").trim();
    });
    ["announced_on", "expected_start", "opened_on"].forEach(function (f) {
      body[f] = String(form.elements[f].value || "").trim() || null;
    });
    var key = form.elements.entry.value;
    busy(form, true);
    try {
      if (key) {
        await api("/api/admin/upcoming/" + encodeURIComponent(key), { admin: true, method: "PATCH", json: body });
      } else {
        body.id = String(form.elements.entry_id.value || "").trim();
        await api("/api/admin/upcoming", { admin: true, method: "POST", json: body });
        form.elements.entry.value = "";
      }
      toast(t("admin.upcoming_saved"));
      await refreshAdminData(token);
    } catch (err) {
      adminFailure(err, token);
    } finally {
      busy(form, false);
    }
  }

  // ---------------------------------------------------------------- administration: actions
  // Disables a form's submit button while its request runs, so one click cannot send the request twice.
  function busy(form, on) {
    var button = form ? form.querySelector('button[type="submit"]') : null;
    if (button) button.disabled = on;
  }

  function adminHeaders() {
    if (!state.adminKey) throw new Error(t("admin.key_needed"));
    return { Accept: "application/json", "X-Client-Key": clientKey(), "X-Admin-Key": state.adminKey };
  }

  function saveAdminKey(input) {
    var key = input && input.value ? String(input.value).trim() : "";
    if (!key) {
      toast(t("admin.key_empty"));
      return;
    }
    state.adminKey = key;
    render();
  }

  function forgetAdminKey() {
    state.adminKey = "";
    toast(t("admin.key_forgotten"));
    render();
  }

  async function submitSource(form, token) {
    var data = new FormData(form);
    var url = String(data.get("source_url") || "").trim();
    var license = String(data.get("license") || "").trim();
    var body = {
      name: String(data.get("name") || "").trim(),
      publisher: String(data.get("publisher") || "").trim(),
      source_url: url || null,
      kind: String(data.get("kind") || "UNKNOWN"),
    };
    if (license) body.license = license;
    busy(form, true);
    try {
      await api("/api/admin/data-sources", { admin: true, method: "POST", json: body });
      form.reset();
      toast(t("admin.source_added"));
      await refreshAdminData(token);
    } catch (err) {
      adminFailure(err, token);
    } finally {
      busy(form, false);
    }
  }

  async function submitUpload(form, token) {
    var box = document.getElementById("uploadResult");
    if (!box) return;
    busy(form, true);
    box.innerHTML = loadingInline(t("admin.uploading"));
    var timer = startTimer(IMPORT_TIMEOUT_MS);
    try {
      var response = await send("/api/admin/imports", { method: "POST", headers: adminHeaders(), body: new FormData(form) }, timer.signal);
      var result = await readJson(response);
      if (response.status === 401) {
        var refused = new Error(t("admin.key_rejected"));
        refused.status = 401;
        throw refused;
      }
      // 201 means stored, 422 means the feed was checked and rejected. Both carry the import summary.
      if (!result || !result.import) throw httpError(response, result);
      if (token !== state.viewToken || !box.isConnected) return;
      box.innerHTML = "<h3>" + esc(t(response.status === 201 ? "admin.uploaded" : "admin.rejected")) + "</h3>" +
        importSummaryHtml(result.import);
      form.elements.file.value = "";
      refreshAdminData(token).catch(function (err) {
        adminFailure(err, token);
      });
    } catch (err) {
      if (err && err.status === 401) {
        adminFailure(err, token);
      } else if (token === state.viewToken && box.isConnected) {
        box.innerHTML = '<div class="banner error" role="alert">' + esc(err && err.message ? err.message : t("msg.unexpected")) + "</div>";
      }
    } finally {
      timer.stop();
      busy(form, false);
    }
  }

  async function createBackup(token) {
    try {
      var data = await api("/api/admin/backup", { admin: true, method: "POST", timeout: BACKUP_TIMEOUT_MS });
      toast(t("admin.backup_done", { file: data.file }));
      await refreshAdminData(token);
    } catch (err) {
      adminFailure(err, token);
    }
  }

  async function deleteImport(id, token) {
    if (!window.confirm(t("admin.import_delete_confirm"))) return;
    try {
      await api("/api/admin/imports/" + encodeURIComponent(id), { admin: true, method: "DELETE" });
      toast(t("admin.import_deleted"));
      await refreshAdminData(token);
    } catch (err) {
      adminFailure(err, token);
    }
  }

  // The evidence or reason is asked in a prompt, so it is recorded with the decision in the audit log.
  // Verifying or revoking a source asks for its evidence on this page, not in a browser dialog. The question stays
  // on screen, the answer is typed with the keyboard, and Cancel or Escape leaves the status unchanged.
  var decisionOpener = null;

  function openSourceDecision(id, verified, opener) {
    var form = document.getElementById("sourceDecisionForm");
    if (!form) return;
    decisionOpener = opener && opener.isConnected ? opener : null;
    form.elements.namedItem("source_id").value = String(id);
    form.elements.namedItem("verified").value = verified ? "true" : "false";
    form.elements.namedItem("note").value = "";
    document.getElementById("decisionQuestion").textContent = t(verified ? "admin.verify_prompt" : "admin.revoke_prompt");
    document.getElementById("decisionSubmit").textContent = t(verified ? "admin.verify" : "admin.revoke");
    form.hidden = false;
    form.elements.namedItem("note").focus();
  }

  function closeSourceDecision() {
    var form = document.getElementById("sourceDecisionForm");
    if (!form) return;
    form.hidden = true;
    form.reset();
    if (decisionOpener && decisionOpener.isConnected) decisionOpener.focus();
    decisionOpener = null;
  }

  async function submitDecision(form, token) {
    var verified = form.elements.namedItem("verified").value === "true";
    var id = form.elements.namedItem("source_id").value;
    var note = String(form.elements.namedItem("note").value || "").trim();
    if (!id || !note) {
      form.elements.namedItem("note").focus();
      return;
    }
    busy(form, true);
    try {
      await api("/api/admin/data-sources/" + encodeURIComponent(id) + "/verify", {
        admin: true,
        method: "POST",
        json: { verified: verified, note: note.slice(0, 500) },
      });
      if (token !== state.viewToken) return;
      closeSourceDecision();
      toast(t(verified ? "admin.verify_done" : "admin.revoke_done"));
      await refreshAdminData(token);
    } catch (err) {
      adminFailure(err, token);
    } finally {
      busy(form, false);
    }
  }

  // ---------------------------------------------------------------- routing table
  // ---------------------------------------------------------------- 4.0 app sections
  // Home, Nearby, Live tracking, Tickets, Metro, Favourites, My account and More services. Every section reads what
  // the server says works right now (/api/features), so a feature that needs data or an authorisation explains
  // itself instead of pretending to work.
  var BENGALURU = [12.9716, 77.5946];
  var METRO_TYPES = [1, 400, 401, 402];
  var NEW_SECTIONS = ["home", "nearby", "live", "tickets", "metro", "favourites", "account", "more", "upcoming", "assistant", "providers"];

  // Small line icons, drawn for this app.
  var ICONS = {
    nearby: '<path d="M12 21s-6-5.6-6-11a6 6 0 0 1 12 0c0 5.4-6 11-6 11z"/><circle cx="12" cy="10" r="2.2"/>',
    plan: '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6"/>',
    live: '<path d="M5 12a7 7 0 0 1 14 0"/><path d="M8.5 12a3.5 3.5 0 0 1 7 0"/><circle cx="12" cy="12" r="1.3"/><path d="M12 13.5V20"/>',
    routes: '<rect x="5" y="4" width="14" height="13" rx="3"/><path d="M5 11h14M8 20l1-3M16 20l-1-3"/><circle cx="8.5" cy="14" r=".8"/><circle cx="15.5" cy="14" r=".8"/>',
    metro: '<rect x="6" y="3" width="12" height="14" rx="3"/><path d="M6 10h12M9 21l2-4M15 21l-2-4"/>',
    tickets: '<path d="M4 8a2 2 0 0 0 0 4v4h16v-4a2 2 0 0 0 0-4V4H4z"/><path d="M14 4v12" stroke-dasharray="2 2"/>',
    favourites: '<path d="M12 20l-7-7a4.2 4.2 0 0 1 6-6l1 1 1-1a4.2 4.2 0 0 1 6 6z"/>',
    airport: '<path d="M3 14l18-5-2-2-6 1-5-5-2 1 3 5-4 1-2-2-1 1 2 4z"/>',
    sos: '<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/>',
    more: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
    assist: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
    upcoming: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4M9 15l2 2 4-4"/>',
  };

  function icon(name) {
    return '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (ICONS[name] || "") + "</svg>";
  }

  async function loadFeatures() {
    try {
      var data = await api("/api/features");
      var map = {};
      data.features.forEach(function (f) {
        map[f.id] = f;
      });
      state.features = map;
      state.version = data.version;
      var version = document.getElementById("splashVersion");
      if (version) version.textContent = t("more.version", { version: data.version });
    } catch (_) {
      /* Without the list, tiles simply show no status chip. */
    }
    return state.features || {};
  }

  function featureChip(id) {
    var feature = state.features && state.features[id];
    if (!feature) return "";
    return '<span class="chip state-' + esc(feature.state.toLowerCase()) + '">' + esc(t("feature.state." + feature.state)) + "</span>";
  }

  function featureReason(id) {
    var feature = state.features && state.features[id];
    return feature && feature.reason ? t("feature.reason." + feature.reason) : "";
  }

  function tile(href, iconName, label, featureId, tone) {
    return '<a class="tile tone-' + tone + '" href="' + href + '">' +
      '<span class="tile-icon">' + icon(iconName) + "</span>" +
      '<span class="tile-label">' + esc(label) + "</span>" + (featureId ? featureChip(featureId) : "") + "</a>";
  }

  async function renderHome(args, token) {
    await loadFeatures();
    if (token !== state.viewToken) return;
    setView(
      '<section class="hero card">' +
      '<form id="homeSearch" class="home-search" role="search">' +
      '<label class="sr-only" for="homeQuery">' + esc(t("home.search_label")) + "</label>" +
      '<input id="homeQuery" name="q" type="search" maxlength="80" autocomplete="off" placeholder="' + esc(t("home.search_placeholder")) + '">' +
      '<div class="home-search-actions">' +
      '<button type="submit" name="kind" value="routes">' + esc(t("home.find_route")) + "</button>" +
      '<button type="submit" name="kind" value="stops" class="secondary">' + esc(t("home.find_stop")) + "</button></div></form>" +
      recentHtml() + "</section>" +
      '<section class="card map-card"><div class="card-head"><h2>' + esc(t("home.map_title")) + "</h2>" +
      '<button type="button" class="secondary" data-action="home-nearby">' + esc(t("home.near_me")) + "</button></div>" +
      '<div id="homeMap" class="map home-map" role="region" aria-label="' + esc(t("home.map_title")) + '"></div></section>' +
      '<section class="tiles" aria-label="' + esc(t("home.services")) + '">' +
      tile("#/nearby", "nearby", t("nav.nearby"), "nearby_stops", "red") +
      tile("#/journey", "plan", t("nav.journey"), "journey_planner", "amber") +
      tile("#/live", "live", t("nav.live"), "live_tracking", "blue") +
      tile("#/routes", "routes", t("home.timetables"), "bus_timetables", "teal") +
      tile("#/metro", "metro", t("nav.metro"), "metro", "violet") +
      tile("#/tickets", "tickets", t("nav.tickets"), "bus_tickets", "orange") +
      tile("#/favourites", "favourites", t("nav.favourites"), "favourites", "pink") +
      tile("#/more/airport", "airport", t("home.airport"), null, "sky") +
      tile("#/assistant", "assist", t("nav.assistant"), "ai_assistant", "blue") +
      tile("#/upcoming", "upcoming", t("nav.upcoming"), "upcoming_transport", "violet") +
      tile("#/more/sos", "sos", t("home.sos"), "sos_call", "danger") +
      tile("#/more", "more", t("nav.more"), null, "slate") +
      "</section>"
    );
    if (state.lowData) {
      var holder = document.getElementById("homeMap");
      if (holder) {
        holder.innerHTML = '<div class="map-placeholder"><p>' + esc(t("home.map_lowdata")) + "</p>" +
          '<button type="button" class="secondary" data-action="show-map">' + esc(t("home.show_map")) + "</button></div>";
      }
    } else {
      showHomeMap();
    }
  }

  function showHomeMap() {
    var map = makeMap("homeMap");
    if (map) map.setView(BENGALURU, 11);
  }

  async function renderNearby(args, token) {
    await renderStops([], token);
    if (state.autoNearby && token === state.viewToken) {
      state.autoNearby = false;
      nearbyStops();
    }
  }

  async function officialLinks(categoryIds) {
    var data = await loadServices();
    var cats = data.categories.filter(function (c) {
      return !categoryIds || categoryIds.indexOf(c.id) !== -1;
    });
    return cats.map(function (c) {
      return '<h3 id="svc-' + esc(c.id) + '">' + esc(t("svc.cat." + c.id)) + '</h3><ul class="list links">' + c.items.map(serviceItem).join("") + "</ul>";
    }).join("") + '<p class="muted small">' + esc(t("more.checked", { date: formatCalendarDate(data.checked) })) + "</p>";
  }

  async function loadServices() {
    if (!state.services) state.services = await api("/api/services");
    return state.services;
  }

  function serviceItem(item) {
    var actions = "";
    if (item.tel && /^[0-9]{3,12}$/.test(item.tel)) {
      actions += '<a class="button-link" href="tel:' + esc(item.tel) + '">' + esc(t("more.call", { number: item.tel })) + "</a>";
    }
    var href = safeHref(item.url);
    if (href) {
      actions += '<a class="button-link secondary" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' + esc(t("more.open_site")) + "</a>";
    }
    return '<li><div><div class="title">' + esc(item.name) + '</div><div class="muted small">' + esc(item.source) + "</div></div>" +
      '<div class="row-actions">' + actions + "</div></li>";
  }

  function unavailableCard(titleKey, bodyKey, featureId) {
    var reason = featureReason(featureId);
    return '<section class="card unavailable"><div class="card-head"><h2>' + esc(t(titleKey)) + "</h2>" + featureChip(featureId) + "</div>" +
      "<p>" + esc(t(bodyKey)) + "</p>" + (reason ? '<p class="muted">' + esc(reason) + "</p>" : "") + "</section>";
  }

  async function renderLive(args, token) {
    await loadFeatures();
    if (token !== state.viewToken) return;
    setView(
      unavailableCard("live.unavailable_title", "live.body", "live_tracking") +
      '<section class="card"><h2>' + esc(t("live.scheduled_title")) + "</h2><p>" + esc(t("live.scheduled_body")) + "</p>" +
      '<p><a class="button-link" href="#/nearby">' + esc(t("live.scheduled_link")) + "</a></p></section>" +
      '<section class="card"><h2>' + esc(t("live.official_title")) + '</h2><div id="liveLinks"></div></section>'
    );
    await fillPanel(document.getElementById("liveLinks"), token, function () {
      return officialLinks(["bus"]);
    });
  }

  async function renderTickets(args, token) {
    await loadFeatures();
    if (token !== state.viewToken) return;
    setView(
      unavailableCard("tickets.title", "tickets.body", "bus_tickets") +
      '<section class="card"><h2>' + esc(t("tickets.where")) + "</h2>" +
      "<p>" + esc(t("tickets.bus_channels")) + "</p><p>" + esc(t("tickets.metro_channels")) + '</p><div id="ticketLinks"></div></section>' +
      unavailableCard("tickets.ncmc_title", "tickets.ncmc_body", "ncmc_cards")
    );
    await fillPanel(document.getElementById("ticketLinks"), token, function () {
      return officialLinks(["bus", "metro"]);
    });
  }

  async function renderMetro(args, token) {
    await loadFeatures();
    if (token !== state.viewToken) return;
    setView(
      '<section class="card"><div class="card-head"><h2>' + esc(t("metro.title")) + "</h2>" + featureChip("metro") + "</div>" +
      '<p class="muted">' + esc(t("metro.intro")) + "</p>" + segmentedClassification() +
      '<div id="metroLines" style="margin-top:12px"></div></section>' +
      '<section class="card"><h2>' + esc(t("metro.stations")) + "</h2>" +
      '<form id="metroSearch" class="toolbar" role="search">' +
      '<label class="field" style="flex:1 1 240px">' + esc(t("metro.search_label")) +
      '<input name="q" type="search" maxlength="80" autocomplete="off" placeholder="' + esc(t("metro.search_placeholder")) + '"></label>' +
      '<button type="submit">' + esc(t("common.search")) + '</button></form><div id="metroStations"></div></section>' +
      '<section class="card"><h2>' + esc(t("metro.tickets_title")) + "</h2><p>" + esc(t("tickets.metro_channels")) + "</p>" +
      '<p><a class="button-link secondary" href="#/tickets">' + esc(t("nav.tickets")) + "</a></p></section>"
    );
    await fillPanel(document.getElementById("metroLines"), token, async function () {
      var params = new URLSearchParams({ classification: state.classification, limit: "500" });
      var data = await api("/api/routes?" + params.toString());
      var lines = data.results.filter(function (r) {
        return METRO_TYPES.indexOf(Number(r.route_type)) !== -1;
      });
      if (!lines.length) return '<div class="empty">' + esc(t("metro.no_data")) + "</div>";
      return '<h3>' + esc(t("metro.lines")) + '</h3><ul class="list">' + lines.map(routeItem).join("") + "</ul>";
    });
    await loadMetroStations("", token);
  }

  async function loadMetroStations(query, token) {
    var seq = ++state.searchToken;
    await fillPanel(document.getElementById("metroStations"), token, async function () {
      var params = new URLSearchParams({ classification: state.classification, q: query });
      var data = await api("/api/metro/stations?" + params.toString());
      return metroStationsHtml(data, query);
    }, seq);
  }

  function metroStationsHtml(data, query) {
    if (!data.stations.length) {
      return '<div class="empty">' + esc(query ? t("metro.no_stations_match") : messageFor(data.message_code)) + "</div>";
    }
    return '<ul class="list">' + data.stations.map(function (st) {
        var lines = st.lines.map(function (line) {
          var colour = /^[0-9A-Fa-f]{6}$/.test(line.color || "") ? "#" + line.color : "var(--scenario)";
          return '<span class="line-chip" style="border-color:' + colour + '">' + esc(line.route_number) + "</span>";
        }).join(" ");
        return '<li><div><div class="title">' + esc(st.name) + '</div><div class="muted">' + lines + "</div></div>" +
          '<div class="row-actions"><a class="button secondary" href="#/stops/' + esc(encodeURIComponent(st.id)) + '">' + esc(t("stops.departures")) + "</a></div></li>";
      }).join("") + "</ul>";
  }

  async function renderFavourites(args, token) {
    setView(
      '<section class="card"><h2>' + esc(t("fav.title")) + '</h2><p class="muted">' + esc(t("fav.intro")) + "</p>" +
      "<h3>" + esc(t("routes.saved_title")) + '</h3><div id="savedRoutes"></div>' +
      "<h3>" + esc(t("fav.journeys_title")) + "</h3>" + savedJourneysHtml() +
      "<h3>" + esc(t("fav.stops_title")) + "</h3>" + favouriteStopsHtml() + "</section>"
    );
    await loadSaved(document.getElementById("savedRoutes"), token);
  }

  function favouriteStopsHtml() {
    var list = favouriteStops();
    if (!list.length) return '<div class="empty">' + esc(t("fav.stops_none")) + "</div>";
    return '<ul class="list">' + list.map(function (f) {
      return '<li><div><div class="title">' + esc(f.name) + '</div><div class="muted">' + esc(f.gtfs) + "</div></div>" +
        '<div class="row-actions">' + badge(f.cls) +
        '<button type="button" class="secondary" data-action="open-fav-stop" data-gtfs="' + esc(f.gtfs) + '" data-cls="' + esc(f.cls) + '">' + esc(t("common.open")) + "</button>" +
        '<button type="button" class="danger" data-action="unfav-stop" data-gtfs="' + esc(f.gtfs) + '" data-cls="' + esc(f.cls) + '">' + esc(t("common.remove")) + "</button></div></li>";
    }).join("") + "</ul>";
  }

  function radio(name, value, current, labelKey) {
    return '<label class="choice"><input type="radio" name="' + name + '" value="' + value + '"' + (current === value ? " checked" : "") + "> " + esc(t(labelKey)) + "</label>";
  }

  async function renderAccount(args, token) {
    await loadFeatures();
    if (token !== state.viewToken) return;
    setView(
      '<section class="card"><div class="card-head"><h2>' + esc(t("account.title")) + "</h2>" + featureChip("accounts") + "</div>" +
      "<p>" + esc(t("account.guest")) + '</p><p class="muted">' + esc(t("account.coming")) + "</p></section>" +
      '<section class="card"><h2>' + esc(t("settings.title")) + "</h2>" +
      '<form id="settingsForm" class="settings">' +
      '<fieldset><legend>' + esc(t("settings.theme")) + "</legend>" +
      radio("theme", "system", state.theme, "settings.theme_system") + radio("theme", "light", state.theme, "settings.theme_light") +
      radio("theme", "dark", state.theme, "settings.theme_dark") + "</fieldset>" +
      '<label class="switch"><input type="checkbox" name="lowData"' + (state.lowData ? " checked" : "") + "> " + esc(t("settings.lowdata")) + "</label>" +
      '<p class="muted small">' + esc(t("settings.lowdata_hint")) + "</p>" +
      '<label class="switch"><input type="checkbox" name="largeText"' + (state.largeText ? " checked" : "") + "> " + esc(t("settings.largetext")) + "</label>" +
      '<p class="muted small">' + esc(t("settings.language_hint")) + "</p></form></section>" +
      '<section class="card"><h2>' + esc(t("erase.title")) + "</h2><p>" + esc(t("erase.body")) + "</p>" +
      '<div id="eraseBox"><button type="button" class="danger" data-action="erase-ask">' + esc(t("erase.button")) + "</button></div></section>"
    );
  }

  // Erasure: the server deletes everything linked to this device's key; this browser forgets its lists and its key.
  function askErase() {
    var box = document.getElementById("eraseBox");
    if (!box) return;
    box.innerHTML = '<p class="banner error" role="alert">' + esc(t("erase.confirm")) + "</p>" +
      '<div class="toolbar"><button type="button" class="danger" data-action="erase-do">' + esc(t("erase.yes")) + "</button>" +
      '<button type="button" class="secondary" data-action="erase-cancel">' + esc(t("erase.no")) + "</button></div>";
  }

  async function eraseMyData() {
    try {
      await api("/api/my-data", { method: "DELETE" });
    } catch (err) {
      fail(err);
      return;
    }
    storage.set(PREFIX + "favStops", "[]");
    storage.set(PREFIX + "favJourneys", "[]");
    storage.set(PREFIX + "recent", "[]");
    storage.set(PREFIX + "clientKey", "");
    memoryClientKey = "";
    toast(t("erase.done"));
    render();
  }

  async function renderMore(args, token) {
    await loadFeatures();
    if (token !== state.viewToken) return;
    setView(
      '<section class="card sos-card" id="svc-sos"><h2>' + esc(t("sos.title")) + "</h2><p>" + esc(t("sos.body")) + "</p>" +
      '<p><a class="button-link danger-link" href="tel:112">' + esc(t("sos.call")) + "</a></p></section>" +
      '<section class="card"><h2>' + esc(t("more.official")) + '</h2><div id="moreLinks"></div></section>' +
      '<section class="card"><h2>' + esc(t("more.tools")) + '</h2><ul class="list">' +
      [["#/assistant", "nav.assistant"], ["#/upcoming", "nav.upcoming"], ["#/providers", "nav.providers"], ["#/routes", "nav.routes"], ["#/stops", "nav.stops"], ["#/scenarios", "nav.scenarios"], ["#/compare", "nav.compare"], ["#/sources", "nav.sources"], ["#/admin", "nav.admin"]]
        .map(function (pair) {
          return '<li><a href="' + pair[0] + '">' + esc(t(pair[1])) + "</a></li>";
        }).join("") + "</ul></section>" +
      '<section class="card"><h2>' + esc(t("more.status")) + '</h2><p class="muted">' + esc(t("more.status_intro")) + "</p>" + featureTable() + "</section>" +
      '<section class="card"><h2>' + esc(t("more.about")) + "</h2><p>" + esc(t("app.disclaimer")) + "</p>" +
      '<p class="muted">' + esc(t("more.version", { version: state.version || "" })) + "</p></section>"
    );
    await fillPanel(document.getElementById("moreLinks"), token, function () {
      return officialLinks(null);
    });
    if (args[0]) {
      var target = document.getElementById("svc-" + args[0]);
      if (target && target.scrollIntoView) target.scrollIntoView({ block: "start" });
    }
  }

  function featureTable() {
    var features = state.features || {};
    var ids = Object.keys(features);
    if (!ids.length) return '<div class="empty">' + esc(t("common.na")) + "</div>";
    return '<ul class="list feature-list">' + ids.map(function (id) {
      return '<li><div><div class="title">' + esc(t("feature.name." + id)) + "</div>" +
        (features[id].reason ? '<div class="muted small">' + esc(featureReason(id)) + "</div>" : "") + "</div>" + featureChip(id) + "</li>";
    }).join("") + "</ul>";
  }

  // ---------------------------------------------------------------- settings: theme, low data, large text
  function applySettings() {
    var root = document.documentElement;
    if (state.theme === "light" || state.theme === "dark") root.setAttribute("data-theme", state.theme);
    else root.removeAttribute("data-theme");
    root.classList.toggle("large-text", !!state.largeText);
  }

  function loadSettings() {
    var theme = storage.get(PREFIX + "theme");
    state.theme = theme === "light" || theme === "dark" ? theme : "system";
    var low = storage.get(PREFIX + "lowData");
    var saveData = !!(navigator.connection && navigator.connection.saveData);
    state.lowData = low === null ? saveData : low === "1";
    state.largeText = storage.get(PREFIX + "largeText") === "1";
    applySettings();
  }

  function saveSetting(target) {
    if (target.name === "theme") {
      state.theme = target.value === "light" || target.value === "dark" ? target.value : "system";
      storage.set(PREFIX + "theme", state.theme);
    } else if (target.name === "lowData") {
      state.lowData = !!target.checked;
      storage.set(PREFIX + "lowData", state.lowData ? "1" : "0");
    } else if (target.name === "largeText") {
      state.largeText = !!target.checked;
      storage.set(PREFIX + "largeText", state.largeText ? "1" : "0");
    } else {
      return;
    }
    applySettings();
    toast(t("settings.saved"));
  }

  function hideSplash() {
    var splash = document.getElementById("splash");
    if (!splash || splash.classList.contains("done")) return;
    var wait = Math.max(0, 900 - (Date.now() - startedAt));
    setTimeout(function () {
      splash.classList.add("done");
      setTimeout(function () {
        splash.hidden = true;
      }, 450);
    }, wait);
  }

  // ---------------------------------------------------------------- upcoming transport (information only)
  var PROJECT_CHIP = { OPERATING: "available", ANNOUNCED: "planned", PLANNED: "planned", UNDER_CONSTRUCTION: "planned", DELAYED: "no_data", AWAITING_CONFIRMATION: "no_data" };

  function historyLine(change) {
    var c = change.changes || {};
    var what = c.created ? t("upcoming.history_created")
      : c.status ? t("upcoming.history_status", { from: t("upcoming.status." + c.status[0]), to: t("upcoming.status." + c.status[1]) })
      : t("upcoming.history_details");
    return "<li>" + esc(formatCalendarDate(String(change.at || "").slice(0, 10))) + ": " + esc(what) + ". " + esc(change.reason || "") + "</li>";
  }

  function projectItem(p) {
    var chip = PROJECT_CHIP[p.status] || "unavailable";
    var mode = MODES.indexOf(p.mode) !== -1 ? p.mode : "other";
    var dates = [];
    if (p.announced_on) dates.push(t("upcoming.announced", { date: formatPartialDate(p.announced_on) }));
    if (p.status === "OPERATING" && p.opened_on) dates.push(t("upcoming.opened", { date: formatCalendarDate(p.opened_on) }));
    // An expected start is shown only when it comes from an official announcement.
    if (p.expected_start && p.official_announcement) dates.push(t("upcoming.expected", { text: formatPartialDate(p.expected_start) }));
    var links = (p.sources || []).map(function (s) {
      var href = safeHref(s.url);
      return href ? '<li><a href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' + esc(s.title) + "</a></li>" : "";
    }).join("");
    var history = p.history || [];
    return '<li class="project"><div><div class="title">' + esc(p.name) + "</div>" +
      '<div class="muted small"><span class="mode-tag">' + esc(t("mode." + mode)) + "</span> " +
      '<span class="mode-tag">' + esc(t("upcoming.type." + p.transport_type)) + "</span> " +
      "<strong>" + esc(t("upcoming.kind." + p.source_kind)) + "</strong></div>" +
      (p.location ? '<div class="small">' + esc(t("upcoming.location", { text: p.location })) + "</div>" : "") +
      "<p>" + esc(p.announcement || "") + "</p>" +
      (dates.length ? '<div class="small">' + esc(dates.join(" · ")) + "</div>" : "") +
      '<div class="muted small">' + esc(t("upcoming.sources")) + '</div><ul class="plain-links">' + links + "</ul>" +
      '<div class="muted small">' + esc(t("upcoming.verified", { date: formatCalendarDate(p.verified_on), note: p.note || "" })) + "</div>" +
      (history.length ? '<details class="small"><summary>' + esc(t("upcoming.history", { count: history.length })) + "</summary><ul>" + history.map(historyLine).join("") + "</ul></details>" : "") +
      "</div>" +
      '<span class="chip state-' + chip + '">' + esc(t("upcoming.status." + p.status)) + "</span></li>";
  }

  async function renderUpcoming(args, token) {
    await loadFeatures();
    if (token !== state.viewToken) return;
    setView('<section class="card"><div class="card-head"><h2>' + esc(t("upcoming.title")) + "</h2>" + featureChip("upcoming_transport") + "</div>" +
      '<p class="muted">' + esc(t("upcoming.intro")) + '</p><div id="upcomingList"></div></section>');
    await fillPanel(document.getElementById("upcomingList"), token, async function () {
      var data = await api("/api/upcoming");
      return '<p class="notice" role="note">' + esc(t("upcoming.note")) + "</p>" +
        '<ul class="list project-list">' + data.projects.map(projectItem).join("") + "</ul>" +
        '<p class="muted small">' + esc(t("more.checked", { date: formatCalendarDate(data.checked) })) + "</p>";
    });
  }

  // ---------------------------------------------------------------- travel assistant (rule-based)
  // The server only says which of the app's own requests answers the question; the answer shown is that request's
  // result, with its classification and source. Nothing here is written by a language model.
  var ASSIST_EXAMPLES = ["Demo Central to Demo Junction", "Demo Lake View to Demo Metro Hub", "route DEMO-1", "metro stations", "stops near me", "When will my bus arrive?"];

  async function renderAssistant(args, token) {
    await loadFeatures();
    if (token !== state.viewToken) return;
    setView('<section class="card"><div class="card-head"><h2>' + esc(t("assist.title")) + "</h2>" + featureChip("ai_assistant") + "</div>" +
      '<p class="muted">' + esc(t("assist.intro")) + "</p>" +
      '<form id="assistForm" class="toolbar" role="search">' +
      '<label class="field" style="flex:1 1 280px">' + esc(t("assist.label")) +
      '<input name="q" type="search" required maxlength="200" autocomplete="off" placeholder="' + esc(t("assist.placeholder")) + '"></label>' +
      '<button type="submit">' + esc(t("assist.ask")) + "</button></form>" +
      '<p class="muted small">' + esc(t("assist.english_only")) + "</p>" +
      '<div class="chips" aria-label="' + esc(t("assist.examples")) + '">' + ASSIST_EXAMPLES.map(function (q) {
        return '<button type="button" class="chip-button" data-action="assist-example" data-q="' + esc(q) + '">' + esc(q) + "</button>";
      }).join(" ") + "</div>" +
      segmentedClassification() +
      '<div id="assistAnswer" style="margin-top:12px" aria-live="polite"></div></section>');
  }

  function assistLink(href, key) {
    return '<p><a class="button-link secondary" href="' + href + '">' + esc(t(key)) + "</a></p>";
  }

  async function assistAnswer(intent, params) {
    var cls = state.classification;
    switch (intent) {
      case "journey": {
        var data = await api("/api/plan?" + new URLSearchParams({ origin: params.origin, destination: params.destination, classification: cls, modes: params.modes || "all" }).toString());
        return "<p>" + esc(t("assist.journey_intro", { from: params.origin, to: params.destination })) + "</p>" + journeyHtml(data);
      }
      case "route": {
        var routes = await api("/api/routes?" + new URLSearchParams({ classification: cls, q: params.q, limit: "20" }).toString());
        return "<p>" + esc(t("assist.route_intro", { q: params.q })) + "</p>" + routeListHtml(routes);
      }
      case "stop": {
        var stops = await api("/api/stops?" + new URLSearchParams({ classification: cls, q: params.q, limit: "20" }).toString());
        return "<p>" + esc(t("assist.stop_intro", { q: params.q })) + "</p>" + stopListHtml(stops.results, false);
      }
      case "metro": {
        var stations = await api("/api/metro/stations?" + new URLSearchParams({ classification: cls, q: params.q || "" }).toString());
        return "<p>" + esc(t("assist.metro_intro")) + "</p>" + metroStationsHtml(stations, params.q || "");
      }
      case "nearby":
        return "<p>" + esc(t("assist.nearby")) + '</p><p><button type="button" data-action="home-nearby">' + esc(t("home.near_me")) + "</button></p>";
      case "live":
        return '<p class="notice" role="note">' + esc(t("assist.live")) + "</p>" + assistLink("#/live", "nav.live");
      case "tickets":
        return '<p class="notice" role="note">' + esc(t("assist.tickets")) + "</p>" + assistLink("#/tickets", "nav.tickets");
      case "emergency":
        return '<p class="notice" role="alert">' + esc(t("assist.emergency")) + '</p><p><a class="button-link danger-link" href="tel:112">' + esc(t("sos.call")) + "</a></p>";
      default:
        return "<p>" + esc(t("assist.help")) + "</p>";
    }
  }

  async function submitAssist(question, token) {
    var box = document.getElementById("assistAnswer");
    if (!box || !question) return;
    var seq = ++state.searchToken;
    box.innerHTML = loadingInline();
    try {
      var parsed = await api("/api/assistant?" + new URLSearchParams({ q: question }).toString());
      var html = await assistAnswer(parsed.intent, parsed.params || {});
      if (seq !== state.searchToken || token !== state.viewToken || !box.isConnected) return;
      box.innerHTML = '<p class="muted small">' + esc(t("assist.you_asked", { q: question })) + "</p>" + html +
        '<p class="muted small">' + esc(t("assist.footer")) + "</p>";
    } catch (err) {
      if (seq === state.searchToken && token === state.viewToken && box.isConnected) box.innerHTML = panelError(err, "rerender");
    }
  }

  // ---------------------------------------------------------------- data and providers
  var FEED_CHIP = { CURRENT: "available", EXPIRED: "unavailable", NOT_STARTED: "no_data", UNKNOWN_DATES: "no_data" };
  var INTEGRATION_CHIP = { CONNECTED: "available", NOT_CONNECTED: "no_data", BLOCKED: "unavailable" };

  function feedItem(f) {
    var coverage = f.feed_start_date && f.feed_end_date
      ? t("providers.coverage", { from: formatCalendarDate(f.feed_start_date), to: formatCalendarDate(f.feed_end_date) }) : "";
    return '<li><div><div class="title">' + esc(f.source) + " " + badge(f.classification) + "</div>" +
      '<div class="muted small">' + esc(coverage) + (f.expires_soon ? " · " + esc(t("providers.expires_soon")) : "") + "</div>" +
      (f.demo ? '<div class="muted small">' + esc(t("providers.demo_feed")) + "</div>" : "") + "</div>" +
      '<span class="chip state-' + (FEED_CHIP[f.state] || "no_data") + '">' + esc(t("providers.feed_state." + f.state)) + "</span></li>";
  }

  function providerItem(p) {
    var href = safeHref(p.url);
    var updated = !p.loads_data ? "" : p.last_successful_update ? t("providers.last_update", { date: utcText(p.last_successful_update) }) : t("providers.never");
    return '<li><div><div class="title">' + esc(p.provider) + "</div>" +
      '<div class="muted">' + esc(p.dataset) + "</div>" +
      '<div class="muted small">' + esc(t("providers.licence", { text: p.licence })) + "</div>" +
      '<div class="muted small">' + esc(t("providers.permission." + p.permission)) + (updated ? " · " + esc(updated) : "") + "</div>" +
      '<div class="small">' + esc(p.limitations) + "</div>" +
      (href ? '<div class="small"><a href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' + esc(t("more.open_site")) + "</a></div>" : "") + "</div>" +
      '<span class="chip state-' + (INTEGRATION_CHIP[p.integration] || "no_data") + '">' + esc(t("providers.integration." + p.integration)) + "</span></li>";
  }

  function integrationItem(i) {
    var href = safeHref(i.official_url);
    return '<li><div><div class="title">' + esc(t("integ.cap." + i.capability)) + "</div>" +
      '<div class="muted small">' + esc(t("providers.needs", { text: i.needs })) + "</div>" +
      (href ? '<div class="small"><a href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' + esc(t("more.open_site")) + "</a></div>" : "") + "</div>" +
      '<span class="chip state-unavailable">' + esc(t("providers.awaiting")) + "</span></li>";
  }

  async function renderProviders(args, token) {
    setView('<section class="card"><h2>' + esc(t("providers.feeds")) + '</h2><div id="feedStatus"></div></section>' +
      '<section class="card"><h2>' + esc(t("providers.integrations_title")) + '</h2><div id="integrationList"></div></section>' +
      '<section class="card"><h2>' + esc(t("providers.list_title")) + '</h2><p class="muted">' + esc(t("providers.intro")) + '</p><div id="providerList"></div></section>');
    await Promise.all([
      fillPanel(document.getElementById("feedStatus"), token, async function () {
        var data = await api("/api/data-status");
        var html = '<p class="notice" role="note">' + esc(t("providers.no_live")) + "</p>";
        if (data.demo_only) html += '<div class="banner unverified">' + esc(t("providers.demo_only")) + "</div>";
        if (!data.feeds.length) return html + '<div class="empty">' + esc(t("providers.no_feeds")) + "</div>";
        return html + '<ul class="list">' + data.feeds.map(feedItem).join("") + "</ul>";
      }),
      fillPanel(document.getElementById("integrationList"), token, async function () {
        var data = await api("/api/integrations");
        return '<ul class="list">' + data.integrations.map(integrationItem).join("") + "</ul>";
      }),
      fillPanel(document.getElementById("providerList"), token, async function () {
        var data = await api("/api/providers");
        return '<ul class="list">' + data.providers.map(providerItem).join("") + "</ul>" +
          '<p class="muted small">' + esc(t("more.checked", { date: formatCalendarDate(data.checked) })) + "</p>";
      })
    ]);
  }

  var ROUTES = {
    home: renderHome,
    nearby: renderNearby,
    live: renderLive,
    tickets: renderTickets,
    metro: renderMetro,
    favourites: renderFavourites,
    account: renderAccount,
    more: renderMore,
    upcoming: renderUpcoming,
    assistant: renderAssistant,
    providers: renderProviders,
    routes: renderRoutes,
    stops: renderStops,
    journey: renderJourney,
    scenarios: renderScenarios,
    compare: renderCompare,
    sources: renderSources,
    admin: renderAdmin,
  };

  function fail(err) {
    toast(err && err.message ? err.message : t("msg.unexpected"));
  }

  // ---------------------------------------------------------------- saved routes, timetables, scenario helpers
  function setClassification(code) {
    if (code !== "OFFICIAL_VERIFIED" && code !== "UNVERIFIED_FEED") return;
    state.classification = code;
    storage.set(PREFIX + "classification", code);
    render();
  }

  // A saved route is found again by its GTFS id, because internal ids change when a feed is re-imported.
  async function openSavedRoute(gtfsId, classification) {
    if (classification !== "OFFICIAL_VERIFIED" && classification !== "UNVERIFIED_FEED") return;
    var data;
    try {
      data = await api("/api/routes?" + new URLSearchParams({ classification: classification, q: gtfsId, limit: "500" }).toString());
    } catch (err) {
      fail(err);
      return;
    }
    var match = data.results.filter(function (route) {
      return route.gtfs_route_id === gtfsId;
    })[0];
    if (!match) {
      toast(t("routes.saved_gone"));
      return;
    }
    state.classification = classification;
    storage.set(PREFIX + "classification", classification);
    location.hash = "#/routes/" + encodeURIComponent(match.id);
  }

  async function saveRoute(node) {
    var gtfsId = node.getAttribute("data-gtfs");
    var label = String(node.getAttribute("data-label") || gtfsId || "").slice(0, 200);
    try {
      await api("/api/saved-routes", {
        method: "POST",
        json: { gtfs_route_id: gtfsId, classification: node.getAttribute("data-cls"), label: label },
      });
      toast(t("routes.saved_done"));
    } catch (err) {
      toast(err.status === 404 ? t("routes.saved_gone") : err.message);
    }
  }

  async function deleteSaved(id, token) {
    try {
      await api("/api/saved-routes/" + encodeURIComponent(id), { method: "DELETE" });
      await loadSaved(document.getElementById("savedRoutes"), token);
    } catch (err) {
      fail(err);
    }
  }

  async function downloadTimetable(routeId) {
    var input = document.getElementById("ttDate");
    if (!input || !isIsoDate(input.value)) {
      toast(t("common.bad_date"));
      return;
    }
    try {
      await download(
        "/api/routes/" + encodeURIComponent(routeId) + "/timetable.csv?date=" + encodeURIComponent(input.value),
        "timetable_" + routeId + "_" + input.value + ".csv"
      );
    } catch (err) {
      toast(err.status === 404 ? messageFor("NOT_COVERED") : err.message);
    }
  }

  function closeScenarioForm() {
    var box = document.getElementById("scnForm");
    if (box) {
      box.hidden = true;
      box.innerHTML = "";
    }
    state.scenarioEditId = null;
    state.scenarioStops = [];
  }

  function addScenarioStop() {
    syncStopsFromDom();
    if (state.scenarioStops.length >= MAX_SCENARIO_STOPS) {
      toast(t("scn.max_stops", { max: MAX_SCENARIO_STOPS }));
      return;
    }
    state.scenarioStops.push({ name: "", lat: null, lon: null });
    renderScenarioStops();
  }

  function removeScenarioStop(index) {
    syncStopsFromDom();
    if (index >= 0 && index < state.scenarioStops.length) state.scenarioStops.splice(index, 1);
    renderScenarioStops();
  }

  async function deleteScenario(id, token) {
    if (!window.confirm(t("scn.delete_confirm"))) return;
    try {
      await api("/api/scenarios/" + encodeURIComponent(id), { method: "DELETE" });
      if (String(state.scenarioEditId) === String(id)) closeScenarioForm();
      toast(t("scn.deleted"));
      await loadScenarioList(document.getElementById("scnList"), token);
    } catch (err) {
      fail(err);
    }
  }

  function exportScenariosCsv() {
    var filter = document.getElementById("scnYearFilter");
    var query = filter && filter.value ? "?year=" + encodeURIComponent(filter.value) : "";
    return download("/api/scenarios/export.csv" + query, "estimated_scenarios.csv");
  }

  // ---------------------------------------------------------------- one delegated handler per event type
  function handleAction(action, node) {
    var token = state.viewToken;
    var id = node.getAttribute("data-id");
    switch (action) {
      case "rerender":
        render();
        break;
      case "cls":
        setClassification(node.getAttribute("data-cls"));
        break;
      case "cls-search":
        state.pendingQuery = node.getAttribute("data-q") || "";
        setClassification(node.getAttribute("data-cls"));
        break;
      case "recent":
        state.pendingQuery = node.getAttribute("data-q") || "";
        location.hash = node.getAttribute("data-kind") === "stops" ? "#/stops" : "#/routes";
        break;
      case "recent-clear":
        storage.set(PREFIX + "recent", "[]");
        toast(t("recent.cleared"));
        render();
        break;
      case "fav-stop":
        setFavouriteStop(node, true);
        break;
      case "unfav-stop":
        setFavouriteStop(node, false);
        break;
      case "open-fav-stop":
        openFavouriteStop(node);
        break;
      case "tt-load":
        loadTimetable(id, token);
        break;
      case "tt-csv":
        downloadTimetable(id);
        break;
      case "save-route":
        saveRoute(node);
        break;
      case "open-saved":
        openSavedRoute(node.getAttribute("data-gtfs"), node.getAttribute("data-cls"));
        break;
      case "del-saved":
        deleteSaved(id, token);
        break;
      case "nearby-me":
        nearbyStops();
        break;
      case "scn-new":
        openScenarioForm(null, token);
        break;
      case "scn-edit":
        openScenarioForm(id, token);
        break;
      case "scn-del":
        deleteScenario(id, token);
        break;
      case "scn-pdf":
        download("/api/scenarios/" + encodeURIComponent(id) + "/export.pdf", "estimated_scenario_" + id + ".pdf").catch(fail);
        break;
      case "scn-csv":
        exportScenariosCsv().catch(fail);
        break;
      case "scn-add-stop":
        addScenarioStop();
        break;
      case "scn-remove-stop":
        removeScenarioStop(Number(node.getAttribute("data-index")));
        break;
      case "scn-cancel":
        closeScenarioForm();
        break;
      case "cmp-run":
        runComparison(token);
        break;
      case "cmp-pdf":
        comparisonPdf().catch(fail);
        break;
      case "src-verify":
        openSourceDecision(id, true, node);
        break;
      case "src-revoke":
        openSourceDecision(id, false, node);
        break;
      case "decision-cancel":
        closeSourceDecision();
        break;
      case "import-delete":
        deleteImport(id, token);
        break;
      case "backup":
        createBackup(token);
        break;
      case "admin-key-clear":
        forgetAdminKey();
        break;
      case "assist-example": {
        var assistForm = document.getElementById("assistForm");
        if (assistForm) assistForm.elements.q.value = node.getAttribute("data-q") || "";
        submitAssist(node.getAttribute("data-q") || "", token);
        break;
      }
      case "save-journey":
        setSavedJourney(node, true);
        break;
      case "unfav-journey":
        setSavedJourney(node, false);
        break;
      case "plan-fav-journey":
        planSavedJourney(node);
        break;
      case "home-nearby":
        state.autoNearby = true;
        location.hash = "#/nearby";
        break;
      case "show-map":
        showHomeMap();
        break;
      case "erase-ask":
        askErase();
        break;
      case "erase-cancel":
        render();
        break;
      case "erase-do":
        eraseMyData();
        break;
      default:
        break;
    }
  }

  el.view.addEventListener("click", function (event) {
    var target = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!target || target.disabled) return;
    handleAction(target.getAttribute("data-action"), target);
  });

  el.view.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || !form.id) return;
    var token = state.viewToken;
    var handled = true;
    switch (form.id) {
      case "routeSearch":
        addRecent("routes", String(form.elements.q.value || "").trim());
        loadRouteResults(String(form.elements.q.value || "").trim(), document.getElementById("routeResults"), token);
        break;
      case "stopSearch":
        addRecent("stops", String(form.elements.q.value || "").trim());
        loadStops(String(form.elements.q.value || "").trim(), token);
        break;
      case "metroSearch":
        loadMetroStations(String(form.elements.q.value || "").trim(), token);
        break;
      case "journeyForm":
        submitJourney(form, token);
        break;
      case "assistForm":
        submitAssist(String(form.elements.q.value || "").trim(), token);
        break;
      case "scenarioForm":
        submitScenario(form, token);
        break;
      case "sourceDecisionForm":
        submitDecision(form, token);
        break;
      case "sourceForm":
        submitSource(form, token);
        break;
      case "upcomingForm":
        submitUpcoming(form, token);
        break;
      case "uploadForm":
        submitUpload(form, token);
        break;
      case "adminKeyForm":
        saveAdminKey(form.elements.key);
        break;
      case "homeSearch":
        state.pendingQuery = String(form.elements.q.value || "").trim();
        addRecent(event.submitter && event.submitter.value === "stops" ? "stops" : "routes", state.pendingQuery);
        location.hash = event.submitter && event.submitter.value === "stops" ? "#/stops" : "#/routes";
        break;
      case "settingsForm":
        break;
      default:
        handled = false;
    }
    if (handled) event.preventDefault();
  });

  el.view.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || !event.target || !event.target.closest) return;
    if (event.target.closest("#sourceDecisionForm")) closeSourceDecision();
  });

  el.view.addEventListener("change", function (event) {
    var target = event.target;
    if (!target) return;
    if (target.form && target.form.id === "settingsForm") {
      saveSetting(target);
    } else if (target.id === "upcomingEntry") {
      fillUpcomingForm(target.form);
    } else if (target.id === "scnYearFilter") {
      loadScenarioList(document.getElementById("scnList"), state.viewToken);
    } else if (target.name === "when" && target.form && target.form.elements.date) {
      // Leave now is the default; the date is used only when "On a date" is chosen.
      target.form.elements.date.disabled = target.value !== "date";
    }
  });

  // ---------------------------------------------------------------- page controls
  el.yearSelect.addEventListener("change", function () {
    var year = Number(el.yearSelect.value);
    if (PLANNING_YEARS.indexOf(year) === -1) {
      el.yearSelect.value = String(state.year);
      return;
    }
    state.year = year;
    storage.set(PREFIX + "year", String(year));
    render();
  });

  el.langSelect.addEventListener("change", function () {
    setLanguage(el.langSelect.value);
    render();
  });

  el.navToggle.addEventListener("click", function () {
    setMenu(!el.sidebar.classList.contains("open"));
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && el.sidebar.classList.contains("open")) {
      setMenu(false);
      el.navToggle.focus();
    }
  });

  window.addEventListener("hashchange", function () {
    render();
  });
  window.addEventListener("online", syncOnlineState);
  window.addEventListener("offline", syncOnlineState);
  window.addEventListener("unhandledrejection", function () {
    toast(t("msg.unexpected"));
  });

  // ---------------------------------------------------------------- startup
  function init() {
    state.lang = pickInitialLanguage();
    loadSettings();
    populateLanguages();
    var savedYear = Number(storage.get(PREFIX + "year"));
    if (PLANNING_YEARS.indexOf(savedYear) !== -1) state.year = savedYear;
    el.yearSelect.value = String(state.year);
    var savedClass = storage.get(PREFIX + "classification");
    if (savedClass === "OFFICIAL_VERIFIED" || savedClass === "UNVERIFIED_FEED") state.classification = savedClass;
    setLanguage(state.lang);
    syncOnlineState();
    // The skip link moves focus to the page content without changing the address. Following it as a plain link
    // would change the route, and the visitor would lose the page they were on.
    var skip = document.querySelector(".skip-link");
    if (skip) {
      skip.addEventListener("click", function (event) {
        var main = document.getElementById("main");
        if (!main) return;
        event.preventDefault();
        main.focus();
      });
    }
    if (!location.hash) history.replaceState(null, "", "#/home");
    setView(loadingCard());
    // Dates come from the server clock, so the first render waits for it (or for its failure).
    loadClock().then(function () {
      render();
    });
    setInterval(tick, CLOCK_TICK_MS);
    if ("serviceWorker" in navigator) {
      // A new worker takes over while this page is open, so say that a reload will show the new version.
      var hadWorker = !!navigator.serviceWorker.controller;
      navigator.serviceWorker.addEventListener("controllerchange", function () {
        if (hadWorker) toast(t("offline.update_ready"));
      });
      navigator.serviceWorker.register("/sw.js").catch(function () {});
    }
  }

  init();
})();
