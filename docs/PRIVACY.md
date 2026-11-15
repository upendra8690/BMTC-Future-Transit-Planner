# Privacy notes (draft)

This is a technical description of what the software stores and sends. It is **not legal advice**. Whoever runs a
deployment must review it, and must add the details that only they know: who operates the service, how to contact
them, the legal basis for processing, and how long each kind of data is kept.

## What the planner stores on the server

- **Timetable feeds** that administrators import: stops, routes, trips and times, with the publisher's name, licence
  and source link. They contain no passenger data.
- **Scenarios**: the proposals a visitor enters (a name, a route code, stops with coordinates, and times). They are
  linked to a device, not to a named person.
- **Saved routes and preferences**: linked to the same device.
- **Device identity**: each browser creates a random key and sends it in the `X-Client-Key` header. The server
  stores only a SHA-256 hash of that key. Clearing the browser's storage gives the browser a new key, and the
  scenarios and saved routes of the old key are no longer shown to it.
- **Audit log**: a record of each administrator action, including the client's IP address.
- **Backups**: copies of the database. They hold everything listed above.

## What the browser stores

The dashboard uses `localStorage` for four values: the device key (`bmtc.clientKey`), the chosen language
(`bmtc.lang`), the planning year (`bmtc.year`) and the classification (`bmtc.classification`). It does not use
`sessionStorage` or cookies. The administration key is kept only in the page's memory. It is gone when the page is
reloaded or closed.

The service worker stores the dashboard's own files, so the app opens without a connection. It never stores answers
from the planner's API. Timetables and scenarios always come from the server.

## Location

When a visitor presses **stops near me**, the browser asks for permission and then shares the device's location
with the planner. The planner uses the coordinates to find nearby stops and does not store them. The coordinates do
appear in the web server's access log, because they are part of the request's query string. The planner does not
ask for location at any other time.

## Logs

- The web server writes an access-log line for every request: the time, the client address, the method, the path,
  the query string and the status. Set how long these logs are kept in your server or in Docker's logging settings.
  Docker's default `json-file` driver keeps them until they are rotated or removed.
- `LOG_LEVEL` controls the planner's own log messages.
- The planner's code does not write the administration key or device keys to any log. A search of the backend
  source found no such logging. No automated test checks this yet.

## Third parties

- **Map tiles** come from OpenStreetMap's tile servers. Each map view sends those servers the visitor's IP address
  and browser details, which is normal for any web map.
- **HTTPS certificates** come from the certificate authority that Caddy uses (Let's Encrypt by default). The
  certificate request carries the domain name.
- The dashboard loads no analytics, advertising, or tracking scripts.

## Retention and deletion

- The planner has no automatic deletion. Scenarios, saved routes, the audit log, backups and access logs are kept
  until someone deletes them. The operator must decide and document how long each kind of data is kept.
- Visitors can delete their own scenarios and saved routes in the dashboard. Nothing in the software deletes all the
  data linked to one visitor on request. Doing that means deleting the matching rows from the database, and the
  operator must provide that process.

## Children

The planner holds no information about children on purpose. Whoever operates it must decide whether it is suitable
for children and what it must do if it is used by them.
