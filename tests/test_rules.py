"""The catalogue after the Clarity collapse: families and deprecation."""

from __future__ import annotations

from words_for_humans.rules import CATALOGUE


class TestClarityFamily:
    def test_the_collapsed_rules_carry_c_ids(self):
        assert CATALOGUE["C-1"].slug == "sentence-length"
        assert CATALOGUE["C-6"].slug == "clear-referent"
        assert CATALOGUE["C-6"].decidability.value == "judgment"

    def test_the_old_ids_are_gone(self):
        for old in ("1.10", "2.1", "3.6", "5.1", "6.3", "6.6", "GR-3", "GR-7"):
            assert old not in CATALOGUE, old


class TestDeprecation:
    def test_the_numbered_and_gr_sections_are_deprecated(self):
        assert CATALOGUE["3.4"].deprecated
        assert CATALOGUE["GR-6"].deprecated

    def test_the_letter_families_are_not(self):
        for rule_id in ("C-1", "C-6", "V-1", "A-10", "D-1"):
            assert not CATALOGUE[rule_id].deprecated, rule_id
