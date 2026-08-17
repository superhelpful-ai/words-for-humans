"""Access to the STE controlled vocabulary.

ASD owns the ASD-STE100 dictionary, so this package does not carry it. Two
sources are supported:

Starter list
    Words that read as needlessly fancy in software prose, each with a plainer
    everyday word. It ships with the package and drives rule 1.1 out of the box.
    The vocabulary is re-selected for software rather than lifted from the
    specification, which bans the technical verbs software depends on.

Local cache
    The full dictionary, extracted from your own copy of the specification by
    `words-for-humans-extract-dictionary`. When a cache is present, the
    check for words that are not in the dictionary at all (rule 1.1) turns on;
    without it that check stays off, because flagging every word absent from a
    97-entry list would report nothing useful.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_STARTER = Path(__file__).parent / "data" / "starter_dictionary.json"

#: Locations searched for a locally extracted dictionary, nearest first.
_CACHE_NAMES = (
    Path(".words-for-humans/dictionary.json"),
    Path(".config/words-for-humans/dictionary.json"),
)


@dataclass
class Dictionary:
    not_approved: dict[str, list[str]] = field(default_factory=dict)
    approved: dict[str, list[str]] = field(default_factory=dict)
    source: str = "starter list"

    @property
    def has_approved_list(self) -> bool:
        """Whether the full approved vocabulary is loaded.

        Rule 1.1 can only be checked against the complete list.
        """
        return len(self.approved) >= 300

    def alternatives_for(self, word: str) -> list[str] | None:
        return self.not_approved.get(word.lower())

    def is_approved(self, word: str) -> bool:
        return word.lower() in self.approved


def _load_starter() -> Dictionary:
    data = json.loads(_STARTER.read_text())
    return Dictionary(not_approved=data.get("not_approved", {}), source="starter list")


def _find_cache(root: Path) -> Path | None:
    for parent in [root, *root.parents]:
        for name in _CACHE_NAMES:
            candidate = parent / name
            if candidate.is_file():
                return candidate
    home = Path.home() / ".config" / "words-for-humans" / "dictionary.json"
    return home if home.is_file() else None


@lru_cache(maxsize=8)
def load(root: str = ".", explicit: str | None = None) -> Dictionary:
    """Load the best dictionary available for `root`."""
    dictionary = _load_starter()

    path = Path(explicit) if explicit else _find_cache(Path(root).resolve())
    if path is None or not path.is_file():
        return dictionary

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return dictionary

    approved = data.get("approved", {})
    not_approved = {
        word: entry.get("alternatives", []) if isinstance(entry, dict) else list(entry)
        for word, entry in data.get("not_approved", {}).items()
    }
    if not approved and not not_approved:
        return dictionary

    merged = dict(dictionary.not_approved)
    merged.update({w: a for w, a in not_approved.items() if a})
    return Dictionary(not_approved=merged, approved=approved, source=str(path))
