/* BMTC Future Transit Planner - web dashboard.
 * No inline scripts or handlers (the CSP forbids them) and no third-party code from a CDN.
 * Official, unverified and estimated data are always rendered in separate, labelled places.
 */
(function () {
  "use strict";

  const PLANNING_YEARS = [2027, 2028, 2029, 2030];
  const DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
  const DAY_LABELS = { MON: "Mon", TUE: "Tue", WED: "Wed", THU: "Thu", FRI: "Fri", SAT: "Sat", SUN: "Sun" };
  const CLS = {
    OFFICIAL_VERIFIED: { label: "Official verified", css: "official" },
    UNVERIFIED_FEED: { label: "Unverified feed", css: "unverified" },
    ESTIMATED_SCENARIO: { label: "Estimated scenario", css: "scenario" },
  };
  const SCENARIO_NOTICE =
    "ESTIMATED SCENARIO: an illustrative proposal only. It is not an official BMTC announcement, and no timetable has been confirmed.";
  const MAX_TRIPS_SHOWN = 200;
  const MAX_SCENARIO_STOPS = 30;

  const state = {
    year: Number(localStorage.getItem("bmtc.year")) || 2027,
    classification: localStorage.getItem("bmtc.classification") === "UNVERIFIED_FEED" ? "UNVERIFIED_FEED" : "OFFICIAL_VERIFIED",
    adminKey: sessionStorage.getItem("bmtc.adminKey") || "",
    map: null,
    scenarioEditId: null,
    scenarioStops: [],
    currentRoute: null,
  };

  const view = document.getElementById("view");
  const yearStatus = document.getElementById("yearStatus");
  const yearSelect = document.getElementById("yearSelect");
  const sidebar = document.getElementById("sidebar");
  const navToggle = document.getElementById("navToggle");
  const toastEl = document.getElementById("toast");

  // ------------------------------------------------------------------ helpers
  const esc = (value) =>
    String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
    );

  const badge = (classification) => {
    const info = CLS[classification] || { label: classification, css: "neutral" };
    return `<span class="badge ${info.css}">${esc(info.label)}</span>`;
  };

  const orDash = (value, suffix) => (value === null || value === undefined || value === "" ? "n/a" : `${value}${suffix || ""}`);

  function localIsoDate(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  function defaultDate() {
    return state.year === new Date().getFullYear() ? localIsoDate(new Date()) : `${state.year}-01-01`;
  }

  function toast(message) {
    toastEl.textContent = message;
    toastEl.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { toastEl.hidden = true; }, 4500);
  }

  function clientKey() {
    let key = localStorage.getItem("bmtc.clientKey");
    if (!key || key.length < 16) {
      const bytes = new Uint8Array(24);
      crypto.getRandomValues(bytes);
      key = btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
      localStorage.setItem("bmtc.clientKey", key);
    }
    return key;
  }

  function messageFrom(data, status) {
    const detail = data && data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (item.loc && item.loc.length > 1 ? `${item.loc.slice(1).join(".")}: ` : "") + item.msg)
        .join("; ");
    }
    if (detail && typeof detail === "object") {
      return detail.message || (detail.errors || []).join("; ") || "The request failed.";
    }
    return `The request failed (${status}).`;
  }

  async function api(path, options = {}) {
    const { method = "GET", json, form, admin = false } = options;
    const headers = { "X-Client-Key": clientKey() };
    if (admin) {
      if (!state.adminKey) throw new Error("Sign in with the admin key first.");
      headers["X-Admin-Key"] = state.adminKey;
    }
    let body;
    if (form) {
      body = form;
    } else if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(json);
    }
    const response = await fetch(path, { method, headers, body });
    if (response.status === 204) return null;
    let data = null;
    try { data = await response.json(); } catch (_) { data = null; }
    if (!response.ok) {
      const error = new Error(messageFrom(data, response.status));
      error.status = response.status;
      error.data = data;
      if (response.status === 401 && admin) {
        state.adminKey = "";
        sessionStorage.removeItem("bmtc.adminKey");
      }
      throw error;
    }
    return data;
  }

  async function download(path, fallbackName) {
    const response = await fetch(path, { headers: { "X-Client-Key": clientKey() } });
    if (!response.ok) {
      let data = null;
      try { data = await response.json(); } catch (_) { data = null; }
      throw new Error(messageFrom(data, response.status));
    }
    const blob = await response.blob();
    const match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "");
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = match ? match[1] : fallbackName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  const setView = (html) => { view.innerHTML = html; };
  const loading = (text) => `<section class="card" aria-busy="true"><p class="muted">${esc(text || "Loading...")}</p></section>`;
  const errorCard = (err) =>
    `<section class="card"><div class="banner error" role="alert"><strong>Something went wrong</strong>${esc(err.message || err)}</div></section>`;

  function segmentedClassification() {
    const pressed = (cls) => (state.classification === cls ? "true" : "false");
    return `<div class="seg" role="group" aria-label="Data classification">
      <button type="button" data-action="cls" data-cls="OFFICIAL_VERIFIED" aria-pressed="${pressed("OFFICIAL_VERIFIED")}">Official verified</button>
      <button type="button" data-action="cls" data-cls="UNVERIFIED_FEED" aria-pressed="${pressed("UNVERIFIED_FEED")}">Unverified feed</button>
    </div>`;
  }

  // ------------------------------------------------------------------ year banner (always visible)
  async function renderYearStatus() {
    try {
      const data = await api(`/api/years/${state.year}/status`);
      yearStatus.innerHTML = `
        <div class="banner official"><strong>${badge("OFFICIAL_VERIFIED")} ${esc(state.year)}</strong>${esc(data.official.message)}</div>
        <div class="banner unverified"><strong>${badge("UNVERIFIED_FEED")} ${esc(state.year)}</strong>${esc(data.unverified.message)}</div>
        <div class="banner scenario"><strong>${badge("ESTIMATED_SCENARIO")}</strong>${esc(SCENARIO_NOTICE)}</div>`;
    } catch (err) {
      yearStatus.innerHTML = `<div class="banner error">${esc(err.message)}</div>`;
    }
  }

  // ------------------------------------------------------------------ map helpers
  function makeMap(elementId) {
    if (state.map) {
      state.map.remove();
      state.map = null;
    }
    const element = document.getElementById(elementId);
    if (!element || typeof L === "undefined") return null;
    const map = L.map(element, { scrollWheelZoom: false }).setView([20, 0], 2);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    state.map = map;
    return map;
  }

  function drawRouteMap(detail) {
    const map = makeMap("routeMap");
    if (!map) return;
    const bounds = [];
    detail.shapes.forEach((shape) => {
      if (shape.points.length > 1) {
        L.polyline(shape.points, { color: "#0b5cad", weight: 4, opacity: 0.8 }).addTo(map);
        shape.points.forEach((p) => bounds.push(p));
      }
    });
    detail.directions.forEach((direction, index) => {
      direction.stops.forEach((stop) => {
        if (stop.lat === null || stop.lon === null) return;
        const point = [stop.lat, stop.lon];
        bounds.push(point);
        L.circleMarker(point, {
          radius: index === 0 ? 5 : 4,
          color: index === 0 ? "#1b7f4c" : "#9a5b00",
          fillOpacity: 0.9,
        }).bindTooltip(esc(stop.name)).addTo(map);
      });
    });
    if (bounds.length) map.fitBounds(L.latLngBounds(bounds), { padding: [18, 18] });
  }

  function plotStops(stops) {
    if (!state.map) return;
    const bounds = [];
    stops.forEach((stop) => {
      if (stop.lat === null || stop.lon === null) return;
      const point = [stop.lat, stop.lon];
      bounds.push(point);
      L.circleMarker(point, { radius: 5, color: "#0b5cad", fillOpacity: 0.85 })
        .bindTooltip(esc(stop.name))
        .addTo(state.map);
    });
    if (bounds.length) state.map.fitBounds(L.latLngBounds(bounds), { padding: [24, 24], maxZoom: 16 });
  }

  // ------------------------------------------------------------------ routes and timetables
  const routeItem = (r) => `<li>
    <div><div class="title">${esc(r.short_name || r.gtfs_route_id)}</div><div class="muted">${esc(r.long_name || "")}</div></div>
    <div class="row-actions">${badge(r.classification)}<a class="button secondary" href="#/routes/${esc(r.id)}">Open</a></div>
  </li>`;

  async function renderRoutes(routeId) {
    if (routeId) return renderRouteDetail(routeId);
    setView(`
      <section class="card">
        <h2>Routes and timetables</h2>
        <p class="muted">Showing ${esc(CLS[state.classification].label)} data whose feed covers ${esc(state.year)}. The two classifications are never combined.</p>
        ${segmentedClassification()}
        <form id="routeSearch" class="toolbar" role="search" style="margin-top:12px">
          <label style="flex:1 1 240px">Route number or name
            <input name="q" type="search" maxlength="80" autocomplete="off" placeholder="Type a route number or part of its name">
          </label>
          <button type="submit">Search</button>
        </form>
        <div id="routeResults" style="margin-top:12px"></div>
      </section>
      <section class="card"><h2>Saved routes</h2><div id="savedRoutes">${loading()}</div></section>`);
    await Promise.all([loadRouteResults(""), loadSaved()]);
  }

  async function loadRouteResults(q) {
    const box = document.getElementById("routeResults");
    if (!box) return;
    box.innerHTML = loading("Searching...");
    const params = new URLSearchParams({ classification: state.classification, year: String(state.year), q, limit: "100" });
    const data = await api(`/api/routes?${params}`);
    if (data.results.length) {
      box.innerHTML = `<ul class="list">${data.results.map(routeItem).join("")}</ul>`;
    } else {
      const message = data.coverage && data.coverage.status === "NONE" ? data.coverage.message : "No routes match this search.";
      box.innerHTML = `<div class="empty">${esc(message)}</div>`;
    }
  }

  async function loadSaved() {
    const box = document.getElementById("savedRoutes");
    if (!box) return;
    const data = await api("/api/saved-routes");
    box.innerHTML = data.saved.length
      ? `<ul class="list">${data.saved.map((s) => `<li>
          <div><div class="title">${esc(s.label)}</div><div class="muted">${esc(s.gtfs_route_id)}</div></div>
          <div class="row-actions">${badge(s.classification)}
            <button type="button" class="secondary" data-action="open-saved" data-gtfs="${esc(s.gtfs_route_id)}" data-cls="${esc(s.classification)}">Open</button>
            <button type="button" class="danger" data-action="del-saved" data-id="${esc(s.id)}">Remove</button>
          </div></li>`).join("")}</ul>`
      : `<div class="empty">No saved routes yet. Open a route and choose Save route.</div>`;
  }

  async function renderRouteDetail(routeId) {
    setView(loading("Loading route..."));
    const detail = await api(`/api/routes/${encodeURIComponent(routeId)}`);
    state.currentRoute = detail;
    const title = `${detail.short_name || detail.gtfs_route_id}${detail.long_name ? " - " + detail.long_name : ""}`;
    const directions = detail.directions.length
      ? detail.directions.map((d) => `
          <h3>${d.direction_id === null ? "Single direction" : "Direction " + esc(d.direction_id)}${d.headsign ? " towards " + esc(d.headsign) : ""}</h3>
          <div class="table-wrap"><table>
            <thead><tr><th class="num">#</th><th>Stop</th><th>Arrival</th><th>Departure</th></tr></thead>
            <tbody>${d.stops.map((s) => `<tr><td class="num">${esc(s.sequence)}</td><td>${esc(s.name)}</td><td>${esc(s.arrival || "")}</td><td>${esc(s.departure || "")}</td></tr>`).join("")}</tbody>
          </table></div>`).join("")
      : `<div class="empty">The feed has no stops for this route.</div>`;

    setView(`
      <section class="card">
        <p><a href="#/routes">&larr; Back to routes</a></p>
        <h2>${esc(title)}</h2>
        <p>${badge(detail.classification)}</p>
        <p class="muted">Operating days (calendar.txt): ${esc(detail.operating_days.join(", ") || "not stated")}</p>
        <p class="muted">${esc(detail.geometry_note)}</p>
        <div id="routeMap" class="map" role="img" aria-label="Map of this route's stops and planned path"></div>
        <div class="toolbar">
          <label class="field">Timetable date<input type="date" id="ttDate" value="${esc(defaultDate())}"></label>
          <button type="button" data-action="tt-load" data-id="${esc(detail.id)}">Show timetable</button>
          <button type="button" class="secondary" data-action="tt-csv" data-id="${esc(detail.id)}">Download CSV</button>
          <button type="button" class="secondary" data-action="save-route" data-gtfs="${esc(detail.gtfs_route_id)}" data-cls="${esc(detail.classification)}" data-label="${esc(title)}">Save route</button>
        </div>
        <div id="timetable" style="margin-top:12px"></div>
      </section>
      <section class="card"><h2>Stops by direction</h2>${directions}</section>`);
    drawRouteMap(detail);
    await loadTimetable(detail.id);
  }

  async function loadTimetable(routeId) {
    const date = document.getElementById("ttDate").value;
    const box = document.getElementById("timetable");
    box.innerHTML = loading("Loading timetable...");
    const data = await api(`/api/routes/${encodeURIComponent(routeId)}/timetable?date=${encodeURIComponent(date)}`);
    if (!data.covered || !data.trips.length) {
      const tone = data.classification === "OFFICIAL_VERIFIED" ? "official" : "unverified";
      box.innerHTML = `<div class="banner ${tone}">${esc(data.message || "No trips on this date.")}</div>`;
      return;
    }
    const shown = data.trips.slice(0, MAX_TRIPS_SHOWN);
    box.innerHTML = `
      <p class="muted">${esc(data.trips.length)} trip(s) on ${esc(date)}. First departure ${esc(data.first_departure || "n/a")}; last arrival ${esc(data.last_arrival || "n/a")}.
        ${data.trips.length > MAX_TRIPS_SHOWN ? `Showing the first ${MAX_TRIPS_SHOWN}. Download the CSV for every trip.` : ""}</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Trip</th><th>Towards</th><th>First departure</th><th>Last arrival</th><th class="num">Stops</th></tr></thead>
        <tbody>${shown.map((t) => `<tr><td>${esc(t.trip_id)}</td><td>${esc(t.headsign || "")}</td><td>${esc(t.first_departure || "")}</td><td>${esc(t.last_arrival || "")}</td><td class="num">${esc(t.stops.length)}</td></tr>`).join("")}</tbody>
      </table></div>`;
  }

  // ------------------------------------------------------------------ stops
  async function renderStops() {
    setView(`
      <section class="card">
        <h2>Stops</h2>
        <p class="muted">Stops from official and unverified data are searched separately.</p>
        ${segmentedClassification()}
        <form id="stopSearch" class="toolbar" role="search" style="margin-top:12px">
          <label style="flex:1 1 240px">Stop name
            <input name="q" type="search" maxlength="80" autocomplete="off" placeholder="Type part of a stop name">
          </label>
          <button type="submit">Search</button>
          <button type="button" class="secondary" data-action="nearby-me">Stops near me</button>
        </form>
        <div id="stopMap" class="map" role="img" aria-label="Map of stops"></div>
        <div id="stopResults"></div>
      </section>`);
    makeMap("stopMap");
    await loadStops("");
  }

  function stopList(stops, showDistance) {
    if (!stops.length) return `<div class="empty">No stops found for this classification and search.</div>`;
    return `<ul class="list">${stops.map((s) => `<li>
      <div><div class="title">${esc(s.name)}</div>
      <div class="muted">${s.lat === null ? "No coordinates in feed" : esc(s.lat.toFixed(5)) + ", " + esc(s.lon.toFixed(5))}${showDistance ? " - " + esc(s.distance_m) + " m away" : ""}</div></div>
      <div class="row-actions">${badge(s.classification)}</div></li>`).join("")}</ul>`;
  }

  async function loadStops(q) {
    const box = document.getElementById("stopResults");
    if (!box) return;
    const params = new URLSearchParams({ classification: state.classification, year: String(state.year), q, limit: "100" });
    const data = await api(`/api/stops?${params}`);
    box.innerHTML = stopList(data.results, false);
    if (state.map) {
      state.map.eachLayer((layer) => { if (layer instanceof L.CircleMarker) state.map.removeLayer(layer); });
      plotStops(data.results);
    }
  }

  async function nearbyStops() {
    if (!navigator.geolocation) {
      toast("Your browser cannot share its location. Search by stop name instead.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const { latitude, longitude } = position.coords;
          const params = new URLSearchParams({
            lat: String(latitude), lon: String(longitude), radius_m: "800",
            classification: state.classification, limit: "50",
          });
          const data = await api(`/api/stops/nearby?${params}`);
          document.getElementById("stopResults").innerHTML = stopList(data.results, true);
          if (state.map) {
            state.map.eachLayer((layer) => { if (layer instanceof L.CircleMarker) state.map.removeLayer(layer); });
            L.circleMarker([latitude, longitude], { radius: 7, color: "#b3261e", fillOpacity: 0.9 }).addTo(state.map).bindTooltip("You are here");
            plotStops(data.results);
          }
        } catch (err) {
          toast(err.message);
        }
      },
      () => toast("Location permission was not given. Search by stop name instead."),
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 }
    );
  }

  // ------------------------------------------------------------------ direct journeys
  function renderJourney() {
    setView(`
      <section class="card">
        <h2>Direct journeys</h2>
        <p class="muted">Finds direct trips only. Trips that need a change are not calculated.</p>
        ${segmentedClassification()}
        <form id="journeyForm" class="form-grid" style="margin-top:12px">
          <label class="field">From (stop name)<input name="origin" required minlength="2" maxlength="80" autocomplete="off"></label>
          <label class="field">To (stop name)<input name="destination" required minlength="2" maxlength="80" autocomplete="off"></label>
          <label class="field">Date<input name="date" type="date" required value="${esc(defaultDate())}"></label>
          <div style="align-self:end"><button type="submit">Find direct trips</button></div>
        </form>
        <div id="journeyResults" style="margin-top:12px"></div>
      </section>`);
  }

  // ------------------------------------------------------------------ scenarios
  async function renderScenarios() {
    state.scenarioEditId = null;
    state.scenarioStops = [];
    setView(`
      <section class="card">
        <div class="banner scenario"><strong>${badge("ESTIMATED_SCENARIO")} Permanent label</strong>${esc(SCENARIO_NOTICE)}</div>
        <p class="muted" style="margin-top:10px">Scenarios belong to this browser's device key. Clearing site data, or using another browser, will hide them.</p>
        <div class="toolbar">
          <label class="field">Year filter
            <select id="scnYearFilter">
              <option value="">All planning years</option>
              ${PLANNING_YEARS.map((y) => `<option value="${y}">${y}</option>`).join("")}
            </select>
          </label>
          <button type="button" data-action="scn-new">New scenario</button>
          <button type="button" class="secondary" data-action="scn-csv">Export CSV</button>
        </div>
      </section>
      <section id="scnForm" class="card" hidden></section>
      <section class="card"><h2>Your scenarios</h2><div id="scnList">${loading()}</div></section>`);
    await loadScenarioList();
  }

  function scenarioItem(s) {
    const e = s.estimate;
    return `<li>
      <div>
        <div class="title">${esc(s.name)} <span class="muted">- ${esc(s.year)} - proposed route ${esc(s.route_code)}</span></div>
        <div class="muted">${esc(s.origin.name)} to ${esc(s.destination.name)} - ${esc(s.first_departure)} to ${esc(s.last_departure)}, every ${esc(s.frequency_minutes)} min - ${esc(s.operating_days.join(" "))}</div>
        <div class="muted">Estimate: ${esc(e.departures_per_day)} departures a day - distance ${esc(orDash(e.estimated_distance_km, " km"))} - journey ${esc(orDash(e.estimated_journey_minutes, " min"))}</div>
      </div>
      <div class="row-actions">${badge("ESTIMATED_SCENARIO")}
        <button type="button" class="secondary" data-action="scn-edit" data-id="${esc(s.id)}">Edit</button>
        <button type="button" class="secondary" data-action="scn-pdf" data-id="${esc(s.id)}">PDF</button>
        <button type="button" class="danger" data-action="scn-del" data-id="${esc(s.id)}">Delete</button>
      </div></li>`;
  }

  async function loadScenarioList() {
    const filter = document.getElementById("scnYearFilter");
    const year = filter ? filter.value : "";
    const data = await api(`/api/scenarios${year ? "?year=" + encodeURIComponent(year) : ""}`);
    const box = document.getElementById("scnList");
    box.innerHTML = data.scenarios.length
      ? `<ul class="list">${data.scenarios.map(scenarioItem).join("")}</ul>`
      : `<div class="empty">${esc(data.message || "No scenarios yet. Choose New scenario to create one.")}</div>`;
  }

  function scenarioFormHtml(s) {
    const v = s || {};
    const days = v.operating_days || ["MON", "TUE", "WED", "THU", "FRI"];
    const yearOptions = PLANNING_YEARS.map((y) => `<option value="${y}" ${Number(v.year || state.year) === y ? "selected" : ""}>${y}</option>`).join("");
    const coord = (value) => (value === null || value === undefined ? "" : String(value));
    return `
      <h2>${s ? "Edit scenario" : "New scenario"}</h2>
      <p class="muted">Use illustrative numbers. Coordinates are optional, but they are needed for a distance and journey-time estimate.</p>
      <form id="scenarioForm" novalidate>
        <div class="form-grid">
          <label class="field">Name<input name="name" maxlength="120" required value="${esc(v.name || "")}"></label>
          <label class="field">Planning year<select name="year">${yearOptions}</select></label>
          <label class="field">Proposed route code<input name="route_code" maxlength="20" required value="${esc(v.route_code || "")}" placeholder="for example PROP-001"></label>
          <label class="field">Frequency (minutes)<input name="frequency_minutes" type="number" min="1" max="240" required value="${esc(v.frequency_minutes || 15)}"></label>
          <label class="field">First departure<input name="first_departure" type="time" required value="${esc(v.first_departure || "06:00")}"></label>
          <label class="field">Last departure<input name="last_departure" type="time" required value="${esc(v.last_departure || "22:00")}"></label>
        </div>
        <fieldset class="card" style="margin-top:12px">
          <legend>Origin and destination</legend>
          <div class="form-grid">
            <label class="field">Origin name<input name="origin_name" maxlength="200" required value="${esc(v.origin ? v.origin.name : "")}"></label>
            <label class="field">Origin latitude<input name="origin_lat" type="number" step="any" min="-90" max="90" value="${esc(coord(v.origin ? v.origin.lat : null))}"></label>
            <label class="field">Origin longitude<input name="origin_lon" type="number" step="any" min="-180" max="180" value="${esc(coord(v.origin ? v.origin.lon : null))}"></label>
            <label class="field">Destination name<input name="destination_name" maxlength="200" required value="${esc(v.destination ? v.destination.name : "")}"></label>
            <label class="field">Destination latitude<input name="destination_lat" type="number" step="any" min="-90" max="90" value="${esc(coord(v.destination ? v.destination.lat : null))}"></label>
            <label class="field">Destination longitude<input name="destination_lon" type="number" step="any" min="-180" max="180" value="${esc(coord(v.destination ? v.destination.lon : null))}"></label>
          </div>
        </fieldset>
        <fieldset style="margin-top:12px; border:0; padding:0">
          <legend class="field">Operating days</legend>
          <div class="checks">${DAYS.map((d) => `<label><input type="checkbox" name="days" value="${d}" ${days.includes(d) ? "checked" : ""}> ${DAY_LABELS[d]}</label>`).join("")}</div>
        </fieldset>
        <h3>Intermediate stops (optional, up to ${MAX_SCENARIO_STOPS})</h3>
        <div id="scnStops"></div>
        <div class="toolbar" style="margin-top:8px"><button type="button" class="secondary" data-action="scn-add-stop">Add stop</button></div>
        <label class="field" style="margin-top:12px">Notes<textarea name="description" maxlength="1000">${esc(v.description || "")}</textarea></label>
        <div class="toolbar" style="margin-top:14px">
          <button type="submit">${s ? "Save changes" : "Create scenario"}</button>
          <button type="button" class="secondary" data-action="scn-cancel">Cancel</button>
        </div>
        <div id="scnError" class="banner error" role="alert" hidden></div>
      </form>`;
  }

  function syncStopsFromDom() {
    const inputs = document.querySelectorAll("#scnStops [data-stop]");
    if (!inputs.length) return;
    const stops = state.scenarioStops.map((stop) => ({ ...stop }));
    inputs.forEach((input) => {
      const index = Number(input.dataset.stop);
      if (!stops[index]) return;
      const raw = input.value.trim();
      if (input.dataset.field === "name") stops[index].name = raw;
      else stops[index][input.dataset.field] = raw === "" ? null : Number(raw);
    });
    state.scenarioStops = stops;
  }

  function renderScenarioStops() {
    const box = document.getElementById("scnStops");
    if (!state.scenarioStops.length) {
      box.innerHTML = `<p class="muted">No intermediate stops.</p>`;
      return;
    }
    box.innerHTML = `<div class="form-grid">${state.scenarioStops.map((stop, i) => `
      <div class="card" style="margin:0">
        <label class="field">Stop ${i + 1} name<input data-stop="${i}" data-field="name" maxlength="200" value="${esc(stop.name || "")}"></label>
        <div class="form-grid" style="margin-top:8px">
          <label class="field">Latitude<input data-stop="${i}" data-field="lat" type="number" step="any" min="-90" max="90" value="${esc(stop.lat === null || stop.lat === undefined ? "" : stop.lat)}"></label>
          <label class="field">Longitude<input data-stop="${i}" data-field="lon" type="number" step="any" min="-180" max="180" value="${esc(stop.lon === null || stop.lon === undefined ? "" : stop.lon)}"></label>
        </div>
        <button type="button" class="danger" data-action="scn-remove-stop" data-index="${i}" style="margin-top:8px">Remove stop</button>
      </div>`).join("")}</div>`;
  }

  async function openScenarioForm(id) {
    const box = document.getElementById("scnForm");
    let scenario = null;
    state.scenarioEditId = id || null;
    if (id) scenario = await api(`/api/scenarios/${encodeURIComponent(id)}`);
    state.scenarioStops = scenario ? scenario.stops.map((s) => ({ name: s.name, lat: s.lat, lon: s.lon })) : [];
    box.innerHTML = scenarioFormHtml(scenario);
    box.hidden = false;
    renderScenarioStops();
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function readScenarioForm(form) {
    syncStopsFromDom();
    const f = new FormData(form);
    const number = (key) => {
      const raw = String(f.get(key) || "").trim();
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
        .filter((stop) => stop.name && stop.name.trim())
        .map((stop) => ({ name: stop.name.trim(), lat: stop.lat ?? null, lon: stop.lon ?? null })),
    };
  }

  async function submitScenario(form) {
    const errorBox = document.getElementById("scnError");
    errorBox.hidden = true;
    const body = readScenarioForm(form);
    try {
      const result = state.scenarioEditId
        ? await api(`/api/scenarios/${encodeURIComponent(state.scenarioEditId)}`, { method: "PUT", json: body })
        : await api("/api/scenarios", { method: "POST", json: body });
      document.getElementById("scnForm").hidden = true;
      toast(result.warnings ? `Saved. ${result.warnings.join(" ")}` : "Scenario saved. It is labelled ESTIMATED_SCENARIO.");
      await loadScenarioList();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
    }
  }

  // ------------------------------------------------------------------ compare
  async function renderCompare() {
    setView(`
      <section class="card">
        <div class="banner scenario"><strong>${badge("ESTIMATED_SCENARIO")}</strong>${esc(SCENARIO_NOTICE)}</div>
        <h2 style="margin-top:12px">Compare two scenarios</h2>
        <div class="toolbar">
          <label class="field">Scenario A<select id="cmpA"></select></label>
          <label class="field">Scenario B<select id="cmpB"></select></label>
          <button type="button" data-action="cmp-run">Compare</button>
          <button type="button" class="secondary" data-action="cmp-pdf">Export PDF</button>
        </div>
        <div id="cmpResult" style="margin-top:12px"></div>
      </section>
      <section class="card"><h2>Compare planning years</h2><div id="yearsCompare">${loading()}</div></section>`);
    const data = await api("/api/scenarios");
    const options = data.scenarios.map((s) => `<option value="${esc(s.id)}">${esc(s.name)} (${esc(s.year)})</option>`).join("");
    document.getElementById("cmpA").innerHTML = options;
    document.getElementById("cmpB").innerHTML = options;
    if (data.scenarios.length < 2) {
      document.getElementById("cmpResult").innerHTML = `<div class="empty">Create at least two scenarios to compare them.</div>`;
    }
    await loadYearsCompare();
  }

  async function loadYearsCompare() {
    const data = await api("/api/years/compare");
    const cell = (cov) => `${badge(cov.classification)}<div class="muted">${esc(cov.message)}</div>`;
    document.getElementById("yearsCompare").innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr><th>Year</th><th>Official verified</th><th>Unverified feed</th><th class="num">Your scenarios</th></tr></thead>
        <tbody>${data.years.map((y) => `<tr>
          <td><strong>${esc(y.year)}</strong></td>
          <td>${cell(y.official)}</td>
          <td>${cell(y.unverified)}</td>
          <td class="num">${esc(y.your_scenarios)}</td></tr>`).join("")}</tbody>
      </table></div>`;
  }

  async function runComparison() {
    const a = document.getElementById("cmpA").value;
    const b = document.getElementById("cmpB").value;
    if (!a || !b) return toast("Choose two scenarios first.");
    const data = await api(`/api/scenarios/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
    const row = (label, key, unit) => `<tr><td>${esc(label)}</td>
      <td class="num">${esc(orDash(data.a.estimate[key], unit))}</td>
      <td class="num">${esc(orDash(data.b.estimate[key], unit))}</td>
      <td class="num">${esc(orDash(data.difference_b_minus_a[key], unit))}</td></tr>`;
    document.getElementById("cmpResult").innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr><th>Estimate</th><th class="num">${esc(data.a.scenario.name)}</th><th class="num">${esc(data.b.scenario.name)}</th><th class="num">Difference (B minus A)</th></tr></thead>
        <tbody>
          ${row("Distance", "estimated_distance_km", " km")}
          ${row("Journey time", "estimated_journey_minutes", " min")}
          ${row("Departures per day", "departures_per_day", "")}
          ${row("Departures per week", "departures_per_week", "")}
        </tbody>
      </table></div>
      <p class="muted">${esc(data.notice)}</p>`;
  }

  // ------------------------------------------------------------------ data sources (public)
  async function renderSources() {
    setView(loading("Loading data sources..."));
    const data = await api("/api/data-sources");
    const list = data.sources.length
      ? data.sources.map((s) => `<li>
          <div>
            <div class="title">${esc(s.name)}</div>
            <div class="muted">Publisher: ${esc(s.publisher)} - licence: ${esc(s.license)} - kind: ${esc(s.kind)}</div>
            <div class="muted">${s.source_url ? `<a href="${esc(s.source_url)}" rel="noopener noreferrer">${esc(s.source_url)}</a>` : "No source link recorded"}</div>
            <div class="muted">${s.verified ? `Verified${s.verified_at ? " on " + esc(s.verified_at.slice(0, 10)) : ""}.` : "Not verified by an administrator."} Completed imports: ${esc(s.completed_imports)}.</div>
          </div>
          <div class="row-actions">${badge(s.classification)}</div></li>`).join("")
      : `<div class="empty">No data sources have been registered yet.</div>`;
    setView(`
      <section class="card">
        <h2>Data-source information</h2>
        <dl class="kv">
          <dt>${badge("OFFICIAL_VERIFIED")}</dt><dd>Confirmed through an authoritative source and verified by an administrator.</dd>
          <dt>${badge("UNVERIFIED_FEED")}</dt><dd>From a third-party, community or unverified feed. Shown separately and labelled.</dd>
          <dt>${badge("ESTIMATED_SCENARIO")}</dt><dd>Proposed or simulated future services. Never an official announcement.</dd>
        </dl>
        <h3>Sources in use</h3>
        <ul class="list">${list}</ul>
      </section>
      <section class="card">
        <h2>What this app does not use</h2>
        <p class="muted">Unofficial reverse-engineered app APIs, scraped app data and community datasets built from them are not used as official sources. The planner never invents routes, timings, bus positions or announcements. Live bus positions are not shown because no authorised live feed is connected.</p>
      </section>`);
  }

  // ------------------------------------------------------------------ administration
  async function renderAdmin() {
    const meta = await api("/api/meta");
    if (!meta.admin_enabled) {
      setView(`<section class="card"><h2>Administration</h2><div class="banner error">Administration is disabled. Set ADMIN_API_KEY in the server's .env file and restart the server.</div></section>`);
      return;
    }
    setView(`
      <section class="card">
        <h2>Administrator sign-in</h2>
        <p class="muted">The key is kept only for this browser session.</p>
        <div class="toolbar">
          <label class="field" style="flex:1 1 260px">Admin key<input id="adminKeyInput" type="password" autocomplete="off"></label>
          <button type="button" data-action="admin-key-save">Save key</button>
          <button type="button" class="secondary" data-action="admin-key-clear">Forget key</button>
        </div>
      </section>
      <div id="adminBody"></div>`);
    if (state.adminKey) {
      await loadAdmin();
    } else {
      document.getElementById("adminBody").innerHTML = `<div class="empty">Enter the admin key to manage data sources and imports.</div>`;
    }
  }

  async function loadAdmin() {
    const body = document.getElementById("adminBody");
    body.innerHTML = `
      <section class="card"><h2>Data sources</h2><div id="adminSources">${loading()}</div>
        <h3>Add a data source</h3>
        <form id="sourceForm" class="form-grid">
          <label class="field">Name<input name="name" required maxlength="200"></label>
          <label class="field">Publisher<input name="publisher" required maxlength="200"></label>
          <label class="field">Source link (https)<input name="source_url" type="url" maxlength="500" placeholder="https://"></label>
          <label class="field">Licence<input name="license" maxlength="200" value="Not specified"></label>
          <label class="field">Kind<select name="kind">
            <option value="OFFICIAL">OFFICIAL</option><option value="COMMUNITY">COMMUNITY</option>
            <option value="SYNTHETIC_DEMO">SYNTHETIC_DEMO</option><option value="UNKNOWN">UNKNOWN</option>
          </select></label>
          <div style="align-self:end"><button type="submit">Add source</button></div>
        </form>
      </section>
      <section class="card"><h2>Upload a GTFS ZIP</h2>
        <p class="muted">Only import a feed after you have confirmed its publisher and licence. Every feed is validated before anything is stored. A feed becomes OFFICIAL_VERIFIED only when its source is an OFFICIAL source that has been verified.</p>
        <form id="uploadForm" class="form-grid">
          <label class="field">Data source<select name="data_source_id" id="uploadSource" required></select></label>
          <label class="field">GTFS ZIP file<input name="file" type="file" accept=".zip,application/zip" required></label>
          <div style="align-self:end"><button type="submit">Validate and import</button></div>
        </form>
        <div id="uploadResult" style="margin-top:12px"></div>
      </section>
      <section class="card"><h2>Imports</h2><div id="adminImports">${loading()}</div></section>
      <section class="card"><h2>Database and backups</h2><div id="adminStats">${loading()}</div>
        <div class="toolbar" style="margin-top:8px"><button type="button" class="secondary" data-action="backup">Create backup (SQLite)</button></div>
      </section>
      <section class="card"><h2>Audit log</h2><div id="adminAudit">${loading()}</div></section>`;

    try {
      const [sources, imports, stats, audit] = await Promise.all([
        api("/api/admin/data-sources", { admin: true }),
        api("/api/admin/imports", { admin: true }),
        api("/api/admin/stats", { admin: true }),
        api("/api/admin/audit-logs?limit=50", { admin: true }),
      ]);
      renderAdminSources(sources.sources);
      document.getElementById("uploadSource").innerHTML = sources.sources
        .map((s) => `<option value="${esc(s.id)}">${esc(s.name)} (${esc(s.kind)})</option>`).join("");
      renderAdminImports(imports.imports);
      renderAdminStats(stats);
      renderAdminAudit(audit.entries);
    } catch (err) {
      toast(err.message);
      document.getElementById("adminBody").insertAdjacentHTML("afterbegin", `<div class="banner error">${esc(err.message)}</div>`);
    }
  }

  function renderAdminSources(sources) {
    const rows = sources.map((s) => `<tr>
      <td>${esc(s.id)}</td><td>${esc(s.name)}<div class="muted">${esc(s.publisher)}</div></td>
      <td>${esc(s.kind)}</td><td>${badge(s.classification)}</td>
      <td>${s.verified ? "Verified" : "Not verified"}${s.admin_note ? `<div class="muted">${esc(s.admin_note)}</div>` : ""}</td>
      <td class="row-actions">${s.verified
        ? `<button type="button" class="danger" data-action="src-revoke" data-id="${esc(s.id)}">Revoke</button>`
        : `<button type="button" class="secondary" data-action="src-verify" data-id="${esc(s.id)}" ${s.kind === "OFFICIAL" ? "" : "disabled title=\"Only OFFICIAL sources can be verified\""}>Verify</button>`}</td>
    </tr>`).join("");
    document.getElementById("adminSources").innerHTML = sources.length
      ? `<div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Kind</th><th>Classification</th><th>Status</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="empty">No data sources yet. Add one below.</div>`;
  }

  function importSummaryHtml(s) {
    const problems = `${s.errors.length} error(s), ${s.warnings.length} warning(s)`;
    return `<div class="card" style="margin:0">
      <div class="title">${esc(s.filename)} ${badge(s.classification)} <span class="badge ${s.status === "COMPLETED" ? "official" : "unverified"}">${esc(s.status)}</span></div>
      <div class="muted">Routes ${esc(s.routes)} - stops ${esc(s.stops)} - trips ${esc(s.trips)} - stop times ${esc(s.stop_times)} - feed dates ${esc(s.feed_start_date || "n/a")} to ${esc(s.feed_end_date || "n/a")}</div>
      <details style="margin-top:6px"><summary>${esc(problems)}</summary>
        <ul>${s.errors.map((e) => `<li>${esc(e)}</li>`).join("")}${s.warnings.map((w) => `<li class="muted">${esc(w)}</li>`).join("")}</ul>
      </details></div>`;
  }

  function renderAdminImports(imports) {
    const box = document.getElementById("adminImports");
    box.innerHTML = imports.length
      ? `<div class="grid-2">${imports.map((s) => `${importSummaryHtml(s)}
          <div class="row-actions" style="margin-bottom:12px"><button type="button" class="danger" data-action="import-delete" data-id="${esc(s.id)}">Delete import ${esc(s.id)}</button></div>`).join("")}</div>`
      : `<div class="empty">No imports yet.</div>`;
  }

  function renderAdminStats(stats) {
    const c = stats.counts;
    const pairs = [
      ["Data sources", c.data_sources], ["Completed imports", c.imports_completed], ["Rejected imports", c.imports_rejected],
      ["Routes", c.routes], ["Stops", c.stops], ["Trips", c.trips], ["Stop times", c.stop_times],
      ["Shape points", c.shape_points], ["Scenarios (all devices)", c.scenarios], ["Audit entries", c.audit_entries],
    ];
    document.getElementById("adminStats").innerHTML = `<dl class="kv">${pairs.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
      <p class="muted">Database: ${esc(stats.database)}. Active imports: official ${esc(stats.active_imports_by_classification.OFFICIAL_VERIFIED)}, unverified ${esc(stats.active_imports_by_classification.UNVERIFIED_FEED)}.</p>`;
  }

  function renderAdminAudit(entries) {
    document.getElementById("adminAudit").innerHTML = entries.length
      ? `<div class="table-wrap"><table><thead><tr><th>Time (UTC)</th><th>Actor</th><th>Action</th><th>Entity</th><th>Detail</th></tr></thead><tbody>${entries.map((e) => `<tr>
          <td>${esc(e.time.replace("T", " ").slice(0, 19))}</td><td>${esc(e.actor)}</td><td>${esc(e.action)}</td>
          <td>${esc(e.entity)} ${esc(e.entity_id || "")}</td><td class="muted">${esc(e.detail || "")}</td></tr>`).join("")}</tbody></table></div>`
      : `<div class="empty">No audit entries yet.</div>`;
  }

  // ------------------------------------------------------------------ routing and events
  const ROUTE_HANDLERS = {
    routes: (rest) => renderRoutes(rest[0]),
    stops: () => renderStops(),
    journey: () => renderJourney(),
    scenarios: () => renderScenarios(),
    compare: () => renderCompare(),
    sources: () => renderSources(),
    admin: () => renderAdmin(),
  };

  async function render() {
    const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
    const name = parts[0] && ROUTE_HANDLERS[parts[0]] ? parts[0] : "routes";
    document.querySelectorAll("[data-nav]").forEach((link) => {
      if (link.getAttribute("href") === `#/${name}`) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    sidebar.classList.remove("open");
    navToggle.setAttribute("aria-expanded", "false");
    renderYearStatus();
    try {
      await ROUTE_HANDLERS[name](parts.slice(1));
    } catch (err) {
      setView(errorCard(err));
    }
  }

  const ACTIONS = {
    cls(el) {
      state.classification = el.dataset.cls === "UNVERIFIED_FEED" ? "UNVERIFIED_FEED" : "OFFICIAL_VERIFIED";
      localStorage.setItem("bmtc.classification", state.classification);
      render();
    },
    async "tt-load"(el) { await loadTimetable(el.dataset.id); },
    async "tt-csv"(el) {
      const date = document.getElementById("ttDate").value;
      await download(`/api/routes/${encodeURIComponent(el.dataset.id)}/timetable.csv?date=${encodeURIComponent(date)}`, "timetable.csv");
    },
    async "save-route"(el) {
      await api("/api/saved-routes", { method: "POST", json: { gtfs_route_id: el.dataset.gtfs, classification: el.dataset.cls, label: el.dataset.label } });
      toast("Route saved to this device.");
    },
    async "open-saved"(el) {
      const params = new URLSearchParams({ classification: el.dataset.cls, q: el.dataset.gtfs, limit: "5" });
      const data = await api(`/api/routes?${params}`);
      const exact = data.results.find((r) => r.gtfs_route_id === el.dataset.gtfs) || data.results[0];
      if (exact) location.hash = `#/routes/${exact.id}`;
      else toast("That route is no longer in the data.");
    },
    async "del-saved"(el) {
      await api(`/api/saved-routes/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE" });
      await loadSaved();
    },
    "nearby-me"() { nearbyStops(); },
    async "scn-new"() { await openScenarioForm(null); },
    async "scn-edit"(el) { await openScenarioForm(el.dataset.id); },
    async "scn-del"(el) {
      if (!window.confirm("Delete this estimated scenario? This cannot be undone.")) return;
      await api(`/api/scenarios/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE" });
      toast("Scenario deleted.");
      await loadScenarioList();
    },
    async "scn-pdf"(el) {
      await download(`/api/scenarios/${encodeURIComponent(el.dataset.id)}/export.pdf`, "estimated_scenario.pdf");
    },
    async "scn-csv"() {
      const filter = document.getElementById("scnYearFilter");
      const year = filter ? filter.value : "";
      await download(`/api/scenarios/export.csv${year ? "?year=" + encodeURIComponent(year) : ""}`, "estimated_scenarios.csv");
    },
    "scn-add-stop"() {
      syncStopsFromDom();
      if (state.scenarioStops.length >= MAX_SCENARIO_STOPS) return toast(`A scenario can have at most ${MAX_SCENARIO_STOPS} stops.`);
      state.scenarioStops.push({ name: "", lat: null, lon: null });
      renderScenarioStops();
    },
    "scn-remove-stop"(el) {
      syncStopsFromDom();
      state.scenarioStops.splice(Number(el.dataset.index), 1);
      renderScenarioStops();
    },
    "scn-cancel"() {
      document.getElementById("scnForm").hidden = true;
      state.scenarioEditId = null;
    },
    async "cmp-run"() { await runComparison(); },
    async "cmp-pdf"() {
      const a = document.getElementById("cmpA").value;
      const b = document.getElementById("cmpB").value;
      if (!a || !b) return toast("Choose two scenarios first.");
      await download(`/api/scenarios/compare.pdf?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`, "estimated_scenario_comparison.pdf");
    },
    "admin-key-save"() {
      const input = document.getElementById("adminKeyInput");
      state.adminKey = input.value.trim();
      if (!state.adminKey) return toast("Enter the admin key.");
      sessionStorage.setItem("bmtc.adminKey", state.adminKey);
      loadAdmin().catch((err) => toast(err.message));
    },
    "admin-key-clear"() {
      state.adminKey = "";
      sessionStorage.removeItem("bmtc.adminKey");
      toast("Admin key forgotten for this session.");
      renderAdmin().catch((err) => setView(errorCard(err)));
    },
    async "src-verify"(el) {
      const note = window.prompt("Record the evidence for this verification (publisher page, date checked, licence):", "");
      if (note === null) return;
      await api(`/api/admin/data-sources/${encodeURIComponent(el.dataset.id)}/verify`, { method: "POST", admin: true, json: { verified: true, note } });
      toast("Source verified. Its imports were reclassified.");
      await loadAdmin();
    },
    async "src-revoke"(el) {
      const note = window.prompt("Reason for revoking verification:", "");
      if (note === null) return;
      await api(`/api/admin/data-sources/${encodeURIComponent(el.dataset.id)}/verify`, { method: "POST", admin: true, json: { verified: false, note } });
      toast("Verification revoked. Its imports were reclassified.");
      await loadAdmin();
    },
    async "import-delete"(el) {
      if (!window.confirm("Delete this import and all of its timetable rows?")) return;
      await api(`/api/admin/imports/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE", admin: true });
      toast("Import deleted.");
      await loadAdmin();
    },
    async backup() {
      const result = await api("/api/admin/backup", { method: "POST", admin: true });
      toast(`Backup written: ${result.file}`);
      await loadAdmin();
    },
  };

  const FORMS = {
    async routeSearch(form) {
      await loadRouteResults(new FormData(form).get("q") || "");
    },
    async stopSearch(form) {
      await loadStops(new FormData(form).get("q") || "");
    },
    async journeyForm(form) {
      const f = new FormData(form);
      const box = document.getElementById("journeyResults");
      box.innerHTML = loading("Searching timetables...");
      const params = new URLSearchParams({
        origin: String(f.get("origin") || "").trim(),
        destination: String(f.get("destination") || "").trim(),
        date: String(f.get("date") || ""),
        classification: state.classification,
      });
      const data = await api(`/api/journey?${params}`);
      box.innerHTML = data.journeys.length
        ? `<p class="muted">${esc(data.note)}</p><div class="table-wrap"><table>
            <thead><tr><th>Route</th><th>Departs</th><th>Arrives</th><th class="num">Minutes</th><th>From</th><th>To</th></tr></thead>
            <tbody>${data.journeys.map((j) => `<tr><td>${esc(j.route_number)}<div class="muted">${esc(j.headsign || "")}</div></td>
              <td>${esc(j.departure)}</td><td>${esc(j.arrival)}</td><td class="num">${esc(j.duration_minutes)}</td>
              <td>${esc(j.origin_stop)}</td><td>${esc(j.destination_stop)}</td></tr>`).join("")}</tbody></table></div>`
        : `<div class="empty">${esc(data.message || "No direct service found.")}</div>`;
    },
    async scenarioForm(form) {
      await submitScenario(form);
    },
    async sourceForm(form) {
      const f = new FormData(form);
      await api("/api/admin/data-sources", {
        method: "POST", admin: true,
        json: {
          name: f.get("name"), publisher: f.get("publisher"),
          source_url: String(f.get("source_url") || "").trim() || null,
          license: String(f.get("license") || "Not specified"), kind: f.get("kind"),
        },
      });
      toast("Data source added. It is unverified until an administrator verifies it.");
      await loadAdmin();
    },
    async uploadForm(form) {
      const box = document.getElementById("uploadResult");
      box.innerHTML = loading("Validating and importing the feed...");
      try {
        const data = await api("/api/admin/imports", { method: "POST", admin: true, form: new FormData(form) });
        box.innerHTML = importSummaryHtml(data.import);
        toast("Feed imported.");
      } catch (err) {
        if (err.data && err.data.import) {
          box.innerHTML = importSummaryHtml(err.data.import);
          toast("The feed was rejected. Review the errors below.");
        } else {
          box.innerHTML = `<div class="banner error">${esc(err.message)}</div>`;
        }
      }
      await loadAdmin();
    },
  };

  document.addEventListener("click", (event) => {
    const el = event.target.closest("[data-action]");
    if (!el || el.disabled) return;
    const handler = ACTIONS[el.dataset.action];
    if (!handler) return;
    event.preventDefault();
    Promise.resolve(handler(el)).catch((err) => toast(err.message));
  });

  view.addEventListener("submit", (event) => {
    const form = event.target;
    const handler = FORMS[form.id === "scenarioForm" ? "scenarioForm" : form.id];
    if (!handler) return;
    event.preventDefault();
    Promise.resolve(handler(form)).catch((err) => toast(err.message));
  });

  view.addEventListener("change", (event) => {
    if (event.target.id === "scnYearFilter") loadScenarioList().catch((err) => toast(err.message));
  });

  yearSelect.value = String(state.year);
  yearSelect.addEventListener("change", () => {
    state.year = Number(yearSelect.value);
    localStorage.setItem("bmtc.year", String(state.year));
    render();
  });

  navToggle.addEventListener("click", () => {
    const open = sidebar.classList.toggle("open");
    navToggle.setAttribute("aria-expanded", String(open));
  });

  window.addEventListener("hashchange", render);
  window.addEventListener("unhandledrejection", (event) => {
    if (event.reason && event.reason.message) toast(event.reason.message);
  });

  if (!location.hash) location.hash = "#/routes";
  render();

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => { /* offline shell is optional */ });
  }
})();
