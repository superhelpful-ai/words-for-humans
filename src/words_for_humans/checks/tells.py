"""Text that is recognisably machine-written.

The `V-` family asks whether a comment carries information. This family asks a
different question: whether the prose has the shape that language models produce
regardless of instruction. Those shapes come from training, not from the prompt,
which is why asking an assistant to avoid them works only some of the time and a
check is worth having.

Each rule here is a closed set of phrases or a structural pattern, so it is
decided without a model. That is deliberate. Anything a regular expression can
settle should not cost an inference call, and the hits from these rules become
labelled examples for the classifier tier.

A tell is not automatically wrong. A human writes "comprehensive" sometimes.
These rules report a smell, and the profile decides whether a smell blocks.

words-for-humans: ignore A-2
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..model import Finding, Segment, SegmentKind
from .context import Context, applies_to, around, covers_rules, finding

#: A-1. "It is not just X, it is Y." A construction models reach for to sound
#: insightful. It states a thing by first stating what the thing is not.
_ANTITHESIS = re.compile(
    r"\b(?:is|are|was|were|it's|that's|this is)\s+not\s+"
    r"(?:just|only|merely|simply|about)\s+[^.,;]{3,60}[,;]?\s*"
    r"(?:it(?:'s| is)|they(?:'re| are)|this is|but(?: rather)?|rather)\b",
    re.IGNORECASE,
)

#: A-2. Adjectives that praise rather than describe. In technical prose they
#: assert a quality the reader cannot check and the code does not establish.
_MARKETING = {
    "blazing",
    "blazingly",
    "best-in-class",
    "bulletproof",
    "cutting-edge",
    "delightful",
    "effortless",
    "elegant",
    "elegantly",
    "world-class",
    "state-of-the-art",
    "seamless",
    "seamlessly",
    "robust",
    "powerful",
    "comprehensive",
    "intuitive",
    "battle-tested",
    "rock-solid",
    "lightning-fast",
    "first-class",
    "turnkey",
    "gracefully",
}

#: A-3. An announcement that a list of virtues follows.
_ENUMERATED_VIRTUES = re.compile(
    r"\b(?:several|multiple|a number of|the following|these|key|main|primary)\s+"
    r"(?:benefits|advantages|considerations|reasons|features|improvements|"
    r"characteristics|properties|caveats|takeaways)\b\s*[:.]",
    re.IGNORECASE,
)

#: A-4. Two hedges stacked, or a hedge on behaviour the code determines. The
#: last branch is the reflexive hedge a model opens with before it answers,
#: of the "no single right answer, but" form, which qualifies nothing.
_DOUBLE_HEDGE = re.compile(
    r"\b(?:might|may|could|should|can)\s+(?:potentially|possibly|perhaps|"
    r"sometimes|occasionally|generally|typically|usually|often)\b"
    r"|\b(?:typically|generally|usually)\s+(?:tends? to|would|might|may)\b"
    r"|\bit(?:'s| is)\s+(?:generally|usually|typically)\s+(?:recommended|advisable|"
    r"considered|best)\b"
    r"|\bthere(?:'s| is) no (?:one[- ]size[- ]fits[- ]all|single|one|single right|"
    r"one right|correct)\s+(?:answer|solution|approach|way)\b"
    r"|\bit depends,? but\b",
    re.IGNORECASE,
)

#: A-5. The comment admits the code is incomplete. These matter beyond style:
#: they usually mark something a reviewer must finish.
_UNFINISHED = re.compile(
    r"\b(?:"
    r"for (?:the sake of )?brevity"
    r"|in a real(?:-world)? (?:implementation|application|scenario|system)"
    r"|in production(?:,| you would| this would| you'd)"
    r"|this is a (?:simplified|basic|minimal|naive|placeholder|mock|dummy|toy)"
    r"|(?:simplified|placeholder) (?:for|implementation|version)"
    r"|left as an exercise"
    r"|(?:you (?:would|should|might) )?(?:want to |need to )?(?:add|implement|handle) "
    r"(?:proper |actual |real )(?:error handling|validation|logging|authentication)"
    r"|(?:omitted|skipped) for (?:brevity|clarity|simplicity)"
    r"|adjust as (?:needed|necessary|appropriate)"
    r"|replace (?:this |it )?with your"
    r")\b",
    re.IGNORECASE,
)

#: A-6. Decorative emoji. A pictograph in a heading is a styling choice models
#: apply by default and few teams ask for.
_EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f900-\U0001f9ff⬀-⯿]")

#: A-7. Credentials and hosts left where a real value belongs.
_PLACEHOLDER = re.compile(
    r"\b(?:"
    r"your[-_](?:api[-_]key|token|secret|password|username|domain|project)"
    r"|(?:api[-_]key|token|secret)[-_]here"
    r"|xxx+|<your[- _][^>]{2,30}>"
    r"|changeme|replace[-_]me"
    r")\b",
    re.IGNORECASE,
)

#: A-8. A comment on every step of code that already reads in order.
_STEP_NARRATION = re.compile(r"^\s*(?:step\s*)?\d+[.):]\s*\w", re.IGNORECASE | re.MULTILINE)

#: A-10. The em dash. A model reaches for it where a comma, colon, or full stop
#: is the plain choice. The en dash and the hyphen are left alone: they join
#: ranges and compounds, as in 10-20, and are not the tell.
_EM_DASH = re.compile("[\u2014\u2015]")

#: A-11. Two negated fragments in a row, the "Not a cache. Just a boundary."
#: cadence a model uses for emphasis. A person writes one of these; the pattern
#: is the pair.
_TRIAD = re.compile(
    r"\bnot\s+[^.?!\n]{1,50}[.?!]\s+"
    r"(?:not|no|just|only|it'?s|it is|rather)\s+[^.?!\n]{1,50}[.?!]",
    re.IGNORECASE,
)

#: A-12. A pleasantry before the first sentence of content. The phrase is
#: reported, not the punctuation that precedes it.
_THROAT_CLEARING = re.compile(
    r"(?:^|[.!?]\s+)"
    r"(great question|good question|excellent question|certainly|absolutely|"
    r"sure thing|of course|i'?d be (?:happy|glad) to(?: help)?|"
    r"i would be (?:happy|glad) to(?: help)?|happy to help)\b",
    re.IGNORECASE,
)

#: A-13. A closer that announces a summary rather than ending. Each requires the
#: trailing comma, so "overall latency" and "in short bursts" are left alone.
_SUMMARY_CLOSER = re.compile(
    r"(?:^|[.!?]\s+)"
    r"(in conclusion|in summary|to summari[sz]e|to sum up|all in all|"
    r"at the end of the day|in closing|in short|overall)\s*,",
    re.IGNORECASE,
)

#: A-14. Narration of the act of answering, in place of the answer.
_META_NARRATION = re.compile(
    r"\b(?:let'?s|let us|we'?ll)\s+(?:dive in|dive into|break (?:this|it) down|"
    r"take a look|get started|explore|unpack|jump in|walk through)\b"
    r"|\b(?:i'?ll|let me|i will|we'?ll)\s+walk you through\b"
    r"|\bwalk you through\b",
    re.IGNORECASE,
)

#: A-10 to A-14 read conversational prose, not user-facing strings or
#: identifiers, where the same phrase can be deliberate copy.
_PROSE_KINDS = (
    SegmentKind.COMMENT,
    SegmentKind.DOCSTRING,
    SegmentKind.MARKDOWN,
    SegmentKind.PR_DESCRIPTION,
)

_WORD_BOUNDARY_MARKETING = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(_MARKETING, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

#: Emoji are conventional in a few places, so only headings and comments are
#: checked. A commit subject with a gitmoji prefix is a team convention.
_EMOJI_KINDS = (
    SegmentKind.COMMENT,
    SegmentKind.DOCSTRING,
    SegmentKind.MARKDOWN,
    SegmentKind.PR_DESCRIPTION,
)


def _flat(text: str) -> str:
    """Collapse whitespace so a quoted match stays on one line in the report."""
    return re.sub(r"\s+", " ", text).strip()


@covers_rules("A-1")
def check_antithesis(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-1: stating what a thing is not, before stating what it is."""
    for match in _ANTITHESIS.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-1",
            f'"{_flat(match.group(0))}" defines by negation.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="State what it is. Drop what it is not.",
        )


@covers_rules("A-2")
def check_marketing_language(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-2: an adjective that praises instead of describing."""
    for match in _WORD_BOUNDARY_MARKETING.finditer(segment.text):
        word = match.group(0)
        yield finding(
            segment,
            context,
            "A-2",
            f'"{word}" asserts quality rather than describing behaviour.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Say what it does, or what it measures.",
        )


@covers_rules("A-3")
@applies_to(
    SegmentKind.COMMENT, SegmentKind.DOCSTRING, SegmentKind.MARKDOWN, SegmentKind.PR_DESCRIPTION
)
def check_enumerated_virtues(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-3: an announced list of benefits."""
    for match in _ENUMERATED_VIRTUES.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-3",
            f'"{_flat(match.group(0))}" announces a list instead of giving it.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Delete the announcement and keep the list.",
        )


@covers_rules("A-4")
def check_double_hedge(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-4: two hedges where the code has one behaviour."""
    for match in _DOUBLE_HEDGE.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-4",
            f'"{_flat(match.group(0))}" hedges twice.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="State what the code does, or name the condition.",
        )


@covers_rules("A-5")
def check_unfinished(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-5: the comment says the code is not finished.

    This is the one rule in the family that is about correctness rather than
    prose. Text like "in a real implementation you would validate this" is a
    reviewer's problem, not a style preference, and it reaches production
    because it reads like documentation.

    words-for-humans: ignore A-5
    """
    for match in _UNFINISHED.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-5",
            f'"{_flat(match.group(0))}" says the code is incomplete.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Finish the code, or record the gap as a tracked task.",
        )


@covers_rules("A-6")
@applies_to(*_EMOJI_KINDS)
def check_decorative_emoji(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-6: pictographs used as decoration."""
    match = _EMOJI.search(segment.text)
    if match:
        yield finding(
            segment,
            context,
            "A-6",
            "Decorative emoji in technical text.",
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Remove it, or keep it only where your team has agreed to.",
        )


@covers_rules("A-7")
def check_placeholder(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-7: a placeholder credential or host left in place."""
    for match in _PLACEHOLDER.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-7",
            f'"{match.group(0)}" is a placeholder value.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Replace it, or point at where the real value comes from.",
        )


@covers_rules("A-8")
@applies_to(SegmentKind.COMMENT, SegmentKind.DOCSTRING)
def check_step_narration(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-8: a numbered commentary on code that already reads in order.

    One numbered line is a list. Three or more consecutive ones above short
    code is a narration of what the reader can see.
    """
    steps = list(_STEP_NARRATION.finditer(segment.text))
    if len(steps) < 3:
        return
    yield finding(
        segment,
        context,
        "A-8",
        f"This comment narrates {len(steps)} numbered steps.",
        offset=steps[0].start(),
        excerpt=segment.text,
        suggestion="Keep the steps that are not obvious from the code below.",
    )


@covers_rules("A-10")
@applies_to(*_PROSE_KINDS)
def check_em_dash(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-10: an em dash where plain punctuation belongs."""
    for match in _EM_DASH.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-10",
            "An em dash.",
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Use a comma, colon, or full stop.",
        )


@covers_rules("A-11")
@applies_to(*_PROSE_KINDS)
def check_triad(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-11: negated fragments stacked for rhythm."""
    for match in _TRIAD.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-11",
            f'"{_flat(match.group(0))}" stacks fragments for rhythm.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Write one plain sentence that states the thing.",
        )


@covers_rules("A-12")
@applies_to(*_PROSE_KINDS)
def check_throat_clearing(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-12: a pleasantry before the first sentence of content."""
    for match in _THROAT_CLEARING.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-12",
            f'"{_flat(match.group(1))}" clears the throat before the content.',
            offset=match.start(1),
            excerpt=around(segment.text, match.start(1), match.end(1)),
            suggestion="Delete it and start with the answer.",
        )


@covers_rules("A-13")
@applies_to(*_PROSE_KINDS)
def check_summary_closer(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-13: a closer that announces a summary rather than ending."""
    for match in _SUMMARY_CLOSER.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-13",
            f'"{_flat(match.group(1))}" announces a summary.',
            offset=match.start(1),
            excerpt=around(segment.text, match.start(1), match.end(1)),
            suggestion="Stop when the point is made, or state the point directly.",
        )


@covers_rules("A-14")
@applies_to(*_PROSE_KINDS)
def check_meta_narration(segment: Segment, context: Context) -> Iterator[Finding]:
    """A-14: narration of the act of answering, in place of the answer."""
    for match in _META_NARRATION.finditer(segment.text):
        yield finding(
            segment,
            context,
            "A-14",
            f'"{_flat(match.group(0))}" narrates instead of stating.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Cut the preamble and give the content.",
        )


CHECKS = [
    check_antithesis,
    check_marketing_language,
    check_enumerated_virtues,
    check_double_hedge,
    check_unfinished,
    check_decorative_emoji,
    check_placeholder,
    check_step_narration,
    check_em_dash,
    check_triad,
    check_throat_clearing,
    check_summary_closer,
    check_meta_narration,
]
