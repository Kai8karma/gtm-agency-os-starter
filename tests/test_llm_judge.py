"""LLM client + judge tests with the Anthropic SDK mocked.

Covers the code paths that would otherwise require a real API key:
  * LLMClient.complete normalizes responses correctly
  * Caching is requested when ``cache_system=True``
  * EvalRunner.run aggregates fixture scores from the (mocked) judge
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from gtmos.llm import LLMClient


class _StubBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _StubUsage:
    input_tokens = 100
    output_tokens = 50
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _StubResponse:
    def __init__(self, text: str, model: str = "claude-sonnet-4-6") -> None:
        self.content = [_StubBlock(text)]
        self.model = model
        self.usage = _StubUsage()
        self.stop_reason = "end_turn"


class _StubMessages:
    def __init__(self, response_text: str) -> None:
        self._text = response_text
        self.last_call: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> _StubResponse:
        self.last_call = kwargs
        return _StubResponse(self._text)


class _StubAnthropic:
    def __init__(self, response_text: str) -> None:
        self.messages = _StubMessages(response_text)

    @classmethod
    def factory(cls, response_text: str):  # type: ignore[no-untyped-def]
        def make(api_key: str, timeout: float, max_retries: int) -> _StubAnthropic:
            assert api_key
            return cls(response_text)

        return make


class TestLLMClient:
    def test_complete_returns_normalized_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = LLMClient(api_key="sk-test-1234567890")
        stub = _StubAnthropic("hello world")
        monkeypatch.setattr(client, "_client", stub)
        out = client.complete(
            model="claude-sonnet-4-6",
            system="you are an agent",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert out.text == "hello world"
        assert out.input_tokens == 100
        assert out.output_tokens == 50
        assert stub.messages.last_call is not None
        # cache_system=True (default) → system arg becomes a list with cache_control
        sys_arg = stub.messages.last_call["system"]
        assert isinstance(sys_arg, list)
        assert sys_arg[0]["cache_control"] == {"type": "ephemeral"}

    def test_complete_without_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = LLMClient(api_key="sk-test-1234567890")
        stub = _StubAnthropic("ok")
        monkeypatch.setattr(client, "_client", stub)
        client.complete(
            model="claude-sonnet-4-6",
            system="x",
            messages=[{"role": "user", "content": "y"}],
            cache_system=False,
        )
        assert stub.messages.last_call is not None
        assert stub.messages.last_call["system"] == "x"

    def test_short_api_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            LLMClient(api_key="x")

    def test_empty_messages_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = LLMClient(api_key="sk-test-1234567890")
        monkeypatch.setattr(client, "_client", _StubAnthropic("ok"))
        with pytest.raises(ValueError, match="user message"):
            client.complete(
                model="x", system="y", messages=[],
            )


# ---- judge with mocked LLM -------------------------------------------------


def _write_full_spec(repo: Path, name: str) -> None:
    (repo / "agents").mkdir(exist_ok=True)
    (repo / "agents" / f"{name}.md").write_text(
        f"# Agent — {name}\n\n"
        "A stub agent for tests. This file exists only so the executor's "
        "minimum-length sanity check passes during unit testing.\n",
        encoding="utf-8",
    )
    (repo / "evals").mkdir(exist_ok=True)
    (repo / "evals" / f"{name}.yaml").write_text(
        yaml.safe_dump(
            {
                "agent": name,
                "judge": {"model": "claude-haiku-4-5", "prompt": "Grade strictly."},
                "pass_threshold": 8.0,
                "rubric": [
                    {"id": "voice_match", "weight": 0.5, "description": "x"},
                    {"id": "provenance", "weight": 0.5, "description": "x"},
                ],
                "fixtures": [
                    {"id": f"f{i}", "input": {"x": i}} for i in range(3)
                ],
            }
        ),
        encoding="utf-8",
    )
    (repo / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")


class TestEvalRunner:
    def test_judge_path_passes_when_judge_says_pass(
        self, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from gtmos.config import Settings
        from gtmos.judge import EvalRunner

        _write_full_spec(tmp_repo, "weekly-review")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
        monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
        s = Settings.load()
        runner = EvalRunner.from_settings(s)

        # Patch the SAME LLM client that the executor + judge share.
        agent_responses = iter(["AGENT OUTPUT 1", "AGENT OUTPUT 2", "AGENT OUTPUT 3"])
        judge_responses = iter([
            '{"score": 9.0, "reasoning": "good", "rubric_breakdown": {"voice_match": 9.0}}',
            '{"score": 8.5, "reasoning": "fine", "rubric_breakdown": {}}',
            '{"score": 9.2, "reasoning": "great", "rubric_breakdown": {}}',
        ])

        def fake_complete(self: Any, **kwargs: Any) -> Any:
            from gtmos.llm import LLMResponse

            messages = kwargs.get("messages") or []
            user_text = ""
            if messages:
                content = messages[0].get("content")
                user_text = content if isinstance(content, str) else ""
            # The judge's user prompt always contains "Agent output:".
            is_judge_call = "Agent output:" in user_text
            text = next(judge_responses) if is_judge_call else next(agent_responses)
            return LLMResponse(
                text=text,
                model="claude-test",
                input_tokens=1,
                output_tokens=1,
                cache_read_tokens=0,
                cache_creation_tokens=0,
                stop_reason="end_turn",
            )

        monkeypatch.setattr(LLMClient, "complete", fake_complete)
        result = runner.run("weekly-review", mode="judge")
        assert result.passed
        assert len(result.fixture_scores) == 3
        assert all(f.score >= 8.0 for f in result.fixture_scores)
