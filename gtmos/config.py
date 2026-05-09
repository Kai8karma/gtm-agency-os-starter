"""Configuration — env loading, required-var enforcement, repo-root resolution.

Single source of truth for runtime configuration. Read once at startup.
Missing required vars raise ConfigError with a clear remediation message —
never silent failure.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Frozen view of runtime configuration. Build via `Settings.load()`."""

    repo_root: Path

    anthropic_api_key: str
    agent_model: str
    judge_model: str

    slack_bot_token: str | None
    slack_signing_secret: str | None
    slack_team_id: str | None
    slack_sig_replay_window_s: int

    hubspot_token: str | None
    lemlist_api_key: str | None
    notion_token: str | None
    notion_tasks_db_id: str | None

    task_store: str
    tasks_db_path: Path

    agent_timeout_s: int
    judge_timeout_s: int

    log_level: str

    required_for: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def load(cls, *, env_file: str | os.PathLike[str] | None = None,
             require: tuple[str, ...] = ()) -> Settings:
        """Load settings from environment.

        Args:
            env_file: optional path to .env file. Default: search upward
                from CWD for a `.env`.
            require: extra capability requirements, e.g. ``("slack",)`` or
                ``("hubspot",)``. Each capability has its own required-vars set;
                if any are missing, ConfigError is raised. ``"llm"`` is always
                required.
        """
        if env_file is not None:
            load_dotenv(env_file, override=False)
        else:
            load_dotenv(override=False)

        # ---- determine final capability set up front -----------------------
        # LLM is always required at this layer.
        require_set: set[str] = set(require) | {"llm"}

        task_store = os.environ.get("GTMOS_TASK_STORE", "sqlite").strip().lower()
        if task_store not in {"sqlite", "notion"}:
            raise ConfigError(
                f"GTMOS_TASK_STORE must be 'sqlite' or 'notion' (got {task_store!r})"
            )
        if task_store == "notion":
            require_set.add("notion")

        missing: list[str] = []

        def need(key: str, capability: str) -> str:
            value = os.environ.get(key, "").strip()
            if not value and capability in require_set:
                missing.append(key)
            return value

        # ---- llm -----------------------------------------------------------
        anthropic_key = need("ANTHROPIC_API_KEY", capability="llm")
        agent_model = os.environ.get("GTMOS_AGENT_MODEL", "claude-sonnet-4-6").strip()
        judge_model = os.environ.get("GTMOS_JUDGE_MODEL", "claude-haiku-4-5").strip()

        # ---- repo root -----------------------------------------------------
        env_root = os.environ.get("GTMOS_REPO_ROOT", "").strip()
        repo_root = Path(env_root).resolve() if env_root else _resolve_repo_root()
        if not repo_root.is_dir():
            raise ConfigError(
                f"GTMOS_REPO_ROOT={repo_root!s} does not exist or is not a directory"
            )

        # ---- slack (capability-gated) --------------------------------------
        slack_bot_token = need("SLACK_BOT_TOKEN", capability="slack") or None
        slack_signing_secret = need("SLACK_SIGNING_SECRET", capability="slack") or None
        slack_team_id = os.environ.get("SLACK_TEAM_ID", "").strip() or None
        try:
            slack_sig_replay_window_s = int(os.environ.get("SLACK_SIG_REPLAY_WINDOW_S", "300"))
        except ValueError as e:
            raise ConfigError(f"SLACK_SIG_REPLAY_WINDOW_S must be an integer: {e}") from e
        if slack_sig_replay_window_s <= 0 or slack_sig_replay_window_s > 600:
            raise ConfigError(
                "SLACK_SIG_REPLAY_WINDOW_S must be in (0, 600] — Slack rejects > 5 min"
            )

        # ---- connectors (capability-gated) ---------------------------------
        hubspot_token = need("HUBSPOT_PRIVATE_APP_TOKEN", capability="hubspot") or None
        lemlist_api_key = need("LEMLIST_API_KEY", capability="lemlist") or None
        notion_token = need("NOTION_TOKEN", capability="notion") or None
        notion_db_id = need("NOTION_TASKS_DB_ID", capability="notion") or None

        env_db = os.environ.get("GTMOS_TASKS_DB", "").strip()
        tasks_db_path = (
            Path(env_db).resolve() if env_db
            else (repo_root / "runs" / ".state" / "tasks.db").resolve()
        )

        # ---- timeouts ------------------------------------------------------
        try:
            agent_timeout_s = int(os.environ.get("GTMOS_AGENT_TIMEOUT_S", "300"))
            judge_timeout_s = int(os.environ.get("GTMOS_JUDGE_TIMEOUT_S", "120"))
        except ValueError as e:
            raise ConfigError(f"timeout env vars must be integers: {e}") from e
        if not (0 < agent_timeout_s <= 1800 and 0 < judge_timeout_s <= 600):
            raise ConfigError("timeouts out of accepted range (agent ≤ 1800s, judge ≤ 600s)")

        log_level = os.environ.get("GTMOS_LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError(f"GTMOS_LOG_LEVEL invalid: {log_level!r}")

        # ---- final required-var check --------------------------------------
        # Re-evaluate `missing` against `require` — we collected eagerly above.
        if missing:
            raise ConfigError(
                "Missing required environment variables: "
                + ", ".join(sorted(set(missing)))
                + ". See .env.example for descriptions."
            )

        return cls(
            repo_root=repo_root,
            anthropic_api_key=anthropic_key,
            agent_model=agent_model,
            judge_model=judge_model,
            slack_bot_token=slack_bot_token,
            slack_signing_secret=slack_signing_secret,
            slack_team_id=slack_team_id,
            slack_sig_replay_window_s=slack_sig_replay_window_s,
            hubspot_token=hubspot_token,
            lemlist_api_key=lemlist_api_key,
            notion_token=notion_token,
            notion_tasks_db_id=notion_db_id,
            task_store=task_store,
            tasks_db_path=tasks_db_path,
            agent_timeout_s=agent_timeout_s,
            judge_timeout_s=judge_timeout_s,
            log_level=log_level,
            required_for=tuple(sorted(require_set)),
        )

    def configure_logging(self) -> None:
        """Configure root logging once. Safe to call multiple times."""
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format="%(asctime)s %(levelname)s %(name)s — %(message)s",
            force=True,
        )
        # Never log secrets. Filter installs once.
        logging.getLogger().addFilter(_SecretRedactor(self))


def _resolve_repo_root() -> Path:
    """Walk up from CWD looking for CLAUDE.md (the doctrine root)."""
    cur = Path.cwd().resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / "CLAUDE.md").is_file():
            return candidate
    raise ConfigError(
        "Could not resolve GTMOS_REPO_ROOT — set the env var or run from inside the repo"
    )


class _SecretRedactor(logging.Filter):
    """Redact known secrets from log records before they leave the process."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._secrets = {
            s for s in (
                settings.anthropic_api_key,
                settings.slack_bot_token,
                settings.slack_signing_secret,
                settings.hubspot_token,
                settings.lemlist_api_key,
                settings.notion_token,
            )
            if s and len(s) >= 8
        }

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        msg = record.getMessage()
        for s in self._secrets:
            if s in msg:
                record.msg = msg.replace(s, "<redacted>")
                record.args = ()
        return True
