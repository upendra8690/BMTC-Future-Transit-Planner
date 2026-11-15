# Test results

This file records what was run to verify this package, and the output that came back. Each result below comes from a run
on the source tree before the package was made. Nothing here is a mock or an estimate. The commands can be repeated
from the project folder, as shown.

## Environment

| Item | Value |
|---|---|
| Operating system | Ubuntu 24.04.5 LTS, x86_64 (the build sandbox) |
| Python | 3.13.18, in a new virtual environment |
| Installed from | `requirements-dev.txt` and `requirements-browser.txt`. The exact versions are in `requirements-verified.txt` (Linux only). |
| Browser | Google Chrome for Testing 153.0.8010.12, driven by Playwright 1.65.2 through `--chrome` |
| Tools | pytest 9.2.0, ruff 0.17.5, bandit 1.9.4, pip-audit 2.10.1 |

Not tested: Windows (the `.bat` launchers and the Windows install steps), Python 3.11 and 3.12, PostgreSQL, a real Android
phone, a real iPhone, and any Flutter or Android build.

## Summary

| Check | Command | Result |
|---|---|---|
| Automated tests | `python -m pytest` | 159 passed, 1 warning (third-party, see section 1) |
| Lint | `ruff check .` | All checks passed |
| Static security scan | `bandit -r backend scripts migrations tests/browser tests/mutation` | No issues identified. Seven intentional suppressions, each with a reason (section 3) |
| Dependency audit | `pip-audit -r requirements-verified.txt` and `pip-audit -r requirements-dev.txt -r requirements-browser.txt` | No known vulnerabilities found, for both |
| Browser checks | `python tests/browser/run_browser_checks.py --chrome /usr/bin/google-chrome` | 36 passed, 0 failed |
| Mutation checks | `python tests/mutation/mutation_check.py` | 5 of 5 broken rules caught; the unmodified control passed |
| Restore drill | scripted steps (section 7) | Every step behaved as documented |
| Import command exit codes | probes (section 8) | 0, 1, 2 and 3 each observed |
| Android starter | `python android/check_starter.py` (static) | Passed. The app has not been compiled. |
| Windows launchers | byte and reference checks (section 10) | Passed. Not run on Windows. |

## 1. Automated tests

Command: `python -m pytest`. The `addopts` setting in `pytest.ini` already passes `-q`, so the summary line is the last line.

```
........................................................................ [ 45%]
........................................................................ [ 90%]
...............                                                          [100%]
=============================== warnings summary ===============================
.../site-packages/fastapi/testclient.py:1
  .../fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
159 passed, 1 warning in 18.75s
```

The warning is raised when FastAPI's test client is imported. It comes from the installed FastAPI and Starlette packages,
not from project code. `pytest.ini` ignores `DeprecationWarning`, but this warning class is not a subclass of it. It does
not change any result. Removing it would mean changing the test client or the dependency set, which has not been done.

## 2. Lint

Command: `ruff check .`. Output: `All checks passed!`

One exemption is set in `ruff.toml`: the mutation check may use `print`, as the browser runner already may.

## 3. Static security scan

Command: `bandit -r backend scripts migrations tests/browser tests/mutation`

Output: `No issues identified.` 4,089 lines were scanned. Seven potential issues were skipped because each is disabled by a
`# nosec` comment in the code:

| Location | Rule | Why it is accepted |
|---|---|---|
| `backend/app/services/maintenance.py:60` | B608 (SQL text built from strings) | The table name comes from the model metadata, never from user input. The line has a comment that says so. |
| `tests/browser/run_browser_checks.py:30` | B404 (subprocess import) | The runner starts only fixed local commands. |
| `tests/browser/run_browser_checks.py:48`, `:107`, `:126` | B603 (subprocess without a shell) | Each command is a fixed argument list, with no shell. |
| `tests/mutation/mutation_check.py:13` | B404 | Same reason, for the pytest runs in temporary copies. |
| `tests/mutation/mutation_check.py:50` | B603 | Same reason. |

Bandit also writes informational `INFO` lines to stderr. The metrics above are the result.

## 4. Dependency audit

- `pip-audit -r requirements-verified.txt`: `No known vulnerabilities found`
- `pip-audit -r requirements-dev.txt -r requirements-browser.txt`: `No known vulnerabilities found`

The second run checks the version ranges, not one fixed set. The audit was done when these checks were run, and new
advisories can appear later, so repeat it before any real deployment.

## 5. Browser checks

Command: `python tests/browser/run_browser_checks.py --chrome /usr/bin/google-chrome`

The runner makes a synthetic demo feed, imports it as `SYNTHETIC_DEMO` into a temporary database, starts its own server on
a free port with a random admin key, runs the checks, and stops the server.

Result: `36 passed, 0 failed`

- Deliberate 401 responses from the wrong-key check: 4. These are expected.
- Map-tile requests that failed: 66. The build sandbox's proxy refuses the OpenStreetMap tile hosts, so the map shows no
  tiles in these runs. The map code is still checked.
- Other browser problems: 0.

The checks, in the order they ran:

1. year banner says no officially verified timetable exists for 2027
2. year banner says the unverified feed covers all of 2027
3. official route list is empty and explains why
4. unverified list shows both demo routes
5. DEMO-1 timetable on Friday 1 January 2027 lists 66 trips
6. route map draws the planned path and stops
7. saving a route confirms on screen
8. stops list shows the six demo stops
9. stops map is created
10. stop search narrows to Demo Junction
11. direct journeys are listed for a Monday
12. first scenario is saved with an estimate and the estimate label
13. scenario list labels the item as an estimated scenario
14. second scenario is saved
15. comparison lists distance, journey time and departures
16. planning-year table has one row per planning year
17. sources page shows the demo source as SYNTHETIC_DEMO and not verified
18. a wrong admin key is refused
19. verify is disabled for a non-OFFICIAL source
20. the import is listed as completed
21. the audit log shows recorded actions
22. a SQLite backup file was written
23. manifest is served with a JSON or manifest content type
24. service worker is registered
25. phone shows a menu button
26. menu starts closed on a phone
27. tapping the menu button opens navigation
28. choosing a page closes the menu
29. phone page has no sideways scrolling: routes
30. phone page has no sideways scrolling: stops
31. phone page has no sideways scrolling: journey
32. phone page has no sideways scrolling: scenarios
33. phone page has no sideways scrolling: compare
34. phone page has no sideways scrolling: sources
35. phone page has no sideways scrolling: admin
36. phone route detail fits the screen width

The "phone" checks use Playwright's Pixel 7 device profile in headless Chrome. They are not run on a real phone.

Check 17 was corrected during this work. An earlier draft looked for the words "Synthetic demo", which the dashboard never shows. It now looks for the text the page does show: `kind: SYNTHETIC_DEMO` and "Not verified by an administrator". The product was not changed.

## 6. Mutation checks

Command: `python tests/mutation/mutation_check.py`

Each broken rule is applied to a temporary copy of the project, and the test suite runs there. A broken copy passes only if
at least one test fails. The unmodified control must pass every test. The project itself is not changed.

```
== control_unmodified: pytest exit 0; 159 passed, 1 warning in 17.17s; verdict: CONTROL OK
== 01_search_without_like_escaping: pytest exit 1; 5 failed, 154 passed, 1 warning in 18.25s; verdict: CAUGHT
   mutated: backend/app/services/schedule.py: 'escaped = text.replace("\\\\", "\\\\\\\\").replace("%", "\\\\%").replace("_", "\\\\_")' -> 'escaped = text'
   FAILED tests/test_search.py::test_pattern_helper_escapes_the_three_special_characters
   FAILED tests/test_search.py::test_percent_sign_matches_only_names_that_contain_one
   FAILED tests/test_search.py::test_underscore_matches_only_a_real_underscore
   FAILED tests/test_search.py::test_backslash_matches_only_a_real_backslash - A...
   FAILED tests/test_search.py::test_percent_signs_do_not_match_every_stop - Ass...
== 02_legacy_database_not_stamped: pytest exit 1; 1 failed, 158 passed, 1 warning in 17.59s; verdict: CAUGHT
   mutated: backend/app/schema_migrations.py: 'command.stamp(cfg, BASELINE_REVISION)' -> 'pass'
   FAILED tests/test_migrations.py::test_database_built_before_migrations_is_stamped_and_keeps_its_rows
== 03_any_source_can_be_verified: pytest exit 1; 1 failed, 158 passed, 1 warning in 17.53s; verdict: CAUGHT
   mutated: backend/app/services/verification.py: 'if verified and source.kind != KIND_OFFICIAL:' -> 'if False:'
   FAILED tests/test_api.py::test_only_official_sources_can_be_verified_and_verification_reclassifies
== 04_admin_fails_open_without_key: pytest exit 1; 1 failed, 158 passed, 1 warning in 18.57s; verdict: CAUGHT
   mutated: backend/app/security.py: 'if not expected:' -> 'if False:'
   FAILED tests/test_api.py::test_admin_routes_are_disabled_when_no_key_is_configured
== 05_device_keys_stored_raw: pytest exit 1; 1 failed, 158 passed, 1 warning in 18.04s; verdict: CAUGHT
   mutated: backend/app/security.py: 'return hashlib.sha256(client_key.encode("utf-8")).hexdigest()' -> 'return client_key'
   FAILED tests/test_security.py::test_device_keys_are_stored_only_as_sha256 - A...

result: 5 of 5 broken rules caught; control run passed: True
```

The rules covered are: search escaping of `%`, `_` and `\`; stamping of a legacy database at the baseline revision;
the rule that only `OFFICIAL` sources can be verified; the refusal of admin access when no key is set; and storing device
keys only as SHA-256 hashes.

## 7. Restore drill

The drill ran on a fresh copy of the source tree, with the default paths (`data/planner.db` and `data/backups/`). It
followed the restore steps in `docs/INSTALL_WINDOWS.md`, using Linux commands.

| Step | Command | Result |
|---|---|---|
| Flags | `--help` for `import_gtfs.py`, `backup_database.py` and `make_synthetic_gtfs.py` | Exit 0 each. The documented options are present. |
| Create | `scripts/migrate_database.py` | `planner.db` created at revision 0001, up to date. |
| Check, empty | `scripts/check_database.py` | `ok: true`, integrity `ok`, no problems. |
| Demo feed | `scripts/make_synthetic_gtfs.py --out <folder>/demo_feed.zip` | Written. Dates 2026-06-01 to 2027-12-31. Labelled "SYNTHETIC_DEMO data, not BMTC timetables." |
| Import | `scripts/import_gtfs.py --file ... --new-source "Demo publisher (synthetic)" --kind SYNTHETIC_DEMO` | Exit 0. `COMPLETED`, classification `UNVERIFIED_FEED`. 2 routes, 6 stops, 192 trips, 960 stop times, 20 shape points. |
| Refused verify, new source | `--new-source ... --verify` | Exit 1: "verify an existing source with --source-id, after it has been created and imported". No source is created. |
| Refused verify, existing source | `--source-id 1 --verify` | Exit 3: "only sources of kind OFFICIAL can be verified". The database is unchanged, apart from the check timestamp. |
| Rejected feed | ZIP with only `agency.txt` | Exit 2. Status `REJECTED`. Four errors listed (missing routes, stops, trips and stop_times). The rejected record is kept. |
| Missing file | `--file <missing path>` | Exit 1: "file not found". |
| Verified backup | `scripts/backup_database.py` | `planner_backup_20261115_103952.db`, 307,200 bytes, integrity `ok`, revision 0001. |
| Damage | Overwrite the first 8 KiB of `data/planner.db` with random bytes | `check_database.py` reports "The database could not be opened: file is not a database" and exits 1. |
| Restore | Delete `planner.db-wal` and `planner.db-shm`, then copy the newest backup over `planner.db` | `check_database.py` reports `ok: true`. The row counts match the report from before the damage. The only difference is the `checked_at` time. |
| Serve | Start `uvicorn` on 127.0.0.1 and call the API | `/api/health` returns HTTP 200 with `"status":"ok"`. `/api/data-sources` lists the demo source as `SYNTHETIC_DEMO`, not verified. |

Note on the rejected feed: a rejected import is recorded, but no routes, stops or trips are stored from it.

## 8. Import command exit codes

`scripts/import_gtfs.py` exits with the codes documented in `docs/INSTALL_WINDOWS.md`:

| Code | Meaning | Observed in |
|---|---|---|
| 0 | Success | Section 7, import of the demo feed |
| 1 | Usage or file error | Section 7, refused `--new-source --verify`; missing file |
| 2 | Feed rejected | Section 7, ZIP missing required files |
| 3 | Verification refused | Section 7, `--source-id 1 --verify` on a `SYNTHETIC_DEMO` source |

## 9. Android starter (static checks only)

Command: `python android/check_starter.py`. Output:

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

No APK was built. The Flutter SDK, the pub packages, the Android SDK and the Gradle and Maven dependencies all come from
hosts that could not be reached from the build sandbox: `storage.googleapis.com`, `pub.dev`, `dl.google.com`,
`maven.google.com`, `services.gradle.org` and `repo.maven.apache.org`. Without them a Flutter build cannot run, so the APK
step was skipped.

## 10. Windows launchers (static checks only)

Each `.bat` file in `scripts/` was checked for CRLF line endings, for ASCII-only bytes, and for the scripts and folders it
refers to:

| File | CRLF | ASCII | Referenced files present |
|---|---|---|---|
| `backup_windows.bat` | yes | yes | yes |
| `run_lan_windows.bat` | yes | yes | yes |
| `run_tests_windows.bat` | yes | yes | yes |
| `run_windows.bat` | yes | yes | yes |
| `setup_windows.bat` | yes | yes | yes |

These files have not been run on Windows.

## 11. Not verified

- Windows: no launcher was run, and the Windows install steps were not followed on a Windows machine.
- Python 3.11 and 3.12: all runs used Python 3.13.18.
- Real phones and tablets: the phone checks use headless Chrome with Playwright's Pixel 7 profile only.
- Android and iOS apps: the Flutter starter was not compiled, and no APK or IPA exists.
- PostgreSQL: only SQLite was used.
- Official data: none is loaded. The 2027 to 2030 official view correctly shows that no officially verified timetable exists.
- Restore on Windows: the drill used Linux commands. The Windows steps are the same commands, but they have not been run.
- Map tiles: the OpenStreetMap tile hosts were refused by the sandbox proxy, so the map imagery was not seen in these runs.

## 12. The packaged copy

The package has a `MANIFEST.sha256` file, which lists a SHA-256 hash for every file in it. On Linux, run
`sha256sum -c MANIFEST.sha256` inside the extracted folder to check that each file matches. The packaged copy was checked
again after it was made, by extracting it into a new folder and repeating the tests there. The result of that check is
reported with the package, not repeated here.
