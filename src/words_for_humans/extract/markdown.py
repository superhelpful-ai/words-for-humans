"""Pull prose out of Markdown documents.

Code fences, tables, link targets, and front matter are removed first. What
remains is split into blocks so that rule 6.6, which limits a paragraph to six
sentences, has real paragraphs to count.
"""

from __future__ import annotations

import re

from ..model import Register, Segment, SegmentKind
from ..text import strip_code

_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_BADGE_ONLY = re.compile(r"^\s*(?:!?\[[^\]]*\]\([^)]*\)\s*)+$")


def extract(path: str, source: str) -> list[Segment]:
    text = _FRONT_MATTER.sub("", source)
    offset_lines = source.count("\n", 0, len(source) - len(text))
    lines = strip_code(text).splitlines()

    segments: list[Segment] = []
    block: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal block
        if block:
            body = "\n".join(t for _, t in block).strip()
            if _is_prose(body):
                segments.append(
                    Segment(
                        path=path,
                        line=block[0][0],
                        kind=SegmentKind.MARKDOWN,
                        text=body,
                        line_offsets=tuple(n for n, _ in block),
                    )
                )
        block = []

    for index, raw in enumerate(lines):
        line_no = index + 1 + offset_lines
        stripped = raw.strip()

        if not stripped or _TABLE_ROW.match(raw) or _BADGE_ONLY.match(raw):
            flush()
            continue

        heading = _HEADING.match(raw)
        if heading:
            flush()
            title = heading.group(1).strip().rstrip("#").strip()
            if _is_prose(title):
                segments.append(
                    Segment(
                        path=path,
                        line=line_no,
                        kind=SegmentKind.MARKDOWN,
                        text=title,
                        line_offsets=(line_no,),
                    )
                )
            continue

        item = _LIST_ITEM.match(raw)
        if item:
            # Rule 8.4 treats a list entry as its own sentence, so each item is
            # measured on its own rather than folded into the paragraph.
            flush()
            body = item.group(1).strip()
            if _is_prose(body):
                segments.append(
                    Segment(
                        path=path,
                        line=line_no,
                        kind=SegmentKind.MARKDOWN,
                        text=body,
                        line_offsets=(line_no,),
                        register=Register.PROCEDURAL if body.endswith(":") else None,
                    )
                )
            continue

        block.append((line_no, stripped))

    flush()
    return segments


def _is_prose(text: str) -> bool:
    if len(text.strip()) < 12:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", text)
    return len(words) >= 3
