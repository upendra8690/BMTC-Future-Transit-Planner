"""Break one planner or schedule rule at a time in a temporary copy, and check that the planner tests notice.

Run from the project folder, with the test requirements installed:
    python tests/mutation/planner_mutation_check.py

The project itself is not changed. Each broken copy is made in a temporary folder that is deleted afterwards. The
command exits with 1 if the unmodified copy fails, or if any broken rule is not caught by a failing test.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - runs pytest with a fixed argument list and no shell
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_FILES = ["tests/test_planner.py", "tests/test_fares.py", "tests/test_plan_api.py"]
IGNORED = shutil.ignore_patterns(
    "__pycache__", ".pytest_cache", ".ruff_cache", ".hypothesis", "*.pyc", "data", "backups", ".env", ".git",
    "node_modules",
)

MUTATIONS = [
    ("min change time ignored", "services/planner.py",
     "_search(net, origins, start, horizon_end, max_changes + 1, plan.min_transfer_seconds)",
     "_search(net, origins, start, horizon_end, max_changes + 1, 0)"),
    ("overtaking trips not split into lanes", "services/planner.py",
     "                    if _no_overtaking(lane[-1], item):", "                    if True:"),
    ("trips from the previous service day ignored", "services/planner.py",
     "LOOKBACK_DAYS = 2", "LOOKBACK_DAYS = 0"),
    ("walks between stops ignored", "services/planner.py",
     "                        if metres <= plan.max_walk_m:", "                        if False:"),
    ("route-less fares ignored", "services/planner.py",
     "*fares.get((import_id, None), [])", ""),
    ("zone-limited fares treated as route fares", "services/planner.py",
     "            FareRule.origin_id.is_(None),\n", ""),
    ("fares added up across changes", "services/planner.py",
     "    if len(ride_fares) > 1:\n        return {\"code\": \"CHANGES_NOT_PRICED\"",
     "    if False:\n        return {\"code\": \"CHANGES_NOT_PRICED\""),
    ("max_changes ignored by the search", "services/planner.py",
     "max_changes + 1, plan.min_transfer_seconds)", "MAX_CHANGES_LIMIT + 1, plan.min_transfer_seconds)"),
    ("classification filter dropped", "services/schedule.py",
     "    stmt = select(GtfsImport.id).where(\n        GtfsImport.classification == classification,",
     "    stmt = select(GtfsImport.id).where(\n        GtfsImport.id > 0,"),
    ("cached network ignores import identity", "services/planner.py",
     "key = (str(session.get_bind().url), classification, first_day, last_day, fingerprints, plan)",
     "key = (str(session.get_bind().url), classification, first_day, last_day, plan)"),
]


def run_tests(work: Path) -> tuple[int, str]:
    result = subprocess.run(  # nosec B603 - fixed argument list, this interpreter, no shell
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=", "-q", *TEST_FILES],
        cwd=work, capture_output=True, text=True, timeout=900, check=False,
    )
    summary = [line for line in result.stdout.splitlines() if " passed" in line or " failed" in line]
    return result.returncode, summary[-1] if summary else result.stdout[-300:]


def run_one(rel: str | None, old: str | None, new: str | None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="planner_mutant_") as tmp:
        work = Path(tmp) / "copy"
        shutil.copytree(ROOT, work, ignore=IGNORED)
        if rel is not None and old is not None and new is not None:
            target = work / "backend" / "app" / rel
            text = target.read_text(encoding="utf-8")
            count = text.count(old)
            if count != 1:
                return -1, f"pattern found {count} times in {rel}; mutation not applied"
            target.write_text(text.replace(old, new), encoding="utf-8")
        return run_tests(work)


def main() -> int:
    code, summary = run_one(None, None, None)
    if code != 0:
        print(f"CONTROL FAILED: the unmodified copy does not pass ({summary})")
        return 1
    print(f"control, unmodified: {summary}")
    missed = []
    for name, rel, old, new in MUTATIONS:
        code, summary = run_one(rel, old, new)
        if code == -1:
            print(f"SKIPPED  {name}: {summary}")
            missed.append(name)
        elif code == 0:
            print(f"MISSED   {name}: all tests still passed ({summary})")
            missed.append(name)
        else:
            print(f"CAUGHT   {name}: {summary}")
    print(f"\n{len(MUTATIONS) - len(missed)} of {len(MUTATIONS)} mutations caught.")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
