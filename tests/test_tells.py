"""The AI tell detectors, and the human prose they must not touch.

Every rule here fires on a phrase a person might legitimately write, so each
test pairs the tell with a sentence that must survive.
"""

from __future__ import annotations

from words_for_humans.checks import tells
from words_for_humans.checks.context import Context
from words_for_humans.classifier import NullClassifier, features, vector
from words_for_humans.dictionary import Dictionary
from words_for_humans.model import Segment, SegmentKind


def _run(check, text: str, kind=SegmentKind.COMMENT, code: str = ""):
    segment = Segment(path="a.ts", line=1, kind=kind, text=text, follows_code=code)
    return list(check(segment, Context(dictionary=Dictionary())))


class TestAntithesis:
    def test_definition_by_negation_is_reported(self):
        assert _run(
            tells.check_antithesis,
            "This is not just a cache, it is a consistency boundary.",
        )

    def test_a_plain_negation_passes(self):
        assert _run(tells.check_antithesis, "The value is not cached between calls.") == []


class TestMarketingLanguage:
    def test_praise_adjectives_are_reported(self):
        result = _run(tells.check_marketing_language, "A robust and seamless retry layer.")
        assert {f.rule_id for f in result} == {"A-2"}
        assert len(result) == 2

    def test_measurable_description_passes(self):
        assert _run(tells.check_marketing_language, "Retries four times over ten seconds.") == []


class TestEnumeratedVirtues:
    def test_an_announced_list_is_reported(self):
        assert _run(tells.check_enumerated_virtues, "This approach has several benefits:")

    def test_a_plain_list_intro_passes(self):
        assert _run(tells.check_enumerated_virtues, "The parser handles three formats:") == []


class TestDoubleHedge:
    def test_stacked_hedges_are_reported(self):
        assert _run(tells.check_double_hedge, "This might potentially block the loop.")

    def test_a_single_hedge_passes(self):
        assert _run(tells.check_double_hedge, "This might block the loop.") == []


class TestUnfinished:
    def test_an_admission_of_incompleteness_is_reported(self):
        for text in [
            "Error handling omitted for brevity.",
            "In a real implementation you would validate the payload.",
            "This is a simplified version of the upstream algorithm.",
        ]:
            assert _run(tells.check_unfinished, text), text

    def test_a_finished_comment_passes(self):
        assert _run(tells.check_unfinished, "Validates the payload against the schema.") == []


class TestDecorativeEmoji:
    def test_an_emoji_is_reported(self):
        assert _run(tells.check_decorative_emoji, "Getting started with the parser 🚀")

    def test_plain_text_passes(self):
        assert _run(tells.check_decorative_emoji, "Getting started with the parser") == []


class TestPlaceholder:
    def test_a_placeholder_credential_is_reported(self):
        assert _run(tells.check_placeholder, "Set the header to your-api-key before calling.")

    def test_a_real_instruction_passes(self):
        assert _run(tells.check_placeholder, "Read the key from the STRIPE_KEY variable.") == []


class TestStepNarration:
    def test_three_numbered_steps_are_reported(self):
        text = "1. Open the file\n2. Read the header\n3. Close the file"
        assert _run(tells.check_step_narration, text)

    def test_two_numbered_lines_pass(self):
        assert _run(tells.check_step_narration, "1. Open the file\n2. Close the file") == []


class TestReflexiveHedge:
    def test_the_no_answer_opener_is_reported(self):
        assert _run(
            tells.check_double_hedge,
            "There is no one-size-fits-all answer, but caching helps.",
        )

    def test_a_real_qualification_passes(self):
        assert _run(tells.check_double_hedge, "This blocks the loop when the queue is full.") == []


class TestEmDash:
    def test_an_em_dash_is_reported(self):
        result = _run(tells.check_em_dash, "This runs fast — usually.")
        assert {f.rule_id for f in result} == {"A-10"}

    def test_a_spaced_en_dash_is_not_reported(self):
        assert _run(tells.check_em_dash, "The parser reads bytes \u2013 not lines.") == []

    def test_a_numeric_range_passes(self):
        assert _run(tells.check_em_dash, "Retry between 10-20 times.") == []

    def test_it_does_not_run_on_user_facing_strings(self):
        assert SegmentKind.STRING not in tells.check_em_dash.kinds
        assert SegmentKind.COMMENT in tells.check_em_dash.kinds


class TestTriad:
    def test_stacked_negated_fragments_are_reported(self):
        assert _run(tells.check_triad, "Not a cache. Just a boundary.")

    def test_a_single_negation_passes(self):
        assert _run(tells.check_triad, "This is not cached. It reads the file once.") == []


class TestThroatClearing:
    def test_a_pleasant_opener_is_reported(self):
        for text in ["Great question! The parser reads bytes.", "Certainly, here is the reason."]:
            assert _run(tells.check_throat_clearing, text), text

    def test_plain_content_passes(self):
        assert _run(tells.check_throat_clearing, "The parser reads bytes off the socket.") == []


class TestSummaryCloser:
    def test_an_announced_summary_is_reported(self):
        assert _run(tells.check_summary_closer, "In conclusion, the retry helps under load.")

    def test_the_word_overall_in_a_sentence_passes(self):
        assert _run(tells.check_summary_closer, "Overall latency dropped by half.") == []


class TestMetaNarration:
    def test_narration_of_answering_is_reported(self):
        for text in ["Let's dive in to the parser.", "This section will walk you through setup."]:
            assert _run(tells.check_meta_narration, text), text

    def test_a_plain_description_passes(self):
        assert _run(tells.check_meta_narration, "The setup step writes the config file.") == []


class TestClassifierSeam:
    def test_the_null_classifier_scores_nothing(self):
        segment = Segment(path="a.ts", line=1, kind=SegmentKind.COMMENT, text="Anything.")
        assert NullClassifier().score(segment).is_bloated is False

    def test_features_are_extracted_for_every_declared_name(self):
        segment = Segment(
            path="a.ts",
            line=1,
            kind=SegmentKind.COMMENT,
            text="This might generally be considered a reasonable implementation.",
            follows_code="function run() {}",
        )
        extracted = features(segment)
        assert extracted["hedge_rate"] > 0
        assert len(vector(segment)) == len(extracted)

    def test_a_comment_over_no_code_has_no_ratio(self):
        segment = Segment(path="a.ts", line=1, kind=SegmentKind.COMMENT, text="A note.")
        assert features(segment)["comment_to_code_ratio"] == 0.0
