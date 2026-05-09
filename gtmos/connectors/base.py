"""Shared HTTP connector base.

Centralizes retry, timeout, redacted error reporting, and capability gating
so individual connectors stay focused on the domain methods.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from gtmos.security import redact

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """Generic connector failure (4xx, parse error, timeout)."""


class ConnectorAuthError(ConnectorError):
    """Authentication / authorization rejected."""


class ConnectorRateLimited(ConnectorError):
    """Connector signaled rate limiting; caller may retry later."""


class ConnectorUnavailable(ConnectorError):
    """Required credentials missing or connector intentionally not wired."""


@dataclass
class HttpConnector:
    """Base for any HTTP-backed connector.

    Subclasses set ``base_url`` and ``auth_headers``; this class owns the
    request loop. Logging redacts via ``security.redact`` before any record
    leaves the process.
    """

    base_url: str
    auth_headers: Mapping[str, str] = field(default_factory=dict)
    timeout_s: float = 30.0
    max_retries: int = 3
    retry_status: tuple[int, ...] = (429, 500, 502, 503, 504)
    user_agent: str = "gtm-agency-os/0.3"

    _client: httpx.Client | None = None

    # ---- lifecycle ----------------------------------------------------------

    def _ensure(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_s),
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                    **self.auth_headers,
                },
                follow_redirects=False,  # explicit redirect handling only
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> HttpConnector:
        self._ensure()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- request loop -------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        expected_status: tuple[int, ...] = (200, 201, 202, 204),
    ) -> dict[str, Any] | list[Any]:
        client = self._ensure()
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = client.request(method.upper(), path, params=params, json=json)
            except httpx.TransportError as e:
                last_error = e
                logger.warning(
                    "connector %s transport error attempt=%d: %s",
                    self.base_url, attempt, redact(str(e)),
                )
                self._sleep_backoff(attempt)
                continue

            if resp.status_code in expected_status:
                return self._parse_body(resp)

            if resp.status_code == 401 or resp.status_code == 403:
                raise ConnectorAuthError(
                    f"{method.upper()} {path} → {resp.status_code}: "
                    f"{redact(resp.text[:300])}"
                )

            if resp.status_code in self.retry_status and attempt < self.max_retries:
                retry_after = _retry_after_seconds(resp)
                logger.info(
                    "connector %s status=%d retry attempt=%d in %.1fs",
                    self.base_url, resp.status_code, attempt, retry_after,
                )
                time.sleep(retry_after)
                continue

            if resp.status_code == 429:
                raise ConnectorRateLimited(
                    f"{method.upper()} {path} rate-limited after {attempt} retries"
                )

            raise ConnectorError(
                f"{method.upper()} {path} → {resp.status_code}: "
                f"{redact(resp.text[:300])}"
            )

        raise ConnectorError(
            f"{method.upper()} {path} failed after {self.max_retries + 1} attempts; "
            f"last error: {redact(str(last_error))}"
        )

    @staticmethod
    def _parse_body(resp: httpx.Response) -> dict[str, Any] | list[Any]:
        if resp.status_code == 204 or not resp.content:
            return {}
        ctype = resp.headers.get("content-type", "")
        if "application/json" not in ctype.lower():
            return {"_raw": redact(resp.text[:500])}
        try:
            return resp.json()
        except ValueError as e:
            raise ConnectorError(f"invalid JSON response: {redact(str(e))}") from e

    def _sleep_backoff(self, attempt: int) -> None:
        if attempt >= self.max_retries:
            return
        # Decorrelated jitter: each backoff is at least 0.5s, at most ~8s.
        base = 0.5 * (2 ** attempt)
        # Jitter is non-security; pseudo-randomness is the right primitive.
        sleep = min(8.0, random.uniform(0.5, base + 0.5))  # noqa: S311  # nosec B311
        time.sleep(sleep)


def _retry_after_seconds(resp: httpx.Response) -> float:
    val = resp.headers.get("Retry-After")
    if not val:
        return 1.0
    try:
        return min(60.0, max(0.5, float(val)))
    except (TypeError, ValueError):
        return 1.0
