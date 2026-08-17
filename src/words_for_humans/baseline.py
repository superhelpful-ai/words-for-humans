"""Baseline support, so the tool can be adopted in an existing repository.

A first run against a codebase that predates the standard reports a large number
of findings. Recording them as a baseline lets the build fail only on findings
that are new, while the recorded ones stay visible in the report.

The baseline keys on the rule, the file, and the offending text rather than a
line number, so edits elsewhere in a file do not invalidate it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .model import Finding


@dataclass
class Baseline:
    fingerprints: set[str]
    path: Path

    @classmethod
    def load(cls, path: Path) -> Baseline:
        if not path.is_file():
            return cls(fingerprints=set(), path=path)
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return cls(fingerprints=set(), path=path)
        return cls(fingerprints=set(data.get("fingerprints", [])), path=path)

    def contains(self, finding: Finding) -> bool:
        return finding.fingerprint() in self.fingerprints

    def write(self, findings: list[Finding]) -> int:
        payload = {
            "note": (
                "Findings recorded when words-for-humans was adopted. They are reported "
                "but do not fail the build. Delete an entry once it is fixed."
            ),
            "fingerprints": sorted({f.fingerprint() for f in findings}),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2) + "\n")
        return len(payload["fingerprints"])
