"""Pins how python-hcl2 represents values; app/hcl/parse.py relies on exactly this."""

import hcl2
import pytest

SRC = """
module "m" {
  s   = "a\\"b$${x}"
  n   = 3
  f   = 1.5
  b   = true
  z   = null
  l   = ["x"]
  o   = { a = "x", "b-c" = 2 }
  ref = module.rg1.resource_id
  v   = var.x
  i   = "${var.x}-a"
}
"""


def test_value_representation() -> None:
    body = hcl2.loads(SRC)["module"][0]['"m"']
    assert body["s"] == '"a\\"b$${x}"'  # literal: source text, quotes kept, escapes untouched
    assert (body["n"], body["f"], body["b"], body["z"]) == (3, 1.5, True, None)
    assert body["l"] == ['"x"']
    assert body["o"] == {"a": '"x"', '"b-c"': 2}
    assert body["ref"] == "${module.rg1.resource_id}"  # expression: wrapped in ${ }
    assert body["v"] == "${var.x}"
    assert body["i"] == '"${var.x}-a"'  # template: quoted but contains ${
    assert body["__is_block__"] is True


@pytest.mark.parametrize(
    ("src", "value"),
    [
        ("a = <<EOT\nhi\nEOT\n", '"<<EOT\nhi\nEOT"'),  # heredoc: quoted, with a raw newline
        ("a = { (var.x) = 1 }\n", {"${(var.x)}": 1}),  # expression key
        ("a = { var.x = 1 }\n", {"${var.x}": 1}),
        ('a = { "q" = 1 }\n', {'"q"': 1}),
        ("a = { b-c = 1 }\n", {"b-c": 1}),
    ],
)
def test_heredoc_and_object_key_representation(src: str, value: object) -> None:
    assert hcl2.loads(src)["a"] == value


def test_syntax_error_has_line() -> None:
    with pytest.raises(Exception) as err:
        hcl2.loads('module "x" {\n  a = \n}\n')
    assert getattr(err.value, "line", None) == 2
