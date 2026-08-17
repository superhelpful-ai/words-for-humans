"""The middle tier: a local model for what patterns cannot settle.

Detection runs at three tiers, and each exists because the one below it cannot
reach the case.

Deterministic
    A regular expression or a structural test. Free, instant, and identical on
    every run. Everything in `checks/` sits here. Any rule that can be moved
    down to this tier should be, because it costs nothing to run and nothing to
    explain.

Classifier
    A small supervised model over the features below, running locally on CPU in
    a millisecond or two. It covers the cases with no fixed phrase to match:
    prose that is bloated in a way no single token betrays. It gives a score,
    not a rule, so it reports rather than blocks.

Model
    A full language model, for the rules that need to know what the code means.
    Slow and metered, so it runs last and only on what survives the tiers above.

`Classifier` is the seam for the middle tier. `NullClassifier` is the default,
so the engine behaves the same whether or not a model is present.

## Where the training data comes from

The corpus does not need hand annotation. Comments in repositories with commit
dates before 2022 are human-written by construction. Generating comments for the
same functions with a current model produces the matching positive class. That
gives a labelled set at the cost of compute rather than annotation time.

The deterministic rules then act as weak labellers over both halves: a segment
that trips several of them is confidently bloated, one that trips none and comes
from the pre-2022 half is confidently clean. The disagreements are the
interesting cases, and they are the ones worth a human eye.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .model import Segment
from .text import split_sentences, ste_words


@dataclass(frozen=True)
class Score:
    """How likely a segment is to be bloated, and why.

    `confidence` is the model's probability. `contributors` names the features
    that pushed it, so a report can say more than a number.
    """

    value: float
    contributors: tuple[str, ...] = ()

    @property
    def is_bloated(self) -> bool:
        return self.value >= 0.5


class Classifier(Protocol):
    def score(self, segment: Segment) -> Score: ...


class NullClassifier:
    """The default. Scores nothing, so the engine runs unchanged without a model."""

    def score(self, segment: Segment) -> Score:
        return Score(value=0.0)


_HEDGE = re.compile(
    r"\b(?:may|might|could|should|typically|generally|usually|often|possibly|"
    r"potentially|perhaps|somewhat|relatively|fairly|quite|rather)\b",
    re.IGNORECASE,
)
_ABSTRACT_NOUN = re.compile(
    r"\b\w+(?:tion|sion|ment|ance|ence|ity|ness|ship|hood|ism)\b", re.IGNORECASE
)
_CONNECTIVE = re.compile(
    r"\b(?:however|therefore|moreover|furthermore|additionally|consequently|"
    r"thus|hence|nevertheless|nonetheless|accordingly)\b",
    re.IGNORECASE,
)


def features(segment: Segment) -> dict[str, float]:
    """Extract the feature vector.

    This is shared between training and inference on purpose. A feature computed
    one way when training and another way when scoring is the most common reason
    a classifier performs worse in production than on the bench.
    """
    text = segment.text
    sentences = split_sentences(text)
    words = ste_words(text)
    word_count = len(words) or 1
    sentence_count = len(sentences) or 1

    code_words = len(segment.follows_code.split()) if segment.follows_code else 0
    overlap = _overlap(text, segment.follows_code) if segment.follows_code else 0.0

    return {
        "word_count": float(word_count),
        "sentence_count": float(sentence_count),
        "mean_sentence_words": word_count / sentence_count,
        "max_sentence_words": float(max((s.word_count for s in sentences), default=0)),
        "mean_word_length": sum(len(w) for w in words) / word_count,
        "hedge_rate": len(_HEDGE.findall(text)) / word_count,
        "abstract_noun_rate": len(_ABSTRACT_NOUN.findall(text)) / word_count,
        "connective_rate": len(_CONNECTIVE.findall(text)) / word_count,
        "comma_rate": text.count(",") / word_count,
        # The ratio of prose to the code it sits above. A short function under a
        # long comment is the shape that prompted this tool.
        "comment_to_code_ratio": word_count / code_words if code_words else 0.0,
        "code_overlap": overlap,
    }


def _overlap(text: str, code: str) -> float:
    split = re.compile(r"[_\-\W]+|(?<=[a-z0-9])(?=[A-Z])")
    prose = {w.lower() for w in split.split(text) if w.isalpha() and len(w) > 2}
    identifiers = {w.lower() for w in split.split(code) if w.isalpha() and len(w) > 2}
    if not prose:
        return 0.0
    return len(prose & identifiers) / len(prose)


FEATURE_NAMES = tuple(
    sorted(
        {
            "word_count",
            "sentence_count",
            "mean_sentence_words",
            "max_sentence_words",
            "mean_word_length",
            "hedge_rate",
            "abstract_noun_rate",
            "connective_rate",
            "comma_rate",
            "comment_to_code_ratio",
            "code_overlap",
        }
    )
)


def vector(segment: Segment) -> list[float]:
    """Features in a fixed order, for a model that expects an array."""
    extracted = features(segment)
    return [extracted[name] for name in FEATURE_NAMES]
