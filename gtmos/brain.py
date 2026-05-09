"""kai-brain bridge — the outcome flywheel substrate.

The brain CLI lives at ``~/.local/bin/brain`` (symlink to ``~/kai-brain/brain``).
We invoke it as a subprocess for every operation. Why subprocess instead of
direct DB access:

  * The brain owns its own confidence / decay / outcome rules; bypassing the
    CLI risks divergence (per memory #621 — outcome-win must adjust decay_rate,
    not just confidence).
  * The brain maintains a separate process with its own logging + telemetry.
  * It enforces source-trust ceilings and gate logic that we don't want to
    re-implement.

This module is the only place gtmos talks to the brain. Anyone else routes
through ``BrainBridge``.

Memory citations:
  * #694 — GTM OS architecture catalog (the spec we're implementing).
  * #225 — Strat-Agent Model (humans close, AI agents scaffold).
  * #570 — USE not BUILD; deploy real, not speculate.
  * #621 — outcome adjusts decay_rate, not just confidence.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gtmos.security import redact

logger = logging.getLogger(__name__)


class BrainError(RuntimeError):
    """Raised when the brain CLI call fails."""


class BrainUnavailable(BrainError):
    """Raised when the brain CLI is not installed or not reachable."""


# ----- helpers --------------------------------------------------------------


_USAGE_ID_RE = re.compile(r"\b(\d+)\b")


def _binary() -> str:
    """Resolve the brain CLI binary; environment override wins for tests."""
    override = os.environ.get("GTMOS_BRAIN_BIN", "").strip()
    if override:
        p = Path(override)
        if not p.is_file() or not os.access(override, os.X_OK):
            raise BrainUnavailable(
                f"GTMOS_BRAIN_BIN={override!r} is not an executable file"
            )
        return override
    found = shutil.which("brain")
    if not found:
        raise BrainUnavailable(
            "brain CLI not on PATH; set GTMOS_BRAIN_BIN or skip BrainBridge."
        )
    return found


def _run(
    args: list[str],
    *,
    timeout_s: int = 30,
    capture_json: bool = False,
) -> tuple[str, str, int]:
    """Run the brain CLI with sanitized args, return (stdout, stderr, rc)."""
    bin_path = _binary()
    cmd = [bin_path, *args]
    # Defensive: every arg must be a string and must NOT start with `-` unless
    # it's an explicit subcommand flag we're choosing (which we control).
    for a in args:
        if not isinstance(a, str):
            raise BrainError(f"brain args must be strings; got {type(a).__name__}")
    env = {
        "HOME": os.environ.get("HOME", ""),
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "TERM": os.environ.get("TERM", "xterm-256color"),
    }
    if capture_json:
        env["BRAIN_OUTPUT"] = "json"

    try:
        proc = subprocess.run(  # nosec B603  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise BrainError(f"brain {args[0] if args else '?'} timed out after {timeout_s}s") from e
    except FileNotFoundError as e:
        raise BrainUnavailable(f"brain CLI missing: {e}") from e

    return proc.stdout, proc.stderr, proc.returncode


# ----- public API -----------------------------------------------------------


@dataclass(frozen=True)
class MemoryHit:
    id: int
    title: str
    preview: str
    confidence: float
    source_trust: str

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> MemoryHit:
        return cls(
            id=int(obj.get("id", 0)),
            title=str(obj.get("title", ""))[:200],
            preview=str(obj.get("preview", ""))[:600],
            confidence=float(obj.get("confidence", 0.0)),
            source_trust=str(obj.get("source_trust", "")),
        )


@dataclass
class BrainBridge:
    """Subprocess wrapper around the brain CLI.

    All methods raise ``BrainError`` (or ``BrainUnavailable``) on failure.
    Callers should treat brain calls as best-effort: a brain failure should
    NOT block a pipeline — the agent run continues with a logged warning.
    """

    timeout_s: int = 30

    @classmethod
    def discover(cls) -> BrainBridge | None:
        """Return a bridge if the brain CLI is available, else None."""
        try:
            _binary()
        except BrainUnavailable:
            return None
        return cls()

    # ---- read paths -------------------------------------------------------

    def search(self, query: str, *, limit: int = 5, min_confidence: float = 0.5) -> list[MemoryHit]:
        if not isinstance(query, str) or not query.strip():
            raise BrainError("query required")
        if limit < 1 or limit > 50:
            raise BrainError("limit must be 1..50")
        if not 0.0 <= min_confidence <= 1.0:
            raise BrainError("min_confidence must be in [0,1]")
        out, err, rc = _run(["search", query, "--limit", str(limit)],
                            timeout_s=self.timeout_s, capture_json=True)
        if rc != 0:
            raise BrainError(f"brain search failed (rc={rc}): {redact(err.strip())}")
        hits = _parse_search_output(out)
        return [h for h in hits if h.confidence >= min_confidence]

    def voice_card(self) -> str:
        out, err, rc = _run(["voice"], timeout_s=self.timeout_s)
        if rc != 0:
            raise BrainError(f"brain voice failed (rc={rc}): {redact(err.strip())}")
        return out.strip()

    # ---- write paths ------------------------------------------------------

    def used(self, memory_id: int, context: str = "") -> int:
        if not isinstance(memory_id, int) or memory_id < 1:
            raise BrainError(f"memory_id must be positive int, got {memory_id!r}")
        # Bound + redact the context — never let secrets leak through brain logs.
        ctx = redact(context)[:280]
        out, err, rc = _run(
            ["used", str(memory_id), ctx],
            timeout_s=self.timeout_s,
        )
        if rc != 0:
            raise BrainError(f"brain used failed (rc={rc}): {redact(err.strip())}")
        return _extract_usage_id(out)

    def outcome(self, usage_id: int, verdict: str, note: str = "") -> None:
        if verdict not in {"win", "loss", "neutral"}:
            raise BrainError(f"verdict must be win|loss|neutral, got {verdict!r}")
        if not isinstance(usage_id, int) or usage_id < 1:
            raise BrainError(f"usage_id must be positive int, got {usage_id!r}")
        n = redact(note)[:200]
        args = ["outcome", str(usage_id), verdict]
        if n:
            args.append(n)
        _out, err, rc = _run(args, timeout_s=self.timeout_s)
        if rc != 0:
            raise BrainError(f"brain outcome failed (rc={rc}): {redact(err.strip())}")
        logger.info("brain outcome %s -> %s", usage_id, verdict)

    def remember(self, mem_type: str, title: str, content: str) -> int | None:
        """Persist a new memory. Returns the new memory id when parseable."""
        allowed = {"discovery", "feedback", "decision", "project", "user", "session", "reference"}
        if mem_type not in allowed:
            raise BrainError(f"mem_type {mem_type!r} not in {allowed}")
        if not title.strip() or not content.strip():
            raise BrainError("title and content required")
        out, err, rc = _run(
            ["remember", mem_type, title.strip()[:160], redact(content).strip()],
            timeout_s=self.timeout_s,
        )
        if rc != 0:
            raise BrainError(f"brain remember failed (rc={rc}): {redact(err.strip())}")
        m = re.search(r"#?(\d+)", out)
        return int(m.group(1)) if m else None


# ----- parsing helpers ------------------------------------------------------


def _parse_search_output(stdout: str) -> list[MemoryHit]:
    """Brain CLI may emit JSON or plain. Prefer JSON when possible."""
    s = stdout.strip()
    if not s:
        return []
    if s.startswith(("[", "{")):
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            return _parse_plain_search(s)
        if isinstance(data, dict) and "results" in data:
            data = data["results"]
        if isinstance(data, list):
            out: list[MemoryHit] = []
            for item in data:
                if isinstance(item, dict):
                    out.append(MemoryHit.from_json(item))
            return out
    return _parse_plain_search(s)


_PLAIN_LINE_RE = re.compile(
    r"#(\d+)\s+\[(\d+\.\d+)\]\s+(.+?)(?:\s+(?:\(.+?\))?)?\s*$"
)


def _parse_plain_search(stdout: str) -> list[MemoryHit]:
    out: list[MemoryHit] = []
    for line in stdout.splitlines():
        m = _PLAIN_LINE_RE.match(line.strip())
        if m:
            try:
                out.append(
                    MemoryHit(
                        id=int(m.group(1)),
                        title=m.group(3).strip()[:200],
                        preview="",
                        confidence=float(m.group(2)),
                        source_trust="",
                    )
                )
            except (TypeError, ValueError):
                continue
    return out


def _extract_usage_id(stdout: str) -> int:
    """The brain CLI prints something like 'usage 42 logged'. Pull the id."""
    for token in stdout.split():
        if token.isdigit():
            return int(token)
    m = _USAGE_ID_RE.search(stdout)
    if m:
        return int(m.group(1))
    raise BrainError(f"brain used: could not parse usage id from {stdout!r}")


__all__ = [
    "BrainBridge",
    "BrainError",
    "BrainUnavailable",
    "MemoryHit",
]
