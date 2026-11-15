#!/usr/bin/env bash
# Restore drill: shows that a verified backup brings the planner back, using a copy of this project.
#
# The drill copies the code into a new temporary folder and works only there, so the project's own data/ and
# .env are never read or changed. Each step below records a check with the result it expects:
#   1. the documented command-line tools answer --help
#   2. the database is created, migrated to the head revision and passes the check
#   3. a synthetic demo feed is imported; the importer refuses to verify it and rejects a feed that is not GTFS
#   4. a verified backup is written, the database is damaged, and the backup is restored as documented
#   5. the restored database passes the check and matches the report from before the damage (checked_at aside)
#   6. the server starts on the restored database and its health, data sources and unverified routes read back
#
# Usage (tested on Linux only; macOS has not been tested. Needs bash, curl and a Python with the project's
# requirements installed):
#   scripts/restore_drill.sh                    results to the terminal
#   scripts/restore_drill.sh drill-log.txt      results to the terminal and to that file
#   PYTHON=/path/to/venv/bin/python scripts/restore_drill.sh
#   KEEP_DRILL=1 scripts/restore_drill.sh       keep the temporary folder for inspection
#
# Exit codes: 0 every check gave the expected result, 1 at least one did not, 2 the drill could not set itself up.
set -uo pipefail

CHECKS=0
FAILED=0
SERVER_PID=
WORK=

# expect_exit WANTED GOT WHAT: passes when the exit code is the one wanted.
expect_exit() {
  CHECKS=$((CHECKS + 1))
  if [ "$2" -eq "$1" ]; then
    printf '[check %s passed: exit %s] %s\n' "$CHECKS" "$2" "$3"
  else
    FAILED=$((FAILED + 1))
    printf '[check %s FAILED: exit %s, wanted %s] %s\n' "$CHECKS" "$2" "$1" "$3"
  fi
}

# run COMMAND...: prints the command, then runs it.
run() {
  printf '\n$ %s\n' "$*"
  "$@"
}

# run_to FILE COMMAND...: prints the command, then runs it with its output written to FILE.
run_to() {
  local file=$1
  shift
  printf '\n$ %s > %s\n' "$*" "$file"
  "$@" > "$file"
}

# ok_if WHAT COMMAND...: passes when the command exits 0.
ok_if() {
  local what=$1
  shift
  "$@"
  expect_exit 0 "$?" "$what"
}

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  if [ "${KEEP_DRILL:-0}" = 1 ]; then
    printf '\nkept the temporary folder: %s\n' "$WORK"
  elif [ -n "$WORK" ]; then
    rm -rf "$WORK"
  fi
}

main() {
  local root py app db backups check feeds newest port http get_path

  root=$(cd "$(dirname "$0")/.." && pwd) || return 2
  py=${PYTHON:-python3}
  command -v "$py" >/dev/null 2>&1 || { echo "error: Python was not found: $py (set PYTHON)"; return 2; }
  # A relative path such as .venv/bin/python would stop working after the drill changes folder, so make it absolute.
  case $py in
    */*) py=$(cd "$(dirname "$py")" && pwd)/$(basename "$py") || return 2 ;;
  esac
  command -v curl >/dev/null 2>&1 || { echo "error: curl is needed for the server read-back"; return 2; }
  WORK=$(mktemp -d "${TMPDIR:-/tmp}/bmtc-restore-drill.XXXXXX") || return 2
  trap cleanup EXIT

  app=$WORK/app
  db=$app/data/planner.db
  backups=$app/data/backups
  check=$WORK/drill_check.py
  feeds=$WORK/feeds
  mkdir -p "$app/data" "$feeds" || return 2
  tar -C "$root" --exclude=__pycache__ --exclude='*.pyc' -cf - backend dashboard migrations scripts alembic.ini \
    | tar -C "$app" -xf - || { echo "error: the project could not be copied"; return 2; }
  cd "$app" || return 2

  # Every database and backup path below is inside the temporary copy.
  unset ADMIN_API_KEY
  export DATABASE_URL="sqlite:///$db" BACKUP_DIR="$backups"

  cat > "$check" <<'PY'
"""Checks used by scripts/restore_drill.sh. Each command exits 0 when its check passes."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

DEMO_NAME = "Demo feed (synthetic)"


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    command, args = argv[0], argv[1:]
    if command == "bad-feed":  # a ZIP with one file that is not GTFS: the importer must reject it
        with zipfile.ZipFile(args[0], "w") as archive:
            archive.writestr("readme.txt", "This is not a GTFS feed.\n")
        return 0
    if command == "scalar":  # scalar DB SQL EXPECTED: the first value the query returns must equal EXPECTED
        with contextlib.closing(sqlite3.connect(args[0])) as conn:
            value = conn.execute(args[1]).fetchone()[0]
        return 0 if str(value) == args[2] else 1
    if command == "same-report":  # checked_at is the only field that depends on when the check ran
        first, second = load(args[0]), load(args[1])
        for report in (first, second):
            report.pop("checked_at", None)
        return 0 if first == second else 1
    if command == "health":
        return 0 if load(args[0]).get("status") == "ok" else 1
    if command == "demo-source":
        sources = load(args[0]).get("sources", [])
        found = [s for s in sources if s.get("kind") == "SYNTHETIC_DEMO" and s.get("name") == DEMO_NAME]
        return 0 if found else 1
    if command == "routes-found":
        return 0 if load(args[0]).get("results") else 1
    print(f"unknown check: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
PY

  printf 'restore drill started: %s (UTC)\n' "$(date -u '+%Y-%m-%d %H:%M:%S')"
  printf 'project read from: %s\n' "$root"
  printf 'drill works in: %s\n' "$app"
  printf 'python: %s (%s)\n' "$py" "$("$py" -V 2>&1)"

  printf '\n=== 1. the documented command-line tools answer --help ===\n'
  for tool in import_gtfs backup_database make_synthetic_gtfs; do
    run "$py" "scripts/$tool.py" --help
    expect_exit 0 "$?" "scripts/$tool.py --help"
  done

  printf '\n=== 2. create the database and migrate it to the head revision ===\n'
  run "$py" scripts/migrate_database.py
  expect_exit 0 "$?" "migrate_database.py reaches the head revision"
  run_to "$WORK/check_new.json" "$py" scripts/check_database.py
  expect_exit 0 "$?" "the new, migrated database passes the check"

  printf '\n=== 3. import a synthetic demo feed (invented data, never verified) ===\n'
  run "$py" scripts/make_synthetic_gtfs.py --out "$feeds/demo_feed.zip" || { echo "error: no demo feed"; return 2; }
  run "$py" scripts/import_gtfs.py --file "$feeds/demo_feed.zip" \
    --new-source "Demo publisher (synthetic)" --kind SYNTHETIC_DEMO --name "Demo feed (synthetic)"
  expect_exit 0 "$?" "the demo feed imports as SYNTHETIC_DEMO"
  ok_if "exactly one data source exists after the import" \
    "$py" "$check" scalar "$db" "SELECT COUNT(*) FROM data_sources" 1

  printf '\n=== 4. refusals and rejections happen as documented ===\n'
  run "$py" scripts/import_gtfs.py --file "$feeds/demo_feed.zip" \
    --new-source "Refusal probe" --kind SYNTHETIC_DEMO --verify
  expect_exit 1 "$?" "a new source cannot be created and verified in one command (usage error, exit 1)"
  run "$py" scripts/import_gtfs.py --source-id 1 --verify --note "Refusal probe"
  expect_exit 3 "$?" "a synthetic source cannot be verified (exit 3)"
  ok_if "the refusal created no data source" "$py" "$check" scalar "$db" "SELECT COUNT(*) FROM data_sources" 1
  ok_if "the refusal left the synthetic source unverified" \
    "$py" "$check" scalar "$db" "SELECT COUNT(*) FROM data_sources WHERE verified = 1" 0
  ok_if "the refusal wrote no verification record" \
    "$py" "$check" scalar "$db" "SELECT COUNT(*) FROM verification_records" 0
  "$py" "$check" bad-feed "$feeds/bad_feed.zip" || { echo "error: no bad feed"; return 2; }
  run "$py" scripts/import_gtfs.py --file "$feeds/bad_feed.zip" --source-id 1
  expect_exit 2 "$?" "a feed without the GTFS files is rejected (exit 2)"
  run "$py" scripts/import_gtfs.py --file "$feeds/does_not_exist.zip" --source-id 1
  expect_exit 1 "$?" "a missing file is an error (exit 1)"

  printf '\n=== 5. verified backup, damage, restore ===\n'
  run "$py" scripts/backup_database.py
  expect_exit 0 "$?" "the backup is written and verified"
  newest=$(ls -t "$backups"/planner_backup_*.db 2>/dev/null | head -n 1)
  ok_if "a backup file exists in the backup folder" test -f "$newest"
  printf 'newest backup: %s\n' "${newest##*/}"
  run_to "$WORK/check_before.json" "$py" scripts/check_database.py
  expect_exit 0 "$?" "the database passes the check before the damage"
  printf '\n$ overwrite the first 8 KiB of the database with random bytes\n'
  dd if=/dev/urandom of="$db" bs=4096 count=2 conv=notrunc 2>/dev/null
  expect_exit 0 "$?" "the damage is written"
  run_to "$WORK/check_damaged.json" "$py" scripts/check_database.py
  expect_exit 1 "$?" "the damaged database fails the check (exit 1)"
  printf '\n$ remove the -wal and -shm files, then copy the newest backup over the database\n'
  rm -f "$db-wal" "$db-shm"
  cp "$newest" "$db"
  expect_exit 0 "$?" "the backup is copied over the database"
  run_to "$WORK/check_restored.json" "$py" scripts/check_database.py
  expect_exit 0 "$?" "the restored database passes the check"
  ok_if "the restored report matches the report from before the damage (checked_at aside)" \
    "$py" "$check" same-report "$WORK/check_before.json" "$WORK/check_restored.json"

  printf '\n=== 6. the server starts on the restored database and reads it back ===\n'
  port=$("$py" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
  printf '\n$ uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port %s\n' "$port"
  "$py" -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port "$port" \
    > "$WORK/server.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 60); do
    curl -s --noproxy '*' -o /dev/null "http://127.0.0.1:$port/api/health" && break
    sleep 0.5
  done
  get_path() { # get_path PATH FILE: GET PATH from the server into FILE and print the HTTP status
    curl -s --noproxy '*' -o "$2" -w '%{http_code}' "http://127.0.0.1:$port$1"
  }
  http=$(get_path /api/health "$WORK/health.json")
  ok_if "GET /api/health answers 200" test "$http" = 200
  ok_if "the health report says the service is ok" "$py" "$check" health "$WORK/health.json"
  http=$(get_path /api/data-sources "$WORK/sources.json")
  ok_if "GET /api/data-sources answers 200" test "$http" = 200
  ok_if "the restored server lists the synthetic demo feed as SYNTHETIC_DEMO" \
    "$py" "$check" demo-source "$WORK/sources.json"
  http=$(get_path "/api/routes?classification=UNVERIFIED_FEED&limit=5" "$WORK/routes.json")
  ok_if "GET /api/routes for unverified feeds answers 200" test "$http" = 200
  ok_if "the restored server returns routes from the demo feed" "$py" "$check" routes-found "$WORK/routes.json"
  kill "$SERVER_PID" 2>/dev/null
  wait "$SERVER_PID" 2>/dev/null
  SERVER_PID=
  printf '\nserver stopped; last lines of its log:\n'
  tail -n 5 "$WORK/server.log"
  ok_if "the server log has no traceback" test "$(grep -c Traceback "$WORK/server.log")" = 0

  printf '\nchecks run: %s, failed: %s\n' "$CHECKS" "$FAILED"
  if [ "$FAILED" -eq 0 ]; then
    printf 'restore drill: PASSED\n'
    return 0
  fi
  printf 'restore drill: FAILED\n'
  return 1
}

LOG_FILE=${1:-}
if [ -n "$LOG_FILE" ]; then
  main 2>&1 | tee "$LOG_FILE"
else
  main 2>&1
fi
exit $?
