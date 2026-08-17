"""The judgment tier: a language model adjudicates the rules a program cannot.

The deterministic half decides what a pattern can settle. The rules in the
catalogue marked JUDGMENT need a reader who understands what the text means. Is
this comment longer than the code it explains? Does this sentence restate its
heading? Would a rewrite say the same thing in fewer words? This module runs
those as model calls.

Two properties shape the design.

Provider independence
    The judgment is the same whoever serves the model. A hosted open model
    through OpenRouter captures the arbitrage between a value-based price and a
    near-zero token cost; a local model through Ollama keeps the text on the
    author's machine and costs nothing. Both sit behind one `Provider`
    interface, so the rest of the tool does not know or care which is in use.

Two outputs from one tier
    The tier answers findings ("does this segment break rule X"), and it also
    labels segments ("is this comment low-value") for training the local
    classifier. The classifier cannot learn low-value-ness from the
    deterministic rules, because they do not encode it; it learns it from these
    labels. The judgment tier is therefore the classifier's teacher, and one
    labelling pass produces the training set.

Nothing here runs unless asked. The call costs money or local compute, so it is
opt-in and runs last, only on what the cheaper tiers could not settle.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from .model import Segment
from .rules import Rule

#: Per-call ceiling. A local model on modest hardware can need longer than
#: the default; set W4H_AI_TIMEOUT (seconds) to give it the time.
_TIMEOUT_SECONDS = 60


def _timeout() -> float:
    try:
        return float(os.environ.get("W4H_AI_TIMEOUT", _TIMEOUT_SECONDS))
    except ValueError:
        return float(_TIMEOUT_SECONDS)


_CACHE_DIR = Path.home() / ".cache" / "words-for-humans" / "judgment"


class ProviderError(RuntimeError):
    """A provider could not return a completion."""


class Provider(Protocol):
    """A source of model completions. The prompt is JSON-in, JSON-out."""

    name: str

    def complete(self, system: str, user: str) -> str: ...


@dataclass
class OllamaProvider:
    """A local or Ollama-hosted model.

    With no key this talks to a local daemon: no per-token cost, and the text
    never leaves the machine. With a key it talks to Ollama's cloud at
    ollama.com, which serves the same API, so CI can judge with the same
    provider a laptop uses.
    """

    model: str = "qwen3.5:latest"
    host: str = "http://localhost:11434"
    api_key: str = ""
    name: str = "ollama"

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        data = _post(f"{self.host}/api/chat", payload, headers)
        return str(data.get("message", {}).get("content", ""))


@dataclass
class OpenRouterProvider:
    """A hosted open model through OpenRouter. Reads OPENROUTER_API_KEY."""

    model: str = "meta-llama/llama-3.3-70b-instruct"
    api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    host: str = "https://openrouter.ai/api/v1"
    name: str = "openrouter"

    def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = _post(f"{self.host}/chat/completions", payload, headers)
        return str(data["choices"][0]["message"]["content"])


def provider_from_environment() -> Provider | None:
    """Build a provider from the environment, or None when none is asked for.

    W4H_AI_PROVIDER names the backend: "openrouter" or "ollama". W4H_AI_KEY
    carries the key a hosted backend needs; for ollama a key implies the
    hosted service, so the host becomes ollama.com unless W4H_AI_HOST says
    otherwise. W4H_AI_MODEL overrides the backend's default model. With
    W4H_AI_PROVIDER unset, the judgment tier stays off, which keeps the
    default run free of model calls.
    """
    name = os.environ.get("W4H_AI_PROVIDER", "").strip().lower()
    if not name:
        return None
    model = os.environ.get("W4H_AI_MODEL", "").strip()
    key = os.environ.get("W4H_AI_KEY", "").strip()
    host = os.environ.get("W4H_AI_HOST", "").strip()
    if name == "ollama":
        provider = OllamaProvider(api_key=key)
        if key:
            provider.host = "https://ollama.com"
        if host:
            provider.host = host
        if model:
            provider.model = model
        return provider
    if name == "openrouter":
        router = OpenRouterProvider(api_key=key or os.environ.get("OPENROUTER_API_KEY", ""))
        if host:
            router.host = host
        if model:
            router.model = model
        return router
    raise ProviderError(f'unknown W4H_AI_PROVIDER {name!r}; use "openrouter" or "ollama"')


@dataclass
class MockProvider:
    """A canned provider for tests. Returns queued responses in order."""

    responses: list[str] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)
    name: str = "mock"

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.responses.pop(0) if self.responses else "{}"


def _post(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    if not url.startswith(("http://", "https://")):
        raise ProviderError(f"unsupported provider URL scheme: {url!r}")
    body = json.dumps(payload).encode("utf-8")
    # The scheme is checked above; the host comes from provider config.
    request = urllib.request.Request(url, data=body, method="POST")  # noqa: S310
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=_timeout()) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ProviderError(str(error)) from error


@dataclass(frozen=True)
class Verdict:
    """One rule's decision on one segment."""

    rule_id: str
    violates: bool
    message: str = ""
    suggestion: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class Label:
    """A training label for the local classifier, distilled from the model."""

    bloated: bool
    score: float
    reason: str = ""


def _extract_json(text: str) -> object:
    """Parse a model reply that should be JSON, tolerating fences and prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    raise ProviderError(f"model did not return JSON: {text[:200]!r}")


_JUDGE_SYSTEM = (
    "You are a code-comment reviewer. You judge prose from a codebase against a "
    "short list of rules and report only the rules it breaks. A comment that "
    "carries real information a reader needs is good; do not flag it. Reply with "
    "JSON only, no prose."
)


def _rule_line(rule: Rule) -> str:
    note = f" {rule.judge_note}" if rule.judge_note else ""
    return f"- {rule.id}: {rule.summary}{note}"


def _judge_user(segment: Segment, rules: list[Rule]) -> str:
    rule_lines = "\n".join(_rule_line(r) for r in rules)
    code = segment.follows_code.strip()
    code_block = f"\nThe code beneath the comment:\n{code}\n" if code else ""
    return (
        f"Rules:\n{rule_lines}\n\n"
        f"The {segment.kind} to judge:\n{segment.text}\n{code_block}\n"
        'Return {"violations": [{"rule": "<id>", "message": "<why, one sentence>", '
        '"suggestion": "<fix or null>"}]}. Include a rule only if it is clearly '
        "broken. If none are broken, return an empty list."
    )


def judge_segment(segment: Segment, rules: list[Rule], provider: Provider) -> list[Verdict]:
    """Ask the model which of `rules` the segment breaks. One call per segment."""
    raw = provider.complete(_JUDGE_SYSTEM, _judge_user(segment, rules))
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return []
    valid = {r.id for r in rules}
    verdicts: list[Verdict] = []
    for item in parsed.get("violations", []):
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule", "")).strip()
        if rule_id not in valid:
            continue
        verdicts.append(
            Verdict(
                rule_id=rule_id,
                violates=True,
                message=str(item.get("message", "")).strip(),
                suggestion=(str(item["suggestion"]).strip() if item.get("suggestion") else None),
            )
        )
    return verdicts


_LABEL_SYSTEM = (
    "You label code comments to train a smaller model to spot low-value prose. "
    "Judge by information, not by length.\n\n"
    "LOW-VALUE (bloated): restates what the code or a nearby name already says; "
    "states only what any reader already knows; pads a point with filler.\n"
    "HIGH-VALUE (keep): gives something the code cannot show, such as a reason, a "
    "constraint, a caveat, a gotcha, an invariant, a default, an example, or "
    "external context.\n\n"
    "Documentation comments (rustdoc ///, javadoc, docstrings) exist to describe a "
    "public interface. Do not call a doc comment bloated merely for being brief or "
    "for echoing the item name. Flag it only when it adds no fact at all beyond the "
    "name.\n\n"
    "Examples:\n"
    '- "Loop over the items and add up the prices." above a reduce that sums prices '
    "-> bloated 0.9 (restates the code)\n"
    '- "Retry with backoff because the limiter returns 429 in bursts after a deploy." '
    "-> keep 0.1 (gives the reason)\n"
    '- "The port to listen on. Defaults to 8080 when PORT is unset." -> keep 0.2 '
    "(states the default and the environment behaviour)\n"
    '- "The matcher." above `struct Matcher` -> bloated 0.7 (only the name, no fact)\n\n'
    "Reply with JSON only."
)


def _label_user(segment: Segment) -> str:
    code = segment.follows_code.strip()
    code_block = f"\nThe code beneath it:\n{code}\n" if code else ""
    return (
        f"The {segment.kind}:\n{segment.text}\n{code_block}\n"
        'Return {"bloated": true|false, "score": 0.0-1.0, "reason": "<one sentence>"}. '
        "score is how low-value the comment is: 0 is essential, 1 is pure noise."
    )


def label_segment(segment: Segment, provider: Provider) -> Label:
    """Ask the model whether a segment is low-value, for classifier training."""
    raw = provider.complete(_LABEL_SYSTEM, _label_user(segment))
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return Label(bloated=False, score=0.0)
    score = float(parsed.get("score", 0.0) or 0.0)
    return Label(
        bloated=bool(parsed.get("bloated", score >= 0.5)),
        score=max(0.0, min(1.0, score)),
        reason=str(parsed.get("reason", "")).strip(),
    )


@dataclass
class JudgmentCache:
    """A content-addressed cache so a re-run costs nothing.

    The key is the model, the segment text, the code beneath it, and the rule
    set. Any change to any of those is a cache miss; nothing else is.
    """

    directory: Path = field(default_factory=lambda: _CACHE_DIR)

    def _key(self, model: str, segment: Segment, tag: str) -> Path:
        digest = hashlib.sha256(
            f"{model}\x00{tag}\x00{segment.text}\x00{segment.follows_code}".encode()
        ).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, model: str, segment: Segment, tag: str) -> object | None:
        path = self._key(model, segment, tag)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, model: str, segment: Segment, tag: str, value: object) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            self._key(model, segment, tag).write_text(json.dumps(value))


def _cache_coordinates(provider: Provider, rules: list[Rule]) -> tuple[str, str]:
    """The cache key parts that are not the segment.

    The tag hashes the full rule content, not just the ids, so editing a
    summary or a judge note invalidates the verdicts it shaped.
    """
    model = str(getattr(provider, "model", provider.name))
    content = "\x00".join(sorted(f"{r.id}|{r.summary}|{r.judge_note}" for r in rules))
    tag = "judge:" + hashlib.sha256(content.encode()).hexdigest()[:16]
    return model, tag


def cached_verdicts(
    segment: Segment, rules: list[Rule], provider: Provider, cache: JudgmentCache
) -> list[Verdict] | None:
    """The stored verdicts for this segment and rule set, or None on a miss."""
    model, tag = _cache_coordinates(provider, rules)
    hit = cache.get(model, segment, tag)
    if isinstance(hit, list):
        return [Verdict(**item) for item in hit if isinstance(item, dict)]
    return None


def judge_segment_cached(
    segment: Segment, rules: list[Rule], provider: Provider, cache: JudgmentCache
) -> list[Verdict]:
    """judge_segment through the content-addressed cache, so a re-run costs nothing."""
    hit = cached_verdicts(segment, rules, provider, cache)
    if hit is not None:
        return hit
    verdicts = judge_segment(segment, rules, provider)
    model, tag = _cache_coordinates(provider, rules)
    cache.put(model, segment, tag, [asdict(v) for v in verdicts])
    return verdicts
