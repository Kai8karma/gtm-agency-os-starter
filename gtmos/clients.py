"""Client loader — parses ``clients/<slug>/client.md`` frontmatter.

Frontmatter schema is enforced via Pydantic so missing fields fail loudly
instead of silently mis-routing a Slack DM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter
from pydantic import BaseModel, Field, ValidationError, field_validator

from gtmos.security import InvalidSlugError, safe_join, validate_slug


class ClientLoadError(Exception):
    """Raised when a client.md is missing, malformed, or fails validation."""


class ClientFrontmatter(BaseModel):
    """Strict view of ``clients/<slug>/client.md`` frontmatter."""

    slug: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    tier: str = Field(default="active")
    team: list[str] = Field(default_factory=list)
    owner_slack_id: str | None = Field(default=None)
    pause: bool = False
    no_go_topics: list[str] = Field(default_factory=list)
    voice_overrides: dict[str, Any] = Field(default_factory=dict)
    tier_overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        return validate_slug(v, allow_underscore_prefix=True)

    @field_validator("owner_slack_id")
    @classmethod
    def _validate_owner_slack_id(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        # Slack user IDs are uppercase alphanumeric, 9-13 chars typically.
        if not v.isalnum() or not v.isupper() or not v.startswith("U"):
            raise ValueError(
                "owner_slack_id must look like a Slack user ID (e.g. U0ABCDE12)"
            )
        if not 5 <= len(v) <= 16:
            raise ValueError("owner_slack_id length out of expected range (5-16)")
        return v


def load_client(repo_root: Path, slug: str) -> ClientFrontmatter:
    """Load and validate ``clients/<slug>/client.md``."""
    safe_slug = validate_slug(slug, allow_underscore_prefix=True)
    path = safe_join(repo_root, "clients", safe_slug, "client.md")
    if not path.is_file():
        raise ClientLoadError(f"clients/{safe_slug}/client.md not found")

    try:
        post = frontmatter.load(path)
    except Exception as e:
        raise ClientLoadError(f"clients/{safe_slug}/client.md frontmatter parse: {e}") from e

    data: dict[str, Any] = dict(post.metadata)
    # Guarantee `slug` matches the directory.
    declared = data.get("slug")
    if declared and declared != safe_slug:
        raise ClientLoadError(
            f"clients/{safe_slug}/client.md frontmatter slug={declared!r} "
            f"!= directory {safe_slug!r}"
        )
    data["slug"] = safe_slug

    try:
        return ClientFrontmatter(**data)
    except ValidationError as e:
        raise ClientLoadError(
            f"clients/{safe_slug}/client.md validation: {e}"
        ) from e


def list_clients(repo_root: Path, *, include_template: bool = False) -> list[str]:
    """Enumerate active client slugs by walking ``clients/``."""
    clients_dir = safe_join(repo_root, "clients")
    if not clients_dir.is_dir():
        return []
    out: list[str] = []
    for child in sorted(clients_dir.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "client.md").is_file():
            continue
        slug = child.name
        try:
            validate_slug(slug, allow_underscore_prefix=True)
        except InvalidSlugError:
            # Directories with non-slug names are skipped silently — this is a
            # discovery loop, not an enforcement layer.
            continue
        if slug.startswith("_") and not include_template:
            continue
        out.append(slug)
    return out


def is_authorized_invoker(client: ClientFrontmatter, slack_user_id: str) -> bool:
    """Check whether a Slack user may invoke per-client subcommands.

    The ``team`` field can hold either Slack user IDs (``U…``) or short
    handles. We accept either form. Empty team list defaults to "owner-only".
    """
    if not isinstance(slack_user_id, str) or not slack_user_id:
        return False
    if client.owner_slack_id and slack_user_id == client.owner_slack_id:
        return True
    if not client.team:
        return False
    return slack_user_id in client.team
