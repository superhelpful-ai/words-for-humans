"""Build a local dictionary cache from your own copy of the ASD-STE100 PDF.

ASD publishes the specification free of charge but owns the copyright, so the
package does not carry the dictionary. Download the PDF yourself from
https://www.asd-ste100.org/ and run this command, installed with the
`dictionary` extra. It writes a JSON cache that words-for-humans reads at
runtime.

    uv tool install 'words-for-humans[dictionary]'
    words-for-humans-extract-dictionary ~/Downloads/ASD-STE100_ISSUE9.pdf

By default the cache is written to `.words-for-humans/dictionary.json`, which the tool's
gitignore entry keeps out of version control.

Part 2 of the specification marks approval by case. An approved word is printed
in uppercase with its part of speech; a word that is not approved is printed in
lowercase, followed by the approved alternatives in uppercase.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import cast

_PART_OF_SPEECH = {"n", "v", "adj", "adv", "prep", "conj", "pron", "art", "int"}
_POS_GROUP = "|".join(sorted(_PART_OF_SPEECH))
_HEADWORD = re.compile(
    rf"^(?P<indent>\s*)(?P<word>[A-Za-z][A-Za-z '/-]*?)\s*\((?P<pos>{_POS_GROUP})\)"
    rf"(?P<rest>.*)$"
)
_ALTERNATIVE = re.compile(rf"\b(?P<word>[A-Z][A-Z '/-]*?)\s*\((?P<pos>{_POS_GROUP})\)")
_NOISE = re.compile(r"^(ASD|Page|Issue|Word|\d{4}-\d{2}-\d{2}|Part \d|Category \d)")


def parse(pages: list[str]) -> dict[str, object]:
    """Read the dictionary out of the extracted page text.

    Part 2 is laid out as a four-column table. After text extraction each entry
    begins at the left margin: an approved word in uppercase followed by its
    meaning, or a word that is not approved in lowercase followed by the first
    approved alternative. Further alternatives for the same word appear on
    indented lines. Everything else on the line is example text.
    """
    approved: dict[str, set[str]] = {}
    not_approved: dict[str, dict[str, object]] = {}
    current: str | None = None

    for page in pages:
        for raw in page.splitlines():
            if not raw.strip() or _NOISE.match(raw.strip()):
                continue

            match = _HEADWORD.match(raw)
            if not match:
                continue

            word = match.group("word").strip()
            pos = match.group("pos")
            rest = match.group("rest")
            indented = bool(match.group("indent"))
            head = word.split()[0]

            if len(word) < 2:
                continue

            if head.isupper() and not indented:
                approved.setdefault(word.lower(), set()).add(pos)
                current = None
            elif head.isupper() and indented and current:
                _add_alternative(not_approved[current], word, pos)
            elif word.islower() and not indented:
                current = word.lower()
                not_approved.setdefault(current, {"part_of_speech": pos, "alternatives": []})
                first = _ALTERNATIVE.search(rest)
                if first:
                    _add_alternative(
                        not_approved[current], first.group("word").strip(), first.group("pos")
                    )

    return {
        "source": "ASD-STE100 (extracted locally from the user's own copy)",
        "approved": {word: sorted(pos) for word, pos in sorted(approved.items())},
        "not_approved": dict(sorted(not_approved.items())),
    }


def _add_alternative(entry: dict[str, object], word: str, pos: str) -> None:
    alternatives = cast(list[str], entry["alternatives"])
    candidate = f"{word.lower()} ({pos})"
    if candidate not in alternatives:
        alternatives.append(candidate)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Path to your ASD-STE100 PDF")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(".words-for-humans/dictionary.json"),
        help="Where to write the cache (default: .words-for-humans/dictionary.json)",
    )
    args = parser.parse_args()

    try:
        from pypdf import PdfReader
    except ImportError:
        print(
            "pypdf is required. Install the dictionary extra:\n"
            "  uv tool install 'words-for-humans[dictionary]'",
            file=sys.stderr,
        )
        return 2

    if not args.pdf.exists():
        print(f"No such file: {args.pdf}", file=sys.stderr)
        return 2

    reader = PdfReader(str(args.pdf))
    pages = [page.extract_text() or "" for page in reader.pages]
    data = parse(pages)

    approved = cast(dict[str, object], data["approved"])
    not_approved = cast(dict[str, object], data["not_approved"])
    if len(approved) < 300:
        print(
            f"Only {len(approved)} approved words found. This does not look like "
            "the ASD-STE100 dictionary; the cache was not written.",
            file=sys.stderr,
        )
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(
        f"Wrote {args.output}: {len(approved)} approved words, "
        f"{len(not_approved)} words that are not approved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
