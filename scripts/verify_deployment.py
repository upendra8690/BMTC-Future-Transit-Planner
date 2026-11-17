"""Check that a public address really serves Bengaluru Transit Planner 4.0, and that the 3.0 address still serves 3.0.

    python scripts/verify_deployment.py https://bengaluru-transit-planner-v4.onrender.com \
        --v3 https://bmtc-future-transit-planner-3-0.onrender.com

Only GET requests are sent, so nothing on either service changes. A free Render service that is asleep can take up to
a minute to answer the first request. The exit code is 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 120
AGENT = "bengaluru-transit-planner-deployment-check"


def fetch(url: str) -> tuple[int, dict[str, str], bytes]:
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"only http and https addresses are checked: {url}")
    headers = {"User-Agent": AGENT, "Accept": "application/json, text/html"}
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 (scheme checked above)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 (scheme checked above)
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()


def as_json(body: bytes) -> dict:
    try:
        return json.loads(body)
    except ValueError:
        return {}


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, name: str, ok: bool, detail: object = "") -> None:
        self.failed += 0 if ok else 1
        print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail != "" else ""))


def check_v4(base: str, report: Report) -> None:
    report.check("4.0 address uses HTTPS", base.startswith("https://"), base)
    started = time.monotonic()
    status, _, body = fetch(base + "/api/health")
    report.check("4.0 health check returns 200", status == 200 and as_json(body).get("status") == "ok",
                 f"HTTP {status} after {time.monotonic() - started:.0f} s")
    status, _, body = fetch(base + "/api/features")
    version = str(as_json(body).get("version", ""))
    report.check("4.0 reports a 4.x version", status == 200 and version.startswith("4."), version or f"HTTP {status}")
    status, headers, body = fetch(base + "/")
    page = body.decode("utf-8", "replace")
    report.check("4.0 page is Bengaluru Transit Planner", status == 200 and
                 "<title>Bengaluru Transit Planner</title>" in page, f"HTTP {status}")
    report.check("4.0 sends a content security policy", "content-security-policy" in headers)
    report.check("4.0 sends HSTS", "strict-transport-security" in headers)
    status, _, body = fetch(base + "/api/data-status")
    data = as_json(body)
    report.check("4.0 says it serves demonstration data only", status == 200 and data.get("demo_only") is True,
                 f"{len(data.get('feeds', []))} feeds")
    status, _, body = fetch(base + "/api/upcoming")
    projects = as_json(body).get("projects", [])
    report.check("4.0 upcoming transport loads, never used by the planner",
                 status == 200 and bool(projects) and all(p.get("in_planner") is False for p in projects),
                 f"{len(projects)} entries")
    query = urllib.parse.urlencode({"classification": "UNVERIFIED_FEED"})
    status, _, body = fetch(f"{base}/api/routes?{query}")
    routes = as_json(body).get("results", [])
    report.check("4.0 demo routes load", status == 200 and bool(routes), f"{len(routes)} routes")
    query = urllib.parse.urlencode({"origin": "Demo Lake View", "destination": "Demo Metro Hub",
                                    "classification": "UNVERIFIED_FEED"})
    status, _, body = fetch(f"{base}/api/plan?{query}")
    plan = as_json(body)
    report.check("4.0 bus + Metro demo journey is planned and marked not live",
                 status == 200 and bool(plan.get("options")) and plan.get("realtime") is False,
                 f"{len(plan.get('options', []))} options")
    query = urllib.parse.urlencode({"origin": "Demo Lake View", "destination": "Demo Metro Hub"})
    status, _, body = fetch(f"{base}/api/plan?{query}")
    report.check("4.0 default (officially verified) journey shows no data", status == 200 and
                 not as_json(body).get("options"), as_json(body).get("message", f"HTTP {status}"))


def check_v3(base: str, report: Report) -> None:
    status, _, body = fetch(base + "/api/health")
    report.check("3.0 health check still returns 200", status == 200 and as_json(body).get("status") == "ok",
                 f"HTTP {status}")
    status, _, _ = fetch(base + "/api/features")
    report.check("3.0 is still 3.0 (it has no /api/features, which 4.0 added)", status == 404, f"HTTP {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("v4_url", help="the public address of the 4.0 service")
    parser.add_argument("--v3", help="the public address of the 3.0 service, to confirm it is unchanged")
    args = parser.parse_args()
    report = Report()
    check_v4(args.v4_url.rstrip("/"), report)
    if args.v3:
        check_v3(args.v3.rstrip("/"), report)
    print("ALL CHECKS PASSED" if report.failed == 0 else f"{report.failed} CHECK(S) FAILED")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
