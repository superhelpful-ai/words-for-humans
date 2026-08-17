# Running it in CI

Check what the pull request changes, not the whole repository. An author should
see the findings in their own diff, not the debt they inherited.

## GitHub Actions

The repository root carries a composite action, so the check is one step:

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
      - uses: superhelpful-ai/words-for-humans@v0.3.0
```

The action installs the tool from PyPI, and on a pull request it checks the
files the pull request changes and the pull request description itself.
[action.yml](../action.yml) documents the inputs: `version`, `base`, `format`,
`strict`, `args`, `working-directory`, `pr-description`, and the judgment
trio below.

To run the judgment rules as well, name a provider and pass a key:

```yaml
      - uses: superhelpful-ai/words-for-humans@v0.3.0
        with:
          ai-provider: openrouter
          ai-key: ${{ secrets.OPENROUTER_API_KEY }}
```

Judgment findings report as warnings and never fail the check. The profile
decides which judgment rules the model is asked: the genre profiles send only
the comment-value rules and the ambiguous-referent check, and `ste` sends the
full catalogue. The same
switches work anywhere the command runs, as environment variables:
`W4H_AI_PROVIDER` (`openrouter` or `ollama`), `W4H_AI_KEY`, `W4H_AI_MODEL`,
`W4H_AI_HOST` (a key on the ollama provider already implies ollama.com), `W4H_AI_TIMEOUT` (seconds per call), and `W4H_AI_LIMIT` (segments judged per
run). A description can also be checked by hand with
`--pr-description-file PATH`.

The repository is not public, and a private action resolves only from private
repositories of the same owner whose Actions access settings allow it.
Anywhere else, spell the steps out:

```yaml
name: Comments

on: pull_request

permissions:
  contents: read
  pull-requests: write

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

`--format github` emits workflow commands, so each finding appears against the
line it belongs to in the Files Changed view.

For GitHub code scanning instead, emit SARIF:

```yaml
      - run: uvx words-for-humans --diff origin/${{ github.base_ref }}...HEAD --format sarif > ste.sarif
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: ste.sarif
```

## Buildkite

```yaml
steps:
  - label: ":memo: comments"
    command: |
      git fetch -q origin "$BUILDKITE_PULL_REQUEST_BASE_BRANCH"
      uvx words-for-humans --diff "origin/$BUILDKITE_PULL_REQUEST_BASE_BRANCH...HEAD"
```

## GitLab

```yaml
comments:
  script:
    - uvx words-for-humans --diff "origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME...HEAD"
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Nothing failing. Warnings may still have been reported. |
| 1 | At least one failing finding. |
| 2 | The command was used incorrectly. |

`--strict` makes warnings fail as well. `--no-fail` always exits 0, which is
useful while you are deciding what to enforce.

## Checking commit messages

```bash
words-for-humans --commits origin/main...HEAD --scope commit
```

Conventional-commit prefixes are stripped before the subject is read, and
trailers are ignored.
