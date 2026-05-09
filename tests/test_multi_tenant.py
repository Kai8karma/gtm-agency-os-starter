"""Per-client isolation tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gtmos.config import Settings
from gtmos.multi_tenant import (
    client_brain_query_prefix,
    client_eval_path,
    client_secrets,
    client_tasks_db,
)


@pytest.fixture
def isolated_settings(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")
    return Settings.load()


def test_per_client_tasks_db(isolated_settings: Settings) -> None:
    p1 = client_tasks_db(isolated_settings, "acme")
    p2 = client_tasks_db(isolated_settings, "globex")
    assert p1 != p2
    assert p1.name == "tasks-acme.db"
    assert p2.name == "tasks-globex.db"


def test_per_client_eval_override(isolated_settings: Settings, tmp_repo: Path) -> None:
    base = tmp_repo / "evals" / "weekly-review.yaml"
    base.write_text("agent: weekly-review\n", encoding="utf-8")
    override = tmp_repo / "evals" / "weekly-review.acme.yaml"
    override.write_text("agent: weekly-review\nagent_overrides: acme\n", encoding="utf-8")

    assert client_eval_path(isolated_settings, "weekly-review", None) == base.resolve()
    assert client_eval_path(isolated_settings, "weekly-review", "acme") == override.resolve()
    # missing override falls back
    assert client_eval_path(isolated_settings, "weekly-review", "globex") == base.resolve()


def test_brain_query_prefix() -> None:
    assert client_brain_query_prefix(None) == ""
    assert client_brain_query_prefix("acme") == "client:acme "
    assert client_brain_query_prefix("_example").startswith("client:_example")


class TestClientSecrets:
    def test_layers_then_restores(
        self, isolated_settings: Settings, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HUBSPOT_PRIVATE_APP_TOKEN", "global-token")
        cd = tmp_repo / "clients" / "acme"
        cd.mkdir(parents=True)
        (cd / "secrets.env").write_text(
            "HUBSPOT_PRIVATE_APP_TOKEN=acme-token\n"
            "LEMLIST_API_KEY=acme-lem-key\n",
            encoding="utf-8",
        )
        with client_secrets(isolated_settings, "acme"):
            assert os.environ["HUBSPOT_PRIVATE_APP_TOKEN"] == "acme-token"
            assert os.environ["LEMLIST_API_KEY"] == "acme-lem-key"
        # outside the context, original is restored
        assert os.environ["HUBSPOT_PRIVATE_APP_TOKEN"] == "global-token"
        assert "LEMLIST_API_KEY" not in os.environ

    def test_no_secrets_file_is_noop(
        self, isolated_settings: Settings, tmp_repo: Path
    ) -> None:
        # No secrets.env present — context is a no-op
        with client_secrets(isolated_settings, "ghost"):
            pass

    def test_invalid_slug_rejected(self, isolated_settings: Settings) -> None:
        from gtmos.security import InvalidSlugError

        with pytest.raises(InvalidSlugError), client_secrets(isolated_settings, "../escape"):
            pass
