"""General recommendations GR-1 through GR-8.

These sit after the 53 rules in Part 1. They are recommendations rather than
rules, so only the ones with a closed set of tokens are checked here.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..model import Finding, Segment, SegmentKind
from .context import Context, applies_to, around, covers_rules, finding
from .words import LATIN_ABBREVIATIONS

#: C-7. Each term maps to a neutral replacement.
_NON_INCLUSIVE = {
    "whitelist": "allowlist",
    "whitelists": "allowlists",
    "whitelisted": "allowed",
    "blacklist": "denylist",
    "blacklists": "denylists",
    "blacklisted": "denied",
    "master": "primary",
    "slave": "replica",
    "slaves": "replicas",
    "grandfathered": "exempt",
    "sanity check": "confidence check",
    "dummy": "placeholder",
    "man-hours": "person-hours",
    "manned": "staffed",
    "manpower": "workforce",
    "middleman": "intermediary",
    "he or she": "they",
    "his or her": "their",
    "chairman": "chair",
    "guys": "everyone",
}

#: GR-4. "this" that is not followed by the noun it refers to.
_BARE_THIS = re.compile(
    r"\bThis\s+(?=(?:is|was|are|were|will|would|can|could|should|means|makes|"
    r"gives|has|have|does|do|allows|causes|prevents|lets)\b)",
    re.IGNORECASE,
)

#: GR-8. A possessive apostrophe on a noun.
_POSSESSIVE = re.compile(r"\b([A-Za-z]{3,})'s\b")

#: Contractions that look like possessives. GR-8 does not cover these; rule 4.2
#: reports them instead.
_NOT_POSSESSIVE = {"it", "that", "there", "here", "what", "who", "he", "she", "let"}


@covers_rules("GR-6")
def check_latin_abbreviations(segment: Segment, context: Context) -> Iterator[Finding]:
    """GR-6: do not use Latin abbreviations."""
    lowered = segment.text.lower()
    for term, replacement in LATIN_ABBREVIATIONS.items():
        pattern = re.escape(term) if "." in term else rf"\b{re.escape(term)}\b"
        for match in re.finditer(pattern, lowered):
            yield finding(
                segment,
                context,
                "GR-6",
                f'"{term}" is a Latin abbreviation.',
                offset=match.start(),
                excerpt=around(segment.text, match.start(), match.end()),
                suggestion=f'Write "{replacement}".',
            )


@covers_rules("C-7")
def check_inclusive_language(segment: Segment, context: Context) -> Iterator[Finding]:
    """C-7: use inclusive language."""
    lowered = segment.text.lower()
    for term, replacement in _NON_INCLUSIVE.items():
        for match in re.finditer(rf"\b{re.escape(term)}\b", lowered):
            yield finding(
                segment,
                context,
                "C-7",
                f'"{term}" is not inclusive language.',
                offset=match.start(),
                excerpt=around(segment.text, match.start(), match.end()),
                suggestion=f'Use "{replacement}".',
            )


@covers_rules("GR-4")
@applies_to(
    SegmentKind.COMMENT, SegmentKind.DOCSTRING, SegmentKind.MARKDOWN, SegmentKind.PR_DESCRIPTION
)
def check_bare_this(segment: Segment, context: Context) -> Iterator[Finding]:
    """GR-4: do not use "this" without the noun it refers to."""
    for match in _BARE_THIS.finditer(segment.text):
        yield finding(
            segment,
            context,
            "GR-4",
            '"this" does not name what it refers to.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Put the noun after it.",
        )


@covers_rules("GR-8")
@applies_to(
    SegmentKind.COMMENT, SegmentKind.DOCSTRING, SegmentKind.MARKDOWN, SegmentKind.PR_DESCRIPTION
)
def check_possessive(segment: Segment, context: Context) -> Iterator[Finding]:
    """GR-8: avoid the possessive form."""
    for match in _POSSESSIVE.finditer(segment.text):
        noun = match.group(1)
        if noun.lower() in _NOT_POSSESSIVE:
            continue
        yield finding(
            segment,
            context,
            "GR-8",
            f'"{match.group(0)}" is a possessive form.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion=f'Write "of the {noun.lower()}".',
        )


CHECKS = [
    check_latin_abbreviations,
    check_inclusive_language,
    check_bare_this,
    check_possessive,
]
