"""Webhook dispatcher tests — drive `_dispatch_*` directly with stubbed pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def settings(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from gtmos.config import Settings

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")
    return Settings.load()


def test_lemlist_dispatch_calls_inbound_triage(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gtmos.webhooks import _dispatch_lemlist_event

    captured: dict[str, Any] = {}

    def fake_run(s, reply, **kwargs):  # type: ignore[no-untyped-def]
        captured["reply"] = reply

    monkeypatch.setattr("gtmos.pipelines.run_inbound_triage", fake_run)

    _dispatch_lemlist_event(
        settings,
        {
            "type": "emailsReplied",
            "leadEmail": "priya@example.com",
            "leadFirstName": "Priya",
            "leadLastName": "N.",
            "campaignId": "seq_abc",
            "clientSlug": "acme",
            "subject": "Re: outreach",
            "body": "Send a calendar link.",
            "activityId": "act-1",
        },
    )
    assert captured["reply"].sender_email == "priya@example.com"
    assert captured["reply"].client_slug == "acme"


def test_lemlist_dispatch_skips_when_client_unknown(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gtmos.webhooks import _dispatch_lemlist_event

    called = {"count": 0}

    def fake_run(s, reply, **kwargs):  # type: ignore[no-untyped-def]
        called["count"] += 1

    monkeypatch.setattr("gtmos.pipelines.run_inbound_triage", fake_run)

    _dispatch_lemlist_event(
        settings,
        {
            "type": "emailsReplied",
            "leadEmail": "x@y.com",
            "campaignId": "seq_x",
            "subject": "Hi",
            "body": "Hello",
        },
    )
    assert called["count"] == 0  # no clientSlug → skipped


def test_lemlist_dispatch_bounce_logs(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gtmos.webhooks import _dispatch_lemlist_event

    # Just exercises the branch — no real-world side effect.
    _dispatch_lemlist_event(
        settings,
        {"type": "emailsBounced", "leadEmail": "x@y.com", "campaignId": "seq_x"},
    )


def test_slack_dispatch_smoke(settings) -> None:  # type: ignore[no-untyped-def]
    from gtmos.webhooks import _dispatch_slack_event

    # Stub handler — currently logs and returns. Smoke run for coverage.
    _dispatch_slack_event(
        settings,
        {"type": "event_callback", "event": {"type": "reaction_added"}},
    )


def test_hubspot_dispatch_iterates_events(settings) -> None:  # type: ignore[no-untyped-def]
    from gtmos.webhooks import _dispatch_hubspot_event

    _dispatch_hubspot_event(
        settings,
        {
            "events": [
                {"subscriptionType": "deal.propertyChange"},
                {"subscriptionType": "contact.creation"},
                "not-a-dict",  # ignored
            ]
        },
    )
