"""Per-repository configuration.

Settings are read from `.words-for-humans.toml`, or from a `[tool.words-for-humans]` table in
`pyproject.toml`. Every setting has a default, so a repository needs no
configuration to run the tool.

    # .words-for-humans.toml
    scopes = ["comment", "docstring", "markdown"]
    exclude = ["vendor/**", "**/generated/**"]
    disable = ["GR-8"]

    [severity]
    "C-3" = "soft"

    [sentence_length]
    code  = [25, 35]
    prose = [30, 40]

    [paths]
    "docs/**" = "prose-technical"
    "planning/**" = "prose-corporate"

`severity` overrides a rule's level. `sentence_length` sets the warn and fail
word counts per tier: `code` for comments, docstrings, and strings; `prose` for
Markdown and pull request text. `paths` maps parts of the repository to other
genre profiles: the last matching pattern wins, and unmatched files use the
top-level profile.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from fnmatch import fnmatch
from pathlib import Path

from .model import SegmentKind
from .profiles import DEFAULT_PROFILE, PROFILES, canonical, hard_rules
from .rules import CATALOGUE, Severity

DEFAULT_EXCLUDES = (
    "**/node_modules/**",
    "**/.git/**",
    "**/dist/**",
    "**/build/**",
    "**/vendor/**",
    "**/.venv/**",
    "**/venv/**",
    "**/__pycache__/**",
    "**/target/**",
    "**/.next/**",
    "**/coverage/**",
    "**/*.min.js",
    "**/*.lock",
    "**/package-lock.json",
    "**/.mypy_cache/**",
    "**/.pytest_cache/**",
    "**/.ruff_cache/**",
    "**/site-packages/**",
)

DEFAULT_SCOPES = frozenset(
    {SegmentKind.COMMENT, SegmentKind.DOCSTRING, SegmentKind.MARKDOWN, SegmentKind.STRING}
)

#: Built-in path-to-profile mappings, applied before the config `[paths]`
#: table so a repository's own entry wins. A changelog narrates history as
#: its genre, so common changelog paths resolve to the `changelog` profile
#: rather than being judged as ordinary prose.
DEFAULT_PATHS: tuple[tuple[str, str], ...] = tuple(
    (pattern, "changelog")
    for base in (
        "CHANGELOG",
        "changelog",
        "CHANGES",
        "HISTORY",
        "RELEASES",
        "RELEASE_NOTES",
        "release-notes",
        "NEWS",
    )
    for pattern in (f"{base}*", f"**/{base}*")
)


@dataclass
class Config:
    scopes: frozenset[SegmentKind] = DEFAULT_SCOPES
    exclude: tuple[str, ...] = DEFAULT_EXCLUDES
    include: tuple[str, ...] = ()
    disable: frozenset[str] = frozenset()
    profile: str = DEFAULT_PROFILE
    #: (pattern, profile) pairs from the `[paths]` table, in declaration order.
    #: The last pattern matching a file's root-relative path decides its
    #: profile; files matching none use `profile` above.
    paths: tuple[tuple[str, str], ...] = ()
    hard_rules: frozenset[str] = field(default_factory=lambda: hard_rules(DEFAULT_PROFILE))
    severity: dict[str, Severity] = field(default_factory=dict)
    max_procedural_words: int | None = None
    max_descriptive_words: int | None = None
    #: Overrides for the (warn, fail) sentence-length counts, keyed by tier
    #: ("code", "prose"). Empty uses the defaults.
    sentence_tiers: dict[str, tuple[int, int]] = field(default_factory=dict)
    keep_task_tags: bool = False
    #: Whether the built-in DEFAULT_PATHS mappings apply. An explicit
    #: --profile flag turns them off, so the whole run is held to one genre.
    default_paths: bool = True
    dictionary_path: str | None = None
    baseline_path: str = ".words-for-humans-baseline.json"
    report_path: str = "words-for-humans-report.txt"
    #: Inside a git repository, discovery lists files with git so that ignored
    #: and untracked build output is skipped. Turn this off to scan every file
    #: on disk, including git-ignored ones.
    respect_gitignore: bool = True

    def profile_for(self, path: str) -> str:
        """The profile for one file, given its root-relative posix path.

        The built-in mappings apply first and the `[paths]` table after, and
        the last matching pattern wins. A repository therefore overrides a
        built-in by naming the same path, and a file matching nothing uses
        the run's profile.
        """
        chosen = self.profile
        built_in = DEFAULT_PATHS if self.default_paths else ()
        for pattern, name in (*built_in, *self.paths):
            if fnmatch(path, pattern):
                chosen = name
        return chosen

    def for_profile(self, name: str) -> Config:
        """This config with another profile active and its hard set recomputed.

        The `[severity]` table stays in force: an override the repository wrote
        applies whichever profile a path resolves to.
        """
        if name == self.profile:
            return self
        return replace(self, profile=name, hard_rules=_hard_with_overrides(name, self.severity))

    @classmethod
    def load(cls, root: Path) -> Config:
        return cls.from_table(_read_table(root))

    @classmethod
    def from_toml(cls, text: str) -> Config:
        """Build a config from the text of a `.words-for-humans.toml` file.

        The GitHub App uses this to apply the reviewed repository's own
        configuration, which it fetches over the API rather than reading from
        disk. A malformed file falls back to the defaults rather than failing
        the review.
        """
        try:
            return cls.from_table(tomllib.loads(text))
        except tomllib.TOMLDecodeError:
            return cls()

    @classmethod
    def from_table(cls, data: dict) -> Config:
        if not data:
            return cls()

        scopes = data.get("scopes")
        severity_table = data.get("severity", {}) or {}
        severity = {
            str(rule_id): Severity(value)
            for rule_id, value in severity_table.items()
            if value in {"hard", "soft"} and str(rule_id) in CATALOGUE
        }
        profile = canonical(str(data.get("profile", DEFAULT_PROFILE)))

        return cls(
            sentence_tiers=_parse_sentence_tiers(data.get("sentence_length", {})),
            scopes=_parse_scopes(scopes) if scopes else DEFAULT_SCOPES,
            exclude=DEFAULT_EXCLUDES + tuple(data.get("exclude", [])),
            include=tuple(data.get("include", [])),
            disable=frozenset(str(r) for r in data.get("disable", [])),
            profile=profile,
            paths=_parse_paths(data.get("paths", {})),
            hard_rules=_hard_with_overrides(profile, severity),
            severity=severity,
            max_procedural_words=data.get("max_procedural_words"),
            max_descriptive_words=data.get("max_descriptive_words"),
            keep_task_tags=bool(data.get("keep_task_tags", False)),
            dictionary_path=data.get("dictionary"),
            baseline_path=data.get("baseline", ".words-for-humans-baseline.json"),
            report_path=data.get("report", "words-for-humans-report.txt"),
            respect_gitignore=bool(data.get("respect_gitignore", True)),
        )


def _hard_with_overrides(profile: str, severity: dict[str, Severity]) -> frozenset[str]:
    """The profile's hard set, adjusted by the config `[severity]` table."""
    hard = set(hard_rules(profile))
    for rule_id, level in severity.items():
        hard.add(rule_id) if level is Severity.HARD else hard.discard(rule_id)
    return frozenset(hard)


def _parse_paths(table: object) -> tuple[tuple[str, str], ...]:
    """Read the `[paths]` table of pattern-to-profile mappings.

    A mapping naming an unknown profile is dropped rather than failing the
    run, matching how an invalid `[severity]` entry is treated: those paths
    keep the top-level profile.
    """
    if not isinstance(table, dict):
        return ()
    return tuple(
        (str(pattern), canonical(str(name)))
        for pattern, name in table.items()
        if canonical(str(name)) in PROFILES
    )


def _read_table(root: Path) -> dict:
    standalone = root / ".words-for-humans.toml"
    if standalone.is_file():
        try:
            return tomllib.loads(standalone.read_text())
        except (tomllib.TOMLDecodeError, OSError):
            return {}

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            parsed = tomllib.loads(pyproject.read_text())
        except (tomllib.TOMLDecodeError, OSError):
            return {}
        return parsed.get("tool", {}).get("words-for-humans", {})
    return {}


def _parse_sentence_tiers(table: object) -> dict[str, tuple[int, int]]:
    """Read the `[sentence_length]` table into (warn, fail) pairs by tier.

    A tier is kept only when it names `code` or `prose` and gives two positive
    integers with the warn count no greater than the fail count. Anything else
    is dropped, so a malformed entry falls back to the default rather than
    failing the run.
    """
    if not isinstance(table, dict):
        return {}
    tiers: dict[str, tuple[int, int]] = {}
    for tier in ("code", "prose"):
        pair = table.get(tier)
        if (
            isinstance(pair, list)
            and len(pair) == 2
            and all(isinstance(x, int) and x > 0 for x in pair)
            and pair[0] <= pair[1]
        ):
            tiers[tier] = (pair[0], pair[1])
    return tiers


def _parse_scopes(values: list[str]) -> frozenset[SegmentKind]:
    kinds = set()
    for value in values:
        try:
            kinds.add(SegmentKind(value))
        except ValueError:
            continue
    return frozenset(kinds) or DEFAULT_SCOPES
