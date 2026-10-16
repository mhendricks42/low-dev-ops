"""Model -> canonical HCL. Deterministic: the same Project always yields the same bytes."""

import re

from pydantic import JsonValue

from app.model import Project, Resource

HEADER = """terraform {
  required_version = ">= 1.11, < 2.0"
  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.12"
    }
  }
}

provider "azapi" {}"""

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Bare object keys that HCL would read as keywords rather than names.
_KEYWORDS = frozenset({"true", "false", "null", "for", "in", "if", "else", "endif", "endfor"})
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _char(c: str) -> str:
    if c in _ESCAPES:
        return _ESCAPES[c]
    code = ord(c)
    if code < 0x20 or 0x7F <= code <= 0x9F or code in (0x2028, 0x2029):
        return f"\\u{code:04x}"
    return c


def _key(k: str) -> str:
    return k if _IDENT.fullmatch(k) and k not in _KEYWORDS else _string(k)


def _string(s: str) -> str:
    s = "".join(_char(c) for c in s)
    # A literal "${" or "%{" would start a template in HCL; doubling the sigil escapes it.
    return '"' + s.replace("${", "$${").replace("%{", "%%{") + '"'


def render_value(value: JsonValue) -> str:
    """Render a JSON value as single-line HCL."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ", ".join(render_value(v) for v in value) + "]"
    if not value:
        return "{}"
    items = (f"{_key(k)} = {render_value(v)}" for k, v in sorted(value.items()))
    return "{ " + ", ".join(items) + " }"


def _attributes(pairs: list[tuple[str, str]]) -> list[str]:
    # terraform fmt aligns "=" across consecutive single-line attributes.
    width = max(len(k) for k, _ in pairs)
    return [f"  {k.ljust(width)} = {v}" for k, v in pairs]


def _with_project_tags(inputs: dict[str, JsonValue], tags: dict[str, str]) -> dict[str, JsonValue]:
    # M4: project tags go on every module (AVM resource modules all take `tags`); the
    # resource's own keys win. Non-object tags are left as written.
    own = inputs.get("tags", {})
    if not tags or not isinstance(own, dict):
        return inputs
    return {**inputs, "tags": {**tags, **own}}


def _module(r: Resource, tags: dict[str, str]) -> str:
    name, version = r.catalog_ref.split("@")
    lines = [f'module "{r.id}" {{']
    lines += _attributes(
        [("source", _string(f"Azure/{name}/azurerm")), ("version", _string(version))]
    )
    args = {k: render_value(v) for k, v in _with_project_tags(r.inputs, tags).items()}
    args |= {ref.input: f"module.{ref.to}.{ref.output}" for ref in r.refs}
    if args:
        lines += ["", *_attributes(sorted(args.items()))]
    lines.append("}")
    return "\n".join(lines)


def generate(project: Project) -> str:
    sections = [
        HEADER,
        *(_module(r, project.tags) for r in project.resources),
        *(c.hcl for c in project.custom_hcl),
    ]
    return "\n\n".join(sections) + "\n"
