# Launch readiness — Bengaluru Transit Planner 4.0.0-beta.1

Assessed 17 November 2026 for a public demo on 18 November 2026. Branch `v4` only; `main` and the live 3.0 site are
unchanged. Checkpoint before this work: tag `checkpoint-pre-launch-2026-11-17`.

**Bengaluru Transit Planner is an independent, unofficial app.** No BMTC, BMRCL, government or other approval,
endorsement or partnership exists.

## Verdict

| Release | Ready? | Why |
|---|---|---|
| Local / staging demo of 4.0 on demo data | **Ready** | All P0 items work and are tested (see below) |
| Public 4.0 URL | **Not yet** — owner action | The Render service for branch `v4` must be created from `render.yaml` in the owner's Render account |
| Android APK of 4.0 | **Not yet** — owner action | The v4 APK build waits for the `V4_PLANNER_URL` repository variable (the public URL above) |
| Real BMTC / BMRCL timetables | **Blocked** | No data licence; requests drafted, not sent |
| Live tracking, tickets, passes, Metro QR, payments, NCMC | **Blocked** | Need written provider agreements; the app refuses these actions |

## P0 checklist (must work for the demo)

| P0 item | Status | Evidence |
|---|---|---|
| Existing 3.0 functionality retained | Working and tested | 121/121 browser regression checks; all earlier pytest tests pass |
| 4.0 home screen and navigation | Working and tested | Launch browser checks, phone and desktop, 4 languages |
| Search, route and stop information | Demo only | Works on the synthetic demo feeds |
| Journey planner (bus only, Metro only, bus + Metro) | Demo only | New `modes` filter; 6 new planner tests |
| Map | Demo only | OpenStreetMap tiles; needs internet |
| Metro and combined journey interface | Demo only | Metro screen and planner |
| Upcoming-service status | Working and tested | 7 projects, each sourced and dated; a validator stops a future service from showing as operating |
| Mobile responsiveness | Working and tested | 390 px and 1280 px, no horizontal scroll, 4 languages |
| Clear demo and data-source labels | Working and tested | Classification badges on every result; "Data and providers" screen states demo-only |
| No critical security or application errors | Working and tested | 34/34 security probes, bandit and pip-audit clean, no console errors |

## P1 and P2

| Item | Status |
|---|---|
| User accounts (registration, login, profile) | **Not implemented.** Device-key data and "Delete my data" work; accounts need Neon Postgres and an email provider |
| Saved journeys | Saved routes and stops work; whole saved journeys are not implemented |
| Notifications | Not implemented |
| PWA installation | Manifest and service worker in place; offline reading tested in a browser; install not tested on a phone |
| Android build | Pipeline exists; 4.0 build not run (needs the public URL) |
| Admin data management | Working and tested (one shared admin key — finding S5) |
| All P2 items | Awaiting provider access; interfaces and refusing adapters built |

## What changed in this release
See [docs/launch/RELEASE_NOTES_4.0.md](docs/launch/RELEASE_NOTES_4.0.md).

## Documents
| Document | Contents |
|---|---|
| [FEATURE_MATRIX.md](docs/launch/FEATURE_MATRIX.md) | Every requested feature with one status |
| [DATA_SOURCES_AND_LICENCES.md](docs/launch/DATA_SOURCES_AND_LICENCES.md) | Provider registry |
| [INTEGRATION_STATUS.md](docs/launch/INTEGRATION_STATUS.md) | Live data, tickets, payments, NCMC adapters |
| [SECURITY_AUDIT.md](docs/launch/SECURITY_AUDIT.md) | OWASP-based checks and open findings |
| [PRIVACY_AND_ACCESSIBILITY.md](docs/launch/PRIVACY_AND_ACCESSIBILITY.md) | Data handling and WCAG results |
| [TEST_RESULTS.md](docs/launch/TEST_RESULTS.md) | Exact commands and numbers |
| [DEPLOYMENT_GUIDE.md](docs/launch/DEPLOYMENT_GUIDE.md) | Owner steps for the public URL and APK |
| [KNOWN_LIMITATIONS.md](docs/launch/KNOWN_LIMITATIONS.md) | What does not work, plainly |
| [RELEASE_NOTES_4.0.md](docs/launch/RELEASE_NOTES_4.0.md) | Changes in 4.0.0-beta.1 |
| [GOVERNMENT_REVIEW_DEMO_GUIDE.md](docs/launch/GOVERNMENT_REVIEW_DEMO_GUIDE.md) | A 10-minute demonstration script |

## Remaining blockers (exact)
1. The owner creates the Render staging service from `render.yaml` (branch `v4`) and checks the HTTPS URL on a phone.
2. The owner sets the GitHub variable `V4_PLANNER_URL` to that URL, so the v4 APK workflow can run.
3. Release signing key and GitHub secrets are not created; the v4 APK would be a debug-signed preview.
4. No licensed BMTC or BMRCL data. The letters in `docs/government/letters/` are drafts and have not been sent.
5. No real-device test has been done.
