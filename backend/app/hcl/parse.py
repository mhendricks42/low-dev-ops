"""HCL -> model. Blocks that map cleanly to AVM modules become resources; everything else is
kept verbatim as custom HCL. On a syntax error nothing is returned (ARCHITECTURE sync rule 3)."""

import re
from typing import Any

import hcl2
from pydantic import JsonValue, ValidationError

from app.hcl import HclParseError
from app.hcl.blocks import Chunk, split_blocks
from app.hcl.generate import HEADER
from app.model import ID_PATTERN, NAME_PATTERN, CustomHcl, Project, Ref, Resource

_HEADER_BLOCKS = set(HEADER.split("\n\n"))
_SOURCE = re.compile(r"^Azure/(avm-[a-z0-9-]+)/azurerm$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_REF = re.compile(r"^\$\{module\.([a-z][a-z0-9_]{0,62})\.([A-Za-z_][A-Za-z0-9_]{0,127})\}$")
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
_MODULE_KEYWORDS = {"source", "version", "count", "for_each", "depends_on", "providers"}


class _Unmappable(Exception):
    pass


def _unquote(raw: str) -> str:
    """Decode the source text of an HCL string literal; raise if it is a template."""
    out, i, body = [], 0, raw[1:-1]
    while i < len(body):
        c = body[i]
        if c == "\\":
            nxt = body[i + 1 : i + 2]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
            elif nxt in ("u", "U"):
                size = 4 if nxt == "u" else 8
                digits = body[i + 2 : i + 2 + size]
                if (
                    not re.fullmatch(rf"[0-9A-Fa-f]{{{size}}}", digits)
                    or int(digits, 16) > 0x10FFFF
                ):
                    raise _Unmappable
                out.append(chr(int(digits, 16)))
                i += 2 + size
            else:
                raise _Unmappable
            continue
        if body.startswith(("$${", "%%{"), i):
            out.append(body[i + 1 : i + 3])
            i += 3
            continue
        if body.startswith(("${", "%{"), i):
            raise _Unmappable  # template: an expression, not a literal
        out.append(c)
        i += 1
    return "".join(out)


def _literal(value: Any) -> JsonValue:
    """Convert a python-hcl2 value to JSON, raising if it is not a plain literal."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if len(value) >= 2 and value[0] == value[-1] == '"':
            return _unquote(value)
        raise _Unmappable
    if isinstance(value, list):
        return [_literal(v) for v in value]
    if isinstance(value, dict) and "__is_block__" not in value:
        return {(_unquote(k) if k.startswith('"') else k): _literal(v) for k, v in value.items()}
    raise _Unmappable


def _module(chunk: Chunk) -> Resource:
    """Map one `module` chunk to a Resource (without parent/layout), or raise _Unmappable."""
    if chunk.has_comment or len(chunk.labels) != 1 or not re.match(ID_PATTERN, chunk.labels[0]):
        raise _Unmappable
    body: dict[str, Any] = hcl2.loads(chunk.text)["module"][0][f'"{chunk.labels[0]}"']
    body.pop("__is_block__", None)
    try:
        source = _SOURCE.match(_literal(body.pop("source")))  # type: ignore[arg-type]
        version = _literal(body.pop("version"))
    except (KeyError, TypeError):
        raise _Unmappable from None
    if not source or not isinstance(version, str) or not _VERSION.match(version):
        raise _Unmappable
    inputs: dict[str, JsonValue] = {}
    refs: list[Ref] = []
    for key, value in body.items():
        if key in _MODULE_KEYWORDS or not re.match(NAME_PATTERN, key):
            raise _Unmappable
        if isinstance(value, str) and (ref := _REF.match(value)):
            refs.append(Ref(input=key, to=ref.group(1), output=ref.group(2)))
        else:
            inputs[key] = _literal(value)
    return Resource(
        id=chunk.labels[0], catalog_ref=f"{source.group(1)}@{version}", inputs=inputs, refs=refs
    )


def parse(hcl: str, previous: Project) -> Project:
    """Parse a main.tf back into a model. Fields HCL does not carry come from `previous`."""
    try:
        hcl2.loads(hcl)
    except Exception as e:  # python-hcl2 raises lark errors of several types
        raise HclParseError(str(e).splitlines()[0], getattr(e, "line", None)) from e
    chunks = [c for c in split_blocks(hcl) if c.text not in _HEADER_BLOCKS]

    mapped: dict[int, Resource] = {}
    for index, chunk in enumerate(chunks):
        if chunk.type != "module":
            continue
        try:
            resource = _module(chunk)
        except _Unmappable:
            continue
        if all(r.id != resource.id for r in mapped.values()):
            mapped[index] = resource

    # A ref must point at a mapped module; demoting one block can strand others, so repeat.
    while dangling := [
        i
        for i, r in mapped.items()
        if any(ref.to not in {m.id for m in mapped.values()} for ref in r.refs)
    ]:
        for i in dangling:
            del mapped[i]

    ids = {r.id for r in mapped.values()}
    old = {r.id: r for r in previous.resources}
    resources = [
        r.model_copy(
            update={
                "parent": old[r.id].parent if r.id in old and old[r.id].parent in ids else None,
                "layout": old[r.id].layout if r.id in old else None,
            }
        )
        for _, r in sorted(mapped.items())
    ]

    old_ids = {c.hcl: c.id for c in reversed(previous.custom_hcl)}
    texts = [c.text for i, c in enumerate(chunks) if i not in mapped]
    custom: list[CustomHcl] = []
    used = {old_ids[t] for t in texts if t in old_ids}
    n = 0
    for text in texts:
        cid = old_ids.get(text)
        if cid is None or any(c.id == cid for c in custom):
            n += 1
            while f"custom_{n}" in used:
                n += 1
            cid = f"custom_{n}"
            used.add(cid)
        custom.append(CustomHcl(id=cid, hcl=text))

    data = previous.model_dump()
    data["resources"] = [r.model_dump() for r in resources]
    data["custom_hcl"] = [c.model_dump() for c in custom]
    try:
        return Project.model_validate(data)  # re-runs every cross-field check
    except ValidationError as e:
        raise HclParseError(f"parsed HCL does not form a valid project: {e}") from e
