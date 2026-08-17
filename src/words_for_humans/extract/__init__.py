"""Extraction of reviewable English from a repository."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..model import Segment, SegmentKind
from . import code_units, comments, commits, databricks, identifiers, markdown, strings

_MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdx"}

#: The label shown as the path of a pull request description finding, which
#: has no file to point at.
DESCRIPTION_PATH = "pull request description"


def pr_description(body: str) -> list[Segment]:
    """A pull request description's prose, relabelled as its own kind.

    The body is Markdown, so it goes through the Markdown extractor.
    Relabelling lets the report read correctly and lets configuration target
    the description on its own. The CLI and the GitHub App both read
    descriptions through this.
    """
    if not body or not body.strip():
        return []
    return [
        replace(segment, kind=SegmentKind.PR_DESCRIPTION)
        for segment in markdown.extract(DESCRIPTION_PATH, body)
    ]


def extract_file(
    path: str,
    source: str,
    *,
    scopes: set[SegmentKind],
    keep_task_tags: bool = False,
) -> list[Segment]:
    """Extract every enabled kind of text from one file."""
    suffix = Path(path).suffix.lower()
    segments: list[Segment] = []

    if suffix in _MARKDOWN_SUFFIXES:
        if SegmentKind.MARKDOWN in scopes:
            segments.extend(markdown.extract(path, source))
        return segments

    markdown_view: str | None = None
    if databricks.is_notebook(path, source):
        source, markdown_view = databricks.split(source)

    if SegmentKind.COMMENT in scopes or SegmentKind.DOCSTRING in scopes:
        segments.extend(
            s
            for s in comments.extract(path, source, keep_task_tags=keep_task_tags)
            if s.kind in scopes
        )
    if SegmentKind.STRING in scopes:
        segments.extend(strings.extract(path, source))
    if SegmentKind.IDENTIFIER in scopes:
        segments.extend(identifiers.extract(path, source))
    if markdown_view is not None and SegmentKind.MARKDOWN in scopes:
        segments.extend(markdown.extract(path, markdown_view))

    return segments


def is_supported(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in _MARKDOWN_SUFFIXES or comments.spec_for(path) is not None


__all__ = [
    "DESCRIPTION_PATH",
    "code_units",
    "commits",
    "databricks",
    "extract_file",
    "identifiers",
    "is_supported",
    "markdown",
    "pr_description",
    "strings",
]
