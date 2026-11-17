# V4 release readiness — 17 November 2026

**The application is not fully working, and this report does not claim it is.** Here is what the evidence proves.

- **Proved:** in the web app, every control on every screen does something (321 of 321). Every feature that runs on
  the app's own data works end to end on the demonstration data. Every feature that needs an outside provider says
  clearly that it is unavailable and never fakes a result.
- **Not proved:** anything with real BMTC or BMRCL data (none is loaded), the Android app (not built or run on a phone
  in this round), passenger accounts (not built), and the public 4.0 deployment (not created).

| Area | Verdict |
|---|---|
| Web app on demo data (desktop and phone browsers) | Ready for a clearly labelled demonstration |
| Real transport information for the public | Not ready — no licensed data |
| Android app | Not ready — not compiled or tested; a link and SOS defect was fixed in code only |
| Accounts and long-term saved data | Not ready — not implemented; free hosting erases data on restart |
| Ticketing, payments, live tracking, NCMC | Blocked by design until written agreements exist |

Status of every feature: [V4_COMPLETE_FEATURE_MATRIX.md](V4_COMPLETE_FEATURE_MATRIX.md). Test commands and results:
[V4_END_TO_END_TEST_REPORT.md](V4_END_TO_END_TEST_REPORT.md).

## The five most important remaining problems

### 1. The Android APK that people have now (3.0, `app-latest`) cannot call 112 or open official sites
The shell blocks every link outside the planner's host. So the SOS "Call 112" button, the helpline buttons and the
official-site buttons do nothing in the app. It also has no back-button handling. Found by code review; fixed only on
`v4`.
**Next action:** approve porting the `android/flutter_app` fix to `main`. Then let the workflow rebuild `app-latest`,
install it on a phone, and tap SOS, a helpline, an official link and the back button. Until then, tell APK users to
dial 112 directly.

### 2. No real transport data
Every timetable, journey and fare is invented demo data, so the app cannot yet help a real commuter.
**Next action:** add your email and phone to `docs/government/letters/`, confirm the addresses by phone, and approve
sending the DULT and BMTC data-access letters. Nothing has been sent.

### 3. No public 4.0 address, so no phone or tester can use 4.0
**Next action:** in Render choose **New → Blueprint**, then this repository and branch **`v4`** (`render.yaml`). Open
the HTTPS address on your phone and walk through `docs/launch/GOVERNMENT_REVIEW_DEMO_GUIDE.md`. Then add the GitHub
variable `V4_PLANNER_URL` with that address, so the v4 APK (with the fixed shell) is built.

### 4. No passenger accounts, and saved routes are erased on every restart
Data is per device. On Render's free disk, server-side saved routes and scenarios are lost whenever the service
restarts.
**Next action:** create a free Neon Postgres database (Singapore). Put its connection string only in Render's
`DATABASE_URL`, run `python scripts/migrate_database.py`, then build Phase 5 accounts.

### 5. Things not yet verified by anyone
These have not been checked yet:
- GitHub CI for the last push (the GitHub API was unreachable here)
- the Docker image (built only in CI)
- Kannada, Telugu and Hindi wording, by a native speaker
- the app with a real screen reader
- the PWA installed on a real phone

**Next action:** open the repository's Actions tab and confirm "CI" (tests and the container job) is green for `v4`.
Then do a 15-minute phone test with TalkBack and record the results in `V4_END_TO_END_TEST_REPORT.md`.

## Constraints kept
- Work only on `v4`. `main` and 3.0 were not changed; nothing was merged.
- No release was published. This round's commit is **local and not pushed**: a push to `v4` builds and publishes the
  `app-v4-preview` pre-release once `V4_PLANNER_URL` is set, and that would be a release.
- No email was sent and no application was submitted.
