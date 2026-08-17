"""File discovery and the run loop."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

from . import checks, dictionary, extract
from .checks.context import ContextMap
from .config import Config
from .judgment import (
    JudgmentCache,
    Provider,
    ProviderError,
    cached_verdicts,
    judge_segment_cached,
)
from .model import Finding, Report, Segment, SegmentKind
from .rules import CATALOGUE, Decidability, Severity

#: Inline escape hatch. Put it in the comment or paragraph itself.
#:
#:     # words-for-humans: ignore
#:     # words-for-humans: ignore C-3, C-1
_IGNORE = re.compile(r"words-for-humans:\s*ignore(?P<rules>[\s\w.,GR-]*)", re.IGNORECASE)

_MAX_BYTES = 2_000_000


def discover(paths: list[str], config: Config, root: Path) -> list[Path]:
    """List the files to check.

    Inside a git repository the file list comes from git by default, so that
    ignored and untracked build output is skipped without restating .gitignore
    here. Set respect_gitignore to false to walk every file on disk instead.
    A committed vendored copy is tracked by git, so .gitignore does not exclude
    it; use the exclude patterns in the config for that.
    """
    files: list[Path] = []
    for raw in paths:
        target = Path(raw)
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(_walk(target, config))
    return [f for f in dict.fromkeys(files) if _included(f, config, root)]


def _walk(directory: Path, config: Config) -> list[Path]:
    if config.respect_gitignore:
        tracked = _git_files(directory)
        if tracked is not None:
            return tracked
    return [p for p in directory.rglob("*") if p.is_file()]


def _git_files(directory: Path) -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=directory,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        return None
    return [directory / name for name in result.stdout.split("\0") if name]


def changed_files(rev_range: str | None, staged: bool, root: Path) -> list[Path]:
    """List files changed in a diff, for pre-commit and pull request runs."""
    command = ["git", "diff", "--name-only", "--diff-filter=ACMR"]
    if staged:
        command.append("--cached")
    elif rev_range:
        command.append(rev_range)
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [root / name for name in result.stdout.splitlines() if name.strip()]


def _included(path: Path, config: Config, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = path.as_posix()

    if any(fnmatch(relative, pattern) for pattern in config.exclude):
        return False
    if config.include and not any(fnmatch(relative, p) for p in config.include):
        return False
    return extract.is_supported(str(path))


def check_segments(segments: list[Segment], contexts: ContextMap) -> tuple[list[Finding], int]:
    """Run every check over every segment, honouring inline ignores.

    Each segment is checked under the profile its path resolves to, so one
    run can hold a design doc and an annual plan to different contracts.
    """
    findings: list[Finding] = []
    suppressed = 0
    for segment in segments:
        context = contexts.for_path(segment.path)
        ignore = _IGNORE.search(segment.text)
        ignored_rules: set[str] | None = None
        if ignore:
            listed = [r.strip() for r in re.split(r"[\s,]+", ignore.group("rules")) if r.strip()]
            ignored_rules = set(listed)
            if not ignored_rules:
                suppressed += 1
                continue
        for finding in checks.run(segment, context):
            if ignored_rules and finding.rule_id in ignored_rules:
                suppressed += 1
                continue
            findings.append(finding)
    return findings, suppressed


#: The judgment tier costs one model call per segment, so a whole-repository
#: run does not get to spend thousands of them unannounced. Raise or lower the
#: cap with W4H_AI_LIMIT. Cache hits do not count against it.
_DEFAULT_JUDGED_SEGMENTS = 200

#: Judgment reads prose. Identifiers and commit subjects go through their own
#: mechanical checks only.
_JUDGED_KINDS = frozenset(SegmentKind) - {SegmentKind.IDENTIFIER, SegmentKind.COMMIT}


def _judgment_rules_for(context) -> list:
    """The judgment rules this segment's profile sends to the model.

    Each profile carries an explicit allowlist, resolved into the context.
    The genre profiles ask the judge a short list of value questions; only
    `ste` asks for dialect conformance. Design rules (D-) judge code units
    rather than prose, so they stay with the GitHub App's separate pass.
    """
    return [
        rule
        for rule in CATALOGUE.values()
        if rule.decidability is Decidability.JUDGMENT
        and not rule.id.startswith("D-")
        and rule.id in context.judgment_rules
    ]


def _judgment_concurrency(provider: Provider) -> int:
    """How many model calls run at once.

    A hosted provider takes parallel requests happily, so a key raises the
    default. A local daemon serves one model and queues the rest, and queue
    time counts against the call timeout, so it stays serial unless
    W4H_AI_CONCURRENCY asks for more.
    """
    raw = os.environ.get("W4H_AI_CONCURRENCY", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return 8 if getattr(provider, "api_key", "") else 1


def judgment_findings(
    segments: list[Segment], contexts: ContextMap, provider: Provider
) -> list[Finding]:
    """Run the judgment rules over the segments, one model call per segment.

    Verdicts come back as soft findings: a model verdict reports, it does not
    fail a build. Results are cached by content, so a re-run of unchanged
    text costs nothing, and cache hits do not count against the call cap. A
    provider failure ends the pass and reports what it judged, because a
    half-judged run is still worth having.
    """
    limit = int(os.environ.get("W4H_AI_LIMIT", _DEFAULT_JUDGED_SEGMENTS))
    cache = JudgmentCache()
    findings: list[Finding] = []
    to_call: list[tuple[Segment, list]] = []
    capped = False
    for segment in segments:
        if segment.kind not in _JUDGED_KINDS or _IGNORE.search(segment.text):
            continue
        rules = _judgment_rules_for(contexts.for_path(segment.path))
        if not rules:
            continue
        hit = cached_verdicts(segment, rules, provider, cache)
        if hit is not None:
            findings.extend(_verdict_finding(v, segment) for v in hit if v.violates)
            continue
        if len(to_call) >= limit:
            capped = True
            continue
        to_call.append((segment, rules))
    if capped:
        print(
            f"words-for-humans: judgment stopped after {limit} model calls. "
            "Set W4H_AI_LIMIT to raise the cap.",
            file=sys.stderr,
        )
    findings.extend(_judge_all(to_call, provider, cache))
    return findings


def _judge_all(
    work: list[tuple[Segment, list]], provider: Provider, cache: JudgmentCache
) -> list[Finding]:
    """Judge the uncached segments, in parallel when the provider allows it."""
    findings: list[Finding] = []
    workers = _judgment_concurrency(provider)
    if workers <= 1 or len(work) <= 1:
        for segment, rules in work:
            try:
                verdicts = judge_segment_cached(segment, rules, provider, cache)
            except ProviderError as error:
                print(f"words-for-humans: judgment stopped: {error}", file=sys.stderr)
                break
            findings.extend(_verdict_finding(v, segment) for v in verdicts if v.violates)
        return findings

    from concurrent.futures import ThreadPoolExecutor

    errors: list[ProviderError] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            (segment, pool.submit(judge_segment_cached, segment, rules, provider, cache))
            for segment, rules in work
        ]
        for segment, future in futures:
            try:
                verdicts = future.result()
            except ProviderError as error:
                errors.append(error)
                continue
            findings.extend(_verdict_finding(v, segment) for v in verdicts if v.violates)
    if errors:
        print(
            f"words-for-humans: judgment failed on {len(errors)} segments: {errors[0]}",
            file=sys.stderr,
        )
    return findings


def _verdict_finding(verdict, segment: Segment) -> Finding:
    rule = CATALOGUE.get(verdict.rule_id)
    return Finding(
        rule_id=verdict.rule_id,
        severity=Severity.SOFT,
        path=segment.path,
        line=segment.line,
        kind=segment.kind,
        message=verdict.message or (rule.summary if rule else ""),
        excerpt=segment.text.strip()[:140],
        suggestion=verdict.suggestion,
        segment_text=segment.text,
    )


def run(
    paths: list[str],
    config: Config,
    root: Path,
    *,
    rev_range: str | None = None,
    staged: bool = False,
    diff_only: bool = False,
    pr_description: str | None = None,
    judge: Provider | None = None,
) -> Report:
    contexts = ContextMap(dictionary.load(str(root), config.dictionary_path), config)

    if diff_only or staged:
        files = [f for f in changed_files(rev_range, staged, root) if _included(f, config, root)]
    else:
        files = discover(paths or [str(root)], config, root)

    report = Report()
    segments: list[Segment] = []

    for path in files:
        try:
            if path.stat().st_size > _MAX_BYTES:
                continue
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        report.files_scanned += 1
        segments.extend(
            extract.extract_file(
                _display_path(path, root),
                source,
                scopes=set(config.scopes),
                keep_task_tags=config.keep_task_tags,
            )
        )

    if rev_range and not diff_only and not staged and SegmentKind.COMMIT in config.scopes:
        segments.extend(extract.commits.extract(rev_range, cwd=str(root)))

    if pr_description and pr_description.strip():
        segments.extend(extract.pr_description(pr_description))

    report.segments_scanned = len(segments)
    findings, suppressed = check_segments(segments, contexts)
    if judge is not None:
        findings.extend(judgment_findings(segments, contexts, judge))
    report.findings = _order(findings)
    report.suppressed = suppressed
    return report


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _order(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (f.path, f.line, f.rule_id, f.message))
