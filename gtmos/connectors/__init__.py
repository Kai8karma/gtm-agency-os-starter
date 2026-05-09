"""External-system connectors.

Each connector is a thin, testable wrapper around one third-party API.
Connectors funnel through ``HttpConnector`` for retry, timeout, and redacted
logging. A connector is *required* to:

  * fail closed when its capability is configured but creds are missing;
  * never log secrets in errors (use ``security.redact``);
  * use parameterized requests (no string-built URLs from user input);
  * surface 4xx/5xx as ``ConnectorError`` with redacted body excerpt.
"""

from __future__ import annotations

from gtmos.connectors.base import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimited,
    ConnectorUnavailable,
    HttpConnector,
)

__all__ = [
    "ConnectorAuthError",
    "ConnectorError",
    "ConnectorRateLimited",
    "ConnectorUnavailable",
    "HttpConnector",
]
