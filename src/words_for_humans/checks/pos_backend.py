"""Optional part-of-speech backend for the syntactic rules.

Two rules read more precisely with a part-of-speech tagger than with a regular
expression. `noun-cluster` (2.1) needs to know whether a word is a noun or a
verb, because a stoplist cannot tell "the read write lock" (a cluster) from
"the counter cannot drift" (a clause). `passive-voice` (3.6) needs the sentence
structure, so it can flag the passive worth rewriting ("returned by the
function") and leave the idiomatic one alone ("the row is locked").

This backend uses spaCy, which is an optional dependency installed with the
`nlp` extra. When it and its model are present, `available()` is true and the
two checks use it. When it is absent, the checks fall back to their regular
expressions, which over-report but keep the tool dependency-free. The load is
lazy, so importing this module costs nothing until the first parse.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from ..rules import MAX_MULTI_WORD_NOUN

_MODEL = "en_core_web_sm"
#: Lazy caches, mutated in place so no `global` statement is needed. Keys:
#: "available" (bool) and "pipeline" (the loaded spaCy model).
_cache: dict[str, object] = {}

#: Software words a general-English tagger calls verbs, but which act as nouns
#: inside a compound ("the read write lock manager"). Forced nominal in a run.
_CODE_NOUNS = frozenset(
    {
        "read",
        "write",
        "lock",
        "set",
        "get",
        "map",
        "cache",
        "hash",
        "index",
        "key",
        "buffer",
        "queue",
        "stack",
        "mask",
        "flag",
        "log",
        "node",
        "block",
        "field",
        "row",
        "page",
        "token",
        "frame",
        "mock",
        "seed",
        "hook",
        "diff",
        "patch",
        "chunk",
        "batch",
        "commit",
        "merge",
    }
)

#: Nominal parts of speech that can sit inside a multi-word noun.
_MODIFIER_POS = frozenset({"NOUN", "PROPN", "ADJ"})
_HEAD_POS = frozenset({"NOUN", "PROPN"})

#: A "by" phrase that is not a real agent, so the passive is not worth rewriting.
_NON_AGENTS = frozenset(
    {
        "default",
        "itself",
        "himself",
        "herself",
        "themselves",
        "myself",
        "yourself",
        "ourselves",
        "hand",
        "name",
        "value",
        "reference",
        "design",
        "convention",
        "chance",
        "nature",
        "definition",
        "contrast",
        "accident",
        "mistake",
        "force",
        "necessity",
        "virtue",
        "means",
        "comparison",
        "turns",
    }
)

#: Verbs whose "by" phrase is a key, not an agent ("sorted by timestamp").
_KEY_VERBS = frozenset({"sort", "order", "group", "index", "key", "arrange", "rank", "filter"})


def available() -> bool:
    """Whether spaCy and its model are installed. Cheap: does not load the model."""
    if "available" not in _cache:
        try:
            spacy = importlib.import_module("spacy")
            _cache["available"] = spacy.util.is_package(_MODEL)
        except Exception:
            _cache["available"] = False
    return bool(_cache["available"])


def _pipeline():
    if "pipeline" not in _cache:
        spacy = importlib.import_module("spacy")
        _cache["pipeline"] = spacy.load(_MODEL, disable=["ner"])
    return _cache["pipeline"]


@dataclass(frozen=True)
class Span:
    """A detected span, with character offsets into the text that was parsed."""

    text: str
    start: int
    end: int
    length: int = 0


def _nominal(token) -> bool:
    return token.pos_ in _MODIFIER_POS or token.text.lower() in _CODE_NOUNS


def _head_noun(token) -> bool:
    return token.pos_ in _HEAD_POS or token.text.lower() in _CODE_NOUNS


def noun_clusters(text: str) -> list[Span]:
    """Stacked multi-word nouns longer than the limit, ending in a head noun."""
    doc = _pipeline()(text)
    spans: list[Span] = []
    run: list = []
    for token in doc:
        if _nominal(token) and token.is_alpha:
            run.append(token)
        else:
            spans.extend(_emit(run))
            run = []
    spans.extend(_emit(run))
    return spans


def _emit(run: list) -> list[Span]:
    while run and not _head_noun(run[-1]):
        run = run[:-1]
    heads = [t for t in run if _head_noun(t)]
    if len(run) > MAX_MULTI_WORD_NOUN and len(heads) >= 2:
        phrase = " ".join(t.text for t in run)
        return [Span(phrase, run[0].idx, run[-1].idx + len(run[-1].text), len(run))]
    return []


def passive_by_agent(text: str) -> list[Span]:
    """Passive clauses that name an agent worth promoting to the subject.

    Agentless passive ("the row is locked") is left alone; so are the idioms
    that only look like agents ("by default", "sorted by timestamp", "by
    calling x").
    """
    doc = _pipeline()(text)
    spans: list[Span] = []
    for token in doc:
        if token.dep_ != "auxpass":
            continue
        verb = token.head
        if verb.lemma_.lower() in _KEY_VERBS:
            continue
        agent = next((c for c in verb.children if c.dep_ == "agent"), None)
        if agent is None:
            continue
        obj = next((c for c in agent.children if c.dep_ == "pobj"), None)
        if obj is None or obj.pos_ == "VERB" or obj.text.lower() in _NON_AGENTS:
            continue
        subj = next((c for c in verb.children if c.dep_ == "nsubjpass"), None)
        left = min(subj.i if subj is not None else verb.i, verb.i)
        right = max(t.i for t in agent.subtree)
        span = doc[left : right + 1]
        spans.append(Span(span.text, span.start_char, span.end_char))
    return spans
