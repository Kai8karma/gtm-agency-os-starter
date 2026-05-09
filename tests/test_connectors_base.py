"""Base HTTP connector — retry, transport, parse paths."""

from __future__ import annotations

import pytest
import respx
from httpx import Response, TimeoutException

from gtmos.connectors import ConnectorError
from gtmos.connectors.base import HttpConnector


@pytest.fixture
def conn() -> HttpConnector:
    return HttpConnector(
        base_url="https://example.test",
        auth_headers={"Authorization": "Bearer x"},
        max_retries=2,
        timeout_s=2.0,
    )


class TestParse:
    @respx.mock
    def test_204_returns_empty_dict(self, conn: HttpConnector) -> None:
        respx.get("https://example.test/x").respond(204)
        assert conn.request("GET", "/x") == {}

    @respx.mock
    def test_non_json_response_returns_raw(self, conn: HttpConnector) -> None:
        respx.get("https://example.test/x").respond(
            200, content=b"plain text", headers={"content-type": "text/plain"}
        )
        out = conn.request("GET", "/x")
        assert isinstance(out, dict)
        assert "_raw" in out


class TestRetry:
    @respx.mock
    def test_5xx_eventually_succeeds(self, conn: HttpConnector) -> None:
        route = respx.get("https://example.test/x")
        route.side_effect = [
            Response(503),
            Response(503),
            Response(200, json={"ok": True}),
        ]
        out = conn.request("GET", "/x")
        assert isinstance(out, dict)
        assert out.get("ok") is True

    @respx.mock
    def test_5xx_fails_after_retries(self, conn: HttpConnector) -> None:
        respx.get("https://example.test/x").respond(503)
        with pytest.raises(ConnectorError):
            conn.request("GET", "/x")


class TestTransport:
    @respx.mock
    def test_transport_error_retries(
        self, conn: HttpConnector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force the first call to time out, then succeed.
        called = {"n": 0}

        def side_effect(request):  # type: ignore[no-untyped-def]
            called["n"] += 1
            if called["n"] == 1:
                raise TimeoutException("read timed out")
            return Response(200, json={"ok": True})

        respx.get("https://example.test/x").mock(side_effect=side_effect)
        # Avoid sleep delay during retry backoff.
        monkeypatch.setattr("gtmos.connectors.base.time.sleep", lambda *a, **k: None)
        out = conn.request("GET", "/x")
        assert out == {"ok": True}


class TestContextManager:
    def test_close_idempotent(self, conn: HttpConnector) -> None:
        conn.close()
        conn.close()  # second call is a no-op

    def test_context_manager(self, conn: HttpConnector) -> None:
        with conn as c:
            assert c is conn
        # closed implicitly
        assert conn._client is None
