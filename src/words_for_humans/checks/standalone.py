"""Text that cannot be understood with only the file in front of the reader.

The `S-` family asks whether the prose stands alone: no pull request, no
ticket, no meeting, no previous version of the code. The four pattern rules
here catch the lexical signals of context dependence. The judgment half of
the family (S-5 to S-7) asks questions about meaning, so it runs in the model
tier. docs/standalone-rules.md records the design.

Commit messages are exempt from S-1 and S-2 by construction: a commit message
is the record of the change, so narrating the change is its job.

Every rule here starts soft. Promotion to hard waits on corpus runs showing
the false-positive rate is near zero, the bar the A rules were held to.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..model import Finding, Segment, SegmentKind
from .context import Context, applies_to, around, covers_rules, finding

_PROSE_KINDS = (
    SegmentKind.COMMENT,
    SegmentKind.DOCSTRING,
    SegmentKind.MARKDOWN,
    SegmentKind.PR_DESCRIPTION,
)

#: S-1. Text that narrates its own revision history. Three exclusions come
#: from the corpus runs. "As requested" is out: on real code it reads "as the
#: caller requested" almost every time. "Call" is out of the meeting words:
#: "following the call to unshift()" is a function call. And a positional or
#: venue word after the phrase ("as discussed above", "per the discussion on
#: pgsql-hackers") marks a cross-reference or citation, not history.
_HISTORY = re.compile(
    r"\bas (?:discussed|agreed)\b(?! (?:in|on|at|with|above|below|earlier))"
    r"|\bper (?:the |our )(?:meeting|discussion|conversation|sync|standup)s?\b"
    r"(?! (?:above|below|on|at|in))"
    r"|\bfollowing (?:the |our )(?:meeting|discussion|conversation|sync|standup)s?\b"
    r"(?! (?:above|below|on|at|in))"
    r"|\bper (?:the )?(?:code[- ])?review(?:er)?s?\b"
    r"|\b(?:after|from|per) (?:the )?(?:code[- ])?review (?:feedback|comments?)\b"
    r"|\b(?:added|updated|changed|fixed|revised|renamed|moved|removed|split|extracted)\b"
    r"[^.;\n]{0,40}\b(?:per|after|following)\b[^.;\n]{0,30}"
    r"\b(?:feedback|review|discussion|meeting)\b"
    r"|\b(?:fixed|updated|added|changed) (?:in|after|per) (?:PR|pull request) ?#?\d+\b",
    re.IGNORECASE,
)

#: S-2. Text that describes the edit rather than the code. Held to a short,
#: high-precision list; the lookbehinds keep "is used to build" (a purpose)
#: apart from "used to be" (a previous version). Two guards come from the
#: corpus runs. "The old version of the data" names a runtime object, so a
#: following "of" exempts the phrase. "Removed the old index" can be what the
#: code does at runtime, so that branch anchors to the start of a sentence,
#: where it reads as edit narration.
_DIFF = re.compile(
    r"\bchanged (?:this|it|these|that) to\b"
    r"|\brenamed (?:this |it |the \w+ )?from\b"
    r"|(?:^|[.!?]\s+)removed the old\b"
    r"|\binstead of the (?:old|previous|original)\b"
    r"|\bthe old (?:implementation|version|approach|behaviou?r|logic|way)\b(?! of\b)"
    r"|(?<!\bis )(?<!\bare )(?<!\bwas )(?<!\bwere )(?<!\bbe )(?<!\bbeen )(?<!\bbeing )"
    r"\bused to (?:be|use|return|call|do|have|take|live)\b",
    re.IGNORECASE,
)

#: S-3. A segment that is nothing but a pointer. RFC references are exempt:
#: an RFC number names a stable definition, not a rotting ticket. So are
#: license URLs, which sit in legally required boilerplate. Markdown is
#: outside this rule entirely: a link list in a README is navigation, and a
#: bibliography is made of bare links on purpose.
_TICKET = r"(?:[A-Z][A-Z0-9]{1,9}-\d+|#\d+|(?:GH|PR)[- ]?#?\d+)"
_URL = r"https?://\S+"
_REFERENCE_ONLY = re.compile(
    rf"^\s*(?:(?:see(?: also)?|refs?|cf)[.:,]?\s+)?(?:{_TICKET}|{_URL})[.,]?\s*$",
    re.IGNORECASE,
)
_STABLE_STANDARD = re.compile(r"\b(?:RFC|PEP|ISO|IEEE)[- ]?\d+\b|/licenses?/", re.IGNORECASE)

#: S-4. Words that place the text relative to the moment of writing. This
#: rule reads documentation only. In a code comment, "currently" and "the
#: latest tuple" describe runtime state more often than writing time, and
#: the corpus runs put that ratio near even, which is not a rule. In
#: Markdown and a pull request description the words mean writing time.
#:
#: The first set decays on its own. "The legacy <thing>" passes when the same
#: segment carries a version or date to anchor it. "Eventually", "existing",
#: "new", and "latest" are deliberately absent: each names runtime state or a
#: technical term ("eventually consistent") too often to report.
_TIME_BARE = re.compile(
    r"\bas of (?:this writing|now|today)\b"
    r"|\bcurrently\b"
    r"|\bfor now\b"
    r"|\bcoming soon\b"
    r"|\bwill (?:\w+ )?soon\b",
    re.IGNORECASE,
)
_TIME_RELATIVE = re.compile(r"\bthe legacy \w+", re.IGNORECASE)
_TIME_ANCHOR = re.compile(r"\bv?\d+\.\d+|\bversion \d|\b(?:19|20)\d{2}\b", re.IGNORECASE)


@covers_rules("S-1")
@applies_to(*_PROSE_KINDS)
def check_history_narration(segment: Segment, context: Context) -> Iterator[Finding]:
    """S-1: state the current truth, not how the text came to be."""
    for match in _HISTORY.finditer(segment.text):
        yield finding(
            segment,
            context,
            "S-1",
            f'"{match.group(0)}" narrates how the text came to be.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion=(
                "State the reason the code or fact holds today. The history "
                "lives in version control."
            ),
        )


@covers_rules("S-2")
@applies_to(*_PROSE_KINDS)
def check_diff_comment(segment: Segment, context: Context) -> Iterator[Finding]:
    """S-2: comment the code, not the change that produced it."""
    for match in _DIFF.finditer(segment.text):
        yield finding(
            segment,
            context,
            "S-2",
            f'"{match.group(0)}" describes the edit, not the code.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion=(
                "Describe what the current code does and why, as if it had always been this way."
            ),
        )


@covers_rules("S-3")
@applies_to(SegmentKind.COMMENT, SegmentKind.DOCSTRING, SegmentKind.PR_DESCRIPTION)
def check_reference_as_explanation(segment: Segment, context: Context) -> Iterator[Finding]:
    """S-3: use a reference to add depth, never as the whole explanation."""
    text = segment.text.strip()
    if not _REFERENCE_ONLY.match(text) or _STABLE_STANDARD.search(text):
        return
    yield finding(
        segment,
        context,
        "S-3",
        "A reference is the whole text; the reader may not be able to follow it.",
        excerpt=text,
        suggestion=(
            "Say what the code does and why, then keep the reference as a pointer to more detail."
        ),
    )


@covers_rules("S-4")
@applies_to(SegmentKind.MARKDOWN, SegmentKind.PR_DESCRIPTION)
def check_time_anchor(segment: Segment, context: Context) -> Iterator[Finding]:
    """S-4: anchor time-relative words to a date or version."""
    for match in _TIME_BARE.finditer(segment.text):
        yield finding(
            segment,
            context,
            "S-4",
            f'"{match.group(0)}" is true only at the moment of writing.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Give a date or version, or state the fact without the time word.",
        )
    if _TIME_ANCHOR.search(segment.text):
        return
    for match in _TIME_RELATIVE.finditer(segment.text):
        yield finding(
            segment,
            context,
            "S-4",
            f'"{match.group(0)}" stops identifying anything once a newer one exists.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Name the thing, or anchor it to a version or date.",
        )


CHECKS = [
    check_history_narration,
    check_diff_comment,
    check_reference_as_explanation,
    check_time_anchor,
]
