"""HubSpot connector tests with httpx mocked via respx."""

from __future__ import annotations

import datetime as dt

import pytest
import respx
from httpx import Response

from gtmos.connectors import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimited,
    ConnectorUnavailable,
)
from gtmos.connectors.hubspot import API_BASE, HubSpotClient


@pytest.fixture
def client() -> HubSpotClient:
    return HubSpotClient(
        base_url=API_BASE,
        auth_headers={"Authorization": "Bearer test-token"},
        max_retries=1,  # keep test loops short
    )


# ---- search_contacts -------------------------------------------------------


class TestSearchContacts:
    @respx.mock
    def test_email_search_returns_normalized(self, client: HubSpotClient) -> None:
        respx.post(f"{API_BASE}/crm/v3/objects/contacts/search").respond(
            200,
            json={
                "results": [
                    {
                        "id": "12345",
                        "properties": {
                            "email": "priya@example.com",
                            "firstname": "Priya",
                            "lastname": "N.",
                            "company": "Northpoint",
                            "lifecyclestage": "lead",
                        },
                    }
                ],
                "total": 1,
            },
        )
        out = client.search_contacts(email="priya@example.com")
        assert out == [
            {
                "id": "12345",
                "email": "priya@example.com",
                "firstname": "Priya",
                "lastname": "N.",
                "company": "Northpoint",
                "lifecyclestage": "lead",
            }
        ]

    def test_must_supply_email_or_domain(self, client: HubSpotClient) -> None:
        with pytest.raises(ValueError, match="email or domain"):
            client.search_contacts()

    def test_limit_validated(self, client: HubSpotClient) -> None:
        with pytest.raises(ValueError, match="limit"):
            client.search_contacts(email="x@y.com", limit=0)
        with pytest.raises(ValueError, match="limit"):
            client.search_contacts(email="x@y.com", limit=200)


# ---- search_deals ----------------------------------------------------------


class TestSearchDeals:
    @respx.mock
    def test_deal_amount_parsed(self, client: HubSpotClient) -> None:
        respx.post(f"{API_BASE}/crm/v3/objects/deals/search").respond(
            200,
            json={
                "results": [
                    {
                        "id": "98",
                        "properties": {
                            "dealname": "Acme renewal",
                            "amount": "12500.00",
                            "dealstage": "negotiation",
                            "closedate": "2026-06-30",
                            "hubspot_owner_id": "ow1",
                        },
                    }
                ]
            },
        )
        out = client.search_deals(stage="negotiation")
        assert out[0]["amount"] == 12500.0
        assert out[0]["name"] == "Acme renewal"

    def test_requires_a_filter(self, client: HubSpotClient) -> None:
        with pytest.raises(ValueError, match="stage, owner_id"):
            client.search_deals()


# ---- log_email_activity ----------------------------------------------------


class TestLogEmail:
    @respx.mock
    def test_returns_engagement_id(self, client: HubSpotClient) -> None:
        respx.post(f"{API_BASE}/crm/v3/objects/emails").respond(
            201, json={"id": "777", "properties": {}}
        )
        out = client.log_email_activity(
            contact_id="12345",
            subject="Re: vendor consolidation",
            body="Send a calendar link.",
        )
        assert out["id"] == "777"

    def test_rejects_non_numeric_contact_id(self, client: HubSpotClient) -> None:
        with pytest.raises(ValueError, match="numeric"):
            client.log_email_activity(contact_id="abc", subject="x", body="y")

    def test_rejects_unknown_direction(self, client: HubSpotClient) -> None:
        with pytest.raises(ValueError, match="direction"):
            client.log_email_activity(
                contact_id="12345", subject="x", body="y", direction="OUTBOUND"
            )


# ---- create_task -----------------------------------------------------------


class TestCreateTask:
    @respx.mock
    def test_uses_due_date_in_payload(self, client: HubSpotClient) -> None:
        capture: dict[str, object] = {}
        def handler(request):  # type: ignore[no-untyped-def]
            import json
            capture["body"] = json.loads(request.content)
            return Response(201, json={"id": "55"})

        respx.post(f"{API_BASE}/crm/v3/objects/tasks").mock(side_effect=handler)
        out = client.create_task(
            contact_id="12345",
            title="Re-touch in 30 days",
            due_at=dt.datetime(2026, 6, 1, tzinfo=dt.UTC),
        )
        assert out["id"] == "55"
        body = capture["body"]
        assert isinstance(body, dict)
        props = body.get("properties") or {}
        assert props.get("hs_task_subject") == "Re-touch in 30 days"
        assert props.get("hs_task_status") == "NOT_STARTED"

    def test_naive_datetime_rejected(self, client: HubSpotClient) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            client.create_task(
                contact_id="12345",
                title="x",
                due_at=dt.datetime(2026, 6, 1),
            )


# ---- error classification --------------------------------------------------


class TestErrorClassification:
    @respx.mock
    def test_401_becomes_auth_error(self, client: HubSpotClient) -> None:
        respx.post(f"{API_BASE}/crm/v3/objects/contacts/search").respond(401, json={"error": "bad"})
        with pytest.raises(ConnectorAuthError):
            client.search_contacts(email="x@y.com")

    @respx.mock
    def test_429_becomes_rate_limit(self, client: HubSpotClient) -> None:
        respx.post(f"{API_BASE}/crm/v3/objects/contacts/search").respond(429)
        with pytest.raises(ConnectorRateLimited):
            client.search_contacts(email="x@y.com")

    @respx.mock
    def test_5xx_retries_then_fails(self, client: HubSpotClient) -> None:
        respx.post(f"{API_BASE}/crm/v3/objects/contacts/search").respond(503)
        with pytest.raises(ConnectorError):
            client.search_contacts(email="x@y.com")

    @respx.mock
    def test_invalid_json_response_raises(self, client: HubSpotClient) -> None:
        respx.post(f"{API_BASE}/crm/v3/objects/contacts/search").respond(
            200, content=b"not json", headers={"content-type": "application/json"}
        )
        with pytest.raises(ConnectorError, match="invalid JSON"):
            client.search_contacts(email="x@y.com")


# ---- factory ---------------------------------------------------------------


class TestFromSettings:
    def test_unavailable_when_token_missing(self) -> None:
        class S:
            hubspot_token = None
        with pytest.raises(ConnectorUnavailable):
            HubSpotClient.from_settings(S())

    def test_constructs_with_token(self) -> None:
        class S:
            hubspot_token = "pat-na1-" + "x" * 30
        c = HubSpotClient.from_settings(S())
        assert c.auth_headers["Authorization"].startswith("Bearer ")
