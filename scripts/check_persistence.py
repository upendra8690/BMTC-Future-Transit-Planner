"""Prove that data survives a server restart on the configured database (DATABASE_URL).

    python scripts/check_persistence.py                         # passenger data only; safe on a new production database
    python scripts/check_persistence.py --include-admin-change  # also an administrator change (test databases only)
    ACCOUNTS_ENABLED=1 python scripts/check_persistence.py --include-account   # also a passenger account (PostgreSQL)

It starts the planner on a free local port and writes data:
- a saved route, stored under a random device key;
- with --include-admin-change, a note on an upcoming-transport entry.

It then stops the server, starts a fresh server process on the same database, and checks that the data is still there.
It also checks that the community Namma Metro import was not loaded twice. At the end it erases the saved route
("Delete my data").

The administrator change is visible in that entry's public history, so use --include-admin-change only on a test
database. ADMIN_API_KEY is read from the environment and never printed. The exit code is 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess  # nosec B404 (starts this project's own server with fixed arguments)
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures = 0


def check(name: str, ok: bool, detail: object = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if not ok and detail != "" else ""))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def call(base: str, method: str, path: str, *, body: dict | None = None, headers: dict | None = None):
    # base is always the local http://127.0.0.1 address this script started.
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method, headers={  # noqa: S310
        "Content-Type": "application/json", "Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310  # nosec B310
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def start(port: int) -> subprocess.Popen:
    env = {**os.environ, "RATE_LIMIT_PER_MINUTE": "100000", "LOG_LEVEL": "WARNING"}
    process = subprocess.Popen(  # nosec B603 (fixed arguments, this interpreter)
        [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--app-dir", "backend",
         "--host", "127.0.0.1", "--port", str(port), "--no-access-log"], cwd=ROOT, env=env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(90):
        try:
            if call(base, "GET", "/api/health")[0] == 200:
                return process
        except OSError:
            pass
        time.sleep(1)
    process.terminate()
    raise SystemExit("the server did not start")


def stop(process: subprocess.Popen) -> None:
    process.terminate()
    process.wait(timeout=30)


def community_imports(base: str) -> list[int]:
    feeds = call(base, "GET", "/api/data-status")[1]["feeds"]
    return [f["import_id"] for f in feeds if f["kind"] == "COMMUNITY"]


def staff_headers(base: str, key_headers: dict[str, str], staff: dict[str, str]) -> dict[str, str]:
    """The credential for an administrator change.

    Without accounts, the shared ADMIN_API_KEY. With accounts running, the key can only assign roles, so a test
    administrator account is registered, given the role with the key, and signed in, as a real administrator would be.
    """
    if not call(base, "GET", "/api/account/status")[1].get("available"):
        return key_headers
    status, body = call(base, "POST", "/api/account/register", body=staff)
    check("a test administrator account is registered", status == 201, body)
    users = (call(base, "GET", "/api/admin/users", headers=key_headers)[1] or {}).get("users", [])
    user_id = next((u["id"] for u in users if u["email"] == staff["email"]), None)
    status, body = call(base, "PUT", f"/api/admin/users/{user_id}/role", headers=key_headers, body={"role": "admin"})
    check("the shared key gives that account the administrator role", status == 200, body)
    status, body = call(base, "POST", "/api/account/sign-in", body=staff)
    check("the administrator signs in with the account", status == 200, body)
    return {"Authorization": "Bearer " + (body or {}).get("token", "")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that data survives a server restart.")
    parser.add_argument("--include-admin-change", action="store_true", help="also check an administrator change")
    parser.add_argument("--include-account", action="store_true",
                        help="also register an account, save a journey to it, and delete it at the end")
    args = parser.parse_args()
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    device = {"X-Client-Key": secrets.token_urlsafe(24)}
    admin = {"X-Admin-Key": os.environ.get("ADMIN_API_KEY", "")}
    marker = "persistence check " + secrets.token_hex(4)
    account = {"email": f"persistence-{secrets.token_hex(4)}@example.org", "password": secrets.token_urlsafe(18)}
    staff = {"email": f"persistence-admin-{secrets.token_hex(4)}@example.org", "password": secrets.token_urlsafe(18)}

    server = start(port)
    try:
        before = community_imports(base)
        check("the community Metro timetable is loaded", len(before) == 1, before)
        query = urllib.parse.urlencode({"classification": "UNVERIFIED_FEED", "q": "Purple"})
        routes = call(base, "GET", f"/api/routes?{query}")[1]["results"]
        check("a real Metro route is found by name", bool(routes))
        status, saved = call(base, "POST", "/api/saved-routes", headers=device, body={
            "gtfs_route_id": routes[0]["gtfs_route_id"], "classification": "UNVERIFIED_FEED", "label": marker})
        check("a saved route is written", status == 201, saved)
        if args.include_account:
            status, body = call(base, "POST", "/api/account/register", body=account)
            check("an account is registered", status == 201, body)
            status, body = call(base, "POST", "/api/account/sign-in", body=account)
            bearer = {"Authorization": "Bearer " + (body or {}).get("token", "")}
            status, body = call(base, "POST", "/api/account/journeys", headers=bearer, body={
                "origin": "Indiranagar", "destination": "Jayanagar", "modes": "metro",
                "classification": "UNVERIFIED_FEED", "label": marker})
            check("a journey is saved to the account", status == 201, body)
        if args.include_admin_change:
            admin = staff_headers(base, admin, staff)
            status, body = call(base, "PATCH", "/api/admin/upcoming/metro_blue", headers=admin,
                                body={"note": marker, "reason": "Persistence check (test database)"})
            check("an administrator change is written", status == 200, body)
    finally:
        stop(server)

    server = start(port)
    try:
        after = community_imports(base)
        check("after a restart, the community import is the same one (not loaded again)", after == before,
              (before, after))
        mine = call(base, "GET", "/api/saved-routes", headers=device)[1]["saved"]
        check("after a restart, the saved route is still there", [r["label"] for r in mine] == [marker], mine)
        if args.include_admin_change:
            blue = {p["id"]: p for p in call(base, "GET", "/api/upcoming")[1]["projects"]}["metro_blue"]
            check("after a restart, the administrator change and its history are still there",
                  blue["note"] == marker and blue["history"][0]["reason"].startswith("Persistence check"),
                  blue["note"])
        if args.include_account:
            status, body = call(base, "POST", "/api/account/sign-in", body=account)
            check("after a restart, the account can sign in", status == 200, body)
            bearer = {"Authorization": "Bearer " + (body or {}).get("token", "")}
            saved = call(base, "GET", "/api/account/journeys", headers=bearer)[1] or {}
            check("after a restart, the account's saved journey is still there",
                  [j["label"] for j in saved.get("journeys", [])] == [marker], saved)
            status, _ = call(base, "POST", "/api/account/delete", headers=bearer,
                             body={"password": account["password"]})
            check("the test account is deleted again", status == 200)
        if args.include_admin_change and call(base, "GET", "/api/account/status")[1].get("available"):
            status, body = call(base, "POST", "/api/account/sign-in", body=staff)
            check("after a restart, the administrator account can sign in", status == 200, body)
            bearer = {"Authorization": "Bearer " + (body or {}).get("token", "")}
            status, _ = call(base, "POST", "/api/account/delete", headers=bearer, body={"password": staff["password"]})
            check("the test administrator account is deleted again", status == 200)
        status, _ = call(base, "DELETE", "/api/my-data", headers=device)
        check("the test data is erased again", status == 200)
    finally:
        stop(server)

    print("ALL CHECKS PASSED" if failures == 0 else f"{failures} CHECK(S) FAILED")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
