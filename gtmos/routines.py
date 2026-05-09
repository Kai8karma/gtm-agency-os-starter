"""Routine dispatcher — runs a single named routine end-to-end.

This is the "fire one routine now" entrypoint used by Claude Routines /
crontab / a manual `gtmos routine <name>` invocation. Daemonized scheduling
itself is intentionally out of scope: cron-style schedulers do this better
than reinventing one in-process. The schedule lives in the routine's
markdown frontmatter.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Iterable
from pathlib import Path

import frontmatter

from gtmos.agents import AgentExecutor
from gtmos.clients import ClientLoadError, list_clients, load_client
from gtmos.config import Settings
from gtmos.security import safe_join

logger = logging.getLogger(__name__)


def run_routine(settings: Settings, name: str) -> int:
    """Run a single routine. Returns process exit code."""
    spec = _load_routine(settings.repo_root, name)
    fanout = spec.get("fanout", "none")
    agent_name = spec.get("agent")

    if fanout == "per-client":
        return _run_per_client(settings, name, spec)
    if fanout == "per-owner":
        return _run_per_owner(settings, name, spec)
    if fanout == "none":
        if agent_name:
            return _run_one(settings, agent_name, task=name, inputs={"routine": name})
        # No agent + no fanout = pure utility routine (e.g., task-cron).
        return _run_utility(settings, name)

    logger.error("unknown fanout for routine %s: %s", name, fanout)
    return 2


# ---- per-fanout implementations --------------------------------------------


def _run_per_client(settings: Settings, name: str, spec: dict) -> int:
    agent = spec.get("agent")
    if not agent:
        logger.error("per-client routine %s missing 'agent' frontmatter", name)
        return 2
    agent_basename = _agent_basename(agent)

    failures = 0
    for slug in list_clients(settings.repo_root):
        try:
            client = load_client(settings.repo_root, slug)
        except ClientLoadError as e:
            logger.error("client %s load failed: %s", slug, e)
            failures += 1
            continue

        if client.pause:
            _log_skip(settings.repo_root, name, slug, "pause=true")
            continue

        if _is_dormant(settings.repo_root, slug):
            _log_skip(settings.repo_root, name, slug, "no recent activity")
            continue

        try:
            _run_one(
                settings,
                agent_basename,
                task=name,
                inputs={"client": slug, "routine": name},
                client_slug=slug,
            )
        except Exception as e:
            logger.exception("client %s routine %s failed", slug, name)
            failures += 1
            _ = e
    return 0 if failures == 0 else 1


def _run_per_owner(settings: Settings, name: str, spec: dict) -> int:
    agent = spec.get("agent")
    if not agent:
        return 2
    agent_basename = _agent_basename(agent)

    owners = _gather_owners(settings.repo_root)
    failures = 0
    for owner in sorted(owners):
        try:
            _run_one(
                settings,
                agent_basename,
                task=f"{name}-{owner}",
                inputs={"owner": owner, "routine": name},
            )
        except Exception:
            logger.exception("owner %s routine %s failed", owner, name)
            failures += 1
    return 0 if failures == 0 else 1


def _run_utility(settings: Settings, name: str) -> int:
    """Routines that don't run an agent (e.g., task-cron)."""
    if name == "task-cron":
        from gtmos.tasks import TaskStore, dispatch_overdue_dms

        store = TaskStore(db_path=settings.tasks_db_path)
        plan = dispatch_overdue_dms(store)
        # MVP: emit a JSON plan. Production wires Slack DM send + mark_dm_sent.
        out = [
            {
                "task_id": dm.task_id,
                "owner_slack_id": dm.owner_slack_id,
                "title": dm.title,
                "days_late": dm.days_late,
            }
            for dm in plan
        ]
        print(json.dumps({"routine": "task-cron", "overdue": out}, indent=2))
        return 0

    logger.error("unknown utility routine: %s", name)
    return 2


# ---- helpers ---------------------------------------------------------------


def _run_one(
    settings: Settings,
    agent_basename: str,
    *,
    task: str,
    inputs: dict,
    client_slug: str | None = None,
) -> int:
    executor = AgentExecutor.from_settings(settings)
    run = executor.run(agent_basename, inputs, client_slug=client_slug, task=task)
    if run.error:
        return 1
    return 0


def _load_routine(repo_root: Path, name: str) -> dict:
    path = safe_join(repo_root, "routines", f"{name}.md")
    if not path.is_file():
        raise FileNotFoundError(f"routines/{name}.md not found")
    post = frontmatter.load(path)
    return dict(post.metadata)


def _agent_basename(agent_field: str) -> str:
    """Convert ``agents/weekly-review.md`` → ``weekly-review``."""
    p = Path(agent_field)
    if p.suffix == ".md":
        return p.stem
    return agent_field


def _is_dormant(repo_root: Path, slug: str, *, days: int = 14) -> bool:
    try:
        campaigns = safe_join(repo_root, "clients", slug, "campaigns")
        runs = safe_join(repo_root, "clients", slug, "runs")
    except Exception:
        return False
    cutoff = dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=days)

    def fresh(d: Path, glob: str) -> bool:
        if not d.is_dir():
            return False
        for p in d.glob(glob):
            if p.is_file():
                mtime = dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.UTC)
                if mtime > cutoff:
                    return True
        return False

    return not (fresh(campaigns, "*.md") or fresh(runs, "*.md"))


def _log_skip(repo_root: Path, routine: str, slug: str, reason: str) -> None:
    today = dt.datetime.now(tz=dt.UTC).strftime("%Y-%m-%d")
    path = safe_join(repo_root, "runs", today, "skipped.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{routine}\t{slug}\t{reason}\n")


def _gather_owners(repo_root: Path) -> Iterable[str]:
    """Pull unique owner_slack_id values from all clients."""
    owners: set[str] = set()
    for slug in list_clients(repo_root):
        try:
            cli = load_client(repo_root, slug)
        except ClientLoadError:
            continue
        if cli.owner_slack_id:
            owners.add(cli.owner_slack_id)
    return owners
