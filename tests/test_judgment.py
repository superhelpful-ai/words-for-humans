from __future__ import annotations

import json

from words_for_humans.judgment import (
    JudgmentCache,
    Label,
    MockProvider,
    judge_segment,
    label_segment,
)
from words_for_humans.model import Segment, SegmentKind
from words_for_humans.rules import rule


def _segment(text: str, code: str = "") -> Segment:
    return Segment(path="x.ts", line=1, kind=SegmentKind.COMMENT, text=text, follows_code=code)


class TestJudge:
    def test_reports_a_violation(self):
        provider = MockProvider(
            responses=[
                json.dumps(
                    {
                        "violations": [
                            {
                                "rule": "V-7",
                                "message": "Longer than the code.",
                                "suggestion": "Cut it.",
                            }
                        ]
                    }
                )
            ]
        )
        result = judge_segment(_segment("a long comment"), [rule("V-7")], provider)
        assert len(result) == 1
        assert result[0].rule_id == "V-7"
        assert result[0].violates
        assert result[0].suggestion == "Cut it."

    def test_drops_a_rule_not_in_the_asked_set(self):
        # The model hallucinates a rule that was not offered; it is discarded.
        provider = MockProvider(
            responses=[
                json.dumps({"violations": [{"rule": "A-9", "message": "restates the heading"}]})
            ]
        )
        assert judge_segment(_segment("text"), [rule("V-7")], provider) == []

    def test_no_violations_returns_empty(self):
        provider = MockProvider(responses=[json.dumps({"violations": []})])
        assert judge_segment(_segment("a good comment"), [rule("V-7")], provider) == []

    def test_tolerates_a_fenced_reply(self):
        provider = MockProvider(responses=['```json\n{"violations": []}\n```'])
        assert judge_segment(_segment("text"), [rule("V-7")], provider) == []


class TestLabel:
    def test_parses_a_label(self):
        provider = MockProvider(
            responses=[json.dumps({"bloated": True, "score": 0.9, "reason": "restates the code"})]
        )
        label = label_segment(_segment("restates code"), provider)
        assert label == Label(bloated=True, score=0.9, reason="restates the code")

    def test_clamps_the_score(self):
        provider = MockProvider(responses=[json.dumps({"bloated": True, "score": 1.7})])
        assert label_segment(_segment("x"), provider).score == 1.0

    def test_a_malformed_reply_is_not_bloated(self):
        provider = MockProvider(responses=["not json at all"])
        # _extract_json raises, but label_segment is called on a dict path; a bare
        # string reply surfaces as a ProviderError to the caller.
        try:
            label_segment(_segment("x"), provider)
            raised = False
        except Exception:
            raised = True
        assert raised


class TestJudgeNotes:
    def test_the_prompt_carries_the_calibration_note(self):
        from words_for_humans.judgment import _judge_user

        prompt = _judge_user(_segment("some text"), [rule("S-5")])
        assert "citation beside a stated fact" in prompt

    def test_editing_a_note_invalidates_the_cache(self):
        from dataclasses import replace

        from words_for_humans.judgment import _cache_coordinates

        provider = MockProvider()
        base = rule("S-5")
        edited = replace(base, judge_note="A different calibration.")
        assert _cache_coordinates(provider, [base]) != _cache_coordinates(provider, [edited])


class TestCache:
    def test_round_trips(self, tmp_path):
        cache = JudgmentCache(directory=tmp_path)
        seg = _segment("hello", "code()")
        assert cache.get("m", seg, "label") is None
        cache.put("m", seg, "label", {"score": 0.5})
        assert cache.get("m", seg, "label") == {"score": 0.5}

    def test_a_different_segment_misses(self, tmp_path):
        cache = JudgmentCache(directory=tmp_path)
        cache.put("m", _segment("hello"), "label", {"score": 0.5})
        assert cache.get("m", _segment("goodbye"), "label") is None


class TestProviderFromEnvironment:
    def test_unset_means_no_provider(self, monkeypatch):
        from words_for_humans.judgment import provider_from_environment

        monkeypatch.delenv("W4H_AI_PROVIDER", raising=False)
        assert provider_from_environment() is None

    def test_ollama_with_a_model_override(self, monkeypatch):
        from words_for_humans.judgment import OllamaProvider, provider_from_environment

        monkeypatch.setenv("W4H_AI_PROVIDER", "ollama")
        monkeypatch.setenv("W4H_AI_MODEL", "qwen3.5:4b")
        provider = provider_from_environment()
        assert isinstance(provider, OllamaProvider)
        assert provider.model == "qwen3.5:4b"

    def test_openrouter_reads_the_key(self, monkeypatch):
        from words_for_humans.judgment import OpenRouterProvider, provider_from_environment

        monkeypatch.setenv("W4H_AI_PROVIDER", "openrouter")
        monkeypatch.setenv("W4H_AI_KEY", "sk-test")
        monkeypatch.delenv("W4H_AI_MODEL", raising=False)
        provider = provider_from_environment()
        assert isinstance(provider, OpenRouterProvider)
        assert provider.api_key == "sk-test"

    def test_an_unknown_provider_is_an_error(self, monkeypatch):
        import pytest

        from words_for_humans.judgment import ProviderError, provider_from_environment

        monkeypatch.setenv("W4H_AI_PROVIDER", "clippy")
        with pytest.raises(ProviderError):
            provider_from_environment()


class TestJudgeSegmentCached:
    def test_a_rerun_answers_from_the_cache(self, tmp_path):
        from words_for_humans.judgment import judge_segment_cached

        response = json.dumps({"violations": [{"rule": "V-7", "message": "Too long."}]})
        provider = MockProvider(responses=[response])
        cache = JudgmentCache(directory=tmp_path)
        segment = _segment("a long comment")

        first = judge_segment_cached(segment, [rule("V-7")], provider, cache)
        second = judge_segment_cached(segment, [rule("V-7")], provider, cache)

        assert [v.rule_id for v in first] == ["V-7"]
        assert second == first
        assert len(provider.calls) == 1


class TestEngineJudgment:
    def test_verdicts_become_soft_findings(self, tmp_path, monkeypatch):
        from words_for_humans.checks.context import ContextMap
        from words_for_humans.config import Config
        from words_for_humans.dictionary import Dictionary
        from words_for_humans.engine import judgment_findings
        from words_for_humans.rules import Severity

        monkeypatch.setattr("words_for_humans.judgment._CACHE_DIR", tmp_path)
        response = json.dumps(
            {"violations": [{"rule": "V-7", "message": "Longer than the code below."}]}
        )
        provider = MockProvider(responses=[response])
        contexts = ContextMap(Dictionary(), Config())
        segment = _segment("a comment that runs on")

        findings = judgment_findings([segment], contexts, provider)

        assert [f.rule_id for f in findings] == ["V-7"]
        assert findings[0].severity is Severity.SOFT
        assert findings[0].path == "x.ts"


class TestOllamaCloud:
    def test_a_key_implies_the_hosted_service(self, monkeypatch):
        from words_for_humans.judgment import OllamaProvider, provider_from_environment

        monkeypatch.setenv("W4H_AI_PROVIDER", "ollama")
        monkeypatch.setenv("W4H_AI_KEY", "ok-test")
        monkeypatch.delenv("W4H_AI_HOST", raising=False)
        monkeypatch.delenv("W4H_AI_MODEL", raising=False)
        provider = provider_from_environment()
        assert isinstance(provider, OllamaProvider)
        assert provider.host == "https://ollama.com"
        assert provider.api_key == "ok-test"

    def test_an_explicit_host_wins_over_the_implied_one(self, monkeypatch):
        from words_for_humans.judgment import provider_from_environment

        monkeypatch.setenv("W4H_AI_PROVIDER", "ollama")
        monkeypatch.setenv("W4H_AI_KEY", "ok-test")
        monkeypatch.setenv("W4H_AI_HOST", "http://gpu-box:11434")
        provider = provider_from_environment()
        assert provider is not None
        assert provider.host == "http://gpu-box:11434"

    def test_no_key_keeps_the_local_daemon(self, monkeypatch):
        from words_for_humans.judgment import provider_from_environment

        monkeypatch.setenv("W4H_AI_PROVIDER", "ollama")
        monkeypatch.delenv("W4H_AI_KEY", raising=False)
        monkeypatch.delenv("W4H_AI_HOST", raising=False)
        provider = provider_from_environment()
        assert provider is not None
        assert provider.host == "http://localhost:11434"
        assert provider.api_key == ""


class TestParallelJudgment:
    @staticmethod
    def _contexts():
        from words_for_humans.checks.context import ContextMap
        from words_for_humans.config import Config
        from words_for_humans.dictionary import Dictionary

        return ContextMap(Dictionary(), Config())

    def test_concurrency_defaults_by_provider(self, monkeypatch):
        from words_for_humans.engine import _judgment_concurrency
        from words_for_humans.judgment import OllamaProvider

        monkeypatch.delenv("W4H_AI_CONCURRENCY", raising=False)
        assert _judgment_concurrency(OllamaProvider()) == 1
        assert _judgment_concurrency(OllamaProvider(api_key="k")) == 8
        monkeypatch.setenv("W4H_AI_CONCURRENCY", "3")
        assert _judgment_concurrency(OllamaProvider()) == 3

    def test_parallel_calls_produce_the_same_findings(self, tmp_path, monkeypatch):
        from dataclasses import dataclass, field

        from words_for_humans.engine import judgment_findings

        @dataclass
        class SteadyProvider:
            """Thread-safe: every call returns the same verdict."""

            api_key: str = "k"
            name: str = "steady"
            model: str = "steady"
            count: int = 0
            _lock: object = field(default_factory=__import__("threading").Lock)

            def complete(self, system: str, user: str) -> str:
                with self._lock:
                    self.count += 1
                return json.dumps(
                    {"violations": [{"rule": "V-7", "message": "Longer than the code."}]}
                )

        monkeypatch.setattr("words_for_humans.judgment._CACHE_DIR", tmp_path)
        monkeypatch.setenv("W4H_AI_CONCURRENCY", "4")
        provider = SteadyProvider()
        segments = [_segment(f"comment number {n} runs on") for n in range(6)]

        findings = judgment_findings(segments, self._contexts(), provider)

        assert len(findings) == 6
        assert provider.count == 6

    def test_cache_hits_do_not_consume_the_call_cap(self, tmp_path, monkeypatch):
        from words_for_humans.engine import judgment_findings

        monkeypatch.setattr("words_for_humans.judgment._CACHE_DIR", tmp_path)
        monkeypatch.delenv("W4H_AI_CONCURRENCY", raising=False)
        response = json.dumps({"violations": [{"rule": "V-7", "message": "Too long."}]})
        segment = _segment("one comment that runs on")

        first = judgment_findings([segment], self._contexts(), MockProvider(responses=[response]))
        monkeypatch.setenv("W4H_AI_LIMIT", "0")
        second = judgment_findings([segment], self._contexts(), MockProvider(responses=[]))

        assert len(first) == 1
        assert [f.rule_id for f in second] == ["V-7"]
