"""Static checks for the Windows launchers in scripts/*.bat.

The launchers run on Windows only, and the build machine is Linux, so these tests check what can be checked from
the text of each file: its bytes and line endings, and the scripts and requirements files it refers to. They do not
run the launchers, so a passing test does not show that a launcher works on Windows.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = sorted((ROOT / "scripts").glob("*.bat"))
SCRIPT_REFERENCE = re.compile(r"scripts\\([A-Za-z0-9_]+\.(?:py|bat))")
REQUIREMENTS_REFERENCE = re.compile(r"requirements[A-Za-z0-9_\-]*\.txt")


def _text(path: Path) -> str:
    return path.read_text(encoding="ascii", errors="replace")


def test_the_five_launchers_are_present():
    assert {path.name for path in LAUNCHERS} == {
        "backup_windows.bat",
        "run_lan_windows.bat",
        "run_tests_windows.bat",
        "run_windows.bat",
        "setup_windows.bat",
    }


@pytest.mark.parametrize("path", LAUNCHERS, ids=lambda p: p.name)
def test_launcher_is_plain_ascii_with_windows_line_endings(path):
    data = path.read_bytes()
    assert all(byte < 128 for byte in data), "the file contains bytes outside plain ASCII"
    assert data.count(b"\n") > 0
    assert data.count(b"\n") == data.count(b"\r\n"), "some lines end with a bare LF instead of CRLF"


@pytest.mark.parametrize("path", LAUNCHERS, ids=lambda p: p.name)
def test_launcher_refers_only_to_scripts_that_exist(path):
    for name in SCRIPT_REFERENCE.findall(_text(path)):
        assert (ROOT / "scripts" / name).is_file(), f"{path.name} refers to scripts\\{name}, which does not exist"


@pytest.mark.parametrize("path", LAUNCHERS, ids=lambda p: p.name)
def test_launcher_refers_only_to_requirements_files_that_exist(path):
    for name in set(REQUIREMENTS_REFERENCE.findall(_text(path))):
        assert (ROOT / name).is_file(), f"{path.name} refers to {name}, which does not exist"
