"""Pull comments and docstrings out of source files.

A regular expression over a whole file finds comment markers inside string
literals as well as real comments, so this scans character by character and
tracks whether it is inside a string. That is the difference between reporting
on a URL in a config string and reporting on an actual comment.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from ..model import Segment, SegmentKind


@dataclass(frozen=True)
class LanguageSpec:
    line_comments: tuple[str, ...]
    block_comments: tuple[tuple[str, str], ...] = ()
    quotes: tuple[str, ...] = ('"', "'")
    triple_quotes: bool = False
    line_continuation_escape: bool = True


C_LIKE = LanguageSpec(line_comments=("//",), block_comments=(("/*", "*/"),), quotes=('"', "'", "`"))
HASH = LanguageSpec(line_comments=("#",))
PYTHON = LanguageSpec(line_comments=("#",), triple_quotes=True)
SQL = LanguageSpec(line_comments=("--",), block_comments=(("/*", "*/"),))
XML_LIKE = LanguageSpec(line_comments=(), block_comments=(("<!--", "-->"),))
LUA = LanguageSpec(line_comments=("--",), block_comments=(("--[[", "]]"),))

_BY_EXTENSION: dict[str, LanguageSpec] = {
    ".c": C_LIKE,
    ".h": C_LIKE,
    ".cpp": C_LIKE,
    ".cc": C_LIKE,
    ".hpp": C_LIKE,
    ".cs": C_LIKE,
    ".java": C_LIKE,
    ".kt": C_LIKE,
    ".kts": C_LIKE,
    ".scala": C_LIKE,
    ".js": C_LIKE,
    ".jsx": C_LIKE,
    ".mjs": C_LIKE,
    ".cjs": C_LIKE,
    ".ts": C_LIKE,
    ".tsx": C_LIKE,
    ".mts": C_LIKE,
    ".cts": C_LIKE,
    ".go": C_LIKE,
    ".rs": C_LIKE,
    ".swift": C_LIKE,
    ".dart": C_LIKE,
    ".php": C_LIKE,
    ".proto": C_LIKE,
    ".gradle": C_LIKE,
    ".groovy": C_LIKE,
    ".css": LanguageSpec(line_comments=(), block_comments=(("/*", "*/"),)),
    ".scss": C_LIKE,
    ".less": C_LIKE,
    ".py": PYTHON,
    ".pyi": PYTHON,
    ".rb": HASH,
    ".sh": HASH,
    ".bash": HASH,
    ".zsh": HASH,
    ".fish": HASH,
    ".yaml": HASH,
    ".yml": HASH,
    ".toml": HASH,
    ".tf": HASH,
    ".tfvars": HASH,
    ".pl": HASH,
    ".r": HASH,
    ".ex": HASH,
    ".exs": HASH,
    ".jl": HASH,
    ".sql": SQL,
    ".html": XML_LIKE,
    ".htm": XML_LIKE,
    ".xml": XML_LIKE,
    ".svg": XML_LIKE,
    ".vue": XML_LIKE,
    ".svelte": XML_LIKE,
    ".lua": LUA,
}

_BY_FILENAME: dict[str, LanguageSpec] = {
    "Dockerfile": HASH,
    "Makefile": HASH,
    "Jenkinsfile": C_LIKE,
    ".gitignore": HASH,
    ".dockerignore": HASH,
}

#: Comment markers that carry instructions to tools, not prose for a reader.
_DIRECTIVE = re.compile(
    r"^\s*(?:@ts-|eslint|prettier|noqa|type:\s*ignore|pylint|mypy|ruff|flake8|"
    r"pragma|nolint|codegen|istanbul|c8|v8|biome-|oxlint|sourceMappingURL|"
    r"#!|/\s*<reference|region\b|endregion\b|fmt:\s*(on|off)|checkov:|tflint-)",
    re.IGNORECASE,
)

#: Tag comments that are deliberately terse notes to other developers.
_TASK_TAG = re.compile(
    r"^\s*(TODO|FIXME|XXX|HACK|NOTE|WARNING|BUG|DEPRECATED)\b[:(]?", re.IGNORECASE
)

_JSDOC_TAG = re.compile(r"^\s*@\w+")


def spec_for(path: str) -> LanguageSpec | None:
    from pathlib import Path

    p = Path(path)
    if p.name in _BY_FILENAME:
        return _BY_FILENAME[p.name]
    return _BY_EXTENSION.get(p.suffix.lower())


def extract(path: str, source: str, *, keep_task_tags: bool = False) -> list[Segment]:
    spec = spec_for(path)
    if spec is None:
        return []
    segments = list(_scan(path, source, spec, keep_task_tags=keep_task_tags))
    if spec is PYTHON:
        segments.extend(_python_docstrings(path, source))
    return segments


def _scan(path: str, source: str, spec: LanguageSpec, *, keep_task_tags: bool) -> list[Segment]:
    segments: list[Segment] = []
    index = 0
    line = 1
    length = len(source)
    pending: list[tuple[int, str]] = []
    source_lines = source.splitlines()

    def flush() -> None:
        """Emit consecutive line comments as one segment.

        A paragraph split across five `//` lines is one piece of prose. Checking
        each line alone would miss sentences that span them.
        """
        nonlocal pending
        if pending:
            block = _clean_line_comments([t for _, t in pending])
            if _is_prose(block, keep_task_tags):
                segments.append(
                    Segment(
                        path=path,
                        line=pending[0][0],
                        kind=SegmentKind.COMMENT,
                        text=block,
                        line_offsets=tuple(n for n, _ in pending),
                        follows_code=code_after(pending[-1][0]),
                    )
                )
        pending = []

    def code_after(last_line: int, count: int = 3) -> str:
        """Return the first few lines of source below a comment.

        Only the code the comment sits above can tell you whether the comment
        adds anything. Collection stops at the next comment, because the words
        in a neighbouring comment are not evidence that this one is redundant.
        """
        collected: list[str] = []
        for raw in source_lines[last_line : last_line + 12]:
            stripped = raw.strip()
            if not stripped:
                # A comment documents the block directly beneath it. A blank
                # line ends that block, and whatever follows is a separate
                # declaration this comment was not written about.
                break
            if any(stripped.startswith(token) for token in spec.line_comments if token):
                break
            if any(stripped.startswith(start) for start, _ in spec.block_comments):
                break
            collected.append(stripped)
            if len(collected) >= count:
                break
        return "\n".join(collected)

    while index < length:
        char = source[index]

        if char == "\n":
            line += 1
            index += 1
            continue

        matched_block = _match(source, index, [start for start, _ in spec.block_comments])
        if matched_block:
            end_token = dict(spec.block_comments)[matched_block]
            close = source.find(end_token, index + len(matched_block))
            close = length if close == -1 else close
            raw = source[index + len(matched_block) : close]
            flush()
            cleaned = _clean_block_comment(raw)
            if _is_prose(cleaned, keep_task_tags):
                closing_line = line + source.count("\n", index, close)
                segments.append(
                    Segment(
                        path=path,
                        line=line,
                        kind=SegmentKind.DOCSTRING if raw.startswith("*") else SegmentKind.COMMENT,
                        text=cleaned,
                        line_offsets=_offsets(line, cleaned),
                        follows_code=code_after(closing_line),
                    )
                )
            line += source.count("\n", index, close)
            index = close + len(end_token)
            continue

        matched_line = _match(source, index, list(spec.line_comments))
        if matched_line:
            end = source.find("\n", index)
            end = length if end == -1 else end
            pending.append((line, source[index + len(matched_line) : end]))
            index = end
            continue

        if spec.triple_quotes and _match(source, index, ['"""', "'''"]):
            token = source[index : index + 3]
            close = source.find(token, index + 3)
            close = length if close == -1 else close
            line += source.count("\n", index, close + 3)
            index = close + 3
            flush()
            continue

        if char in spec.quotes:
            index, line = _skip_string(source, index, line, char, spec)
            continue

        if not char.isspace():
            flush()
        index += 1

    flush()
    return segments


def _skip_string(
    source: str, index: int, line: int, quote: str, spec: LanguageSpec
) -> tuple[int, int]:
    index += 1
    length = len(source)
    while index < length:
        char = source[index]
        if spec.line_continuation_escape and char == "\\":
            index += 2
            continue
        if char == "\n":
            line += 1
            # An unterminated single-line string means the quote was apostrophe
            # or similar. Stop here so the scanner does not swallow the file.
            if quote != "`":
                return index, line
        if char == quote:
            return index + 1, line
        index += 1
    return index, line


def _match(source: str, index: int, tokens: list[str]) -> str | None:
    for token in sorted(tokens, key=len, reverse=True):
        if token and source.startswith(token, index):
            return token
    return None


def _offsets(start_line: int, text: str) -> tuple[int, ...]:
    return tuple(range(start_line, start_line + text.count("\n") + 1))


def _clean_line_comments(lines: list[str]) -> str:
    return "\n".join(line.strip().lstrip("/!").strip() for line in lines).strip()


def _clean_block_comment(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        lines.append(stripped)
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    kept = [line for line in lines if not _JSDOC_TAG.match(line) or len(line.split()) > 4]
    return "\n".join(kept).strip()


def _is_prose(text: str, keep_task_tags: bool) -> bool:
    """Decide whether a comment is English worth checking.

    Commented-out code, tool directives, dividers, and one-word notes are not
    prose. Reporting on them buries the findings that matter.
    """
    stripped = text.strip()
    if len(stripped) < 12:
        return False
    if _DIRECTIVE.match(stripped):
        return False
    if not keep_task_tags and _TASK_TAG.match(stripped):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", stripped)
    if len(words) < 3:
        return False
    if (
        len(stripped.replace(" ", ""))
        and sum(c.isalpha() or c.isspace() for c in stripped) / len(stripped) < 0.62
    ):
        return False
    if re.search(r"[;{}]\s*$", stripped) and "(" in stripped:
        return False
    return not re.match(r"^[-=*_#~+]{4,}$", stripped)


def _python_docstrings(path: str, source: str) -> list[Segment]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    segments: list[Segment] = []
    for node in ast.walk(tree):
        if not isinstance(
            tree_type := node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        doc = ast.get_docstring(tree_type, clean=True)
        if not doc or len(doc.strip()) < 12:
            continue
        body = getattr(tree_type, "body", [])
        if not body:
            continue
        line = getattr(body[0], "lineno", 1)
        segments.append(
            Segment(
                path=path,
                line=line,
                kind=SegmentKind.DOCSTRING,
                text=doc,
                line_offsets=_offsets(line, doc),
            )
        )
    return segments
