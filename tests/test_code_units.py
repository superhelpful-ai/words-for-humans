"""Code-unit extraction for the design rules."""

from __future__ import annotations

from words_for_humans.extract import code_units

_SOURCE = '''import os


def top(x):
    def nested():
        return x
    return nested


class Widget:
    """A widget."""

    def method(self):
        return 1
'''


class TestExtract:
    def test_it_returns_top_level_functions_and_classes(self):
        units = code_units.extract("m.py", _SOURCE)
        assert [(u.name, u.kind) for u in units] == [("top", "function"), ("Widget", "class")]

    def test_a_nested_function_is_not_a_separate_unit(self):
        units = code_units.extract("m.py", _SOURCE)
        top = next(u for u in units if u.name == "top")
        assert "def nested()" in top.source

    def test_a_method_stays_inside_its_class(self):
        units = code_units.extract("m.py", _SOURCE)
        widget = next(u for u in units if u.name == "Widget")
        assert "def method(self)" in widget.source

    def test_the_unit_records_its_start_line_and_signature(self):
        units = code_units.extract("m.py", _SOURCE)
        top = next(u for u in units if u.name == "top")
        assert top.line == 4
        assert top.signature == "def top(x):"

    def test_added_lines_are_carried_through(self):
        units = code_units.extract("m.py", _SOURCE, added_lines=frozenset({4, 5}))
        assert all(u.added_lines == frozenset({4, 5}) for u in units)


class TestLineMapping:
    def test_an_offset_maps_back_to_a_file_line(self):
        units = code_units.extract("m.py", _SOURCE)
        top = next(u for u in units if u.name == "top")
        # The unit starts at file line 4; "return nested" is its fourth line.
        offset = top.source.index("return nested")
        assert top.line_for_offset(offset) == 7


class TestUnsupported:
    def test_a_non_python_file_yields_nothing(self):
        assert code_units.extract("m.ts", "function f() { return 1; }") == []

    def test_a_file_that_does_not_parse_yields_nothing(self):
        assert code_units.extract("m.py", "def broken(:\n") == []

    def test_an_empty_file_yields_nothing(self):
        assert code_units.extract("m.py", "") == []
