"""Split HCL source into top-level blocks, keeping each block's exact text.

python-hcl2 parses values but drops formatting and comments; custom HCL must survive
byte for byte, so this scanner finds where each top-level block starts and ends.
"""

import re
from dataclasses import dataclass

from app.hcl import HclParseError

# Same marker characters as python-hcl2, so both agree on where a heredoc ends.
_HEREDOC = re.compile(r"<<-?([A-Za-z][A-Za-z0-9._-]*)\r?\n")
_HEADER = re.compile(
    r'([A-Za-z_][\w-]*)((?:[ \t]+(?:"(?:[^"\\\n]|\\.)*"|[A-Za-z_][\w-]*))*)[ \t]*\{'
)
_LABEL = re.compile(r'"((?:[^"\\\n]|\\.)*)"|([A-Za-z_][\w-]*)')


@dataclass(frozen=True)
class Chunk:
    text: str  # exact source, including comments directly above; outer blank lines trimmed
    line: int  # line of the block header (or first line, for comment-only chunks)
    type: str | None  # e.g. "module"; None for text that is not a block
    labels: list[str]
    has_comment: bool  # mapping such a block would lose the comment


def _trim(text: str) -> str:
    return re.sub(r"\A(?:[ \t]*\r?\n)+", "", text).rstrip()


def _chunk(text: str, code_start: int | None, start_line: int, has_comment: bool) -> Chunk:
    trimmed = _trim(text)
    offset = len(text) - len(text.lstrip()) if code_start is None else code_start
    line = start_line + text.count("\n", 0, offset)
    m = _HEADER.match(text, code_start) if code_start is not None else None
    if not m:
        return Chunk(trimmed, line, None, [], has_comment)
    labels = [
        x.group(1) if x.group(1) is not None else x.group(2) for x in _LABEL.finditer(m.group(2))
    ]
    return Chunk(trimmed, line, m.group(1), labels, has_comment)


def split_blocks(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    stack: list[tuple[str, int]] = []  # ("{" | "${" | '"', line it opened on)
    i, line, n = 0, 1, len(text)
    start, start_line = 0, 1
    code_start: int | None = None  # first non-comment character of the current chunk
    has_comment = False

    while i < n:
        c = text[i]
        if stack and stack[-1][0] == '"':
            if c == "\n":
                raise HclParseError("unterminated string", line)
            if c == "\\":
                i += 2
                continue
            if text.startswith(("$${", "%%{"), i):
                i += 3
                continue
            if text.startswith(("${", "%{"), i):
                stack.append(("${", line))
                i += 2
                continue
            if c == '"':
                stack.pop()
            i += 1
            continue

        if c == "\n":
            line += 1
        elif c == "#" or text.startswith("//", i):
            has_comment = True
            i = text.find("\n", i)
            i = n if i == -1 else i
            continue
        elif text.startswith("/*", i):
            has_comment = True
            end = text.find("*/", i + 2)
            if end == -1:
                raise HclParseError("unterminated comment", line)
            line += text.count("\n", i, end)
            i = end + 2
            continue
        elif not c.isspace():
            if code_start is None:
                code_start = i
            if c == '"':
                stack.append(('"', line))
            elif (m := _HEREDOC.match(text, i)) is not None:
                # python-hcl2 allows any whitespace but "\n" (so "\r" too) before the marker.
                close = re.compile(rf"^[^\S\n]*{re.escape(m.group(1))}\r?$", re.M)
                closing = close.search(text, m.end())
                if closing is None:
                    raise HclParseError("unterminated heredoc", line)
                line += text.count("\n", i, closing.end())
                i = closing.end()
                continue
            elif c == "{":
                stack.append(("{", line))
            elif c == "}":
                if not stack:
                    raise HclParseError("unexpected '}'", line)
                stack.pop()
                if not stack:
                    # Keep a trailing comment on the closing line with its block.
                    eol = text.find("\n", i)
                    eol = n if eol == -1 else eol
                    rest = text[i + 1 : eol].strip()
                    end = eol if rest == "" or rest.startswith(("#", "//")) else i + 1
                    has_comment = has_comment or (end == eol and rest != "")
                    chunk = _chunk(text[start:end], code_start - start, start_line, has_comment)
                    chunks.append(chunk)
                    start, start_line, code_start, i = end, line, None, end
                    has_comment = False
                    continue
        i += 1

    if stack:
        kind, opened = stack[0]
        raise HclParseError("unclosed '{'" if kind == "{" else "unterminated string", opened)
    if text[start:].strip():
        chunks.append(_chunk(text[start:], None, start_line, True))
    return chunks
