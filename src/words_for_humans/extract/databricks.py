"""Recognise .py files exported from Databricks notebooks.

Databricks exports a notebook as a .py file whose first line is
"# Databricks notebook source". Cells are separated by "# COMMAND ----------"
lines, and every line of a markdown cell arrives prefixed with "# MAGIC".
Read as ordinary comments, a markdown cell repeats the word MAGIC once per
line, so `split` separates the export into a code view and a markdown view
before the comment extractor runs.
"""

from __future__ import annotations

import re

_HEADER = "# Databricks notebook source"
_COMMAND = re.compile(r"^# COMMAND -{4,}")
_DBTITLE = re.compile(r"^# DBTITLE ")
_MAGIC = re.compile(r"^# MAGIC(?: |$)")
_MARKDOWN_DIRECTIVES = ("%md", "%md-sandbox")


def is_notebook(path: str, source: str) -> bool:
    return path.endswith(".py") and source.startswith(_HEADER)


def split(source: str) -> tuple[str, str]:
    """Split an exported notebook into aligned code and markdown views.

    Both views keep the original line numbering: notebook markup becomes a
    blank line in the code view, and everything outside a markdown cell
    becomes a blank line in the markdown view. A finding in either view then
    points at the right line of the exported file.

    Markdown cells lose their "# MAGIC " prefix and their "%md" directive.
    Other magic cells, "%sql" for example, hold code in another language and
    appear in neither view.
    """
    code: list[str] = []
    markdown: list[str] = []
    in_markdown_cell = False

    for line in source.splitlines():
        code_line = ""
        markdown_line = ""
        magic = _MAGIC.match(line)
        if magic:
            body = line[magic.end() :]
            if body.startswith("%"):
                directive, _, rest = body.partition(" ")
                in_markdown_cell = directive in _MARKDOWN_DIRECTIVES
                if in_markdown_cell:
                    markdown_line = rest.strip()
            elif in_markdown_cell:
                markdown_line = body
        elif _COMMAND.match(line) or _DBTITLE.match(line) or line == _HEADER:
            in_markdown_cell = False
        else:
            in_markdown_cell = False
            code_line = line
        code.append(code_line)
        markdown.append(markdown_line)

    return "\n".join(code), "\n".join(markdown)
