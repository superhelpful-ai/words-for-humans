"""Sentence and paragraph rules: 4.2, 5.1, 6.3, 6.6."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..model import Finding, Register, Segment, SegmentKind
from ..rules import MAX_SENTENCES_PER_PARAGRAPH
from ..text import Sentence, split_paragraphs, split_sentences
from .context import Context, applies_to, around, covers_rules, finding

_CONTRACTIONS = re.compile(
    r"\b(?:can't|cannot|won't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't|"
    r"hasn't|haven't|hadn't|shouldn't|wouldn't|couldn't|mustn't|it's|that's|"
    r"there's|here's|what's|let's|we'll|we're|we've|you'll|you're|you've|"
    r"they'll|they're|they've|i'm|i've|i'll|he's|she's|who's)\b",
    re.IGNORECASE,
)

_CONTRACTION_EXPANSIONS = {
    "can't": "cannot",
    "cannot": "can not",
    "won't": "will not",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "hasn't": "has not",
    "haven't": "have not",
    "hadn't": "had not",
    "shouldn't": "should not",
    "wouldn't": "would not",
    "couldn't": "could not",
    "mustn't": "must not",
    "it's": "it is",
    "that's": "that is",
    "there's": "there is",
    "here's": "here is",
    "what's": "what is",
    "let's": "let us",
    "we'll": "we will",
    "we're": "we are",
    "we've": "we have",
    "you'll": "you will",
    "you're": "you are",
    "you've": "you have",
    "they'll": "they will",
    "they're": "they are",
    "they've": "they have",
    "he's": "he is",
    "she's": "she is",
    "who's": "who is",
}


def sentences_of(segment: Segment, context: Context) -> list[Sentence]:
    default = segment.register or Register.DESCRIPTIVE
    return split_sentences(segment.text, default=default)


@covers_rules("C-1")
def check_sentence_length(segment: Segment, context: Context) -> Iterator[Finding]:
    """C-1: sentence length.

    A sentence over the warn count is reported; one over the higher fail count
    fails the build. The counts come from the segment kind, so a comment is held
    tighter than a Markdown paragraph. The `ste` profile sets the two counts
    equal, at the specification limits of 20 words for an instruction and 25 for
    a description, so any sentence over the limit fails.

    Word counting follows rules 8.5 to 8.7, so a parenthesised aside, a quoted
    string, a number with its unit, and a hyphenated compound each count once.
    """
    for sentence in sentences_of(segment, context):
        count = sentence.word_count
        warn, fail = context.sentence_thresholds(segment.kind, sentence.register)
        if count <= warn:
            continue
        over_fail = count > fail
        kind = "instruction" if sentence.register is Register.PROCEDURAL else "sentence"
        limit = fail if over_fail else warn
        yield finding(
            segment,
            context,
            "C-1",
            f"This {kind} has {count} words. The limit is {limit}.",
            offset=sentence.offset,
            excerpt=sentence.text,
            suggestion=f"Split it into {1 + count // limit} shorter sentences.",
            severity=context.length_severity("C-1", segment, over_fail),
        )


@covers_rules("C-2")
@applies_to(
    SegmentKind.COMMENT, SegmentKind.DOCSTRING, SegmentKind.MARKDOWN, SegmentKind.PR_DESCRIPTION
)
def check_paragraph_length(segment: Segment, context: Context) -> Iterator[Finding]:
    """C-2: no more than six sentences in a paragraph."""
    for offset, paragraph in split_paragraphs(segment.text):
        count = len(split_sentences(paragraph))
        if count > MAX_SENTENCES_PER_PARAGRAPH:
            yield finding(
                segment,
                context,
                "C-2",
                f"This paragraph has {count} sentences. The limit is "
                f"{MAX_SENTENCES_PER_PARAGRAPH}.",
                offset=offset,
                excerpt=paragraph,
                suggestion="Break it into paragraphs of one topic each.",
            )


@covers_rules("4.2")
def check_contractions(segment: Segment, context: Context) -> Iterator[Finding]:
    """Rule 4.2: do not use contractions."""
    for match in _CONTRACTIONS.finditer(segment.text):
        word = match.group(0)
        expansion = _CONTRACTION_EXPANSIONS.get(word.lower())
        yield finding(
            segment,
            context,
            "4.2",
            f'"{word}" is a contraction.',
            offset=match.start(),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion=f'Write "{expansion}".' if expansion else None,
        )


CHECKS = [check_sentence_length, check_paragraph_length, check_contractions]
