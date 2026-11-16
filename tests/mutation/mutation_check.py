"""Break one safety rule at a time in a scratch copy, and check that the test suite notices.

Run from the project folder, with the test requirements installed:

    python tests/mutation/mutation_check.py

Each broken copy is made in a temporary folder that is deleted afterwards. The project itself is not changed.
The command exits with 1 if the unmodified control run fails, or if any broken rule is not caught by a failing test.
"""

import re
import shutil
import subprocess  # nosec B404 - runs pytest with a fixed argument list and no shell
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MUTANTS = [
    ("control_unmodified", None, None, None),
    ("01_search_without_like_escaping", "backend/app/services/schedule.py",
     r'escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")', "escaped = text"),
    ("02_legacy_database_not_stamped", "backend/app/schema_migrations.py",
     "command.stamp(cfg, BASELINE_REVISION)", "pass"),
    ("03_any_source_can_be_verified", "backend/app/services/verification.py",
     "if verified and source.kind != KIND_OFFICIAL:", "if False:"),
    ("04_admin_fails_open_without_key", "backend/app/security.py",
     "if not expected:", "if False:"),
    ("05_device_keys_stored_raw", "backend/app/security.py",
     'return hashlib.sha256(client_key.encode("utf-8")).hexdigest()', "return client_key"),
    ("06_inline_script_added_to_page", "dashboard/index.html",
     '<script src="/app.js" defer></script>',
     '<script src="/app.js" defer></script>\n  <script>window.leak = 1;</script>'),
    ("07_english_message_removed", "dashboard/i18n.js",
     '    "scn.err_pair": "Give both latitude and longitude, or leave both empty.",\n', ""),
    ("08_worker_caches_api_answers", "dashboard/sw.js",
     "if (SAVED_API.test(url.pathname)) event.respondWith(savedAnswer(event));",
     "event.respondWith(savedAnswer(event));"),
    ("09_admin_key_written_to_storage", "dashboard/app.js",
     'storage.set(PREFIX + "lang", code);', 'storage.set(PREFIX + "adminKey", state.adminKey || "");'),
    ("10_eval_added_to_dashboard", "dashboard/app.js",
     'var PREFIX = "bmtc.";', 'var PREFIX = "bmtc.";\n  eval("0");'),
]

IGNORED = shutil.ignore_patterns(
    "data", "backups", "dist", ".venv", ".env", "__pycache__", ".pytest_cache", ".ruff_cache",
    "*.db", "*.db-wal", "*.db-shm",
)


def run_one(work: Path, name: str, rel: str | None, old: str | None, new: str | None):
    dest = work / name
    shutil.copytree(ROOT, dest, ignore=IGNORED)
    if rel is not None:
        target = dest / rel
        text = target.read_text(encoding="utf-8")
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"{name}: expected one match in {rel}, found {count}")
        target.write_text(text.replace(old, new), encoding="utf-8")
    proc = subprocess.run(  # nosec B603 - fixed argument list, run with this same interpreter
        [sys.executable, "-m", "pytest", "-rf", "-p", "no:cacheprovider"],
        cwd=dest, capture_output=True, text=True, timeout=900,
    )
    output = proc.stdout + proc.stderr
    failed = [line for line in output.splitlines() if line.startswith("FAILED ")]
    summary = [line for line in output.splitlines() if re.search(r"\d+ (passed|failed)", line)]
    return proc.returncode, summary[-1] if summary else "(no summary line)", failed


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="bmtc_mutants_"))
    control_ok = False
    caught = 0
    try:
        for name, rel, old, new in MUTANTS:
            code, summary, failed = run_one(work, name, rel, old, new)
            if rel is None:
                control_ok = code == 0
                verdict = "CONTROL OK" if control_ok else "CONTROL FAILED"
            else:
                verdict = "CAUGHT" if code != 0 else "NOT CAUGHT"
                caught += verdict == "CAUGHT"
            print(f"== {name}: pytest exit {code}; {summary}; verdict: {verdict}")
            if rel is not None:
                print(f"   mutated: {rel}: {old!r} -> {new!r}")
            for item in failed:
                print(f"   {item}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    total = len(MUTANTS) - 1
    print(f"\nresult: {caught} of {total} broken rules caught; control run passed: {control_ok}")
    print("scratch copies removed")
    return 0 if control_ok and caught == total else 1


if __name__ == "__main__":
    sys.exit(main())
