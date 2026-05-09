"""Stubs for not-yet-wired connectors must fail closed at runtime."""

from __future__ import annotations

import datetime as dt

import pytest

from gtmos.connectors import ConnectorUnavailable
from gtmos.connectors.discovery import ApolloClientStub, ClayClientStub
from gtmos.connectors.lemlist import LemlistClientStub


class TestLemlistStub:
    def test_unavailable_without_token(self) -> None:
        class S:
            lemlist_api_key = None
        with pytest.raises(ConnectorUnavailable):
            LemlistClientStub.from_settings(S())

    def test_constructs_with_token(self) -> None:
        class S:
            lemlist_api_key = "lem-key-12345"
        c = LemlistClientStub.from_settings(S())
        assert c is not None

    def test_methods_raise_not_implemented(self) -> None:
        c = LemlistClientStub()
        with pytest.raises(NotImplementedError):
            c.add_to_sequence(sequence_id="seq", prospect_email="x@y.com")
        with pytest.raises(NotImplementedError):
            c.list_recent_replies(since=dt.datetime.now(tz=dt.UTC))
        with pytest.raises(NotImplementedError):
            c.pause_prospect(prospect_email="x@y.com", sequence_id="seq")


class TestDiscoveryStubs:
    def test_apollo_unavailable(self) -> None:
        class S:
            pass
        with pytest.raises(ConnectorUnavailable):
            ApolloClientStub.from_settings(S())

    def test_apollo_search_not_implemented(self) -> None:
        c = ApolloClientStub()
        with pytest.raises(NotImplementedError):
            c.search(title="cto")

    def test_clay_unavailable(self) -> None:
        class S:
            pass
        with pytest.raises(ConnectorUnavailable):
            ClayClientStub.from_settings(S())

    def test_clay_enrich_not_implemented(self) -> None:
        c = ClayClientStub()
        with pytest.raises(NotImplementedError):
            c.enrich(email="x@y.com")
