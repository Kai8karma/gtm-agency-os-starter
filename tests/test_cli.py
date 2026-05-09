"""CLI smoke tests — argparse routing + offline subcommands."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pytest
import yaml

from gtmos.cli import main


def _ready_repo(repo: Path) -> None:
    """Drop a minimum doctrine + agent + eval into ``repo``."""
    (repo / "CLAUDE.md").write_text("# CLAUDE\n" + ("\n" * 60), encoding="utf-8")
    (repo / "agents").mkdir(exist_ok=True)
    (repo / "agents" / "weekly-review.md").write_text(
        "# Agent — weekly-review\n\nA weekly per-client review agent for tests.\n",
        encoding="utf-8",
    )
    (repo / "evals").mkdir(exist_ok=True)
    (repo / "evals" / "weekly-review.yaml").write_text(
        yaml.safe_dump(
            {
                "agent": "weekly-review",
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


@pytest.fixture
def cli_repo(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("GTMOS_OFFLINE", "1")
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")
    _ready_repo(tmp_repo)
    return tmp_repo


def _capture(monkeypatch: pytest.MonkeyPatch) -> StringIO:
    buf = StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    return buf


class TestVerify:
    def test_verify_passes(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = _capture(monkeypatch)
        rc = main(["verify"])
        assert rc == 0
        assert "PASS" in out.getvalue()

    def test_verify_fails_when_eval_missing(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (cli_repo / "evals" / "weekly-review.yaml").unlink()
        out = _capture(monkeypatch)
        rc = main(["verify"])
        assert rc == 1
        assert "no evals/weekly-review.yaml" in out.getvalue()


class TestEval:
    def test_structural_mode_passes(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = _capture(monkeypatch)
        rc = main(["eval", "--mode", "structural"])
        assert rc == 0
        assert "weekly-review" in out.getvalue()

    def test_single_agent(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = main(["eval", "weekly-review", "--mode", "structural"])
        assert rc == 0


class TestClients:
    def test_lists_active_only(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (cli_repo / "clients").mkdir(exist_ok=True)
        (cli_repo / "clients" / "_example").mkdir()
        (cli_repo / "clients" / "_example" / "client.md").write_text(
            "---\nslug: _example\nname: Tpl\n---\n", encoding="utf-8"
        )
        (cli_repo / "clients" / "acme").mkdir()
        (cli_repo / "clients" / "acme" / "client.md").write_text(
            "---\nslug: acme\nname: Acme\n---\n", encoding="utf-8"
        )
        out = _capture(monkeypatch)
        rc = main(["clients"])
        assert rc == 0
        assert "acme" in out.getvalue()
        assert "_example" not in out.getvalue()

    def test_include_template_flag(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (cli_repo / "clients").mkdir(exist_ok=True)
        (cli_repo / "clients" / "_example").mkdir()
        (cli_repo / "clients" / "_example" / "client.md").write_text(
            "---\nslug: _example\nname: Tpl\n---\n", encoding="utf-8"
        )
        out = _capture(monkeypatch)
        rc = main(["clients", "--include-template"])
        assert rc == 0
        assert "_example" in out.getvalue()


class TestTasks:
    def test_add_list_done_roundtrip(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out1 = _capture(monkeypatch)
        rc = main([
            "tasks", "add",
            "--title", "Test task",
            "--owner", "U0KAI",
            "--client", "acme",
            "--due", "2099-01-01T00:00:00+00:00",
        ])
        assert rc == 0
        assert "added task" in out1.getvalue()

        out2 = _capture(monkeypatch)
        rc = main(["tasks", "list", "--owner", "U0KAI"])
        assert rc == 0
        assert "Test task" in out2.getvalue()

    def test_add_rejects_naive_datetime(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = main([
            "tasks", "add",
            "--title", "T",
            "--owner", "U0KAI",
            "--client", "acme",
            "--due", "2099-01-01T00:00:00",
        ])
        assert rc == 2

    def test_overdue_empty(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = _capture(monkeypatch)
        rc = main(["tasks", "overdue"])
        assert rc == 0
        assert "no overdue" in out.getvalue() or "DM" in out.getvalue()


class TestRunAgent:
    def test_invalid_input_json_rejected(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = main(["run-agent", "weekly-review", "--input", "not json"])
        assert rc == 2

    def test_input_must_be_object(
        self, cli_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # JSON arrays aren't accepted (must be a dict).
        rc = main(["run-agent", "weekly-review", "--input", "[1,2,3]"])
        assert rc == 2


class TestVersionFlag:
    def test_version_flag(self, cli_repo: Path, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit) as ei:
            main(["--version"])
        assert ei.value.code == 0


class TestUnknownSubcommand:
    def test_unknown_subcommand(
        self, cli_repo: Path, capsys: pytest.CaptureFixture
    ) -> None:
        with pytest.raises(SystemExit):
            main(["does-not-exist"])
