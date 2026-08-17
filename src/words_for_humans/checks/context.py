"""Shared state and helpers for the checks."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol, cast

from ..config import Config
from ..dictionary import Dictionary
from ..model import Finding, Register, Segment, SegmentKind
from ..rules import (
    DEFAULT_SENTENCE_TIERS,
    MAX_WORDS_DESCRIPTIVE,
    MAX_WORDS_PROCEDURAL,
    Severity,
)

#: Rules whose findings fail the run by default.
#:
#: These are the rules with a fixed threshold or a closed set of forbidden
#: tokens, where a false positive is rare enough to justify blocking a build.
#:
#: C-4 (noun-cluster) is deliberately not in this set. Finding a multi-word
#: noun without a part-of-speech tagger means guessing which runs of words
#: form one noun, and the guess is wrong often enough that failing on it is
#: not defensible. It is reported as a warning instead. Promote it when you
#: want it blocking:
#:
#:     [severity]
#:     "C-4" = "hard"
#:
#: The reverse works too, for example to stop passive voice failing a build:
#:
#:     [severity]
#:     "C-3" = "soft"
DEFAULT_HARD_RULES = frozenset({"3.4", "4.2", "8.1", "GR-6", "C-1", "C-2", "C-3"})

#: Identifiers and commit subjects are outside what the specification governs, so
#: nothing found in them fails a build.
ALWAYS_SOFT_KINDS = frozenset({SegmentKind.IDENTIFIER, SegmentKind.COMMIT})

#: Segment kinds that take the looser `prose` sentence-length tier. Everything
#: else takes the tighter `code` tier.
PROSE_LENGTH_KINDS = frozenset(
    {SegmentKind.MARKDOWN, SegmentKind.PR_DESCRIPTION, SegmentKind.COMMIT}
)


class Check(Protocol):
    """A deterministic check over one segment.

    Each check declares the rules it implements, and optionally the segment
    kinds it applies to. The `covers_rules` and `applies_to` decorators attach
    both, so `Context.covers` reads them as fields rather than guessing at
    attributes that may not be there.
    """

    rule_ids: tuple[str, ...]
    kinds: frozenset[SegmentKind] | None

    def __call__(self, segment: Segment, context: Context) -> Iterable[Finding]: ...


@dataclass
class Context:
    dictionary: Dictionary
    hard_rules: frozenset[str] = DEFAULT_HARD_RULES
    disabled_rules: frozenset[str] = frozenset()
    #: The judgment-tier rules this profile sends to the model. The default is
    #: empty: a context built by hand judges nothing until it is told to.
    judgment_rules: frozenset[str] = frozenset()
    severity_overrides: dict[str, Severity] = field(default_factory=dict)
    scopes: frozenset[SegmentKind] = frozenset(SegmentKind)
    max_procedural_words: int | None = None
    max_descriptive_words: int | None = None
    #: Resolved (warn, fail) word counts keyed by tier ("code", "prose"). When
    #: None, the strict ASD-STE100 single limits apply, which is the `ste` case.
    sentence_tiers: dict[str, tuple[int, int]] | None = None
    #: Whether the part-of-speech backend is active. It makes noun-cluster and
    #: passive-voice precise, so those checks use it and the profile reports them.
    pos: bool = False

    @classmethod
    def from_config(cls, dictionary: Dictionary, config: Config) -> Context:
        """Assemble the check context from a loaded dictionary and a config.

        Both the CLI engine and the GitHub App build a context from the same
        settings, so the mapping lives here rather than in each caller.

        The active profile silences its dialect rules by folding them into the
        disabled set. Naming a rule in the config `[severity]` table turns it
        back on, so a repository that wants passive-voice warnings under a
        genre profile can ask for them.

        The judgment allowlist follows the same contract. The profile names
        the judgment rules the model is asked, the `[severity]` table opts a
        rule back in, and `disable` opts one out.

        Sentence length is a warn-and-fail pair per tier under every profile
        that carries tiers. `ste` carries none, which keeps the strict single
        limit of the specification.

        When the part-of-speech backend is installed, noun-cluster and
        passive-voice become precise, so they are un-quieted under the genre
        profiles. Without it they stay quiet, because their regex fallbacks
        over-report.
        """
        from ..profiles import judgment_rules, quiet_rules, sentence_tiers
        from ..rules import CATALOGUE, Decidability
        from . import pos_backend

        disabled = (config.disable | quiet_rules(config.profile)) - set(config.severity)
        pos = pos_backend.available()
        if pos:
            disabled -= {"C-3", "C-4"}
        judgment_ids = frozenset(
            rule.id for rule in CATALOGUE.values() if rule.decidability is Decidability.JUDGMENT
        )
        judged = (
            judgment_rules(config.profile) | (frozenset(config.severity) & judgment_ids)
        ) - config.disable
        profile_tiers = sentence_tiers(config.profile)
        tiers = None if profile_tiers is None else {**profile_tiers, **config.sentence_tiers}
        return cls(
            dictionary=dictionary,
            hard_rules=config.hard_rules,
            disabled_rules=disabled,
            judgment_rules=judged,
            severity_overrides=config.severity,
            scopes=config.scopes,
            max_procedural_words=config.max_procedural_words,
            max_descriptive_words=config.max_descriptive_words,
            sentence_tiers=tiers,
            pos=pos,
        )

    def covers(self, segment: Segment, check: Check) -> bool:
        if check.rule_ids and all(r in self.disabled_rules for r in check.rule_ids):
            return False
        return check.kinds is None or segment.kind in check.kinds

    def severity_for(self, rule_id: str, segment: Segment) -> Severity:
        if segment.kind in ALWAYS_SOFT_KINDS:
            return Severity.SOFT
        override = self.severity_overrides.get(rule_id)
        if override is not None:
            return override
        return Severity.HARD if rule_id in self.hard_rules else Severity.SOFT

    def sentence_thresholds(self, kind: SegmentKind, register: Register) -> tuple[int, int]:
        """The (warn, fail) word counts for a sentence of this kind and register.

        Under `ste` there is no warn band: the two counts are equal, so any
        sentence over the specification limit fails.
        """
        if self.sentence_tiers is not None:
            tier = "prose" if kind in PROSE_LENGTH_KINDS else "code"
            return self.sentence_tiers.get(tier, DEFAULT_SENTENCE_TIERS[tier])
        if register is Register.PROCEDURAL:
            limit = self.max_procedural_words or MAX_WORDS_PROCEDURAL
        else:
            limit = self.max_descriptive_words or MAX_WORDS_DESCRIPTIVE
        return (limit, limit)

    def length_severity(self, rule_id: str, segment: Segment, over_fail: bool) -> Severity:
        """Severity for a sentence-length finding.

        A sentence in the warn band always reports soft. One over the fail count
        fails the build, unless the segment kind never blocks, the profile does
        not block this rule, or the config demotes it.
        """
        if segment.kind in ALWAYS_SOFT_KINDS:
            return Severity.SOFT
        override = self.severity_overrides.get(rule_id)
        if override is not None:
            return override
        if not over_fail:
            return Severity.SOFT
        return Severity.HARD if rule_id in self.hard_rules else Severity.SOFT


@dataclass
class ContextMap:
    """One context per profile the config's `[paths]` table can resolve to.

    Contexts are built lazily and cached, so a run with no path mappings
    builds exactly one, and a run with mappings builds one per distinct
    profile its files land in. Both the CLI engine and the GitHub App route
    each segment through `for_path`, so a repository's mapping applies the
    same way in either.
    """

    dictionary: Dictionary
    config: Config
    _built: dict[str, Context] = field(default_factory=dict)

    def for_path(self, path: str) -> Context:
        """The context for one file, by its root-relative posix path."""
        return self.for_profile(self.config.profile_for(path))

    def for_profile(self, name: str) -> Context:
        context = self._built.get(name)
        if context is None:
            context = Context.from_config(self.dictionary, self.config.for_profile(name))
            self._built[name] = context
        return context


def finding(
    segment: Segment,
    context: Context,
    rule_id: str,
    message: str,
    *,
    offset: int = 0,
    excerpt: str | None = None,
    suggestion: str | None = None,
    severity: Severity | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity if severity is not None else context.severity_for(rule_id, segment),
        path=segment.path,
        line=segment.line_for_offset(offset),
        kind=segment.kind,
        message=message,
        excerpt=_shorten(excerpt if excerpt is not None else segment.text),
        suggestion=suggestion,
        segment_text=segment.text,
    )


def _shorten(text: str, limit: int = 140) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def around(text: str, start: int, end: int, width: int = 45) -> str:
    """Return `text` around a match, with a little context on each side."""
    return text[max(0, start - width) : min(len(text), end + width)]


_CheckFn = Callable[[Segment, "Context"], Iterable[Finding]]


def applies_to(*kinds: SegmentKind) -> Callable[[_CheckFn], Check]:
    """Restrict a check to certain segment kinds."""

    def decorate(func: _CheckFn) -> Check:
        func.kinds = frozenset(kinds)  # type: ignore[attr-defined]
        if not hasattr(func, "rule_ids"):
            func.rule_ids = ()  # type: ignore[attr-defined]
        return cast(Check, func)

    return decorate


def covers_rules(*rule_ids: str) -> Callable[[_CheckFn], Check]:
    """Record which rules a check implements, so config can disable it."""

    def decorate(func: _CheckFn) -> Check:
        func.rule_ids = tuple(rule_ids)  # type: ignore[attr-defined]
        if not hasattr(func, "kinds"):
            func.kinds = None  # type: ignore[attr-defined]
        return cast(Check, func)

    return decorate
