---
name: words-for-humans-review
description: Review code comments, docstrings, documentation and user-facing strings against the ASD-STE100 Simplified Technical English rules that need judgment rather than pattern matching. Use after words-for-humans has run, or when asked to check writing for Simplified Technical English, STE conformance, or ASD-STE100 compliance.
---

# ASD-STE100 review

`words-for-humans` decides 38 of the 83 rules by inspection: sentence length, paragraph
length, semicolons, contractions, passive voice, tense, spelling, and the closed
word lists. This skill covers the 40 that need a reader who understands what the
text is about.

Run the command first. Never repeat what it already reports.

## Step 1: get the mechanical findings

```bash
words-for-humans --format json --no-fail
```

Use `--diff origin/main...HEAD` when reviewing a change rather than a repository.

Read the output. Those findings are settled; do not restate them, and do not
second-guess them unless one is plainly wrong, in which case say so and give the
text that proves it.

## Step 2: review the rules the command cannot decide

Read the same files and judge these. Each needs the meaning of the text, which
is why a pattern cannot decide it.

### Words (section 1)

| Rule | What to judge |
| --- | --- |
| 1.2 | An approved word used as the wrong part of speech. "Test" is an approved noun, not a verb. |
| 1.3 | An approved word carrying a meaning the dictionary does not approve. |
| 1.5, 1.6 | A word absent from the dictionary is allowed only as a technical noun. Decide whether it truly names a thing in the subject field. |
| 1.7, 1.13 | A technical noun used as a verb, or a technical verb used as a noun. |
| 1.8, 1.9 | Terminology that is not the company's approved term, or a longer term where a shorter one exists. |
| 1.11 | The same thing called by two different names. This needs the whole file, or the whole change, in view. |

In a codebase, most unlisted words are identifiers, library names, or protocol
terms. Those are technical nouns and are fine. Report a word only when an
ordinary English alternative was available and was not used.

### Sentences and structure (sections 4, 5, 6)

| Rule | What to judge |
| --- | --- |
| 4.3 | Text that carries several conditions or steps in one paragraph and should be a vertical list. |
| 4.4 | Sentences that jump between topics with no connecting word. |
| 4.5 | A noun with no article or demonstrative where one belongs. |
| 5.2 | More than one instruction in a sentence, where the actions are not simultaneous. |
| 5.3 | An instruction not written as a command. |
| 5.4 | A condition that arrives after the command instead of before it. |
| 5.5 | A note that gives an instruction. A note may only inform. |
| 6.1 | Information delivered too fast, or a sentence carrying more than one subject. |
| 6.2 | A paragraph with no key phrase to orient the reader. |
| 6.5 | A paragraph covering more than one topic. |

Rules 5.2 through 5.5 apply to procedural text. In a repository that means
README steps, runbooks, migration guides, and the imperative lines in a
docstring. Ordinary explanatory comments are descriptive, so judge them under
section 6 instead.

### Safety instructions (section 7)

Rules 7.1 to 7.3 apply wherever the text warns about damage or loss: a comment
above a destructive migration, an error message before an irreversible action, a
runbook step that drops data. Check that the level of risk is named, that the
text opens with the command or the condition, and that the consequence is
stated. Do not apply this section to ordinary comments.

### Writing practices (section 9, GR)

| Rule | What to judge |
| --- | --- |
| 9.1 | A sentence that needs recasting, not a word swapped for its approved alternative. |
| 9.2 | An approved word used loosely. |
| GR-1 | A dropped "that" that makes the sentence ambiguous. |
| GR-2 | "with" standing in for a relation the reader has to guess. |
| C-6 | A pronoun whose referent is not certain. |
| GR-5 | A word borrowed from another language that reads as a false friend. |

## Step 3: report

Group findings by file. For each one give:

- the file and line
- the rule number and section
- the text as it stands
- a rewrite that obeys the rule

A rewrite is the point. A finding without one is an observation, not a review.

Keep the rewrite faithful to what the code actually does. If obeying a rule
would make the comment less accurate, say so and leave the text alone: an
inaccurate comment that conforms is worse than an accurate one that does not.

End with a count by section and the three changes that would remove the most
findings.

## What not to report

- Anything `words-for-humans` already reported.
- Commented-out code, tool directives, and generated files.
- Identifiers. ASD-STE100 governs prose and says nothing about naming.
- Terminology from a library, protocol, or vendor that has no English
  alternative.
- Task tags such as TODO and FIXME, which are notes between developers rather
  than documentation.

## Scope

The specification was written for aircraft maintenance documentation. Applying
it to source code means judging what carries over. Sentence length, active
voice, one instruction per sentence, and consistent terminology carry over
cleanly. The technical noun categories were written for aerospace hardware and
need reading across to software. When a rule does not transfer, say that rather
than forcing a finding.
