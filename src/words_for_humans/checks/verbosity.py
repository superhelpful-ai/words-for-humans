"""Rules for comments that say nothing.

ASD-STE100 constrains how a sentence is built. It has nothing to say about
whether the sentence was worth writing, because it was published for people
documenting aircraft, who were not producing text at the rate a code assistant
does. These rules cover what the standard does not: prose that restates the
code, opens with filler, narrates itself, or pads a simple statement.

Rule identifiers in this family are prefixed `V-`. They are this tool's rules,
not ASD's, and the distinction is kept visible everywhere they are reported.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..model import Finding, Segment, SegmentKind
from .context import Context, applies_to, around, covers_rules, finding

#: Openers that carry no information. The sentence reads the same without them.
_FILLER_OPENERS = re.compile(
    r"(?:^|(?<=[.!?]\s))\s*(?P<phrase>"
    r"it(?:'s| is) (?:worth|important to) not(?:ing|e) that|"
    r"it should be noted that|"
    r"please note that|"
    r"note that|"
    r"keep in mind that|"
    r"as (?:you can see|mentioned (?:above|earlier|previously))|"
    r"in (?:essence|summary|short|other words|general|particular)|"
    r"simply put|"
    r"basically|"
    r"essentially|"
    r"fundamentally|"
    r"at (?:its|the) core|"
    r"generally speaking"
    r")\b[,:]?\s*",
    re.IGNORECASE,
)

#: First-person narration of a walkthrough. A comment is not a conversation
#: with the reader. The tell is future or procedural framing ("let's", "we'll",
#: "now we", "here we"), not a bare "we" stating a design fact ("We store the
#: result in a cache", "We pin the version"), which reads fine and is not
#: narration. Matching bare "we" was almost all false positives on real code.
_NARRATION = re.compile(
    r"(?:^|(?<=[.!?]\s))\s*(?P<phrase>"
    r"let(?:'s| us)\b|"
    r"we(?:'ll| will|(?:'re| are) going to)\b|"
    r"(?:first|next|then|finally|now),? we\b|"
    r"here we\b|"
    r"i(?:'ll| will|(?:'m| am) going to)\b"
    r")",
    re.IGNORECASE,
)

#: Openers that restate what any reader can see from the declaration below.
#:
#: The empty verb phrase is required, not optional. "This module records each
#: rule as metadata" names its subject and then says something; only "this
#: module is responsible for" spends words without adding any. The match is
#: anchored to the start of the comment for the same reason: the same words
#: mid-paragraph are usually carrying a real reference.
_OBVIOUS_OPENER = re.compile(
    r"^\s*(?P<phrase>"
    r"this (?:function|method|class|module|file|component|hook|script|variable|"
    r"constant|interface|type|helper|utility)\s+"
    r"(?:is (?:responsible for|used (?:to|for)|meant to|intended to)|"
    r"serves to|aims to|exists to|simply (?:does|handles|is))"
    r")",
    re.IGNORECASE,
)

#: Padding that has a shorter equivalent.
_PADDING = {
    "in order to": "to",
    "in order for": "for",
    "due to the fact that": "because",
    "owing to the fact that": "because",
    "for the purpose of": "for",
    "with the exception of": "except",
    "in the event that": "if",
    "at this point in time": "now",
    "a large number of": "many",
    "a small number of": "few",
    "the majority of": "most",
    "is able to": "can",
    "are able to": "can",
    "has the ability to": "can",
    "make use of": "use",
    "makes use of": "uses",
    "take into account": "consider",
    "takes into consideration": "considers",
    "in the process of": "",
    "it is possible that": "perhaps",
    "there is no need to": "do not",
    "serves as a": "is a",
    "acts as a": "is a",
    "provides the ability to": "lets you",
    "allows you to": "lets you",
}

#: A comment whose words are all present in the code beneath it is restating it.
_IDENTIFIER_SPLIT = re.compile(r"[_\-\W]+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

#: Words too common to prove a comment restates the code.
_WEAK = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "for",
    "in",
    "on",
    "at",
    "by",
    "with",
    "from",
    "and",
    "or",
    "is",
    "are",
    "be",
    "this",
    "that",
    "it",
    "its",
    "as",
    "if",
    "then",
    "we",
    "you",
    "will",
    "can",
    "do",
    "does",
    "not",
    "new",
    "get",
    "set",
    "value",
    "data",
    "return",
    "returns",
    "function",
    "method",
    "class",
}

#: Below this, there is not enough in the comment to judge it either way.
_MIN_WORDS_FOR_RESTATEMENT = 2

#: The share of a comment's content words that must already appear in the code
#: below before the comment counts as a restatement. Set high on purpose: a
#: comment that adds one real word is doing something, and a false positive here
#: deletes information.
_RESTATEMENT_THRESHOLD = 0.8


@covers_rules("V-1")
@applies_to(SegmentKind.COMMENT, SegmentKind.DOCSTRING)
def check_restates_code(segment: Segment, context: Context) -> Iterator[Finding]:
    """V-1: the comment repeats the declaration below it.

    A comment earns its place by saying something the code cannot: why the code
    is written this way, what breaks without it, what the caller must know. One
    that only renames the identifiers below it costs a reader time and gives
    nothing back.
    """
    if not segment.follows_code:
        return

    words = _content_words(segment.text)
    if len(words) < _MIN_WORDS_FOR_RESTATEMENT:
        return

    code_words = _content_words(segment.follows_code)
    if not code_words:
        return

    covered = words & code_words
    if len(covered) / len(words) < _RESTATEMENT_THRESHOLD:
        return

    yield finding(
        segment,
        context,
        "V-1",
        "This comment repeats the code below it and adds nothing.",
        excerpt=segment.text,
        suggestion="Delete it, or replace it with why the code is written this way.",
    )


def _content_words(text: str) -> set[str]:
    parts = [p.lower() for p in _IDENTIFIER_SPLIT.split(text) if p.isalpha()]
    return {p for p in parts if p not in _WEAK and len(p) > 2}


@covers_rules("V-2")
def check_filler_opener(segment: Segment, context: Context) -> Iterator[Finding]:
    """V-2: the sentence opens with a phrase that carries no information."""
    for match in _FILLER_OPENERS.finditer(segment.text):
        phrase = match.group("phrase").strip()
        yield finding(
            segment,
            context,
            "V-2",
            f'"{phrase}" adds nothing to the sentence.',
            offset=match.start("phrase"),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Delete it and start with the statement.",
        )


@covers_rules("V-3")
@applies_to(
    SegmentKind.COMMENT, SegmentKind.DOCSTRING, SegmentKind.MARKDOWN, SegmentKind.PR_DESCRIPTION
)
def check_narration(segment: Segment, context: Context) -> Iterator[Finding]:
    """V-3: the text narrates itself instead of stating the fact."""
    for match in _NARRATION.finditer(segment.text):
        phrase = match.group("phrase").strip()
        yield finding(
            segment,
            context,
            "V-3",
            f'"{phrase}" narrates rather than states.',
            offset=match.start("phrase"),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Write what the code does, not what you are about to do.",
        )


@covers_rules("V-4")
@applies_to(SegmentKind.COMMENT, SegmentKind.DOCSTRING)
def check_obvious_opener(segment: Segment, context: Context) -> Iterator[Finding]:
    """V-4: the comment opens by naming what the declaration already names."""
    for match in _OBVIOUS_OPENER.finditer(segment.text):
        phrase = match.group("phrase").strip()
        yield finding(
            segment,
            context,
            "V-4",
            f'"{phrase}" restates the declaration below.',
            offset=match.start("phrase"),
            excerpt=around(segment.text, match.start(), match.end()),
            suggestion="Start with the verb: what it does, or why it exists.",
        )


@covers_rules("V-5")
def check_padding(segment: Segment, context: Context) -> Iterator[Finding]:
    """V-5: a long phrase where a short one means the same."""
    lowered = segment.text.lower()
    for phrase, replacement in _PADDING.items():
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", lowered):
            suggestion = f'Write "{replacement}".' if replacement else "Delete it."
            yield finding(
                segment,
                context,
                "V-5",
                f'"{phrase}" is padding.',
                offset=match.start(),
                excerpt=around(segment.text, match.start(), match.end()),
                suggestion=suggestion,
            )


#: Parameter documentation in the three common styles.
_PARAM_DOC = re.compile(
    r"""(?x)
    ^\s*(?:
        :param\s+(?P<sphinx_name>\w+)\s*:\s*(?P<sphinx_desc>.+?)$
      | @param\s+(?:\{(?P<js_type>[^}]*)\}\s+)?(?P<js_name>[\w.\[\]]+)\s*
        (?:-\s*)?(?P<js_desc>.+?)$
      | (?P<google_name>\w+)\s*\((?P<google_type>[^)]*)\)\s*:\s*(?P<google_desc>.+?)$
    )
    """,
    re.MULTILINE,
)

#: Words a parameter description adds without saying anything.
_DESCRIPTION_FILLER = {
    "the",
    "a",
    "an",
    "of",
    "for",
    "to",
    "this",
    "that",
    "is",
    "are",
    "be",
    "will",
    "used",
    "use",
    "value",
    "values",
    "object",
    "instance",
    "optional",
    "required",
    "given",
    "provided",
    "specified",
    "input",
    "output",
    "param",
    "parameter",
    "argument",
    "should",
    "must",
    "can",
    "which",
    "it",
    "its",
    "and",
    "or",
    "with",
    "from",
    "in",
    "on",
    "as",
    "by",
    "if",
    "not",
    "any",
    "type",
    "string",
    "number",
    "boolean",
    "integer",
    "float",
    "list",
    "dict",
    "array",
    "true",
    "false",
    "none",
    "null",
}


@covers_rules("V-6")
@applies_to(SegmentKind.DOCSTRING, SegmentKind.COMMENT)
def check_param_restates_name(segment: Segment, context: Context) -> Iterator[Finding]:
    """V-6: the parameter description repeats the parameter name.

    ":param user_id: The user ID." documents nothing. The reader already has
    the name and the type from the signature. A description earns its line by
    giving the unit, the range, the default, or what happens when it is wrong.
    """
    for match in _PARAM_DOC.finditer(segment.text):
        groups = match.groupdict()
        name = groups["sphinx_name"] or groups["js_name"] or groups["google_name"]
        description = groups["sphinx_desc"] or groups["js_desc"] or groups["google_desc"]
        type_hint = groups["js_type"] or groups["google_type"] or ""
        if not name or not description:
            continue

        described = {
            word
            for word in re.split(r"[^A-Za-z]+", description.lower())
            if word and word not in _DESCRIPTION_FILLER
        }
        if not described:
            yield _param_finding(segment, context, match, name, description)
            continue

        # The name is split without the length filter that `_content_words`
        # applies. "id" and "ok" are too short to count as content in prose but
        # are exactly the tokens a parameter name is built from, and dropping
        # them lets ":param user_id: The user ID." through.
        known = {
            part.lower()
            for source in (name, type_hint)
            for part in _IDENTIFIER_SPLIT.split(source)
            if part.isalpha()
        }
        if described <= known:
            yield _param_finding(segment, context, match, name, description)


def _param_finding(segment, context, match, name: str, description: str) -> Finding:
    return finding(
        segment,
        context,
        "V-6",
        f'The description of "{name}" repeats its name.',
        offset=match.start(),
        excerpt=match.group(0).strip(),
        suggestion="Give the unit, the range, the default, or drop the line.",
    )


CHECKS = [
    check_restates_code,
    check_filler_opener,
    check_narration,
    check_obvious_opener,
    check_padding,
    check_param_restates_name,
]
