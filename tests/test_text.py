"""Word counting and sentence splitting, which every length rule depends on."""

from __future__ import annotations

import pytest

from words_for_humans.model import Register
from words_for_humans.text import (
    detect_register,
    split_paragraphs,
    split_sentences,
    ste_words,
    strip_code,
)


class TestSteWordCount:
    def test_plain_sentence_counts_each_word(self):
        assert len(ste_words("Remove the cover from the housing")) == 6

    def test_rule_8_5_counts_a_parenthesis_group_as_one_word(self):
        assert len(ste_words("Install the screws (2) in the flange")) == 7
        assert len(ste_words("Install the screws in the flange")) == 6

    def test_rule_8_6_counts_a_number_with_its_unit_as_one_word(self):
        assert ste_words("Drain 2 liters of fuel") == ["Drain", "2 liters", "of", "fuel"]

    def test_rule_8_6_counts_quoted_text_as_one_word(self):
        assert len(ste_words('The status is "ready for review" now')) == 5

    def test_rule_8_7_counts_a_hyphenated_word_as_one_word(self):
        assert len(ste_words("Use the service-account key")) == 4

    def test_the_specification_example_counts_fourteen_words(self):
        sentence = "Install the three auxiliary screws (2) in the flange of the motor assembly (9)."
        assert len(ste_words(sentence)) == 14

    def test_trailing_punctuation_does_not_create_a_word(self):
        assert len(ste_words("Stop the pump, then open the valve.")) == 7


class TestStripCode:
    def test_inline_code_is_kept_not_replaced_with_a_placeholder(self):
        out = strip_code("Decide which `Factory` to use for the tests.")
        assert "`Factory`" in out
        assert "(code)" not in out

    def test_inline_code_still_counts_as_one_word(self):
        assert len(ste_words("Call `client.send(payload)` before the loop.")) == 5
        assert len(ste_words("Call it before the loop.")) == 5

    def test_a_fenced_block_is_dropped(self):
        assert "secret" not in strip_code("Intro.\n```\nsecret = 1\n```\nOutro.")

    def test_a_markdown_link_keeps_its_text_and_loses_the_url(self):
        out = strip_code("See the [setup guide](https://example.com/setup) first.")
        assert "setup guide" in out
        assert "example.com" not in out


class TestSentenceSplitting:
    def test_splits_on_a_period(self):
        assert len(split_sentences("Open the valve. Close the vent.")) == 2

    def test_does_not_split_on_a_decimal(self):
        assert len(split_sentences("The limit is 2.5 bar in normal use.")) == 1

    def test_does_not_split_on_a_dotted_identifier(self):
        assert len(split_sentences("Call config.load before the first read.")) == 1

    def test_does_not_split_on_a_known_abbreviation(self):
        assert len(split_sentences("Use a cache, e.g. Redis, for the lookup.")) == 1

    def test_splits_when_a_bold_marker_follows_the_period(self):
        # "**A bold lead-in.** The rest." is two sentences: the closing ** sits
        # between the period and the space, and must not merge the clauses.
        sentences = split_sentences("**Reset the counter.** The vent stays closed.")
        assert len(sentences) == 2
        assert sentences[1].word_count == 4

    def test_offsets_point_back_into_the_source(self):
        sentences = split_sentences("First one. Second one.")
        assert sentences[1].offset == 11


class TestRegister:
    def test_an_opening_imperative_is_procedural(self):
        assert detect_register("Remove the cover assembly") is Register.PROCEDURAL

    def test_a_statement_is_descriptive(self):
        assert detect_register("The cover assembly holds the seal") is Register.DESCRIPTIVE

    def test_a_verb_used_as_a_subject_noun_is_not_an_instruction(self):
        assert detect_register("Log output is written to stdout") is Register.DESCRIPTIVE

    @pytest.mark.parametrize("sentence", ["Do not open the valve.", "Don't open the valve."])
    def test_a_negative_command_is_procedural(self, sentence):
        assert detect_register(sentence) is Register.PROCEDURAL


class TestParagraphs:
    def test_splits_on_a_blank_line(self):
        assert len(split_paragraphs("One line.\n\nAnother line.")) == 2

    def test_a_single_block_is_one_paragraph(self):
        assert len(split_paragraphs("One line.\nStill the same block.")) == 1
