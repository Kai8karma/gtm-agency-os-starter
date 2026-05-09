"""Eval judge — runs an agent against fixtures, scores via Claude.

Each `evals/<agent>.yaml` declares:
  * judge.model      — model used to grade
  * pass_threshold   — minimum score (0-10)
  * rubric           — list of {id, weight, description}
  * fixtures         — list of {id, description, input, expected_signals?}

The judge:
  1. validates the YAML structure (also done by ``scripts/run-evals.sh``),
  2. runs the agent against each fixture (offline mode skips the LLM call),
  3. asks the judge model to grade output against the rubric, returning JSON,
  4. aggregates fixture scores → overall score,
  5. compares against ``pass_threshold``.

In ``offline`` mode, judging falls through to the structural checks already
covered by ``scripts/run-evals.sh`` so CI without API keys still proves the
harness works.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gtmos.agents import AgentExecutor
from gtmos.config import Settings
from gtmos.llm import LLMClient, env_offline
from gtmos.security import safe_join

logger = logging.getLogger(__name__)


class EvalError(Exception):
    """Raised when an eval definition is malformed."""


_REQUIRED_KEYS = ("agent", "judge", "rubric", "fixtures", "pass_threshold")


@dataclass(frozen=True)
class FixtureScore:
    fixture_id: str
    score: float
    reasoning: str
    rubric_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class EvalResult:
    agent: str
    threshold: float
    fixture_scores: list[FixtureScore] = field(default_factory=list)
    error: str | None = None

    @property
    def overall(self) -> float:
        if not self.fixture_scores:
            return 0.0
        return sum(f.score for f in self.fixture_scores) / len(self.fixture_scores)

    @property
    def passed(self) -> bool:
        return self.error is None and self.overall >= self.threshold


@dataclass
class EvalRunner:
    settings: Settings
    judge_llm: LLMClient
    executor: AgentExecutor

    @classmethod
    def from_settings(cls, settings: Settings) -> EvalRunner:
        llm = LLMClient.from_settings(settings)
        executor = AgentExecutor(settings=settings, llm=llm)
        return cls(settings=settings, judge_llm=llm, executor=executor)

    # ---- top-level loop -----------------------------------------------------

    def run(self, agent_name: str, *, mode: str = "auto") -> EvalResult:
        spec = _load_spec(self.settings.repo_root, agent_name)
        threshold = float(spec["pass_threshold"])
        result = EvalResult(agent=agent_name, threshold=threshold)

        if mode == "auto":
            mode = "structural" if env_offline() else "judge"
        if mode not in {"structural", "judge"}:
            raise EvalError(f"unknown mode {mode!r}")

        for fixture in spec["fixtures"]:
            fixture_id = str(fixture.get("id") or "unnamed")
            try:
                if mode == "structural":
                    score = _structural_score(spec, fixture)
                    result.fixture_scores.append(
                        FixtureScore(
                            fixture_id=fixture_id,
                            score=score,
                            reasoning="structural pass (offline mode)",
                        )
                    )
                else:
                    score = self._judge_one(spec, agent_name, fixture)
                    result.fixture_scores.append(score)
            except Exception as e:
                logger.exception("fixture %s failed", fixture_id)
                result.error = f"{fixture_id}: {e}"
                break

        return result

    # ---- per-fixture --------------------------------------------------------

    def _judge_one(
        self, spec: dict[str, Any], agent_name: str, fixture: dict[str, Any]
    ) -> FixtureScore:
        fixture_id = str(fixture.get("id") or "unnamed")
        agent_run = self.executor.run(
            agent_name,
            inputs=fixture.get("input") or {},
            task=f"eval-{fixture_id}",
        )
        if agent_run.error:
            return FixtureScore(
                fixture_id=fixture_id,
                score=0.0,
                reasoning=f"agent error: {agent_run.error}",
            )

        judge_model = (
            spec.get("judge", {}).get("model") or self.settings.judge_model
        )
        judge_prompt = spec.get("judge", {}).get("prompt") or _DEFAULT_JUDGE_PROMPT
        rubric = spec.get("rubric") or []

        system = (
            judge_prompt
            + "\n\nRubric items (with weights):\n"
            + "\n".join(
                f"- {r.get('id')} (w={r.get('weight'):.2f}): {r.get('description')}"
                for r in rubric
            )
            + "\n\nRespond ONLY with a JSON object:"
            "\n  {"
            '\n    "score": <0-10>,'
            '\n    "reasoning": "<one paragraph>",'
            '\n    "rubric_breakdown": {"<id>": <0-10>, ...}'
            "\n  }"
        )

        user = (
            f"Fixture: {fixture_id}\n"
            f"Description: {fixture.get('description','')}\n\n"
            f"Agent input:\n```json\n{json.dumps(fixture.get('input', {}), indent=2)}"
            "\n```\n\n"
            f"Expected signals: {fixture.get('expected_signals', [])}\n\n"
            f"Agent output:\n```\n{agent_run.output_text}\n```"
        )

        resp = self.judge_llm.complete(
            model=judge_model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=600,
            temperature=0.0,
        )
        return _parse_judge_response(fixture_id, resp.text)


# ---- helpers ---------------------------------------------------------------


def _load_spec(repo_root: Path, agent_name: str) -> dict[str, Any]:
    path = safe_join(repo_root, "evals", f"{agent_name}.yaml")
    if not path.is_file():
        raise EvalError(f"evals/{agent_name}.yaml not found")
    with path.open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
        raise EvalError(f"evals/{agent_name}.yaml is not a mapping")
    for k in _REQUIRED_KEYS:
        if k not in spec:
            raise EvalError(f"evals/{agent_name}.yaml missing key '{k}'")
    fixtures = spec.get("fixtures") or []
    if len(fixtures) < 3:
        raise EvalError(
            f"evals/{agent_name}.yaml must declare ≥3 fixtures (got {len(fixtures)})"
        )
    rubric = spec.get("rubric") or []
    if rubric:
        weight_sum = sum(float(r.get("weight", 0)) for r in rubric)
        if abs(weight_sum - 1.0) > 0.01:
            raise EvalError(
                f"evals/{agent_name}.yaml rubric weights sum to {weight_sum:.2f} "
                "(expected 1.00)"
            )
    threshold = float(spec.get("pass_threshold", 0))
    if not 0 < threshold <= 10:
        raise EvalError(
            f"evals/{agent_name}.yaml pass_threshold {threshold} out of (0, 10]"
        )
    return spec


def _structural_score(spec: dict[str, Any], fixture: dict[str, Any]) -> float:
    """In offline mode every well-formed fixture scores at threshold + 0.5."""
    threshold = float(spec.get("pass_threshold", 8.0))
    fid = fixture.get("id")
    if not isinstance(fid, str) or not fid:
        raise EvalError("fixture missing 'id'")
    if "input" not in fixture:
        raise EvalError(f"fixture {fid!r} missing 'input'")
    return min(threshold + 0.5, 10.0)


def _parse_judge_response(fixture_id: str, text: str) -> FixtureScore:
    """Tolerant JSON extraction — judge may wrap output in prose or ```json."""
    candidate = _extract_json(text)
    if candidate is None:
        return FixtureScore(
            fixture_id=fixture_id,
            score=0.0,
            reasoning=f"could not parse judge response: {text[:200]!r}",
        )
    try:
        score = float(candidate.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(10.0, score))
    breakdown_raw = candidate.get("rubric_breakdown") or {}
    breakdown: dict[str, float] = {}
    if isinstance(breakdown_raw, dict):
        for k, v in breakdown_raw.items():
            try:
                breakdown[str(k)] = max(0.0, min(10.0, float(v)))
            except (TypeError, ValueError):
                continue
    return FixtureScore(
        fixture_id=fixture_id,
        score=score,
        reasoning=str(candidate.get("reasoning", ""))[:1000],
        rubric_breakdown=breakdown,
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    # Try direct parse first.
    stripped = text.strip()
    for candidate in (stripped, _strip_codeblock(stripped)):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    # Fallback: find first '{' and walk to matching '}'.
    start = stripped.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(stripped[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(stripped[start : i + 1])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    return None
    return None


def _strip_codeblock(text: str) -> str:
    if text.startswith("```"):
        # strip language tag + closing fence
        first_newline = text.find("\n")
        if first_newline > 0:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


_DEFAULT_JUDGE_PROMPT = (
    "You are a strict evaluator for a B2B GTM agency's agent outputs. "
    "Grade the output against the rubric. Penalize banned phrases, "
    "missing provenance, vague metrics, and any auto-publish behavior. "
    "Score conservatively — only the best outputs deserve 9-10."
)


# Keep CLI runners that don't go through Settings.load() (offline scripts) able
# to call the structural path with just paths. Public so scripts/run-evals.sh
# can adopt it incrementally.

def evaluate_offline(repo_root: Path, agent_name: str) -> EvalResult:
    """Run structural-only eval for `agent_name`. Does not require API keys."""
    spec = _load_spec(repo_root, agent_name)
    result = EvalResult(agent=agent_name, threshold=float(spec["pass_threshold"]))
    for fixture in spec["fixtures"]:
        fid = str(fixture.get("id") or "unnamed")
        try:
            score = _structural_score(spec, fixture)
            result.fixture_scores.append(
                FixtureScore(
                    fixture_id=fid,
                    score=score,
                    reasoning="structural pass (offline mode)",
                )
            )
        except EvalError as e:
            result.error = f"{fid}: {e}"
            break
    return result


__all__ = [
    "EvalError",
    "EvalResult",
    "EvalRunner",
    "FixtureScore",
    "evaluate_offline",
]


# `os` is referenced for typing-driven import dropping in some lint configs.
_ = os
