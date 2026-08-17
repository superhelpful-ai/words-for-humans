"""Databricks notebook exports must not read as MAGIC-prefixed comments."""

from __future__ import annotations

from pathlib import Path

from words_for_humans.checks import words
from words_for_humans.checks.context import Context
from words_for_humans.dictionary import Dictionary
from words_for_humans.extract import databricks, extract_file
from words_for_humans.model import SegmentKind

_FIXTURE = Path(__file__).parent / "fixtures" / "databricks_notebook.py"
_SCOPES = {SegmentKind.COMMENT, SegmentKind.DOCSTRING, SegmentKind.MARKDOWN}


def _segments():
    return extract_file("notebook.py", _FIXTURE.read_text(), scopes=_SCOPES)


class TestDetection:
    def test_an_exported_notebook_is_recognised(self):
        assert databricks.is_notebook("notebook.py", _FIXTURE.read_text())

    def test_an_ordinary_python_file_is_not(self):
        assert not databricks.is_notebook("module.py", "# A plain comment.\nx = 1\n")

    def test_a_non_python_file_is_not(self):
        assert not databricks.is_notebook("notebook.sql", "# Databricks notebook source")


class TestSplit:
    def test_both_views_keep_the_line_count(self):
        source = _FIXTURE.read_text()
        code, markdown = databricks.split(source)
        assert code.count("\n") == markdown.count("\n") == source.rstrip("\n").count("\n")


class TestExtraction:
    def test_the_magic_token_never_reaches_a_segment(self):
        assert all("MAGIC" not in s.text for s in _segments())

    def test_the_command_separators_produce_no_segment(self):
        assert all("COMMAND" not in s.text for s in _segments())

    def test_a_markdown_cell_is_extracted_as_markdown(self):
        markdown = [s for s in _segments() if s.kind is SegmentKind.MARKDOWN]
        assert any("aggregates the gross revenue" in s.text for s in markdown)

    def test_a_sql_cell_produces_no_segment(self):
        assert all("count(*)" not in s.text for s in _segments())

    def test_markdown_line_numbers_point_into_the_export(self):
        [paragraph] = [s for s in _segments() if "aggregates" in s.text]
        assert paragraph.line == 5

    def test_an_ordinary_comment_keeps_its_line_number(self):
        [comment] = [s for s in _segments() if s.kind is SegmentKind.COMMENT]
        assert "runs once for each day" in comment.text
        assert comment.line == 11

    def test_no_slang_reports_nothing_for_the_export(self):
        context = Context(dictionary=Dictionary())
        found = [f for s in _segments() for f in words.check_jargon(s, context)]
        assert found == []
