"""End-to-end pipeline tests — agent + HubSpot + Slack all mocked."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
import yaml

# ---- shared fixtures -------------------------------------------------------


def _ready_pipeline_repo(repo: Path, agent_name: str) -> None:
    (repo / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
    (repo / "BRAND_GUIDELINES.md").write_text("# brand\n", encoding="utf-8")
    (repo / "agents").mkdir(exist_ok=True)
    (repo / "agents" / f"{agent_name}.md").write_text(
        f"# Agent — {agent_name}\n\n"
        "A stub agent for pipeline tests. Long enough to pass the "
        "minimum-content sanity check inside the executor.\n",
        encoding="utf-8",
    )
    (repo / "evals").mkdir(exist_ok=True)
    (repo / "evals" / f"{agent_name}.yaml").write_text(
        yaml.safe_dump(
            {
                "agent": agent_name,
                "judge": {"model": "claude-haiku-4-5", "prompt": "Grade strictly."},
                "pass_threshold": 8.0,
                "rubric": [{"id": "x", "weight": 1.0, "description": "x"}],
                "fixtures": [{"id": f"f{i}", "input": {}} for i in range(3)],
            }
        ),
        encoding="utf-8",
    )


def _client_md(repo: Path, slug: str = "acme", *, owner: str = "U0KAI",
               team: list[str] | None = None, pause: bool = False) -> None:
    cd = repo / "clients" / slug
    cd.mkdir(parents=True, exist_ok=True)
    pause_line = "pause: true\n" if pause else ""
    team_yaml = "[" + ", ".join(repr(t) for t in (team or [owner])) + "]"
    (cd / "client.md").write_text(
        f"---\nslug: {slug}\nname: {slug.title()}\nowner_slack_id: {owner}\nteam: {team_yaml}\n{pause_line}---\n",
        encoding="utf-8",
    )
    (cd / "campaigns").mkdir(exist_ok=True)
    (cd / "campaigns" / "active.md").write_text("# active\n", encoding="utf-8")
    (cd / "runs").mkdir(exist_ok=True)


@pytest.fixture
def pipeline_settings(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from gtmos.config import Settings

    _ready_pipeline_repo(tmp_repo, "weekly-review")
    _ready_pipeline_repo(tmp_repo, "inbound-triage")
    _client_md(tmp_repo, "acme")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("HUBSPOT_PRIVATE_APP_TOKEN", "pat-na1-" + "x" * 30)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xo" + "xb-test-bot-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "sig")
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")
    return Settings.load(require=("hubspot", "slack"))


class _StubAgentRun:
    def __init__(self, output_text: str, repo_root: Path) -> None:
        self.output_text = output_text
        self.error: str | None = None
        # Path doesn't need to exist on disk for tests that don't read it.
        self.artifact_path = repo_root / "runs" / "stub.md"


class _StubExecutor:
    def __init__(self, repo_root: Path, output_text: str) -> None:
        self.settings = type("S", (), {"repo_root": repo_root})()
        self._text = output_text
        self.calls: list[dict[str, Any]] = []

    def run(self, name: str, inputs: dict[str, Any], *,
            client_slug: str | None = None, task: str | None = None,
            **kwargs: Any) -> _StubAgentRun:
        self.calls.append({"name": name, "inputs": inputs,
                           "client_slug": client_slug, "task": task})
        return _StubAgentRun(self._text, self.settings.repo_root)


class _StubHubSpot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def engagement_counts(self, **kwargs: Any) -> dict[str, int]:
        self.calls.append(("engagement_counts", kwargs))
        return {"emails_sent": 412, "emails_received": 47, "meetings": 11, "notes": 3}

    def search_deals(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("search_deals", kwargs))
        return [
            {"id": "1", "name": "Acme renewal", "stage": "neg", "amount": 12500.0,
             "close_date": "", "owner_id": ""},
            {"id": "2", "name": "Globex pilot", "stage": "open", "amount": 5000.0,
             "close_date": "", "owner_id": ""},
        ]

    def search_contacts(self, *, email: str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("search_contacts", {"email": email, **kwargs}))
        return [{"id": "999", "email": email or "x@y.com", "firstname": "Priya",
                 "lastname": "N.", "company": "Northpoint", "lifecyclestage": "lead"}]

    def log_email_activity(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("log_email_activity", kwargs))
        return {"id": "log-1"}

    def create_note(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("create_note", kwargs))
        return {"id": "note-1"}

    def create_task(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("create_task", kwargs))
        return {"id": "task-1"}


class _StubSlack:
    def __init__(self) -> None:
        self.dms: list[dict[str, Any]] = []

    def dm_user(self, *, user_id: str, text: str, provenance: str | None = None) -> dict[str, Any]:
        self.dms.append({"user_id": user_id, "text": text, "provenance": provenance})
        return {"ok": True, "ts": "1700000000.000100"}


# ---- weekly-review ---------------------------------------------------------


class TestWeeklyReview:
    def test_runs_end_to_end(
        self, pipeline_settings, tmp_repo: Path
    ) -> None:  # type: ignore[no-untyped-def]
        from gtmos.pipelines import run_weekly_review

        ex = _StubExecutor(tmp_repo, "All caught up. 412 sent, 47 replies, 11 booked.")
        hs = _StubHubSpot()
        sl = _StubSlack()

        result = run_weekly_review(
            pipeline_settings,
            client_slug="acme",
            hubspot=hs,
            slack=sl,
            executor=ex,
        )
        assert result.succeeded
        assert result.metrics["engagement"]["emails_sent"] == 412
        assert result.metrics["deals_modified"] == 2
        assert result.metrics["pipeline_value"] == 17500.0
        assert len(sl.dms) == 1
        # DM goes to the owner, includes the verdict + provenance.
        assert sl.dms[0]["user_id"] == "U0KAI"
        assert "412 sent" in sl.dms[0]["text"]

    def test_skips_paused_client(
        self, pipeline_settings, tmp_repo: Path
    ) -> None:  # type: ignore[no-untyped-def]
        _client_md(tmp_repo, "acme", pause=True)
        from gtmos.pipelines import run_weekly_review

        ex = _StubExecutor(tmp_repo, "")
        hs = _StubHubSpot()
        sl = _StubSlack()
        result = run_weekly_review(
            pipeline_settings, client_slug="acme",
            hubspot=hs, slack=sl, executor=ex,
        )
        assert result.skipped
        assert sl.dms == []

    def test_continues_when_hubspot_fails(
        self, pipeline_settings, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:  # type: ignore[no-untyped-def]
        from gtmos.connectors import ConnectorError
        from gtmos.pipelines import run_weekly_review

        class _BrokenHS(_StubHubSpot):
            def engagement_counts(self, **kwargs: Any) -> dict[str, int]:
                raise ConnectorError("hubspot down")

            def search_deals(self, **kwargs: Any) -> list[dict[str, Any]]:
                raise ConnectorError("hubspot down")

        ex = _StubExecutor(tmp_repo, "Degraded: HubSpot unreachable.")
        sl = _StubSlack()
        result = run_weekly_review(
            pipeline_settings, client_slug="acme",
            hubspot=_BrokenHS(), slack=sl, executor=ex,
        )
        assert "hubspot" in " ".join(result.errors).lower()
        # We still DM the owner with the degraded verdict.
        assert len(sl.dms) == 1


# ---- inbound-triage --------------------------------------------------------


class TestInboundTriage:
    def _reply(self, body: str = "Send a calendar link.") -> Any:
        from gtmos.pipelines import InboundReply

        return InboundReply(
            client_slug="acme",
            sender_email="priya@northpoint.test",
            sender_name="Priya N.",
            subject="Re: vendor consolidation",
            body=body,
        )

    def test_respond_tier_routes_to_owner_dm_and_hubspot_log(
        self, pipeline_settings, tmp_repo: Path
    ) -> None:  # type: ignore[no-untyped-def]
        from gtmos.pipelines import run_inbound_triage

        agent_text = (
            '{"tier": "Respond", "confidence": 0.92, '
            '"evidence": "Send a calendar link", '
            '"suggested_next": "DM the owner with a draft Tue/Thu calendar slot"}'
        )
        ex = _StubExecutor(tmp_repo, agent_text)
        hs = _StubHubSpot()
        sl = _StubSlack()

        result = run_inbound_triage(
            pipeline_settings, self._reply(),
            hubspot=hs, slack=sl, executor=ex,
        )
        assert result.tier == "Respond"
        assert result.confidence == pytest.approx(0.92)
        assert result.contact_id == "999"
        # HubSpot got an email-activity log
        labels = [c[0] for c in hs.calls]
        assert "log_email_activity" in labels
        # Slack DM went to the owner
        assert len(sl.dms) == 1
        assert sl.dms[0]["user_id"] == "U0KAI"
        assert not result.escalated
        assert not result.errors

    def test_nurture_tier_creates_note_and_task(
        self, pipeline_settings, tmp_repo: Path
    ) -> None:  # type: ignore[no-untyped-def]
        from gtmos.pipelines import run_inbound_triage

        agent_text = (
            '{"tier": "Nurture", "confidence": 0.85, '
            '"evidence": "ping me then", "suggested_next": "30-day re-touch"}'
        )
        hs = _StubHubSpot()
        sl = _StubSlack()
        ex = _StubExecutor(tmp_repo, agent_text)

        result = run_inbound_triage(
            pipeline_settings, self._reply("ping me in October"),
            hubspot=hs, slack=sl, executor=ex,
        )
        assert result.tier == "Nurture"
        labels = [c[0] for c in hs.calls]
        assert "create_note" in labels
        assert "create_task" in labels
        assert sl.dms == []  # nurture is silent on Slack

    def test_skip_tier_writes_nothing(
        self, pipeline_settings, tmp_repo: Path
    ) -> None:  # type: ignore[no-untyped-def]
        from gtmos.pipelines import run_inbound_triage

        agent_text = '{"tier": "Skip", "confidence": 0.95, "evidence": "out of office"}'
        hs = _StubHubSpot()
        sl = _StubSlack()
        ex = _StubExecutor(tmp_repo, agent_text)

        result = run_inbound_triage(
            pipeline_settings, self._reply("Out of office until 2026-05-20."),
            hubspot=hs, slack=sl, executor=ex,
        )
        assert result.tier == "Skip"
        # search_contacts ran (always), but no log/note/task should fire.
        labels = [c[0] for c in hs.calls]
        assert "search_contacts" in labels
        assert "log_email_activity" not in labels
        assert "create_note" not in labels
        assert sl.dms == []

    def test_low_confidence_escalates(
        self, pipeline_settings, tmp_repo: Path
    ) -> None:  # type: ignore[no-untyped-def]
        from gtmos.pipelines import run_inbound_triage

        agent_text = '{"tier": "Respond", "confidence": 0.55, "evidence": "ambiguous"}'
        hs = _StubHubSpot()
        sl = _StubSlack()
        ex = _StubExecutor(tmp_repo, agent_text)

        result = run_inbound_triage(
            pipeline_settings, self._reply("vague reply"),
            hubspot=hs, slack=sl, executor=ex,
        )
        assert result.escalated is True
        assert len(sl.dms) == 1
        # No HubSpot writes when escalating below the gate.
        labels = [c[0] for c in hs.calls]
        assert "log_email_activity" not in labels
        assert "create_note" not in labels

    def test_invalid_email_rejected(self) -> None:
        from gtmos.pipelines import InboundReply

        with pytest.raises(ValueError, match="sender_email"):
            InboundReply(client_slug="acme", sender_email="not-email", body="x")

    def test_empty_body_rejected(self) -> None:
        from gtmos.pipelines import InboundReply

        with pytest.raises(ValueError, match="body"):
            InboundReply(client_slug="acme", sender_email="x@y.com", body="   ")

    def test_naive_received_at_rejected(self) -> None:
        from gtmos.pipelines import InboundReply

        with pytest.raises(ValueError, match="timezone"):
            InboundReply(
                client_slug="acme",
                sender_email="x@y.com",
                body="hi",
                received_at=dt.datetime(2026, 1, 1),
            )

    def test_classification_falls_back_to_regex(
        self, pipeline_settings, tmp_repo: Path
    ) -> None:  # type: ignore[no-untyped-def]
        from gtmos.pipelines import run_inbound_triage

        # No JSON; just prose with a tier word inside.
        agent_text = "I think this should be Skip. The sender is out of office."
        ex = _StubExecutor(tmp_repo, agent_text)
        hs = _StubHubSpot()
        sl = _StubSlack()

        result = run_inbound_triage(
            pipeline_settings, self._reply("OOO"),
            hubspot=hs, slack=sl, executor=ex,
        )
        # Regex fallback gives us the tier with confidence 0.5 → escalation.
        assert result.tier == "Skip"
        assert result.escalated is True
