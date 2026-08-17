# How detection works

Three tiers. Each exists because the one below it cannot reach the case, and
work is pushed as far down as it will go.

| Tier | Cost | Decides | Where it lives |
| --- | --- | --- | --- |
| Deterministic | Free | A fixed threshold, a closed set of phrases, a structural pattern | `checks/` |
| Classifier | Microseconds, local CPU | Bloat with no single token to point at | `classifier.py` |
| Model | Metered per call | What the text means, and whether it is true of the code | The review skill and the app |

## Why the bottom tier carries most of the load

Asking an assistant to write shorter comments works some of the time. The
patterns it reaches for come from training rather than from the prompt, so they
survive the instruction and reappear a few files later. A check does not get
tired of asking.

Most of those patterns are closed sets. "It's worth noting that", "several
benefits:", "in a real implementation you would" — a regular expression settles
each one, at no cost, with an explanation the author can act on. Anything that
can be settled this way should be, and moving a rule down a tier is always an
improvement.

## The rule families

**ASD-STE100** (`1.1` to `9.4`, `GR-1` to `GR-8`). The published standard.
Constrains how a sentence is built: length, voice, tense, vocabulary,
punctuation. Credible because it is not this tool's opinion, and it predates the
problem it is being pointed at.

**Comment value** (`V-`). Whether the text says anything. The standard has no
rule against a comment that restates the code below it, because it was written
for people documenting aircraft rather than for a machine producing text at
volume.

**AI tells** (`A-`). Whether the text has the shape a language model produces.
Definition by negation, praise adjectives, announced lists, stacked hedges,
admissions that the code is unfinished, decorative emoji, placeholder values,
step narration.

`A-5` is the one to watch. Text such as "in a real implementation you would
validate this" is not a style problem; it marks code somebody has to finish, and
it reaches production because it reads like documentation.

## The classifier tier

`classifier.py` defines the seam. `NullClassifier` is the default, so nothing
changes until a model is present.

The features are in `features()`, shared between training and inference on
purpose. A feature computed one way when training and another way when scoring
is the usual reason a model does worse in production than on the bench.

### Getting the training data

The corpus needs no hand annotation.

1. **Negative class.** Comments from repositories whose commits predate 2022.
   Human-written by construction.
2. **Positive class.** Generate comments for the same functions with a current
   model. Same code, same domain, different author.
3. **Weak labels.** Run the deterministic rules over both halves. A segment that
   trips several is confidently bloated; one that trips none and comes from the
   pre-2022 half is confidently clean.
4. **The interesting part.** Where the weak labels and the source disagree. A
   pre-2022 comment that trips four rules is either genuinely bad or a false
   positive worth fixing, and either answer is useful.

The cost is compute rather than annotation time, and every deterministic rule
added improves the labelling of the whole corpus.

## Adding a rule

1. Write it in the family it belongs to, under `checks/`.
2. Register it in `rules.py` with its decidability.
3. Decide whether it blocks, in `profiles.py`.
4. Test the tell **and** the human sentence that must survive it.

That last step is not optional. Every rule in the `A-` family fires on a phrase
somebody might legitimately write, and a false positive here tells an author to
delete something that was carrying information. `tests/test_tells.py` pairs each
detector with the sentence it must leave alone.
