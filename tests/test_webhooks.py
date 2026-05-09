"""Webhook receiver tests — signature verification + routing.

Uses FastAPI's TestClient to drive the HTTP layer end-to-end without
spinning up a real HTTP server. Pipelines are stubbed so we test the
auth/dispatch layer in isolation.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_app(tmp_repo, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xo" + "xb-test")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "slack-secret")
    monkeypatch.setenv("LEMLIST_WEBHOOK_SECRET", "lemlist-secret")
    monkeypatch.setenv("HUBSPOT_WEBHOOK_SECRET", "hubspot-secret")
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")

    # Import after env is set so the module-level `app = build_app()` picks
    # the right config.
    from gtmos.webhooks import build_app

    return TestClient(build_app())


# ---- Lemlist --------------------------------------------------------------


def _sign_lemlist(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class TestLemlistWebhook:
    def test_health(self, client_app: TestClient) -> None:
        r = client_app.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_no_secret_returns_503(
        self, client_app: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LEMLIST_WEBHOOK_SECRET", raising=False)
        r = client_app.post("/webhooks/lemlist", content=b"{}")
        assert r.status_code == 503

    def test_bad_signature_rejected(self, client_app: TestClient) -> None:
        body = b'{"type":"emailsReplied"}'
        r = client_app.post(
            "/webhooks/lemlist",
            content=body,
            headers={"X-Lemlist-Signature": "deadbeef"},
        )
        assert r.status_code == 401

    def test_valid_signature_accepted(
        self, client_app: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stub the dispatcher so we don't hit real pipelines.
        captured: dict[str, Any] = {}

        def fake_dispatch(settings, event):  # type: ignore[no-untyped-def]
            captured["event"] = event

        monkeypatch.setattr("gtmos.webhooks._dispatch_lemlist_event", fake_dispatch)

        body = json.dumps(
            {
                "type": "emailsReplied",
                "leadEmail": "priya@example.com",
                "campaignId": "seq_abc",
                "clientSlug": "acme",
                "subject": "Re: outreach",
                "body": "Send a calendar link.",
            }
        ).encode("utf-8")
        sig = _sign_lemlist("lemlist-secret", body)
        r = client_app.post(
            "/webhooks/lemlist",
            content=body,
            headers={"X-Lemlist-Signature": sig},
        )
        assert r.status_code == 200
        assert r.json() == {"accepted": True}
        # BackgroundTasks runs synchronously in TestClient.
        assert captured["event"]["leadEmail"] == "priya@example.com"

    def test_invalid_json_body_400(self, client_app: TestClient) -> None:
        body = b"not json"
        sig = _sign_lemlist("lemlist-secret", body)
        r = client_app.post(
            "/webhooks/lemlist",
            content=body,
            headers={"X-Lemlist-Signature": sig},
        )
        assert r.status_code == 400


# ---- Slack ----------------------------------------------------------------


def _sign_slack(secret: str, ts: str, body: bytes) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        b"v0:" + ts.encode("ascii") + b":" + body,
        hashlib.sha256,
    ).hexdigest()
    return "v0=" + digest


class TestSlackWebhook:
    def test_url_verification_handshake(self, client_app: TestClient) -> None:
        body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode("utf-8")
        ts = str(int(time.time()))
        sig = _sign_slack("slack-secret", ts, body)
        r = client_app.post(
            "/webhooks/slack",
            content=body,
            headers={
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
        assert r.status_code == 200
        assert r.json() == {"challenge": "abc123"}

    def test_bad_signature_rejected(self, client_app: TestClient) -> None:
        body = b'{"type":"event_callback"}'
        ts = str(int(time.time()))
        r = client_app.post(
            "/webhooks/slack",
            content=body,
            headers={
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": "v0=deadbeef",
            },
        )
        assert r.status_code == 401

    def test_event_dispatched(
        self, client_app: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_dispatch(settings, event):  # type: ignore[no-untyped-def]
            captured["event"] = event

        monkeypatch.setattr("gtmos.webhooks._dispatch_slack_event", fake_dispatch)

        body = json.dumps(
            {
                "type": "event_callback",
                "event": {"type": "reaction_added", "user": "U0KAI"},
            }
        ).encode("utf-8")
        ts = str(int(time.time()))
        sig = _sign_slack("slack-secret", ts, body)
        r = client_app.post(
            "/webhooks/slack",
            content=body,
            headers={
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
        assert r.status_code == 200
        assert captured["event"]["type"] == "event_callback"


# ---- HubSpot --------------------------------------------------------------


def _sign_hubspot(secret: str, method: str, url: str, body: bytes, ts: str) -> str:
    raw = (method + url + body.decode("utf-8") + ts).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


class TestHubSpotWebhook:
    def test_no_secret_503(
        self, client_app: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HUBSPOT_WEBHOOK_SECRET", raising=False)
        r = client_app.post("/webhooks/hubspot", content=b"{}")
        assert r.status_code == 503

    def test_non_numeric_timestamp_rejected(
        self, client_app: TestClient
    ) -> None:
        body = b'{"events":[]}'
        r = client_app.post(
            "/webhooks/hubspot",
            content=body,
            headers={
                "X-HubSpot-Signature-V3": "deadbeef",
                "X-HubSpot-Request-Timestamp": "not-numeric",
            },
        )
        assert r.status_code == 401

    def test_old_timestamp_rejected(self, client_app: TestClient) -> None:
        body = b'{"events":[]}'
        url = "http://testserver/webhooks/hubspot"
        old_ts = str(int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000) - 600_000)
        sig = _sign_hubspot("hubspot-secret", "POST", url, body, old_ts)
        r = client_app.post(
            "/webhooks/hubspot",
            content=body,
            headers={
                "X-HubSpot-Signature-V3": sig,
                "X-HubSpot-Request-Timestamp": old_ts,
            },
        )
        assert r.status_code == 401

    def test_valid_signature_accepted(
        self, client_app: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_dispatch(settings, event):  # type: ignore[no-untyped-def]
            captured["event"] = event

        monkeypatch.setattr("gtmos.webhooks._dispatch_hubspot_event", fake_dispatch)

        body = json.dumps({"events": [{"subscriptionType": "deal.propertyChange"}]}).encode("utf-8")
        url = "http://testserver/webhooks/hubspot"
        ts = str(int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000))
        sig = _sign_hubspot("hubspot-secret", "POST", url, body, ts)
        r = client_app.post(
            "/webhooks/hubspot",
            content=body,
            headers={
                "X-HubSpot-Signature-V3": sig,
                "X-HubSpot-Request-Timestamp": ts,
            },
        )
        assert r.status_code == 200
        assert "events" in captured["event"]
