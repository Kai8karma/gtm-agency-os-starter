"""Slack message connector.

Used by pipelines and the Slack handler to send messages — separate from
``slack_app.py`` (which receives them). One concern per file (Pattern 2).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient

from gtmos.connectors.base import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimited,
    ConnectorUnavailable,
)
from gtmos.security import redact

logger = logging.getLogger(__name__)


@dataclass
class SlackMessenger:
    """Minimal Slack message sender wrapping ``slack_sdk.WebClient``.

    Provides:
      * ``post_message(channel, text)`` — channel or DM.
      * ``dm_user(user_id, text)`` — opens an IM channel with the user, posts.

    All sends append a provenance line so the recipient can trace it.
    Falls through ``ConnectorRateLimited`` on Slack 429 with Retry-After.
    """

    bot_token: str
    default_provenance: str = ""
    _client: WebClient | None = None

    def __post_init__(self) -> None:
        if not self.bot_token or not self.bot_token.startswith(("xoxb-", "xoxp-", "xoxe.")):
            raise ConnectorUnavailable(
                "SLACK_BOT_TOKEN unset or wrong shape (expected xoxb- / xoxp-)"
            )

    @classmethod
    def from_settings(cls, settings: object, *, provenance: str = "") -> SlackMessenger:
        token = getattr(settings, "slack_bot_token", None)
        if not token:
            raise ConnectorUnavailable("SLACK_BOT_TOKEN unset")
        return cls(bot_token=token, default_provenance=provenance)

    def _ensure(self) -> WebClient:
        if self._client is None:
            self._client = WebClient(token=self.bot_token, timeout=20)
        return self._client

    # ---- send paths ---------------------------------------------------------

    def post_message(
        self,
        *,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        blocks: Sequence[dict[str, Any]] | None = None,
        provenance: str | None = None,
    ) -> dict[str, Any]:
        """Post to a channel ID, conversation ID, or user-id (will resolve DM)."""
        if not isinstance(channel, str) or not channel:
            raise ValueError("channel required")
        if not isinstance(text, str):
            raise ValueError("text must be a string")

        target_channel = channel
        if channel.startswith("U"):
            target_channel = self._open_dm(channel)

        prov = provenance if provenance is not None else self.default_provenance
        body_text = (text + "\n\n" + prov).strip() if prov else text

        kwargs: dict[str, Any] = {"channel": target_channel, "text": body_text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if blocks:
            kwargs["blocks"] = list(blocks)

        try:
            resp = self._ensure().chat_postMessage(**kwargs)
        except SlackApiError as e:
            return self._classify_slack_error("chat_postMessage", e)

        return _normalize(resp.data)

    def dm_user(self, *, user_id: str, text: str, provenance: str | None = None) -> dict[str, Any]:
        if not isinstance(user_id, str) or not user_id.startswith("U"):
            raise ValueError(f"user_id must be a Slack user id (got {user_id!r})")
        return self.post_message(channel=user_id, text=text, provenance=provenance)

    # ---- helpers ------------------------------------------------------------

    def _open_dm(self, user_id: str) -> str:
        try:
            resp = self._ensure().conversations_open(users=user_id)
        except SlackApiError as e:
            self._classify_slack_error("conversations_open", e)
            raise  # unreachable; classify raises
        data = _normalize(resp.data)
        channel = (data.get("channel") or {}).get("id")
        if not channel:
            raise ConnectorError("conversations_open returned no channel id")
        return channel

    @staticmethod
    def _classify_slack_error(op: str, e: SlackApiError) -> dict[str, Any]:
        try:
            err_code = (e.response.data or {}).get("error", "unknown")
        except Exception:
            err_code = "unknown"
        msg = redact(str(e))
        if err_code in {"invalid_auth", "not_authed", "token_revoked"}:
            raise ConnectorAuthError(f"{op}: {err_code}") from e
        if err_code in {"ratelimited", "rate_limited"}:
            raise ConnectorRateLimited(f"{op}: rate limited") from e
        raise ConnectorError(f"{op}: {err_code} — {msg}") from e


def _normalize(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    return {"_raw": str(data)}


__all__ = [
    "ConnectorAuthError",
    "ConnectorError",
    "ConnectorRateLimited",
    "ConnectorUnavailable",
    "SlackMessenger",
]
