"""The multi-word noun rule, C-4.

C-4 limits a multi-word noun to three words, because in a longer string the
reader cannot tell which word modifies which. Finding these without a
part-of-speech tagger means looking for a run of words that carry no function
word and no verb, introduced by a determiner. "The runway light connection
resistance calibration" matches; "the pump that we installed today" does not,
because "that" and "we" break the run.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..model import Finding, Segment, SegmentKind
from ..rules import MAX_MULTI_WORD_NOUN
from .context import Context, applies_to, covers_rules, finding

_DETERMINER = {
    "the",
    "a",
    "an",
    "this",
    "that",
    "these",
    "those",
    "each",
    "every",
    "its",
    "their",
    "our",
    "your",
    "his",
    "her",
    "any",
    "no",
    "some",
}

#: Words that cannot sit inside a multi-word noun. A run that contains one of
#: these is a clause, not a noun.
_BREAKERS = {
    "and",
    "or",
    "but",
    "nor",
    "if",
    "then",
    "else",
    "when",
    "while",
    "because",
    "so",
    "as",
    "than",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "from",
    "by",
    "into",
    "onto",
    "over",
    "under",
    "after",
    "before",
    "during",
    "without",
    "within",
    "between",
    "through",
    "about",
    "against",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "am",
    "has",
    "have",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "can",
    "could",
    "may",
    "might",
    "must",
    "not",
    "it",
    "we",
    "you",
    "they",
    "he",
    "she",
    "i",
    "who",
    "which",
    "what",
    "there",
    "here",
    "also",
    "only",
    "very",
    "more",
    "most",
    "such",
    "both",
    "all",
    "many",
    "much",
    "few",
    "less",
    "least",
    "above",
    "below",
    "across",
    "along",
    "among",
    "around",
    "behind",
    "beside",
    "beyond",
    "despite",
    "except",
    "inside",
    "near",
    "off",
    "out",
    "outside",
    "past",
    "per",
    "since",
    "throughout",
    "toward",
    "towards",
    "underneath",
    "unlike",
    "until",
    "upon",
    "versus",
    "via",
    "plus",
    "minus",
    # Finite verbs. A run that contains one is a clause, not a noun.
    "accepts",
    "adds",
    "allows",
    "calls",
    "causes",
    "contains",
    "controls",
    "creates",
    "decides",
    "drives",
    "emits",
    "expects",
    "exposes",
    "feeds",
    "gets",
    "gives",
    "handles",
    "holds",
    "includes",
    "keeps",
    "lets",
    "lives",
    "makes",
    "maps",
    "means",
    "needs",
    "owns",
    "points",
    "prevents",
    "provides",
    "reads",
    "requires",
    "returns",
    "runs",
    "sends",
    "sets",
    "ships",
    "shows",
    "sits",
    "takes",
    "uses",
    "wraps",
    "writes",
    "works",
    # Adverbs, modals, and connectives that cannot sit inside a noun.
    "again",
    "alongside",
    "already",
    "always",
    "instead",
    "never",
    "often",
    "rather",
    "still",
    "together",
    "usually",
    "yet",
    "cannot",
    "therefore",
    "thus",
    "hence",
    "however",
    "otherwise",
    "meanwhile",
    "nonetheless",
    "nevertheless",
    "regardless",
    "consequently",
    "accordingly",
    "moreover",
    "furthermore",
    "likewise",
    "indeed",
    "perhaps",
    "hereby",
    "thereby",
    "whereby",
    "henceforth",
    "thereafter",
    "besides",
    "anyway",
    "somehow",
    "elsewhere",
}

#: Anything other than a space or a hyphen between two words ends the run. A
#: multi-word noun is one grammatical unit, so it cannot span a comma, a period,
#: a bracket, or a line break.
_RUN_SEPARATOR = re.compile(r"^[ \t]*-?[ \t]*$")

_WORD = re.compile(r"[A-Za-z][A-Za-z-]*")


@covers_rules("C-4")
@applies_to(
    SegmentKind.COMMENT,
    SegmentKind.DOCSTRING,
    SegmentKind.MARKDOWN,
    SegmentKind.PR_DESCRIPTION,
    SegmentKind.STRING,
)
def check_multi_word_noun(segment: Segment, context: Context) -> Iterator[Finding]:
    """C-4: write multi-word nouns of no more than three words.

    With the part-of-speech backend a cluster is a run of nominals ending in a
    head noun, so a verb or an adjective stack no longer counts as one. Without
    it, a determiner-anchored run of non-function words is the best a pattern can
    do, which over-reports on clauses and adjective stacks.
    """
    if context.pos:
        yield from _pos_multi_word_noun(segment, context)
    else:
        yield from _regex_multi_word_noun(segment, context)


def _pos_multi_word_noun(segment: Segment, context: Context) -> Iterator[Finding]:
    from . import pos_backend

    for span in pos_backend.noun_clusters(segment.text):
        yield finding(
            segment,
            context,
            "C-4",
            f'"{span.text}" is a multi-word noun of {span.length} words. The limit is '
            f"{MAX_MULTI_WORD_NOUN}.",
            offset=span.start,
            excerpt=span.text,
            suggestion="Shorten it, or hyphenate the words that act as one unit.",
        )


def _regex_multi_word_noun(segment: Segment, context: Context) -> Iterator[Finding]:
    tokens = [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(segment.text)]
    index = 0
    while index < len(tokens):
        word = tokens[index][0].lower()
        if word not in _DETERMINER:
            index += 1
            continue

        run: list[tuple[str, int, int]] = []
        cursor = index + 1
        previous_end = tokens[index][2]
        while cursor < len(tokens):
            candidate, start, end = tokens[cursor]
            lowered = candidate.lower()
            if not _RUN_SEPARATOR.match(segment.text[previous_end:start]):
                break
            if lowered in _BREAKERS or lowered in _DETERMINER or lowered.endswith("ly"):
                break
            run.append((candidate, start, end))
            previous_end = end
            cursor += 1

        if len(run) > MAX_MULTI_WORD_NOUN:
            phrase = " ".join(w for w, _, _ in run)
            yield finding(
                segment,
                context,
                "C-4",
                f'"{phrase}" is a multi-word noun of {len(run)} words. The limit is '
                f"{MAX_MULTI_WORD_NOUN}.",
                offset=run[0][1],
                excerpt=phrase,
                suggestion="Shorten it, or hyphenate the words that act as one unit.",
            )
        index = max(cursor, index + 1)


CHECKS = [check_multi_word_noun]
