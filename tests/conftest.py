from __future__ import annotations

import pytest

from words_for_humans.checks.context import Context
from words_for_humans.dictionary import Dictionary
from words_for_humans.model import Segment, SegmentKind


@pytest.fixture
def context() -> Context:
    return Context(
        dictionary=Dictionary(not_approved={"utilize": ["use (v)"], "ensure": ["make sure (v)"]})
    )


@pytest.fixture
def segment():
    def build(text: str, kind: SegmentKind = SegmentKind.COMMENT, line: int = 1) -> Segment:
        return Segment(path="example.py", line=line, kind=kind, text=text)

    return build


@pytest.fixture
def findings(context, segment):
    """Run one check over one piece of text and return the rule ids it reports."""

    def run(check, text: str, kind: SegmentKind = SegmentKind.COMMENT):
        return list(check(segment(text, kind), context))

    return run
