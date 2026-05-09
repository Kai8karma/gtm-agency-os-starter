"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    """Path to the repo we're testing against."""
    here = Path(__file__).resolve().parent.parent
    assert (here / "CLAUDE.md").is_file(), f"CLAUDE.md missing at {here}"
    return here


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """A throwaway repo root with the minimum doctrine files."""
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
    (tmp_path / "agents").mkdir()
    (tmp_path / "evals").mkdir()
    (tmp_path / "clients").mkdir()
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / ".state").mkdir()
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip any host env vars that could leak into tests."""
    sensitive = {
        "ANTHROPIC_API_KEY",
        "HUBSPOT_PRIVATE_APP_TOKEN",
        "LEMLIST_API_KEY",
        "NOTION_TOKEN",
        "NOTION_TASKS_DB_ID",
    }
    for key in list(os.environ):
        if key.startswith(("GTMOS_", "SLACK_")) or key in sensitive:
            monkeypatch.delenv(key, raising=False)
    return
