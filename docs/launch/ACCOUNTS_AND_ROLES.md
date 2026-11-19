# Passenger accounts, saved journeys, administrator accounts and notifications

**Status on 19 Nov 2026: built and tested, screens included; switched off on the public service.** The public service
has no permanent database, so every account would be erased at the next restart. The app therefore refuses to start
accounts there: the Account screen says why, and the feature list shows "Accounts: planned. Needs a permanent
database." Everything below has been run end to end in a browser against a local server with accounts switched on.

## When accounts run
They run only when **both** of these hold:
- the server is started with `ACCOUNTS_ENABLED=1`;
- `DATABASE_URL` is a PostgreSQL database.

`ACCOUNTS_ALLOW_SQLITE=1` exists only for local development and tests. `GET /api/account/status` reports whether
accounts are available, why not, and the session lengths.

## Switching them on for the public service (owner steps)
1. Create a PostgreSQL database (the decided route is a free Neon project; Render PostgreSQL also works).
2. In the Render dashboard, set `DATABASE_URL` to its connection string and `ACCOUNTS_ENABLED=1`. Never put the
   connection string in GitHub. The container then stops treating storage as temporary, migrations run on start, and
   imports, saved routes, notices and accounts survive restarts.
3. Register your own account on the Account screen.
4. Make it an administrator, either:
   - in the app: Administration, "Set up administrator accounts", enter the shared `ADMIN_API_KEY`, choose
     "Administrator" for your account; or
   - from a shell with the same environment: `python scripts/create_admin.py you@example.org`.
5. Sign in again. From now on the shared key can only list accounts and assign roles.

## What is built
| Capability | Endpoint | Screen |
|---|---|---|
| Register | `POST /api/account/register` | Account, "Create an account". Shows the one-time recovery code |
| Sign in / out | `POST /api/account/sign-in`, `POST /api/account/sign-out` | Account |
| Who am I | `GET /api/account/me` | Account ("Signed in as ...", role, when the sign-in ends) |
| Change password | `POST /api/account/password` | Account; signs out every session |
| Recover | `POST /api/account/recover` | Account, "Forgot your password?"; issues a new code |
| Saved journeys | `GET/POST /api/account/journeys`, `DELETE /api/account/journeys/{id}` | Account: list, plan, remove, and "Copy journeys saved on this device" (no duplicates) |
| Notification preferences | `GET/PUT /api/account/notifications` | Account; says that nothing is sent yet |
| Export | `GET /api/account/export` | Account, "Download my account data" (JSON; never hashes) |
| Delete | `POST /api/account/delete` | Account; needs the password |
| Accounts and roles | `GET /api/admin/users`, `PUT /api/admin/users/{id}/role` | Administration, "Accounts and roles" |

## Administrator accounts in place of the shared key
- **With accounts running**, administration uses individual accounts. Every change is recorded as `user:<id>`.
- **The shared `ADMIN_API_KEY`** is then accepted only for listing accounts and assigning roles, so it can create the
  first administrator and nothing else. Any other administrative call with the key is refused (HTTP 403).
- **Without accounts** (the public service today) the key works as before, recorded as `admin`.
- **`scripts/create_admin.py`** gives an existing account a role from the server's shell, audited as `cli`.
- **The last administrator** cannot lose the role (HTTP 409), so the server is never left without one.
- **Roles:**
  - `passenger` (default).
  - `editor`: service notices and upcoming-transport entries only. The Administration screen shows editors only
    those two sections.
  - `admin`: everything, including accounts and roles.

## Security design
- **Passwords:** salted scrypt hashes (N=2^14, r=8, p=1) only; the password is never stored or logged.
- **Sessions:**
  - The token is shown once and travels only in the `Authorization: Bearer` header, never in a cookie, so cross-site
    requests cannot use it (no CSRF). Only its SHA-256 hash is stored.
  - Passenger sessions last 30 days and are kept on the device. Editor and administrator sessions last 12 hours and
    are kept only in the page's memory: a reload signs them out, like the admin key.
  - Changing or recovering the password, or changing the role, ends every session of that account.
  - Signing in as an editor or administrator is written to the audit log (`account.sign_in`).
- **Brute force:**
  - Eight wrong passwords lock the account for 15 minutes; the per-address rate limit also applies.
  - Sign-in answers never reveal whether an email address exists, and an unknown address costs the same hashing time.
- **Recovery:** no email service is connected, so recovery uses a one-time code, stored only as a hash. If a passenger
  loses both the password and the code, the account cannot be recovered. That is stated when the code is shown.
- **Offline cache:** the service worker caches only an allowlist of public timetable answers; account answers are
  never cached.

## Tests
- `tests/test_accounts.py`: 35 tests, including the key's limited scope, session lengths, sign-out on role change,
  the last-administrator rule, audited staff sign-ins, editor limits and `create_admin.py`.
- `tests/browser/accounts_check.py`: 24 browser checks at phone size (register, recovery code, reload, copy journeys,
  notification choices, export, first administrator with the key, administrator sign-in and reload, recovery,
  deletion, and the same screens on a server without accounts).
- The CI PostgreSQL job registers an account, saves a journey, restarts the server and checks both are still there.

## Not built yet
| Item | Why | Needed |
|---|---|---|
| Accounts on the public service | No permanent database there | The owner steps above |
| Sending notifications | Needs a delivery service: web push keys, or an email or SMS provider with its own terms and costs | An owner decision on the channel |
| Email-based password reset | Needs an email provider | Same as above |
| Two-step sign-in for administrators | Not built | Planned after a permanent database |
