"""HCL -> model. Blocks that map cleanly to AVM modules become resources; everything else is
kept verbatim as custom HCL. On a syntax error nothing is returned (ARCHITECTURE sync rule 3)."""

import re
from collections import Counter, defaultdict
from typing import Any

import hcl2
from lark import Token, Tree
from pydantic import JsonValue, ValidationError

from app.hcl import HclParseError
from app.hcl.blocks import Chunk, split_blocks
from app.hcl.generate import HEADER
from app.model import ID_PATTERN, NAME_PATTERN, RESERVED_NAMES, CustomHcl, Project, Ref, Resource

_HEADER_BLOCKS = set(HEADER.split("\n\n"))
_SOURCE = re.compile(r"Azure/(avm-[a-z0-9-]+)/azurerm")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_REF = re.compile(r"\$\{module\.([a-z][a-z0-9_]{0,62})\.([A-Za-z_][A-Za-z0-9_]{0,127})\}")
_BARE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}


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


def _key(key: str) -> str:
    """Object keys: quoted strings or bare identifiers; anything else is an expression."""
    if key.startswith('"'):
        return str(_literal(key))
    if _BARE_KEY.fullmatch(key):
        return key
    raise _Unmappable


def _literal(value: Any) -> JsonValue:
    """Convert a python-hcl2 value to JSON, raising if it is not a plain literal."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        # A quoted literal never holds a raw newline; python-hcl2 renders heredocs that way.
        if len(value) >= 2 and value[0] == value[-1] == '"' and "\n" not in value:
            return _unquote(value)
        raise _Unmappable
    if isinstance(value, list):
        return [_literal(v) for v in value]
    if isinstance(value, dict) and "__is_block__" not in value:
        return {_key(k): _literal(v) for k, v in value.items()}
    raise _Unmappable


def _name(node: Token | Tree[Token]) -> str:
    """Text of an attribute name or object key, with quotes dropped so `a` and `"a"` match."""
    if isinstance(node, Token):
        return str(node)
    return "".join(t for t in node.scan_values(lambda v: isinstance(v, Token)) if t != '"')


def _has_duplicates(tree: Tree[Token]) -> bool:
    """True if an attribute or object key repeats. python-hcl2 keeps only the last one."""
    for node in tree.iter_subtrees():
        kind = {"body": "attribute", "object": "object_elem"}.get(str(node.data))
        if kind is None:
            continue
        names = [
            _name(child.children[0])
            for child in node.children
            if isinstance(child, Tree) and child.data == kind
        ]
        if len(names) != len(set(names)):
            return True
    return False


def _module(chunk: Chunk) -> Resource:
    """Map one `module` chunk to a Resource (without parent/layout), or raise _Unmappable."""
    if chunk.has_comment or len(chunk.labels) != 1 or not re.fullmatch(ID_PATTERN, chunk.labels[0]):
        raise _Unmappable
    try:
        # The whole file already parsed; a failure here means the splitter cut it differently.
        if _has_duplicates(hcl2.parses_to_tree(chunk.text)):
            raise _Unmappable
        body: dict[str, Any] = hcl2.loads(chunk.text)["module"][0][f'"{chunk.labels[0]}"']
        source = _SOURCE.fullmatch(str(_literal(body.pop("source"))))
        version = _literal(body.pop("version"))
    except _Unmappable:
        raise
    except Exception:
        raise _Unmappable from None
    body.pop("__is_block__", None)
    if not source or not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise _Unmappable
    inputs: dict[str, JsonValue] = {}
    refs: list[Ref] = []
    for key, value in body.items():
        if key in RESERVED_NAMES or not re.fullmatch(NAME_PATTERN, key):
            raise _Unmappable
        if isinstance(value, str) and (ref := _REF.fullmatch(value)):
            refs.append(Ref(input=key, to=ref.group(1), output=ref.group(2)))
        else:
            inputs[key] = _literal(value)
    try:
        return Resource(
            id=chunk.labels[0], catalog_ref=f"{source.group(1)}@{version}", inputs=inputs, refs=refs
        )
    except ValidationError:
        raise _Unmappable from None


def _demote_dangling(mapped: dict[int, Resource]) -> None:
    """Drop resources whose refs point at a module that is not mapped, transitively.

    Demoting one block can strand the blocks that refer to it, so walk the reverse-reference
    graph once instead of rescanning (linear in the number of refs).
    """
    by_id = {r.id: i for i, r in mapped.items()}
    referrers: dict[str, list[int]] = defaultdict(list)
    for i, r in mapped.items():
        for ref in r.refs:
            referrers[ref.to].append(i)
    queue = [i for i, r in mapped.items() if any(ref.to not in by_id for ref in r.refs)]
    while queue:
        i = queue.pop()
        if i in mapped:
            queue += referrers[mapped.pop(i).id]


def _block_keys(chunks: list[Chunk]) -> Counter[tuple[str, str | None]]:
    return Counter((c.type, c.labels[0] if c.labels else None) for c in chunks if c.type)


def _hcl2_block_keys(tree: dict[str, Any]) -> Counter[tuple[str, str | None]]:
    keys: Counter[tuple[str, str | None]] = Counter()
    for kind, entries in tree.items():
        if kind == "__comments__" or not isinstance(entries, list):
            continue
        for entry in entries:
            names = [k for k in entry if k != "__is_block__"]
            label = names[0] if len(names) == 1 and names[0].startswith('"') else None
            keys[(kind, label[1:-1] if label else None)] += 1
    return keys


def parse(hcl: str, previous: Project) -> Project:
    """Parse a main.tf back into a model. Fields HCL does not carry come from `previous`."""
    try:
        tree: dict[str, Any] = hcl2.loads(hcl)
    except Exception as e:  # python-hcl2 raises lark errors of several types
        raise HclParseError(str(e).splitlines()[0], getattr(e, "line", None)) from e
    all_chunks = split_blocks(hcl)
    if _block_keys(all_chunks) != _hcl2_block_keys(tree):
        # Never guess: a module the splitter sees might be text inside a heredoc, or vice versa.
        raise HclParseError("could not split the file into blocks unambiguously")
    chunks = [c for c in all_chunks if c.text not in _HEADER_BLOCKS]

    mapped: dict[int, Resource] = {}
    seen: set[str] = set()
    for index, chunk in enumerate(chunks):
        if chunk.type != "module":
            continue
        try:
            resource = _module(chunk)
        except _Unmappable:
            continue
        if resource.id not in seen:
            seen.add(resource.id)
            mapped[index] = resource

    _demote_dangling(mapped)

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
    taken: set[str] = set()
    n = 0
    for text in texts:
        cid = old_ids.get(text)
        if cid is None or cid in taken:
            n += 1
            while f"custom_{n}" in used:
                n += 1
            cid = f"custom_{n}"
            used.add(cid)
        taken.add(cid)
        custom.append(CustomHcl(id=cid, hcl=text))

    data = previous.model_dump()
    data["resources"] = [r.model_dump() for r in resources]
    data["custom_hcl"] = [c.model_dump() for c in custom]
    try:
        return Project.model_validate(data)  # re-runs every cross-field check
    except ValidationError as e:
        raise HclParseError(f"parsed HCL does not form a valid project: {e}") from e
