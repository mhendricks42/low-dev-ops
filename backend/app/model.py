"""The internal model: one Project per project.json, the single source of truth (ADR-0002)."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

ID_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
CATALOG_REF_PATTERN = r"^avm-[a-z0-9-]+@\d+\.\d+\.\d+$"
# Input and output names are written into HCL unquoted, so they must be plain identifiers.
NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]{0,127}$"


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Meta(_Model):
    name: str
    created: str
    lowdevops_version: str


class Subscription(_Model):
    id: str
    tenant_id: str
    location: str


class Naming(_Model):
    workload: str
    env: str
    region: str
    pattern: str


class Ref(_Model):
    input: str = Field(pattern=NAME_PATTERN)
    to: str = Field(pattern=ID_PATTERN)
    output: str = Field(pattern=NAME_PATTERN)


class Layout(_Model):
    x: float
    y: float


class Resource(_Model):
    id: str = Field(pattern=ID_PATTERN)
    catalog_ref: str = Field(pattern=CATALOG_REF_PATTERN)
    parent: str | None = None
    inputs: dict[Annotated[str, StringConstraints(pattern=NAME_PATTERN)], JsonValue] = {}
    refs: list[Ref] = []
    layout: Layout | None = None

    @field_validator("refs")
    @classmethod
    def _canonical_order(cls, refs: list[Ref]) -> list[Ref]:
        # Same order the generator emits and the parser reads, so round-trips compare equal.
        return sorted(refs, key=lambda r: r.input)


class CustomHcl(_Model):
    id: str
    hcl: str


class Waiver(_Model):
    finding_id: str
    resource: str
    reason: str
    by: str
    at: str


class Project(_Model):
    schema_version: Literal[1]
    meta: Meta
    subscription: Subscription
    naming: Naming
    tags: dict[str, str] = {}
    resources: list[Resource] = []
    custom_hcl: list[CustomHcl] = []
    waivers: list[Waiver] = []

    @model_validator(mode="after")
    def _check_references(self) -> "Project":
        ids: set[str] = set()
        for r in self.resources:
            if r.id in ids:
                raise ValueError(f"duplicate resource id '{r.id}'")
            ids.add(r.id)
        custom_ids: set[str] = set()
        for c in self.custom_hcl:
            if c.id in custom_ids:
                raise ValueError(f"duplicate customHcl id '{c.id}'")
            custom_ids.add(c.id)
        for r in self.resources:
            if r.parent is not None and r.parent not in ids:
                raise ValueError(f"resource '{r.id}' has unknown parent '{r.parent}'")
            for ref in r.refs:
                if ref.to == r.id:
                    raise ValueError(f"resource '{r.id}' references itself")
                if ref.to not in ids:
                    raise ValueError(f"resource '{r.id}' has a ref to unknown resource '{ref.to}'")
                if ref.input in r.inputs:
                    raise ValueError(
                        f"resource '{r.id}' input '{ref.input}' is set both as input and ref"
                    )
        return self
