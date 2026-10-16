"""Load and cross-check catalog/*.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.catalog.model import CatalogEntry

CATALOG_DIR = Path(__file__).resolve().parents[3] / "catalog"


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class Catalog:
    entries: dict[str, CatalogEntry]

    def get(self, catalog_ref: str) -> CatalogEntry | None:
        module, _, version = catalog_ref.partition("@")
        entry = self.entries.get(module)
        return entry if entry is not None and entry.version == version else None


def _load_entry(path: Path) -> CatalogEntry:
    try:
        # safe_load only: YAML tags such as !!python/object are rejected, never constructed.
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise CatalogError(f"{path.name}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise CatalogError(f"{path.name}: must be a YAML mapping")
    try:
        entry = CatalogEntry.model_validate(data)
    except ValidationError as e:
        raise CatalogError(f"{path.name}: {e}") from e
    if path.stem != entry.module:
        raise CatalogError(f"{path.name}: file name does not match module '{entry.module}'")
    return entry


def load_catalog(directory: Path = CATALOG_DIR) -> Catalog:
    entries: dict[str, CatalogEntry] = {}
    files = sorted(directory.glob("*.yaml"))
    if not files:
        raise CatalogError(f"{directory}: no catalog entries")
    for path in files:
        entry = _load_entry(path)
        entries[entry.module] = entry  # file names are unique, and each must equal its module
    for entry in entries.values():
        for ref in entry.refs:
            target = entries.get(ref.from_)
            if target is None:
                raise CatalogError(
                    f"{entry.module}.yaml: ref to unknown catalog entry '{ref.from_}'"
                )
            if ref.output not in target.outputs:
                raise CatalogError(
                    f"{entry.module}.yaml: ref '{ref.input}': '{ref.from_}' has no output "
                    f"'{ref.output}'"
                )
    return Catalog(entries)
