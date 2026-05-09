"""Agent executor with brain recall + outcome backfill, brain mocked."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from gtmos.agents import (
    AgentExecutor,
    AgentRun,
    _extract_applied_ids,
    _new_decision_id,
    report_outcome,
)
from gtmos.brain import BrainBridge, BrainError, MemoryHit
from gtmos.config import Settings
from gtmos.llm import LLMResponse


def _setup(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    (tmp_repo / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
    (tmp_repo / "BRAND_GUIDELINES.md").write_text("# brand\n", encoding="utf-8")
    (tmp_repo / "agents").mkdir(exist_ok=True)
    (tmp_repo / "agents" / "weekly-review.md").write_text(
        "# Agent — weekly-review\n\nA stub agent for executor brain tests, "
        "long enough to clear the minimum-content gate.\n",
        encoding="utf-8",
    )
    (tmp_repo / "evals").mkdir(exist_ok=True)
    (tmp_repo / "evals" / "weekly-review.yaml").write_text(
        yaml.safe_dump(
            {
                "agent": "weekly-review",
                "judge": {"model": "x", "prompt": "x"},
                "pass_threshold": 8.0,
                "rubric": [{"id": "x", "weight": 1.0, "description": "x"}],
                "fixtures": [{"id": f"f{i}", "input": {}} for i in range(3)],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")
    return Settings.load()


class _StubBrain(BrainBridge):
    """Minimal stub that records calls + returns canned data."""

    def __init__(self) -> None:
        self.searches: list[str] = []
        self.useds: list[tuple[int, str]] = []
        self.outcomes: list[tuple[int, str, str]] = []

    def search(  # type: ignore[override]
        self, query: str, *, limit: int = 5, min_confidence: float = 0.5
    ) -> list[MemoryHit]:
        self.searches.append(query)
        return [
            MemoryHit(
                id=694,
                title="GTM OS architecture catalog",
                preview="5 layers: Doctrine + Surfaces + Agents + Pipelines + Eval",
                confidence=0.7,
                source_trust="core",
            ),
            MemoryHit(
                id=225,
                title="Strat-Agent Model",
                preview="humans close",
                confidence=0.69,
                source_trust="core",
            ),
        ]

    def used(self, memory_id: int, context: str = "") -> int:  # type: ignore[override]
        self.useds.append((memory_id, context))
        return 1000 + memory_id

    def outcome(self, usage_id: int, verdict: str, note: str = "") -> None:  # type: ignore[override]
        self.outcomes.append((usage_id, verdict, note))


def _make_executor(settings: Settings, brain: BrainBridge | None, agent_text: str) -> AgentExecutor:
    class _LLM:
        def complete(self, **kwargs: Any) -> LLMResponse:
            return LLMResponse(
                text=agent_text,
                model="claude-test",
                input_tokens=1,
                output_tokens=1,
                cache_read_tokens=0,
                cache_creation_tokens=0,
                stop_reason="end_turn",
            )

    return AgentExecutor(settings=settings, llm=_LLM(), brain=brain)  # type: ignore[arg-type]


class TestRecallAndUsage:
    def test_recall_seeds_system_prompt_and_logs_applied(
        self, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _setup(tmp_repo, monkeypatch)
        brain = _StubBrain()
        agent_text = (
            "Verdict: ship it.\n\n"
            "[[brain.applied: #694 — 5-layer architecture]]\n"
            "[[brain.applied: #225 — humans close]]"
        )
        ex = _make_executor(settings, brain, agent_text)
        run = ex.run("weekly-review", inputs={"client": "acme"}, client_slug="acme")
        assert run.error is None
        assert run.decision_id is not None
        # Both applied memories were logged via brain.used
        applied = sorted(uid for uid, _ in brain.useds)
        assert applied == [225, 694]
        assert run.brain_usage_ids == (1000 + 694, 1000 + 225)

    def test_no_applied_no_usage_logged(
        self, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _setup(tmp_repo, monkeypatch)
        brain = _StubBrain()
        ex = _make_executor(settings, brain, "Verdict: skip. Nothing cited.")
        run = ex.run("weekly-review", inputs={"x": 1})
        assert brain.useds == []
        assert run.brain_usage_ids == ()

    def test_brain_search_failure_does_not_block(
        self, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _setup(tmp_repo, monkeypatch)

        class _BrokenBrain(_StubBrain):
            def search(self, query: str, *, limit: int = 5, min_confidence: float = 0.5):  # type: ignore[override]
                raise BrainError("brain down")

        brain = _BrokenBrain()
        ex = _make_executor(settings, brain, "Verdict: ok.")
        run = ex.run("weekly-review", inputs={})
        assert run.error is None  # pipeline survives a brain outage


class TestOutcomeReporting:
    def test_report_outcome_closes_each_usage(
        self, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _setup(tmp_repo, monkeypatch)
        brain = _StubBrain()
        ex = _make_executor(settings, brain, "ok [[brain.applied: #694]]")
        run = ex.run("weekly-review", inputs={})
        n = report_outcome(ex, run, "win", note="acme closed")
        assert n == 1
        assert brain.outcomes == [(1000 + 694, "win", "acme closed")]

    def test_report_outcome_no_brain_no_op(
        self, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _setup(tmp_repo, monkeypatch)
        ex = _make_executor(settings, brain=None, agent_text="ok")
        run = AgentRun(
            name="weekly-review",
            output_text="x",
            response=None,
            artifact_path=tmp_repo / "x.md",
            brain_usage_ids=(1234,),
        )
        assert report_outcome(ex, run, "win") == 0


class TestHelpers:
    def test_extract_applied_ids(self) -> None:
        text = "[[brain.applied: #1]] [[brain.applied: 2]] [[brain.applied: #3 — note]]"
        assert _extract_applied_ids(text) == [1, 2, 3]

    def test_new_decision_id_components(self) -> None:
        d = _new_decision_id("weekly-review", "acme", "review")
        assert d.startswith("weekly-review-acme-review-")
        # contains a 6-char hex suffix
        assert len(d.split("-")[-1]) == 6
