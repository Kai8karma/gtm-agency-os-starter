"""Task store tests — covers schema, parameterized queries, throttling."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from gtmos.tasks import TaskStore, TaskStoreError, dispatch_overdue_dms


@pytest.fixture
def store(tmp_path: Path) -> TaskStore:
    return TaskStore(db_path=tmp_path / "tasks.db")


def _later(offset_hours: int) -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC) + dt.timedelta(hours=offset_hours)


class TestAddTask:
    def test_basic_add(self, store: TaskStore) -> None:
        t = store.add(
            title="Send proposal to acme",
            owner_slack_id="U0KAI",
            client_slug="acme",
            due_at=_later(48),
        )
        assert t.id > 0
        assert t.status == "open"
        assert t.title == "Send proposal to acme"

    def test_owner_must_start_with_U(self, store: TaskStore) -> None:
        with pytest.raises(TaskStoreError):
            store.add(
                title="x",
                owner_slack_id="kai",
                client_slug="acme",
                due_at=_later(1),
            )

    def test_invalid_status_rejected(self, store: TaskStore) -> None:
        with pytest.raises(TaskStoreError):
            store.add(
                title="x",
                owner_slack_id="U0K",
                client_slug="acme",
                due_at=_later(1),
                status="snoozed",
            )

    def test_naive_datetime_rejected(self, store: TaskStore) -> None:
        with pytest.raises(TaskStoreError, match="timezone-aware"):
            store.add(
                title="x",
                owner_slack_id="U0K",
                client_slug="acme",
                due_at=dt.datetime.now(),
            )

    def test_bad_slug_rejected(self, store: TaskStore) -> None:
        from gtmos.security import InvalidSlugError

        with pytest.raises(InvalidSlugError):
            store.add(
                title="x",
                owner_slack_id="U0K",
                client_slug="../escape",
                due_at=_later(1),
            )


class TestSqlInjection:
    def test_title_with_quotes_is_safe(self, store: TaskStore) -> None:
        nasty = "Robert'); DROP TABLE tasks;--"
        t = store.add(
            title=nasty,
            owner_slack_id="U0K",
            client_slug="acme",
            due_at=_later(2),
        )
        # Table still exists, value stored verbatim.
        roundtrip = store.get(t.id)
        assert roundtrip.title == nasty
        assert store.list_by_owner("U0K") != []


class TestStatusTransitions:
    def test_update_status(self, store: TaskStore) -> None:
        t = store.add(
            title="x",
            owner_slack_id="U0K",
            client_slug="acme",
            due_at=_later(1),
        )
        store.update_status(t.id, "done")
        assert store.get(t.id).status == "done"

    def test_invalid_status_update_rejected(self, store: TaskStore) -> None:
        t = store.add(
            title="x",
            owner_slack_id="U0K",
            client_slug="acme",
            due_at=_later(1),
        )
        with pytest.raises(TaskStoreError):
            store.update_status(t.id, "snoozed")


class TestOverdueAndThrottle:
    def test_overdue_includes_past_due(self, store: TaskStore) -> None:
        store.add(
            title="late one",
            owner_slack_id="U0K",
            client_slug="acme",
            due_at=_later(-48),
        )
        overdue = store.overdue()
        assert len(overdue) == 1

    def test_done_tasks_skipped(self, store: TaskStore) -> None:
        t = store.add(
            title="late and done",
            owner_slack_id="U0K",
            client_slug="acme",
            due_at=_later(-48),
        )
        store.update_status(t.id, "done")
        assert store.overdue() == []

    def test_throttle_skips_recently_dmed(self, store: TaskStore) -> None:
        t = store.add(
            title="late",
            owner_slack_id="U0K",
            client_slug="acme",
            due_at=_later(-48),
        )
        store.mark_dm_sent(t.id)
        # Within throttle window — no DM should be planned.
        assert dispatch_overdue_dms(store) == []

    def test_throttle_releases_after_window(self, store: TaskStore) -> None:
        t = store.add(
            title="late",
            owner_slack_id="U0K",
            client_slug="acme",
            due_at=_later(-72),
        )
        # Mark DM sent 30h ago — beyond default 24h throttle.
        store.mark_dm_sent(t.id, when=_later(-30))
        plan = dispatch_overdue_dms(store)
        assert len(plan) == 1
        assert plan[0].task_id == t.id
        assert plan[0].days_late >= 1


class TestSchemaIdempotence:
    def test_double_init_is_safe(self, tmp_path: Path) -> None:
        TaskStore(db_path=tmp_path / "t.db")
        TaskStore(db_path=tmp_path / "t.db")  # no error
