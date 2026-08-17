"""The ASD-STE100 rule catalogue.

ASD-STE100 Issue 9 (2025-01-15) contains 53 writing rules across nine sections,
plus eight general recommendations. This module records each rule as metadata:
its number, section, a paraphrase of what it requires, and whether a program can
decide it without human or model judgment.

The paraphrases here are summaries written for this tool. They are not the text
of the specification. ASD owns the specification; the authoritative wording is in
the free official document at https://www.asd-ste100.org/.

`Decidability` drives the split between the two halves of the system. `MECHANICAL`
rules are checked by the CLI. `JUDGMENT` rules need a reader who understands what
the text means, and are handled by the review skill. `CONTEXT` rules constrain how
text is counted or laid out rather than flagging prose on their own.

The tool's own families carry letter prefixes: C (reads clearly), S (stands
alone), V (says something), A (sounds human), D (design). The C rules began
as ASD-STE100 rules and earned their keep on real software prose.
The numbered and GR rules that remain are deprecated: only the `ste` profile
reports them, and the next major release removes them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Decidability(StrEnum):
    MECHANICAL = "mechanical"
    JUDGMENT = "judgment"
    CONTEXT = "context"


class Severity(StrEnum):
    """How a finding affects the exit code.

    HARD findings fail the run. They come from rules with an unambiguous
    threshold or a closed set of forbidden tokens, so a false positive is rare.

    SOFT findings are reported but never fail the run. They come from rules that
    depend on the dictionary, on part-of-speech guessing, or on word lists that
    no heuristic covers completely.
    """

    HARD = "hard"
    SOFT = "soft"


@dataclass(frozen=True)
class Rule:
    id: str
    slug: str
    section: str
    summary: str
    decidability: Decidability
    #: A deprecated rule still runs, but only the `ste` profile reports it,
    #: and the next major release removes it.
    deprecated: bool = False
    #: Calibration for the judgment tier, carried into the judge prompt
    #: beside the summary. The corpus reads showed a judge applies a bare
    #: summary too hard; the note states what not to flag.
    judge_note: str = ""

    @property
    def label(self) -> str:
        """The rule code with its slug, for self-documenting output."""
        return f"{self.id} {self.slug}"


SECTIONS = {
    "C": "Clarity",
    "S": "Standalone",
    "1": "Words",
    "2": "Multi-word nouns",
    "3": "Verbs",
    "4": "Sentences",
    "5": "Procedural writing",
    "6": "Descriptive writing",
    "7": "Safety instructions",
    "8": "Punctuation and word count",
    "9": "Writing practices",
    "GR": "General recommendations",
    "V": "Comment value",
    "A": "AI tells",
    "D": "Design smells",
}


#: The sections scheduled for removal: everything still carrying the
#: specification's own numbering. The letter families are the product.
_DEPRECATED_SECTIONS = frozenset({"1", "2", "3", "4", "5", "6", "7", "8", "9", "GR"})


def _r(
    id: str, slug: str, summary: str, decidability: Decidability, *, judge_note: str = ""
) -> Rule:
    if id.startswith("C-"):
        key = "C"
    elif id.startswith("S-"):
        key = "S"
    elif id.startswith("V-"):
        key = "V"
    elif id.startswith("A-"):
        key = "A"
    elif id.startswith("D-"):
        key = "D"
    elif id.startswith("GR"):
        key = "GR"
    else:
        key = id.split(".", maxsplit=1)[0]
    return Rule(
        id=id,
        slug=slug,
        section=SECTIONS[key],
        summary=summary,
        decidability=decidability,
        deprecated=key in _DEPRECATED_SECTIONS,
        judge_note=judge_note,
    )


M = Decidability.MECHANICAL
J = Decidability.JUDGMENT
C = Decidability.CONTEXT

CATALOGUE: dict[str, Rule] = {
    r.id: r
    for r in [
        # Clarity. Whether the prose reads easily, whoever wrote it. These
        # began as ASD-STE100 rules and earned their keep on real software
        # prose, so the collapse gave each a single id of its own.
        _r(
            "C-1",
            "sentence-length",
            "In descriptive text, use a maximum of 25 words in each sentence, "
            "and 20 in a procedure.",
            M,
        ),
        _r("C-2", "paragraph-length", "Write no more than six sentences in a paragraph.", M),
        _r(
            "C-3",
            "passive-voice",
            "Use the active voice. Passive voice is allowed in descriptive writing "
            "only when the agent is unknown.",
            M,
        ),
        _r("C-4", "noun-cluster", "Write multi-word nouns of no more than three words.", M),
        _r("C-5", "no-slang", "Do not use regional, slang, or jargon words as technical nouns.", M),
        _r(
            "C-6",
            "clear-referent",
            "Use pronouns only where the referent is unambiguous.",
            J,
            judge_note=(
                "Flag a pronoun only when two plausible referents compete. A pronoun "
                "whose referent is the obvious subject of the sentence is fine."
            ),
        ),
        _r("C-7", "inclusive-language", "Use inclusive language.", M),
        # Standalone. Whether the text can be understood by a reader who has
        # only the file in front of them: no pull request, no ticket, no
        # conversation. docs/standalone-rules.md records the design and the
        # published authority behind each rule.
        _r(
            "S-1",
            "history-narration",
            "State the current truth, not how the text came to be.",
            M,
        ),
        _r("S-2", "diff-comment", "Comment the code, not the change that produced it.", M),
        _r(
            "S-3",
            "reference-as-explanation",
            "Use a reference to add depth, never as the whole explanation.",
            M,
        ),
        _r(
            "S-4",
            "time-anchor",
            'Anchor time-relative words such as "currently" to a date or version.',
            M,
        ),
        _r(
            "S-5",
            "required-context",
            "Restate what the reader needs; a citation stays optional.",
            J,
            judge_note=(
                "A citation beside a stated fact is good. Flag only text the reader "
                "cannot understand without opening the reference."
            ),
        ),
        _r(
            "S-6",
            "deprecated-anchor",
            "State the current constraint, not the retiring thing it replaced.",
            J,
            judge_note=(
                "Flag an explanation that leans on a system being removed. Text whose "
                "subject is the old behaviour, such as a migration note, is doing its job."
            ),
        ),
        _r(
            "S-7",
            "context-bound-example",
            "Give an example its own context in the sentence it appears in.",
            J,
            judge_note=(
                "Flag only an example that assumes a person, incident, or backstory the "
                "reader cannot know. A placeholder or generic example is fine."
            ),
        ),
        # Section 1 - Words
        _r(
            "1.1",
            "approved-word",
            "Use dictionary-approved words, technical nouns, or technical verbs.",
            M,
        ),
        _r("1.2", "approved-pos", "Use an approved word only as its listed part of speech.", J),
        _r("1.3", "approved-meaning", "Use an approved word only with its approved meaning.", J),
        _r("1.4", "approved-form", "Use only the approved forms of verbs and adjectives.", J),
        _r(
            "1.5",
            "technical-noun",
            "An unlisted word is allowed only if it fits a technical noun category.",
            J,
        ),
        _r(
            "1.6",
            "unapproved-noun",
            "Use an unapproved word only as a technical noun or part of one.",
            J,
        ),
        _r("1.7", "noun-as-verb", "Do not use a technical noun as a verb.", J),
        _r(
            "1.8",
            "domain-noun",
            "Use technical nouns approved in your company, industry, or subject field.",
            J,
        ),
        _r("1.9", "short-noun", "Prefer the short, easily understood technical noun.", J),
        _r(
            "1.11",
            "one-noun-per-thing",
            "Do not use different technical nouns for the same item.",
            J,
        ),
        _r("1.12", "technical-verb", "Use verbs that fit a technical verb category.", J),
        _r("1.13", "verb-as-noun", "Do not use a technical verb as a noun.", J),
        _r("1.14", "american-spelling", "Use American English spelling.", M),
        # Section 2 - Multi-word nouns
        _r(
            "2.2",
            "define-then-shorten",
            "Write a longer technical noun in full, then shorten or hyphenate it.",
            J,
        ),
        # Section 3 - Verbs
        _r("3.1", "dictionary-verb-form", "Use only the verb forms given in the dictionary.", J),
        _r(
            "3.2",
            "simple-tense",
            "Use only the infinitive, imperative, simple present, simple past, "
            "simple future, and past participle as an adjective.",
            M,
        ),
        _r("3.3", "participle-adjective", "Use the past participle form as an adjective.", J),
        _r(
            "3.4",
            "auxiliary-stack",
            "Do not use auxiliary verbs to build complex verb constructions.",
            M,
        ),
        _r(
            "3.5",
            "gerund",
            'Use an "-ing" form only as a technical noun or a modifier within one.',
            M,
        ),
        _r("3.7", "verb-not-noun", "Describe an action with an approved verb, not a noun.", M),
        # Section 4 - Sentences
        _r("4.1", "short-sentence", "Write short and clear sentences.", C),
        _r(
            "4.2",
            "no-contraction",
            "Do not omit words or use contractions to shorten a sentence.",
            M,
        ),
        _r("4.3", "vertical-list", "Use a vertical list for complex text.", J),
        _r(
            "4.4",
            "connecting-words",
            "Connect related sentences with connecting words and phrases.",
            J,
        ),
        _r(
            "4.5",
            "article",
            "Use an article or demonstrative adjective before a noun where applicable.",
            J,
        ),
        # Section 5 - Procedural writing
        _r(
            "5.2",
            "one-instruction",
            "Write one instruction per sentence unless the actions are simultaneous.",
            J,
        ),
        _r("5.3", "imperative", "Write instructions in the imperative form.", J),
        _r(
            "5.4",
            "condition-first",
            "Put a required condition first, separated from the command by a comma.",
            J,
        ),
        _r("5.5", "note-not-instruction", "Write notes to give information, not instructions.", J),
        # Section 6 - Descriptive writing
        _r("6.1", "gradual", "Give information gradually.", J),
        _r(
            "6.2",
            "key-words",
            "Use key words and key phrases to give the text a logical structure.",
            J,
        ),
        _r("6.4", "paragraph-grouping", "Use paragraphs to group related information.", J),
        _r("6.5", "one-topic", "Give each paragraph one topic.", J),
        # Section 7 - Safety instructions
        _r(
            "7.1",
            "risk-word",
            'Identify the level of risk with a word such as "warning" or "caution".',
            J,
        ),
        _r(
            "7.2",
            "command-first",
            "Start a safety instruction with a clear command or condition.",
            J,
        ),
        _r("7.3", "explain-risk", "Explain the risk or the possible result.", J),
        # Section 8 - Punctuation and word count
        _r("8.1", "no-semicolon", "Use standard English punctuation, but not the semicolon.", M),
        _r("8.2", "hyphen", "Use hyphens to connect directly related words.", J),
        _r(
            "8.3",
            "parentheses",
            "Use parentheses for references, identifiers, abbreviations, and alternatives.",
            J,
        ),
        _r(
            "8.4",
            "colon-count",
            "In a vertical list, a colon ends a sentence for word-count purposes.",
            C,
        ),
        _r("8.5", "parenthesis-count", "Parenthesised text counts as one word.", C),
        _r(
            "8.6",
            "identifier-count",
            "Numbers, numbers with units, abbreviations, alphanumeric identifiers, "
            "quoted text, titles, and proper nouns each count as one word.",
            C,
        ),
        _r("8.7", "hyphen-count", "A hyphenated word counts as one word.", C),
        # Section 9 - Writing practices
        _r(
            "9.1",
            "recast",
            "Recast the sentence when a word-for-word replacement is not enough.",
            J,
        ),
        _r("9.2", "correct-use", "Use each approved word correctly.", J),
        _r("9.3", "phrasal-verb", "Do not build phrasal verbs from two words used together.", M),
        _r("9.4", "consistent-terms", "Use a consistent style for terminology and wording.", J),
        # General recommendations
        _r("GR-1", "keep-that", 'Keep the conjunction "that" rather than dropping it.', J),
        _r("GR-2", "ambiguous-with", 'Avoid the ambiguous preposition "with".', J),
        _r("GR-4", "dangling-this", 'Do not use "this" without the noun it refers to.', M),
        _r("GR-5", "false-friend", "Avoid false friends.", J),
        # Comment value. These are this tool's rules, not ASD's. ASD-STE100
        # governs how a sentence is built and says nothing about whether the
        # sentence was worth writing, which is the failure mode of generated
        # comments.
        _r("V-1", "says-nothing", "A comment must say something the code does not.", M),
        _r("V-2", "filler-opener", "Do not open a sentence with filler.", M),
        _r("V-3", "narrates-writing", "State the fact rather than narrate the writing.", M),
        _r("V-4", "restates-declaration", "Do not open a comment by restating the declaration.", M),
        _r("V-5", "padding-phrase", "Use the short phrase where it means the same.", M),
        _r("V-6", "empty-param-doc", "A parameter description must add to its name.", M),
        _r(
            "V-7",
            "over-long-comment",
            "Cut a comment longer than the code it explains.",
            J,
            judge_note=(
                "Count information, not lines. A short comment stating a constraint, "
                "invariant, or reason above short code is fine at any ratio."
            ),
        ),
        # AI tells. Prose shaped the way a language model shapes it,
        # whatever the prompt asked for.
        _r("A-1", "definition-by-negation", "Do not define a thing by saying what it is not.", M),
        _r("A-2", "praise-adjective", "Describe behaviour rather than assert quality.", M),
        _r("A-3", "announced-list", "Give the list rather than announce it.", M),
        _r("A-4", "stacked-hedge", "Do not stack hedges on deterministic behaviour.", M),
        _r("A-5", "incomplete-code", "Do not ship a comment that says the code is incomplete.", M),
        _r("A-6", "decorative-emoji", "Do not use decorative emoji in technical text.", M),
        _r("A-7", "placeholder-value", "Do not leave a placeholder value in place.", M),
        _r("A-8", "step-narration", "Do not narrate steps the code already shows.", M),
        _r(
            "A-9",
            "heading-restatement",
            "Do not restate the section heading in its first sentence.",
            J,
        ),
        _r("A-10", "em-dash", "Do not use an em dash. Use a comma, colon, or full stop.", M),
        _r("A-11", "triad", "Do not stack short negated fragments for rhythm.", M),
        _r(
            "A-12",
            "throat-clearing",
            "Do not open with a pleasantry before the first sentence of content.",
            M,
        ),
        _r(
            "A-13",
            "summary-closer",
            "Do not close by announcing a summary of what was just written.",
            M,
        ),
        _r(
            "A-14",
            "meta-narration",
            "State the content rather than narrate that you are about to state it.",
            M,
        ),
        _r("GR-6", "latin-abbreviation", "Avoid Latin abbreviations.", M),
        _r("GR-8", "possessive", "Avoid the possessive form.", M),
        # Design smells. These are this tool's rules, keyed to two published
        # sources: A Philosophy of Software Design (Ousterhout) and Clean Code
        # (Martin). ASD-STE100 governs the prose. These govern the code the prose
        # sits next to. Each needs a reader who understands the code. All are
        # judgment rules run in the model tier, and none is a hard rule.
        _r(
            "D-1",
            "shallow-module",
            "A module's interface must be simpler than its implementation.",
            J,
        ),
        _r("D-2", "information-leakage", "Do not spread one design decision across modules.", J),
        _r(
            "D-3",
            "temporal-decomposition",
            "Decompose by responsibility, not by order of execution.",
            J,
        ),
        _r("D-4", "pass-through-method", "Remove a method that only forwards to another.", J),
        _r(
            "D-5",
            "special-general-mixture",
            "Keep special-purpose code out of a general mechanism.",
            J,
        ),
        _r(
            "D-6",
            "conjoined-methods",
            "Do not write two methods that each need the other to be read.",
            J,
        ),
        _r(
            "D-7",
            "leaky-abstraction",
            "Do not make the caller depend on an implementation detail.",
            J,
        ),
        _r("D-8", "overexposure", "Do not make the common caller learn a rare feature.", J),
        _r("D-9", "nonobvious-code", "Explain code that is correct but not obvious.", J),
        _r("D-10", "misleading-name", "Give a name that reveals intent and does not mislead.", J),
        _r("D-11", "inconsistent-vocabulary", "Use one name for one concept.", J),
        _r("D-12", "does-two-things", "Write a function that does one thing.", J),
        _r("D-13", "flag-argument", "Replace a boolean argument with two functions.", J),
        _r("D-14", "temporal-coupling", "Make a required call order visible in the signatures.", J),
        _r("D-15", "duplicated-logic", "State one idea in one place.", J),
        _r("D-16", "obscure-conditional", "Give a complex condition a name.", J),
    ]
}

#: Sentence word limits from C-1, one per register. The `ste` profile uses
#: these as strict single limits: any sentence over the limit fails.
MAX_WORDS_PROCEDURAL = 20
MAX_WORDS_DESCRIPTIVE = 25

#: Sentence-length thresholds under the default profile, as (warn, fail) word
#: counts. A sentence over `warn` is reported as a warning; over `fail` it
#: fails the build. `code` covers comments, docstrings, and user-facing
#: strings, held tighter because a code reader wants the point fast. `prose`
#: covers Markdown, pull request descriptions, and commit messages, where a
#: longer sentence is more often legitimate. The looser genre profiles carry
#: their own prose tier, and a repository can override either tier in its
#: config.
DEFAULT_SENTENCE_TIERS: dict[str, tuple[int, int]] = {
    "code": (25, 35),
    "prose": (30, 40),
}

#: Paragraph limit from C-2.
MAX_SENTENCES_PER_PARAGRAPH = 6

#: Multi-word noun limit from C-4.
MAX_MULTI_WORD_NOUN = 3


def rule(rule_id: str) -> Rule:
    return CATALOGUE[rule_id]


def mechanical_rules() -> list[Rule]:
    return [r for r in CATALOGUE.values() if r.decidability is Decidability.MECHANICAL]


def judgment_rules() -> list[Rule]:
    return [r for r in CATALOGUE.values() if r.decidability is Decidability.JUDGMENT]
