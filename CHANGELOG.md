# Changelog

## 0.3.1

- Added a `--version` flag to the command.
- Added a README section on the hosted GitHub App, which launched with this
  release.
- Rewrote the pre-commit and CI documentation for the public repository: the
  remote pre-commit hook and the composite action replace the private-repo
  workarounds.
- Corrected the rule counts in the review skill, the installation guide, and
  the account module docstring to match the catalogue: 104 rules, 41 decided
  locally, 58 needing judgment, 5 counting rules.
- Renamed the git hook bypass variable from `STE_LINT_SKIP` to
  `WORDS_FOR_HUMANS_SKIP`.
- Replaced the deprecated `concise` profile alias with `code` in the
  repository's own configuration.
- Added badges, this changelog, CONTRIBUTING.md, and issue templates.

## 0.3.0 and earlier

The project was developed privately and open-sourced at 0.3.0. Releases 0.1.0
through 0.3.0 are on PyPI without individual entries here.
