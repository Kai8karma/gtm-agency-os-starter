"""Slack handler integration tests — focus on routing + auth, mock the LLM."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def slack_settings(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from gtmos.config import Settings

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xo" + "xb-test")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test-secret")
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")
    return Settings.load(require=("slack",))


def _client_md(repo: Path, slug: str, owner: str = "U0KAI", team: list[str] | None = None) -> None:
    cd = repo / "clients" / slug
    cd.mkdir(parents=True, exist_ok=True)
    team_yaml = "[" + ", ".join(repr(t) for t in (team or [owner])) + "]"
    (cd / "client.md").write_text(
        f"---\nslug: {slug}\nname: Acme\nowner_slack_id: {owner}\nteam: {team_yaml}\n---\n",
        encoding="utf-8",
    )


def _agent_md(repo: Path, name: str) -> None:
    (repo / "agents").mkdir(exist_ok=True)
    (repo / "agents" / f"{name}.md").write_text(
        "# Agent — " + name + "\n\nThis is a stub agent for tests.\n",
        encoding="utf-8",
    )


def test_build_app_requires_slack_creds(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gtmos.config import Settings
    from gtmos.slack_app import build_app

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    s = Settings.load()  # no slack creds
    with pytest.raises(RuntimeError, match="SLACK_"):
        build_app(s)


def test_help_subcommand(slack_settings) -> None:  # type: ignore[no-untyped-def]
    from gtmos.slack_app import _route

    captured: list[str] = []
    def respond(msg: str) -> None:
        captured.append(msg)

    _route(
        slack_settings,
        executor=None,  # type: ignore[arg-type]
        command={"text": "help", "user_id": "U0KAI", "team_id": "T0X"},
        respond=respond,
        client=None,  # type: ignore[arg-type]
    )
    assert any("`/ops`" in m for m in captured)


def test_unknown_subcommand_rejected(slack_settings) -> None:  # type: ignore[no-untyped-def]
    from gtmos.slack_app import _route

    captured: list[str] = []
    _route(
        slack_settings,
        executor=None,  # type: ignore[arg-type]
        command={"text": "blowup the world", "user_id": "U0KAI", "team_id": "T0X"},
        respond=captured.append,
        client=None,  # type: ignore[arg-type]
    )
    assert any("unknown subcommand" in m for m in captured)


def test_per_client_command_requires_slug(slack_settings) -> None:  # type: ignore[no-untyped-def]
    from gtmos.slack_app import _route

    captured: list[str] = []
    _route(
        slack_settings,
        executor=None,  # type: ignore[arg-type]
        command={"text": "review", "user_id": "U0KAI", "team_id": "T0X"},
        respond=captured.append,
        client=None,  # type: ignore[arg-type]
    )
    assert any("requires a client slug" in m for m in captured)


def test_invalid_slug_rejected(slack_settings) -> None:  # type: ignore[no-untyped-def]
    from gtmos.slack_app import _route

    captured: list[str] = []
    _route(
        slack_settings,
        executor=None,  # type: ignore[arg-type]
        command={
            "text": "review ../../etc/passwd",
            "user_id": "U0KAI",
            "team_id": "T0X",
        },
        respond=captured.append,
        client=None,  # type: ignore[arg-type]
    )
    assert any("invalid client slug" in m for m in captured)


def test_unauthorized_user_rejected(slack_settings) -> None:  # type: ignore[no-untyped-def]
    from gtmos.slack_app import _route

    repo = slack_settings.repo_root
    _client_md(repo, "acme", owner="U0KAI", team=["U0KAI"])
    _agent_md(repo, "weekly-review")

    captured: list[str] = []
    _route(
        slack_settings,
        executor=None,  # type: ignore[arg-type]
        command={"text": "review acme", "user_id": "U0EVIL", "team_id": "T0X"},
        respond=captured.append,
        client=None,  # type: ignore[arg-type]
    )
    assert any("not in clients/acme" in m for m in captured)


def test_workspace_team_id_enforced(slack_settings, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from gtmos.config import Settings
    from gtmos.slack_app import _route

    monkeypatch.setenv("SLACK_TEAM_ID", "T0EXPECTED")
    s = Settings.load(require=("slack",))

    captured: list[str] = []
    _route(
        s,
        executor=None,  # type: ignore[arg-type]
        command={"text": "help", "user_id": "U0KAI", "team_id": "T0WRONG"},
        respond=captured.append,
        client=None,  # type: ignore[arg-type]
    )
    assert any("not authorized" in m for m in captured)


def test_status_subcommand(slack_settings) -> None:  # type: ignore[no-untyped-def]
    from gtmos.slack_app import _route

    captured: list[str] = []
    _route(
        slack_settings,
        executor=None,  # type: ignore[arg-type]
        command={"text": "status", "user_id": "U0KAI", "team_id": "T0X"},
        respond=captured.append,
        client=None,  # type: ignore[arg-type]
    )
    assert any("status" in m.lower() and "model" in m for m in captured)


def test_unknown_client_rejected(slack_settings) -> None:  # type: ignore[no-untyped-def]
    from gtmos.slack_app import _route

    captured: list[str] = []
    _route(
        slack_settings,
        executor=None,  # type: ignore[arg-type]
        command={"text": "review nonexistent", "user_id": "U0KAI", "team_id": "T0X"},
        respond=captured.append,
        client=None,  # type: ignore[arg-type]
    )
    assert any("not found" in m for m in captured)


@pytest.mark.integration
def test_build_app_succeeds_with_creds(slack_settings) -> None:  # type: ignore[no-untyped-def]
    """Constructing the Slack App calls Slack's auth.test endpoint.

    Marked integration so CI without a real bot token skips it. The route-
    handler tests above cover the logic without requiring a live token.
    """
    from gtmos.slack_app import build_app

    app = build_app(slack_settings)
    assert app is not None
