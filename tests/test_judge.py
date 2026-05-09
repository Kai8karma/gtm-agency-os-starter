"""Eval judge — structural mode + JSON parsing tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gtmos.judge import EvalError, _extract_json, _load_spec, evaluate_offline


def _write_spec(tmp_repo: Path, name: str, **overrides: object) -> None:
    base = {
        "agent": name,
        "judge": {"model": "claude-haiku-4-5", "prompt": "Grade strictly."},
        "pass_threshold": 8.0,
        "rubric": [
            {"id": "voice_match", "weight": 0.5, "description": "matches voice"},
            {"id": "provenance", "weight": 0.5, "description": "footer present"},
        ],
        "fixtures": [
            {"id": f"f-{i}", "input": {"k": i}, "expected_signals": []} for i in range(3)
        ],
    }
    base.update(overrides)
    (tmp_repo / "evals").mkdir(exist_ok=True)
    (tmp_repo / "evals" / f"{name}.yaml").write_text(yaml.safe_dump(base), encoding="utf-8")
    (tmp_repo / "agents").mkdir(exist_ok=True)
    (tmp_repo / "agents" / f"{name}.md").write_text(
        "# Agent — " + name + "\n\nThis is a test agent for unit testing.\n",
        encoding="utf-8",
    )


class TestLoadSpec:
    def test_valid_spec_loads(self, tmp_repo: Path) -> None:
        _write_spec(tmp_repo, "x")
        spec = _load_spec(tmp_repo, "x")
        assert spec["agent"] == "x"

    def test_missing_required_key_raises(self, tmp_repo: Path) -> None:
        _write_spec(tmp_repo, "x")
        # corrupt the spec
        path = tmp_repo / "evals" / "x.yaml"
        spec = yaml.safe_load(path.read_text())
        del spec["pass_threshold"]
        path.write_text(yaml.safe_dump(spec))
        with pytest.raises(EvalError, match="pass_threshold"):
            _load_spec(tmp_repo, "x")

    def test_too_few_fixtures_raises(self, tmp_repo: Path) -> None:
        _write_spec(tmp_repo, "x", fixtures=[{"id": "f1", "input": {}}])
        with pytest.raises(EvalError, match="≥3 fixtures"):
            _load_spec(tmp_repo, "x")

    def test_rubric_weights_must_sum_to_one(self, tmp_repo: Path) -> None:
        _write_spec(
            tmp_repo,
            "x",
            rubric=[
                {"id": "a", "weight": 0.3, "description": ""},
                {"id": "b", "weight": 0.3, "description": ""},
            ],
        )
        with pytest.raises(EvalError, match="weights sum"):
            _load_spec(tmp_repo, "x")

    def test_threshold_out_of_range(self, tmp_repo: Path) -> None:
        _write_spec(tmp_repo, "x", pass_threshold=15)
        with pytest.raises(EvalError, match="pass_threshold"):
            _load_spec(tmp_repo, "x")

    def test_missing_eval_file_raises(self, tmp_repo: Path) -> None:
        with pytest.raises(EvalError, match="not found"):
            _load_spec(tmp_repo, "missing")


class TestEvaluateOffline:
    def test_passes_well_formed_spec(self, tmp_repo: Path) -> None:
        _write_spec(tmp_repo, "x")
        result = evaluate_offline(tmp_repo, "x")
        assert result.error is None
        assert result.passed
        assert len(result.fixture_scores) == 3
        assert all(f.score >= 8.0 for f in result.fixture_scores)


class TestExtractJSON:
    def test_direct_object(self) -> None:
        out = _extract_json('{"score": 9.1, "reasoning": "ok"}')
        assert out == {"score": 9.1, "reasoning": "ok"}

    def test_codeblock_wrapped(self) -> None:
        text = '```json\n{"score": 8.0, "reasoning": "fine"}\n```'
        out = _extract_json(text)
        assert out is not None
        assert out["score"] == 8.0

    def test_object_inside_prose(self) -> None:
        text = (
            "Here is the grade.\n"
            'I think the answer is {"score": 7.5, "reasoning": "meh"} done.'
        )
        out = _extract_json(text)
        assert out is not None
        assert out["score"] == 7.5

    def test_no_json_returns_none(self) -> None:
        assert _extract_json("no json at all") is None
        assert _extract_json("") is None

    def test_unbalanced_braces_returns_none(self) -> None:
        # `{` with no closing `}` should return None, not crash.
        assert _extract_json("{ {{ ") is None
