"""Word rules: 1.1, 1.14, 9.3, and C-5 slang."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..model import Finding, Segment, SegmentKind
from .context import Context, applies_to, around, covers_rules, finding

#: British spellings and their American forms. Rule 1.14 requires American
#: spelling. The suffix patterns below catch the productive cases; this list
#: covers the words where the change is not a suffix rule.
_SPELLING = {
    "aeroplane": "airplane",
    "aluminium": "aluminum",
    "analogue": "analog",
    "artefact": "artifact",
    "axe": "ax",
    "behaviour": "behavior",
    "cancelled": "canceled",
    "cancelling": "canceling",
    "catalogue": "catalog",
    "centre": "center",
    "cheque": "check",
    "colour": "color",
    "defence": "defense",
    "dialogue": "dialog",
    "draught": "draft",
    "enquire": "inquire",
    "enquiry": "inquiry",
    "favour": "favor",
    "fibre": "fiber",
    "fulfil": "fulfill",
    "grey": "gray",
    "honour": "honor",
    "labelled": "labeled",
    "labelling": "labeling",
    "labour": "labor",
    "licence": "license",
    "litre": "liter",
    "manoeuvre": "maneuver",
    "metre": "meter",
    "modelled": "modeled",
    "modelling": "modeling",
    "mould": "mold",
    "neighbour": "neighbor",
    "offence": "offense",
    "practise": "practice",
    "programme": "program",
    "pretence": "pretense",
    "signalled": "signaled",
    "signalling": "signaling",
    "skilful": "skillful",
    "sulphur": "sulfur",
    "travelled": "traveled",
    "travelling": "traveling",
    "tyre": "tire",
    "whilst": "while",
    "amongst": "among",
}

#: Suffix patterns for the productive British spellings.
_SPELLING_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(\w{3,})isation\b", re.IGNORECASE), r"\1ization"),
    (re.compile(r"\b(\w{3,})isations\b", re.IGNORECASE), r"\1izations"),
    (re.compile(r"\b(\w{3,})ise\b", re.IGNORECASE), r"\1ize"),
    (re.compile(r"\b(\w{3,})ised\b", re.IGNORECASE), r"\1ized"),
    (re.compile(r"\b(\w{3,})ises\b", re.IGNORECASE), r"\1izes"),
    (re.compile(r"\b(\w{3,})ising\b", re.IGNORECASE), r"\1izing"),
    (re.compile(r"\b(\w{3,})yse\b", re.IGNORECASE), r"\1yze"),
    (re.compile(r"\b(\w{3,})ysed\b", re.IGNORECASE), r"\1yzed"),
    (re.compile(r"\b(\w{3,})ysing\b", re.IGNORECASE), r"\1yzing"),
)

#: Words that end in "-ise" or "-yse" in American English too.
_SPELLING_EXCEPTIONS = {
    "advertise",
    "advise",
    "arise",
    "chastise",
    "compromise",
    "comprise",
    "concise",
    "despise",
    "devise",
    "disguise",
    "enterprise",
    "excise",
    "exercise",
    "franchise",
    "improvise",
    "incise",
    "merchandise",
    "otherwise",
    "precise",
    "premise",
    "promise",
    "raise",
    "revise",
    "rise",
    "supervise",
    "surmise",
    "surprise",
    "televise",
    "wise",
    "analyse",
    "paralyse",
}

#: C-5 forbids regional, slang, and jargon words. These are the ones that
#: show up in code comments.
_JARGON = {
    "janky": "unreliable",
    "hacky": "temporary",
    "sketchy": "unreliable",
    "wonky": "incorrect",
    "gnarly": "complex",
    "hairy": "complex",
    "magic": "automatic",
    "magical": "automatic",
    "gotcha": "risk",
    "footgun": "risk",
    "cruft": "unused code",
    "bikeshed": "argue about detail",
    "nuke": "delete",
    "blow up": "fail",
    "barf": "fail",
    "bail": "stop",
    "kludge": "temporary solution",
    "gross": "complex",
    "nasty": "complex",
    "smart": "automatic",
    "clever": "complex",
    "dumb": "simple",
    "sane": "correct",
    "insane": "incorrect",
    "crazy": "unexpected",
    "spin up": "start",
    "tear down": "stop",
    "under the hood": "internally",
    "yak shaving": "unrelated work",
    "grok": "understand",
}

#: Rule 9.3 forbids phrasal verbs. Each maps to a single-word replacement.
_PHRASAL_VERBS = {
    "set up": "prepare",
    "sets up": "prepares",
    "setting up": "preparation",
    "turn on": "start",
    "turn off": "stop",
    "shut down": "stop",
    "carry out": "do",
    "carries out": "does",
    "carried out": "did",
    "find out": "find",
    "look up": "find",
    "look for": "find",
    "check out": "examine",
    "figure out": "find",
    "work out": "calculate",
    "make up": "form",
    "put off": "delay",
    "put together": "assemble",
    "take out": "remove",
    "take off": "remove",
    "take up": "use",
    "throw away": "discard",
    "hold on": "wait",
    "give up": "stop",
    "come back": "return",
    "go back": "return",
    "fill in": "complete",
    "point out": "show",
    "bring about": "cause",
    "cut off": "disconnect",
    "back up": "copy",
    "roll back": "revert",
    "roll out": "release",
    "get rid of": "remove",
    "end up": "become",
}

_LATIN = {
    "e.g.": "for example",
    "i.e.": "that is",
    "etc.": "and so on",
    "viz.": "namely",
    "cf.": "compare",
    "vs.": "compared to",
    "et al.": "and others",
    "n.b.": "note",
    "ad hoc": "unplanned",
    "per se": "by itself",
    "via": "by",
}

#: C-5 words that are also plain technical English in fixed compounds.
#: "gross" is slang when it describes code and standard finance vocabulary
#: before a noun like "revenue" or "margin". A term here is not reported when
#: the word after it matches its pattern.
_JARGON_COMPOUNDS = {
    "gross": re.compile(
        r"\s+(?:revenue|margin|profit|income|sales|merchandise|value|weight|"
        r"amount|total|earnings|receipts|pay|salary|domestic)\b"
    ),
}

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


@covers_rules("1.14")
def check_spelling(segment: Segment, context: Context) -> Iterator[Finding]:
    """Rule 1.14: use American English spelling."""
    seen: set[tuple[int, str]] = set()

    for match in _WORD.finditer(segment.text):
        word = match.group(0)
        american = _SPELLING.get(word.lower())
        if american and (match.start(), word.lower()) not in seen:
            seen.add((match.start(), word.lower()))
            yield finding(
                segment,
                context,
                "1.14",
                f'"{word}" is British spelling.',
                offset=match.start(),
                excerpt=around(segment.text, match.start(), match.end()),
                suggestion=f'Write "{_match_case(word, american)}".',
            )

    for pattern, replacement in _SPELLING_PATTERNS:
        for match in pattern.finditer(segment.text):
            word = match.group(0)
            if word.lower() in _SPELLING_EXCEPTIONS or word.lower() in _SPELLING:
                continue
            if (match.start(), word.lower()) in seen:
                continue
            seen.add((match.start(), word.lower()))
            american = pattern.sub(replacement, word)
            yield finding(
                segment,
                context,
                "1.14",
                f'"{word}" is British spelling.',
                offset=match.start(),
                excerpt=around(segment.text, match.start(), match.end()),
                suggestion=f'Write "{american}".',
            )


@covers_rules("1.1")
@applies_to(
    SegmentKind.COMMENT,
    SegmentKind.DOCSTRING,
    SegmentKind.MARKDOWN,
    SegmentKind.PR_DESCRIPTION,
    SegmentKind.STRING,
    SegmentKind.COMMIT,
)
def check_unapproved_words(segment: Segment, context: Context) -> Iterator[Finding]:
    """Rule 1.1: use a word the dictionary approves.

    Two levels of strictness. The words the dictionary explicitly rejects are
    always reported, with the approved alternative. Words that are simply absent
    from the dictionary are reported only when the full dictionary is loaded,
    because the starter list cannot tell absence from ignorance.
    """
    dictionary = context.dictionary
    reported: set[str] = set()

    for match in _WORD.finditer(segment.text):
        word = match.group(0)
        lowered = word.lower()
        if lowered in reported or len(lowered) < 3:
            continue

        alternatives = dictionary.alternatives_for(lowered)
        if alternatives:
            reported.add(lowered)
            suggestion = ", ".join(a.split(" (")[0] for a in alternatives[:3])
            yield finding(
                segment,
                context,
                "1.1",
                f'"{word}" is not an approved word.',
                offset=match.start(),
                excerpt=around(segment.text, match.start(), match.end()),
                suggestion=f"Use {suggestion}.",
            )


@covers_rules("C-5")
def check_jargon(segment: Segment, context: Context) -> Iterator[Finding]:
    """C-5: do not use regional, slang, or jargon words."""
    lowered = segment.text.lower()
    for term, replacement in _JARGON.items():
        compound = _JARGON_COMPOUNDS.get(term)
        for match in re.finditer(rf"\b{re.escape(term)}\b", lowered):
            if compound and compound.match(lowered, match.end()):
                continue
            yield finding(
                segment,
                context,
                "C-5",
                f'"{term}" is slang or jargon.',
                offset=match.start(),
                excerpt=around(segment.text, match.start(), match.end()),
                suggestion=f'Use "{replacement}".',
            )


@covers_rules("9.3")
def check_phrasal_verbs(segment: Segment, context: Context) -> Iterator[Finding]:
    """Rule 9.3: do not make phrasal verbs."""
    lowered = segment.text.lower()
    for phrase, replacement in _PHRASAL_VERBS.items():
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", lowered):
            yield finding(
                segment,
                context,
                "9.3",
                f'"{phrase}" is a phrasal verb.',
                offset=match.start(),
                excerpt=around(segment.text, match.start(), match.end()),
                suggestion=f'Use "{replacement}".',
            )


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement.capitalize()
    return replacement


CHECKS = [check_spelling, check_unapproved_words, check_jargon, check_phrasal_verbs]
LATIN_ABBREVIATIONS = _LATIN
