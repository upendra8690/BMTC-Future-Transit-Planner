# Production database: PostgreSQL for the 4.0 service

## Why
The public service runs on Render's free plan with SQLite on the container's disk. **That disk is erased on every
restart and every deploy.** Saved routes and administrator edits are lost, and passenger accounts would be lost too,
which is why the app keeps accounts switched off. A managed PostgreSQL database fixes this.

## What has been verified in this repository
These pass in GitHub Actions on every push (job "PostgreSQL", PostgreSQL 16), using a throwaway database:
- Migrations run on PostgreSQL, and a second run changes nothing.
- The community Namma Metro feed imports, and a second run does not import it again.
- **Data survives a restart** (`scripts/check_persistence.py`): a saved route, an administrator change and a passenger
  account with a saved journey are all still there after the server process is restarted.
- A PostgreSQL-backed real-mode server passes the deployment checks.

The app uses psycopg 3.2. Addresses of the form `postgres://` and `postgresql://` are accepted as given by hosting
providers.

## Recommendation
**Render Postgres, Basic-256mb, in the Singapore region, in the same Render workspace as the 4.0 service.**

| Option | Monthly cost (as published; confirm before buying) | Backups and recovery | Fit |
|---|---|---|---|
| **Render Postgres Basic-256mb** (recommended) | US$6 | Point-in-time recovery on paid databases (3-day window on the Hobby workspace plan, 7 days on Pro); logical backups kept 7 days | Same provider and region as the web service; private internal address; no extra account |
| Render Postgres Basic-1gb | US$19 | As above | Only if the database outgrows 256 MB RAM performance |
| Neon Free | ₹0 | Short restore history on Free (about 6 hours per third-party sources; check Neon's docs) | Good no-cost interim. 1 GB storage per project; scales to zero, so the first query after idle is slower |
| Render Postgres Free | ₹0 | **None**, and the database **expires after 30 days** | Not suitable for production |

Size today is well below 1 GB (about 9 MB with the Metro feed in SQLite). Sources: Render pricing and Render Postgres
backup documentation; Neon free-plan FAQ (checked 18 Nov 2026).

The web service also stays on Render's free plan, which sleeps when idle; the first request can take up to a minute.
For a pilot, the paid Starter web instance (about US$7 a month) removes sleeping. That is a separate decision.

## Steps for the owner (never paste the database address into chat, email or GitHub)
1. **Create the database.** Render dashboard → New + → Postgres:
   - Name: `bengaluru-transit-planner-v4-db`
   - Region: Singapore
   - PostgreSQL 16
   - Plan: Basic-256mb
2. **Connect it.** In the database's Connections section, copy the Internal Database URL.
3. **Set it on the 4.0 service.** Open `bengaluru-transit-planner-v4` → Environment → add `DATABASE_URL` and paste the
   value there. Save, which redeploys.
4. **Check the deployment.**
   - At start-up, the container runs the migrations and loads the community Metro feed into the new database.
   - Check with `python scripts/verify_deployment.py https://bengaluru-transit-planner-v4.onrender.com`.
   - Then make a change in Administration (for example a note on an upcoming entry), trigger a manual deploy from the
     Render dashboard, and confirm the change is still there.
5. **Optional: passenger accounts.**
   - Add `ACCOUNTS_ENABLED=1` to the same service. Accounts start only because the database is PostgreSQL.
   - The account screens in the app are not built yet; the API is ready and tested (see `ACCOUNTS_AND_ROLES.md`).
6. **Backups.**
   - Render's point-in-time recovery covers accidents.
   - Once a month, also download a logical backup from the database's Recovery page and keep it offline.
   - The admin "Backup" button works only for SQLite; on PostgreSQL use Render's backups.

## Rollback
Remove `DATABASE_URL` from the service to return to the temporary SQLite database. The PostgreSQL data stays in the
database until you delete it.
