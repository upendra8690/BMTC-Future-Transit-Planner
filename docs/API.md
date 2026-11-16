# API reference

The planner exposes a JSON API under `/api`. The running server also publishes its own reference:

- Swagger UI: `http://127.0.0.1:8000/api/docs`
- OpenAPI document: `http://127.0.0.1:8000/api/openapi.json`

This page lists all 38 operations (the count in the OpenAPI document) and the rules that apply to them. Where this page and
the running server disagree, the server is right and this page needs a fix.

## Rules that apply everywhere

**Classifications.** Timetable and journey endpoints take `classification`, either `OFFICIAL_VERIFIED` or `UNVERIFIED_FEED`.
Any other value gets HTTP 400, with the message that scenarios use their own endpoints. Each query searches one
classification only, so official and unverified data are never mixed in one result. Scenarios are always
`ESTIMATED_SCENARIO` and have their own endpoints.

**Coverage.** Results cover only the dates a loaded feed covers. When a year or date has no data, the response says so in a
`message` field. Where the year is later than the current year, the message is "No officially verified timetable is available for this
future year." Otherwise it names the year or the date. Nothing is extrapolated.

**Time zone.** The service time zone is the agency time zone of the loaded feed. With no feed loaded it is
`SERVICE_TIMEZONE`. `/api/clock` and the journey responses name the zone and say where it came from (`timezone_source`).
Timestamps with a `Z` suffix are in UTC.

**Authentication.** Three kinds of caller:

| Caller | Header | Used for |
|---|---|---|
| Anyone | none | Public reads: health, clock, metadata, years, routes, stops, timetables, departures, journeys, plans, data sources |
| A device | `X-Client-Key`: 16 to 128 characters, letters, digits, `-` and `_` | Scenarios, saved routes and preferences belonging to that device. The server stores only the SHA-256 hash of the key. |
| The administrator | `X-Admin-Key` | Everything under `/api/admin`. Disabled (HTTP 503) unless `ADMIN_API_KEY` is set. A wrong key gets 401. |

The dashboard creates a device key in the browser and keeps it in local storage. Clearing the site's data forgets the key, and
with it access to that device's scenarios and saved routes.

**Cross-origin requests.** Off by default. Set `CORS_ORIGINS` to a comma-separated list of origins to allow those pages to
call the API. The API then accepts the methods GET, POST, PUT and DELETE, and the headers `Content-Type`, `X-Client-Key` and
`X-Admin-Key`.

**Rate limit.** Each client address may make `RATE_LIMIT_PER_MINUTE` requests (120 by default) to `/api/` in a sliding minute.
Beyond that the server answers 429 with `Retry-After: 60`.

**Errors.** Errors have FastAPI's shape, `{"detail": ...}`. A rejected import is the exception: it returns `{"import": ...}`
with status 422, described below. The codes used are:

| Code | Meaning |
|---|---|
| 400 | A device header is missing or malformed (`X-Client-Key`); the classification is not one of the two data classifications; an upload is empty; a verification is refused (a source that is not `OFFICIAL`, or verifying without the evidence note) |
| 401 | The administrator key is wrong or missing |
| 404 | The item does not exist, or belongs to another device. Missing and foreign items give the same answer, so IDs cannot be probed. |
| 413 | The upload is larger than `MAX_UPLOAD_MB` (100 by default) |
| 422 | A parameter or body failed validation; a device would keep more than 20 preferences; or a feed was rejected (the body then holds the import summary) |
| 429 | The rate limit was reached |
| 500 | A backup could not be written, or its copy failed the check. The unfinished copy is removed. |
| 501 | A backup was requested for a database that is not SQLite |
| 503 | Administration is disabled because `ADMIN_API_KEY` is not set |

## System and years

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{"status": "ok", "time_utc": ...}` when the database answers. Used by the Docker health check. |
| GET | `/api/clock` | `now_utc`, `service_timezone`, `timezone_source`, `now_local`, `service_date`, `weekday`, a `feeds` list with each classification's coverage for that date, and the note that times are scheduled only. |
| GET | `/api/meta` | `name`, `version`, the non-affiliation notice (`affiliation`), `live_positions_available` (always `false`) with `live_positions_note`, `journey_assumptions` (`min_change_minutes`, `max_walk_m`, `walk_speed_kmph`, `max_changes`), `planning_years`, `classifications`, `scenario_notice`, `estimate_assumptions` (`average_bus_speed_kmph`, `stop_dwell_minutes`, `road_detour_factor`) and `admin_enabled`. |
| GET | `/api/years/compare` | `years`: for each planning year (2027 to 2030), the `official` and `unverified` coverage, and `your_scenarios`, the number of scenarios this device has in that year (0 without a device key). Includes `scenario_notice`. |
| GET | `/api/years/{year}/status` | Coverage of one year (2000 to 2100): `is_planning_year`, `is_future`, and the `official` and `unverified` coverage, each with its message. |

## Routes, stops and timetables (public)

| Method | Path | Parameters | Notes |
|---|---|---|---|
| GET | `/api/routes` | `classification` (default `OFFICIAL_VERIFIED`), `year` (2000 to 2100, optional), `q` (up to 80 characters, may be empty), `limit` (1 to 500, default 100) | Matches `q` against route short names and long names as text, ignoring letter case. A GTFS route ID matches exactly. `%`, `_` and `\` in `q` are literal. With `year`, the response includes `coverage` for that year. |
| GET | `/api/routes/{route_id}` | | The route, with `operating_days`, `directions` (each with `representative_trip_id`, `stop_count` and its `stops`, taken from the trip with the most stops in that direction) and `shapes`. 404 when the route is not in active data. |
| GET | `/api/routes/{route_id}/timetable` | `date` (required, `YYYY-MM-DD`) | The trips that run on that date, each with its stops and arrival and departure times, plus `covered`, `coverage_from` and `coverage_to`. For a date outside the feed, `covered` is false, `trips` is empty, `message_code` is `NOT_COVERED` and `message` explains the coverage. When the feed has no service on that date the code is `NO_SERVICE`, and when service runs but lists no trips it is `NO_TRIPS`. |
| GET | `/api/routes/{route_id}/timetable.csv` | `date` (required) | The same timetable as a CSV download. 404 when the date is not covered, with the coverage message as the detail. |
| GET | `/api/stops` | `classification`, `year` (2000 to 2100, optional), `q` (up to 80 characters, may be empty), `limit` (1 to 500, default 100) | Matches `q` against stop names as text, ignoring letter case. A GTFS stop ID matches exactly. |
| GET | `/api/stops/nearby` | `lat` (-90 to 90), `lon` (-180 to 180), both required; `radius_m` (50 to 5000, default 800); `classification`; `limit` (1 to 200, default 50) | Stops within the radius, nearest first, each with `distance_m`, in `results`. The response also gives `origin` and `radius_m`. |
| GET | `/api/stops/{stop_id}/departures` | `classification`, `limit` (1 to 100, default 20) | The next scheduled departures from the stop, from the current moment in the service time zone. The search covers the two service days before today, today and the seven days after it. A trip that ends at this stop is not listed, even when the feed gives it a time there. 404 when the stop is not in this classification's data. |
| GET | `/api/journey` | `origin`, `destination` (2 to 80 characters each), `date` (optional, `YYYY-MM-DD`; without it, the trips leaving from now), `classification` | The older direct-only search, kept for compatibility. It lists trips with no change that call at a matching origin stop before a matching destination stop. The dashboard uses `/api/plan`. The response adds `service_timezone` and `timezone_source`. |
| GET | `/api/data-sources` | | Each data source: `id`, `name`, `publisher`, `source_url`, `license`, `kind`, `verified`, `verified_at`, its `classification` and `completed_imports`. |

## Journey planning (public)

| Method | Path | Parameters | Notes |
|---|---|---|---|
| GET | `/api/plan` | `origin`, `destination` (2 to 80 characters each, required), `date` (`YYYY-MM-DD`; without it, the next three hours from now), `classification` (default `OFFICIAL_VERIFIED`), `max_changes` (0 to 2, default 2), `limit` (1 to 10, default 5) | Journey options with up to two changes, across every feed of one classification. |

Planning uses scheduled times only. The response says so in `note`, and `realtime` is always `false`.

- **Limits.** A change needs at least `MIN_TRANSFER_MINUTES` (3 by default). A walk between two stops of the same
  classification is at most `MAX_TRANSFER_WALK_M` (300 metres by default), and walks are never chained. Walking is at
  `WALK_SPEED_KMPH` (4.8 km/h by default). A name that matches more than 200 stops is cut to 200, and `match_note` says so.
- **Dates.** In date mode the search covers the two service days before the date and the date itself, so trips that run past
  midnight are found. Without a date it covers the next three hours.
- **Response.** `mode` is `date` or `now`, and `date` is the planned date or `null`. `options` holds up to `limit` journeys,
  ordered by arrival time and then by changes. Each option has `departs_at`, `arrives_at`, `duration_minutes`, `changes`,
  `wait_minutes` (now mode only), `fare`, `labels` (`EARLIEST_ARRIVAL` and/or `FEWEST_CHANGES`) and `legs`.
- **Legs.** A `ride` leg gives the route number and name, the headsign, the trip ID, the service date, the stop it boards at
  (`from`) and the stop it leaves at (`to`), `departs_at`, `arrives_at`, `duration_minutes`, `stops_between`, its candidate
  `fares`, and `source`: the feed's import ID, name, publisher, classification, agency name and time zone. Its `timing` is
  `scheduled`. A `walk` leg has `"type": "walk"` and `"estimated": true`, the stops it goes from and to (`from`, `to`),
  `distance_m`, `starts_at`, `arrives_at` and `duration_minutes`.
- **Fare.** `fare.code` is `IN_FEED` (with the total: `price`, `currency`, `fare_id`), `SEVERAL_IN_FEED` (the candidate fares
  are on the ride leg), `NOT_IN_FEED`, or `CHANGES_NOT_PRICED`. A journey with changes is never given a total; its code is
  `CHANGES_NOT_PRICED`.
- **Other fields.** `sources` lists the feeds used. `message` and `message_code` explain an empty result, such as
  `ORIGIN_NOT_FOUND`, `DESTINATION_NOT_FOUND`, `SAME_STOP` or `NO_PLANNED_JOURNEY`. `service_timezone`, `timezone_source`
  and `assumptions` (minimum change time, longest walk, walking speed and the search window in minutes) are included too.

## Scenarios (device-scoped)

Scenarios are proposals. Each response carries the scenario notice, and the CSV and PDF exports carry it too. Each
scenario's `estimate` lists its assumptions. They come from the placeholder values `AVG_BUS_SPEED_KMPH` (15 km/h),
`STOP_DWELL_MINUTES` (0.5) and `DETOUR_FACTOR` (1.3) in `.env`, so they are estimates, not measurements.

The estimate is calculated this way: the straight-line length through the origin, any intermediate stops and the destination,
multiplied by the detour factor, gives the distance. The journey time is the distance divided by the average speed, plus the
dwell time for each intermediate stop. Departures per day are `(last departure − first departure) ÷ frequency + 1`, and
departures per week are that number times the operating days. When any point lacks coordinates, `estimated_distance_km` and `estimated_journey_minutes` are null, and `missing` says what to add.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/scenarios` | Optional `year` (2027 to 2030). Without `X-Client-Key` the list is empty, with a message that asks for the key. |
| POST | `/api/scenarios` | Requires `X-Client-Key`. Returns 201 with the scenario, its `estimate` and, when relevant, `warnings`. Body fields: `name` (1 to 120 characters, required), `year` (2027 to 2030, required), `route_code` (1 to 20 characters: letters, digits, spaces, hyphens and underscores, starting with a letter or digit, required), `origin_name` and `destination_name` (1 to 200 characters each, required), `first_departure` and `last_departure` (`HH:MM`, required; the last is not earlier than the first), `frequency_minutes` (1 to 240, required), `operating_days` (one to seven of `MON` to `SUN`, required; duplicates are removed), `description` (up to 1000 characters), and `stops` (up to 30 items, each with a name of up to 200 characters). Coordinates `*_lat` and `*_lon` must be given as a pair or not at all, and the same holds for each stop. A warning is returned when `route_code` matches the short name of a route in verified official data for that year. |
| GET | `/api/scenarios/{scenario_id}` | Requires `X-Client-Key`. 404 for another device's scenario. |
| PUT | `/api/scenarios/{scenario_id}` | Requires `X-Client-Key`. Replaces the scenario. Same body as POST. |
| DELETE | `/api/scenarios/{scenario_id}` | Requires `X-Client-Key`. Returns 204. |
| GET | `/api/scenarios/compare` | Requires `X-Client-Key`. Query `a` and `b` are scenario IDs, both of which must belong to the device. Returns `a` and `b`, each with its scenario and estimate, and `difference_b_minus_a` for distance, journey minutes, and departures per day and per week. |
| GET | `/api/scenarios/compare.pdf` | Requires `X-Client-Key`. The same comparison as a PDF. |
| GET | `/api/scenarios/export.csv` | Requires `X-Client-Key`. The device's scenarios as CSV, optionally for one year. Values that a spreadsheet would read as formulas are written as text. |
| GET | `/api/scenarios/{scenario_id}/export.pdf` | Requires `X-Client-Key`. One scenario and its estimate as a PDF. |

## Saved routes and preferences (device-scoped)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/saved-routes` | `{"saved": [...]}`, each with `id`, `classification`, `gtfs_route_id` and `label`. Empty without `X-Client-Key`. |
| POST | `/api/saved-routes` | Requires `X-Client-Key`. Body: `gtfs_route_id` (1 to 100 characters), `classification` (`OFFICIAL_VERIFIED` or `UNVERIFIED_FEED`) and `label` (1 to 200 characters). The route must exist in active data of that classification, or the response is 404. Returns 201. Saving the same route again changes its label. |
| DELETE | `/api/saved-routes/{saved_id}` | Requires `X-Client-Key`. Returns 204. Another device's saved route gives 404. |
| GET | `/api/preferences` | `{"values": {...}}`. Empty without `X-Client-Key`. |
| PUT | `/api/preferences` | Requires `X-Client-Key`. Body: `{"values": {"key": "value", ...}}`. The keys given are added or changed, and the device's other preferences are kept. Returns the device's full `values`. Each key is lowercase letters and underscores (1 to 50 characters) and each value is up to 500 characters. A device keeps at most 20 preferences; a request that would exceed that gets 422. |

## Administration (`X-Admin-Key` required)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/admin/data-sources` | The public fields of each source, plus `admin_note` (the note from its last verification) and `verified_by`. |
| POST | `/api/admin/data-sources` | Returns 201. Body: `name` and `publisher` (1 to 200 characters each, required), `source_url` (optional; must start with `http://` or `https://`, up to 500 characters), `license` (up to 200 characters, default "Not specified") and `kind` (`OFFICIAL`, `COMMUNITY`, `SYNTHETIC_DEMO` or `UNKNOWN`, default `UNKNOWN`). A new source is never verified. |
| POST | `/api/admin/data-sources/{source_id}/verify` | Body: `verified` (true or false, required) and `note` (up to 500 characters). Verifying needs a non-empty note. The server asks for the evidence (the publisher's page, the date it was checked and the licence) but does not check what the note says. A verification without a note, or of a source that is not `OFFICIAL`, gets 400. Revoking needs no note. Imports of the source are reclassified in the same step. The response gives the source and `reclassified_imports`, the number of imports that changed. |
| GET | `/api/admin/imports` | The 200 most recent imports, each with its status, classification, counts, warnings, errors and `fares`, the number of fare prices the feed stored. |
| POST | `/api/admin/imports` | Multipart form: `file` (a GTFS ZIP) and `data_source_id`. Returns **201** when the import is completed and **422** when it is rejected. Both carry the import summary under `import`. A rejected feed stores no timetable rows, and its import record lists the errors. Returns 413 when the file is over `MAX_UPLOAD_MB`, 400 when it is empty and 404 when the source does not exist. |
| DELETE | `/api/admin/imports/{import_id}` | Removes the import with its timetable and fare rows. Returns 204. |
| GET | `/api/admin/stats` | `counts`: data sources, completed and rejected imports, routes, stops, trips, stop times, shape points, scenarios and audit entries. `active_imports_by_classification`, and `database` (the name of the database engine, for example `sqlite`). |
| POST | `/api/admin/backup` | Copies the SQLite database to `BACKUP_DIR`, checks the copy, and returns `file`, `bytes`, `directory`, `revision` and `verified: true`. 501 for a database that is not SQLite. 500 when the copy cannot be written or fails its check; the copy is removed in that case. |
| GET | `/api/admin/audit-logs` | `entries`: the most recent audit entries (`limit` 1 to 500, default 100), each with `id`, `time`, `actor`, `action`, `entity`, `entity_id`, `detail` and `ip`. |

Each administrative change writes an audit entry, and so does each import attempt, whether it is completed or rejected. Scenario create, update and delete write entries under the device's actor (`device:` and the first 12 characters of its key hash). Saved routes and preferences are not audited.

## Examples

```bash
# Search official routes for "10" in 2027. With no official data loaded, the list is empty and the coverage says why.
curl "http://127.0.0.1:8000/api/routes?classification=OFFICIAL_VERIFIED&year=2027&q=10"

# Timetable of one route (replace ROUTE_ID with an id from a search) on a Monday in 2027
curl "http://127.0.0.1:8000/api/routes/ROUTE_ID/timetable?date=2027-01-11"

# Journey options with up to two changes on that date (replace the parts with names from your feed)
curl "http://127.0.0.1:8000/api/plan?origin=ORIGIN_PART&destination=DESTINATION_PART&date=2027-01-11&classification=UNVERIFIED_FEED"

# Direct journeys only, from the older endpoint
curl "http://127.0.0.1:8000/api/journey?origin=ORIGIN_PART&destination=DESTINATION_PART&date=2027-01-11&classification=UNVERIFIED_FEED"

# Upload a GTFS ZIP as the administrator (replace YOUR_ADMIN_KEY and the source id)
curl -H "X-Admin-Key: YOUR_ADMIN_KEY" -F "data_source_id=1" -F "file=@feed.zip" http://127.0.0.1:8000/api/admin/imports

# Create a scenario for a device
curl -X POST -H "X-Client-Key: my-device-key-0123456789" -H "Content-Type: application/json" \
     -d '{"name":"Trial","year":2028,"route_code":"PROP-1","origin_name":"A","destination_name":"B",
          "first_departure":"06:00","last_departure":"22:00","frequency_minutes":15,
          "operating_days":["MON","TUE","WED","THU","FRI"]}' \
     http://127.0.0.1:8000/api/scenarios
```

The examples use bash, zsh, or a macOS or Linux shell. On Windows, `curl.exe` works in Command Prompt, but the quoting
differs, and PowerShell needs its own quoting rules.
