"""The S- family: prose that must stand alone, with only the file in view."""

from __future__ import annotations

from words_for_humans.checks import standalone
from words_for_humans.checks.context import Context
from words_for_humans.dictionary import Dictionary
from words_for_humans.model import Segment, SegmentKind
from words_for_humans.rules import Severity


def _run(check, text: str, kind: SegmentKind = SegmentKind.COMMENT):
    segment = Segment(path="a.py", line=1, kind=kind, text=text)
    context = Context(dictionary=Dictionary())
    if not context.covers(segment, check):
        return []
    return list(check(segment, context))


class TestHistoryNarration:
    def test_review_feedback_narration_is_flagged(self):
        result = _run(standalone.check_history_narration, "Added retry per code review feedback.")
        assert [f.rule_id for f in result] == ["S-1"]
        assert result[0].severity is Severity.SOFT

    def test_meeting_narration_is_flagged(self):
        assert _run(standalone.check_history_narration, "Revised per our discussion.")
        assert _run(standalone.check_history_narration, "Fixed after PR #482.")

    def test_a_reason_is_not_flagged(self):
        text = "Retry here because the upstream API rate-limits in bursts."
        assert _run(standalone.check_history_narration, text) == []

    def test_runtime_senses_are_not_history(self):
        assert _run(standalone.check_history_narration, "Detoast the value as requested.") == []
        text = "Following the call to unshift(), the stream pauses."
        assert _run(standalone.check_history_narration, text) == []

    def test_a_cross_reference_or_citation_is_not_history(self):
        assert _run(standalone.check_history_narration, "As discussed in section 3.") == []
        text = "Per the discussion on pgsql-hackers, sampling is block level."
        assert _run(standalone.check_history_narration, text) == []

    def test_a_commit_message_is_exempt(self):
        text = "Added retry per code review feedback."
        assert _run(standalone.check_history_narration, text, SegmentKind.COMMIT) == []


class TestDiffComment:
    def test_an_edit_description_is_flagged(self):
        assert _run(standalone.check_diff_comment, "Changed this to a Map for performance.")
        assert _run(standalone.check_diff_comment, "Removed the old validation here.")
        assert _run(standalone.check_diff_comment, "This value used to be configurable.")

    def test_a_purpose_clause_is_not_a_diff(self):
        assert _run(standalone.check_diff_comment, "The parser is used to build the tree.") == []

    def test_the_current_behaviour_is_not_flagged(self):
        text = "A Map keeps lookups O(1); the hot path calls this per row."
        assert _run(standalone.check_diff_comment, text) == []

    def test_a_runtime_object_is_not_a_diff(self):
        text = "Join against the old version of the data to produce the diff."
        assert _run(standalone.check_diff_comment, text) == []
        text = "We should have just removed the old index here."
        assert _run(standalone.check_diff_comment, text) == []

    def test_a_commit_message_is_exempt(self):
        text = "Changed this to a Map for performance."
        assert _run(standalone.check_diff_comment, text, SegmentKind.COMMIT) == []


class TestReferenceAsExplanation:
    def test_a_bare_ticket_is_flagged(self):
        assert _run(standalone.check_reference_as_explanation, "See JIRA-1234.")
        assert _run(standalone.check_reference_as_explanation, "#482")
        assert _run(standalone.check_reference_as_explanation, "https://example.com/design-doc")

    def test_a_reference_next_to_an_explanation_passes(self):
        text = "Rounds half-up because invoices are reconciled in cents. See JIRA-1234."
        assert _run(standalone.check_reference_as_explanation, text) == []

    def test_a_stable_standard_is_exempt(self):
        assert _run(standalone.check_reference_as_explanation, "See RFC 7231.") == []
        assert _run(standalone.check_reference_as_explanation, "PEP 8") == []

    def test_a_license_url_is_exempt(self):
        url = "http://www.apache.org/licenses/LICENSE-2.0"
        assert _run(standalone.check_reference_as_explanation, url) == []

    def test_markdown_link_lists_are_outside_the_rule(self):
        url = "https://example.com/design-doc"
        assert _run(standalone.check_reference_as_explanation, url, SegmentKind.MARKDOWN) == []


class TestTimeAnchor:
    def test_bare_time_words_are_flagged_in_documentation(self):
        md = SegmentKind.MARKDOWN
        assert _run(standalone.check_time_anchor, "Currently behind a flag.", md)
        assert _run(standalone.check_time_anchor, "For now, retries are disabled.", md)
        assert _run(standalone.check_time_anchor, "Streaming will land soon.", md)

    def test_a_code_comment_is_outside_the_rule(self):
        text = "Skip it for now; the loop processes it when it finds the root."
        assert _run(standalone.check_time_anchor, text, SegmentKind.COMMENT) == []

    def test_a_legacy_name_without_an_anchor_is_flagged(self):
        text = "The legacy syntax is still accepted."
        result = _run(standalone.check_time_anchor, text, SegmentKind.MARKDOWN)
        assert [f.rule_id for f in result] == ["S-4"]

    def test_a_version_anchors_the_legacy_name(self):
        text = "The legacy syntax is still accepted until v3.0."
        assert _run(standalone.check_time_anchor, text, SegmentKind.MARKDOWN) == []

    def test_runtime_names_pass(self):
        md = SegmentKind.MARKDOWN
        assert _run(standalone.check_time_anchor, "The new parser handles unicode.", md) == []
        assert _run(standalone.check_time_anchor, "The latest tuple wins the merge.", md) == []

    def test_eventually_consistent_is_a_term_not_a_promise(self):
        text = "Reads are eventually consistent."
        assert _run(standalone.check_time_anchor, text, SegmentKind.MARKDOWN) == []
