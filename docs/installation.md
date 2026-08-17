# Installing words-for-humans in your repository

`words-for-humans` reads the comments, docstrings, Markdown, and user-facing
strings in a repository and reports the prose that carries no information. This
guide takes a repository from nothing to full adoption: the command, a config,
a baseline, a commit hook, a pull request check, and the review skill. Each
step works on its own, so stop at the depth you want.

## Requirements

- [uv](https://docs.astral.sh/uv/) or pipx. Both install the command in an
  isolated environment with no effect on your project's dependencies.
- git. The tool uses it to list files and read diffs. It still works outside a
  repository, with plain directory walks.

## 1. Install the command

```bash
uv tool install words-for-humans
```

With pipx instead:

```bash
pipx install words-for-humans
```

To try it once without installing anything:

```bash
uvx words-for-humans
```

The repository root also carries an [install.sh](../install.sh) that makes
this choice for you: it installs with uv, pipx, or pip, whichever the machine
has, and prints the next steps. It is self-contained, so it works sent as a
file or piped from a URL. `WFH_VERSION` pins a version and `WFH_EXTRAS` adds
extras, for example `WFH_EXTRAS=nlp sh install.sh`.

## 2. See what it finds

Run it from the repository root:

```bash
words-for-humans
```

The terminal shows the counts. The findings themselves go to
`words-for-humans-report.txt`, so a large first run does not bury the summary.
For a page you can send to someone:

```bash
words-for-humans --format html > report.html
```

## 3. Adopt it without failing the build

A codebase written before the tool will produce many findings. Record them,
so only new prose can fail a run:

```bash
words-for-humans --init
words-for-humans --write-baseline
```

`--init` writes `.words-for-humans.toml`, a commented starting point for
excludes, scopes, and severities. `--write-baseline` records every current
finding in `.words-for-humans-baseline.json`. Recorded findings stay visible
in reports but do not fail the build.

Commit both files. Keep the reports out of version control:

```bash
echo "words-for-humans-report.txt" >> .gitignore
echo ".words-for-humans/" >> .gitignore
```

Before you record the baseline, add vendored or generated paths to `exclude`
in the config. The built-in list already skips `node_modules`, `.venv`,
`dist`, and the like.

## 4. Check every commit

With [pre-commit](https://pre-commit.com/), add this to
`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: words-for-humans
        name: words-for-humans
        entry: words-for-humans --staged
        language: python
        additional_dependencies: [words-for-humans]
        types_or: [python, javascript, jsx, ts, tsx, go, rust, markdown, sql, shell]
        pass_filenames: false
        require_serial: true
```

Without pre-commit, write `.git/hooks/pre-commit` yourself:

```bash
#!/usr/bin/env bash
set -euo pipefail
uvx words-for-humans --staged
```

Make it executable with `chmod +x .git/hooks/pre-commit`. Either way the hook
reads only staged files, so it stays fast and never reports on work the
commit does not touch. `git commit --no-verify` bypasses it for one commit.

## 5. Check every pull request

For GitHub Actions, add a workflow:

```yaml
name: Comments

on: pull_request

jobs:
  words-for-humans:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v10.0.0
      - run: |
          uvx words-for-humans \
            --diff origin/${{ github.base_ref }}...HEAD \
            --format github
```

`--format github` annotates the changed lines in the Files Changed view. Only
what the diff adds is checked, so an author is never shown the repository's
existing debt as though it were theirs. [ci.md](ci.md) has a one-step composite
action, the SARIF variant, and recipes for Buildkite and GitLab.

## 6. Install the review skill

The command decides 38 of the 83 rules by inspection. The other 40 need a
reader who understands the subject: whether a word is a genuine technical
noun, whether a paragraph has one topic. A Claude Code skill covers those,
and it ships inside the package:

```bash
words-for-humans --install-skill
```

This writes `.claude/skills/words-for-humans-review/SKILL.md` into the
repository. Commit it. Claude Code picks it up automatically when asked to
review writing, and it runs the command first so nothing is reported twice.

## 7. The full dictionary, if you want it

The default `code` profile does not need the ASD-STE100 vocabulary, so
most repositories can skip this step. The `ste` profile leans on it.

ASD owns the dictionary's copyright, so the package ships without it.
Download the specification free of charge from
[asd-ste100.org](https://www.asd-ste100.org/), then extract the vocabulary
from your own copy:

```bash
uv tool install 'words-for-humans[dictionary]'
words-for-humans-extract-dictionary ~/Downloads/ASD-STE100_ISSUE9.pdf
```

The cache lands in `.words-for-humans/dictionary.json`, which step 3 keeps
out of version control. `words-for-humans --status` shows which dictionary a
run uses.

## Something broke, or something is wrongly reported

`words-for-humans --list-rules` names every rule and its slug. To silence one
rule everywhere, add it to `disable` in the config. To silence one place, put
`# words-for-humans: ignore` in the comment. If a rule fires on prose you
think is right, send the text to whoever pointed you at this guide: false
positives are the findings we most want to see.
