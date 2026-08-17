"""The [paths] table: mapping parts of a repository to genre profiles."""

from __future__ import annotations

from words_for_humans import engine
from words_for_humans.checks.context import ContextMap
from words_for_humans.config import Config
from words_for_humans.dictionary import Dictionary
from words_for_humans.rules import Severity


def _config(**data) -> Config:
    return Config.from_table({"profile": "code", **data})


class TestParsing:
    def test_mappings_keep_declaration_order(self):
        config = _config(paths={"docs/**": "prose-technical", "docs/plans/**": "prose-corporate"})
        assert config.paths == (
            ("docs/**", "prose-technical"),
            ("docs/plans/**", "prose-corporate"),
        )

    def test_a_mapping_accepts_the_old_profile_name(self):
        config = _config(paths={"src/**": "concise"})
        assert config.paths == (("src/**", "code"),)

    def test_a_mapping_to_an_unknown_profile_is_dropped(self):
        config = _config(paths={"docs/**": "no-such-profile"})
        assert config.paths == ()

    def test_a_paths_value_of_the_wrong_shape_is_ignored(self):
        assert _config(paths="docs/**").paths == ()


class TestResolution:
    def test_the_last_matching_pattern_wins(self):
        config = _config(paths={"docs/**": "prose-technical", "docs/plans/**": "prose-corporate"})
        assert config.profile_for("docs/design.md") == "prose-technical"
        assert config.profile_for("docs/plans/q3.md") == "prose-corporate"

    def test_an_unmatched_file_keeps_the_run_profile(self):
        config = _config(paths={"docs/**": "prose-technical"})
        assert config.profile_for("src/engine.py") == "code"

    def test_severity_overrides_survive_the_profile_switch(self):
        config = _config(
            paths={"plans/**": "prose-corporate"},
            severity={"A-10": "soft"},
        )
        corporate = config.for_profile(config.profile_for("plans/q3.md"))
        assert corporate.profile == "prose-corporate"
        assert "A-10" not in corporate.hard_rules
        assert "A-7" in corporate.hard_rules


class TestContextMap:
    def test_one_context_per_profile_and_it_is_cached(self):
        config = _config(paths={"plans/**": "prose-corporate"})
        contexts = ContextMap(Dictionary(), config)
        assert contexts.for_path("plans/a.md") is contexts.for_path("plans/b.md")
        assert contexts.for_path("plans/a.md") is not contexts.for_path("src/a.py")

    def test_the_mapped_context_carries_the_genre_contract(self):
        config = _config(paths={"plans/**": "prose-corporate"})
        contexts = ContextMap(Dictionary(), config)
        corporate = contexts.for_path("plans/q3.md")
        assert "A-6" in corporate.disabled_rules
        assert corporate.sentence_tiers is not None
        assert corporate.sentence_tiers["prose"] == (35, 50)
        default = contexts.for_path("README.md")
        assert default.sentence_tiers is not None
        assert default.sentence_tiers["prose"] == (30, 40)


class TestEndToEnd:
    def test_one_run_holds_two_genres(self, tmp_path):
        sentence = " ".join(["word"] * 44) + " end.\n"
        (tmp_path / "plans").mkdir()
        (tmp_path / "notes.md").write_text(sentence)
        (tmp_path / "plans" / "q3.md").write_text(sentence)
        (tmp_path / ".words-for-humans.toml").write_text(
            '[paths]\n"plans/**" = "prose-corporate"\n'
        )

        report = engine.run([str(tmp_path)], Config.load(tmp_path), tmp_path)

        severity = {f.path: f.severity for f in report.findings if f.rule_id == "C-1"}
        assert severity["notes.md"] is Severity.HARD
        assert severity["plans/q3.md"] is Severity.SOFT
