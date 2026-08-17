# Proposal: the Standalone rule family

## The proposal

Add a rule family, `S-` (Standalone), that checks whether a piece of prose can
be understood by a reader who has only the file in front of them. Position the
tool's own families as the product: V (says something), S (stands alone),
A (sounds human), and D (design). The ASD-STE100 sections stay in the
catalogue as the dialect the `ste` profile enforces, and the genre profiles
do not report them.

## Context

The tool exists to enforce one standard: every document, comment, and
description must be readable and useful on its own. A reader who has not seen
the conversation, ticket, or pull request that produced the text must still
get full value. That standard has three failure modes, and the catalogue
covers two of them.

Prose that says nothing is covered by the V rules: restated declarations,
filler openers, empty parameter docs. Prose that sounds generated is covered
by the A rules: em dashes, throat-clearing, announced lists, summary closers,
triads. Prose that cannot stand alone is covered by nothing. No rule before this
family flagged a comment narrating its own review history, a ticket number
standing in for an explanation, or a comment that only makes sense against a
previous version of the code.

The gap has a cause. The catalogue grew from ASD-STE100, which governs how a
sentence is built: approved words, verb forms, articles, punctuation. The
standard says nothing about whether a sentence depends on context the reader
does not have. It is also a translation-oriented controlled dialect, scoped
by its own publisher to aerospace maintenance writing. Mainstream clarity
authorities, including the
[Federal Plain Language Guidelines](https://digital.gov/guides/plain-language)
and [GOV.UK](https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/clear-language/),
prescribe plain language for general prose, not a controlled vocabulary.
Applying the dialect outside its industry is what produced the tool's
false positives.

## The rules

The pattern rules run in the free deterministic tier. The judgment rules need
a reader who understands what the text means, so they run in the model tier.

| ID  | Slug                     | Requirement                                                        | Decided by |
| --- | ------------------------ | ------------------------------------------------------------------ | ---------- |
| S-1 | history-narration        | State the current truth, not how the text came to be.              | pattern    |
| S-2 | diff-comment             | Comment the code, not the change that produced it.                 | pattern    |
| S-3 | reference-as-explanation | A reference may add depth. It may not be the whole explanation.    | pattern    |
| S-4 | time-anchor              | Anchor "currently", "new", and "soon" to a date or version.        | pattern    |
| S-5 | required-context         | Restate what the reader needs; a citation stays optional.          | judgment   |
| S-6 | deprecated-anchor        | State the current constraint, not the retiring thing it replaced.  | judgment   |
| S-7 | context-bound-example    | An example carries its own context in the sentence it appears in.  | judgment   |

### S-1 history-narration

Text that narrates its own revision history says nothing about the code or
the subject. The history lives in version control. Clean Code (Martin, 2008)
names this smell "journal comments". Ousterhout's A Philosophy of Software
Design states the positive form: the rationale belongs in the comment, not in
a commit log the next reader will never open.

```text
Fails:  // Added retry per code review feedback.
Fails:  Revised after the planning meeting.
Passes: // Retry here because the upstream API rate-limits in bursts.
```

Detection is a pattern list, trimmed by the corpus run to phrases with no
runtime sense:

```text
as discussed      as agreed          per our discussion
per code review   review feedback    fixed after PR #482
```

Commit messages are exempt, since a commit message is the record of the
change. A venue or positional word after a phrase marks a citation or a
cross-reference, so "as discussed on pgsql-hackers" and "as discussed above"
both pass.

### S-2 diff-comment

A comment that describes the edit rather than the code is unreadable once the
previous version is gone, which is immediately.

```text
Fails:  // Changed this to a Map for performance.
Fails:  // Removed the old validation here.
Passes: // A Map keeps lookups O(1); the hot path calls this per row.
```

Detection is a pattern list held to high precision:

```text
changed this to   renamed from    removed the old (sentence-initial)
used to be        used to return  instead of the previous
```

Two runtime senses are exempt. "The old version of the data" names an object
the code handles, so a following "of" passes. A mid-sentence "removed the
old" is what the code does, so only the sentence-initial form reports.
Commit messages are exempt for the same reason as S-1, and changelog paths
resolve to the `changelog` profile, where the whole family stays quiet.

### S-3 reference-as-explanation

A bare ticket number, issue link, or URL in place of prose delegates the
explanation to a resource the reader may not reach. The reference is welcome
next to an explanation, never instead of one. A study of 9.6 million links in
source comments ([Hata et al., ICSE 2019](https://arxiv.org/abs/1901.07440))
found about one in ten already dead and the rest rarely updated, which is the
rot this rule guards against.

```text
Fails:  // See JIRA-1234.
Passes: // Rounds half-up because invoices are reconciled in cents. See JIRA-1234.
```

Detection: the segment consists only of a reference, meaning a ticket
pattern, an issue number, or a URL, with at most a pointer word such as
"see". The rule reads comments, docstrings, and pull request descriptions.
Markdown is outside it, because a link list is navigation and a bibliography
is bare links on purpose. Stable external standards (an RFC or PEP number)
and license URLs are exempt: those name definitions and boilerplate, not
rotting pointers.

### S-4 time-anchor

Words that place the text relative to the moment of writing decay as soon as
that moment passes.
[Google's style guide](https://developers.google.com/style/timeless-documentation)
publishes this as its timeless-documentation rule, and this rule adopts its
avoid-list. It reads documentation only, meaning Markdown and pull request
descriptions. In a code comment the same words name runtime state: the
corpus run put that ratio near even, and the hand-written control had the
highest comment rate of all four corpora.

```text
Fails:  The new engine is currently behind a flag and will be enabled soon.
Passes: As of v2.3 the engine is behind a flag; v2.4 is planned to enable it.
```

Detection is a word list ("currently", "as of this writing", "for now",
"coming soon") plus "the legacy <thing>" when no version or date appears in
the segment. "New", "latest", "existing", and "eventually" are absent on
corpus evidence: each names runtime state or a technical term too often to
report.

### S-5 required-context

When understanding the text requires opening another document, the necessary
idea belongs in the text. Whether a reference gates comprehension or adds
depth is a semantic question, so this is a judgment rule. The Federal Plain
Language Guidelines state the fix directly: repeat brief material rather than
cross-reference it. GitLab's low-context communication guidance is the same
rule for engineering docs: a link must carry a preview of what it points to.
The reader then has full information on first read.

- Fails: "Use the thresholds from the Q3 capacity doc."
- Passes: "Alert at 80% of quota, the ceiling the capacity plan sets, and see
  that plan for the derivation."

### S-6 deprecated-anchor

Explaining current code by pointing at something scheduled for removal leaves
the explanation dangling once the removal happens. The durable constraint
belongs in the text; the retiring system does not.

- Fails: `// Works around the old sync pipeline, which is going away.`
- Passes: `// Writes must be idempotent: the queue redelivers on timeout.`

### S-7 context-bound-example

An example that assumes an unstated backstory, a named person, or an incident
the reader was not present for illustrates nothing.

- Fails: "Avoid what happened with the Jenkins box."
- Passes: "Avoid single points of failure, such as one build machine whose
  disk fills and blocks every release."

## Severity and profiles

S-1 is hard under the genre profiles, on the corpus evidence recorded below:
the tuned run left nine findings across 968,000 segments, every one a
genuine journal comment. The other pattern rules report soft, each a
candidate for hard once its precision supports it; that is the same path
noun-cluster (C-4) took. The judgment rules stay soft under the existing
invariant that a model verdict never fails a build.

The genre profiles' judgment allowlist is {C-6, S-5, S-6, S-7, V-7, A-9}.
These are the questions the allowlist exists to ask: their answers help any
author, on any profile. The `ste` and `minimal` profiles continue to send
the full judgment catalogue.

A changelog narrates history and old behaviour as its genre, so common
changelog paths (`CHANGELOG*`, `HISTORY*`, `RELEASE_NOTES*`, and kin)
resolve to a built-in `changelog` profile that silences the S family in
both tiers. A repository overrides the mapping by naming the same path in
its `[paths]` table.

S rules apply to comments, docstrings, markdown, and pull request
descriptions, with the narrower scopes each rule states above. S-1 and S-2
do not apply to commit messages.

## Prior art

No existing tool detects any of these failures. A survey of the production
linter ecosystem, the style-guide literature, and the academic work on
comment quality supports both halves of that claim. The failures are real
and named; the detection is unbuilt.

Every production prose linter is a pattern engine. Vale, proselint,
write-good, alex, textlint, RedPen, and LanguageTool all reduce to word
lists, regexes, and counts within a scope. Their catalogues check word choice
and grammar; none of them ask what the reader must already know. The nearest
existing rule is `unexpanded-acronym` in textlint and RedPen, which handles
one special case of undefined vocabulary. Vale v3 is worth watching for a
different reason: it extracts comments from about nineteen languages via
tree-sitter. The S pattern rules could later ship as a Vale style for teams
already running it.

The academic record names the failures without detecting them. The current
comment-smell taxonomy
([Jabrayilzade et al., EMSE 2024](https://link.springer.com/article/10.1007/s10664-023-10425-5))
catalogues eleven smells from 2,447 labeled comments. None of the three S
comment patterns appears in it. A systematic review of a decade of comment-quality
research ([Rani et al., JSS 2023](https://www.sciencedirect.com/science/article/pii/S0164121222001911))
lists 21 quality attributes with no entry for context independence. The
stale-comment literature detects comment-code mismatch, and every approach
needs the diff as a second input; none reads decay signals from the comment
text alone.

Two precedents transfer directly. Self-admitted technical debt detection
([Potdar and Shihab, ICSME 2014](https://ieeexplore.ieee.org/document/6976075))
proved the recipe this family uses: a curated pattern list, then a labeled
corpus, then a lightweight classifier. Its 62 debt patterns ("hack",
"workaround", "temporary") also feed S-6's judgment prompt. The published
style authorities supply the rules' legitimacy: plain-language guidance
against cross-references, Google's timeless-documentation word list, and
GitLab's low-context rule. Amazon's memo bar states the family's acceptance
test: a reader with no context gets the full argument.

One authority pulls the other way. SonarQube rule S1707 requires a ticket
reference on TODO comments. That is compatible with S-3: a task tag is a
pointer to future work, not an explanation of present code, and the
`keep_task_tags` setting already separates the two.

## Alternatives considered

Extending the V family was rejected: V asks whether text says anything, and
S asks whether the reader can receive it. A rule that conflates the two is
harder to tune and to explain. Judging everything with the model was
rejected: the pattern half of the family is cheap, deterministic, and runs
without a provider, which keeps the default install useful. Adopting a
word-level linter's rule set was rejected because those catalogues check
word choice, not context dependence, and the existing A and V families
already cover the overlap.

## Rollout

1. Land S-1 through S-4 as soft pattern rules with fixture tests per rule.
2. Run the four validation corpora and read every finding. Cut any pattern
   whose precision falls below roughly 95%, the bar the A rules were held to.
3. Add S-5, S-6, and S-7 to the catalogue as judgment rules and to the genre
   allowlist. Judge a corpus sample and read the verdicts before shipping.
4. Promote S-1 to hard under the genre profiles once step 2 supports it.

## Corpus results

Steps 1 and 2 ran against the four validation corpora: 79 repositories and
968,000 prose segments across work, personal, mature open source, and one
hand-written control. The first pass produced 17,058 findings; reading them
cut the patterns that measured idiom rather than decay, and the tuned pass
produced 2,100.

| Rule | Tuned findings | Reading |
| --- | --- | --- |
| S-1 | 9 | Every survivor is a genuine journal comment. Hard under the genre profiles. |
| S-2 | 361 | "Used to be" is real history; two runtime senses are exempted. Stays soft. |
| S-3 | 1,097 | Bare issue links above code, the intended smell. Stays soft. |
| S-4 | 633 | Reads documentation only; in comments the words name runtime state. |

Three cuts carried the pass. "As requested" left S-1: on real code it reads
"as the caller requested" almost every time. S-3 left Markdown: a link list
is navigation, and a license header is boilerplate. S-4 left code comments,
where the hand-written control had the highest rate of all four corpora,
which marks the pattern as idiom rather than decay. Each cut is recorded as
a comment on the pattern it shaped.

## Judgment sample results

Step 3 judged 750 segments across five repositories through Ollama, with the
seven-rule genre allowlist. The model returned 236 findings, and the read
surfaced two problems ahead of any per-rule tuning.

The sample was contaminated by changelogs. Discovery walks files in name
order, so `CHANGELOG.md` reaches the judge first, and a changelog narrates
history and old behaviour as its genre. Most of the verdicts on those files
were correct readings of text that is allowed to look that way. The
built-in `changelog` profile is the outcome: common changelog paths resolve
to it, and it silences the S family in both tiers.

The sample also ended V-8 (repeats-commit). The judge sees the segment and
the code beneath it, never the commit message, so its verdicts guessed from
surface shape. The rule also inverted this family's own principle by making
an artifact outside the file load-bearing, and the failure it aimed at,
comments narrating the change, is S-1 and S-2's job. The catalogue no
longer carries it.

The genuine hits were S-5 and S-6 doing their jobs: "Adapted from <url>"
with nothing restated, "Workaround until this is fixed: <link>", and a
comment explaining code by the failure of a retiring environment. S-7
returned four verdicts, all pedantic. S-5's misses read the rule too hard,
flagging sentences that do state the fact and cite for depth; the judge
prompt needs the distinction spelled out, not just the rule summary.

## Open questions

- Should S-3 treat a task tag such as `TODO(JIRA-1234)` as a reference? The
  `keep_task_tags` setting already governs task tags, and the two should not
  fight.
- Is publishing the S pattern rules as a Vale style worth the maintenance, as
  a path into teams that already run Vale?
