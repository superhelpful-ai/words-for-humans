"""Output formats: readable text, JSON, SARIF, and a shareable HTML page."""

from __future__ import annotations

import html
import json
import os
import sys
from collections import Counter

from .model import Finding, Report, SegmentKind
from .rules import CATALOGUE, Severity

_COLOURS = {
    "red": "\033[31m",
    "yellow": "\033[33m",
    "grey": "\033[90m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def _supports_colour(stream) -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("CI"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def _paint(text: str, colour: str, enabled: bool) -> str:
    return f"{_COLOURS[colour]}{text}{_COLOURS['reset']}" if enabled else text


def text(report: Report, stream=sys.stdout, *, show_soft: bool = True) -> None:
    """Print the full findings and the summary to one stream."""
    colour = _supports_colour(stream)
    detail(report, stream, show_soft=show_soft, colour=colour)
    _summary(report, stream, colour, show_soft)


def _rule_tag(rule_id: str) -> str:
    """The rule code with its slug, so a line reads without the catalogue."""
    rule = CATALOGUE.get(rule_id)
    return f"{rule_id} {rule.slug}" if rule else rule_id


def detail(
    report: Report, stream=sys.stdout, *, show_soft: bool = True, colour: bool | None = None
) -> None:
    """Print one block per finding, grouped by file. No summary."""
    if colour is None:
        colour = _supports_colour(stream)
    findings = report.findings if show_soft else report.hard

    current_path = None
    for finding in findings:
        if finding.path != current_path:
            current_path = finding.path
            print(f"\n{_paint(current_path, 'bold', colour)}", file=stream)

        level = "error" if finding.severity is Severity.HARD else "warn"
        tint = "red" if finding.severity is Severity.HARD else "yellow"
        location = f"  {finding.line}:"
        print(
            f"{location:<7} {_paint(level, tint, colour)} "
            f"{_paint(f'[{_rule_tag(finding.rule_id)}]', 'grey', colour)} {finding.message}",
            file=stream,
        )
        print(f"        {_paint(finding.excerpt, 'grey', colour)}", file=stream)
        if finding.suggestion:
            print(f"        {_paint('→ ' + finding.suggestion, 'grey', colour)}", file=stream)


def summary(
    report: Report, stream=sys.stdout, *, show_soft: bool = True, colour: bool | None = None
) -> None:
    """Print the counts and the most frequent rules. No per-finding detail."""
    if colour is None:
        colour = _supports_colour(stream)
    _summary(report, stream, colour, show_soft)


def _summary(report: Report, stream, colour: bool, show_soft: bool) -> None:
    hard = len(report.hard)
    soft = len(report.soft)

    print(
        f"\n{report.files_scanned} files, {report.segments_scanned} pieces of text checked.",
        file=stream,
    )
    if not report.findings:
        print(_paint("No ASD-STE100 findings.", "bold", colour), file=stream)
        return

    parts = [_paint(f"{hard} failing", "red", colour) if hard else "0 failing"]
    if show_soft:
        parts.append(_paint(f"{soft} warnings", "yellow", colour) if soft else "0 warnings")
    if report.suppressed:
        parts.append(f"{report.suppressed} suppressed")
    print(", ".join(parts) + ".", file=stream)

    findings = report.findings if show_soft else report.hard
    counts = Counter(f.rule_id for f in findings)
    print("\nMost frequent rules:", file=stream)
    for rule_id, count in counts.most_common(8):
        rule = CATALOGUE.get(rule_id)
        slug = rule.slug if rule else ""
        summary = rule.summary if rule else ""
        print(f"  {count:>4}  {rule_id:<5} {slug:<22} {summary}", file=stream)


def as_json(report: Report) -> str:
    return json.dumps(
        {
            "files_scanned": report.files_scanned,
            "segments_scanned": report.segments_scanned,
            "suppressed": report.suppressed,
            "summary": {
                "hard": len(report.hard),
                "soft": len(report.soft),
                "by_rule": dict(Counter(f.rule_id for f in report.findings).most_common()),
            },
            "findings": [_finding_dict(f) for f in report.findings],
        },
        indent=2,
    )


def _finding_dict(finding: Finding) -> dict:
    return {
        "rule": finding.rule_id,
        "section": finding.section,
        "rule_summary": finding.rule_summary,
        "severity": finding.severity.value,
        "path": finding.path,
        "line": finding.line,
        "kind": finding.kind.value,
        "message": finding.message,
        "excerpt": finding.excerpt,
        "suggestion": finding.suggestion,
    }


def as_sarif(report: Report) -> str:
    """SARIF 2.1.0, for GitHub code scanning and other review surfaces."""
    rules_used = sorted({f.rule_id for f in report.findings})
    return json.dumps(
        {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "words-for-humans",
                            "informationUri": "https://www.asd-ste100.org/",
                            "rules": [
                                {
                                    "id": rule_id,
                                    "name": f"ASD-STE100 rule {rule_id}",
                                    "shortDescription": {
                                        "text": CATALOGUE[rule_id].summary
                                        if rule_id in CATALOGUE
                                        else rule_id
                                    },
                                    "properties": {
                                        "section": CATALOGUE[rule_id].section
                                        if rule_id in CATALOGUE
                                        else ""
                                    },
                                }
                                for rule_id in rules_used
                            ],
                        }
                    },
                    "results": [
                        {
                            "ruleId": f.rule_id,
                            "level": "error" if f.severity is Severity.HARD else "warning",
                            "message": {
                                "text": f.message + (f" {f.suggestion}" if f.suggestion else "")
                            },
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": f.path},
                                        "region": {"startLine": max(f.line, 1)},
                                    }
                                }
                            ],
                        }
                        for f in report.findings
                        if f.kind is not SegmentKind.COMMIT
                    ],
                }
            ],
        },
        indent=2,
    )


def as_github_annotations(report: Report) -> str:
    """GitHub Actions workflow commands, for inline pull request annotations."""
    lines = []
    for finding in report.findings:
        if finding.kind is SegmentKind.COMMIT:
            continue
        level = "error" if finding.severity is Severity.HARD else "warning"
        message = finding.message
        if finding.suggestion:
            message = f"{message} {finding.suggestion}"
        lines.append(
            f"::{level} file={finding.path},line={max(finding.line, 1)},"
            f"title=ASD-STE100 {finding.rule_id}::{message}"
        )
    return "\n".join(lines)


# The shareable report.
#
# One self-contained page a person can be shown, and can forward to a colleague,
# after the tool is run against their own repository. It carries the three things
# the PRD asks for: the headline count, the clearest examples with their
# replacements, and the breakdown by rule. No external assets, so it survives
# being saved to disk and emailed.

#: The three rule families, each with a one-line gloss for a reader who has not
#: read the rule catalogue.
_FAMILIES = {
    "value": ("Comment value", "Text that says nothing the code does not."),
    "tell": ("AI tells", "Text shaped the way a language model shapes it."),
    "ste": ("ASD-STE100", "How a technical sentence should be built."),
}


def _family_of(rule_id: str) -> str:
    if rule_id.startswith("V-"):
        return "value"
    if rule_id.startswith("A-"):
        return "tell"
    return "ste"


def _select_examples(findings: list[Finding], limit: int = 12, per_rule: int = 3) -> list[Finding]:
    """Pick the findings that make the case, favouring variety over repetition.

    A reader shown twelve copies of the same length rule learns one thing. The
    families that land are the two this tool adds: a comment that says nothing,
    and prose shaped like a model's. Those come first, hard findings before soft,
    and no single rule takes more than a few slots.
    """
    order = {"tell": 0, "value": 1, "ste": 2}
    ranked = sorted(
        findings,
        key=lambda f: (
            order[_family_of(f.rule_id)],
            0 if f.severity is Severity.HARD else 1,
            f.path,
            f.line,
        ),
    )
    picked: list[Finding] = []
    per: Counter = Counter()
    seen_text: set[str] = set()
    for finding in ranked:
        if per[finding.rule_id] >= per_rule:
            continue
        shown = _shown_text(finding)
        if shown in seen_text:
            continue
        picked.append(finding)
        per[finding.rule_id] += 1
        seen_text.add(shown)
        if len(picked) >= limit:
            break
    return picked


def _shown_text(finding: Finding) -> str:
    """The offending text to display: the whole comment when we kept it, else the excerpt."""
    whole = finding.segment_text.strip()
    if whole and len(whole) <= 400:
        return whole
    return finding.excerpt.strip()


_HTML_STYLE = """
:root {
  color-scheme: light dark;
  --bg: #fbfbfa; --panel: #ffffff; --ink: #1a1a18; --muted: #6b6b66;
  --line: #e7e6e2; --accent: #b4341f; --soft: #8a8a83;
  --code-bg: #f5f4f1; --tell: #7a3ea8; --value: #b4341f; --ste: #4a6b8a;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #17171a; --panel: #1f1f23; --ink: #ececea; --muted: #9a9a94;
    --line: #2e2e33; --accent: #e8674f; --soft: #7d7d78;
    --code-bg: #26262b; --tell: #b98ad8; --value: #e8674f; --ste: #86a8c8;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 46rem; margin: 0 auto; padding: 4rem 1.5rem 6rem; }
.eyebrow {
  font-size: .72rem; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 1.2rem;
}
h1 { font-size: 1.6rem; font-weight: 600; margin: 0 0 .5rem; letter-spacing: -.01em; }
h1 .repo { color: var(--accent); }
.lede { color: var(--muted); margin: 0 0 3rem; max-width: 34rem; }
.hero {
  border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
  padding: 2.4rem 0; margin-bottom: 2.6rem;
}
.hero .count { font-size: 4.2rem; line-height: 1; font-weight: 650; letter-spacing: -.03em; }
.hero .count.clean { color: var(--soft); }
.hero .what { color: var(--muted); margin-top: .7rem; font-size: 1.02rem; }
.stats { display: flex; flex-wrap: wrap; gap: 2.4rem; margin-bottom: 3.4rem; }
.stat .n { font-size: 1.5rem; font-weight: 600; }
.stat .l {
  font-size: .8rem; color: var(--muted); text-transform: uppercase; letter-spacing: .06em;
}
h2 {
  font-size: .8rem; letter-spacing: .1em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; margin: 0 0 1.3rem;
}
.card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 1.2rem 1.3rem; margin-bottom: 1rem;
}
.card .top {
  display: flex; align-items: baseline; gap: .6rem; margin-bottom: .7rem; flex-wrap: wrap;
}
.badge {
  font-size: .7rem; font-weight: 600; letter-spacing: .04em;
  padding: .12rem .5rem; border-radius: 5px; white-space: nowrap;
}
.badge.tell { color: var(--tell); border: 1px solid var(--tell); }
.badge.value { color: var(--value); border: 1px solid var(--value); }
.badge.ste { color: var(--ste); border: 1px solid var(--ste); }
.card .msg { font-weight: 500; flex: 1; min-width: 12rem; }
.card .loc {
  font-size: .78rem; color: var(--soft); margin-left: auto;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
}
.quote {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .86rem;
  background: var(--code-bg); border-radius: 7px; padding: .7rem .85rem;
  white-space: pre-wrap; word-break: break-word; color: var(--ink);
}
.fix { margin-top: .6rem; font-size: .9rem; color: var(--muted); }
.fix b { color: var(--ink); font-weight: 600; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th {
  text-align: left; font-size: .72rem; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; padding: 0 0 .6rem; border-bottom: 1px solid var(--line);
}
td { padding: .55rem 0; border-bottom: 1px solid var(--line); vertical-align: middle; }
td.rule {
  font-family: ui-monospace, Menlo, monospace; font-weight: 600;
  white-space: nowrap; width: 3.4rem;
}
td.count { text-align: right; font-variant-numeric: tabular-nums; width: 3rem; font-weight: 600; }
.bar { height: 5px; border-radius: 3px; background: var(--line); min-width: 2px; }
.bar > span { display: block; height: 100%; border-radius: 3px; background: var(--accent); }
td.barcell { width: 40%; padding-left: 1rem; }
.foot {
  margin-top: 4rem; padding-top: 1.6rem; border-top: 1px solid var(--line);
  color: var(--muted); font-size: .85rem;
}
.foot p { margin: 0 0 .7rem; }
.foot code {
  font-family: ui-monospace, Menlo, monospace; background: var(--code-bg);
  padding: .1rem .35rem; border-radius: 4px; font-size: .82em;
}
"""


def as_html(report: Report, *, repo: str | None = None) -> str:
    """A single self-contained page, for showing a person their own repository."""
    findings = report.findings
    total = len(findings)
    hard = len(report.hard)
    repo_name = repo or "this repository"

    by_rule = Counter(f.rule_id for f in findings)
    parts: list[str] = []
    parts.append('<div class="wrap">')
    parts.append('<p class="eyebrow">Words for Humans</p>')
    parts.append(
        f'<h1>What the tool found in <span class="repo">{html.escape(repo_name)}</span></h1>'
    )
    parts.append(
        '<p class="lede">Prose in the codebase that no human should have to read: '
        "comments that restate the code, sentences that open with filler, and text "
        "shaped the way a language model shapes it.</p>"
    )

    parts.append('<div class="hero">')
    if total:
        clause = "" if total == 1 else "s"
        parts.append(f'<div class="count">{total}</div>')
        parts.append(
            f'<div class="what">finding{clause} worth cutting, '
            f"{hard} of them serious enough to fail a build.</div>"
        )
    else:
        parts.append('<div class="count clean">0</div>')
        parts.append(
            '<div class="what">Nothing to cut. Every checked piece of text earns its place.</div>'
        )
    parts.append("</div>")

    parts.append('<div class="stats">')
    for value, label in (
        (report.files_scanned, "files read"),
        (report.segments_scanned, "pieces of text checked"),
        (len({f.rule_id for f in findings}), "rules that fired"),
    ):
        parts.append(
            f'<div class="stat"><div class="n">{value}</div><div class="l">{label}</div></div>'
        )
    parts.append("</div>")

    examples = _select_examples(findings)
    if examples:
        parts.append("<h2>The clearest examples</h2>")
        for finding in examples:
            fam = _family_of(finding.rule_id)
            parts.append('<div class="card">')
            parts.append('<div class="top">')
            parts.append(f'<span class="badge {fam}">{html.escape(finding.rule_id)}</span>')
            parts.append(f'<span class="msg">{html.escape(finding.message)}</span>')
            parts.append(f'<span class="loc">{html.escape(finding.path)}:{finding.line}</span>')
            parts.append("</div>")
            parts.append(f'<div class="quote">{html.escape(_shown_text(finding))}</div>')
            if finding.suggestion:
                parts.append(
                    f'<div class="fix"><b>Instead:</b> {html.escape(finding.suggestion)}</div>'
                )
            parts.append("</div>")

    if by_rule:
        top = by_rule.most_common()[0][1]
        parts.append("<h2>Every rule that fired</h2>")
        parts.append(
            "<table><thead><tr><th>Rule</th><th>What it asks</th>"
            "<th></th><th>Count</th></tr></thead><tbody>"
        )
        for rule_id, count in by_rule.most_common():
            rule = CATALOGUE.get(rule_id)
            summary = rule.summary if rule else ""
            width = max(2, round(count / top * 100))
            parts.append(
                f'<tr><td class="rule">{html.escape(rule_id)}</td>'
                f"<td>{html.escape(summary)}</td>"
                f'<td class="barcell"><div class="bar">'
                f'<span style="width:{width}%"></span></div></td>'
                f'<td class="count">{count}</td></tr>'
            )
        parts.append("</tbody></table>")

    parts.append('<div class="foot">')
    parts.append(
        "<p>Words for Humans reads comments, docstrings, Markdown, user-facing strings "
        "and commit messages, and reports the prose that carries no information. The rules "
        "come from ASD-STE100, a published controlled-English standard, and two families "
        "this tool adds for the failure modes generated text has.</p>"
    )
    parts.append(
        "<p>Run it on another repository: "
        "<code>uvx words-for-humans --format html . &gt; report.html</code></p>"
    )
    parts.append("</div>")
    parts.append("</div>")

    body = "\n".join(parts)
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Words for Humans — {html.escape(repo_name)}</title>\n"
        f"<style>{_HTML_STYLE}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )
