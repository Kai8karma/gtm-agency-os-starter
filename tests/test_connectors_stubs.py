"""Stubs for not-yet-wired connectors must fail closed at runtime."""

from __future__ import annotations

import pytest

from gtmos.connectors import ConnectorUnavailable
from gtmos.connectors.discovery import ApolloClientStub, ClayClientStub
from gtmos.connectors.lemlist import LemlistClientStub


class TestLemlistStubAlias:
    """LemlistClientStub is now a deprecated alias for the real LemlistClient.

    Real-client behavior is exercised in tests/test_lemlist.py. Here we just
    confirm the alias still routes through the real subclass and that
    fail-closed behavior on missing creds is preserved.
    """

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

    def test_alias_is_subclass_of_real_client(self) -> None:
        from gtmos.connectors.lemlist import LemlistClient

        assert issubclass(LemlistClientStub, LemlistClient)


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
