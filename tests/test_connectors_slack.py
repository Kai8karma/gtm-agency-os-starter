"""Slack messenger tests with the Slack SDK mocked."""

from __future__ import annotations

from typing import Any

import pytest
from slack_sdk.errors import SlackApiError

from gtmos.connectors import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimited,
    ConnectorUnavailable,
)
from gtmos.connectors.slack import SlackMessenger


def _make(token: str = "xo" + "xb-test-bot-token") -> SlackMessenger:
    return SlackMessenger(bot_token=token, default_provenance="test-prov")


class _StubResp:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


class _StubWebClient:
    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []
        self.opened: list[str] = []

    def chat_postMessage(self, **kwargs: Any) -> _StubResp:
        self.posted.append(kwargs)
        return _StubResp({"ok": True, "ts": "1700000000.000100"})

    def conversations_open(self, *, users: str) -> _StubResp:
        self.opened.append(users)
        return _StubResp({"ok": True, "channel": {"id": "D" + users[1:]}})


class TestConstruction:
    def test_unavailable_without_token(self) -> None:
        with pytest.raises(ConnectorUnavailable):
            SlackMessenger(bot_token="")

    def test_unavailable_with_wrong_shape(self) -> None:
        with pytest.raises(ConnectorUnavailable):
            SlackMessenger(bot_token="bearer-something-else")

    def test_from_settings_without_token(self) -> None:
        class S:
            slack_bot_token = None
        with pytest.raises(ConnectorUnavailable):
            SlackMessenger.from_settings(S())


class TestPostMessage:
    def test_appends_provenance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        m = _make()
        stub = _StubWebClient()
        monkeypatch.setattr(m, "_client", stub)
        m.post_message(channel="C123", text="Hello team")
        assert stub.posted[0]["text"].endswith("test-prov")

    def test_dm_resolves_to_im_channel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        m = _make()
        stub = _StubWebClient()
        monkeypatch.setattr(m, "_client", stub)
        m.dm_user(user_id="U0KAI", text="ping")
        assert stub.opened == ["U0KAI"]
        assert stub.posted[0]["channel"].startswith("D")

    def test_invalid_user_id_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        m = _make()
        stub = _StubWebClient()
        monkeypatch.setattr(m, "_client", stub)
        with pytest.raises(ValueError, match="user_id"):
            m.dm_user(user_id="kai", text="x")

    def test_missing_channel_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = _make()
        stub = _StubWebClient()
        monkeypatch.setattr(m, "_client", stub)
        with pytest.raises(ValueError, match="channel"):
            m.post_message(channel="", text="x")


class TestErrorClassification:
    def _err(self, code: str) -> SlackApiError:
        from slack_sdk.web import SlackResponse

        resp = SlackResponse(
            client=None,  # type: ignore[arg-type]
            http_verb="POST",
            api_url="https://example.test/x",
            req_args={},
            data={"ok": False, "error": code},
            headers={},
            status_code=200,
        )
        return SlackApiError("boom", resp)

    def test_invalid_auth_becomes_auth_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = _make()

        class _BadClient:
            def chat_postMessage(_self, **kwargs: Any) -> Any:
                raise self._err("invalid_auth")

        monkeypatch.setattr(m, "_client", _BadClient())
        with pytest.raises(ConnectorAuthError):
            m.post_message(channel="C1", text="x")

    def test_ratelimited_becomes_rate_limited(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = _make()

        class _SlowClient:
            def chat_postMessage(_self, **kwargs: Any) -> Any:
                raise self._err("ratelimited")

        monkeypatch.setattr(m, "_client", _SlowClient())
        with pytest.raises(ConnectorRateLimited):
            m.post_message(channel="C1", text="x")

    def test_other_errors_become_connector_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = _make()

        class _OddClient:
            def chat_postMessage(_self, **kwargs: Any) -> Any:
                raise self._err("channel_not_found")

        monkeypatch.setattr(m, "_client", _OddClient())
        with pytest.raises(ConnectorError, match="channel_not_found"):
            m.post_message(channel="C1", text="x")
