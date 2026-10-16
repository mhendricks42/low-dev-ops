"""Local app settings: <workspace>/settings.json (M5). No secrets, ever.

"settings.json" cannot be a project name (names match ^[a-z][a-z0-9-]{0,62}$), so it never
collides with a project directory.
"""

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.api.projects import _workspace


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Backend(_Model):
    """The shared state backend of one subscription (PRD: state bootstrap)."""

    resource_group: str
    storage_account: str
    container: str
    location: str


class Settings(_Model):
    backends: dict[str, Backend] = {}  # by subscription id


def _path() -> Path:
    return _workspace().resolve() / "settings.json"


def load() -> Settings:
    path = _path()
    if not path.is_file():
        return Settings()
    return Settings.model_validate_json(path.read_text())


def save(settings: Settings) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = settings.model_dump_json(by_alias=True, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as f:
        f.write(text)
    try:
        os.replace(f.name, path)
    except BaseException:
        os.unlink(f.name)
        raise
