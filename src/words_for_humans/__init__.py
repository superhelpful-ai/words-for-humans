"""Words for Humans: finds text in a repository that no human should have to read.

The engine checks comments, docstrings, Markdown, strings and pull request
descriptions against three rule families: ASD-STE100 Simplified Technical
English for how a sentence is built, and two of its own for whether the sentence
was worth writing.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
