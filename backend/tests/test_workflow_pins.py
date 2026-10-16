"""Every GitHub Action is pinned to a commit SHA, not a movable tag (M3.1, #9)."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

GITHUB = Path(__file__).resolve().parents[2] / ".github"
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
DOCKER_PINNED = re.compile(r"^docker://[^@\s]+@sha256:[0-9a-f]{64}$")


def action_files(root: Path) -> list[Path]:
    # Workflows plus local (composite) actions, whose own steps can pull in remote actions.
    patterns = [
        "workflows/*.yml",
        "workflows/*.yaml",
        "actions/**/action.yml",
        "actions/**/action.yaml",
    ]
    return sorted(path for pattern in patterns for path in root.glob(pattern))


def uses_refs(node: object) -> Iterator[str]:
    # Walks the parsed YAML, so quoted keys and flow mappings are seen like any other form.
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uses":
                yield str(value)
            else:
                yield from uses_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from uses_refs(item)


def unpinned(ref: str) -> bool:
    if ref.startswith("./"):
        # Only local actions in the scanned folder; their own action.yml is checked too.
        return not ref.startswith("./.github/actions/")
    if ref.startswith("docker://"):
        return not DOCKER_PINNED.match(ref)
    return not PINNED.match(ref)


def test_every_action_is_pinned_to_a_sha() -> None:
    files = action_files(GITHUB)
    assert files, "no workflows found"
    found = [
        f"{path.name}: {ref}"
        for path in files
        for ref in uses_refs(yaml.safe_load(path.read_text()))
        if unpinned(ref)
    ]
    assert found == []


@pytest.mark.parametrize(
    "text",
    [
        "jobs: {a: {steps: [{uses: evil/action@main}]}}",
        'jobs:\n  a:\n    steps:\n      - "uses": evil/action@v1\n',
        "jobs:\n  a:\n    uses: evil/repo/.github/workflows/x.yml@main\n",
        "runs:\n  steps:\n    - uses: docker://alpine:latest\n",
        "runs:\n  steps:\n    - uses: actions/checkout@v7\n",
        "jobs: {a: {steps: [{uses: ./tools/unscanned}]}}",
    ],
)
def test_every_spelling_of_an_unpinned_action_is_caught(text: str) -> None:
    assert any(unpinned(ref) for ref in uses_refs(yaml.safe_load(text)))


def test_local_and_digest_pinned_refs_are_accepted(tmp_path: Path) -> None:
    refs = ["./.github/actions/x", f"o/r@{'a' * 40}", f"docker://i@sha256:{'b' * 64}"]
    assert not any(unpinned(ref) for ref in uses_refs({"steps": [{"uses": r} for r in refs]}))
    (tmp_path / "workflows").mkdir()
    (tmp_path / "actions" / "x").mkdir(parents=True)
    (tmp_path / "workflows" / "release.yaml").touch()
    (tmp_path / "actions" / "x" / "action.yml").touch()
    assert [p.name for p in action_files(tmp_path)] == ["action.yml", "release.yaml"]
