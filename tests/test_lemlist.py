"""Lemlist real-client tests with httpx mocked via respx."""

from __future__ import annotations

import datetime as dt

import pytest
import respx
from httpx import Response

from gtmos.connectors import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorUnavailable,
)
from gtmos.connectors.lemlist import API_BASE, LemlistClient


@pytest.fixture
def client() -> LemlistClient:
    return LemlistClient(
        base_url=API_BASE,
        auth_headers={"Authorization": "Basic test"},
        max_retries=1,
    )


class TestFromSettings:
    def test_unavailable_when_missing(self) -> None:
        class S:
            lemlist_api_key = None
        with pytest.raises(ConnectorUnavailable):
            LemlistClient.from_settings(S())

    def test_constructs_with_key(self) -> None:
        class S:
            lemlist_api_key = "lem-key-12345"
        c = LemlistClient.from_settings(S())
        assert c.auth_headers["Authorization"].startswith("Basic ")


class TestPushToCampaign:
    @respx.mock
    def test_push_success(self, client: LemlistClient) -> None:
        respx.post(f"{API_BASE}/api/campaigns/seq_abc123/leads/x@y.com").respond(
            201, json={"_id": "L1", "email": "x@y.com"}
        )
        out = client.push_to_campaign(
            campaign_id="seq_abc123",
            email="x@y.com",
            first_name="Priya",
            last_name="N.",
            company_name="Northpoint",
        )
        assert out.get("_id") == "L1"

    def test_invalid_email(self, client: LemlistClient) -> None:
        with pytest.raises(ValueError, match="email"):
            client.push_to_campaign(campaign_id="seq_abc123", email="not-email")

    def test_invalid_campaign_id(self, client: LemlistClient) -> None:
        with pytest.raises(ValueError, match="campaign_id"):
            client.push_to_campaign(campaign_id="!!!", email="x@y.com")


class TestPauseResumeStop:
    @respx.mock
    def test_pause(self, client: LemlistClient) -> None:
        respx.post(f"{API_BASE}/api/campaigns/seq_abc123/leads/x@y.com/pause").respond(200, json={})
        out = client.pause_in_campaign(campaign_id="seq_abc123", email="x@y.com")
        assert isinstance(out, dict)

    @respx.mock
    def test_resume(self, client: LemlistClient) -> None:
        respx.post(f"{API_BASE}/api/campaigns/seq_abc123/leads/x@y.com/resume").respond(200, json={})
        out = client.resume_in_campaign(campaign_id="seq_abc123", email="x@y.com")
        assert isinstance(out, dict)

    @respx.mock
    def test_stop(self, client: LemlistClient) -> None:
        respx.delete(f"{API_BASE}/api/campaigns/seq_abc123/leads/x@y.com").respond(200, json={"removed": True})
        out = client.stop_in_campaign(campaign_id="seq_abc123", email="x@y.com")
        assert out.get("removed") is True


class TestListReplies:
    @respx.mock
    def test_returns_empty_list(self, client: LemlistClient) -> None:
        respx.get(f"{API_BASE}/api/activities").respond(200, json=[])
        assert client.list_replies(campaign_id="seq_abc123") == []

    @respx.mock
    def test_returns_dict_items(self, client: LemlistClient) -> None:
        respx.get(f"{API_BASE}/api/activities").respond(
            200,
            json=[
                {"_id": "act1", "type": "emailsReplied", "leadEmail": "a@b.com"},
                {"_id": "act2", "type": "emailsReplied", "leadEmail": "c@d.com"},
            ],
        )
        out = client.list_replies(
            campaign_id="seq_abc123",
            since=dt.datetime(2026, 5, 1, tzinfo=dt.UTC),
        )
        assert [r["leadEmail"] for r in out] == ["a@b.com", "c@d.com"]


class TestSenderHealth:
    @respx.mock
    def test_aggregates_stats(self, client: LemlistClient) -> None:
        respx.get(f"{API_BASE}/api/campaigns/seq_abc123").respond(
            200,
            json={
                "_id": "seq_abc123",
                "stats": {
                    "emailsSent": 412,
                    "emailsDelivered": 401,
                    "emailsOpened": 198,
                    "emailsReplied": 47,
                    "emailsBounced": 11,
                    "emailsUnsubscribed": 2,
                },
            },
        )
        out = client.sender_health(campaign_id="seq_abc123")
        assert out["sent"] == 412
        assert out["bounced"] == 11
        assert out["unsubscribed"] == 2

    @respx.mock
    def test_handles_empty_stats(self, client: LemlistClient) -> None:
        respx.get(f"{API_BASE}/api/campaigns/seq_abc123").respond(200, json={"_id": "x"})
        out = client.sender_health(campaign_id="seq_abc123")
        assert out["sent"] == 0


class TestErrorPaths:
    @respx.mock
    def test_401_becomes_auth_error(self, client: LemlistClient) -> None:
        respx.get(f"{API_BASE}/api/campaigns/seq_abc123").respond(401, json={"err": "bad"})
        with pytest.raises(ConnectorAuthError):
            client.sender_health(campaign_id="seq_abc123")

    @respx.mock
    def test_5xx_eventually_raises(self, client: LemlistClient) -> None:
        respx.get(f"{API_BASE}/api/campaigns/seq_abc123").respond(503)
        with pytest.raises(ConnectorError):
            client.sender_health(campaign_id="seq_abc123")


class TestListBounces:
    @respx.mock
    def test_bounces_returned(self, client: LemlistClient) -> None:
        respx.get(f"{API_BASE}/api/activities").respond(
            200,
            json={
                "items": [
                    {"_id": "b1", "type": "emailsBounced", "leadEmail": "x@y.com"}
                ]
            },
        )
        out = client.list_bounces(campaign_id="seq_abc123")
        assert len(out) == 1
        assert out[0]["leadEmail"] == "x@y.com"

    def test_bounces_invalid_campaign(self, client: LemlistClient) -> None:
        with pytest.raises(ValueError, match="campaign_id"):
            client.list_bounces(campaign_id="!!")

    def test_bounces_invalid_limit(self, client: LemlistClient) -> None:
        with pytest.raises(ValueError, match="limit"):
            client.list_bounces(campaign_id="seq_abc123", limit=0)


class TestPushMergeFields:
    @respx.mock
    def test_merge_fields_passthrough(self, client: LemlistClient) -> None:
        # Capture the body to verify merge_fields land in the payload.
        captured: dict[str, object] = {}

        def handler(request):  # type: ignore[no-untyped-def]
            import json as _json
            captured["body"] = _json.loads(request.content)
            return Response(201, json={"_id": "L2"})

        respx.post(f"{API_BASE}/api/campaigns/seq_abc123/leads/x@y.com").mock(
            side_effect=handler
        )
        client.push_to_campaign(
            campaign_id="seq_abc123",
            email="x@y.com",
            merge_fields={"role": "VP RevOps", "trigger_date": "2026-05-09"},
        )
        body = captured.get("body")
        assert isinstance(body, dict)
        assert body.get("role") == "VP RevOps"
        assert body.get("trigger_date") == "2026-05-09"

    @respx.mock
    def test_invalid_merge_field_keys_dropped(self, client: LemlistClient) -> None:
        captured: dict[str, object] = {}

        def handler(request):  # type: ignore[no-untyped-def]
            import json as _json
            captured["body"] = _json.loads(request.content)
            return Response(201, json={"_id": "L3"})

        respx.post(f"{API_BASE}/api/campaigns/seq_abc123/leads/x@y.com").mock(
            side_effect=handler
        )
        client.push_to_campaign(
            campaign_id="seq_abc123",
            email="x@y.com",
            merge_fields={"bad-key!": "ignored", "ok_key": "kept"},
        )
        body = captured["body"]
        assert isinstance(body, dict)
        assert "bad-key!" not in body
        assert body.get("ok_key") == "kept"
