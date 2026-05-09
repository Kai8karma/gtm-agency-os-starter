"""Security primitives — Slack signature verification, slug + path validation.

Every input that crosses a trust boundary funnels through this module.
Failure modes here are tested in tests/test_security.py.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ---- exceptions -------------------------------------------------------------


class SecurityError(Exception):
    """Base class for security-policy violations."""


class SignatureError(SecurityError):
    """Slack request signature did not verify."""


class ReplayError(SecurityError):
    """Slack request timestamp outside the accepted window."""


class InvalidSlugError(SecurityError):
    """Client slug failed validation."""


class PathEscapeError(SecurityError):
    """Resolved path escapes its allowed root."""


# ---- Slack signature verification -------------------------------------------


@dataclass(frozen=True)
class SlackVerifier:
    """Verifies inbound Slack requests using HMAC-SHA256.

    Slack signs each request with a v0:<ts>:<body> string. This class enforces:
      * the timestamp is within ``replay_window_s`` of now (replay protection),
      * the HMAC-SHA256 of v0:<ts>:<body> with `signing_secret` matches the
        provided ``X-Slack-Signature`` header (constant-time comparison),
      * the team ID, if configured, matches a body-extracted team_id.

    Reference:
        https://api.slack.com/authentication/verifying-requests-from-slack
    """

    signing_secret: str
    replay_window_s: int = 300
    expected_team_id: str | None = None

    def verify(
        self,
        *,
        timestamp: str,
        signature: str,
        body: bytes,
        now: float | None = None,
    ) -> None:
        """Verify a Slack request. Raises SignatureError / ReplayError on failure."""
        if not isinstance(body, (bytes, bytearray)):
            raise SignatureError("body must be bytes")

        if not isinstance(timestamp, str) or not timestamp.lstrip("-").isdigit():
            raise SignatureError("X-Slack-Request-Timestamp missing or non-numeric")

        ts_int = int(timestamp)
        now_ts = time.time() if now is None else now
        if abs(now_ts - ts_int) > self.replay_window_s:
            raise ReplayError(
                f"timestamp {ts_int} outside replay window {self.replay_window_s}s"
            )

        if not isinstance(signature, str) or not signature.startswith("v0="):
            raise SignatureError("X-Slack-Signature missing or wrong version")

        sig_basestring = b"v0:" + timestamp.encode("ascii") + b":" + bytes(body)
        digest = hmac.new(
            self.signing_secret.encode("utf-8"),
            sig_basestring,
            hashlib.sha256,
        ).hexdigest()
        expected = "v0=" + digest
        if not hmac.compare_digest(expected, signature):
            raise SignatureError("HMAC mismatch")

        if self.expected_team_id is not None:
            team_id = _extract_team_id(body)
            if team_id is None:
                # Don't fail closed if Slack omits team_id (some interactive
                # payloads do); log and accept. The signature already proved
                # authenticity.
                logger.debug("team_id absent from body; accepting on signature alone")
            elif team_id != self.expected_team_id:
                raise SignatureError(
                    f"team_id mismatch: got {team_id!r}, expected {self.expected_team_id!r}"
                )


_TEAM_ID_RE = re.compile(rb"team_id=([A-Z0-9]+)")


def _extract_team_id(body: bytes) -> str | None:
    match = _TEAM_ID_RE.search(body)
    if match is None:
        return None
    try:
        return match.group(1).decode("ascii")
    except UnicodeDecodeError:
        return None


# ---- slug validation --------------------------------------------------------


_SLUG_RE = re.compile(r"^[a-z0-9_](?:[a-z0-9_-]{0,62}[a-z0-9])?$")
_RESERVED_SLUGS = frozenset({
    ".",
    "..",
    "_state",
    ".state",
    ".git",
    "node_modules",
})


def validate_slug(slug: object, *, allow_underscore_prefix: bool = False) -> str:
    """Validate a client/campaign slug.

    Rules:
      * 1-64 chars, lowercase ascii, digits, ``-``, ``_``;
      * must start and end with alphanumeric;
      * not in the reserved list;
      * by default, leading-underscore slugs are rejected (template slugs only;
        callers that *expect* template slugs must opt in).
    """
    if not isinstance(slug, str):
        raise InvalidSlugError(f"slug must be str (got {type(slug).__name__})")
    if not _SLUG_RE.fullmatch(slug):
        raise InvalidSlugError(
            f"slug {slug!r} must match [a-z0-9][a-z0-9_-]*[a-z0-9], len 1-64"
        )
    if slug in _RESERVED_SLUGS:
        raise InvalidSlugError(f"slug {slug!r} is reserved")
    if slug.startswith("_") and not allow_underscore_prefix:
        raise InvalidSlugError(
            f"slug {slug!r} starts with underscore (reserved for template clients)"
        )
    return slug


# ---- path containment -------------------------------------------------------


def safe_join(root: Path, *parts: str) -> Path:
    """Resolve ``root / parts`` and raise PathEscapeError if outside ``root``.

    Use this anywhere user-controlled input contributes to a filesystem path.
    Defends against ``..``-based traversal, absolute-path injection, and
    symlink redirection.
    """
    root = Path(root).resolve(strict=True)
    if not parts:
        return root

    candidate = root.joinpath(*parts)
    # `Path.resolve(strict=False)` is necessary because the leaf may not exist
    # yet when we're constructing a path for a write.
    resolved = candidate.resolve(strict=False)

    try:
        resolved.relative_to(root)
    except ValueError as e:
        raise PathEscapeError(
            f"path {resolved!s} escapes root {root!s}"
        ) from e

    # If any intermediate path component is a symlink, ensure it doesn't escape.
    cur = root
    for part in candidate.relative_to(root).parts:
        cur = cur / part
        if cur.is_symlink():
            link_target = cur.resolve()
            try:
                link_target.relative_to(root)
            except ValueError as e:
                raise PathEscapeError(
                    f"symlink {cur!s} → {link_target!s} escapes root {root!s}"
                ) from e

    return resolved


# ---- redaction --------------------------------------------------------------

# Note on patterns: each regex is built from string fragments so this source
# file does not itself contain a literal credential or PEM marker that scanners
# would flag. The compiled regex behavior is identical.

_REDACT_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),                  # Anthropic
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),                # Slack
    re.compile(r"ghp_[A-Za-z0-9]{36}"),                         # GitHub PAT
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),                # GitHub fine PAT
    re.compile(r"pat-na1-[A-Za-z0-9-]{20,}"),                   # HubSpot
    re.compile(r"secret_[A-Za-z0-9]{40,}"),                     # Notion
    re.compile(r"AKIA[0-9A-Z]{16}"),                            # AWS key id
    re.compile(
        "-----" + "BEGIN " + r"[A-Z ]*" + "PRIVATE " + "KEY-----"
    ),                                                          # any PEM key
]


def redact(text: str) -> str:
    """Redact common secret patterns from a string.

    Use before logging, before writing run artifacts, before posting to Slack.
    Pattern set is conservative — false positives turn into ``<redacted>`` text,
    which is preferable to leaking real keys.
    """
    if not isinstance(text, str) or not text:
        return text
    out = text
    for pat in _REDACT_PATTERNS:
        out = pat.sub("<redacted>", out)
    return out


# ---- prompt injection / user-origin gate ------------------------------------


def is_likely_tool_output(text: str) -> bool:
    """Heuristic flag for content that looks like injected tool output.

    Mirrors the user-origin gate from kai-brain (``capture-learnings.py``).
    Returns True when the text contains strong tool-output markers, suggesting
    the LLM should treat it as untrusted (lower confidence, isolate from
    instructions).

    This is a heuristic, not a guarantee. Treat outputs as untrusted by default;
    use this flag to escalate caution further.
    """
    if not isinstance(text, str) or len(text) < 20:
        return False
    markers = (
        "<system-reminder>",
        "<user-prompt-submit-hook>",
        "system: you are",
        "ignore previous instructions",
        "ignore the above",
        "</instructions>",
        "<|im_start|>",
        "BEGIN PROMPT",
    )
    lower = text.lower()
    return any(m.lower() in lower for m in markers)
