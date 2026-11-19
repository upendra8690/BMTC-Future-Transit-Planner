# Release notes — Bengaluru Transit Planner 4.0.0-beta.1 (17 November 2026)

Public-demo candidate. Unofficial; not affiliated with or endorsed by BMTC, BMRCL or the Government of Karnataka.
Runs on invented demo data.

## New
- **Choose how to travel:** the planner can search bus only, Metro only, or bus and Metro together. Mixed journeys are
  labelled "Bus + Metro". If nothing is found with only the chosen mode, the app says so.
- **Upcoming transport:** new Metro lines, suburban rail and BMTC feeder services, each with a status (Operating,
  Announced, Under construction, Planned, Awaiting confirmation, Unavailable), source links and the date checked. A
  built-in check stops any future service from being shown as operating.
- **Travel assistant:** type a question such as "Majestic to Whitefield by bus" or "route 500D". It is rule-based,
  answers only from the app's loaded data, and declines live, ticket and payment questions with the official
  channel. For emergencies it points to 112.
- **Data and providers:** which timetables are loaded and whether they still cover today; every data provider with
  its licence and permission status; and every provider integration with what it needs.
- **Provider adapters:** one entry point for live data, tickets, passes, Metro QR, payments and NCMC. It refuses until
  an authorised provider is connected, so the app cannot produce a fake ticket, QR code, receipt, balance or payment.
- New API: `/api/upcoming`, `/api/providers`, `/api/data-status`, `/api/integrations`,
  `/api/integrations/{capability}/request`, `/api/assistant`, and `modes` on `/api/plan`.

## Improved
- The home screen has tiles for the assistant and for upcoming transport; More services lists the new screens.
- All new text is in English, Kannada, Telugu and Hindi.
- CI now builds and calls the Docker image, and runs on pushes to `v4`.
- `render.yaml` describes the separate 4.0 staging service (branch `v4`).

## Fixed
- The security probe for keyless saved-route access now matches the documented behaviour (finding S6).

## Unchanged
Version 3.0 on `main` and its live site. All 3.0 features remain in 4.0 (121/121 browser regression checks).
