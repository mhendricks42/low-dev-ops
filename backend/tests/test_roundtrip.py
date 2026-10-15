import pytest

from app.hcl.generate import generate
from app.hcl.parse import parse
from tests.conftest import VALID, load_project


@pytest.mark.parametrize("name", VALID)
def test_parse_generate_round_trip(name: str) -> None:
    model = load_project(name)
    assert parse(generate(model), previous=model) == model
