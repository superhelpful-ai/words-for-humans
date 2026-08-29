# Contributing

## Set up

```bash
uv sync
```

## Before you push

```bash
uv run pytest
uv run ruff check .
uv run words-for-humans --stdout
```

All three must pass. CI runs the tool against this repository's own comments
and documentation, so any prose you add is held to the same rules the tool
enforces. Write plain, direct sentences and the check passes on its own.

## Reporting a false positive

A rule that fires on prose a human wrote for a reason is a bug in the rule.
Open an issue with the false-positive template: name the rule, paste the
exact text, and say why the text is right as written.
