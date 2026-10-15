import pytest

from app.hcl import HclParseError
from app.hcl.blocks import split_blocks
from tests.conftest import FIXTURES, load_project


def test_splits_custom_fixture_into_exact_block_texts() -> None:
    text = (FIXTURES / "valid" / "custom-hcl" / "main.tf").read_text()
    chunks = split_blocks(text)
    assert [(c.type, c.labels) for c in chunks] == [
        ("terraform", []),
        ("provider", ["azapi"]),
        ("module", ["rg1"]),
        ("resource", ["azapi_resource", "sa"]),
        ("locals", []),
        ("variable", ["env"]),
        ("module", ["rg2"]),
    ]
    customs = [c.hcl for c in load_project("custom-hcl").custom_hcl]
    assert [c.text for c in chunks[3:]] == customs  # comments above a block belong to it
    assert "\n\n".join(c.text for c in chunks) + "\n" == text


def test_braces_inside_strings_comments_and_heredocs_are_ignored() -> None:
    text = (
        'locals {\n  a = "}{"\n  # }\n  // }\n  /* } */\n'
        '  b = "${lookup(m, "}")}"\n  c = "$${not}"\n'
        "  d = <<-EOT\n  }\n  EOT\n}\n"
        'output "x" { value = 1 } # trailing } comment\n'
    )
    chunks = split_blocks(text)
    assert [c.type for c in chunks] == ["locals", "output"]
    assert chunks[1].text == 'output "x" { value = 1 } # trailing } comment'
    assert chunks[1].line == 12


def test_trailing_comment_only_text_is_its_own_chunk() -> None:
    chunks = split_blocks("locals {}\n\n# the end\n")
    assert [(c.type, c.text) for c in chunks] == [("locals", "locals {}"), (None, "# the end")]


@pytest.mark.parametrize(
    ("text", "message", "line"),
    [
        ("locals {}\n}\n", "unexpected '}'", 2),
        ("locals {\n  a = 1\n", "unclosed '{'", 1),
        ('locals {\n  a = "x\n}\n', "unterminated string", 2),
        ("locals {\n  a = <<EOT\nx\n}\n", "unterminated heredoc", 2),
        ("/* never closed\nlocals {}\n", "unterminated comment", 1),
    ],
)
def test_errors_report_line(text: str, message: str, line: int) -> None:
    with pytest.raises(HclParseError, match=message) as err:
        split_blocks(text)
    assert err.value.line == line
