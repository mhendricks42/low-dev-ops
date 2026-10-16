"""One catalog entry per AVM module: its pin, inputs, allowed refs and outputs (ADR-0003)."""

from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from app.model import NAME_PATTERN, _not_reserved

MODULE_PATTERN = r"^avm-[a-z0-9-]+$"
VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"


InputName = Annotated[str, StringConstraints(pattern=NAME_PATTERN), AfterValidator(_not_reserved)]
OutputName = Annotated[str, StringConstraints(pattern=NAME_PATTERN)]


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True
    )


class InputSpec(_Model):
    # basic: shown in the wizard; advanced: behind "more options"; hidden: never shown.
    tier: Literal["basic", "advanced", "hidden"]
    default: JsonValue = None
    # Filled from the project instead of a default: naming (M4) or the subscription.
    fill: Literal["name", "location", "tenant_id"] | None = None
    description: str | None = None


class AllowedRef(_Model):
    input: InputName
    from_: str = Field(alias="from", pattern=MODULE_PATTERN)
    output: OutputName


class CatalogEntry(_Model):
    schema_version: Literal[1]
    module: str = Field(pattern=MODULE_PATTERN)
    version: str = Field(pattern=VERSION_PATTERN)
    title: str
    category: Literal["foundation", "compute"]
    caf_abbreviation: str = Field(pattern=r"^[a-z]{2,8}$")
    # Only for raw azurerm/azapi entries: why AVM can't be used (ADR-0003). None in M2.
    raw_reason: str | None = None
    inputs: dict[InputName, InputSpec]
    refs: list[AllowedRef] = []
    outputs: list[OutputName]
    # Input overrides for the generated example, e.g. a name the module's validation accepts.
    example: dict[InputName, JsonValue] = {}

    @field_validator("outputs")
    @classmethod
    def _unique_outputs(cls, outputs: list[str]) -> list[str]:
        seen: set[str] = set()
        for o in outputs:
            if o in seen:
                raise ValueError(f"duplicate output '{o}'")
            seen.add(o)
        return outputs

    @model_validator(mode="after")
    def _check_inputs(self) -> "CatalogEntry":
        ref_inputs = {r.input for r in self.refs}
        for r in self.refs:
            if r.input not in self.inputs:
                raise ValueError(f"ref input '{r.input}' is not listed under inputs")
        for name, spec in self.inputs.items():
            has_default = "default" in spec.model_fields_set
            if has_default and spec.fill is not None:
                raise ValueError(f"input '{name}' has both a default and a fill")
            if spec.tier == "basic" and not (
                has_default or spec.fill is not None or name in ref_inputs
            ):
                raise ValueError(f"basic input '{name}' needs a default, a fill or an allowed ref")
            if spec.tier == "hidden" and not has_default:
                raise ValueError(f"hidden input '{name}' needs a default")
        for name in self.example:
            if name not in self.inputs:
                raise ValueError(f"example sets unlisted input '{name}'")
        return self

    @property
    def catalog_ref(self) -> str:
        return f"{self.module}@{self.version}"
