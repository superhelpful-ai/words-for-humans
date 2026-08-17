"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import dictionary, engine, judgment, profiles, report
from .baseline import Baseline
from .config import Config
from .model import Report
from .rules import CATALOGUE, Decidability

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="words-for-humans",
        description=(
            "Check code comments, documentation, user-facing strings and "
            "identifiers against ASD-STE100 Simplified Technical English."
        ),
        epilog=(
            "Findings from rules with a fixed threshold fail the run. Findings "
            "that depend on the dictionary or on guessing a part of speech are "
            "reported as warnings and do not affect the exit code."
        ),
    )
    parser.add_argument("paths", nargs="*", default=[], help="Files or directories to check")
    parser.add_argument("-C", "--root", default=".", help="Repository root (default: .)")

    selection = parser.add_argument_group("what to check")
    selection.add_argument("--staged", action="store_true", help="Only files staged for commit")
    selection.add_argument(
        "--diff",
        metavar="REV_RANGE",
        help="Only files changed in a revision range, for example origin/main...HEAD",
    )
    selection.add_argument(
        "--commits",
        metavar="REV_RANGE",
        help="Also check commit messages in a revision range",
    )
    selection.add_argument(
        "--scope",
        action="append",
        choices=["comment", "docstring", "markdown", "string", "identifier", "commit"],
        help="Limit to one kind of text. Repeatable.",
    )
    selection.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Scan every file on disk, including git-ignored ones",
    )
    selection.add_argument(
        "--pr-description-file",
        metavar="PATH",
        help="Also check a pull request description, read from a file",
    )

    behaviour = parser.add_argument_group("behaviour")
    behaviour.add_argument(
        "--format",
        choices=["text", "json", "sarif", "github", "html"],
        default="text",
        help="Output format (default: text). html writes a shareable page to stdout.",
    )
    behaviour.add_argument("--quiet", action="store_true", help="Hide warnings, show failures only")
    behaviour.add_argument(
        "--stdout",
        action="store_true",
        help="Print every finding to the terminal instead of writing the report file",
    )
    behaviour.add_argument(
        "--report",
        metavar="PATH",
        help="Where to write the full findings on a whole-repository run "
        "(default: words-for-humans-report.txt)",
    )
    behaviour.add_argument("--strict", action="store_true", help="Fail the run on warnings as well")
    behaviour.add_argument(
        "--no-fail", action="store_true", help="Always exit 0, whatever is found"
    )
    behaviour.add_argument(
        "--profile",
        type=profiles.canonical,
        choices=profiles.names(),
        help=(
            "A genre preset, strictest first: ste enforces the whole standard; "
            "code (default) fails on comments that say nothing; the prose-* and "
            "comms-* profiles give documents and announcements the room their "
            "genre needs; minimal fails on nothing."
        ),
    )
    behaviour.add_argument("--disable", action="append", metavar="RULE", help="Turn off a rule")
    behaviour.add_argument("--dictionary", metavar="PATH", help="Path to an extracted dictionary")

    baseline = parser.add_argument_group("baseline")
    baseline.add_argument(
        "--write-baseline",
        action="store_true",
        help="Record every current finding so only new ones fail later runs",
    )
    baseline.add_argument(
        "--no-baseline", action="store_true", help="Ignore the baseline file for this run"
    )

    account_group = parser.add_argument_group("account")
    account_group.add_argument(
        "--status", action="store_true", help="Show the plan and dictionary in use, then exit"
    )
    account_group.add_argument(
        "--sync-dictionary",
        action="store_true",
        help="Download the full dictionary and company glossary for your account",
    )

    parser.add_argument(
        "--init", action="store_true", help="Write a starter .words-for-humans.toml and exit"
    )
    parser.add_argument(
        "--install-skill",
        action="store_true",
        help="Install the words-for-humans-review skill into .claude/skills/ and exit",
    )
    parser.add_argument(
        "--list-rules", action="store_true", help="Print the rule catalogue and exit"
    )
    return parser


class _UsageError(Exception):
    """A bad invocation, reported once and exited with EXIT_USAGE."""


def _engine_inputs(args: argparse.Namespace) -> tuple[str | None, judgment.Provider | None]:
    """The description text and judgment provider this invocation asks for."""
    description = None
    if args.pr_description_file:
        try:
            description = Path(args.pr_description_file).read_text(encoding="utf-8")
        except OSError as error:
            raise _UsageError(f"cannot read the description: {error}") from error
    try:
        return description, judgment.provider_from_environment()
    except judgment.ProviderError as error:
        raise _UsageError(str(error)) from error


def _apply_flags(config: Config, args: argparse.Namespace) -> None:
    """Fold the command-line overrides into the loaded config."""
    if args.profile:
        # An explicit flag beats the config, including its [paths] table and
        # the built-in mappings: the whole run is held to the named profile.
        config.profile = args.profile
        config.paths = ()
        config.default_paths = False
        config.hard_rules = profiles.hard_rules(args.profile)
    if args.scope:
        from .model import SegmentKind

        config.scopes = frozenset(SegmentKind(s) for s in args.scope)
    if args.disable:
        config.disable = config.disable | frozenset(args.disable)
    if args.dictionary:
        config.dictionary_path = args.dictionary
    if args.no_gitignore:
        config.respect_gitignore = False


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_rules:
        _print_rules()
        return EXIT_OK

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"words-for-humans: not a directory: {root}", file=sys.stderr)
        return EXIT_USAGE

    if args.init:
        return _init_config(root)

    if args.install_skill:
        return _install_skill(root)

    if args.status:
        _print_status(root, args.dictionary)
        return EXIT_OK

    if args.sync_dictionary:
        return _sync_dictionary(root)

    config = Config.load(root)
    _apply_flags(config, args)

    try:
        pr_description, judge = _engine_inputs(args)
    except _UsageError as error:
        print(f"words-for-humans: {error}", file=sys.stderr)
        return EXIT_USAGE

    result = engine.run(
        args.paths,
        config,
        root,
        rev_range=args.commits or args.diff,
        staged=args.staged,
        diff_only=bool(args.diff),
        pr_description=pr_description,
        judge=judge,
    )

    baseline_path = root / config.baseline_path
    if args.write_baseline:
        count = Baseline(fingerprints=set(), path=baseline_path).write(result.findings)
        print(f"Recorded {count} findings in {config.baseline_path}.")
        print("These stay visible in reports but will not fail a run.")
        return EXIT_OK

    if not args.no_baseline:
        known = Baseline.load(baseline_path)
        if known.fingerprints:
            result = _apply_baseline(result, known)

    _emit(result, args, config, root)

    if args.no_fail:
        return EXIT_OK
    failing = len(result.hard) + (len(result.soft) if args.strict else 0)
    return EXIT_FINDINGS if failing else EXIT_OK


def _apply_baseline(result: Report, known: Baseline) -> Report:
    """Demote recorded findings so only new ones can fail the run."""
    from .rules import Severity

    kept = []
    baselined = 0
    for finding in result.findings:
        if known.contains(finding):
            baselined += 1
            if finding.severity is Severity.HARD:
                kept.append(_demote(finding))
                continue
        kept.append(finding)
    result.findings = kept
    result.suppressed += baselined
    return result


def _demote(finding):
    from dataclasses import replace

    from .rules import Severity

    return replace(finding, severity=Severity.SOFT)


#: A whole-repository run that finds more than this, with no baseline recorded
#: yet, is treated as a first run and shown how to adopt the tool incrementally.
_MANY_FINDINGS = 100


def _emit(result: Report, args: argparse.Namespace, config: Config, root: Path) -> None:
    if args.format == "json":
        print(report.as_json(result))
    elif args.format == "sarif":
        print(report.as_sarif(result))
    elif args.format == "github":
        annotations = report.as_github_annotations(result)
        if annotations:
            print(annotations)
    elif args.format == "html":
        print(report.as_html(result, repo=root.name))
    else:
        _emit_text(result, args, config, root)


def _emit_text(result: Report, args: argparse.Namespace, config: Config, root: Path) -> None:
    """Summary to the terminal, full findings to a file on a whole-repository run.

    A first run against a large codebase prints thousands of findings, and a wall
    of them buries the counts that tell a reader where to start. So the terminal
    gets the summary, and the findings themselves go to a file the reader opens
    when ready. A changed-files run (--staged, --diff) is small, so it prints in
    place. --stdout forces everything to the terminal.
    """
    show_soft = not args.quiet
    shown = result.findings if show_soft else result.hard
    full_scan = not args.staged and not args.diff

    provenance = _provenance(config)
    wrote_to: Path | None = None
    if full_scan and not args.stdout and shown:
        destination = root / (args.report or config.report_path)
        wrote_to = _write_report_doc(result, destination, show_soft, provenance)

    if wrote_to is None:
        report.detail(result, sys.stdout, show_soft=show_soft)

    report.summary(result, sys.stdout, show_soft=show_soft)
    print(f"\n{provenance}")

    if wrote_to is not None:
        shown_here = _relative(wrote_to, root)
        print(f"\nFull findings ({len(shown)}) written to {shown_here}.")

    if not args.quiet:
        _hints(result, config, root, full_scan)


def _provenance(config: Config) -> str:
    """One line naming the contract this run enforced.

    A report is often read by somebody who did not choose the profile, or by
    an agent summarising the run for them. Naming the gate stops that reader
    grading the output against a contract the run never enforced.
    """
    line = f"Profile {config.profile}: {profiles.describe(config.profile)}"
    if config.paths:
        mapped = ", ".join(sorted({name for _, name in config.paths}))
        line += f" The [paths] table holds some files to {mapped}."
    return line


def _write_report_doc(
    result: Report, destination: Path, show_soft: bool, provenance: str
) -> Path | None:
    """Write the detailed findings to a file. Returns the path, or None on failure."""
    try:
        with destination.open("w", encoding="utf-8") as handle:
            report.detail(result, handle, show_soft=show_soft, colour=False)
            report.summary(result, handle, show_soft=show_soft, colour=False)
            print(f"\n{provenance}", file=handle)
    except OSError as error:
        print(f"words-for-humans: could not write {destination}: {error}", file=sys.stderr)
        return None
    return destination


def _hints(result: Report, config: Config, root: Path, full_scan: bool) -> None:
    if (
        full_scan
        and not (root / config.baseline_path).is_file()
        and len(result.findings) > _MANY_FINDINGS
    ):
        lines = [
            f"\nThis looks like a first run: {len(result.findings)} findings across "
            f"{result.files_scanned} files.",
            "To adopt on an existing codebase, record what is here so only new findings fail:",
            "    words-for-humans --write-baseline",
        ]
        if not _config_exists(root):
            lines.append("And scaffold a config for excludes and severities:")
            lines.append("    words-for-humans --init")
        print("\n".join(lines), file=sys.stderr)

    if result.findings and sys.stderr.isatty():
        print(
            "\nNext: --stdout to print findings here, --diff origin/main...HEAD for "
            "changed files,\n      --format html > report.html to share a page.",
            file=sys.stderr,
        )

    loaded = dictionary.load(str(root), config.dictionary_path)
    if not loaded.has_approved_list:
        print(
            "\nThe dictionary rules are running against the starter word list of "
            f"{len(loaded.not_approved)} words.\nFor the full ASD-STE100 vocabulary, extract "
            "it from your own copy of the specification:\n"
            "    words-for-humans-extract-dictionary <your ASD-STE100 PDF>",
            file=sys.stderr,
        )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _config_exists(root: Path) -> bool:
    if (root / ".words-for-humans.toml").is_file():
        return True
    pyproject = root / "pyproject.toml"
    return pyproject.is_file() and "[tool.words-for-humans]" in pyproject.read_text(
        encoding="utf-8", errors="ignore"
    )


_STARTER_CONFIG = """\
# words-for-humans configuration.
# Every setting has a default, so the file is a starting point, not a requirement.

# A genre preset, strictest first: ste, code, prose-technical, prose-corporate,
# comms-external, comms-internal, minimal. code (default) fails on comments that
# say nothing. The prose and comms profiles give documents longer sentence
# budgets and, at the corporate and internal tiers, allow emoji.
profile = "code"

# Map parts of the repository to other profiles. The last matching pattern
# wins; unmatched files use the profile above.
# [paths]
# "docs/**" = "prose-technical"
# "planning/**" = "prose-corporate"

# Which kinds of text to read.
scopes = ["comment", "docstring", "markdown", "string"]

# Paths to skip, added to the built-in list (node_modules, .venv, dist, and so on).
# Put vendored or upstream copies you do not edit here, since .gitignore does not
# cover code that is committed.
exclude = [
    # "**/vendored/**",
    # "**/_shared/**",
]

# Turn off individual rules by code. See 'words-for-humans --list-rules'.
disable = []

# Promote or demote a rule. hard fails the run, soft only warns.
# [severity]
# "C-3" = "hard"   # make passive voice fail the build
# "V-5" = "soft"   # report padding without failing
"""


def _init_config(root: Path) -> int:
    destination = root / ".words-for-humans.toml"
    if destination.is_file():
        print(f"{destination.name} already exists. Leaving it unchanged.")
        return EXIT_OK
    try:
        destination.write_text(_STARTER_CONFIG, encoding="utf-8")
    except OSError as error:
        print(f"words-for-humans: could not write {destination}: {error}", file=sys.stderr)
        return EXIT_USAGE
    print(f"Wrote {destination.name}. Edit it to set excludes, scopes, and severities.")
    return EXIT_OK


def _install_skill(root: Path) -> int:
    """Copy the packaged review skill into the repository's .claude/skills/."""
    from importlib import resources

    source = resources.files("words_for_humans").joinpath(
        "data/skills/words-for-humans-review/SKILL.md"
    )
    content = source.read_text(encoding="utf-8")
    destination = root / ".claude" / "skills" / "words-for-humans-review" / "SKILL.md"
    shown = _relative(destination, root)
    if destination.is_file() and destination.read_text(encoding="utf-8") == content:
        print(f"{shown} is already current.")
        return EXIT_OK
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    except OSError as error:
        print(f"words-for-humans: could not write {destination}: {error}", file=sys.stderr)
        return EXIT_USAGE
    print(f"Wrote {shown}.")
    print("Claude Code picks it up automatically. It reviews the rules that need judgment.")
    return EXIT_OK


def _print_status(root: Path, explicit_dictionary: str | None) -> None:
    from . import account

    entitlement = account.resolve()
    loaded = dictionary.load(str(root), explicit_dictionary)

    print(f"Plan:       {entitlement.plan.value}")
    print(f"Account:    {entitlement.account or 'not signed in'}")
    print(f"Dictionary: {loaded.source}")
    print(
        f"            {len(loaded.approved)} approved words, "
        f"{len(loaded.not_approved)} words that are not approved"
    )
    rules = CATALOGUE.values()
    mechanical = sum(1 for r in rules if r.decidability is Decidability.MECHANICAL)
    judgment = sum(1 for r in rules if r.decidability is Decidability.JUDGMENT)
    print(f"Rules:      {mechanical} checked here, {judgment} need the review pass")
    if not entitlement.signed_in:
        print(
            "\nSet WORDS_FOR_HUMANS_TOKEN to use the full dictionary, your company glossary, "
            "and the\nrules that need judgment."
        )


def _sync_dictionary(root: Path) -> int:
    from . import account

    destination = root / ".words-for-humans" / "dictionary.json"
    if account.sync_dictionary(destination):
        dictionary.load.cache_clear()
        loaded = dictionary.load(str(root))
        print(f"Wrote {destination.relative_to(root)}: {len(loaded.approved)} approved words.")
        return EXIT_OK

    if not account.token():
        print(
            "No account token found. Set WORDS_FOR_HUMANS_TOKEN, or extract the dictionary "
            "from your own\ncopy of the specification with "
            "words-for-humans-extract-dictionary.",
            file=sys.stderr,
        )
    else:
        print(
            "Your plan does not include the full dictionary, or the service could not be reached.",
            file=sys.stderr,
        )
    return EXIT_USAGE


def _print_rules() -> None:
    current_section = None
    for rule in CATALOGUE.values():
        if rule.section != current_section:
            current_section = rule.section
            note = " (deprecated)" if rule.deprecated else ""
            print(f"\n{current_section}{note}")
        marker = {
            Decidability.MECHANICAL: "cli ",
            Decidability.JUDGMENT: "llm ",
            Decidability.CONTEXT: "    ",
        }[rule.decidability]
        print(f"  {marker} {rule.id:<5} {rule.slug:<22} {rule.summary}")
    print(
        "\ncli = checked by this command."
        "\nllm = needs judgment, checked by the words-for-humans-review skill."
        "\n      Rules with no marker define how text is counted."
        "\n\nDeprecated sections are reported only by the ste profile, and the"
        "\nnext major release removes them."
    )


if __name__ == "__main__":
    raise SystemExit(main())
