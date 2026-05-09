"""Skill bridge — invoke installed Claude Code skills as sub-agents.

Pattern recognized via brain neurons:
  * #199 (jxnl) — single agent over multi.
  * #376 (anthropic-eng) — sub-agent architectures: specialized agents handle
    focused tasks with condensed output.
  * #225 (kai) — Strat-Agent model: scaffold via skill calls, humans close.

Skills already authored that map to GTM OS pipelines:

  GTM operations:
    sales:account-research, sales:call-prep, sales:pipeline-review,
    sales:draft-outreach, sales:forecast, sales:call-summary
    common-room:account-research, common-room:contact-research,
    common-room:compose-outreach, common-room:prospect
    apollo:enrich-lead, apollo:prospect, apollo:sequence-load
    kai-gtm-engineer:contact-intel, kai-gtm-engineer:gtm-daily-brief,
    kai-gtm-engineer:brain-query
  Brand + voice:
    brand-voice:brand-voice-enforcement, brand-voice:guideline-generation
  Eval + reliability:
    eval-harness, eval-loop, verification-loop, dual-review
  Brain + memory:
    brain, learn, checkpoint, brain-sync

Most skills are not callable as functions in this Python runtime — they're
invoked via Claude Code subagents. This bridge records the *intent* to call
a skill, persists it as a structured task, and provides a CLI hook so an
operator (or a Claude Code session) can run the queued tasks.

For skills that DO have CLI entrypoints (e.g. ``brain ...``), we shell out
directly via the same subprocess pattern as ``gtmos.brain``.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from gtmos.config import Settings
from gtmos.security import redact, safe_join, validate_slug

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillRequest:
    """A queued request to invoke a skill in a future session."""

    skill: str  # e.g. "sales:account-research"
    args: dict[str, object] = field(default_factory=dict)
    client_slug: str | None = None
    requested_by: str = "gtmos"
    requested_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(tz=dt.UTC))

    def as_jsonable(self) -> dict[str, object]:
        return {
            "skill": self.skill,
            "args": self.args,
            "client_slug": self.client_slug,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at.isoformat(timespec="seconds"),
        }


@dataclass
class SkillBridge:
    """Queues skill invocations + executes the ones we can run inline."""

    settings: Settings

    # ---- queueing ----------------------------------------------------------

    def queue(self, request: SkillRequest) -> Path:
        """Persist a skill request as a JSON file under ``runs/.state/skill-queue/``."""
        if not isinstance(request.skill, str) or ":" not in request.skill or len(request.skill) > 80:
            raise ValueError(f"skill must look like 'plugin:skill', got {request.skill!r}")
        if request.client_slug is not None:
            validate_slug(request.client_slug, allow_underscore_prefix=True)

        queue_dir = safe_join(self.settings.repo_root, "runs", ".state", "skill-queue")
        queue_dir.mkdir(parents=True, exist_ok=True)
        ts = request.requested_at.strftime("%Y%m%dT%H%M%S")
        slug = (request.client_slug or "_") + "-" + request.skill.replace(":", "_")
        path = queue_dir / f"{ts}-{slug}.json"
        path.write_text(
            json.dumps(request.as_jsonable(), indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("queued skill %s for client=%s", request.skill, request.client_slug or "-")
        return path

    def list_pending(self) -> list[Path]:
        queue_dir = safe_join(self.settings.repo_root, "runs", ".state", "skill-queue")
        if not queue_dir.is_dir():
            return []
        return sorted(queue_dir.glob("*.json"))

    # ---- inline execution: only for skills with a real CLI -----------------

    _CLI_BACKED: frozenset[str] = frozenset({"brain"})

    def can_run_inline(self, skill: str) -> bool:
        prefix = skill.split(":", 1)[0]
        return prefix in self._CLI_BACKED and shutil.which(prefix) is not None

    def run_inline(self, request: SkillRequest, *, timeout_s: int = 30) -> str:
        """Run an inline skill via subprocess. Limited to ``_CLI_BACKED`` whitelist."""
        prefix = request.skill.split(":", 1)[0]
        if prefix not in self._CLI_BACKED:
            raise PermissionError(
                f"skill {request.skill!r} is not in the inline-run whitelist; "
                f"queue it with .queue() instead"
            )
        if not shutil.which(prefix):
            raise FileNotFoundError(f"{prefix} CLI not on PATH")

        if request.skill == "brain:search":
            q = str(request.args.get("query", "")).strip()
            limit = int(request.args.get("limit", 5))
            if not q:
                raise ValueError("brain:search requires args.query")
            from gtmos.brain import BrainBridge

            br = BrainBridge(timeout_s=timeout_s)
            hits = br.search(q, limit=max(1, min(50, limit)))
            return json.dumps([h.__dict__ for h in hits], default=str)

        raise NotImplementedError(
            f"inline runner not wired for {request.skill!r} - add a clause or queue it"
        )


def queue_skill(
    settings: Settings,
    skill: str,
    args: dict[str, object],
    *,
    client_slug: str | None = None,
    requested_by: str = "gtmos",
) -> Path:
    """Convenience wrapper to queue a skill request from anywhere."""
    bridge = SkillBridge(settings=settings)
    redacted = {k: redact(str(v))[:1000] for k, v in args.items()}
    return bridge.queue(
        SkillRequest(
            skill=skill,
            args=redacted,
            client_slug=client_slug,
            requested_by=requested_by,
        )
    )


__all__ = ["SkillBridge", "SkillRequest", "queue_skill"]
