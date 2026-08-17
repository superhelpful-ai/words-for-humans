"""The genre profiles: what each fails, silences, and allows to run long."""

from __future__ import annotations

from words_for_humans import profiles
from words_for_humans.checks import sentences
from words_for_humans.checks.context import Context
from words_for_humans.config import Config
from words_for_humans.dictionary import Dictionary
from words_for_humans.model import Segment, SegmentKind
from words_for_humans.rules import Severity


def _context(profile: str) -> Context:
    return Context.from_config(Dictionary(), Config.from_table({"profile": profile}))


def _sentence(profile: str, words: int, kind: SegmentKind):
    text = " ".join(["word"] * (words - 1)) + " end."
    segment = Segment(path="doc.md", line=1, kind=kind, text=text)
    findings = sentences.check_sentence_length(segment, _context(profile))
    return [(f.rule_id, f.severity) for f in findings]


class TestTaxonomy:
    def test_the_default_is_code(self):
        assert profiles.DEFAULT_PROFILE == "code"

    def test_concise_resolves_to_code(self):
        assert profiles.canonical("concise") == "code"
        assert Config.from_table({"profile": "concise"}).profile == "code"

    def test_an_unknown_profile_falls_back_to_the_default(self):
        assert profiles.hard_rules("no-such-profile") == profiles.hard_rules("code")

    def test_every_profile_has_a_description(self):
        assert all(profiles.describe(name) for name in profiles.names())

    def test_empty_prose_and_placeholders_fail_under_every_genre_gate(self):
        for name in ("code", "prose-technical", "prose-corporate", "comms-external"):
            assert {"V-1", "V-4", "A-5", "A-7"} <= profiles.hard_rules(name), name
        assert {"V-1", "A-7"} <= profiles.hard_rules("comms-internal")


class TestCorporateProse:
    def test_emoji_are_allowed(self):
        assert "A-6" in _context("prose-corporate").disabled_rules

    def test_prose_gets_more_room(self):
        assert _sentence("prose-corporate", 35, SegmentKind.MARKDOWN) == []
        assert _sentence("prose-corporate", 45, SegmentKind.MARKDOWN) == [("C-1", Severity.SOFT)]
        assert _sentence("prose-corporate", 55, SegmentKind.MARKDOWN) == [("C-1", Severity.HARD)]

    def test_comments_stay_tight(self):
        assert _sentence("prose-corporate", 30, SegmentKind.COMMENT) == [("C-1", Severity.SOFT)]

    def test_puffery_still_fails(self):
        assert "A-2" in profiles.hard_rules("prose-corporate")

    def test_stated_intent_warns_instead_of_failing(self):
        assert profiles.severities("prose-corporate")["V-3"] is Severity.SOFT
        assert profiles.severities("code")["V-3"] is Severity.HARD


class TestComms:
    def test_external_praise_warns_instead_of_failing(self):
        assert profiles.severities("comms-external")["A-2"] is Severity.SOFT
        assert profiles.severities("comms-external")["A-7"] is Severity.HARD

    def test_external_still_reports_emoji(self):
        assert "A-6" not in _context("comms-external").disabled_rules

    def test_internal_em_dash_warns_instead_of_failing(self):
        assert profiles.severities("comms-internal")["A-10"] is Severity.SOFT

    def test_internal_prose_gets_the_most_room(self):
        assert _sentence("comms-internal", 39, SegmentKind.MARKDOWN) == []
        assert _sentence("comms-internal", 65, SegmentKind.MARKDOWN) == [("C-1", Severity.HARD)]


class TestDictionaryConformance:
    def test_the_genre_profiles_do_not_report_it(self):
        assert "1.1" in _context("code").disabled_rules
        assert "1.1" in _context("prose-corporate").disabled_rules

    def test_ste_still_does(self):
        assert "1.1" not in _context("ste").disabled_rules


class TestSte:
    def test_keeps_the_single_specification_limits(self):
        assert _context("ste").sentence_tiers is None


class TestStandaloneSeverity:
    def test_history_narration_fails_under_the_genre_profiles(self):
        for name in ("code", "prose-technical", "prose-corporate"):
            assert "S-1" in profiles.hard_rules(name), name

    def test_the_other_pattern_rules_stay_soft(self):
        for rule_id in ("S-2", "S-3", "S-4"):
            assert profiles.severities("code")[rule_id] is Severity.SOFT, rule_id


class TestChangelogProfile:
    def test_the_standalone_family_is_quiet(self):
        context = _context("changelog")
        assert {"S-1", "S-2", "S-3", "S-4"} <= context.disabled_rules
        assert {"S-5", "S-6", "S-7"}.isdisjoint(context.judgment_rules)

    def test_the_rest_of_the_contract_matches_prose(self):
        assert "A-10" in profiles.hard_rules("changelog")
        assert "C-1" in profiles.hard_rules("changelog")

    def test_changelog_paths_resolve_to_it_by_default(self):
        config = Config.from_table({})
        assert config.profile_for("CHANGELOG.md") == "changelog"
        assert config.profile_for("docs/CHANGELOG.md") == "changelog"
        assert config.profile_for("HISTORY.rst") == "changelog"
        assert config.profile_for("src/main.py") == "code"

    def test_a_repository_path_entry_overrides_the_built_in(self):
        config = Config.from_table({"paths": {"CHANGELOG*": "prose-technical"}})
        assert config.profile_for("CHANGELOG.md") == "prose-technical"

    def test_an_explicit_profile_flag_overrides_the_built_in(self):
        config = Config.from_table({})
        config.default_paths = False
        assert config.profile_for("CHANGELOG.md") == "code"


class TestJudgmentAllowlist:
    def test_genre_profiles_send_only_the_value_rules(self):
        assert profiles.judgment_rules("code") == {"C-6", "S-5", "S-6", "S-7", "V-7", "A-9"}
        for name in ("prose-technical", "prose-corporate", "comms-external", "comms-internal"):
            assert profiles.judgment_rules(name) == profiles.judgment_rules("code"), name

    def test_ste_and_minimal_send_the_full_prose_catalogue(self):
        from words_for_humans.rules import CATALOGUE, Decidability

        every = {
            r.id
            for r in CATALOGUE.values()
            if r.decidability is Decidability.JUDGMENT and not r.id.startswith("D-")
        }
        assert profiles.judgment_rules("ste") == every
        assert profiles.judgment_rules("minimal") == every
        assert "5.3" in every and "D-1" not in every

    def test_the_engine_asks_only_the_allowlisted_rules(self):
        from words_for_humans.engine import _judgment_rules_for

        asked = {rule.id for rule in _judgment_rules_for(_context("code"))}
        assert asked == {"C-6", "S-5", "S-6", "S-7", "V-7", "A-9"}

    def test_the_severity_table_opts_a_rule_back_in(self):
        config = Config.from_table({"profile": "code", "severity": {"5.3": "soft"}})
        context = Context.from_config(Dictionary(), config)
        assert "5.3" in context.judgment_rules

    def test_disable_opts_a_rule_out(self):
        config = Config.from_table({"profile": "code", "disable": ["V-7"]})
        context = Context.from_config(Dictionary(), config)
        assert "V-7" not in context.judgment_rules
