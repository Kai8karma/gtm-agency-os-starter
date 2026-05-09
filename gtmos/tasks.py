"""Task store + closed-loop cron (Pattern 10).

Default backend: sqlite (no external deps, deterministic, local).
Notion backend stub provided as an extension point — not wired in this MVP
because it would require a live Notion workspace to test.

Schema (sqlite):

    CREATE TABLE tasks (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        title         TEXT NOT NULL,
        owner_slack_id TEXT NOT NULL,
        client_slug   TEXT NOT NULL,
        due_at        TEXT NOT NULL,           -- ISO-8601, UTC
        status        TEXT NOT NULL DEFAULT 'open',
        last_dm_at    TEXT,                    -- ISO-8601, UTC
        created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX tasks_due_status_idx ON tasks(status, due_at);
    CREATE INDEX tasks_owner_idx     ON tasks(owner_slack_id);

All queries are parameterized; user input never reaches the SQL string.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from gtmos.security import validate_slug

logger = logging.getLogger(__name__)

_VALID_STATUSES = ("open", "in_progress", "done", "cancelled")
_DM_THROTTLE_HOURS = 24


class TaskStoreError(Exception):
    pass


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    owner_slack_id: str
    client_slug: str
    due_at: dt.datetime
    status: str
    last_dm_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime


@dataclass(frozen=True)
class OverdueDM:
    """Result of a single closed-loop DM dispatch (Pattern 10)."""

    task_id: int
    owner_slack_id: str
    title: str
    days_late: int


@dataclass
class TaskStore:
    """sqlite-backed task store. One file per repo (default in runs/.state/tasks.db)."""

    db_path: Path

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._cx() as cx:
            cx.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    title         TEXT NOT NULL,
                    owner_slack_id TEXT NOT NULL,
                    client_slug   TEXT NOT NULL,
                    due_at        TEXT NOT NULL,
                    status        TEXT NOT NULL DEFAULT 'open',
                    last_dm_at    TEXT,
                    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS tasks_due_status_idx
                    ON tasks(status, due_at);
                CREATE INDEX IF NOT EXISTS tasks_owner_idx
                    ON tasks(owner_slack_id);
                """
            )

    # ---- connection plumbing -----------------------------------------------

    @contextmanager
    def _cx(self) -> Iterable[sqlite3.Connection]:
        cx = sqlite3.connect(
            self.db_path,
            detect_types=0,
            isolation_level=None,  # autocommit; we own transactions
            check_same_thread=False,
        )
        try:
            cx.execute("PRAGMA foreign_keys=ON;")
            cx.execute("PRAGMA journal_mode=WAL;")
            cx.row_factory = sqlite3.Row
            yield cx
        finally:
            cx.close()

    # ---- writes ------------------------------------------------------------

    def add(
        self,
        *,
        title: str,
        owner_slack_id: str,
        client_slug: str,
        due_at: dt.datetime,
        status: str = "open",
    ) -> Task:
        if not isinstance(title, str) or not title.strip():
            raise TaskStoreError("title required")
        if not isinstance(owner_slack_id, str) or not owner_slack_id.startswith("U"):
            raise TaskStoreError(f"owner_slack_id invalid: {owner_slack_id!r}")
        validate_slug(client_slug, allow_underscore_prefix=True)
        if status not in _VALID_STATUSES:
            raise TaskStoreError(f"status {status!r} not in {_VALID_STATUSES}")
        if due_at.tzinfo is None:
            raise TaskStoreError("due_at must be timezone-aware")

        with self._cx() as cx:
            cur = cx.execute(
                "INSERT INTO tasks (title, owner_slack_id, client_slug, due_at, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (title.strip(), owner_slack_id, client_slug, _iso(due_at), status),
            )
            task_id = cur.lastrowid
        return self.get(task_id)

    def update_status(self, task_id: int, status: str) -> Task:
        if status not in _VALID_STATUSES:
            raise TaskStoreError(f"status {status!r} not in {_VALID_STATUSES}")
        with self._cx() as cx:
            cx.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, _iso(_now()), task_id),
            )
        return self.get(task_id)

    def mark_dm_sent(self, task_id: int, *, when: dt.datetime | None = None) -> None:
        ts = _iso(when or _now())
        with self._cx() as cx:
            cx.execute(
                "UPDATE tasks SET last_dm_at = ?, updated_at = ? WHERE id = ?",
                (ts, ts, task_id),
            )

    # ---- reads -------------------------------------------------------------

    def get(self, task_id: int) -> Task:
        with self._cx() as cx:
            row = cx.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise TaskStoreError(f"task {task_id} not found")
        return _row_to_task(row)

    def list_by_owner(self, owner_slack_id: str) -> list[Task]:
        with self._cx() as cx:
            rows = cx.execute(
                "SELECT * FROM tasks WHERE owner_slack_id = ? "
                "AND status IN ('open', 'in_progress') "
                "ORDER BY due_at ASC",
                (owner_slack_id,),
            ).fetchall()
        return [_row_to_task(r) for r in rows]

    def overdue(
        self, *, now: dt.datetime | None = None, throttle_hours: int = _DM_THROTTLE_HOURS
    ) -> list[Task]:
        cutoff = (now or _now()).astimezone(dt.UTC)
        cutoff_iso = _iso(cutoff)
        throttle_cutoff_iso = _iso(cutoff - dt.timedelta(hours=throttle_hours))
        with self._cx() as cx:
            rows = cx.execute(
                "SELECT * FROM tasks "
                "WHERE status IN ('open', 'in_progress') "
                "AND due_at < ? "
                "AND (last_dm_at IS NULL OR last_dm_at < ?) "
                "ORDER BY due_at ASC",
                (cutoff_iso, throttle_cutoff_iso),
            ).fetchall()
        return [_row_to_task(r) for r in rows]


# ---- closed loop -----------------------------------------------------------


def dispatch_overdue_dms(
    store: TaskStore,
    *,
    now: dt.datetime | None = None,
    throttle_hours: int = _DM_THROTTLE_HOURS,
) -> list[OverdueDM]:
    """Plan-only step of the closed loop. Returns the list of DMs that *should*
    fire. Caller is responsible for the actual Slack send (so we don't couple
    the store to network IO).
    """
    when = (now or _now()).astimezone(dt.UTC)
    overdue = store.overdue(now=when, throttle_hours=throttle_hours)
    out: list[OverdueDM] = []
    for task in overdue:
        days_late = max(1, (when - task.due_at).days)
        out.append(
            OverdueDM(
                task_id=task.id,
                owner_slack_id=task.owner_slack_id,
                title=task.title,
                days_late=days_late,
            )
        )
    return out


# ---- helpers ---------------------------------------------------------------


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _iso(d: dt.datetime) -> str:
    return d.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=int(row["id"]),
        title=str(row["title"]),
        owner_slack_id=str(row["owner_slack_id"]),
        client_slug=str(row["client_slug"]),
        due_at=_parse(row["due_at"]),
        status=str(row["status"]),
        last_dm_at=_parse(row["last_dm_at"]) if row["last_dm_at"] else None,
        created_at=_parse(row["created_at"]),
        updated_at=_parse(row["updated_at"]),
    )


def _parse(s: str) -> dt.datetime:
    """Best-effort ISO/SQLite datetime parsing."""
    if not s:
        raise TaskStoreError("empty timestamp")
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        # SQLite default `CURRENT_TIMESTAMP` is "YYYY-MM-DD HH:MM:SS" with no tz.
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.UTC)
