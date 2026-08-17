# words-for-humans

Most new code is written by an assistant and reviewed by a person. The code
gets tests, types, and CI. The prose around it gets nothing, and the prose is
what the reviewer reads first. `words-for-humans` checks that prose: comments,
docstrings, Markdown, user-facing strings, and pull request descriptions, so
generated changes cost a reviewer less attention to digest.

Your assistant writes comments like this:

```ts
// This function is responsible for calculating the total price of all the items
// that are present in the cart. It's worth noting that we will iterate over each
// of the items in order to accumulate the sum of their individual prices.
export function calculateCartTotal(items: CartItem[]): number {
  return items.reduce((sum, item) => sum + item.price, 0);
}
```

Three lines that tell a reader nothing the signature does not. Multiply that
across a year of generated pull requests and the comments stop being read at
all, which costs you the ones that mattered.

It also writes comments like this:

```ts
// Added retry per code review feedback. See JIRA-1234.
await retryWithBackoff(() => client.send(payload));
```

The review is not in the file, and the ticket will not always be reachable.
The next reader gets a comment about a conversation they were not part of,
instead of the reason the code is shaped this way.

`words-for-humans` finds both:

```
slop_demo.ts
  1:    error [V-4] "This function is responsible for" restates the declaration below.
        → Start with the verb: what it does, or why it exists.
  2:    error [V-2] "It's worth noting that" adds nothing to the sentence.
        → Delete it and start with the statement.
  8:    warn  [S-1] "Added retry per code review feedback" narrates how the text came to be.
        → State the reason the code or fact holds today. The history lives in version control.
```

And it leaves this one alone, because it says something the code cannot, and
says it to a reader with no context beyond the file:

```ts
// Retry with backoff because the upstream rate limiter returns 429 in bursts
// after a deploy, and a flat retry makes the burst worse.
await retryWithBackoff(() => client.send(payload));
```

## The four questions

Every piece of prose is held to four questions, one rule family per question:

| Family | Question |
| --- | --- |
| `V-` | Does it say anything the code does not? |
| `S-` | Does it stand alone, with only the file in front of the reader? |
| `A-` | Does it sound like a person wrote it? |
| `C-` | Does it read easily? |

A fifth family, `D-`, asks the same kind of question of the code itself. Its
rules come from A Philosophy of Software Design and Clean Code, and it runs
in the GitHub App's model pass.

**Standing alone is the question generated text fails most often.** An
assistant writes from the conversation that produced the change, so its
prose leans on that conversation. The signals are lexical: a reason replaced
by history, a comment that describes the edit, a ticket number in place of
an explanation, a relative name with no anchor. Each of those reads fine in
the pull request and means nothing a month later. The `S-` rules hold prose
to one bar: a reader with zero background gets full value, without the
review, the ticket, or the chat thread. References are welcome as citations
that add depth, never as dependencies that gate understanding.

[docs/standalone-rules.md](docs/standalone-rules.md) records the design and
the published authority behind each `S-` rule.

**Sounding human is the question a prompt cannot settle.** Asking an
assistant for shorter comments works some of the time; the habits come from
training, so they come back a few files later. The `A-` family catches the
shapes that survive the prompt: definition by negation, praise adjectives,
announced lists of benefits, stacked hedges, and decorative emoji. It also
catches placeholder credentials, step narration, the em dash, a pleasantry
before the first sentence, and an announced summary at the end. One of them matters beyond
style: `A-5` catches the comment that presents the code as a stand-in for
the version somebody still has to write. That comment marks unfinished work,
reads like documentation, and ships.

Two tiers do the checking. Rules a pattern can settle run in this package,
free and offline. Rules that need a reader who understands what the text
means run as model calls, through the judgment tier or the bundled
`words-for-humans-review` skill. Whether a reference gates comprehension,
and whether a comment earns its length, are questions of that kind.
[docs/detection.md](docs/detection.md) covers the tiers and how the
classifier tier is trained.

## Install

```bash
uv tool install words-for-humans
```

Or run it without installing:

```bash
uvx words-for-humans
```

[docs/installation.md](docs/installation.md) walks a repository through full
adoption: install, config, baseline, pre-commit, CI, and the review skill.

## Use

```bash
words-for-humans                             # the whole repository
words-for-humans --staged                    # what you are about to commit
words-for-humans --diff origin/main...HEAD   # what a pull request changes
words-for-humans --stdout                    # print every finding, do not write a file
words-for-humans --format json               # for a script
words-for-humans --format html > report.html # a page to send someone
words-for-humans --init                      # write a starter config
words-for-humans --list-rules                # every rule, its slug, and which half checks it
```

A run over the whole repository prints the summary to the terminal and writes
the findings themselves to `words-for-humans-report.txt`. The counts that say
where to start are then not buried under thousands of lines. A changed-files run
(`--staged`, `--diff`) is small, so it prints in place. `--stdout` prints
everything to the terminal instead. Add the report file to `.gitignore`.

Findings from rules with a fixed threshold or a closed set of phrases fail the
run. Findings that depend on guessing a part of speech are reported as warnings
and do not affect the exit code.

### Adopting it in an existing repository

The first run against a codebase written before the tool will report a great
deal. Record it and move on:

```bash
words-for-humans --write-baseline
```

Everything found so far stays visible in reports but stops failing the build.
Only new findings can fail from then on.

## The report

`--format html` writes a single self-contained page. It leads with the count of
findings. Below that it shows the clearest examples, each with its replacement,
then lists every rule that fired. No external assets, so it survives being saved
to disk and forwarded.

```bash
words-for-humans --format html . > report.html
```

The page is for showing someone the tool run against their own repository,
before they install anything.

## Profiles

A profile is a named configuration of the rule set: which rules report, which
fail, and what sentence lengths apply. Pick the preset that names what you
are checking, and assign others to parts of the tree with `[paths]`.

```bash
words-for-humans --profile code   # default
```

Strictest first:

| Profile | Genre | What changes |
| --- | --- | --- |
| `ste` | Aerospace-grade technical writing | The whole ASD-STE100 standard, enforced, with its strict sentence limits. |
| `code` | Comments, docstrings, strings | The default. Fails on prose that says nothing. Dialect rules are silent. |
| `prose-technical` | READMEs, specs, design docs | The `code` contract, named for the genre. |
| `changelog` | Changelogs, release notes | History narration is the genre, so the standalone rules stay out. Common changelog paths land here on their own. |
| `prose-corporate` | Plans, reviews, briefs | Prose sentences up to 35/50 words (warn/fail). Emoji allowed. Stated intent ("we will") warns rather than fails. |
| `comms-external` | Announcements, customer-facing text | As corporate, but praise adjectives warn instead of fail. |
| `comms-internal` | Internal notes | Sentences up to 40/60. Emoji allowed, em dashes warn. |
| `minimal` | Diagnosis | Nothing fails. Reports everything so you can see the shape first. |

Empty prose, placeholder values, and the tells of generated text fail under
every genre profile. `concise`, the old name of the default, still works as
an alias of `code`. The `comms-*` pair is provisional: no corpus has tuned it
yet.

## Configure

`words-for-humans --init` writes a starter `.words-for-humans.toml` in the
repository root. The settings can also live in a `[tool.words-for-humans]` table
in `pyproject.toml`:

```toml
profile = "code"
scopes = ["comment", "docstring", "markdown", "string"]
exclude = ["vendor/**", "**/generated/**"]
disable = ["GR-8"]

[severity]
"C-3" = "hard"   # make passive voice fail the build
"V-5" = "soft"   # report padding without failing

[paths]
"docs/**" = "prose-technical"
"planning/**" = "prose-corporate"
```

One repository usually holds more than one genre, so the `[paths]` table maps
directories to profiles. The last matching pattern wins, unmatched files use
the top-level profile, and `--profile` on the command line overrides the whole
table. Entries in `[severity]` stay in force whichever profile a path lands
in.

Inside a git repository, discovery lists files with git, so anything in
`.gitignore` is skipped. A vendored copy that is committed is still tracked, so
`.gitignore` does not exclude it; add its path to `exclude`. To scan every file
on disk, including ignored ones, set `respect_gitignore = false` or pass
`--no-gitignore`. The report file path is `report = "words-for-humans-report.txt"`
by default.

To silence one place rather than one rule, put the escape hatch in the comment:

```python
# words-for-humans: ignore
# words-for-humans: ignore C-1, V-2
```

## Pre-commit

The package is on PyPI and the repository is not public, so the hook is
declared locally and pre-commit installs the package itself:

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

Without pre-commit, a plain git hook that does the same is in
[docs/installation.md](docs/installation.md). Inside this repository,
`./hooks/install.sh` installs it directly.

## GitHub

Run the check in your own Actions workflow. It checks only what the diff adds,
so an author is never shown the repository's existing debt as though it were
theirs:

```yaml
- run: uvx words-for-humans --diff origin/${{ github.base_ref }}...HEAD --format github
```

[docs/ci.md](docs/ci.md) has full recipes for GitHub Actions, Buildkite, and
GitLab, and a one-step composite action. A hosted GitHub App that reviews
pull requests is in private development.

## Where the rules come from

The tool began as a checker for [ASD-STE100 Simplified Technical English][ste],
the controlled English specification the aerospace and defence industries have
used for technical documentation since 1986. The standard earned its keep in
one place: its clarity rules, which hold for any reader. Those became the `C-`
family: sentence and paragraph length, passive voice, noun clusters, slang,
ambiguous pronouns, inclusive language.

The rest of the standard is a controlled dialect for aerospace maintenance
writing, and mainstream clarity authorities prescribe plain language instead.
So the catalogue keeps the ASD-STE100 sections under their spec numbering
(`3.4`, `GR-6`) as a deprecated appendix: only the `ste` profile reports them,
and the next major release removes them. `words-for-humans --list-rules`
prints the whole catalogue, each rule with a slug that names what it checks
(`C-1 sentence-length`, `S-1 history-narration`, `V-1 says-nothing`). Five
counting rules define how words are tallied rather than reporting anything.
A parenthesised aside counts as one word, and so do quoted text, a number
with its unit, and a hyphenated compound.

The `S-` family stands on published authority outside the standard: the
Federal Plain Language Guidelines on cross-references, Google's
timeless-documentation rule, and GitLab's low-context communication guidance.
[docs/standalone-rules.md](docs/standalone-rules.md) cites each.

## The dictionary

ASD publishes the specification free of charge but owns the copyright, so the
controlled vocabulary of roughly 900 approved words is not in this repository
and never will be.

The tool ships a starter list of 22 words that the standard does not approve,
chosen because they turn up in developer prose. Only the `ste` profile leans
on the vocabulary; the genre profiles do not report dictionary conformance.

For the full dictionary, extract it from your own copy of the specification:

```bash
uv tool install 'words-for-humans[dictionary]'
words-for-humans-extract-dictionary ~/Downloads/ASD-STE100_ISSUE9.pdf
```

The result lands in `.words-for-humans/dictionary.json`, which is gitignored.
`words-for-humans --sync-dictionary` will download it for an account instead;
accounts are not yet open.

## Layout

```
src/words_for_humans/     the engine, the command, and the review skill
tests/                    the test suite
action.yml                the composite GitHub Action
hooks/                    git hook installer for this repository
```

## Naming

This project is not affiliated with or endorsed by ASD. ASD-STE100 and
Simplified Technical English are ASD's. The tool checks text against the
standard; it does not represent the standard.

[ste]: https://www.asd-ste100.org/
