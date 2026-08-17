"""Core data types shared by the extractors, the checks, and the reporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .rules import CATALOGUE, Severity


class Register(StrEnum):
    """Which sentence-length limit applies.

    ASD-STE100 sets different limits for the two kinds of text: 20 words for a
    procedure (rule 5.1) and 25 for description (rule 6.3). Most prose in a
    codebase is descriptive, so that is the default; a sentence that opens with
    a bare imperative is treated as procedural.
    """

    PROCEDURAL = "procedural"
    DESCRIPTIVE = "descriptive"


class SegmentKind(StrEnum):
    COMMENT = "comment"
    DOCSTRING = "docstring"
    MARKDOWN = "markdown"
    STRING = "string"
    IDENTIFIER = "identifier"
    COMMIT = "commit"
    PR_DESCRIPTION = "pr_description"
    CODE = "code"


@dataclass(frozen=True)
class Segment:
    """A run of human-readable text pulled out of a file.

    `line` is the 1-indexed line in `path` where the text starts. `line_offsets`
    maps each line of `text` back to its line number in the file, so a finding
    inside a multi-line comment points at the right line.

    `follows_code` holds the few lines of source directly beneath a comment.
    Deciding whether a comment says anything the code does not already say is
    impossible without it, and that check is the most useful one in the set.
    """

    path: str
    line: int
    kind: SegmentKind
    text: str
    line_offsets: tuple[int, ...] = ()
    register: Register | None = None
    follows_code: str = ""

    def line_for_offset(self, offset: int) -> int:
        """Map a character offset within `text` back to a file line number."""
        if not self.line_offsets:
            return self.line + self.text.count("\n", 0, max(offset, 0))
        newlines = self.text.count("\n", 0, max(offset, 0))
        if newlines < len(self.line_offsets):
            return self.line_offsets[newlines]
        return self.line_offsets[-1]


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    path: str
    line: int
    kind: SegmentKind
    message: str
    excerpt: str
    suggestion: str | None = None
    #: The whole piece of text the finding came from. The excerpt is trimmed to
    #: the offending phrase, which suits a terminal line but not a report that
    #: has to show somebody the comment they actually wrote.
    segment_text: str = ""

    @property
    def rule_summary(self) -> str:
        rule = CATALOGUE.get(self.rule_id)
        return rule.summary if rule else ""

    @property
    def section(self) -> str:
        rule = CATALOGUE.get(self.rule_id)
        return rule.section if rule else ""

    def fingerprint(self) -> str:
        """A location-independent identity, used by the baseline file.

        Line numbers move as a file is edited, so the baseline keys on the rule,
        the file, and the offending text instead.
        """
        return f"{self.rule_id}|{self.path}|{self.excerpt.strip()}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    segments_scanned: int = 0
    suppressed: int = 0

    @property
    def hard(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.HARD]

    @property
    def soft(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.SOFT]
