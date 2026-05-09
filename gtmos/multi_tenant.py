"""Per-client isolation — namespaced state per engagement.

Each client gets:
  * its own task store (``runs/.state/tasks-<slug>.db``)
  * its own connector token set (resolved from ``clients/<slug>/secrets.env``
    if present, falling back to global env)
  * its own brain recall namespace (a ``client:<slug>`` tag prepended to
    queries so we don't leak one engagement's outcomes into another)
  * its own eval baseline (``evals/<agent>.<slug>.yaml`` overrides
    ``evals/<agent>.yaml`` when present)

This is the v0.4 scope: data isolation by namespace + per-client secrets.
v1.0 isolation (separate processes / containers) is out of scope.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from gtmos.config import Settings
from gtmos.security import safe_join, validate_slug

logger = logging.getLogger(__name__)


_CLIENT_SECRET_FILE = "secrets.env"  # nosec B105  # noqa: S105


def client_tasks_db(settings: Settings, slug: str) -> Path:
    """Path to the per-client sqlite task DB. Falls back to global path on '_' prefix."""
    safe_slug = validate_slug(slug, allow_underscore_prefix=True)
    base = settings.tasks_db_path.parent
    base.mkdir(parents=True, exist_ok=True)
    return base / f"tasks-{safe_slug}.db"


def client_eval_path(settings: Settings, agent_name: str, slug: str | None) -> Path:
    """Resolve evals/<agent>.<slug>.yaml override or fall back to evals/<agent>.yaml."""
    base = safe_join(settings.repo_root, "evals", f"{agent_name}.yaml")
    if slug is None:
        return base
    safe_slug = validate_slug(slug, allow_underscore_prefix=True)
    override = safe_join(settings.repo_root, "evals", f"{agent_name}.{safe_slug}.yaml")
    return override if override.is_file() else base


def client_brain_query_prefix(slug: str | None) -> str:
    """Prefix used to namespace brain searches for a client.

    Used by ``AgentExecutor`` when seeding recall queries so cross-engagement
    outcomes don't leak. The brain CLI doesn't natively scope by tag, so this
    is a soft namespace via search query rather than a hard isolation.
    """
    if slug is None:
        return ""
    safe_slug = validate_slug(slug, allow_underscore_prefix=True)
    return f"client:{safe_slug} "


@contextmanager
def client_secrets(settings: Settings, slug: str) -> Iterator[None]:
    """Layer ``clients/<slug>/secrets.env`` over ``os.environ`` for the duration
    of the context. Existing process env is restored on exit.

    The file is dotenv-formatted (``KEY=value`` per line). Comments + blanks
    skipped. Loaded via ``python-dotenv``'s parser.
    """
    safe_slug = validate_slug(slug, allow_underscore_prefix=True)
    secret_path = safe_join(settings.repo_root, "clients", safe_slug, _CLIENT_SECRET_FILE)
    if not secret_path.is_file():
        # Nothing to layer; use global env.
        yield
        return

    from dotenv import dotenv_values

    layered = dotenv_values(secret_path)
    saved: dict[str, str | None] = {}
    try:
        for k, v in layered.items():
            if v is None:
                continue
            if not isinstance(k, str) or not k.replace("_", "").isalnum():
                logger.warning("client %s secret key %r ignored (not alphanumeric)", slug, k)
                continue
            saved[k] = os.environ.get(k)
            os.environ[k] = v
        yield
    finally:
        for k, original in saved.items():
            if original is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = original


def reload_settings_for_client(settings: Settings, slug: str) -> Settings:  # noqa: ARG001
    """Re-load Settings inside an active ``client_secrets`` context.

    ``slug`` is accepted for symmetry with the broader API even though the
    reload itself reads the (already-layered) os.environ rather than the slug.
    Tokens that came from per-client overrides are picked up; everything else
    inherits the parent settings.
    """
    return Settings.load(require=settings.required_for)


__all__ = [
    "client_brain_query_prefix",
    "client_eval_path",
    "client_secrets",
    "client_tasks_db",
    "reload_settings_for_client",
]
