"""A push must never publish an Android release from branch v4.

The v4 pre-release ("app-v4-preview") may be published only by a manual run that explicitly asks for it. These checks
read the workflow as text (PyYAML is not a test dependency) and fail if a later edit lets a push publish again.
"""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "android-apk.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _step(text: str, marker: str) -> str:
    """The workflow step whose first lines contain ``marker``, up to the next step."""
    start = text.index(marker)
    begin = text.rfind("\n      - ", 0, start)
    end = text.find("\n      - ", start)
    return text[begin : end if end != -1 else len(text)]


def test_publish_flag_needs_a_manual_v4_run_with_an_address():
    line = next(raw for raw in _text().splitlines() if raw.strip().startswith("PUBLISH:"))
    v4_clause = line.split("||", 1)[1]
    assert "github.ref_name == 'main'" in line.split("||", 1)[0]
    for required in (
        "github.ref_name == 'v4'",
        "github.event_name == 'workflow_dispatch'",
        "inputs.publish_v4_preview",
        "vars.V4_PLANNER_URL != ''",
    ):
        assert required in v4_clause, required
    assert v4_clause.count("&&") == 3


def test_release_and_artifact_steps_are_gated_by_the_publish_flag():
    text = _text()
    release = _step(text, "softprops/action-gh-release")
    artifact = _step(text, "actions/upload-artifact")
    assert "if: env.PUBLISH == 'true'" in release
    assert "if: env.PUBLISH == 'true'" in artifact


def test_manual_publish_input_defaults_to_off():
    block = _text().split("publish_v4_preview:", 1)[1].split("\n\n", 1)[0]
    assert re.search(r"type:\s*boolean", block)
    assert re.search(r"default:\s*false", block)


def test_no_other_step_publishes_a_release():
    text = _text()
    assert text.count("action-gh-release") == 1
    assert "gh release" not in text
