# Deploying the planner

This guide runs the planner on one Linux server with Docker. Caddy sits in front of it and serves HTTPS for your
domain. The guide says what the project provides and what you must check yourself.

## Status of this guide

- `docker-compose.yml` was checked: it renders correctly from a placeholder `.env`, and it refuses to start when
  `PLANNER_DOMAIN` is missing.
- The image was **not** built and the containers were **not** run in the verification session. The build sandbox's
  outbound proxy returned `403 Forbidden` for `registry-1.docker.io`, so the base image `python:3.13-slim`
  could not be downloaded. The first deployment is therefore the first real run of the image. Check it with the steps
  in section 3 and record the result.
- `deploy/Caddyfile` was not run either. Caddy's certificate issuance depends on the public DNS record and on
  ports 80 and 443 reaching the server.

## What you need

- A Linux server with Docker Engine and the Compose plugin. `docker compose version` should print a version.
- A public domain name whose DNS record points at the server.
- Ports 80 and 443 open to the internet. Caddy needs port 80 to obtain certificates.
- Disk space for the database and backups. Plan for the size of your feeds, multiplied by the number of backups you keep.

## 1. Get the project onto the server

Copy the project folder to the server, for example with `scp` or from an extracted ZIP, then change into it.

## 2. Create the settings file

```sh
cp .env.example .env
```

Edit `.env`:

- `ADMIN_API_KEY`: a long random value of at least 32 characters. Generate one with
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Administration stays disabled without it.
- `PLANNER_DOMAIN`: the public host name, for example `planner.example.org`.
- `SERVICE_TIMEZONE`: the fallback time zone, for example `Asia/Kolkata`. A loaded feed names its own zone and that
  zone takes priority.
- Leave `DATABASE_URL` and `BACKUP_DIR` blank. The defaults point inside the data volume.

Do not add `FORWARDED_ALLOW_IPS` to `.env`. `docker-compose.yml` sets it to Caddy's fixed address, and that setting
must win.

## 3. Start and check

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=50 planner
curl -fsS https://YOUR-DOMAIN/api/health
```

- `docker compose ps` should show `planner` as `healthy`. The health check calls `/api/health`, which answers
  `{"status": "ok", "time_utc": ...}` when the database responds.
- The planner applies its database migrations every time it starts, so an upgrade needs no separate step.
- Open `https://YOUR-DOMAIN/` in a browser. The page should show the year banners and the language picker.
  If the certificate is not issued, read `docker compose logs caddy`.

## 4. Load a timetable feed

Load only feeds whose publisher and licence you have checked. [SOURCES.md](../SOURCES.md) explains the sources
and what is still unverified.

In the browser, open **Administration**, sign in with `ADMIN_API_KEY`, add a data source (name, publisher, source
link, licence, and kind), then upload the GTFS ZIP file. The kind is one of `OFFICIAL`, `COMMUNITY`,
`SYNTHETIC_DEMO` or `UNKNOWN`. A source is labelled *official verified* only when its kind is `OFFICIAL` and an
administrator verifies it.

The command line works too. Copy the ZIP into the data volume, then run the importer inside the container:

```sh
docker compose cp feed.zip planner:/app/data/feed.zip
docker compose exec planner python scripts/import_gtfs.py --file /app/data/feed.zip \
    --new-source "Publisher name" --kind OFFICIAL --source-url https://example.org/feed
```

Two overlapping feeds of the same kind are both kept and searched. The import report warns about the overlap, and
the older import can then be removed from Administration. Otherwise routes and trips may appear twice.

## 5. Backups

No backup schedule is built in. Choose one of these:

- In **Administration**, press **Create backup (SQLite)**. The file is written to `/app/data/backups` in the
  volume.
- From the command line: `docker compose exec planner python scripts/backup_database.py`.

Copy backups off the server regularly:

```sh
docker compose cp planner:/app/data/backups ./backups-copy
```

Test a restore before you rely on the backups. `scripts/restore_drill.sh [log-file]` runs the whole cycle on a copy of
the project, on Linux: it builds a database, makes a verified backup, damages the database, restores it, and reads the
restored server back. It works in a temporary folder and never reads or changes `data/` or `.env`. The drill has run on
Linux only. macOS has not been tested, and Windows has no drill (`docs/INSTALL_WINDOWS.md` gives the manual steps).
[TEST_RESULTS.md](TEST_RESULTS.md) records the result of the last run. The restore steps for the Docker volume (copy the
backup file over `planner.db` while the planner is stopped, after removing the `-wal` and `-shm` files) have not been
run inside Docker.

## 6. Update

1. Make a backup (section 5).
2. Replace the project files with the new version. Keep `.env` and do not remove the data volume.
3. Run `docker compose up -d --build`.
4. Check `/api/health` and the dashboard, as in section 3.

## 7. Operating notes

- **Logs.** `docker compose logs -f planner` follows the server log. The web server writes one access-log line per
  request, with the client address, the path and the query string. The query string includes the coordinates of
  "stops near me". [PRIVACY.md](PRIVACY.md) describes this.
- **Client addresses.** The rate limit counts each client by address. Behind Caddy, the server (uvicorn) takes the real client
  address from `X-Forwarded-For` only when the connection comes from Caddy's address, `172.28.0.20`. Do not widen
  that setting. Anyone who can reach the planner's port directly could otherwise fake their address.
- **Ports.** The planner publishes no port. Only Caddy is reachable from outside.
- **Stopping.** `docker compose down` keeps the volumes. Do not add `-v` unless you mean to delete the data.
- **Maps.** Map tiles come from OpenStreetMap's public servers. Their usage policy limits traffic, so a busy
  deployment should use its own tile provider.
- **Secrets.** Keep `.env` out of version control and out of backups you share. To change the admin key, edit
  `.env` and run `docker compose up -d` (not tested in this build).

## 8. Not covered by this guide

- Docker Desktop on Windows: not tested.
- PostgreSQL: not tested. The planner uses SQLite.
- Automatic backups, monitoring, alerts, and log rotation settings.
- Legal review of the privacy notes.
