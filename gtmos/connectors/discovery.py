"""Lead discovery connectors — Apollo / Clay / Bitscale stubs.

Same shape as ``lemlist.py``: declare the contract, fail closed at runtime.
Each engagement wires whichever of Apollo / Clay / Bitscale they use.
"""

from __future__ import annotations

from typing import Any

from gtmos.connectors.base import ConnectorUnavailable


class ApolloClientStub:
    """Apollo people-search stub."""

    @classmethod
    def from_settings(cls, settings: object) -> ApolloClientStub:  # noqa: ARG003
        # No standard env var name yet — engagements add their own.
        raise ConnectorUnavailable(
            "Apollo connector is not wired in v0.3. "
            "Add an APOLLO_API_KEY env var, implement search(), and replace this class."
        )

    def search(self, **filters: Any) -> list[dict[str, Any]]:
        raise NotImplementedError("Apollo.search not wired in v0.3.")


class ClayClientStub:
    """Clay enrichment / Claygent stub."""

    @classmethod
    def from_settings(cls, settings: object) -> ClayClientStub:  # noqa: ARG003
        raise ConnectorUnavailable(
            "Clay connector is not wired in v0.3. "
            "Wire your Clay table webhooks and implement enrich() per engagement."
        )

    def enrich(self, *, email: str | None = None, linkedin_url: str | None = None) -> dict[str, Any]:
        raise NotImplementedError("Clay.enrich not wired in v0.3.")


__all__ = ["ApolloClientStub", "ClayClientStub", "ConnectorUnavailable"]
