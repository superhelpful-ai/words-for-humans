"""The deterministic half of the validator.

Each check reads one segment and yields findings. A check only covers a rule the
tool can decide by inspection; the rules that need a reader who understands the
subject matter are left to the review skill.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..model import Finding, Segment
from . import (
    nouns,
    punctuation,
    recommendations,
    sentences,
    standalone,
    tells,
    verbosity,
    verbs,
    words,
)
from .context import Check, Context, finding

CHECKS: list[Check] = [
    *sentences.CHECKS,
    *verbs.CHECKS,
    *nouns.CHECKS,
    *words.CHECKS,
    *punctuation.CHECKS,
    *recommendations.CHECKS,
    *verbosity.CHECKS,
    *tells.CHECKS,
    *standalone.CHECKS,
]


def run(segment: Segment, context: Context) -> Iterator[Finding]:
    for check in CHECKS:
        if not context.covers(segment, check):
            continue
        yield from check(segment, context)


__all__ = ["CHECKS", "Check", "Context", "finding", "run"]
