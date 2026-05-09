"""HubSpot connector — real CRM read/write against the v3 API.

Capability: ``hubspot``. Token is a HubSpot private-app token
(``HUBSPOT_PRIVATE_APP_TOKEN``).

Implemented endpoints (sufficient for the weekly-review + inbound-triage
pipelines this OS ships with):

  * search_contacts(query) — find a contact by email or domain
  * search_deals(stage, owner, since) — list pipeline movement
  * recent_activities(since) — engagement history (emails, calls, notes)
  * log_email_activity(contact_id, subject, body, direction)
  * create_note(contact_id, body)
  * create_task(contact_id, title, due_at, owner_id)

Anything else is intentionally absent — extend per engagement.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from gtmos.connectors.base import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorUnavailable,
    HttpConnector,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.hubapi.com"


class HubSpotClient(HttpConnector):
    """HubSpot Private App authenticated client."""

    @classmethod
    def from_settings(cls, settings: object) -> HubSpotClient:
        token = getattr(settings, "hubspot_token", None)
        if not token:
            raise ConnectorUnavailable(
                "HUBSPOT_PRIVATE_APP_TOKEN is unset; "
                "load Settings with require=('hubspot',) to gate startup."
            )
        return cls(
            base_url=API_BASE,
            auth_headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    # ---- contacts -----------------------------------------------------------

    def search_contacts(
        self,
        *,
        email: str | None = None,
        domain: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if not (email or domain):
            raise ValueError("search_contacts requires email or domain")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be in [1, 100]")

        filters: list[dict[str, Any]] = []
        if email:
            filters.append({"propertyName": "email", "operator": "EQ", "value": email})
        if domain:
            filters.append(
                {"propertyName": "hs_email_domain", "operator": "EQ", "value": domain}
            )

        body = {
            "filterGroups": [{"filters": filters}],
            "properties": ["email", "firstname", "lastname", "company", "lifecyclestage"],
            "limit": limit,
        }
        resp = self.request("POST", "/crm/v3/objects/contacts/search", json=body)
        if not isinstance(resp, dict):
            raise ConnectorError("contacts.search returned non-object body")
        results = resp.get("results") or []
        return [_pick_contact(r) for r in results]

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        if not contact_id or not contact_id.isdigit():
            raise ValueError("contact_id must be a numeric HubSpot id")
        resp = self.request(
            "GET",
            f"/crm/v3/objects/contacts/{contact_id}",
            params={"properties": "email,firstname,lastname,company,lifecyclestage"},
        )
        if not isinstance(resp, dict):
            raise ConnectorError("contacts.get returned non-object body")
        return _pick_contact(resp)

    # ---- deals --------------------------------------------------------------

    def search_deals(
        self,
        *,
        stage: str | None = None,
        owner_id: str | None = None,
        since: dt.datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []
        if stage:
            filters.append({"propertyName": "dealstage", "operator": "EQ", "value": stage})
        if owner_id:
            filters.append({"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id})
        if since:
            filters.append({
                "propertyName": "hs_lastmodifieddate",
                "operator": "GTE",
                "value": int(since.astimezone(dt.UTC).timestamp() * 1000),
            })
        if not filters:
            # No-filter searches are accepted but expensive; require at least one.
            raise ValueError("search_deals requires stage, owner_id, or since")

        body = {
            "filterGroups": [{"filters": filters}],
            "properties": ["dealname", "amount", "dealstage", "closedate", "hubspot_owner_id"],
            "limit": min(limit, 100),
            "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "DESCENDING"}],
        }
        resp = self.request("POST", "/crm/v3/objects/deals/search", json=body)
        if not isinstance(resp, dict):
            raise ConnectorError("deals.search returned non-object body")
        return [_pick_deal(r) for r in (resp.get("results") or [])]

    # ---- engagements (notes / tasks / emails) -------------------------------

    def log_email_activity(
        self,
        *,
        contact_id: str,
        subject: str,
        body: str,
        direction: str = "INCOMING_EMAIL",
        timestamp: dt.datetime | None = None,
    ) -> dict[str, Any]:
        if direction not in {"INCOMING_EMAIL", "EMAIL"}:
            raise ValueError("direction must be INCOMING_EMAIL or EMAIL")
        if not contact_id.isdigit():
            raise ValueError("contact_id must be numeric")
        ts = int((timestamp or dt.datetime.now(tz=dt.UTC)).astimezone(dt.UTC).timestamp() * 1000)

        payload = {
            "properties": {
                "hs_timestamp": ts,
                "hs_email_subject": subject[:500],
                "hs_email_text": body[:65000],
                "hs_email_direction": direction,
            },
            "associations": [
                {
                    "to": {"id": contact_id},
                    "types": [
                        {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 198},
                    ],
                }
            ],
        }
        resp = self.request("POST", "/crm/v3/objects/emails", json=payload)
        if not isinstance(resp, dict):
            raise ConnectorError("emails.create returned non-object body")
        return resp

    def create_note(self, *, contact_id: str, body: str) -> dict[str, Any]:
        if not contact_id.isdigit():
            raise ValueError("contact_id must be numeric")
        ts = int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)
        payload = {
            "properties": {"hs_timestamp": ts, "hs_note_body": body[:65000]},
            "associations": [
                {
                    "to": {"id": contact_id},
                    "types": [
                        {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202},
                    ],
                }
            ],
        }
        resp = self.request("POST", "/crm/v3/objects/notes", json=payload)
        if not isinstance(resp, dict):
            raise ConnectorError("notes.create returned non-object body")
        return resp

    def create_task(
        self,
        *,
        contact_id: str,
        title: str,
        due_at: dt.datetime,
        owner_id: str | None = None,
        body: str = "",
    ) -> dict[str, Any]:
        if not contact_id.isdigit():
            raise ValueError("contact_id must be numeric")
        if due_at.tzinfo is None:
            raise ValueError("due_at must be timezone-aware")
        ts_now = int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)
        ts_due = int(due_at.astimezone(dt.UTC).timestamp() * 1000)

        properties = {
            "hs_timestamp": ts_now,
            "hs_task_subject": title[:255],
            "hs_task_body": body[:65000],
            "hs_task_status": "NOT_STARTED",
            "hs_task_priority": "MEDIUM",
            "hs_task_type": "TODO",
            "hs_task_due_date": ts_due,
        }
        if owner_id:
            properties["hubspot_owner_id"] = owner_id

        payload = {
            "properties": properties,
            "associations": [
                {
                    "to": {"id": contact_id},
                    "types": [
                        {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204},
                    ],
                }
            ],
        }
        resp = self.request("POST", "/crm/v3/objects/tasks", json=payload)
        if not isinstance(resp, dict):
            raise ConnectorError("tasks.create returned non-object body")
        return resp

    # ---- engagement metrics for weekly review -------------------------------

    def engagement_counts(
        self,
        *,
        owner_id: str | None = None,
        since: dt.datetime,
    ) -> dict[str, int]:
        """Return counts of {emails_sent, emails_received, meetings, notes} since timestamp.

        Cheap aggregate used by weekly-review. Each search is one POST.
        """
        out: dict[str, int] = {}
        for label, object_type, prop in (
            ("emails_sent", "emails", "hs_email_direction"),
            ("emails_received", "emails", "hs_email_direction"),
            ("meetings", "meetings", None),
            ("notes", "notes", None),
        ):
            filters: list[dict[str, Any]] = [
                {
                    "propertyName": "hs_lastmodifieddate",
                    "operator": "GTE",
                    "value": int(since.astimezone(dt.UTC).timestamp() * 1000),
                }
            ]
            if owner_id:
                filters.append(
                    {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id}
                )
            if prop and label == "emails_sent":
                filters.append({"propertyName": prop, "operator": "EQ", "value": "EMAIL"})
            if prop and label == "emails_received":
                filters.append(
                    {"propertyName": prop, "operator": "EQ", "value": "INCOMING_EMAIL"}
                )

            body = {"filterGroups": [{"filters": filters}], "limit": 1, "properties": []}
            resp = self.request("POST", f"/crm/v3/objects/{object_type}/search", json=body)
            if isinstance(resp, dict):
                out[label] = int(resp.get("total") or 0)
            else:
                out[label] = 0
        return out


# ---- response shapers -------------------------------------------------------


def _pick_contact(raw: dict[str, Any]) -> dict[str, Any]:
    props = raw.get("properties") or {}
    return {
        "id": str(raw.get("id", "")),
        "email": props.get("email") or "",
        "firstname": props.get("firstname") or "",
        "lastname": props.get("lastname") or "",
        "company": props.get("company") or "",
        "lifecyclestage": props.get("lifecyclestage") or "",
    }


def _pick_deal(raw: dict[str, Any]) -> dict[str, Any]:
    props = raw.get("properties") or {}
    amount_raw = props.get("amount")
    try:
        amount = float(amount_raw) if amount_raw not in (None, "") else 0.0
    except (TypeError, ValueError):
        amount = 0.0
    return {
        "id": str(raw.get("id", "")),
        "name": props.get("dealname") or "",
        "stage": props.get("dealstage") or "",
        "amount": amount,
        "close_date": props.get("closedate") or "",
        "owner_id": props.get("hubspot_owner_id") or "",
    }


__all__ = ["ConnectorAuthError", "ConnectorError", "ConnectorUnavailable", "HubSpotClient"]
