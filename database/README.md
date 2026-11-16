# Database

The planner keeps everything in one SQLite file, `data/planner.db`. The folder is created the first time the planner
starts or a setup script runs. To use another database, set `DATABASE_URL` in `.env`.

**Support.** SQLite is the tested database. SQLAlchemy can also connect to PostgreSQL through `DATABASE_URL`, but
PostgreSQL was **not tested** in this build. The built-in backup works only for SQLite; for other databases the
administration backup endpoint returns an error that asks you to use the database's own tools (`pg_dump` for
PostgreSQL).

## Connection settings

Every connection to SQLite does the following, set in `backend/app/database.py`:

- enforces foreign keys (`PRAGMA foreign_keys=ON`)
- waits up to 5 seconds for a lock instead of failing at once (`busy_timeout=5000`)
- uses write-ahead logging for the live database (`journal_mode=WAL`)

Backups are written with the `DELETE` journal mode, so each backup is one self-contained file.

## Tables

There are 18 tables. The planner's data comes from GTFS feeds, which are stored once per import. Every imported row
carries the `import_id` of the feed it came from, so a feed can be removed without touching the others. Removing an import
removes its timetable rows and its fare rows.

| Table | What it holds |
|---|---|
| `data_sources` | A publisher of timetable data: name, publisher, licence, link, kind (`OFFICIAL`, `COMMUNITY`, `SYNTHETIC_DEMO` or `UNKNOWN`) and whether an administrator verified it. |
| `verification_records` | Each verify or revoke decision for a source, with the administrator's note and who made it. |
| `gtfs_imports` | One row per feed import: file name, SHA-256, status (`COMPLETED` or `REJECTED`), classification, feed dates, counts, warnings and errors. |
| `agencies` | Rows from `agency.txt`. |
| `routes` | Rows from `routes.txt`, including the route type, which the planner stores but does not use. |
| `stops` | Rows from `stops.txt`, with coordinates. |
| `service_calendars` | Weekly service patterns from `calendar.txt`, with start and end dates. |
| `service_exceptions` | Added or removed service dates from `calendar_dates.txt`. |
| `trips` | Rows from `trips.txt`, each linked to its route. |
| `stop_times` | The stop sequence and times for each trip, from `stop_times.txt`. |
| `shape_points` | Route shape points from `shapes.txt`. |
| `fare_attributes` | Fare prices from `fare_attributes.txt`: fare ID, price, currency, payment method (on board or before boarding) and the number of transfers the feed allows (empty when the feed does not say). |
| `fare_rules` | Fare rules from `fare_rules.txt`: the route, origin zone, destination zone or contained zone that each fare applies to. Rules that name a zone or a stop are stored but are never used to price a journey. |
| `scenarios` | Future scenario proposals, scoped to one device key. Always `ESTIMATED_SCENARIO`. They are never written into the timetable tables. |
| `scenario_stops` | Intermediate stops of a scenario, in order. |
| `saved_routes` | Routes a device has saved, scoped to that device key. |
| `user_preferences` | Key and value preferences for one device key. |
| `audit_logs` | Who did what and when, for administrative and scenario actions. Some entries record the client IP address. |

### Column reference

Generated from the SQLAlchemy models in `backend/app/models.py`:

```
audit_logs: id, created_at, actor, action, entity, entity_id, detail, ip
data_sources: id, name, publisher, source_url, license, kind, verified, verification_note, verified_by, verified_at, created_at
verification_records: id, data_source_id, action, note, actor, created_at
gtfs_imports: id, data_source_id, filename, sha256, size_bytes, status, classification, agency_name, feed_start_date, feed_end_date, route_count, stop_count, trip_count, stop_time_count, shape_point_count, is_active, warnings, errors, created_at
agencies: id, import_id, gtfs_id, name, url, timezone
routes: id, import_id, gtfs_route_id, short_name, long_name, route_type, color, text_color
stops: id, import_id, gtfs_stop_id, name, lat, lon, location_type
service_calendars: id, import_id, service_id, mon, tue, wed, thu, fri, sat, sun, start_date, end_date
service_exceptions: id, import_id, service_id, date, exception_type
trips: id, import_id, route_id, gtfs_trip_id, gtfs_route_id, service_id, headsign, direction_id, shape_id
stop_times: id, import_id, trip_id, stop_id, sequence, arrival_sec, departure_sec, stop_headsign
shape_points: id, import_id, gtfs_shape_id, sequence, lat, lon
fare_attributes: id, import_id, fare_id, price, currency, payment_method, transfers
fare_rules: id, import_id, fare_id, route_id, origin_id, destination_id, contains_id
scenarios: id, owner_hash, name, year, route_code, description, origin_name, origin_lat, origin_lon, destination_name, destination_lat, destination_lon, first_departure, last_departure, frequency_minutes, operating_days, status, created_at, updated_at
scenario_stops: id, scenario_id, sequence, name, lat, lon
saved_routes: id, client_hash, classification, gtfs_route_id, label, created_at
user_preferences: id, client_hash, key, value, updated_at
```

## Migrations

The schema is managed by Alembic migrations in `migrations/versions/`. The first migration, `0001`, creates the 16 tables
of the first release. `0002_fares` adds `fare_attributes` and `fare_rules`, which makes 18 tables in all. Other rules:

- The planner runs the migrations every time it starts, so the database is always brought up to date.
- Migration `0002` only adds the two fare tables. It changes no existing row. Feeds imported before it have no fare rows,
  because earlier versions did not read the fare files. Import the feed again to store its fares.
- A database built by an earlier build has the tables but no version record. It is marked as being at `0001` first,
  and only later migrations run. Its rows are kept. `tests/test_migrations.py` checks this.
- `python scripts/migrate_database.py` does the same on demand. It prints a JSON report and exits with `0` when the
  database is at the newest revision.
- Downgrading to `base` drops every table, so it deletes all data. Make a backup first.

### Adding a change to the schema

1. Change the model in `backend/app/models.py`.
2. Bring the database to the newest revision with `python scripts/migrate_database.py`.
3. Run `python -m alembic revision --autogenerate -m "short description"` from the project folder. Alembic writes a new
   file into `migrations/versions/`.
4. Read the generated file and correct anything autogenerate missed. SQLite changes use batch operations, which the
   environment enables with `render_as_batch`.
5. Run the tests with `python -m pytest`. `tests/test_migrations.py` checks that a new database at the newest revision
   matches the models, and that upgrade and downgrade work.

## Checking the database

```
python scripts/check_database.py
```

It reports the SQLite integrity check, foreign-key violations, the row count of each table, and whether the migration
revision is the newest one. It exits with `0` when everything is in order. It never creates a missing database.

## Backing up and restoring

```
python scripts/backup_database.py
```

- The backup uses SQLite's online backup API, so the server can keep running.
- Each copy is checked for integrity and its expected tables. Its migration revision is written into the report. If the check fails, the copy is deleted and
  the script reports an error.
- The file name is `planner_backup_YYYYMMDD_HHMMSS.db`, in UTC. A second backup in the same second gets `_2`, then `_3`.
- The default folder is `data/backups`, or `BACKUP_DIR` from `.env`. Choose another with `--out`.
- The administration page and the `POST /api/admin/backup` endpoint make the same copy and run the same check. The endpoint also writes an audit entry; the script does not.

To restore, stop the planner, delete `planner.db-wal` and `planner.db-shm` if they exist, and copy the backup over
`planner.db`. See `docs/INSTALL_WINDOWS.md` for the Windows steps.

## Retention and personal data

- Nothing is removed automatically. Audit entries and verification records are kept until someone deletes the database.
  Imports can be deleted by an administrator, which removes their timetable and fare rows. Scenarios and saved routes can
  be deleted by the device that owns them.
- The planner has no user accounts. A device is identified by a key kept in its browser. The database stores only the
  SHA-256 hash of that key.
- Audit entries for administrative and scenario actions include the client IP address.
