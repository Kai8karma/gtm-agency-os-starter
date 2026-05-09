"""Routine dispatcher tests — fanout + skip conditions, agent calls mocked."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def routines_repo(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")
    (tmp_repo / "agents").mkdir(exist_ok=True)
    (tmp_repo / "agents" / "weekly-review.md").write_text(
        "# Agent — weekly-review\n\nA weekly per-client review agent for tests.\n",
        encoding="utf-8",
    )
    (tmp_repo / "routines").mkdir(exist_ok=True)
    (tmp_repo / "routines" / "per-client-weekly-review.md").write_text(
        "---\n"
        "name: per-client-weekly-review\n"
        "fanout: per-client\n"
        "agent: agents/weekly-review.md\n"
        "---\n# routine\n",
        encoding="utf-8",
    )
    (tmp_repo / "routines" / "task-cron.md").write_text(
        "---\nname: task-cron\nfanout: none\n---\n# task-cron\n",
        encoding="utf-8",
    )
    (tmp_repo / "routines" / "weird.md").write_text(
        "---\nname: weird\nfanout: martian\n---\n# weird\n",
        encoding="utf-8",
    )
    return tmp_repo


def _client(repo: Path, slug: str, *, pause: bool = False, dormant: bool = False) -> None:
    cd = repo / "clients" / slug
    cd.mkdir(parents=True, exist_ok=True)
    pause_line = "pause: true\n" if pause else ""
    (cd / "client.md").write_text(
        f"---\nslug: {slug}\nname: {slug}\nowner_slack_id: U0KAI\n{pause_line}---\n",
        encoding="utf-8",
    )
    (cd / "campaigns").mkdir(exist_ok=True)
    if not dormant:
        (cd / "campaigns" / "active.md").write_text("# active\n", encoding="utf-8")


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Capture every agent run dispatched by the routine layer."""
    captured: list[dict[str, Any]] = []

    class StubExecutor:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        @classmethod
        def from_settings(cls, settings: Any) -> StubExecutor:
            return cls()

        def run(
            self,
            name: str,
            inputs: dict[str, Any],
            *,
            client_slug: str | None = None,
            task: str | None = None,
            **kwargs: Any,
        ) -> Any:
            captured.append(
                {"name": name, "inputs": inputs, "client_slug": client_slug, "task": task}
            )

            class _R:
                error = None
                artifact_path = Path("/dev/null/run.md")

            return _R()

    monkeypatch.setattr("gtmos.routines.AgentExecutor", StubExecutor)
    return captured


class TestPerClientFanout:
    def test_runs_for_each_active_client(
        self, routines_repo: Path, calls: list[dict[str, Any]]
    ) -> None:
        _client(routines_repo, "acme")
        _client(routines_repo, "globex")
        from gtmos.config import Settings
        from gtmos.routines import run_routine

        rc = run_routine(Settings.load(), "per-client-weekly-review")
        assert rc == 0
        slugs = sorted(c["client_slug"] for c in calls)
        assert slugs == ["acme", "globex"]

    def test_skips_paused_client(
        self, routines_repo: Path, calls: list[dict[str, Any]]
    ) -> None:
        _client(routines_repo, "acme", pause=True)
        _client(routines_repo, "globex")
        from gtmos.config import Settings
        from gtmos.routines import run_routine

        rc = run_routine(Settings.load(), "per-client-weekly-review")
        assert rc == 0
        assert [c["client_slug"] for c in calls] == ["globex"]

    def test_skips_dormant_client(
        self, routines_repo: Path, calls: list[dict[str, Any]]
    ) -> None:
        _client(routines_repo, "acme", dormant=True)
        _client(routines_repo, "globex")
        from gtmos.config import Settings
        from gtmos.routines import run_routine

        rc = run_routine(Settings.load(), "per-client-weekly-review")
        assert rc == 0
        assert [c["client_slug"] for c in calls] == ["globex"]


class TestUtilityRoutines:
    def test_task_cron_runs(
        self, routines_repo: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from gtmos.config import Settings
        from gtmos.routines import run_routine

        rc = run_routine(Settings.load(), "task-cron")
        assert rc == 0
        out = capsys.readouterr().out
        assert "task-cron" in out

    def test_unknown_routine_returns_2(
        self, routines_repo: Path
    ) -> None:
        from gtmos.config import Settings
        from gtmos.routines import run_routine

        rc = run_routine(Settings.load(), "weird")
        assert rc == 2

    def test_missing_routine_raises(
        self, routines_repo: Path
    ) -> None:
        from gtmos.config import Settings
        from gtmos.routines import run_routine

        with pytest.raises(FileNotFoundError):
            run_routine(Settings.load(), "does-not-exist")


class TestPerOwnerFanout:
    def test_runs_for_each_unique_owner(
        self, routines_repo: Path, calls: list[dict[str, Any]]
    ) -> None:
        # Two clients, same owner → owner runs once; another client w/ different owner.
        _client(routines_repo, "acme")
        (routines_repo / "clients" / "acme" / "client.md").write_text(
            "---\nslug: acme\nname: acme\nowner_slack_id: U0KAI\n---\n",
            encoding="utf-8",
        )
        _client(routines_repo, "globex")
        (routines_repo / "clients" / "globex" / "client.md").write_text(
            "---\nslug: globex\nname: globex\nowner_slack_id: U0OPS\n---\n",
            encoding="utf-8",
        )
        (routines_repo / "routines" / "daily-digest.md").write_text(
            "---\nname: daily-digest\nfanout: per-owner\nagent: agents/weekly-review.md\n---\n",
            encoding="utf-8",
        )
        from gtmos.config import Settings
        from gtmos.routines import run_routine

        rc = run_routine(Settings.load(), "daily-digest")
        assert rc == 0
        owners = sorted(c["inputs"]["owner"] for c in calls)
        assert owners == ["U0KAI", "U0OPS"]


class TestPerClientMissingAgent:
    def test_missing_agent_returns_2(
        self, routines_repo: Path
    ) -> None:
        (routines_repo / "routines" / "broken.md").write_text(
            "---\nname: broken\nfanout: per-client\n---\n",
            encoding="utf-8",
        )
        from gtmos.config import Settings
        from gtmos.routines import run_routine

        rc = run_routine(Settings.load(), "broken")
        assert rc == 2
