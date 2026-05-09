"""Configuration / env-loading tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gtmos.config import ConfigError, Settings


@pytest.fixture
def fake_repo(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-1234567890abcdef")
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")  # quiet pytest output
    monkeypatch.delenv("GTMOS_AGENT_MODEL", raising=False)
    monkeypatch.delenv("GTMOS_JUDGE_MODEL", raising=False)
    return tmp_repo


class TestSettingsLoad:
    def test_minimal_load(self, fake_repo: Path) -> None:
        s = Settings.load()
        assert s.repo_root == fake_repo
        assert s.anthropic_api_key.startswith("test-key")
        assert s.task_store == "sqlite"
        assert s.tasks_db_path == (fake_repo / "runs" / ".state" / "tasks.db").resolve()
        assert s.agent_timeout_s == 300
        assert s.slack_sig_replay_window_s == 300
        assert s.log_level == "WARNING"

    def test_missing_anthropic_key_raises(
        self, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
            Settings.load()

    def test_invalid_repo_root_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
        monkeypatch.setenv("GTMOS_REPO_ROOT", "/nope/this/does/not/exist")
        with pytest.raises(ConfigError, match="does not exist"):
            Settings.load()

    def test_slack_capability_required(
        self, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ANTHROPIC_API_KEY is set; slack creds are not.
        with pytest.raises(ConfigError, match="SLACK_"):
            Settings.load(require=("slack",))

    def test_slack_capability_passes_when_set(
        self, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xo" + "xb-test-bot-token")
        monkeypatch.setenv("SLACK_SIGNING_SECRET", "sig-secret")
        s = Settings.load(require=("slack",))
        assert s.slack_bot_token is not None
        assert s.slack_signing_secret == "sig-secret"

    def test_invalid_log_level_raises(
        self, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GTMOS_LOG_LEVEL", "TRACE")
        with pytest.raises(ConfigError, match="GTMOS_LOG_LEVEL"):
            Settings.load()

    def test_invalid_replay_window_raises(
        self, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SLACK_SIG_REPLAY_WINDOW_S", "9999")
        with pytest.raises(ConfigError, match="SLACK_SIG_REPLAY_WINDOW_S"):
            Settings.load()

    def test_invalid_task_store_raises(
        self, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GTMOS_TASK_STORE", "redis")
        with pytest.raises(ConfigError, match="GTMOS_TASK_STORE"):
            Settings.load()

    def test_notion_task_store_requires_creds(
        self, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GTMOS_TASK_STORE", "notion")
        with pytest.raises(ConfigError, match="NOTION_"):
            Settings.load()

    def test_settings_is_frozen(self, fake_repo: Path) -> None:
        s = Settings.load()
        with pytest.raises((AttributeError, TypeError)):
            s.anthropic_api_key = "leaked"  # type: ignore[misc]

    def test_resolves_repo_root_via_claude_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No env GTMOS_REPO_ROOT — config should walk up looking for CLAUDE.md
        outer = tmp_path
        (outer / "CLAUDE.md").write_text("# test\n")
        inner = outer / "deeply" / "nested"
        inner.mkdir(parents=True)
        monkeypatch.chdir(inner)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
        s = Settings.load()
        assert s.repo_root == outer.resolve()
