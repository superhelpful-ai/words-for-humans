"""Verb rules: 3.2, 3.4, 3.5, 3.7, and C-3 passive voice.

Section 3 allows six verb forms only: the infinitive, the imperative, the simple
present, the simple past, the simple future, and the past participle used as an
adjective. Everything else - continuous tenses, perfect tenses, passive voice,
gerunds, and auxiliary stacks - is outside the specification.

These checks match on word shape rather than parse the sentence. That is enough
for the common constructions and cheap enough to run on a whole repository, but
it means an occasional false positive, which is why the exclusion lists below
carry the weight they do.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..model import Finding, Segment
from .context import Context, around, covers_rules, finding

_BE = r"(?:is|are|was|were|be|been|being|am)"
_HAVE = r"(?:has|have|had)"
_MODAL = r"(?:will|would|shall|should|can|could|may|might|must)"
_ADVERB = r"(?:\s+\w+ly)?"

#: Past participles that do not end in "-ed".
_IRREGULAR_PARTICIPLES = {
    "been",
    "begun",
    "broken",
    "brought",
    "built",
    "bought",
    "caught",
    "chosen",
    "come",
    "cut",
    "done",
    "drawn",
    "driven",
    "eaten",
    "fallen",
    "felt",
    "found",
    "forgotten",
    "given",
    "gone",
    "got",
    "gotten",
    "held",
    "hidden",
    "hit",
    "kept",
    "known",
    "laid",
    "led",
    "left",
    "lost",
    "made",
    "meant",
    "met",
    "paid",
    "put",
    "read",
    "run",
    "said",
    "seen",
    "sent",
    "set",
    "shown",
    "shut",
    "sold",
    "spoken",
    "spent",
    "split",
    "stood",
    "taken",
    "taught",
    "thrown",
    "told",
    "understood",
    "won",
    "withdrawn",
    "written",
}

#: Words ending in "-ed" that describe a state rather than report an action.
#: Rule 3.3 permits the past participle as an adjective, so these are not
#: passive voice and must not be reported as such.
_PREDICATE_ADJECTIVES = {
    "advanced",
    "aligned",
    "allowed",
    "applied",
    "based",
    "cached",
    "complicated",
    "connected",
    "dedicated",
    "defined",
    "deprecated",
    "detailed",
    "disabled",
    "distributed",
    "documented",
    "enabled",
    "encrypted",
    "expected",
    "exposed",
    "extended",
    "finished",
    "fixed",
    "focused",
    "gone",
    "guaranteed",
    "hosted",
    "implemented",
    "included",
    "installed",
    "intended",
    "interested",
    "involved",
    "isolated",
    "keyed",
    "limited",
    "linked",
    "loaded",
    "located",
    "managed",
    "mixed",
    "named",
    "needed",
    "nested",
    "ordered",
    "outdated",
    "owned",
    "populated",
    "prefixed",
    "prepared",
    "protected",
    "provided",
    "qualified",
    "related",
    "required",
    "reserved",
    "restricted",
    "scoped",
    "shared",
    "signed",
    "sorted",
    "specified",
    "supported",
    "suffixed",
    "trusted",
    "typed",
    "undefined",
    "unsigned",
    "unused",
    "used",
    "versioned",
}

#: Words ending in "-ing" that are ordinary nouns or adjectives, not gerunds.
#: Rule 3.5 permits the "-ing" form inside a technical noun.
_ING_NOUNS = {
    "accounting",
    "beginning",
    "billing",
    "building",
    "ceiling",
    "clothing",
    "coding",
    "engineering",
    "everything",
    "handling",
    "housing",
    "leading",
    "logging",
    "mapping",
    "marketing",
    "meaning",
    "meeting",
    "morning",
    "nothing",
    "opening",
    "packaging",
    "padding",
    "planning",
    "pricing",
    "processing",
    "rating",
    "reading",
    "recording",
    "reporting",
    "rounding",
    "routing",
    "sampling",
    "scheduling",
    "setting",
    "settings",
    "shipping",
    "something",
    "spacing",
    "staffing",
    "string",
    "testing",
    "thing",
    "things",
    "timing",
    "tracking",
    "training",
    "warning",
    "wiring",
    "working",
}

_PARTICIPLE = r"(?:\w+ed|" + "|".join(sorted(_IRREGULAR_PARTICIPLES)) + r")"

_PASSIVE = re.compile(rf"\b{_BE}{_ADVERB}\s+(?P<participle>{_PARTICIPLE})\b", re.IGNORECASE)
_CONTINUOUS = re.compile(rf"\b(?P<aux>{_BE}){_ADVERB}\s+(?P<verb>\w+ing)\b", re.IGNORECASE)
_PERFECT = re.compile(
    rf"\b(?P<aux>{_HAVE}){_ADVERB}\s+(?P<participle>{_PARTICIPLE})\b", re.IGNORECASE
)
_MODAL_PERFECT = re.compile(
    rf"\b(?P<aux>{_MODAL}\s+{_HAVE}(?:\s+been)?)\s+(?P<participle>{_PARTICIPLE})\b",
    re.IGNORECASE,
)
_AUX_STACK = re.compile(
    rf"\b(?P<aux>{_MODAL}\s+be\s+able\s+to|{_MODAL}\s+be\s+\w+ing)\b", re.IGNORECASE
)

_GERUND_AFTER_PREPOSITION = re.compile(
    r"\b(?:by|for|of|after|before|without|when|while|on|in|through|about|"
    r"instead\s+of|prior\s+to)\s+(?P<verb>\w+ing)\b",
    re.IGNORECASE,
)

_NOMINALISATION = re.compile(
    r"\b(?:do|does|did|perform|performs|performed|make|makes|made|carry\s+out|"
    r"carries\s+out|conduct|conducts|conducted|provide|provides|give|gives)\s+"
    r"(?:a|an|the)\s+(?P<noun>\w+(?:tion|sion|ment|ance|ence|al|ing))\b",
    re.IGNORECASE,
)


@covers_rules("C-3")
def check_passive_voice(segment: Segment, context: Context) -> Iterator[Finding]:
    """C-3: use the active voice.

    With the part-of-speech backend, only passive that names an agent worth
    promoting is reported ("returned by the function"); the idiomatic agentless
    passive of software prose ("the row is locked") is left alone. Without it,
    the pattern reports every passive it can match, minus a list of participles
    that are really adjectives.
    """
    if context.pos:
        yield from _pos_passive_voice(segment, context)
    else:
        yield from _regex_passive_voice(segment, context)


def _pos_passive_voice(segment: Segment, context: Context) -> Iterator[Finding]:
    from . import pos_backend

    for span in pos_backend.passive_by_agent(segment.text):
        yield finding(
            segment,
            context,
            "C-3",
            f'"{span.text}" is passive voice with a named agent.',
            offset=span.start,
            excerpt=span.text,
            suggestion="Name the agent and put it first.",
        )


def _regex_passive_voice(segment: Segment, context: Context) -> Iterator[Finding]:
    for match in _PASSIVE.finditer(segment.text):
        participle = match.group("participle").lower()
        if participle in _PREDICATE_ADJECTIVES:
            continue
        yield finding(
            segment,
            context,
            "C-3",
            f'"{match.group(0).strip()}" is passive voice.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Name the agent and put it first.",
        )


@covers_rules("3.2")
def check_verb_tense(segment: Segment, context: Context) -> Iterator[Finding]:
    """Rule 3.2: only simple tenses, the infinitive, and the imperative."""
    for match in _CONTINUOUS.finditer(segment.text):
        verb = match.group("verb").lower()
        if verb in _ING_NOUNS:
            continue
        yield finding(
            segment,
            context,
            "3.2",
            f'"{match.group(0).strip()}" is a continuous tense.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion=f'Use the simple present: "{_simple_present(verb)}".',
        )

    for pattern, label in ((_PERFECT, "a perfect tense"), (_MODAL_PERFECT, "a perfect tense")):
        for match in pattern.finditer(segment.text):
            yield finding(
                segment,
                context,
                "3.2",
                f'"{match.group(0).strip()}" is {label}.',
                offset=match.start(),
                excerpt=around(segment.text, match.start(), match.end()),
                suggestion="Use the simple past or the simple present.",
            )


@covers_rules("3.4")
def check_auxiliary_stack(segment: Segment, context: Context) -> Iterator[Finding]:
    """Rule 3.4: do not build complex verb constructions with auxiliaries."""
    for match in _AUX_STACK.finditer(segment.text):
        yield finding(
            segment,
            context,
            "3.4",
            f'"{match.group(0).strip()}" stacks auxiliary verbs.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Use one verb in a simple tense.",
        )


@covers_rules("3.5")
def check_gerund(segment: Segment, context: Context) -> Iterator[Finding]:
    """Rule 3.5: an "-ing" form is allowed only inside a technical noun."""
    for match in _GERUND_AFTER_PREPOSITION.finditer(segment.text):
        verb = match.group("verb").lower()
        if verb in _ING_NOUNS:
            continue
        yield finding(
            segment,
            context,
            "3.5",
            f'"{match.group(0).strip()}" uses an "-ing" form as a gerund.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Recast with a finite verb, or confirm this is a technical noun.",
        )


@covers_rules("3.7")
def check_nominalisation(segment: Segment, context: Context) -> Iterator[Finding]:
    """Rule 3.7: describe an action with a verb, not a noun."""
    for match in _NOMINALISATION.finditer(segment.text):
        yield finding(
            segment,
            context,
            "3.7",
            f'"{match.group(0).strip()}" hides the action in a noun.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Use the verb directly.",
        )


def _simple_present(verb_ing: str) -> str:
    stem = verb_ing[:-3]
    if not stem:
        return verb_ing
    if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
        stem = stem[:-1]
    elif stem.endswith(("at", "ut", "iz", "us", "iv", "ur", "ol", "id", "ag")):
        stem += "e"
    return stem


CHECKS = [
    check_passive_voice,
    check_verb_tense,
    check_auxiliary_stack,
    check_gerund,
    check_nominalisation,
]
