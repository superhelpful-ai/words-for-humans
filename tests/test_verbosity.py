"""The comment value rules, and the good comments they must leave alone.

Precision matters more here than anywhere else in the tool. A false positive on
these rules tells someone to delete a comment that was carrying information.
"""

from __future__ import annotations

from words_for_humans.checks import verbosity
from words_for_humans.checks.context import Context
from words_for_humans.dictionary import Dictionary
from words_for_humans.extract import comments
from words_for_humans.model import Segment, SegmentKind


def _run(check, text: str, code: str = "", kind=SegmentKind.COMMENT):
    segment = Segment(path="example.ts", line=1, kind=kind, text=text, follows_code=code)
    return list(check(segment, Context(dictionary=Dictionary())))


class TestRestatesCode:
    def test_a_comment_that_renames_the_declaration_is_reported(self):
        result = _run(
            verbosity.check_restates_code,
            "Calculate the cart total",
            "export function calculateCartTotal(items: CartItem[]): number {",
        )
        assert [f.rule_id for f in result] == ["V-1"]

    def test_a_comment_giving_a_reason_is_left_alone(self):
        result = _run(
            verbosity.check_restates_code,
            "Retry with backoff because the upstream limiter returns 429 in bursts.",
            "await retryWithBackoff(() => client.send(payload));",
        )
        assert result == []

    def test_a_comment_with_no_code_below_it_is_not_judged(self):
        result = _run(verbosity.check_restates_code, "Calculate the cart total", "")
        assert result == []

    def test_one_word_of_new_information_saves_the_comment(self):
        result = _run(
            verbosity.check_restates_code,
            "Parse the config lazily",
            "function parseConfig(source: string) {",
        )
        assert result == []


class TestFillerOpener:
    def test_filler_is_reported(self):
        for opener in [
            "It's worth noting that the cache expires after an hour.",
            "Note that the cache expires after an hour.",
            "Essentially, the cache expires after an hour.",
            "In summary, the cache expires after an hour.",
        ]:
            assert _run(verbosity.check_filler_opener, opener), opener

    def test_a_plain_statement_passes(self):
        assert _run(verbosity.check_filler_opener, "The cache expires after an hour.") == []


class TestNarration:
    def test_first_person_narration_is_reported(self):
        result = _run(verbosity.check_narration, "Let's parse the header first.")
        assert [f.rule_id for f in result] == ["V-3"]

    def test_walkthrough_framing_is_reported(self):
        for text in ("We'll retry on a 429.", "Now we flush the buffer.", "Here we hold the lock."):
            assert [f.rule_id for f in _run(verbosity.check_narration, text)] == ["V-3"], text

    def test_a_statement_of_fact_passes(self):
        assert _run(verbosity.check_narration, "The header is parsed before the body.") == []

    def test_a_bare_we_stating_a_design_fact_passes(self):
        facts = ("We store the result in a cache.", "We pin the version.", "We also use it.")
        for text in facts:
            assert _run(verbosity.check_narration, text) == [], text


class TestObviousOpener:
    def test_restating_the_declaration_is_reported(self):
        result = _run(verbosity.check_obvious_opener, "This function is responsible for parsing.")
        assert [f.rule_id for f in result] == ["V-4"]

    def test_a_comment_that_starts_with_the_verb_passes(self):
        assert _run(verbosity.check_obvious_opener, "Parses the header before the body.") == []


class TestPadding:
    def test_padding_is_reported_with_its_replacement(self):
        result = _run(verbosity.check_padding, "Loop over the items in order to sum them.")
        assert result[0].rule_id == "V-5"
        assert result[0].suggestion == 'Write "to".'

    def test_the_short_form_passes(self):
        assert _run(verbosity.check_padding, "Loop over the items to sum them.") == []


class TestFollowsCode:
    def test_the_extractor_captures_the_code_below_a_comment(self):
        source = "// Calculate the cart total\nfunction calculateCartTotal() {\n  return 0;\n}\n"
        segments = comments.extract("example.ts", source)
        assert segments
        assert "calculateCartTotal" in segments[0].follows_code

    def test_the_captured_code_makes_the_restatement_visible(self):
        source = "// Calculate the cart total\nfunction calculateCartTotal() {\n  return 0;\n}\n"
        segment = comments.extract("example.ts", source)[0]
        result = list(verbosity.check_restates_code(segment, Context(dictionary=Dictionary())))
        assert [f.rule_id for f in result] == ["V-1"]
