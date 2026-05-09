"""Lemlist connector — sequencer integration.

This module declares the contract this OS expects from a sequencer connector
but does **not** implement it in v0.3. Wiring against your Lemlist workspace
requires:

  * a Lemlist API key (``LEMLIST_API_KEY`` env var),
  * the campaign IDs you want this OS to push prospects into,
  * a deliverability owner who watches bounce + reply rates per campaign.

To enable: subclass ``LemlistClientStub`` and implement the methods, then
register your subclass in ``gtmos/pipelines/`` where it is consumed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from gtmos.connectors.base import ConnectorUnavailable


class LemlistClientStub:
    """Stub that fails closed. Replace with a real implementation per engagement."""

    @classmethod
    def from_settings(cls, settings: object) -> LemlistClientStub:
        token = getattr(settings, "lemlist_api_key", None)
        if not token:
            raise ConnectorUnavailable("LEMLIST_API_KEY unset")
        return cls()

    def add_to_sequence(
        self,
        *,
        sequence_id: str,
        prospect_email: str,
        merge_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "LemlistClientStub.add_to_sequence is not wired in v0.3. "
            "Implement against https://developer.lemlist.com/ and replace this class."
        )

    def list_recent_replies(self, *, since: dt.datetime) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "LemlistClientStub.list_recent_replies is not wired in v0.3."
        )

    def pause_prospect(self, *, prospect_email: str, sequence_id: str) -> dict[str, Any]:
        raise NotImplementedError(
            "LemlistClientStub.pause_prospect is not wired in v0.3."
        )


__all__ = ["ConnectorUnavailable", "LemlistClientStub"]
