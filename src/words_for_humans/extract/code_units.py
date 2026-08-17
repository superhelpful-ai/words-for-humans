"""Pull functions and classes out of a file as units for the design judge.

The prose extractors read the text in a file. The design rules read the code, so
they need a different unit. A unit is a whole function or class, with its source
and the line it starts on. A model verdict then maps to a file line the same way a
prose finding does.

Only Python is covered in the first release. Locating a function or class boundary
reliably needs a parser, and the standard library gives one for Python through
`ast`. For a language without a parser here, the extractor returns nothing rather
than guess a boundary with a regular expression.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

_PYTHON_SUFFIXES = (".py", ".pyi")


@dataclass(frozen=True)
class CodeUnit:
    """One function or class, the subject of a design rule.

    `source` is the unit's own text, passed to the judge. `line` is the file line
    where that text starts, so an offset inside `source` maps back to a file line.
    `added_lines` holds the file lines a diff added, so a finding can be kept only
    when it lands on the author's change.
    """

    path: str
    line: int
    name: str
    kind: str
    source: str
    signature: str
    added_lines: frozenset[int] = frozenset()

    def line_for_offset(self, offset: int) -> int:
        """Map a character offset within `source` back to a file line number."""
        return self.line + self.source.count("\n", 0, max(offset, 0))


def extract(path: str, source: str, *, added_lines: frozenset[int] = frozenset()) -> list[CodeUnit]:
    """Return each top-level function and class in a Python file.

    Methods and nested functions are not separate units. They sit inside the
    source of the class or function that contains them, so the model reads them in
    context. A file in another language, or one that does not parse, yields
    nothing.
    """
    if not path.endswith(_PYTHON_SUFFIXES):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    units: list[CodeUnit] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        segment = ast.get_source_segment(source, node)
        if not segment:
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        units.append(
            CodeUnit(
                path=path,
                line=node.lineno,
                name=node.name,
                kind=kind,
                source=segment,
                signature=segment.splitlines()[0].strip(),
                added_lines=added_lines,
            )
        )
    return units
