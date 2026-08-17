"""Tests for the optional part-of-speech backend. Skipped without the nlp extra."""

from __future__ import annotations

import pytest

pytest.importorskip("spacy")

from words_for_humans.checks import pos_backend

if not pos_backend.available():
    pytest.skip("en_core_web_sm not installed", allow_module_level=True)

from words_for_humans.checks.context import Context
from words_for_humans.checks.nouns import check_multi_word_noun
from words_for_humans.checks.verbs import check_passive_voice
from words_for_humans.dictionary import Dictionary
from words_for_humans.model import Segment, SegmentKind


def _seg(text: str) -> Segment:
    return Segment(path="x.md", line=1, kind=SegmentKind.MARKDOWN, text=text)


class TestNounClusters:
    def test_flags_a_stacked_noun_cluster(self):
        spans = pos_backend.noun_clusters("Replace the runway light connection resistance.")
        assert any("runway light connection resistance" in s.text for s in spans)

    def test_does_not_sweep_in_a_trailing_verb(self):
        # The regex bug: it flagged "...resistance calibration failed" (6 words).
        text = "The runway light connection resistance calibration failed."
        spans = pos_backend.noun_clusters(text)
        assert spans and all("failed" not in s.text for s in spans)

    def test_ignores_an_adjective_stack(self):
        assert pos_backend.noun_clusters("A large complex distributed system.") == []

    def test_code_noun_override_recovers_a_verb_tagged_stack(self):
        spans = pos_backend.noun_clusters("The read write lock manager instance.")
        assert any("read write lock" in s.text for s in spans)


class TestPassiveByAgent:
    def test_flags_passive_that_names_an_agent(self):
        assert len(pos_backend.passive_by_agent("The value is returned by the function.")) == 1

    def test_allows_agentless_passive(self):
        assert pos_backend.passive_by_agent("The row is locked.") == []

    def test_ignores_the_by_default_idiom(self):
        assert pos_backend.passive_by_agent("This is disabled by default.") == []

    def test_ignores_a_sort_key(self):
        assert pos_backend.passive_by_agent("Results are sorted by timestamp.") == []


class TestRouting:
    @staticmethod
    def _ctx(pos: bool) -> Context:
        return Context(dictionary=Dictionary(), pos=pos)

    def test_passive_routes_to_backend_when_pos_is_on(self):
        seg = Segment(path="x", line=1, kind=SegmentKind.COMMENT, text="The row is locked.")
        # Agentless: the POS path stays silent, the regex fallback reports.
        assert list(check_passive_voice(seg, self._ctx(pos=True))) == []
        assert len(list(check_passive_voice(seg, self._ctx(pos=False)))) == 1

    def test_noun_cluster_routes_to_backend_when_pos_is_on(self):
        seg = _seg("A large complex distributed system.")
        # Adjective stack: POS ignores it, the regex fallback over-reports.
        assert list(check_multi_word_noun(seg, self._ctx(pos=True))) == []
        assert len(list(check_multi_word_noun(seg, self._ctx(pos=False)))) == 1
