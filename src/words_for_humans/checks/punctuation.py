"""Punctuation rule 8.1."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..model import Finding, Segment
from .context import Context, covers_rules, finding

_SEMICOLON = re.compile(r";")

#: A semicolon inside these is code or an entity reference, not punctuation.
_CODE_CONTEXT = re.compile(r"&\w+;|&#\d+;|[){\]]\s*;|;\s*$|^\s*;|:\s*\w+\s*;")


@covers_rules("8.1")
def check_semicolon(segment: Segment, context: Context) -> Iterator[Finding]:
    """Rule 8.1: use standard punctuation, but not the semicolon."""
    for match in _SEMICOLON.finditer(segment.text):
        line_start = segment.text.rfind("\n", 0, match.start()) + 1
        line_end = segment.text.find("\n", match.start())
        line = segment.text[line_start : line_end if line_end != -1 else len(segment.text)]
        if _CODE_CONTEXT.search(line):
            continue
        yield finding(
            segment,
            context,
            "8.1",
            "The semicolon is not permitted.",
            offset=match.start(),
            excerpt=line.strip(),
            suggestion="Write two sentences.",
        )


CHECKS = [check_semicolon]
