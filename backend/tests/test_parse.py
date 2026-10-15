import time

import pytest

from app.hcl import HclParseError
from app.hcl.generate import HEADER, generate
from app.hcl.parse import _demote_dangling, parse
from app.model import Project, Ref, Resource
from tests.conftest import FIXTURES, load_project

RG = """module "rg1" {
  source  = "Azure/avm-res-resources-resourcegroup/azurerm"
  version = "0.4.0"

  location = "westeurope"
  name     = "rg-a"
}"""


def hcl(*blocks: str) -> str:
    return "\n\n".join([HEADER, *blocks]) + "\n"


def custom_texts(project: Project) -> list[str]:
    return [c.hcl for c in project.custom_hcl]


def test_custom_hcl_survives_byte_for_byte() -> None:
    previous = load_project("custom-hcl")
    text = (FIXTURES / "valid" / "custom-hcl" / "main.tf").read_text()
    parsed = parse(text, previous)
    assert custom_texts(parsed) == custom_texts(previous)
    assert [r.id for r in parsed.resources] == ["rg1"]  # rg2 uses var., so it stays custom
    assert generate(parsed) == text


def test_new_resources_from_hcl_get_no_parent_or_layout() -> None:
    text = (FIXTURES / "valid" / "rg-vnet" / "main.tf").read_text()
    parsed = parse(text, previous=load_project("rg"))
    vnet = parsed.resources[1]
    assert (vnet.id, vnet.parent, vnet.layout) == ("vnet1", None, None)
    assert vnet.catalog_ref == "avm-res-network-virtualnetwork@0.22.3"
    assert [(r.input, r.to, r.output) for r in vnet.refs] == [("parent_id", "rg1", "resource_id")]
    assert parsed.resources[0].layout == load_project("rg").resources[0].layout


def test_edited_value_reaches_model() -> None:
    previous = load_project("rg")
    text = generate(previous).replace('"rg-webapp-dev-weu"', '"rg-renamed"')
    assert parse(text, previous).resources[0].inputs["name"] == "rg-renamed"


def test_string_escapes_decode_and_regenerate_identically() -> None:
    text = hcl(RG.replace('"rg-a"', '"a\\"b\\\\c$${x}%%{y}\\n"'))
    parsed = parse(text, load_project("rg"))
    assert parsed.resources[0].inputs["name"] == 'a"b\\c${x}%{y}\n'
    assert generate(parsed) == text


def test_syntax_error_raises_with_line_and_leaves_previous_unchanged() -> None:
    previous = load_project("rg-vnet")
    before = previous.model_dump()
    with pytest.raises(HclParseError) as err:
        parse(hcl(RG.replace('name     = "rg-a"', "name = ")), previous)
    assert err.value.line == 18
    assert previous.model_dump() == before


@pytest.mark.parametrize(
    "block",
    [
        RG.replace('"rg-a"', '"rg-${var.env}"'),  # template
        RG.replace('"rg-a"', 'lower("RG-A")'),  # function call
        RG.replace('"rg-a"', "var.name"),  # variable
        RG.replace("location = ", "count    = 1\n  location = "),  # meta-argument
        RG.replace('"Azure/avm-res-resources-resourcegroup/azurerm"', '"./modules/rg"'),
        RG.replace('"0.4.0"', '"~> 0.4"'),  # unpinned
        RG.replace('module "rg1"', 'module "RG1"'),  # label is not a valid id
        RG.replace("  location", "  # why\n  location"),  # comment would be lost
        "# about rg1\n" + RG,  # comment above would be lost
        RG.replace("}", "  lifecycle {\n    prevent_destroy = true\n  }\n}"),  # nested block
        RG.replace('"rg-a"', "module.rg9.name"),  # ref to unknown module
        RG.replace('name     = "rg-a"', 'name     = "rg-a"\n  name     = "rg-b"'),  # duplicate
        RG.replace('"rg-a"', '"rg-a"\n  tags     = { a = 1, "a" = 2 }'),  # duplicate key
        RG.replace('"rg-a"', "<<EOT\nrg-a\nEOT"),  # heredoc
        RG.replace('"rg-a"', "<<-EOT\n    rg-a\n  EOT"),  # indented heredoc
        RG.replace('name     = "rg-a"', 'name     = "rg-a"\n  tags     = { (var.k) = 1 }'),
        RG.replace('name     = "rg-a"', 'name     = "rg-a"\n  tags     = { var.k = 1 }'),
    ],
)
def test_unmappable_module_becomes_custom(block: str) -> None:
    parsed = parse(hcl(block), load_project("rg"))
    assert parsed.resources == []
    assert custom_texts(parsed) == [block]


def test_quoted_and_dashed_object_keys_are_literal() -> None:
    block = RG.replace(
        'name     = "rg-a"', 'name     = "rg-a"\n  tags     = { "a b" = "x", b-c = "y" }'
    )
    tags = parse(hcl(block), load_project("rg")).resources[0].inputs["tags"]
    assert tags == {"a b": "x", "b-c": "y"}


def test_ref_to_a_demoted_module_demotes_the_referrer() -> None:
    rg = RG.replace('"rg-a"', "var.name")
    vnet = RG.replace('module "rg1"', 'module "vnet1"').replace('"rg-a"', "module.rg1.name")
    parsed = parse(hcl(rg, vnet), load_project("rg"))
    assert parsed.resources == []
    assert custom_texts(parsed) == [rg, vnet]


def test_duplicate_module_label_keeps_the_second_as_custom() -> None:
    parsed = parse(hcl(RG, RG), load_project("rg"))
    assert [r.id for r in parsed.resources] == ["rg1"]
    assert custom_texts(parsed) == [RG]


def test_edited_header_is_kept_as_custom() -> None:
    edited = HEADER.split("\n\n")[0].replace("~> 2.12", "~> 2.13")
    text = edited + '\n\nprovider "azapi" {}\n'
    assert custom_texts(parse(text, load_project("rg"))) == [edited]


def test_custom_ids_are_reused_by_text_and_new_ones_numbered() -> None:
    previous = load_project("custom-hcl")
    text = generate(previous) + '\noutput "x" {\n  value = 1\n}\n'
    ids = [c.id for c in parse(text, previous).custom_hcl]
    assert ids == ["custom_1", "custom_2", "custom_3", "custom_4", "custom_5"]


def test_heredoc_closing_marker_with_trailing_space_does_not_close_it() -> None:
    # HCL keeps reading the heredoc past "EOT ", so this is one block, kept verbatim.
    text = 'module "a" {\n  x = <<EOT\nEOT \n}\nmodule "b" {\nEOT\n}\n'
    parsed = parse(text, load_project("rg"))
    assert parsed.resources == []
    assert custom_texts(parsed) == [text.rstrip()]


def test_chain_of_dangling_refs_is_demoted_end_to_end() -> None:
    blocks = [
        RG.replace('module "rg1"', f'module "m{i}"').replace('"rg-a"', f"module.m{i - 1}.name")
        for i in range(1, 20)
    ]
    parsed = parse(hcl(*blocks), load_project("rg"))
    assert parsed.resources == []  # m0 does not exist, so every module is demoted
    assert custom_texts(parsed) == blocks


def test_demoting_a_long_chain_is_linear() -> None:
    # Timed on the pure helper so the guard does not depend on parser speed.
    n = 20_000
    mapped = {
        i: Resource(
            id=f"m{i}",
            catalog_ref="avm-res-resources-resourcegroup@0.4.0",
            refs=[Ref(input="parent_id", to=f"m{i - 1}", output="name")],
        )
        for i in range(1, n)
    }
    start = time.perf_counter()
    _demote_dangling(mapped)
    assert mapped == {}
    assert time.perf_counter() - start < 1  # a rescanning loop would take minutes here
