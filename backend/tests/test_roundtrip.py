import pytest

from app.hcl.generate import generate
from app.hcl.parse import parse
from tests.conftest import VALID, load_project


@pytest.mark.parametrize("name", VALID)
def test_parse_generate_round_trip(name: str) -> None:
    model = load_project(name)
    assert parse(generate(model), previous=model) == model


def test_merged_project_tags_are_not_copied_into_resources() -> None:
    # The parser drops tag values equal to the project's, so a round trip keeps them in one place.
    project = load_project("rg")
    rg = project.resources[0].model_copy(update={"inputs": {"tags": {"owner": "app-team"}}})
    project = project.model_copy(
        update={"tags": {"env": "dev", "owner": "platform-team"}, "resources": [rg]}
    )
    parsed = parse(generate(project), project)
    assert parsed.resources[0].inputs.get("tags") == {"owner": "app-team"}
    bare = project.model_copy(update={"resources": [rg.model_copy(update={"inputs": {}})]})
    assert "tags" not in parse(generate(bare), bare).resources[0].inputs
