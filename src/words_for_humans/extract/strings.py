"""Pull out string literals that a person will read.

Most string literals in a codebase are keys, paths, or identifiers, and STE has
nothing to say about them. This looks only at literals in positions that reach a
human: log and error messages, CLI help, alerts, and JSX text nodes.
"""

from __future__ import annotations

import re

from ..model import Segment, SegmentKind

_CALL_SITES = re.compile(
    r"""(?x)
    (?:
        console\.(?:log|info|warn|error|debug)
      | (?:logger|log|logging)\.(?:info|warn|warning|error|debug|critical|exception|fatal)
      | print
      | raise\s+\w*(?:Error|Exception|Warning)
      | throw\s+new\s+\w*(?:Error|Exception)
      | new\s+\w*Error
      | \w*Error
      | warnings\.warn
      | click\.echo
      | typer\.echo
      | toast\.(?:success|error|info|warning)
      | alert
      | notify
      | t
    )
    \s*\(\s*
    (?P<quote>['"])(?P<body>(?:\\.|(?!(?P=quote)).){8,400})(?P=quote)
    """
)

_HELP_KWARG = re.compile(
    r"""(?x)
    (?:help|description|message|title|label|placeholder|hint|tooltip|summary|
       errorMessage|helperText)
    \s*[=:]\s*
    (?P<quote>['"])(?P<body>(?:\\.|(?!(?P=quote)).){8,400})(?P=quote)
    """
)

_JSX_TEXT = re.compile(r">(?P<body>[^<>{}\n]{12,300})<")

#: A literal that is really an identifier, path, format key, or template.
_NOT_PROSE = re.compile(r"^(?:[\w.\-/]+|https?://\S*|[A-Z_][A-Z0-9_]*|\s*[{%<].*)$|^[^A-Za-z]*$")


def extract(path: str, source: str) -> list[Segment]:
    from pathlib import Path

    suffix = Path(path).suffix.lower()
    patterns = [_CALL_SITES, _HELP_KWARG]
    if suffix in {".jsx", ".tsx", ".vue", ".svelte", ".html"}:
        patterns.append(_JSX_TEXT)

    seen: set[tuple[int, str]] = set()
    segments: list[Segment] = []
    for pattern in patterns:
        for match in pattern.finditer(source):
            body = match.group("body")
            if not _is_prose(body):
                continue
            line = source.count("\n", 0, match.start("body")) + 1
            key = (line, body)
            if key in seen:
                continue
            seen.add(key)
            segments.append(
                Segment(
                    path=path,
                    line=line,
                    kind=SegmentKind.STRING,
                    text=_normalise(body),
                    line_offsets=(line,),
                )
            )
    return segments


def _normalise(body: str) -> str:
    """Replace interpolations with a neutral token so they count as one word."""
    out = re.sub(r"\$\{[^}]*\}", "(value)", body)
    out = re.sub(r"\{[^}\s]*\}", "(value)", out)
    out = re.sub(r"%[sdifr]", "(value)", out)
    return out.replace("\\n", " ").replace("\\t", " ").strip()


def _is_prose(body: str) -> bool:
    text = body.strip()
    if len(text) < 12 or _NOT_PROSE.match(text):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", text)
    return len(words) >= 3 and " " in text
