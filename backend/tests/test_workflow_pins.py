"""Every GitHub Action is pinned to a commit SHA, not a movable tag (M3.1, #9)."""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def test_every_action_is_pinned_to_a_sha() -> None:
    files = sorted(WORKFLOWS.glob("*.yml"))
    assert files, "no workflows found"
    unpinned = [
        f"{path.name}: {ref}"
        for path in files
        for ref in USES.findall(path.read_text())
        if not ref.startswith(("./", "docker://")) and not PINNED.match(ref)
    ]
    assert unpinned == []
