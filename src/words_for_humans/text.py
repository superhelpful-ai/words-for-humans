"""Sentence segmentation and ASD-STE100 word counting.

Rules 8.4 through 8.7 define what counts as one word, and those definitions are
what make an STE word count differ from a naive split on whitespace. A
parenthesised aside counts as one word, so does quoted text, so does a number
with its unit, and so does a hyphenated compound. A sentence-length check that
ignores these reports lengths the specification would not recognise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model import Register

#: Abbreviations whose trailing period does not end a sentence.
_ABBREVIATIONS = {
    "e.g.",
    "i.e.",
    "etc.",
    "vs.",
    "cf.",
    "al.",
    "viz.",
    "resp.",
    "approx.",
    "fig.",
    "no.",
    "vol.",
    "ch.",
    "sec.",
    "eq.",
    "ref.",
    "min.",
    "max.",
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "st.",
    "inc.",
    "ltd.",
    "co.",
    "dept.",
}

#: Units of measurement. Rule 8.6 counts a number and its unit as one word.
_UNITS = {
    "m",
    "cm",
    "mm",
    "km",
    "in",
    "ft",
    "yd",
    "mi",
    "g",
    "kg",
    "mg",
    "lb",
    "lbs",
    "oz",
    "t",
    "s",
    "sec",
    "secs",
    "ms",
    "us",
    "ns",
    "min",
    "mins",
    "h",
    "hr",
    "hrs",
    "l",
    "ml",
    "liter",
    "liters",
    "litre",
    "litres",
    "gal",
    "b",
    "kb",
    "mb",
    "gb",
    "tb",
    "kib",
    "mib",
    "gib",
    "tib",
    "hz",
    "khz",
    "mhz",
    "ghz",
    "v",
    "a",
    "ma",
    "w",
    "kw",
    "mw",
    "c",
    "f",
    "k",
    "pa",
    "kpa",
    "bar",
    "psi",
    "rpm",
    "n",
    "nm",
    "%",
    "px",
    "em",
    "rem",
    "pt",
    "deg",
    "degrees",
}

#: Verbs that commonly open an instruction in developer prose. A sentence that
#: starts with one is treated as procedural, so the 20-word limit applies.
_IMPERATIVE_VERBS = {
    "add",
    "apply",
    "avoid",
    "bind",
    "build",
    "calculate",
    "call",
    "cancel",
    "change",
    "check",
    "clear",
    "click",
    "close",
    "commit",
    "compare",
    "configure",
    "connect",
    "copy",
    "create",
    "declare",
    "decode",
    "define",
    "delete",
    "deploy",
    "disable",
    "disconnect",
    "do",
    "download",
    "drain",
    "enable",
    "encode",
    "enter",
    "examine",
    "export",
    "extend",
    "fetch",
    "fill",
    "filter",
    "find",
    "follow",
    "format",
    "get",
    "give",
    "hold",
    "ignore",
    "implement",
    "import",
    "increase",
    "initialize",
    "insert",
    "install",
    "keep",
    "load",
    "lock",
    "log",
    "look",
    "make",
    "measure",
    "merge",
    "modify",
    "monitor",
    "mount",
    "move",
    "note",
    "obey",
    "open",
    "override",
    "parse",
    "pass",
    "press",
    "prevent",
    "print",
    "pull",
    "push",
    "put",
    "read",
    "rebuild",
    "record",
    "refer",
    "register",
    "release",
    "reload",
    "remove",
    "rename",
    "render",
    "repeat",
    "replace",
    "reset",
    "restart",
    "restore",
    "return",
    "review",
    "rewrite",
    "run",
    "save",
    "select",
    "send",
    "set",
    "show",
    "skip",
    "sort",
    "split",
    "start",
    "stop",
    "store",
    "supply",
    "test",
    "throw",
    "trim",
    "turn",
    "unlock",
    "update",
    "upload",
    "use",
    "validate",
    "verify",
    "wait",
    "write",
}

#: Words that, right after an opening verb, mean the verb was really a noun.
#: "Log output is written" opens with "log", but it is not an instruction.
_NOT_IMPERATIVE_FOLLOWERS = {
    "is",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "will",
    "would",
    "can",
    "could",
    "should",
    "may",
    "might",
    "must",
    "does",
    "did",
}

#: A sentence ends at terminal punctuation, but a closing inline-emphasis marker
#: can sit between the punctuation and the whitespace. "**A bold lead-in.** The
#: rest." ends a sentence at the period, even though `**` follows it before the
#: space. Without this the bold clause merges into the next sentence and inflates
#: its word count against rules 5.1 and 6.3.
_SENTENCE_END = re.compile(r"[.!?]+[*_`~]*(?=\s|$)")
_PARENTHETICAL = re.compile(r"\([^()]*\)")
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']{2,}'|`[^`]*`")
_NUMBER = re.compile(r"^[+-]?\d[\d,]*(\.\d+)?$")
_STRIP_EDGE_PUNCT = re.compile(r"^[^\w(\[\"'`%]+|[^\w)\]\"'`%]+$")


@dataclass(frozen=True)
class Sentence:
    text: str
    offset: int
    register: Register

    @property
    def word_count(self) -> int:
        return len(ste_words(self.text))


def _protect_abbreviations(text: str) -> str:
    """Replace the period in a known abbreviation so it does not end a sentence."""
    out = text
    for abbrev in _ABBREVIATIONS:
        pattern = re.compile(r"\b" + re.escape(abbrev[:-1]) + r"\.", re.IGNORECASE)
        out = pattern.sub(lambda m: m.group(0)[:-1] + "\x00", out)
    return out


def split_sentences(text: str, default: Register = Register.DESCRIPTIVE) -> list[Sentence]:
    """Split prose into sentences, keeping each one's offset in `text`."""
    protected = _protect_abbreviations(text)
    sentences: list[Sentence] = []
    start = 0
    for match in _SENTENCE_END.finditer(protected):
        raw = protected[start : match.end()]
        if raw.strip():
            sentences.append(_make_sentence(raw, start, default))
        start = match.end()
    tail = protected[start:]
    if tail.strip():
        sentences.append(_make_sentence(tail, start, default))
    return sentences


def _make_sentence(raw: str, offset: int, default: Register) -> Sentence:
    leading = len(raw) - len(raw.lstrip())
    body = raw.strip().replace("\x00", ".")
    return Sentence(text=body, offset=offset + leading, register=detect_register(body, default))


#: Determiners that confirm an opening verb really is a command. "Check the
#: pump" is an instruction; "Log output is written" is not, and the difference
#: is whether a determiner follows the first word.
_DETERMINERS = {
    "the",
    "a",
    "an",
    "this",
    "these",
    "that",
    "those",
    "its",
    "their",
    "your",
    "our",
    "his",
    "her",
    "each",
    "every",
    "any",
    "all",
    "both",
    "it",
    "them",
}


def detect_register(sentence: str, default: Register = Register.DESCRIPTIVE) -> Register:
    """Decide whether a sentence is an instruction or a description.

    The two differ only in their word limit, 20 against 25, so a wrong call
    costs five words rather than a spurious finding.
    """
    words = [w.lower() for w in re.split(r"[^\w'-]+", sentence) if w]
    if not words:
        return default

    first = words[0]
    if first == "don't" or (first == "do" and len(words) > 1 and words[1] == "not"):
        return Register.PROCEDURAL
    if first not in _IMPERATIVE_VERBS:
        return default
    if len(words) > 1 and words[1] in _DETERMINERS:
        return Register.PROCEDURAL
    if any(word in _NOT_IMPERATIVE_FOLLOWERS for word in words[1:4]):
        return default
    return Register.PROCEDURAL


def ste_words(sentence: str) -> list[str]:
    """Count words the way ASD-STE100 counts them.

    Rule 8.5 collapses a parenthesised group to one word and rule 8.6 does the
    same for quoted text, numbers with units, abbreviations, and alphanumeric
    identifiers. Rule 8.7 collapses a hyphenated compound. Hyphenated compounds,
    abbreviations, and identifiers hold together under a whitespace split
    already, so only the spanning constructs need explicit handling.
    """
    masked = _PARENTHETICAL.sub(" \x01paren\x01 ", sentence)
    masked = _QUOTED.sub(" \x01quote\x01 ", masked)

    raw_tokens = [t for t in masked.split() if t]
    tokens: list[str] = []
    for token in raw_tokens:
        cleaned = _STRIP_EDGE_PUNCT.sub("", token)
        if cleaned:
            tokens.append(cleaned)

    words: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _NUMBER.match(token) and index + 1 < len(tokens):
            following = tokens[index + 1].lower().rstrip(".,")
            if following in _UNITS:
                words.append(f"{token} {tokens[index + 1]}")
                index += 2
                continue
        words.append(token)
        index += 1
    return words


def split_paragraphs(text: str) -> list[tuple[int, str]]:
    """Split on blank lines, returning each paragraph with its offset."""
    paragraphs: list[tuple[int, str]] = []
    offset = 0
    for block in re.split(r"\n\s*\n", text):
        if block.strip():
            paragraphs.append((offset, block))
        offset += len(block) + 2
    return paragraphs


def strip_code(text: str) -> str:
    """Remove code blocks, and reduce a Markdown link to its visible text.

    STE governs prose, so a fenced or indented code block is dropped outright.
    Inline code, an autolink, and a bare URL are left in place. Each is a single
    token already, which is how rule 8.6 counts it, so no placeholder is needed
    to keep the word count right. Leaving the real span in place also keeps an
    excerpt readable: an earlier version substituted "(code)", and that token
    then showed up in reports and was checked as though it were prose. A Markdown
    link keeps its visible text and loses its target.
    """
    out = re.sub(r"```.*?```", "\n", text, flags=re.DOTALL)
    out = re.sub(r"~~~.*?~~~", "\n", out, flags=re.DOTALL)
    out = re.sub(r"^(?: {4}|\t)\S.*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", out)
    return out
