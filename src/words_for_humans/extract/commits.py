"""Pull commit messages from a git range.

The subject line and the body are separate segments. A subject is a title, and
rule 8.6 counts a title as one word inside a sentence, but as a standalone piece
of text it still has to read as English.
"""

from __future__ import annotations

import re
import subprocess

from ..model import Segment, SegmentKind

_RECORD = "\x1e"
_FIELD = "\x1f"

#: Conventional-commit prefix, stripped before the subject is checked.
_CONVENTIONAL = re.compile(r"^(\w+)(\([^)]*\))?!?:\s*")

#: Trailers and machine-generated lines that are not prose.
_TRAILER = re.compile(
    r"^\s*(?:[A-Z][\w-]+:\s|Co-Authored-By|Signed-off-by|Reviewed-by|Refs?|"
    r"Closes|Fixes|Resolves|https?://|\d+\.\s*https?://)",
    re.IGNORECASE,
)


def extract(rev_range: str, *, cwd: str | None = None) -> list[Segment]:
    try:
        result = subprocess.run(
            ["git", "log", f"--format={_RECORD}%H{_FIELD}%B", rev_range],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    segments: list[Segment] = []
    for record in result.stdout.split(_RECORD):
        if not record.strip():
            continue
        sha, _, message = record.partition(_FIELD)
        sha = sha.strip()[:12]
        lines = message.strip().splitlines()
        if not lines:
            continue

        subject = _CONVENTIONAL.sub("", lines[0]).strip()
        if len(subject.split()) >= 3:
            segments.append(
                Segment(
                    path=f"commit {sha}",
                    line=1,
                    kind=SegmentKind.COMMIT,
                    text=subject,
                    line_offsets=(1,),
                )
            )

        body = [line for line in lines[1:] if line.strip() and not _TRAILER.match(line)]
        if body:
            text = "\n".join(body).strip()
            if len(text.split()) >= 5:
                segments.append(
                    Segment(
                        path=f"commit {sha}",
                        line=2,
                        kind=SegmentKind.COMMIT,
                        text=text,
                        line_offsets=(2,),
                    )
                )
    return segments
