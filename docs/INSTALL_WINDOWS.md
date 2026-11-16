# Windows installation and daily use

This guide runs the planner on one Windows PC, which you then open in Chrome or Edge at `http://127.0.0.1:8000/`.
Phones need the extra steps in `docs/PHONE_ACCESS.md`.

**Status of the Windows scripts.** The `.bat` files use Windows (CRLF) line endings and plain ASCII, and every command
and path they use was checked against the code. They have **not been run on Windows**: the build environment is Linux.
The Python code was tested on Linux with Python 3.13 (see `docs/TEST_RESULTS.md`). If a step fails on Windows, copy the
exact message when you report it.

## 1. Install Python

1. Install Python 3.13 from python.org. The Linux checks used this version. The setup script accepts 3.11 or newer, but
   3.11 and 3.12 have not been tested.
2. On the first installer screen, tick **Add python.exe to PATH**.
3. If the setup script reports that Python was not found, Windows may be using its App execution alias for
   `python.exe`. Open **Settings > Apps > Advanced app settings > App execution aliases**, turn off the `python.exe`
   and `python3.exe` aliases, then open a new Command Prompt.

## 2. Unpack the planner

1. Unzip the planner archive to a folder such as `C:\BMTC-Planner`.
2. Do not keep the folder inside OneDrive or another sync folder. Sync tools can lock or copy the database file while
   the server is running.

## 3. Set up once

In Command Prompt, from the planner folder, run:

```
scripts\setup_windows.bat
```

The script:

- finds Python 3.11 or newer, first as `python` and then as `py -3`
- creates a virtual environment in `.venv`
- installs the packages in `requirements-dev.txt`
- copies `.env.example` to `.env` if there is no `.env` yet
- runs `scripts\migrate_database.py`, which creates `data\planner.db` or upgrades it, then `scripts\check_database.py`

## 4. Set the administrator key

Open `.env` in Notepad and set `ADMIN_API_KEY` to a long random value. The example file recommends at least 32
characters. The server only checks that the key is not empty, so choosing a long key is up to you. PowerShell can make
one:

```
powershell -NoProfile -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')"
```

Keep `.env` private. While `ADMIN_API_KEY` is empty, uploads, verification, backups and the audit log are disabled.
The server reads `.env` once, when it starts, so restart it after any change. A variable already set in the Windows
environment takes precedence over `.env`.

## 5. Run the tests (optional)

```
scripts\run_tests_windows.bat
```

Every test uses its own temporary database, so your data is not touched. The last line shows the number of tests
passed. A failing test is listed with its details above that line.

Two optional checks need a few extra steps. Both have been run on Linux only, not yet on Windows. Activate the virtual
environment first (`.venv\Scripts\activate`).

- **Browser checks:** `python -m pip install -r requirements-browser.txt`, then
  `python tests\browser\run_browser_checks.py --chrome "C:\Program Files\Google\Chrome\Application\chrome.exe"`.
  The runner starts its own server on a free port, with a temporary database and a random admin key. It runs 121 checks,
  stops the server, and does not touch `data\`.
- **Mutation check:** `python tests\mutation\mutation_check.py`. It breaks ten safety rules one at a time, in temporary
  copies of the project, and confirms that the tests fail each time. It takes a few minutes and does not change your files.

## 6. Start the planner

```
scripts\run_windows.bat
```

Open `http://127.0.0.1:8000/` in Chrome or Edge. Press **Ctrl+C** in the command window to stop the server. This
address works only on this PC.

## 7. Load timetable data

The planner ships with **no official BMTC data**. Read `SOURCES.md` before importing any feed. Then, with the virtual
environment active (`.venv\Scripts\activate`), import a feed from the planner folder:

```
python scripts\import_gtfs.py --file "C:\Downloads\feed.zip" --new-source "Publisher name" --kind UNKNOWN
```

`--kind` records what the source is: `UNKNOWN`, `COMMUNITY`, `SYNTHETIC_DEMO` or `OFFICIAL`. Only a source of kind
`OFFICIAL` that an administrator has verified produces `OFFICIAL_VERIFIED` data. Every other import is shown as
`UNVERIFIED_FEED`.

Verification is a separate, explicit step, and it works only for a source created with `--kind OFFICIAL`:

```
python scripts\import_gtfs.py --source-id 1 --verify --note "Checked against the publisher's own page"
```

Use the id shown in the Data sources table on the Administration page. `--revoke` withdraws verification.

Exit codes: `0` success, `1` a usage or file error, `2` the feed was rejected (the JSON report lists why), `3`
verification was refused.

The Administration page can do the same after you sign in with the admin key: upload a ZIP, verify an `OFFICIAL`
source (its button is disabled for other kinds), or create a backup.

To try the planner with invented data, generate and import the synthetic demo feed. It contains invented stops, routes
and trips, is labelled `SYNTHETIC_DEMO`, and is not BMTC timetable data:

```
python scripts\make_synthetic_gtfs.py --out data\demo_feed.zip
python scripts\import_gtfs.py --file data\demo_feed.zip --new-source "Demo publisher" --kind SYNTHETIC_DEMO
```

Remove it from the Imports table on the Administration page with **Delete import N**.

## 8. Back up and check the database

```
scripts\backup_windows.bat
```

This writes a copy of `data\planner.db` to `data\backups`, or to the folder set by `BACKUP_DIR` in `.env`. It works while
the server is running. The copy is checked for integrity and its expected tables, and the script reports success only
if that check passes. To choose another folder:

```
scripts\backup_windows.bat --out "D:\BMTC-backups"
```

To check the live database at any time:

```
python scripts\check_database.py
```

It prints a JSON report and exits with `0` when the database is healthy.

**To restore a backup** (the server must be stopped with Ctrl+C):

1. Delete `data\planner.db-wal` and `data\planner.db-shm` if they exist. They belong to the database being replaced,
   and a leftover file from a server that stopped unexpectedly could corrupt the restored copy.
2. Copy the backup file over `data\planner.db`, so that the copy is named `planner.db`.
3. Run `python scripts\check_database.py`, then `scripts\run_windows.bat`.

These steps follow the same order as the Linux restore drill, `scripts/restore_drill.sh`, which runs them on a copy of
the project. The drill is a shell script and does not run on Windows, so these steps have not been run on Windows.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Python 3.11 or newer was not found." | Install Python 3.13, tick **Add python.exe to PATH**, then see step 1 if the message continues. |
| "Python was not found" in Command Prompt | The App execution alias is intercepting `python`. See step 1. |
| "Setup stopped with an error." | Read the lines above that message, fix the cause, then run `scripts\setup_windows.bat` again. |
| The server stops with "address already in use" | Another program uses port 8000. Close it, or change `--port 8000` in `scripts\run_windows.bat` and use the new address. |
| The Administration page says it is disabled | `ADMIN_API_KEY` is empty in `.env`. Set it, then restart the server. |
| "Invalid or missing admin key." | The key typed does not match `ADMIN_API_KEY` in `.env`. Keys are case-sensitive. |
| `check_database.py` reports a problem with the revision | Run `python scripts\migrate_database.py`, then `python scripts\check_database.py` again. |
| Windows Firewall asks about Python | Not needed for `127.0.0.1`. For phone access with `scripts\run_lan_windows.bat`, allow it on private networks only, after reading `docs/PHONE_ACCESS.md`. |
