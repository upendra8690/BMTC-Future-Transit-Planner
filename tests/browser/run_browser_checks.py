#!/usr/bin/env python3
"""Run the browser checks from start to finish, in a temporary folder whose path is printed at the end.

  python tests/browser/run_browser_checks.py
  python tests/browser/run_browser_checks.py --chrome "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

The runner does this:

1. builds the synthetic demo feed and imports it as SYNTHETIC_DEMO data, and builds a second feed for dates that do
   not overlap the demo (the administration check uploads it through the browser, then removes it)
2. starts the planner on a free local port, with its own temporary database, backup folder and random admin key
3. runs tests/browser/ui_check.py against it
4. stops the server

Your project data folder and .env file are not used. The test server raises the per-minute request limit, because
the checks make many requests in a short time; the rate limit itself is covered by the automated tests.

Install the browser requirements first: python -m pip install -r requirements-browser.txt
Then either run python -m playwright install chromium, or pass --chrome with an installed Chrome or Chromium.

Exit codes: 0 all checks passed, 1 a check failed, 2 setup problem (for example Playwright is missing).
"""

from __future__ import annotations

import argparse
import http.client
import os
import secrets
import socket
import subprocess  # nosec B404 - the runner starts only fixed local commands, always passed as lists
import sys
import tempfile
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
EXIT_SETUP = 2


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_step(command: list[str], env: dict[str, str], label: str) -> None:
    print(f"-> {label}", flush=True)
    result = subprocess.run(command, cwd=PROJECT_DIR, env=env, capture_output=True, text=True)  # nosec B603
    if result.returncode != 0:
        print(result.stdout, file=sys.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"setup step failed: {label} (exit code {result.returncode})")


def wait_for_health(port: int, timeout: float = 60.0) -> None:
    """Poll the test server's health check until it answers 200, or give up after the timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            connection.request("GET", "/api/health")
            if connection.getresponse().status == 200:
                return
        except (OSError, http.client.HTTPException):
            time.sleep(0.3)
        finally:
            connection.close()
    raise SystemExit(f"the test server did not answer http://127.0.0.1:{port}/api/health in {timeout:.0f} seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the dashboard browser checks end to end.")
    parser.add_argument("--chrome", default="", help="Chrome or Chromium executable (default: Playwright's Chromium)")
    args = parser.parse_args(argv)

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("Playwright is not installed. Run: python -m pip install -r requirements-browser.txt", file=sys.stderr)
        return EXIT_SETUP

    work = Path(tempfile.mkdtemp(prefix="bmtc_browser_"))
    backups = work / "backups"
    shots = work / "screenshots"
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    admin_key = secrets.token_urlsafe(32)
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(work / 'ui.db').as_posix()}",
        "ADMIN_API_KEY": admin_key,
        "BACKUP_DIR": str(backups),
        "RATE_LIMIT_PER_MINUTE": "100000",
        "LOG_LEVEL": "WARNING",
    }
    python = sys.executable

    demo_feed = work / "demo_feed.zip"
    run_step([python, "scripts/make_synthetic_gtfs.py", "--out", str(demo_feed)], env, "build the synthetic demo feed")
    run_step(
        [python, "scripts/import_gtfs.py", "--file", str(demo_feed),
         "--new-source", "Demo publisher (synthetic)", "--kind", "SYNTHETIC_DEMO"],
        env, "import the demo feed as SYNTHETIC_DEMO",
    )
    upload_feed = work / "upload_feed_2028.zip"
    run_step(
        [python, "scripts/make_synthetic_gtfs.py", "--out", str(upload_feed),
         "--start", "2028-01-01", "--end", "2028-03-31"],
        env, "build a second feed for dates that do not overlap the demo",
    )

    server_log = (work / "server.log").open("w", encoding="utf-8")
    server = subprocess.Popen(  # nosec B603
        [python, "-m", "uvicorn", "app.main:create_app", "--factory", "--app-dir", "backend",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=PROJECT_DIR, env=env, stdout=server_log, stderr=subprocess.STDOUT,
    )
    code = EXIT_SETUP
    try:
        print(f"-> start the planner test server at {base}", flush=True)
        wait_for_health(port)
        check_env = {
            **os.environ,
            "BMTC_BASE_URL": base,
            "BMTC_ADMIN_KEY": admin_key,
            "BMTC_BACKUP_DIR": str(backups),
            "BMTC_UPLOAD_ZIP": str(upload_feed),
            "BMTC_OUT_DIR": str(shots),
        }
        if args.chrome:
            check_env["BMTC_CHROME"] = args.chrome
        print("-> run the browser checks", flush=True)
        code = subprocess.run(  # nosec B603
            [python, "tests/browser/ui_check.py"], cwd=PROJECT_DIR, env=check_env
        ).returncode
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        server_log.close()

    print(f"\nFiles from this run (screenshots, demo database, server log): {work}")
    return code


if __name__ == "__main__":
    sys.exit(main())
