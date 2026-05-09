"""Anthropic API wrapper.

Single chokepoint for all Claude calls. Owns:
  * client construction (timeout, retries),
  * prompt-cache discipline (system stable, user varies),
  * secret redaction in error paths,
  * deterministic shape: ``LLMResponse``.

Callers should never instantiate ``anthropic.Anthropic`` directly.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass

import anthropic
from anthropic.types import MessageParam

from gtmos.security import redact

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    stop_reason: str


@dataclass
class LLMClient:
    """Thin wrapper around ``anthropic.Anthropic``.

    Construct via ``LLMClient.from_settings(settings)``. Calls
    ``client.messages.create()`` under the hood with sensible defaults:
        * 5-minute prompt cache TTL on the system block,
        * automatic SDK retries on transient errors (3 attempts),
        * timeout from ``Settings.agent_timeout_s``.
    """

    api_key: str
    timeout_s: int = 300
    _client: anthropic.Anthropic | None = None

    def __post_init__(self) -> None:
        if not self.api_key or len(self.api_key) < 10:
            raise ValueError("api_key missing or too short")

    @classmethod
    def from_settings(cls, settings: object) -> LLMClient:
        return cls(
            api_key=settings.anthropic_api_key,
            timeout_s=getattr(settings, "agent_timeout_s", 300),
        )

    def _ensure(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                timeout=float(self.timeout_s),
                max_retries=3,
            )
        return self._client

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: Iterable[MessageParam],
        max_tokens: int = 2048,
        cache_system: bool = True,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Run a single message-create call.

        ``system`` should be stable across calls (doctrine, brand card,
        agent prompt) so the prompt cache hits.
        """
        client = self._ensure()
        msgs = list(messages)
        if not msgs:
            raise ValueError("at least one user message required")

        # Cache the system block. Anthropic prompt-cache requires explicit
        # cache_control on a content block, not a top-level string.
        if cache_system:
            system_arg: object = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_arg = system

        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_arg,  # type: ignore[arg-type]
                messages=msgs,
            )
        except anthropic.APIError as e:
            # Never log the api key. Redact arbitrary error strings.
            logger.error("Anthropic API error: %s", redact(str(e)))
            raise

        # Concatenate text blocks. Tools/extended-content out of scope here.
        text_parts: list[str] = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", ""))
        text = "".join(text_parts)

        usage = resp.usage
        return LLMResponse(
            text=text,
            model=resp.model,
            input_tokens=int(getattr(usage, "input_tokens", 0)),
            output_tokens=int(getattr(usage, "output_tokens", 0)),
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_creation_tokens=int(
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            ),
            stop_reason=str(getattr(resp, "stop_reason", "") or ""),
        )


def env_offline() -> bool:
    """Useful for tests + offline CI: skip when ``GTMOS_OFFLINE=1``."""
    return os.environ.get("GTMOS_OFFLINE", "").strip() == "1"
