import os

import pytest

from app.hcl.generate import generate, render_value
from tests.conftest import FIXTURES, VALID, load_project


@pytest.mark.parametrize("name", VALID)
def test_snapshot(name: str) -> None:
    expected = FIXTURES / "valid" / name / "main.tf"
    actual = generate(load_project(name))
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        expected.write_text(actual)
    assert actual == expected.read_text()


def test_generate_is_deterministic() -> None:
    project = load_project("rg-vnet-nsg")
    assert generate(project) == generate(project.model_copy(deep=True))


@pytest.mark.parametrize(
    ("value", "hcl"),
    [
        ("plain", '"plain"'),
        ('q"b\\s', '"q\\"b\\\\s"'),
        ("line\nnext\ttab", '"line\\nnext\\ttab"'),
        ("${var.x} %{if}", '"$${var.x} %%{if}"'),
        ("$ and % alone", '"$ and % alone"'),
        (True, "true"),
        (False, "false"),
        (None, "null"),
        (3, "3"),
        (1.5, "1.5"),
        ([], "[]"),
        (["a", 1], '["a", 1]'),
        ({}, "{}"),
        ({"a": 1, "b-c": "x", "1x": True}, '{ "1x" = true, a = 1, "b-c" = "x" }'),
        ({"o": {"p": [1]}}, "{ o = { p = [1] } }"),
        ({"null": 1, "for": 2, "foo\n": 3}, '{ "foo\\n" = 3, "for" = 2, "null" = 1 }'),
        ("nul\x00 esc\x1b ls\u2028 del\x7f", '"nul\\u0000 esc\\u001b ls\\u2028 del\\u007f"'),
    ],
)
def test_render_value(value: object, hcl: str) -> None:
    assert render_value(value) == hcl  # type: ignore[arg-type]  # parametrize erases the JsonValue type
