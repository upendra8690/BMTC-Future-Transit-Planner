# Test results

This file records what was run to verify this build, BMTC Future Transit Planner 3.0.0, and what came back. The verification runs began at 20:23 UTC on 15 November 2026. Since then no code file has changed. The files that changed are documents, the dependency pins, the banner image and a test cache. A second set of runs was made in a fresh environment at 21:19 to 21:21 UTC on the same day. The raw logs were kept outside the package, so they are not included here. Commands are shown as they were run from the project folder.

## Environment

| Item | Value |
|---|---|
| Operating system | Ubuntu 24.04.5 LTS, x86_64 (the build sandbox) |
| Hardware | 2 vCPU (Intel Xeon Processor, 2.10 GHz), 7.8 GiB RAM. A shared sandbox, so timings vary between runs |
| Python | 3.13.18 (from `/usr/local/bin/python3.13`) |
| Pinned packages | `requirements-verified.txt`, 50 packages. Among them FastAPI 0.163.1, Starlette 1.10.0, SQLAlchemy 2.1.8, Alembic 1.20.1, uvicorn 0.54.0, Pydantic 2.14.3, reportlab 5.1.0, pypdf 6.21.4, tzdata 2026.6 |
| Test tools (pinned) | pytest 9.2.0, hypothesis 6.170.15, freezegun 1.5.5, ruff 0.17.5, bandit 1.9.4 |
| Audit tool | pip-audit 2.10.1, installed separately from the pins |
| Browser | Google Chrome for Testing 153.0.8010.12 at `/usr/bin/google-chrome`, driven by Playwright 1.65.2 (pinned) in headless mode |
| Container tools | Docker 29.9.3 and Docker Compose v5.7.0. The Docker daemon was not running in the sandbox |
| Node.js | v22.23.4, used only for syntax checks of the dashboard scripts |

Two Python environments were used:

- **Verification environment.** Python 3.13.18 with the pinned versions installed, plus pip-audit and the tree-sitter and tree-sitter-dart packages used by the Android check. It was used for the first set of runs (20:23 to 20:34 UTC): tests, lint, bandit, the dependency audit, the Node syntax check, the Android check, the browser checks, the mutation checks, the restore drill and the benchmark.
- **Fresh environment.** A new virtual environment built from `requirements-verified.txt` alone. `pip check` reports no broken requirements, and `pip freeze` matches the 50 pins exactly. It was used for the second set of runs (21:19 to 21:21 UTC): tests, lint, bandit, the browser checks, the restore drill and the benchmark. The mutation checks and the Android check were not repeated in it.

The fresh environment was built after a gap was found. The pins had left out `freezegun`, which `tests/test_plan_api.py` imports, and the `python-dateutil` version that `freezegun` needs. Both were added (section 12).

## Summary

| Check | Command | Verification environment (20:23 to 20:34 UTC) | Fresh environment (21:19 to 21:21 UTC) |
|---|---|---|---|
| Automated tests | `python -m pytest -p no:cacheprovider` (`pytest.ini` adds `-q`) | 366 passed, 1 warning, 38.50 s, exit 0 | 366 passed, 1 warning, 43.37 s, exit 0 |
| Lint | `python -m ruff check --no-cache .` | All checks passed, exit 0 | All checks passed, exit 0 |
| Static security scan, main scope | `python -m bandit -r backend scripts migrations android/check_starter.py tests/browser tests/mutation` | Exit 0 (quiet run) | Exit 0. No issues identified; 10 suppressed by `# nosec` |
| Static scan of test modules (informational) | `python -m bandit -q -r tests/test_*.py` | 917 low-severity issues, none medium or high | Exit 1 by design: 917 low-severity issues, none medium or high |
| Browser checks | `python tests/browser/run_browser_checks.py --chrome /usr/bin/google-chrome` | 121 passed, 0 failed, exit 0 | 121 passed, 0 failed, exit 0 |
| Mutation checks | `tests/mutation/mutation_check.py` and `tests/mutation/planner_mutation_check.py` | 10 of 10 caught in each; control passed in each | Not repeated |
| Restore drill | `PYTHON=<venv>/bin/python scripts/restore_drill.sh <log file>` | 29 of 29 checks passed | 29 of 29 checks passed |
| Planner benchmark | `python scripts/bench_planner.py` (defaults) | Exit 0 (section 9) | Exit 0 (section 9) |
| Node syntax | `node --check` on `app.js`, `i18n.js` and `sw.js` | Exit 0 (20:23 UTC); the three files passed again at 21:13 UTC | Not repeated |
| Android starter (static checks) | `python android/check_starter.py` | Passed. The app is not compiled | Not repeated |
| Dependency audit | `pip-audit` (section 4) | Two runs at 20:23 to 20:24 UTC, before the final pins: no known vulnerabilities | Not repeated. Four runs on the final pins at 20:48 UTC: no known vulnerabilities |
| Pin reproduction | `pip install -r requirements-verified.txt` into a new venv | Not applicable | 50 packages, identical to the pins; `pip check` clean |

Container checks are in section 11. "Not repeated" means the check was not run in that environment.

## 1. Automated tests

Command: `python -m pytest -p no:cacheprovider`. The options in `pytest.ini` add `-q`.

Verification environment: `366 passed, 1 warning in 38.50s`, exit 0. Fresh environment: `366 passed, 1 warning in 43.37s`, exit 0.

The warning is `StarletteDeprecationWarning`. It says that using `httpx` with `starlette.testclient` is deprecated, and it suggests installing `httpx2` instead. It is raised when FastAPI's test client is imported, comes from a third-party package, and does not affect any result. It is reported, not suppressed.

Tests per file (collected in the fresh environment with `pytest --collect-only`; the total matches the verification run):

| File | Tests |
|---|---|
| `tests/test_gtfs_importer.py` | 37 |
| `tests/test_api.py` | 35 |
| `tests/test_exports_and_pdf.py` | 34 |
| `tests/test_dashboard_static.py` | 23 |
| `tests/test_scenarios.py` | 22 |
| `tests/test_planner.py` | 21 |
| `tests/test_now_api.py` | 21 |
| `tests/test_schedule.py` | 20 |
| `tests/test_config.py` | 18 |
| `tests/test_importer_regressions.py` | 17 |
| `tests/test_windows_launchers.py` | 16 |
| `tests/test_maintenance.py` | 16 |
| `tests/test_cli.py` | 15 |
| `tests/test_fares.py` | 14 |
| `tests/test_clock.py` | 11 |
| `tests/test_search.py` | 8 |
| `tests/test_text_and_search.py` | 6 |
| `tests/test_security_headers.py` | 5 |
| `tests/test_plan_api.py` | 5 |
| `tests/test_migrations.py` | 5 |
| `tests/test_hardening.py` | 5 |
| `tests/test_security.py` | 4 |
| `tests/test_rate_limit.py` | 4 |
| `tests/test_trusted_proxy.py` | 2 |
| `tests/test_planner_performance.py` | 1 |
| `tests/test_openapi.py` | 1 |
| **Total** | **366** |

## 2. Lint

Command: `python -m ruff check --no-cache .`. Result: `All checks passed!`, exit 0 in both environments.

## 3. Static security scan

**Main scope.** Command: `python -m bandit -q -r backend scripts migrations android/check_starter.py tests/browser tests/mutation`. The verification run was quiet and exited 0. A non-quiet run of the same scope in the fresh environment printed `No issues identified.`, counted 6,595 lines of code, and reported 10 potential issues disabled by `# nosec` comments. Those comments are:

| Location | Rule | Why it is suppressed |
|---|---|---|
| `scripts/bench_planner.py:55` | B311 | Seeded random generator, for benchmark data only |
| `scripts/bench_planner.py:122` | B311 | Seeded random generator, for benchmark queries only |
| `tests/browser/run_browser_checks.py:31` | B404 | The runner starts only fixed local commands, always passed as lists |
| `tests/browser/run_browser_checks.py:49` | B603 | Fixed command list, no shell |
| `tests/browser/run_browser_checks.py:114` | B603 | Starts the test server from a fixed list, no shell |
| `tests/browser/run_browser_checks.py:134` | B603 | Fixed command list, no shell |
| `tests/mutation/mutation_check.py:13` | B404 | Runs pytest with a fixed argument list and no shell |
| `tests/mutation/mutation_check.py:62` | B603 | Fixed argument list, run with this same interpreter |
| `tests/mutation/planner_mutation_check.py:13` | B404 | Runs pytest with a fixed argument list and no shell |
| `tests/mutation/planner_mutation_check.py:54` | B603 | Fixed argument list, this interpreter, no shell |

The quiet verification run also printed 46 warnings such as `Test in comment: list is not a test name or id, ignoring`. They come from the explanation text after the rule IDs in those comments, which bandit reads as words rather than rule IDs. The suppressions still apply to the rules they name.

**Test modules (informational).** Command: `python -m bandit -q -r tests/test_*.py`. Exit 1 is expected, because bandit exits 1 whenever it reports an issue and this scan does not gate the build. It reports 917 low-severity issues in 3,536 lines of code, and none medium or high:

| Rule | Count | Meaning |
|---|---|---|
| B101 | 912 | `assert` used (in tests, expected) |
| B404 | 2 | `subprocess` imported |
| B603 | 2 | `subprocess` called without a shell |
| B311 | 1 | Use of the `random` module |

These are test modules, not the running application, and the scan does not gate the build.

## 4. Dependency audit

Four runs were made on the final pins, all with pip-audit 2.10.1, after the pins were last changed at 20:46 UTC. Each run's report lists no known vulnerabilities.

| Run | Command | Packages audited | `packaging` listed | Vulnerabilities |
|---|---|---|---|---|
| 1 | `pip-audit -r requirements-verified.txt` (default method) | 49 | No | 0 |
| 2 | `pip-audit -r requirements-verified.txt --disable-pip --no-deps` | 50 | Yes | 0 |
| 3 | `pip-audit --path <fresh venv>/lib/python3.13/site-packages` | 51 (the 50 pins and `pip`) | Yes | 0 |
| 4 | `pip-audit -r requirements-dev.txt -r requirements-browser.txt` (version ranges) | 49 | No | 0 |

The default method does not list `packaging`, which is pinned at 26.3. Run 2 lists all 50 pins, so it is the run that covers every pin. Before the final pins were set, the verification environment was audited with the default method and with `pip-audit --local`, at 20:23 and 20:24 UTC. Both printed `No known vulnerabilities found` and exited 0.

Audit results are a snapshot. New advisories can appear later, so repeat the audit before any real deployment.

## 5. Browser checks

Command: `python tests/browser/run_browser_checks.py --chrome /usr/bin/google-chrome`.

The runner builds the synthetic demo feed in a temporary folder, imports it as `SYNTHETIC_DEMO`, and builds a second feed for dates that do not overlap the demo. It starts its own server on a free local port (127.0.0.1) with a temporary database, a temporary backup folder and a random admin key. It runs the checks, then stops the server. The project's `data/` folder is not used.

Result: `121 passed, 0 failed`, exit 0 in both environments.

Expected responses, reported by the runner and not counted as failures. The counts were the same in both environments:

- 4 deliberate 401 responses from the wrong-key check.
- 1 deliberate 404 response from the unknown-route check.
- 1 deliberately refused upload.
- 6 requests that failed while the browser was set offline, as the offline checks intend.
- 102 map-tile requests that failed. The sandbox refuses the OpenStreetMap tile hosts (`ERR_TUNNEL_CONNECTION_FAILED`), so no map imagery was seen. The map code is still checked.
- Other browser problems: 0.

The 121 checks, by area:

| Area | Checks | What is checked |
|---|---|---|
| Years and coverage | 4 | Year banners say when no officially verified timetable exists and when the unverified feed covers a year. The official list is empty and says why. The planning-year table has one row per year. |
| Routes and timetables | 9 | The DEMO-1 timetable on Friday 1 January 2027 lists 66 trips. The route map draws the planned path. The timetable CSV has the expected columns, name and trips. A saved route stays listed after a reload. An unknown route gets a clear message. |
| Clock and notices | 4 | The clock bar names the feed's time zone, the service date and its weekday. Every page says the planner is unofficial and not affiliated with BMTC or any operator. |
| Stops | 7 | The six demo stops are listed. The stops map is created. Stop search narrows the list. Stops near the device location appear. A stop list is kept for offline reading. A search with typed words is not kept. Leaving a fitted map at once raises no map error. |
| Journeys | 6 | The date stays disabled until "On a date" is chosen. The form offers no change, up to one change and up to two changes. Journeys for Monday 11 January 2027 are listed, at most five options. The result says live positions are not available and labels the earliest arrival. With no change allowed, no option has a change. |
| Scenarios and comparison | 13 | A scenario is saved with an estimate and its label. A last departure before the first is refused on screen and is not saved. Edits keep the estimate. A name containing HTML is shown as plain text. The scenario CSV and PDF download. The comparison lists distance, journey time and departures, and its PDF downloads. |
| Sources and administration | 23 | The demo source is shown as `SYNTHETIC_DEMO`, not verified. A wrong admin key is refused. The right key opens administration. Verify is disabled for a non-`OFFICIAL` source. Verification asks for evidence, can be cancelled, and can be revoked. A feed can be uploaded, listed and removed, and its report gives the fare count. A file that is not a valid feed is refused, and the report says nothing was stored. A backup file is written. The audit log records actions. Forgetting the key hides the administration data. |
| Browser storage | 6 | Storage holds only the planner's own keys, and never the admin key. Checked while the key is in use, after it is forgotten, and at the end of the desktop checks. |
| Accessibility | 8 | The first Tab press lands on the skip link, and following it moves focus into the content. A keyboard-focused button shows a visible focus ring. Enter presses a filter button, and arrow keys move between change choices. A new service worker shows a reload notice. axe-core (WCAG 2.1 AA) finds no violations on any main view. |
| Languages | 10 | Kannada, Telugu and Hindi translate the navigation, apply their font stacks, and keep text left to right. Switching back to English restores the navigation. |
| Offline | 9 | A timetable opened online is shown offline with the same rows, labelled as a saved copy with the time it was saved. The note goes away when the server answers again. The offline banner appears and hides. A search made offline shows an error with a retry button. Retrying after reconnecting loads the list. The app shell loads from the cache while offline. |
| Installation | 4 | The manifest is served with the right type, declares English, left-to-right and standalone display, and has 192 and 512 pixel icons. The service worker is registered. |
| Phone layout | 17 | On a Pixel 7 profile, the menu opens, closes with Escape, and closes on choosing a page. Each main page has no sideways scrolling. The scenario form and route detail fit the screen. Routes in Kannada, Telugu and Hindi fit a phone. |
| Errors | 1 | No unexpected browser errors, uncaught exceptions or failed requests. |

The phone checks use Playwright's Pixel 7 device profile in headless Chrome. They were not run on a real phone.

## 6. Mutation checks

Each harness applies one broken rule at a time to a temporary copy of the project and runs the test suite against it. A broken rule counts as caught only if at least one test fails against it. The unmodified control must pass every test. The project itself is not changed. Both harnesses are run by hand. In the verification run the project harness took about 8 minutes and the planner harness about 1.5 minutes.

**Project harness** (`tests/mutation/mutation_check.py`). Control: 366 passed, 1 warning, verdict control OK. Result: `10 of 10 broken rules caught`, exit 0.

| # | Rule broken in the copy | Tests that failed |
|---|---|---|
| 01 | Search escaping of `%`, `_` and `\` removed | 6 |
| 02 | Legacy database not stamped at the baseline revision | 1 |
| 03 | Any source can be verified, not only `OFFICIAL` | 1 |
| 04 | Admin routes open when no key is set | 1 |
| 05 | Device keys stored raw instead of as SHA-256 | 1 |
| 06 | Inline script added to the dashboard page | 1 |
| 07 | A message key removed from the English dictionary | 3 |
| 08 | Service worker answers every API request from its saved copy, not only timetable answers | 1 |
| 09 | The language setting replaced by a save of the admin key in browser storage (`app.js`) | 1 |
| 10 | `eval` added to the dashboard | 1 |

**Planner harness** (`tests/mutation/planner_mutation_check.py`). Control: 40 passed, 1 warning. Result: `10 of 10 mutations caught`, exit 0.

| # | Rule broken in the copy | Tests that failed |
|---|---|---|
| 1 | Minimum change time ignored | 1 |
| 2 | Overtaking trips not split into lanes | 1 |
| 3 | Trips from the previous service day ignored | 1 |
| 4 | Walks between stops ignored | 4 |
| 5 | Fares that apply to every route ignored | 2 |
| 6 | Zone-limited fares treated as route fares | 1 |
| 7 | Fares added up across changes | 2 |
| 8 | `max_changes` ignored by the search | 1 |
| 9 | Classification filter dropped | 2 |
| 10 | Cached network ignores the identity of the import | 1 |

## 7. Restore drill

Command: `PYTHON=<venv>/bin/python scripts/restore_drill.sh <log file>`. The drill runs on Linux in a new temporary copy of the code folders. It never reads or changes the project's `data/` folder or `.env`. Its header says it is tested on Linux only, and that macOS has not been tested.

Result: `checks run: 29, failed: 0`, `restore drill: PASSED`, exit 0 in both environments. The details below are from the verification run.

| Step | Checks | What happened |
|---|---|---|
| 1. Command-line help | 1 to 3 | `import_gtfs.py`, `backup_database.py` and `make_synthetic_gtfs.py` each print help and exit 0. |
| 2. Create and migrate | 4 to 5 | `migrate_database.py` migrated a new database to head revision `0002`, and reported it up to date. The new database passes the check. |
| 3. Demo feed | 6 to 7 | The synthetic feed imported as `SYNTHETIC_DEMO`, status `COMPLETED`, classification `UNVERIFIED_FEED`: 2 routes, 6 stops, 192 trips, 960 stop times and 20 shape points. Exactly one data source exists. |
| 4. Refusals and rejections | 8 to 14 | A new source cannot be created and verified in one command (exit 1). Verifying a synthetic source is refused (exit 3). The refusal creates no source, leaves the source unverified, and writes no verification record. A feed without the GTFS files is rejected with status `REJECTED` and exit 2, and stores no routes, stops or trips. A missing file gives exit 1. |
| 5. Backup, damage, restore | 15 to 22 | A verified backup was written: integrity `ok`, revision `0002`, 331,776 bytes. The database's first 8 KiB were overwritten with random bytes, and the check then failed as expected. After the `-wal` and `-shm` files were removed and the backup was copied over the database, the check passed, and its report matched the one from before the damage apart from `checked_at`. |
| 6. Serve | 23 to 29 | The server started on the restored database. `/api/health` returned 200, and its report says the service is ok. `/api/data-sources` listed the demo source as `SYNTHETIC_DEMO`. `/api/routes?classification=UNVERIFIED_FEED` returned routes. The server log has no traceback. |

## 8. Import command exit codes

`scripts/import_gtfs.py` exits as documented in `docs/INSTALL_WINDOWS.md`, and its `--help` text gives the same codes. The restore drill observed each one:

| Code | Meaning | Observed |
|---|---|---|
| 0 | Success | Importing the demo feed |
| 1 | Usage or file error | Combining `--new-source` with `--verify`; a missing file |
| 2 | Feed rejected | A ZIP without the required GTFS files. Its record is kept with status `REJECTED`, with no timetable rows |
| 3 | Verification refused | `--source-id 1 --verify` on a `SYNTHETIC_DEMO` source. The message was "only sources of kind OFFICIAL can be verified" |

## 9. Planner benchmark

Command: `python scripts/bench_planner.py`, with its defaults: 2,000 stops, 300 routes, 5 trips per route, 30 stops per trip, and 40 queries per measure. It ran twice: in the verification environment at about 20:34 UTC, and in the fresh environment at about 21:20 UTC. Both runs exited 0.

The benchmark runs in a temporary database. Its generated feed is registered as an official, verified source, so that the planner's official path is exercised. **This is synthetic data, not BMTC data. The numbers describe this sandbox and this generated network. They are not measurements of real timetables or of production hardware.**

Generated network: 2,000 stops in a box about 22 km square, 1,500 trips, 45,000 stop-time rows and a 374,632-byte ZIP. Generating the neighbour data took 1.73 s and 1.76 s, and the import took 0.82 s and 0.88 s, in the two runs.

Timings in milliseconds, over 40 queries per measure:

| Measure | Verification: min / median / max | Fresh: min / median / max | What it covers |
|---|---|---|---|
| Cold pass, 11 January 2027 | 6.6 / 15.1 / 532.2 | 4.8 / 11.9 / 505.5 | The network cache is cleared first, so the first query builds the network and the rest reuse it |
| Repeat, same date | 7.9 / 14.0 / 23.9 | 4.8 / 11.8 / 14.9 | The network is already cached |
| New date, 12 January 2027 | 5.1 / 13.0 / 639.6 | 8.2 / 18.6 / 681.1 | The first query builds that date's network |
| Direct only (zero changes), same date | 4.8 / 5.8 / 11.7 | 5.4 / 6.1 / 8.0 | `max_changes` set to 0 |

Four of the first five query pairs returned at least one journey on 11 January 2027 in both runs. Each run is a single measurement on a shared 2-vCPU sandbox. Timings vary between runs, and the maximums are the most variable values. This is not a load test.

## 10. Android starter and Windows launchers

**Android starter (static checks only).** Command: `python android/check_starter.py`. Exit 0 in the verification run. Output:

```
YAML ok: pubspec.yaml and analysis_options.yaml
Dart grammar: 0 ERROR node(s), 0 missing token(s) in lib/main.dart
found   reads the planner address from --dart-define: String.fromEnvironment('PLANNER_URL')
found   allows JavaScript, which the dashboard needs: JavaScriptMode.unrestricted
found   decides navigation for every link: onNavigationRequest
found   reports load errors for the main frame only: isForMainFrame
found   loads the planner address: loadRequest(
found   imports webview_flutter: package:webview_flutter/webview_flutter.dart
RESULT: static checks passed. The app itself has not been compiled.
```

Flutter is not installed in the build sandbox, and no APK was built.

**Windows launchers (text checks only).** `tests/test_windows_launchers.py` passed its 16 tests inside the pytest run in both environments. They check that the five launchers in `scripts/` exist (`setup_windows.bat`, `run_windows.bat`, `run_lan_windows.bat`, `run_tests_windows.bat` and `backup_windows.bat`), that each is plain ASCII with Windows line endings, and that every script and requirements file a launcher names exists. The launchers were not run on Windows.

## 11. Docker kit

Files: `Dockerfile`, `docker-compose.yml` and `deploy/Caddyfile`. The Compose checks ran in a scratch copy that holds only those files and a `.env` file. That copy is outside the project and the package.

- `docker compose config -q` with `PLANNER_DOMAIN=planner.example.org`: exit 0.
- `docker compose config -q` with `PLANNER_DOMAIN=` (blank): exit 1, with `required variable PLANNER_DOMAIN is missing a value`.
- `docker buildx build --check .`: exit 1. The Docker daemon is not running in the sandbox (`Cannot connect to the Docker daemon`), so the build check could not run.

Not done: the image was not built, no container was run, Caddy did not obtain a certificate, and the Docker volume restore was not run. `docs/DEPLOY.md` records the same limits.

## 12. Changes made during this build's verification

- **Dependency pins.** `freezegun` was missing from both `requirements-verified.txt` and `requirements-dev.txt`, although `tests/test_plan_api.py` imports it. The fresh environment exposed the gap. `python-dateutil==4.0.0`, which `freezegun` needs, was also missing from the pins. Both were added, and `freezegun` was added to `requirements-dev.txt`. `setup_windows.bat` installs `requirements-dev.txt`, so Windows setup includes `freezegun` too.
- **Translation.** The message code `msgcode.NO_DIRECT_SERVICE` had no translation, although the server sends it. Its text is now in English, Kannada and Hindi, restored from the 2.0 text, and there is a Telugu draft. Two static tests check the message codes: one checks that the codes the test lists match the codes the server sets, and one checks that each listed code has a translation in every language.
- **Documentation corrected to match the code.** `docs/architecture.md` (feed states, including `GAP_TODAY`; the service clock; the network cache key; the scenario estimates; audit actors; the SQL statements; the restore drill; the Windows launchers; the service worker), `docs/TRANSLATION.md`, `docs/PRIVACY.md`, `docs/SECURITY_ASVS.md` (the bandit figures and the V12 wording), `docs/API.md` (the leg fields) and `README.md`. The bandit figures in `docs/SECURITY_ASVS.md` match section 3.
- **Banner.** `assets/banner.svg` shows the current figures (366 tests and 38 operations) and a neutral tagline.
- **This file and `README.md`** were checked line by line against the logs and the code.

## 13. Not verified

- **Windows.** The `.bat` launchers, the setup steps and the restore steps were not run on Windows. Only their text was checked.
- **Python versions.** Every run used Python 3.13.18. Python 3.11 and 3.12 were not tested, even though the setup script accepts 3.11 or newer.
- **Real phones and tablets.** None was used. Phone checks use headless Chrome with a Pixel 7 device profile.
- **Other browsers.** Only Chrome was used. Safari and Firefox were not tested.
- **Installing as an app.** The manifest and service worker were checked in headless Chrome. The install step was not tested on any device.
- **Local network access (plain HTTP).** Not tested. The browser checks ran on `127.0.0.1`.
- **Android and iOS apps.** The Flutter starter was not compiled. No APK or IPA exists.
- **PostgreSQL.** Only SQLite was used. Automatic backup returns 501 for PostgreSQL, and the message points to `pg_dump`.
- **Official data.** None is loaded. The DULT Transport Data Hub could not be reached from the sandbox, and its licence has not been read. The planner shows no official timetable for 2027 to 2030.
- **Real city feeds.** Only the synthetic demo feed was imported. Namma Metro data is not included.
- **Live positions.** None. No verified real-time source is connected.
- **Look-ahead windows.** Departures for a stop search the service days from two days before today to seven days ahead. Leave-now journeys from `/api/plan` search the next three hours, over the service days from two days before today to tomorrow. Each day's service comes from the feed's own calendar.
- **Kannada, Telugu and Hindi wording.** All three are first drafts. No native speaker has reviewed them. Right-to-left languages were not tested.
- **PDF text.** PDF exports are in English. Characters the PDF font cannot show are replaced with `?`, and a notice is added to the export.
- **Map imagery.** The sandbox refuses the OpenStreetMap tile hosts, so no map tiles were seen.
- **Docker image, Caddy and the Docker volume restore.** Not built or run. See section 11.
- **Load and performance.** Two benchmark runs on a generated network, on a shared 2-vCPU sandbox (section 9). Nothing else was measured.
- **Screen readers.** No screen-reader testing was done.
- **Security testing beyond the automated checks.** There was no penetration test. The security evidence is the automated tests, the mutation checks, bandit, and the dependency audit.
- **Later advisories.** The dependency audit is a snapshot taken on 15 November 2026.
- **Absence of bugs.** The checks above cannot prove that the software has no bugs. They show that the listed checks pass.

## 14. The packaged copy

The delivery ZIP has one top folder, `bmtc_future_transit_planner_3_0`, which contains `MANIFEST.sha256`. The manifest lists a SHA-256 hash for every file in the package, except itself. To check a copy, extract the ZIP into a new empty folder, change into the extracted `bmtc_future_transit_planner_3_0` folder, and run `sha256sum -c MANIFEST.sha256`. Then run `python -m pytest -p no:cacheprovider` and `python tests/browser/run_browser_checks.py --chrome /usr/bin/google-chrome`.

The results for the delivered copy are reported with the package, not in this file, because this file ships inside the package.
