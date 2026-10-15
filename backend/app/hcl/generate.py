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

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _string(s: str) -> str:
    s = "".join(_ESCAPES.get(c, c) for c in s)
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
    items = (
        f"{k if _IDENT.match(k) else _string(k)} = {render_value(v)}"
        for k, v in sorted(value.items())
    )
    return "{ " + ", ".join(items) + " }"


def _attributes(pairs: list[tuple[str, str]]) -> list[str]:
    # terraform fmt aligns "=" across consecutive single-line attributes.
    width = max(len(k) for k, _ in pairs)
    return [f"  {k.ljust(width)} = {v}" for k, v in pairs]


def _module(r: Resource) -> str:
    name, version = r.catalog_ref.split("@")
    lines = [f'module "{r.id}" {{']
    lines += _attributes(
        [("source", _string(f"Azure/{name}/azurerm")), ("version", _string(version))]
    )
    args = {k: render_value(v) for k, v in r.inputs.items()}
    args |= {ref.input: f"module.{ref.to}.{ref.output}" for ref in r.refs}
    if args:
        lines += ["", *_attributes(sorted(args.items()))]
    lines.append("}")
    return "\n".join(lines)


def generate(project: Project) -> str:
    sections = [
        HEADER,
        *(_module(r) for r in project.resources),
        *(c.hcl for c in project.custom_hcl),
    ]
    return "\n\n".join(sections) + "\n"
