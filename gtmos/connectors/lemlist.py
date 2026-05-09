"""Lemlist connector — real v1 / v2 API client.

Capability: ``lemlist``. API key from ``LEMLIST_API_KEY`` env var.

Implemented endpoints (sufficient for the inbound + outbound pipelines):

  * push_to_campaign(campaign_id, prospect)
  * pause_in_campaign(campaign_id, email)
  * resume_in_campaign(campaign_id, email)
  * stop_in_campaign(campaign_id, email)
  * list_replies(campaign_id, since)
  * list_bounces(campaign_id, since)
  * sender_health(campaign_id) — for deliverability monitoring (Sprint 5)

Auth: Lemlist uses Basic auth with the API key as the password and an empty
username (``Authorization: Basic base64(":<key>")``). All v1 endpoints live
under ``api.lemlist.com/api/`` and v2 (newer) under ``api.lemlist.com/v2/``.

The client never auto-stops a campaign without an explicit caller request
(PUBL-01 — humans pull triggers on customer-facing actions).
"""

from __future__ import annotations

import base64
import datetime as dt
import logging
import re
from typing import Any

from gtmos.connectors.base import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorUnavailable,
    HttpConnector,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.lemlist.com"


class LemlistClient(HttpConnector):
    """Lemlist API client, real."""

    @classmethod
    def from_settings(cls, settings: object) -> LemlistClient:
        token = getattr(settings, "lemlist_api_key", None)
        if not token:
            raise ConnectorUnavailable(
                "LEMLIST_API_KEY unset; load Settings with require=('lemlist',)"
            )
        # Basic auth with empty username + key as password.
        encoded = base64.b64encode(f":{token}".encode("ascii")).decode("ascii")
        return cls(
            base_url=API_BASE,
            auth_headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/json",
            },
            timeout_s=30.0,
        )

    # ---- prospect lifecycle -------------------------------------------------

    def push_to_campaign(
        self,
        *,
        campaign_id: str,
        email: str,
        first_name: str = "",
        last_name: str = "",
        company_name: str = "",
        merge_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not _is_id(campaign_id):
            raise ValueError(f"campaign_id must be alphanumeric (got {campaign_id!r})")
        if not _is_email(email):
            raise ValueError(f"email invalid: {email!r}")
        body: dict[str, Any] = {
            "email": email,
        }
        if first_name:
            body["firstName"] = first_name[:100]
        if last_name:
            body["lastName"] = last_name[:100]
        if company_name:
            body["companyName"] = company_name[:200]
        if merge_fields:
            for k, v in merge_fields.items():
                if isinstance(k, str) and k.replace("_", "").isalnum():
                    body[k[:80]] = (str(v) if v is not None else "")[:1000]

        resp = self.request(
            "POST",
            f"/api/campaigns/{campaign_id}/leads/{email}",
            json=body,
        )
        if not isinstance(resp, dict):
            raise ConnectorError("push_to_campaign returned non-object body")
        return resp

    def pause_in_campaign(self, *, campaign_id: str, email: str) -> dict[str, Any]:
        if not _is_id(campaign_id):
            raise ValueError("campaign_id invalid")
        if not _is_email(email):
            raise ValueError("email invalid")
        resp = self.request(
            "POST",
            f"/api/campaigns/{campaign_id}/leads/{email}/pause",
        )
        return resp if isinstance(resp, dict) else {"_raw": str(resp)[:500]}

    def resume_in_campaign(self, *, campaign_id: str, email: str) -> dict[str, Any]:
        if not _is_id(campaign_id):
            raise ValueError("campaign_id invalid")
        if not _is_email(email):
            raise ValueError("email invalid")
        resp = self.request(
            "POST",
            f"/api/campaigns/{campaign_id}/leads/{email}/resume",
        )
        return resp if isinstance(resp, dict) else {"_raw": str(resp)[:500]}

    def stop_in_campaign(self, *, campaign_id: str, email: str) -> dict[str, Any]:
        """Hard stop — removes the prospect from further sends. Irreversible."""
        if not _is_id(campaign_id):
            raise ValueError("campaign_id invalid")
        if not _is_email(email):
            raise ValueError("email invalid")
        resp = self.request(
            "DELETE",
            f"/api/campaigns/{campaign_id}/leads/{email}",
        )
        return resp if isinstance(resp, dict) else {"_raw": str(resp)[:500]}

    # ---- replies + bounces --------------------------------------------------

    def list_replies(
        self,
        *,
        campaign_id: str,
        since: dt.datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List recent replies for a campaign. Empty list = no replies yet."""
        if not _is_id(campaign_id):
            raise ValueError("campaign_id invalid")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be 1..100")
        params: dict[str, Any] = {
            "campaignId": campaign_id,
            "type": "emailsReplied",
            "limit": limit,
        }
        if since:
            params["startDate"] = since.astimezone(dt.UTC).strftime("%Y-%m-%d")
        resp = self.request("GET", "/api/activities", params=params)
        return _ensure_list(resp)

    def list_bounces(
        self,
        *,
        campaign_id: str,
        since: dt.datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not _is_id(campaign_id):
            raise ValueError("campaign_id invalid")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be 1..100")
        params: dict[str, Any] = {
            "campaignId": campaign_id,
            "type": "emailsBounced",
            "limit": limit,
        }
        if since:
            params["startDate"] = since.astimezone(dt.UTC).strftime("%Y-%m-%d")
        resp = self.request("GET", "/api/activities", params=params)
        return _ensure_list(resp)

    # ---- deliverability (Sprint 5 plumbing) ---------------------------------

    def sender_health(self, *, campaign_id: str) -> dict[str, Any]:
        """Aggregate stats: sent / delivered / opened / replied / bounced.

        Used by the deliverability monitor to decide whether to auto-pause.
        """
        if not _is_id(campaign_id):
            raise ValueError("campaign_id invalid")
        resp = self.request("GET", f"/api/campaigns/{campaign_id}")
        if not isinstance(resp, dict):
            return {"sent": 0, "delivered": 0, "opened": 0, "replied": 0, "bounced": 0}

        stats = resp.get("stats") or {}
        return {
            "sent": int(stats.get("emailsSent") or 0),
            "delivered": int(stats.get("emailsDelivered") or 0),
            "opened": int(stats.get("emailsOpened") or 0),
            "replied": int(stats.get("emailsReplied") or 0),
            "bounced": int(stats.get("emailsBounced") or 0),
            "unsubscribed": int(stats.get("emailsUnsubscribed") or 0),
        }


# ---- helpers ---------------------------------------------------------------


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


def _is_email(v: object) -> bool:
    return isinstance(v, str) and bool(_EMAIL_RE.match(v))


def _is_id(v: object) -> bool:
    return isinstance(v, str) and bool(_ID_RE.match(v))


def _ensure_list(resp: object) -> list[dict[str, Any]]:
    if isinstance(resp, list):
        return [r for r in resp if isinstance(r, dict)]
    if isinstance(resp, dict) and "items" in resp and isinstance(resp["items"], list):
        return [r for r in resp["items"] if isinstance(r, dict)]
    return []


# Keep the old stub class name available for callers that still import it,
# but route to the real client + warn.
class LemlistClientStub(LemlistClient):
    """Deprecated alias. Use ``LemlistClient`` directly."""


__all__ = [
    "ConnectorAuthError",
    "ConnectorError",
    "ConnectorUnavailable",
    "LemlistClient",
    "LemlistClientStub",
]
