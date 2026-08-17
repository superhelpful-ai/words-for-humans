"""One test per rule the CLI decides, plus the false positives worth guarding."""

from __future__ import annotations

from words_for_humans.checks import nouns, punctuation, recommendations, sentences, verbs, words
from words_for_humans.model import SegmentKind


class TestSentenceLength:
    def test_a_long_description_breaks_sentence_length(self, findings):
        text = "The " + "long " * 30 + "sentence."
        result = findings(sentences.check_sentence_length, text)
        assert [f.rule_id for f in result] == ["C-1"]

    def test_a_long_instruction_breaks_sentence_length(self, findings):
        text = "Remove " + "the cover and " * 8 + "the seal."
        result = findings(sentences.check_sentence_length, text)
        assert [f.rule_id for f in result] == ["C-1"]

    def test_a_short_sentence_passes(self, findings):
        assert findings(sentences.check_sentence_length, "Remove the cover.") == []

    def test_a_twenty_five_word_description_is_at_the_limit(self, findings):
        text = " ".join(["word"] * 25) + "."
        assert findings(sentences.check_sentence_length, text) == []


class TestSentenceLengthTiers:
    """The two-tier warn/fail behaviour of `concise`, over Context.from_config."""

    @staticmethod
    def _run(words: int, kind: SegmentKind, **data):
        from words_for_humans.checks.context import Context
        from words_for_humans.config import Config
        from words_for_humans.dictionary import Dictionary
        from words_for_humans.model import Segment

        table = {"profile": "concise", **data}
        context = Context.from_config(Dictionary(), Config.from_table(table))
        text = " ".join(["word"] * (words - 1)) + " end."
        segment = Segment(path="x.py", line=1, kind=kind, text=text)
        return [(f.rule_id, f.severity) for f in sentences.check_sentence_length(segment, context)]

    def test_code_warns_above_twenty_five(self):
        from words_for_humans.rules import Severity

        assert self._run(24, SegmentKind.COMMENT) == []
        assert self._run(30, SegmentKind.COMMENT) == [("C-1", Severity.SOFT)]

    def test_code_fails_above_thirty_five(self):
        from words_for_humans.rules import Severity

        assert self._run(40, SegmentKind.COMMENT) == [("C-1", Severity.HARD)]

    def test_prose_is_held_looser_than_code(self):
        from words_for_humans.rules import Severity

        # 33 words: over the code fail count, only a warning in prose.
        assert self._run(33, SegmentKind.MARKDOWN) == [("C-1", Severity.SOFT)]
        assert self._run(45, SegmentKind.MARKDOWN) == [("C-1", Severity.HARD)]

    def test_a_commit_never_fails(self):
        from words_for_humans.rules import Severity

        assert self._run(60, SegmentKind.COMMIT) == [("C-1", Severity.SOFT)]

    def test_config_overrides_a_tier(self):
        from words_for_humans.rules import Severity

        override = {"sentence_length": {"code": [10, 15]}}
        assert self._run(12, SegmentKind.COMMENT, **override) == [("C-1", Severity.SOFT)]
        assert self._run(18, SegmentKind.COMMENT, **override) == [("C-1", Severity.HARD)]


class TestParagraphLength:
    def test_seven_sentences_break_paragraph_length(self, findings):
        text = " ".join(f"Sentence number {n}." for n in range(7))
        result = findings(sentences.check_paragraph_length, text)
        assert [f.rule_id for f in result] == ["C-2"]

    def test_six_sentences_are_at_the_limit(self, findings):
        text = " ".join(f"Sentence number {n}." for n in range(6))
        assert findings(sentences.check_paragraph_length, text) == []


class TestContractions:
    def test_a_contraction_breaks_rule_4_2(self, findings):
        result = findings(sentences.check_contractions, "The valve doesn't open.")
        assert result[0].rule_id == "4.2"
        assert result[0].suggestion == 'Write "does not".'


class TestPassiveVoice:
    def test_a_passive_clause_breaks_passive_voice(self, findings):
        result = findings(verbs.check_passive_voice, "The cover was removed by the technician.")
        assert [f.rule_id for f in result] == ["C-3"]

    def test_an_active_clause_passes(self, findings):
        assert findings(verbs.check_passive_voice, "The technician removed the cover.") == []

    def test_a_predicate_adjective_is_not_passive(self, findings):
        assert findings(verbs.check_passive_voice, "The field is required.") == []


class TestVerbTense:
    def test_a_continuous_tense_breaks_rule_3_2(self, findings):
        result = findings(verbs.check_verb_tense, "The pump is running at full speed.")
        assert [f.rule_id for f in result] == ["3.2"]

    def test_a_perfect_tense_breaks_rule_3_2(self, findings):
        result = findings(verbs.check_verb_tense, "The queries have drifted apart.")
        assert [f.rule_id for f in result] == ["3.2"]

    def test_a_modal_with_an_infinitive_is_not_a_perfect_tense(self, findings):
        assert findings(verbs.check_verb_tense, "The embed would have to stop.") == []

    def test_an_ing_noun_is_not_a_continuous_tense(self, findings):
        assert findings(verbs.check_verb_tense, "The setting is correct.") == []

    def test_the_simple_present_passes(self, findings):
        assert findings(verbs.check_verb_tense, "The pump runs at full speed.") == []


class TestAuxiliaryStack:
    def test_a_stacked_auxiliary_breaks_rule_3_4(self, findings):
        result = findings(verbs.check_auxiliary_stack, "The reader will be able to see it.")
        assert [f.rule_id for f in result] == ["3.4"]


class TestGerund:
    def test_a_gerund_after_a_preposition_breaks_rule_3_5(self, findings):
        result = findings(verbs.check_gerund, "Check the value before converting it.")
        assert [f.rule_id for f in result] == ["3.5"]

    def test_a_technical_noun_in_ing_passes(self, findings):
        assert findings(verbs.check_gerund, "Errors go through logging first.") == []


class TestMultiWordNoun:
    def test_four_words_break_noun_cluster(self, findings):
        result = findings(
            nouns.check_multi_word_noun, "Replace the runway light connection resistance."
        )
        assert [f.rule_id for f in result] == ["C-4"]

    def test_three_words_are_at_the_limit(self, findings):
        assert findings(nouns.check_multi_word_noun, "Replace the runway light connection.") == []

    def test_a_run_does_not_cross_a_sentence_boundary(self, findings):
        assert findings(nouns.check_multi_word_noun, "Check the pump. Two valves ship.") == []

    def test_a_modal_or_conjunctive_adverb_breaks_the_run(self, findings):
        # These are clauses, not noun clusters: the run must stop at "cannot"
        # and "therefore" rather than spanning the predicate.
        run = nouns.check_multi_word_noun
        assert findings(run, "The frame counter cannot drift over time.") == []
        assert findings(run, "The write buffer therefore stays small.") == []

    def test_a_run_does_not_cross_a_comma(self, findings):
        assert findings(nouns.check_multi_word_noun, "Use the pump, valve, seal and cover.") == []

    def test_a_finite_verb_ends_the_run(self, findings):
        assert findings(nouns.check_multi_word_noun, "The app needs one more field.") == []


class TestWords:
    def test_british_spelling_breaks_rule_1_14(self, findings):
        result = findings(words.check_spelling, "The colour of the cover is red.")
        assert result[0].rule_id == "1.14"
        assert result[0].suggestion == 'Write "color".'

    def test_an_ise_suffix_breaks_rule_1_14(self, findings):
        result = findings(words.check_spelling, "Normalise the value first.")
        assert result[0].suggestion == 'Write "Normalize".'

    def test_an_american_ise_word_passes(self, findings):
        assert findings(words.check_spelling, "Advertise the new release.") == []

    def test_a_word_the_dictionary_rejects_breaks_rule_1_1(self, findings):
        result = findings(words.check_unapproved_words, "Utilize the second pump.")
        assert result[0].rule_id == "1.1"
        assert result[0].suggestion == "Use use."

    def test_jargon_breaks_no_slang(self, findings):
        result = findings(words.check_jargon, "This is a janky workaround.")
        assert [f.rule_id for f in result] == ["C-5"]

    def test_gross_before_a_financial_noun_passes(self, findings):
        assert findings(words.check_jargon, "Sum the gross revenue for each supplier.") == []
        assert findings(words.check_jargon, "The gross margin stays above ten percent.") == []
        assert findings(words.check_jargon, "Report the gross merchandise value monthly.") == []

    def test_gross_without_a_financial_noun_breaks_no_slang(self, findings):
        result = findings(words.check_jargon, "This gross workaround must go away.")
        assert [f.rule_id for f in result] == ["C-5"]

    def test_a_phrasal_verb_breaks_rule_9_3(self, findings):
        result = findings(words.check_phrasal_verbs, "Carry out the test after the reset.")
        assert [f.rule_id for f in result] == ["9.3"]


class TestPunctuation:
    def test_a_semicolon_breaks_rule_8_1(self, findings):
        result = findings(punctuation.check_semicolon, "Open the valve; close the vent.")
        assert [f.rule_id for f in result] == ["8.1"]

    def test_a_semicolon_in_an_html_entity_passes(self, findings):
        assert findings(punctuation.check_semicolon, "Write &amp; for an ampersand here.") == []


class TestRecommendations:
    def test_a_latin_abbreviation_breaks_gr_6(self, findings):
        result = findings(recommendations.check_latin_abbreviations, "Use a cache, e.g. Redis.")
        assert "GR-6" in [f.rule_id for f in result]

    def test_non_inclusive_language_breaks_gr_7(self, findings):
        result = findings(recommendations.check_inclusive_language, "Add it to the whitelist now.")
        assert result[0].suggestion == 'Use "allowlist".'

    def test_a_bare_this_breaks_gr_4(self, findings):
        result = findings(recommendations.check_bare_this, "This is the reason for the delay.")
        assert [f.rule_id for f in result] == ["GR-4"]

    def test_a_possessive_breaks_gr_8(self, findings):
        result = findings(recommendations.check_possessive, "Read the app's configuration file.")
        assert result[0].suggestion == 'Write "of the app".'

    def test_a_contraction_is_not_reported_as_a_possessive(self, findings):
        assert findings(recommendations.check_possessive, "It's the wrong value.") == []


class TestSeverity:
    def test_an_identifier_finding_never_fails_a_run(self, context, segment):
        from words_for_humans.rules import Severity

        target = segment("the colour value", SegmentKind.IDENTIFIER)
        result = list(words.check_spelling(target, context))
        assert result and all(f.severity is Severity.SOFT for f in result)

    def test_a_comment_finding_can_fail_a_run(self, context, segment):
        from words_for_humans.rules import Severity

        target = segment("Open the valve; close the vent.", SegmentKind.COMMENT)
        result = list(punctuation.check_semicolon(target, context))
        assert result and result[0].severity is Severity.HARD
