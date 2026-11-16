# Production readiness report

Measured 16 November 2026 on a developer laptop (Intel Core i5-1235U, 15.7 GB RAM), one uvicorn worker, SQLite, the
SYNTHETIC demo feeds (2 bus routes, 1 Metro line, 10 stops). **These results describe demo-sized data only.** A full
BMTC feed has thousands of stops and routes; performance must be re-measured with real data.

## Load test (`tests/audit/load_test.py`, rate limit raised for the test)
| Users | Requests | Errors | p50 | p95 | Max |
|---|---|---|---|---|---|
| 1 | 90 | 0 | 13 ms | 28 ms | 45 ms |
| 20 concurrent | 900 | 0 | 21 ms | 105 ms | 263 ms |

Slowest endpoint under load: stop departures (p95 181 ms). Bus + Metro plan: p95 61 ms.

## Reliability behaviour (tested)
| Situation | Behaviour | Evidence |
|---|---|---|
| No timetable feed | Features report NO_DATA with a reason; no invented data | `test_features_api.py` |
| Feed deleted | Features return to NO_DATA | `test_features_api.py` |
| Live feed absent | Live tracking shows "not available"; no positions drawn | Edge; features API |
| Offline | App shell and saved timetables open; banner shown | Browser checks |
| Server restart on Render | Demo feeds reloaded automatically; **device data on the free disk is lost** | Seed script runs; documented |
| Rate limit | 429 with Retry-After after 120 requests/min per client | Observed in Edge runs |
| Service-worker update | New version takes over; user told to reload | Browser checks |

## Not tested yet
Database outage; invalid upstream API responses (no upstream APIs are active); Android low-memory; slow-network
throttling; backup/restore on Postgres (the SQLite restore drill passed in 3.0).

## Hosting facts and costs
| Item | Today | For a pilot |
|---|---|---|
| App hosting | Render free web service (sleeps after ~15 min idle; cold start up to ~1 minute; 512 MB RAM) | Always-on instance (paid, typically a few hundred rupees per month upwards) |
| Database | SQLite on an ephemeral disk | Persistent Postgres (Neon free tier, or paid for backups/retention) |
| Backups | None for user data on Render | Provider point-in-time recovery + weekly export |
| Monitoring | None beyond Render logs | Uptime check (free tiers exist) + error alerts |
| Domain | `onrender.com` subdomain | Optional custom domain |

**The free Render deployment is a demonstration environment, not production-grade hosting.**
