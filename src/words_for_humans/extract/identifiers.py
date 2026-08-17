"""Pull declared identifiers out of source files and split them into words.

ASD-STE100 was written for maintenance documentation, not for code, and it has
no rule about naming. Only the rules that survive the move to an identifier are
applied here: spelling, jargon, and the multi-word noun limit. Every finding on
an identifier is reported as soft, because the specification does not govern
this text and a failing build over a variable name is not defensible.
"""

from __future__ import annotations

import re

from ..model import Segment, SegmentKind

_DECLARATION = re.compile(
    r"""(?x)
    \b(?:
        (?:function|class|interface|type|enum|struct|trait|impl)\s+(?P<a>[A-Za-z_]\w*)
      | (?:const|let|var)\s+(?P<b>[A-Za-z_]\w*)\s*[:=]
      | (?:def|async\s+def)\s+(?P<c>[A-Za-z_]\w*)
      | (?:func)\s+(?P<d>[A-Za-z_]\w*)
      | (?:fn)\s+(?P<e>[A-Za-z_]\w*)
    )
    """
)

_SPLIT = re.compile(r"[_\-]+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def extract(path: str, source: str) -> list[Segment]:
    seen: set[str] = set()
    segments: list[Segment] = []
    for match in _DECLARATION.finditer(source):
        name = next((g for g in match.groups() if g), None)
        if not name or name in seen:
            continue
        seen.add(name)
        words = split_identifier(name)
        if len(words) < 2:
            continue
        line = source.count("\n", 0, match.start()) + 1
        segments.append(
            Segment(
                path=path,
                line=line,
                kind=SegmentKind.IDENTIFIER,
                text=" ".join(words),
                line_offsets=(line,),
            )
        )
    return segments


def split_identifier(name: str) -> list[str]:
    parts = [p for p in _SPLIT.split(name) if p]
    return [p.lower() for p in parts if p.isalpha()]
