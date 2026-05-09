"""Client loader tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gtmos.clients import (
    ClientFrontmatter,
    ClientLoadError,
    is_authorized_invoker,
    list_clients,
    load_client,
)


def _write_client(repo: Path, slug: str, body: str) -> None:
    d = repo / "clients" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "client.md").write_text(body, encoding="utf-8")


def test_loads_minimal_valid_client(tmp_repo: Path) -> None:
    _write_client(
        tmp_repo,
        "acme",
        """---
slug: acme
name: Acme Inc.
team: ["U0KAI", "U0OPS"]
owner_slack_id: U0KAI
---
# acme
""",
    )
    c = load_client(tmp_repo, "acme")
    assert c.slug == "acme"
    assert c.name == "Acme Inc."
    assert c.owner_slack_id == "U0KAI"
    assert c.pause is False


def test_slug_directory_mismatch_rejected(tmp_repo: Path) -> None:
    _write_client(
        tmp_repo,
        "acme",
        """---
slug: not-acme
name: Misnamed
---
""",
    )
    with pytest.raises(ClientLoadError, match="slug"):
        load_client(tmp_repo, "acme")


def test_invalid_slack_id_rejected(tmp_repo: Path) -> None:
    _write_client(
        tmp_repo,
        "acme",
        """---
slug: acme
name: Acme
owner_slack_id: kai-without-prefix
---
""",
    )
    with pytest.raises(ClientLoadError):
        load_client(tmp_repo, "acme")


def test_missing_required_name_rejected(tmp_repo: Path) -> None:
    _write_client(
        tmp_repo,
        "acme",
        """---
slug: acme
---
no name
""",
    )
    with pytest.raises(ClientLoadError):
        load_client(tmp_repo, "acme")


def test_path_traversal_blocked(tmp_repo: Path) -> None:
    from gtmos.security import InvalidSlugError, PathEscapeError

    with pytest.raises((InvalidSlugError, PathEscapeError)):
        load_client(tmp_repo, "../../../etc")


def test_list_clients_excludes_template_by_default(tmp_repo: Path) -> None:
    _write_client(
        tmp_repo,
        "_example",
        """---
slug: _example
name: Template
---
""",
    )
    _write_client(
        tmp_repo,
        "acme",
        """---
slug: acme
name: Acme
---
""",
    )
    assert list_clients(tmp_repo) == ["acme"]
    assert sorted(list_clients(tmp_repo, include_template=True)) == ["_example", "acme"]


def test_authorized_invoker_owner_passes() -> None:
    c = ClientFrontmatter(slug="acme", name="Acme", owner_slack_id="U0KAI")
    assert is_authorized_invoker(c, "U0KAI") is True


def test_authorized_invoker_team_member_passes() -> None:
    c = ClientFrontmatter(
        slug="acme",
        name="Acme",
        owner_slack_id="U0KAI",
        team=["U0KAI", "U0OPS"],
    )
    assert is_authorized_invoker(c, "U0OPS") is True


def test_unauthorized_user_rejected() -> None:
    c = ClientFrontmatter(
        slug="acme", name="Acme", owner_slack_id="U0KAI", team=["U0KAI"]
    )
    assert is_authorized_invoker(c, "U0EVIL") is False


def test_empty_user_rejected() -> None:
    c = ClientFrontmatter(slug="acme", name="Acme", owner_slack_id="U0KAI")
    assert is_authorized_invoker(c, "") is False
    assert is_authorized_invoker(c, None) is False  # type: ignore[arg-type]
