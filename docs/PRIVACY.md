# Privacy notes

This is a technical description of what the software stores and sends, checked against the code in this release. It is
**not legal advice**. Whoever runs a deployment must review it, and must add what only they know: who operates the service,
how to contact them, the legal basis for processing, and how long each kind of data is kept.

## What the planner stores on the server

- **Timetable feeds** that administrators import: stops, routes, trips and times, fare prices and fare rules, with the
  publisher's name, the licence and the source link. Feeds contain no passenger data.
- **Data sources and verification records.** Each source has a name, publisher, licence, source link and kind. When an
  administrator verifies a source, the note they enter is kept as a verification record. The note is free text, and only
  administrators can see it.
- **Scenarios.** A visitor enters a name, a description, a route number, the origin and destination names and coordinates,
  intermediate stops with coordinates, the years, a frequency and the operating days. The text fields are free text, so they
  can contain whatever the visitor types. Each scenario is linked to a hash of the visitor's device key, not to a name.
- **Saved routes.** A saved route stores the route's GTFS identifier, its classification and a label. It is linked to the
  device key hash.
- **Preferences.** The API stores key and value pairs for each device (`GET` and `PUT /api/preferences`), and a device can keep
  at most 20. The dashboard does not call this endpoint. No endpoint deletes preferences.
- **Searches.** Journey, plan, stop and nearby searches are not stored in the database. The web server's access log keeps
  them (see Logs).
- **Device identity.** Each browser creates a random key, keeps it in its local storage, and sends it in the `X-Client-Key`
  header. The server stores only the SHA-256 hash of that key. Clearing the browser's storage gives the browser a new key.
  The scenarios and saved routes of the old key stay in the database, and this browser no longer sees them. Nothing in the
  software removes them.
- **Audit log.** Entries are written for these actions: `data_source.create`, `data_source.verify`, `gtfs.import`,
  `gtfs.import_rejected`, `gtfs.import_failed`, `gtfs.delete`, `database.backup`, `scenario.create`, `scenario.update` and
  `scenario.delete`. Each entry has an actor, an action, the entity it concerns and a short detail. Entries that come through
  the API also record the client's IP address. A scenario change by a visitor has the actor `device:` followed by the first 12 characters of the hash of their device key. Administrator actions have the actor `admin`. Entries from the command line have the actor `cli` and no address. Saved routes and preferences
  are not audited.
- **Backups.** Full copies of the database, so they contain everything listed above.

## What the browser stores

The dashboard uses `localStorage` for four values: the device key (`bmtc.clientKey`), the chosen language (`bmtc.lang`), the
planning year (`bmtc.year`) and the classification (`bmtc.classification`). It does not use `sessionStorage` or cookies. The
administration key is kept only in the page's memory. It is gone when the page is reloaded or closed.

The service worker stores the dashboard's own files, so the app opens without a connection. It also keeps copies of public
timetable answers: the list of routes, one route, a route's timetable, the list of stops and the list of data sources. Up to
120 copies are kept, and the oldest are dropped first. A copy stays until the browser clears the site's data or the limit pushes it out. Each copy is
keyed by its full address, so it also records the query values, such as the classification, the year or the date of a
timetable. A route or stop search with typed words (a non-empty `q`) is never kept. Journey and plan answers, nearby stops,
departures, the clock, scenarios, saved routes, preferences and administration are never kept, and they always come from the
server.

## Location

When a visitor presses **Stops near me**, the browser asks for permission and then shares the device's location with the
planner. The planner uses the coordinates to find nearby stops and does not store them in its database. The coordinates appear in the web
server's access log, because they are part of the request's query string. The dashboard asks for location only when that
button is pressed.

## Logs

- **The web server's access log.** The server writes a line for each request: the client address and port, the request line
  (method, path, query string and HTTP version), and the status code. Journey and plan searches send their origin and
  destination in the query string, for example `/api/plan?origin=…&destination=…`. Stop searches send their text as `q`, and
  "stops near me" sends coordinates. The access log therefore records what a visitor searched for, with the visitor's address.
  The planner does not store these searches in its database. Set how long the logs are kept in your server or Docker's
  logging settings. Docker's default `json-file` driver keeps them until they are removed, unless log rotation is set.
- **The planner's own log messages.** At start-up the planner warns when `ADMIN_API_KEY` is shorter than 32 characters, without
  printing the key. For each request that is not a `GET` to the API, it writes the method, the path (without the query string),
  the status code and the time taken. For a failed import it writes the traceback with the file name. `LOG_LEVEL` sets the
  level. The planner's code does not log the administration key, device keys or request headers.
- **Caddy.** The Caddy configuration in `deploy/` has no `log` directive, so Caddy writes no access log unless one is added.

## Third parties

- **Map tiles** come from OpenStreetMap's tile servers. Each map view sends those servers the visitor's IP address and browser
  details, which is normal for any web map. The dashboard's content security policy allows images from those servers only.
- **HTTPS certificates** (in the Docker and Caddy kit) come from a public certificate authority, which Caddy uses for
  `PLANNER_DOMAIN`. The certificate request carries the domain name.
- **Scripts.** The dashboard loads no analytics, advertising or tracking scripts. Its content security policy allows scripts
  only from the planner's own server.

## Retention and deletion

- The planner has no automatic deletion. Scenarios, saved routes, preferences, the audit log, backups and access logs are kept
  until someone deletes them. The operator must decide and document how long each kind of data is kept.
- Visitors can delete their own scenarios and saved routes in the dashboard. Preferences cannot be deleted through the API.
- Administrators can delete an import. That removes its timetable and fare rows, and the audit log records the deletion.
- No endpoint deletes audit entries.
- Nothing in the software deletes all the data linked to one visitor on request. Doing that means deleting the matching rows in
  the database, and the operator must provide that process.

## Free text

Scenario names and descriptions, the labels of saved routes, and the notes an administrator enters when verifying a source are
free text. They can contain personal information if someone types it. The planner does not check them for personal data.

## Children

The planner asks for no age or date of birth, and no table has a field for either. Whoever operates it must decide whether it
is suitable for children, and what it must do if children use it.
