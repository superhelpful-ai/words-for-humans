"""Rule profiles: named configurations of the rule set.

A profile decides which rules report, which fail, which reach the judgment
tier, and what sentence lengths apply. Each preset here is tuned for one
kind of text. A comment competes with the code below it, so `code` holds it
short; a plan runs longer and uses emoji on purpose, so `prose-corporate`
allows both. A repository picks a profile per run and can assign others to
parts of the tree through the `[paths]` table. What never changes is the
point of the tool: prose that says nothing, placeholder values, and the
tells of generated text fail under every preset except `minimal`.

Each profile also carries an explicit allowlist of judgment-tier rules, the
ones a model adjudicates. Under the genre profiles that list is short: the
comment-value rules and the ambiguous-referent check. The rest of the judgment
catalogue enforces the ASD-STE100 dialect, so only `ste` and `minimal` send
it to the judge.

The profiles, strictest first:

`ste`
    ASD-STE100 conformance, for a team that has adopted the standard. The
    whole standard is enforced, with the strict single sentence limits of the
    specification.

`code`
    The default. Comments, docstrings, and user-facing strings, held to the
    tightest sentence budget because a comment competes with the code below
    it. The ASD-STE100 dialect rules stay silent: passive voice, semicolons,
    contractions, and British spelling are correct in software prose.

`prose-technical`
    READMEs, specifications, design docs. It shares the `code` contract
    today, named apart so the two genres can diverge as corpus evidence
    arrives.

`changelog`
    Changelogs and release notes. A changelog narrates history and old
    behaviour on purpose, so the standalone rules stay out of it. The
    default config maps common changelog paths here.

`prose-corporate`
    Plans, reviews, briefs. Prose sentences get more room, emoji pass
    without comment, and the padding and puffery rules stay hard, because a
    plan full of praise adjectives is the failure this genre invites.

`comms-external`
    Announcements and customer-facing text. Praise adjectives report as
    warnings rather than failures, since selling is the genre. Everything
    that marks unfinished or generated text stays hard.

`comms-internal`
    The loosest gate that still fails on empty prose. Sentences get the most
    room, emoji pass without comment, and the em dash reports without
    blocking.

`minimal`
    Fails on nothing and silences nothing. Use it to see the shape of a
    corpus before deciding what to enforce.

The `comms-` pair is provisional: no corpus has tuned it yet, so expect its
thresholds to move. `concise`, the default's name before the genre profiles
existed, resolves to `code` wherever a profile is named.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rules import CATALOGUE, DEFAULT_SENTENCE_TIERS, Decidability, Severity


@dataclass(frozen=True)
class Profile:
    """One named configuration of the rule set."""

    description: str
    #: Rules that fail the build. Everything else reports as a warning.
    hard: frozenset[str]
    #: Rules not reported at all. A repository turns one back on by naming it
    #: in the config `[severity]` table.
    quiet: frozenset[str]
    #: The judgment-tier rules the profile sends to the model. This is an
    #: explicit allowlist: a judgment rule outside it is never asked, whoever
    #: runs the judge. A repository opts a rule back in by naming it in the
    #: config `[severity]` table, and opts one out with `disable`.
    judgment: frozenset[str]
    #: Sentence limits as (warn, fail) word counts keyed by tier ("code",
    #: "prose"). None keeps the strict single limits of the specification,
    #: which is the `ste` case.
    sentence_tiers: dict[str, tuple[int, int]] | None


#: The rules that ask whether the text says anything at all: restated
#: declarations, padding phrases, narration of the writing. A false positive
#: is rare enough to justify blocking a build, and the fix is a rewrite of
#: that sentence rather than a matter of taste.
_SAYS_NOTHING = frozenset({"V-1", "V-2", "V-3", "V-4", "V-5", "V-6"})

#: Tells of generated text that block wherever the genre lets them: definition
#: by negation, praise adjectives, announced lists, stacked hedges,
#: placeholder values, and the em dash. A-6 (decorative emoji) is absent on
#: purpose: plenty of teams put emoji in a README deliberately, so it reports
#: as a warning and the looser genres silence it. A-11 to A-14 (triads,
#: throat-clearing, summary closers, meta-narration) also turn up in
#: legitimate tutorials, so a warning is the honest severity everywhere.
_TELLS = frozenset({"A-1", "A-2", "A-3", "A-4", "A-5", "A-7", "A-8", "A-10"})

#: What fails under every genre profile: empty prose, generated-text tells,
#: history narration, and the sentence-length rule, which carries
#: warn-and-fail tiers rather than the strict specification limits. S-1 is
#: hard on corpus evidence: the tuned four-corpus run left nine findings,
#: and every one was a genuine journal comment.
_GENRE_HARD = _SAYS_NOTHING | _TELLS | frozenset({"C-1", "S-1"})

#: V-3 (narration) blocks a comment, where "now we will iterate" restates the
#: loop below it. A plan states future intent, so "we will expand the
#: registry" is that genre doing its job. The corporate and comms profiles
#: report V-3 without failing on it.
_STATES_INTENT = frozenset({"V-3"})

#: Not reported under the genre profiles. Almost all of these enforce the
#: ASD-STE100 controlled dialect rather than catch padding. Each is correct
#: usage in ordinary prose: contractions, British spelling, semicolons, Latin
#: abbreviations, phrasal verbs, possessives, and the tense and gerund
#: restrictions. Reporting them at the volume software produces buries the
#: findings that are the point. The `ste` profile turns them back on.
#:
#: 1.1 (approved-word) is dictionary conformance, an `ste` concern: outside a
#: team that has adopted the standard, "review is not an approved word" is
#: noise, and with a full dictionary extracted it fires at volume.
#:
#: GR-4 (bare "this") is silenced for a different reason. Whether "this"
#: names its referent clearly is a semantic judgment, and a pattern cannot
#: make it: 86% of its findings on real code are "this is" anaphora that
#: reads perfectly. The genuine check is C-6 in the judgment tier.
_DIALECT = frozenset(
    {
        "1.1",
        "1.14",
        "3.2",
        "3.4",
        "3.5",
        "3.7",
        "4.2",
        "8.1",
        "9.3",
        "GR-4",
        "GR-6",
        "GR-8",
    }
)

#: Quiet until the part-of-speech backend is installed. Passive voice and
#: noun clusters are clarity rules, but their regex fallbacks guess, and the
#: guesses over-report. The context un-quiets them when the backend is there.
_NEEDS_POS = frozenset({"C-3", "C-4"})

#: Fails a build under the ASD-STE100 profile.
STE_HARD = frozenset({"3.4", "4.2", "8.1", "GR-6", "C-1", "C-2", "C-3"})

#: The judgment rules the genre profiles send to the model.
#:
#: The judgment catalogue is mostly the rest of ASD-STE100: imperative form,
#: articles, approved word forms, parenthesis usage, connecting words. Those
#: questions belong to the standard. Asked of a README or a code comment, they
#: produce findings that are true under the standard and useless to the
#: author. A judge handed the whole list will find a violation in almost any
#: healthy paragraph. The genre profiles ask only the questions whose answer
#: helps any reader:
#:
#: C-6 (clear-referent)
#:     An ambiguous pronoun confuses every reader. GR-4, its pattern cousin,
#:     is quiet for the same reason this is here: the question is semantic.
#: S-5, S-6, S-7 (required-context, deprecated-anchor, context-bound-example)
#:     Whether a reference gates comprehension, an explanation leans on a
#:     retiring system, or an example assumes an unstated backstory. Each is
#:     a question about meaning, so no pattern can decide it.
#: V-7 (over-long-comment)
#:     This tool's own value rule. Whether a comment earns its length is the
#:     point of the tool, and no pattern can decide it.
#: A-9 (heading-restatement)
#:     A generated-text tell that needs the heading and the sentence read
#:     together.
#:
#: The rest of the judgment catalogue stays with the `ste` profile, where a
#: team has adopted the standard and the findings are the product.
_JUDGMENT_VALUE = frozenset({"C-6", "S-5", "S-6", "S-7", "V-7", "A-9"})

#: A changelog narrates history and old behaviour as its genre, so the
#: standalone rules stay out of it, in both tiers. The judgment sample made
#: the case: a judge reading a changelog under the S rules flags the genre
#: itself.
_CHANGELOG_QUIET = frozenset({"S-1", "S-2", "S-3", "S-4"})
_CHANGELOG_JUDGMENT = _JUDGMENT_VALUE - frozenset({"S-5", "S-6", "S-7"})

#: Every prose judgment rule in the catalogue. Design rules (`D-`) judge code
#: units rather than prose, so they run in their own pass and are never in a
#: profile's judgment set.
_JUDGMENT_ALL = frozenset(
    rule.id
    for rule in CATALOGUE.values()
    if rule.decidability is Decidability.JUDGMENT and not rule.id.startswith("D-")
)

#: Sentence tiers for the genres that give prose more room. The code tier
#: never loosens: a comment is a comment whatever repository it lives in.
_CORPORATE_TIERS = {"code": (25, 35), "prose": (35, 50)}
_INTERNAL_TIERS = {"code": (25, 35), "prose": (40, 60)}

PROFILES: dict[str, Profile] = {
    "ste": Profile(
        description="Fails on ASD-STE100 conformance. The full standard, enforced.",
        hard=STE_HARD,
        quiet=frozenset(),
        judgment=_JUDGMENT_ALL,
        sentence_tiers=None,
    ),
    "code": Profile(
        description=(
            "Fails on comments that say nothing. ASD-STE100 dialect rules are silent here."
        ),
        hard=_GENRE_HARD,
        quiet=_DIALECT | _NEEDS_POS,
        judgment=_JUDGMENT_VALUE,
        sentence_tiers=DEFAULT_SENTENCE_TIERS,
    ),
    "prose-technical": Profile(
        description="READMEs, specs, design docs. The `code` contract, named for the genre.",
        hard=_GENRE_HARD,
        quiet=_DIALECT | _NEEDS_POS,
        judgment=_JUDGMENT_VALUE,
        sentence_tiers=DEFAULT_SENTENCE_TIERS,
    ),
    "changelog": Profile(
        description="Changelogs and release notes. History narration is the genre.",
        hard=_GENRE_HARD - _CHANGELOG_QUIET,
        quiet=_DIALECT | _NEEDS_POS | _CHANGELOG_QUIET,
        judgment=_CHANGELOG_JUDGMENT,
        sentence_tiers=DEFAULT_SENTENCE_TIERS,
    ),
    "prose-corporate": Profile(
        description="Plans, reviews, briefs. Longer sentences and emoji pass; puffery fails.",
        hard=_GENRE_HARD - _STATES_INTENT,
        quiet=_DIALECT | _NEEDS_POS | {"A-6"},
        judgment=_JUDGMENT_VALUE,
        sentence_tiers=_CORPORATE_TIERS,
    ),
    "comms-external": Profile(
        description="Customer-facing text. Praise adjectives warn; unfinished text fails.",
        hard=_GENRE_HARD - _STATES_INTENT - {"A-2"},
        quiet=_DIALECT | _NEEDS_POS,
        judgment=_JUDGMENT_VALUE,
        sentence_tiers=_CORPORATE_TIERS,
    ),
    "comms-internal": Profile(
        description="Internal notes. The loosest gate that still fails on empty prose.",
        hard=_GENRE_HARD - _STATES_INTENT - {"A-2", "A-10"},
        quiet=_DIALECT | _NEEDS_POS | {"A-6"},
        judgment=_JUDGMENT_VALUE,
        sentence_tiers=_INTERNAL_TIERS,
    ),
    "minimal": Profile(
        description="Reports everything, fails on nothing.",
        hard=frozenset(),
        quiet=frozenset(),
        judgment=_JUDGMENT_ALL,
        sentence_tiers=DEFAULT_SENTENCE_TIERS,
    ),
}

#: Names from before the genre taxonomy, kept working because they are in
#: published configs.
ALIASES = {"concise": "code"}

DEFAULT_PROFILE = "code"


def canonical(name: str) -> str:
    """Resolve a profile name, mapping pre-taxonomy names to their successors."""
    return ALIASES.get(name, name)


def names() -> list[str]:
    """Every profile name, strictest first."""
    return list(PROFILES)


def _profile(name: str) -> Profile:
    return PROFILES.get(canonical(name)) or PROFILES[DEFAULT_PROFILE]


def hard_rules(profile: str) -> frozenset[str]:
    return _profile(profile).hard


def quiet_rules(profile: str) -> frozenset[str]:
    """Rules the profile does not report at all."""
    return _profile(profile).quiet


def judgment_rules(profile: str) -> frozenset[str]:
    """The judgment-tier rules the profile sends to the model."""
    return _profile(profile).judgment


def sentence_tiers(profile: str) -> dict[str, tuple[int, int]] | None:
    """The profile's (warn, fail) sentence tiers, or None for strict single limits."""
    return _profile(profile).sentence_tiers


def severities(profile: str) -> dict[str, Severity]:
    """Explicit severity for every rule under a profile."""
    hard = hard_rules(profile)
    return {rule_id: Severity.HARD if rule_id in hard else Severity.SOFT for rule_id in CATALOGUE}


def describe(profile: str) -> str:
    return _profile(profile).description
