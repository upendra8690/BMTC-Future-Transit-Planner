# Deployment and release plan for 4.0

## Branches and versions
- `main`: version 3.x, serving the live demo. Tagged `v3.0.0`.
- `v4`: all 4.0 work. Pre-releases tagged `v4.0.0-alpha.N`. Merged to `main` only at the 4.0 release.
- The Android workflow builds APKs from `main`; a separate pre-release APK can be built from `v4` when Phase 11 starts.

## Environments
| Environment | Where | Database | Notes |
|---|---|---|---|
| Development | Your PC | SQLite in `data/` | `uvicorn` as in the README |
| CI | GitHub Actions | SQLite, and Postgres service container (from Phase 5) | Tests, lint, security checks, APK build |
| Demo | Render free | SQLite reseeded on start (3.x); Postgres via Neon for 4.0 accounts | Sleeps when idle |

## Your one-time actions (when the phase needs them)

### Free Postgres (Phase 5, decision D3)
1. Sign up at neon.tech with GitHub, create a project in a region near India (for example Singapore).
2. Copy the connection string (`postgresql://...`).
3. In Render → your service → Environment, add `DATABASE_URL` with that value. Never put it in git.

### Android release signing (Phase 11)
Run on your PC (Java is needed; Android Studio includes it):
```
keytool -genkeypair -v -keystore bmtc-planner-release.jks -alias bmtc-planner -keyalg RSA -keysize 2048 -validity 10000
```
Keep the `.jks` file and passwords somewhere safe (not in the project folder). Then in GitHub → Settings → Secrets and
variables → Actions, add:
- `ANDROID_KEYSTORE_BASE64`: the output of `certutil -encode bmtc-planner-release.jks out.txt` (copy the text between the BEGIN/END lines)
- `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` (`bmtc-planner`), `ANDROID_KEY_PASSWORD`

The workflow will sign with these when present and publish the APK's SHA-256 checksum in the release notes.
People with the current debug-signed app must uninstall it once before installing the signed one.

## Cost and permission register

| Item | Free option | Paid / permission needed |
|---|---|---|
| Production hosting | Render free (sleeps, limited RAM) | Always-on instance (paid) |
| Persistent database | Neon free tier | Larger plans |
| Domain | `onrender.com` subdomain | Custom domain (~₹800+/year) |
| SMS / OTP | — | Paid provider + DLT registration |
| Push notifications | Web Push (VAPID), FCM | — |
| Maps and geocoding | OSM tiles (light use), Nominatim (1 req/s) | Higher-volume tile/geocoding plans |
| Real-time bus data | — | BMTC data agreement or public feed |
| Ticketing | — | ONDC buyer-app registration or BMTC agreement (registered business) |
| Payment processing | — | Gateway merchant KYC; fees per transaction |
| Wallet | — | RBI PPI licence (not planned) |
| AI assistant | Rule-based | LLM API key (usage pricing) |
| App stores | GitHub Releases APK; Samsung Galaxy Store; Indus Appstore (check terms); F-Droid (needs an open-source licence) | Google Play: one-time US$25 |

## Release checklist (4.0)
1. All phases' "done" items pass tests on SQLite and Postgres; lint and security checks pass.
2. `FEATURE_MATRIX_4_0.md` statuses are true.
3. Screenshots regenerated from the running app.
4. APK built, signed (if secrets exist), checksum published.
5. Release notes and known limitations written.
6. `BMTC_FUTURE_TRANSIT_PLANNER_4_0.zip` built from the tagged commit (source only, no secrets, no database).
7. Merge `v4` into `main`, tag `v4.0.0`, deploy.
