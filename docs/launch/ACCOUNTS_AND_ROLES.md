# Passenger accounts, saved journeys, administrator roles and notifications

**Status on 18 Nov 2026: built and tested, switched off.** The public service has no permanent database, so every
account would be erased at the next restart. The app therefore refuses to start accounts there, and the feature list
shows "Accounts: planned. Needs a permanent database."

## When accounts run
They run only when **both** of these hold:
- the server is started with `ACCOUNTS_ENABLED=1`;
- `DATABASE_URL` is a PostgreSQL database.

`ACCOUNTS_ALLOW_SQLITE=1` exists only for local development and tests. `GET /api/account/status` reports whether
accounts are available, and why not.

## What is built (API and database; migration 0004)
| Capability | Endpoint | Notes |
|---|---|---|
| Register | `POST /api/account/register` | Email and password (10–128 characters). Returns a one-time recovery code |
| Sign in | `POST /api/account/sign-in` | Returns a session token for the `Authorization: Bearer` header |
| Sign out | `POST /api/account/sign-out` | Ends this session |
| Who am I | `GET /api/account/me` | |
| Change password | `POST /api/account/password` | Signs out every session |
| Recover | `POST /api/account/recover` | Email + recovery code + new password; issues a new code; signs out everywhere |
| Saved journeys | `GET/POST /api/account/journeys`, `DELETE /api/account/journeys/{id}` | Up to 50; another account's journey is reported as missing |
| Notification preferences | `GET/PUT /api/account/notifications` | Stored only; `delivery` is `NOT_AVAILABLE` |
| Export | `GET /api/account/export` | Everything kept about the account; never hashes |
| Delete | `POST /api/account/delete` | Needs the password; removes the account, sessions, journeys and preferences |
| Roles | `GET /api/admin/users`, `PUT /api/admin/users/{id}/role` | admin only; audited |

## Security design
- **Passwords:** salted scrypt hashes (N=2^14, r=8, p=1) only; the password is never stored or logged.
- **Sessions:**
  - The token is shown once and travels only in the `Authorization: Bearer` header, never in a cookie, so cross-site
    requests cannot use it (no CSRF).
  - Only the token's SHA-256 hash is stored, and sessions expire after 30 days.
  - Changing or recovering the password ends every session.
- **Brute force:**
  - Eight wrong passwords lock the account for 15 minutes; the per-address rate limit also applies.
  - Sign-in answers never reveal whether an email address exists, and an unknown address costs the same hashing time.
- **Recovery:** no email service is connected, so recovery uses a one-time code, stored only as a hash. If a passenger
  loses both the password and the code, the account cannot be recovered. That is stated when the code is shown.
- **Roles:**
  - `passenger` (default).
  - `editor`: may add and update upcoming-transport entries.
  - `admin`: everything in Administration, including roles.
- **Attribution:** a signed-in editor or admin is recorded in the audit log and in upcoming-transport history as
  `user:<id>`. The `ADMIN_API_KEY` keeps working as the emergency key and is recorded as `admin`.
- **Offline cache:** the service worker caches only an allowlist of public timetable answers; account answers are
  never cached.

Tests: `tests/test_accounts.py` (26). The CI PostgreSQL job also registers an account, saves a journey, restarts the
server and checks both are still there.

## Not built yet
| Item | Why | Needed |
|---|---|---|
| Account screens in the app (sign-in, register, saved journeys, settings) | Only useful once the database is permanent; building the screens and translating them is the next step after that | `DATABASE_URL` on PostgreSQL, then the screens |
| Sending notifications | Needs a delivery service: web push keys, or an email or SMS provider with its own terms and costs | An owner decision on the channel |
| Email-based password reset | Needs an email provider | Same as above |
| Per-person administrator accounts in place of the shared key | The roles are ready; they become usable when accounts run | Accounts running, then create the first admin with the key |
