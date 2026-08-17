"""The shareable HTML report."""

from __future__ import annotations

from words_for_humans import report
from words_for_humans.model import Finding, Report, SegmentKind
from words_for_humans.rules import Severity


def _finding(
    rule_id: str,
    *,
    path: str = "src/cart.ts",
    line: int = 1,
    message: str = "",
    excerpt: str = "text",
    suggestion: str | None = None,
    severity: Severity = Severity.HARD,
    segment_text: str = "",
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        path=path,
        line=line,
        kind=SegmentKind.COMMENT,
        message=message or f"finding for {rule_id}",
        excerpt=excerpt,
        suggestion=suggestion,
        segment_text=segment_text,
    )


def _report(findings: list[Finding], **counts) -> Report:
    return Report(
        findings=findings,
        files_scanned=counts.get("files_scanned", 3),
        segments_scanned=counts.get("segments_scanned", 40),
    )


class TestHtmlShape:
    def test_it_is_a_self_contained_document(self):
        html = report.as_html(_report([_finding("V-1")]))
        assert html.startswith("<!doctype html>")
        assert "<style>" in html and "</style>" in html
        assert "http://" not in html and "src=" not in html

    def test_the_repo_name_is_shown_in_the_title_and_heading(self):
        html = report.as_html(_report([_finding("V-1")]), repo="acme-web")
        assert "<title>Words for Humans — acme-web</title>" in html
        assert "acme-web" in html

    def test_the_headline_is_the_total_and_the_hard_count(self):
        findings = [_finding("V-1"), _finding("A-2"), _finding("C-3", severity=Severity.SOFT)]
        html = report.as_html(_report(findings))
        assert ">3<" in html  # total
        assert "2 of them serious enough to fail a build" in html

    def test_the_stats_report_what_was_read(self):
        html = report.as_html(_report([_finding("V-1")], files_scanned=59, segments_scanned=470))
        assert "59" in html and "files read" in html
        assert "470" in html and "pieces of text checked" in html


class TestExamples:
    def test_ai_tells_and_comment_value_come_before_length_rules(self):
        findings = [
            _finding("C-1", severity=Severity.SOFT, excerpt="a long sentence"),
            _finding("A-5", excerpt="in a real implementation"),
        ]
        html = report.as_html(_report(findings))
        assert html.index("A-5") < html.index("a long sentence")

    def test_no_single_rule_floods_the_examples(self):
        findings = [_finding("C-1", line=n, excerpt=f"sentence {n}") for n in range(10)]
        examples = report._select_examples(findings)
        assert sum(1 for f in examples if f.rule_id == "C-1") <= 3

    def test_identical_text_is_not_shown_twice(self):
        findings = [
            _finding("A-3", excerpt="", segment_text="the same paragraph"),
            _finding("A-5", excerpt="", segment_text="the same paragraph"),
        ]
        examples = report._select_examples(findings)
        assert len(examples) == 1

    def test_the_whole_comment_is_shown_when_it_was_kept(self):
        finding = _finding("V-1", excerpt="trimmed", segment_text="the whole comment")
        html = report.as_html(_report([finding]))
        assert "the whole comment" in html


class TestSafety:
    def test_code_in_a_finding_cannot_break_the_page(self):
        html = report.as_html(_report([_finding("V-1", excerpt="<script>alert(1)</script>")]))
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestEmpty:
    def test_a_clean_repository_reports_zero(self):
        html = report.as_html(_report([], files_scanned=12, segments_scanned=88))
        assert "Nothing to cut" in html
        assert "The clearest examples" not in html
